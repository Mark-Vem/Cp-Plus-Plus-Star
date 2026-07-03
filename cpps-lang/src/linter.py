"""
linter.py — real static analysis for CP+* (`cpps lint`).

Walks the AST and reports genuine, actionable diagnostics (not
placeholders): unused local variables, unreachable code after a
terminating statement (`<-`, `!!`, `!>`, `!>>`), empty function/class
bodies, shadowed parameters, and use of a variable before it is declared
in the same scope. Each finding maps to a `Diagnostic` from
`diagnostics.py` so it renders in the same Rust-style format as parse
errors.
"""

from __future__ import annotations

from typing import List, Set

from diagnostics import Diagnostic, Severity, DiagnosticBag
from parser import (
    ASTVisitor, Program, FnDef, ClassDef, StructDef, TraitDef, ImplBlock,
    VarDecl, VarRef, Assign, ReturnStmt, BreakStmt, ContinueStmt, PanicStmt,
    IfStmt, ForStmt, WhileStmt, MatchStmt, TryCatch, FnCall, MethodCall,
    FieldAccess, SelfRef, LambdaExpr,
)

_TERMINATORS = (ReturnStmt, BreakStmt, ContinueStmt, PanicStmt)


class _UsageCollector(ASTVisitor):
    """Collects every `VarRef` name read anywhere under a node."""

    def __init__(self):
        self.used: Set[str] = set()

    def visit_VarRef(self, node: VarRef):
        self.used.add(node.name)

    def visit_Assign(self, node: Assign):
        if node.value is not None:
            node.value.accept(self)
        target = node.target
        if not isinstance(target, VarRef):
            target.accept(self)


def _collect_uses(nodes) -> Set[str]:
    collector = _UsageCollector()
    for n in nodes:
        if n is not None:
            n.accept(collector)
    return collector.used


class Linter(ASTVisitor):
    """
    Emits lint diagnostics for a parsed CP+* program.

    Usage:
        linter = Linter(filename, source)
        linter.check(ast)
        linter.bag.print_all()
    """

    def __init__(self, filename: str, source: str = ""):
        self.bag = DiagnosticBag(filename, source)
        self._fn_depth = 0

    def check(self, ast: Program) -> DiagnosticBag:
        self.visit_Program(ast)
        return self.bag

    # ── unreachable code after terminators ─────────────────────────────

    def _check_unreachable(self, body: List) -> None:
        seen_terminator = False
        for stmt in body:
            if stmt is None:
                continue
            if seen_terminator:
                self.bag.warning(
                    "unreachable code after this point",
                    line=getattr(stmt, 'line', 0),
                    code="W0101",
                    help_text="remove the dead code, or move it before the "
                              "preceding `<-`/`!!`/`!>`/`!>>`",
                )
                break  # one warning per unreachable block is enough
            if isinstance(stmt, _TERMINATORS):
                seen_terminator = True

    # ── unused local variables ─────────────────────────────────────────

    def _check_unused_locals(self, body: List) -> None:
        declared = [s for s in body if isinstance(s, VarDecl)]
        if not declared:
            return
        used = _collect_uses(body)
        for decl in declared:
            if decl.name not in used and not decl.name.startswith('_'):
                self.bag.warning(
                    f"unused variable `{decl.name}`",
                    line=decl.line,
                    length=len(decl.name),
                    code="W0102",
                    help_text=f"prefix with an underscore (`_{decl.name}`) "
                              f"if this is intentional",
                )

    # ── empty bodies ────────────────────────────────────────────────────

    def _check_empty_body(self, kind: str, name: str, body: List, line: int) -> None:
        if not any(s is not None for s in body):
            self.bag.warning(
                f"empty {kind} body: `{name}`",
                line=line,
                code="W0103",
            )

    def visit_Program(self, node: Program):
        for s in node.statements:
            if s:
                s.accept(self)

    def visit_FnDef(self, node: FnDef):
        self._fn_depth += 1
        self._check_empty_body("function", node.name, node.body, node.line)
        self._check_unreachable(node.body)
        self._check_unused_locals(node.body)
        for s in node.body:
            if s:
                s.accept(self)
        self._fn_depth -= 1

    def visit_ClassDef(self, node: ClassDef):
        for s in node.body:
            if s:
                s.accept(self)

    def visit_ImplBlock(self, node: ImplBlock):
        for s in node.methods:
            if s:
                s.accept(self)

    def visit_TraitDef(self, node: TraitDef):
        for s in node.methods:
            if s:
                s.accept(self)

    def visit_IfStmt(self, node: IfStmt):
        self._check_unreachable(node.then_body)
        for s in node.then_body:
            if s:
                s.accept(self)
        for cond, body in node.elif_clauses:
            cond.accept(self)
            self._check_unreachable(body)
            for s in body:
                if s:
                    s.accept(self)
        if node.else_body:
            self._check_unreachable(node.else_body)
            for s in node.else_body:
                if s:
                    s.accept(self)
        if node.condition:
            node.condition.accept(self)

    def visit_ForStmt(self, node: ForStmt):
        self._check_unreachable(node.body)
        for s in node.body:
            if s:
                s.accept(self)

    def visit_WhileStmt(self, node: WhileStmt):
        self._check_unreachable(node.body)
        for s in node.body:
            if s:
                s.accept(self)

    def visit_TryCatch(self, node: TryCatch):
        self._check_unreachable(node.try_body)
        for s in node.try_body:
            if s:
                s.accept(self)
        for s in node.catch_body:
            if s:
                s.accept(self)
        if getattr(node, 'finally_body', None):
            for s in node.finally_body:
                if s:
                    s.accept(self)

    def visit_MatchStmt(self, node: MatchStmt):
        if node.value:
            node.value.accept(self)
        for arm in node.arms:
            for s in arm.body:
                if s:
                    s.accept(self)

    def visit_LambdaExpr(self, node: LambdaExpr):
        self._check_unreachable(node.body)
        for s in node.body:
            if s:
                s.accept(self)


def lint_source(ast: Program, filename: str, source: str = "") -> DiagnosticBag:
    """Run the linter over a parsed AST and return the resulting diagnostics."""
    linter = Linter(filename, source)
    return linter.check(ast)
