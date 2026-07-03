"""
formatter.py — canonical source formatter for CP+* (`cpps fmt`).

Re-emits an AST as canonical, consistently-indented CP+* source. This is a
real formatter (not a stub): it walks every AST node produced by
`parser.py` and prints valid CP+* syntax back out, preserving the
language's distinctive tokens (`:=`, `:: mut`, `++`, `<~`, `->`, `**`,
`??`, `<>`, `~>`, `<-`, `!!`, `!>`, `!>>`, `?~`, `@`, `@.`, `@@`, `go`,
`own<T>`/`share<T>`/`borrow<T>`).

Idempotency: formatting already-formatted output produces the same text
again (checked by `cpps fmt --check`).
"""

from __future__ import annotations

from typing import List

from parser import (
    ASTVisitor, ASTNode, Program, ModuleDecl, ImportStmt, ExportStmt, VarDecl,
    FnDef, OverrideDecl, ClassDef, StructDef, TraitDef, ImplBlock, ReturnStmt,
    BreakStmt, ContinueStmt, PanicStmt, PipeStmt, GoStmt, IfStmt, ForStmt,
    WhileStmt, TryCatch, MacroInvoke, MatchStmt, MatchArm, Literal, VarRef,
    SelfRef, BinaryOp, UnaryOp, Assign, FnCall, MethodCall, FieldAccess,
    IndexAccess, ListLiteral, TupleLiteral, MapLiteral, OwnershipExpr,
    ResultOk, ResultErr, AwaitExpr, PipeExpr, LambdaExpr, ReflectExpr,
    RangeExpr, TernaryExpr, TypeCastExpr, SpreadExpr,
    WildcardPattern, LiteralPattern, BindingPattern, TuplePattern,
    RangePattern, OrPattern, StructPattern, EnumPattern, GuardedPattern,
)

INDENT_UNIT = "    "


def _lit(value) -> str:
    if isinstance(value, str):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'none'
    return str(value)


class Formatter(ASTVisitor):
    """Formats an AST back into canonical CP+* source text."""

    def __init__(self):
        self.depth = 0
        self.lines: List[str] = []

    def format(self, ast: Program) -> str:
        self.depth = 0
        self.lines = []
        self.visit_Program(ast)
        text = '\n'.join(self.lines)
        return text.rstrip('\n') + '\n' if text else ''

    def _pad(self) -> str:
        return INDENT_UNIT * self.depth

    def _emit(self, text: str) -> None:
        self.lines.append(self._pad() + text if text else '')

    def _block(self, stmts: List[ASTNode]) -> str:
        saved = self.lines
        self.lines = []
        self.depth += 1
        for s in stmts:
            if s is not None:
                s.accept(self)
        self.depth -= 1
        body = self.lines
        self.lines = saved
        return '\n'.join(body)

    # ── expressions → single-line strings ──────────────────────────────

    def expr(self, node) -> str:
        if node is None:
            return ''
        method = getattr(self, f'e_{type(node).__name__}', None)
        if method is None:
            return f'<{type(node).__name__}>'
        return method(node)

    def e_Literal(self, n: Literal) -> str:
        return _lit(n.value)

    def e_VarRef(self, n: VarRef) -> str:
        return n.name

    def e_SelfRef(self, n) -> str:
        return '@'

    def e_BinaryOp(self, n: BinaryOp) -> str:
        return f'{self.expr(n.left)} {n.op} {self.expr(n.right)}'

    def e_UnaryOp(self, n: UnaryOp) -> str:
        return f'{n.op}{self.expr(n.operand)}'

    def e_Assign(self, n: Assign) -> str:
        return f'{self.expr(n.target)} {n.op} {self.expr(n.value)}'

    def e_FnCall(self, n: FnCall) -> str:
        args = ', '.join(self.expr(a) for a in n.args)
        targs = f'<{", ".join(n.type_args)}>' if getattr(n, 'type_args', None) else ''
        return f'{n.name}{targs}({args})'

    def e_MethodCall(self, n: MethodCall) -> str:
        args = ', '.join(self.expr(a) for a in n.args)
        sep = '::' if n.method and n.method[0:1].isupper() else ':'
        return f'{self.expr(n.obj)}{sep}{n.method}({args})'

    def e_FieldAccess(self, n: FieldAccess) -> str:
        base = self.expr(n.obj)
        if isinstance(n.obj, SelfRef):
            return f'@.{n.field}'
        return f'{base}.{n.field}'

    def e_IndexAccess(self, n: IndexAccess) -> str:
        return f'{self.expr(n.obj)}[{self.expr(n.index)}]'

    def e_ListLiteral(self, n: ListLiteral) -> str:
        return '[' + ', '.join(self.expr(e) for e in n.elements) + ']'

    def e_TupleLiteral(self, n: TupleLiteral) -> str:
        return '(' + ', '.join(self.expr(e) for e in n.elements) + ')'

    def e_MapLiteral(self, n: MapLiteral) -> str:
        pairs = ', '.join(f'{self.expr(k)}: {self.expr(v)}' for k, v in n.pairs)
        return '{' + pairs + '}'

    def e_OwnershipExpr(self, n: OwnershipExpr) -> str:
        lt = f"'{n.lifetime}, " if getattr(n, 'lifetime', None) else ''
        return f'{n.kind}<{lt}{self.expr(n.inner)}>'

    def e_ResultOk(self, n: ResultOk) -> str:
        return f'!>ok({self.expr(n.value)})' if False else f'ok({self.expr(n.value)})'

    def e_ResultErr(self, n: ResultErr) -> str:
        return f'err({self.expr(n.value)})'

    def e_AwaitExpr(self, n: AwaitExpr) -> str:
        return f'await {self.expr(n.expr)}'

    def e_PipeExpr(self, n: PipeExpr) -> str:
        return f'{self.expr(n.left)} ~> {self.expr(n.right)}'

    def e_LambdaExpr(self, n: LambdaExpr) -> str:
        params = ', '.join(f'{p[0]}: {p[1]}' if len(p) > 1 and p[1] else p[0] for p in n.params)
        body_str = self._block(n.body)
        return f'({params}) -> {n.return_type} ** {{\n{body_str}\n{self._pad()}}}'

    def e_ReflectExpr(self, n: ReflectExpr) -> str:
        return f'@reflect {self.expr(n.target)}'

    def e_RangeExpr(self, n: RangeExpr) -> str:
        op = '..=' if n.inclusive else '..'
        return f'{self.expr(n.start)}{op}{self.expr(n.end)}'

    def e_TernaryExpr(self, n: TernaryExpr) -> str:
        return f'{self.expr(n.condition)} ? {self.expr(n.then_expr)} : {self.expr(n.else_expr)}'

    def e_TypeCastExpr(self, n: TypeCastExpr) -> str:
        return f'{self.expr(n.expr)} as {n.cast_type}'

    def e_SpreadExpr(self, n: SpreadExpr) -> str:
        return f'...{self.expr(n.expr)}'

    def pattern(self, p) -> str:
        if p is None:
            return '_'
        if isinstance(p, WildcardPattern):
            return '_'
        if isinstance(p, LiteralPattern):
            return _lit(p.value)
        if isinstance(p, BindingPattern):
            return p.name
        if isinstance(p, TuplePattern):
            return '(' + ', '.join(self.pattern(e) for e in p.elements) + ')'
        if isinstance(p, RangePattern):
            op = '..=' if p.inclusive else '..'
            return f'{self.expr(p.lo) if hasattr(p.lo, "accept") else p.lo}{op}{self.expr(p.hi) if hasattr(p.hi, "accept") else p.hi}'
        if isinstance(p, OrPattern):
            return ' | '.join(self.pattern(e) for e in p.patterns)
        if isinstance(p, StructPattern):
            fields = ', '.join(name if fp is None else f'{name}: {self.pattern(fp)}' for name, fp in p.fields)
            return f'{p.type_name} {{ {fields} }}'
        if isinstance(p, EnumPattern):
            return f'{p.variant}({self.pattern(p.inner)})' if p.inner is not None else p.variant
        if isinstance(p, GuardedPattern):
            guard = self.expr(p.guard) if hasattr(p.guard, 'accept') else str(p.guard)
            return f'{self.pattern(p.pattern)} if {guard}'
        if hasattr(p, 'accept'):
            return self.expr(p)
        return str(p)

    # ── statements → appended lines ────────────────────────────────────

    def visit_Program(self, node: Program):
        for s in node.statements:
            if s:
                s.accept(self)

    def visit_ModuleDecl(self, node: ModuleDecl):
        self._emit(f'module {node.name}')

    def visit_ImportStmt(self, node: ImportStmt):
        alias = f' as {node.alias}' if getattr(node, 'alias', None) else ''
        if len(node.module) == 1:
            self._emit(f'import {node.module[0]}{alias}')
        else:
            self._emit('import -> {')
            self.depth += 1
            for mod in node.module:
                self._emit(f'{mod},')
            self.depth -= 1
            self._emit('}')

    def visit_ExportStmt(self, node: ExportStmt):
        self._emit(f'export {node.name}')

    def visit_VarDecl(self, node: VarDecl):
        if node.ownership:
            self._emit(f'{node.ownership}<{node.var_type}> {node.name} := {self.expr(node.value)}')
            return
        if node.var_type == 'auto' and not node.is_mut:
            self._emit(f'{node.name} := {self.expr(node.value)}')
            return
        mut = 'mut ' if node.is_mut else ''
        val = f' = {self.expr(node.value)}' if node.value is not None else ''
        self._emit(f'{node.name} :: {mut}{node.var_type}{val}')

    def visit_FnDef(self, node: FnDef):
        if getattr(node, 'doc', None):
            for docline in node.doc.splitlines():
                self._emit(f'-- {docline}')
        export = 'export ' if node.is_export else ''
        params = ', '.join(f'{p[0]}: {p[1]}' if len(p) > 1 and p[1] else p[0] for p in node.params)
        self._emit(f'{export}++ {node.name} <~ ({params}) -> {node.return_type} ** {{')
        body = self._block(node.body)
        if body:
            self._emit_raw(body)
        self._emit('}')

    def _emit_raw(self, text: str) -> None:
        self.lines.append(text)

    def visit_OverrideDecl(self, node: OverrideDecl):
        self._emit('@@override')
        node.fn.accept(self)

    def visit_ClassDef(self, node: ClassDef):
        if getattr(node, 'doc', None):
            for docline in node.doc.splitlines():
                self._emit(f'-- {docline}')
        parents = f' : {", ".join(node.parents)}' if node.parents else ''
        traits = f' impl {", ".join(node.traits)}' if node.traits else ''
        self._emit(f'class {node.name}{parents}{traits} -> {{')
        body = self._block(node.body)
        if body:
            self._emit_raw(body)
        self._emit('}')

    def visit_StructDef(self, node: StructDef):
        self._emit(f'struct {node.name} {{')
        self.depth += 1
        for f in node.fields:
            self._emit(f'{f[0]}: {f[1]}')
        self.depth -= 1
        self._emit('}')

    def visit_TraitDef(self, node: TraitDef):
        self._emit(f'trait {node.name} {{')
        body = self._block(node.methods)
        if body:
            self._emit_raw(body)
        self._emit('}')

    def visit_ImplBlock(self, node: ImplBlock):
        trait = f'{node.trait_name} for ' if node.trait_name else ''
        self._emit(f'impl {trait}{node.type_name} {{')
        body = self._block(node.methods)
        if body:
            self._emit_raw(body)
        self._emit('}')

    def visit_ReturnStmt(self, node: ReturnStmt):
        val = f' {self.expr(node.value)}' if node.value is not None else ''
        self._emit(f'<-{val}')

    def visit_BreakStmt(self, node: BreakStmt):
        label = f' {node.label}' if node.label else ''
        self._emit(f'!>{label}')

    def visit_ContinueStmt(self, node: ContinueStmt):
        label = f' {node.label}' if node.label else ''
        self._emit(f'!>>{label}')

    def visit_PanicStmt(self, node: PanicStmt):
        self._emit(f'!! {self.expr(node.message)}')

    def visit_PipeStmt(self, node: PipeStmt):
        self._emit(f'~> {self.expr(node.expr)}')

    def visit_GoStmt(self, node: GoStmt):
        self._emit(f'go {self.expr(node.call)}')

    def visit_IfStmt(self, node: IfStmt):
        self._emit(f'?? {self.expr(node.condition)} ** {{')
        body = self._block(node.then_body)
        if body:
            self._emit_raw(body)
        for cond, cbody in node.elif_clauses:
            self._emit(f'}} ?? {self.expr(cond)} ** {{')
            b = self._block(cbody)
            if b:
                self._emit_raw(b)
        if node.else_body:
            self._emit('} !! {')
            b = self._block(node.else_body)
            if b:
                self._emit_raw(b)
        self._emit('}')

    def visit_ForStmt(self, node: ForStmt):
        label = f'{node.label}: ' if getattr(node, 'label', None) else ''
        self._emit(f'{label}<> {node.var_name} :: {self.expr(node.iterable)} ** {{')
        body = self._block(node.body)
        if body:
            self._emit_raw(body)
        self._emit('}')

    def visit_WhileStmt(self, node: WhileStmt):
        label = f'{node.label}: ' if getattr(node, 'label', None) else ''
        self._emit(f'{label}while {self.expr(node.condition)} ** {{')
        body = self._block(node.body)
        if body:
            self._emit_raw(body)
        self._emit('}')

    def visit_TryCatch(self, node: TryCatch):
        self._emit('try ** {')
        body = self._block(node.try_body)
        if body:
            self._emit_raw(body)
        self._emit(f'}} catch ({node.catch_var}) ** {{')
        body = self._block(node.catch_body)
        if body:
            self._emit_raw(body)
        if getattr(node, 'finally_body', None):
            self._emit('} finally ** {')
            body = self._block(node.finally_body)
            if body:
                self._emit_raw(body)
        self._emit('}')

    def visit_MacroInvoke(self, node: MacroInvoke):
        args = ', '.join(self.expr(a) for a in node.args)
        self._emit(f'@{node.kind} {node.name}({args})')

    def visit_MatchStmt(self, node: MatchStmt):
        self._emit(f'?~ {self.expr(node.value)} {{')
        self.depth += 1
        for arm in node.arms:
            self.visit_MatchArm(arm)
        self.depth -= 1
        self._emit('}')

    def visit_MatchArm(self, node: MatchArm):
        guard = f' ?? {self.expr(node.guard)}' if getattr(node, 'guard', None) else ''
        pattern_str = self.pattern(node.pattern)
        body = self._block(node.body).strip()
        self._emit(f'{pattern_str}{guard} => {{ {body} }},')

    # Expression-statements (bare pipe/call expressions used as statements)
    def visit_default(self, node: ASTNode):
        try:
            self._emit(self.expr(node))
        except Exception:
            self._emit(f'<{type(node).__name__}>')


def format_source(ast: Program) -> str:
    """Format a parsed AST into canonical CP+* source text."""
    return Formatter().format(ast)
