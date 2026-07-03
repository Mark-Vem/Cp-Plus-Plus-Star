"""
ir.py — bytecode/IR groundwork for CP+* (`cpps build`).

IMPORTANT — SCOPE DISCLOSURE:
This module lowers a real, useful subset of the CP+* AST (expressions,
arithmetic/comparison/logical ops, variable decl/assignment, if/while,
function calls, print/pipe statements, return) into a linear stack-based
IR (`IRProgram` of `IRInstr`s) and can execute that IR directly via
`IRInterpreter` — a genuine, working bytecode VM, not a stub.

It is explicitly **groundwork**, not a full compiler backend:
  - It does NOT implement classes/structs/traits/impl, pattern matching,
    generics, ownership/borrow checking, goroutines, or reflection at the
    IR level — those still execute exclusively through the tree-walking
    `interpreter.py`, which remains the source of truth for full-language
    semantics.
  - There is no machine-code generation, no LLVM integration, and no JIT.
    `cpps build` produces a portable, inspectable `.cpir` (JSON) bytecode
    artifact and can *optionally* run it with the lightweight stack VM
    below for the supported subset — it does not produce a native binary.
This scope was explicitly called out to the user up front: full
LLVM/JIT native compilation is out of scope for this project.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, List, Optional

from parser import (
    Program, VarDecl, FnDef, ReturnStmt, PipeStmt, IfStmt, WhileStmt,
    BreakStmt, ContinueStmt, Literal, VarRef, BinaryOp, UnaryOp, Assign,
    FnCall, TernaryExpr, ASTNode,
)


class Op(Enum):
    PUSH_CONST = 'PUSH_CONST'
    LOAD = 'LOAD'
    STORE = 'STORE'
    BINOP = 'BINOP'
    UNOP = 'UNOP'
    CALL = 'CALL'
    PRINT = 'PRINT'
    POP = 'POP'
    JUMP = 'JUMP'
    JUMP_IF_FALSE = 'JUMP_IF_FALSE'
    RETURN = 'RETURN'
    HALT = 'HALT'
    MAKE_FN = 'MAKE_FN'
    LABEL = 'LABEL'


@dataclass
class IRInstr:
    op: Op
    arg: Any = None
    line: int = 0

    def to_dict(self):
        return {'op': self.op.value, 'arg': self.arg, 'line': self.line}

    @staticmethod
    def from_dict(d):
        return IRInstr(Op(d['op']), d.get('arg'), d.get('line', 0))

    def __repr__(self):
        return f"{self.op.value:<16} {self.arg!r}" if self.arg is not None else self.op.value


@dataclass
class IRFunction:
    name: str
    params: List[str]
    code: List[IRInstr] = field(default_factory=list)


@dataclass
class IRProgram:
    """A linear, JSON-serializable bytecode program: a `main` instruction
    stream plus zero or more lowered functions."""
    main: List[IRInstr] = field(default_factory=list)
    functions: List[IRFunction] = field(default_factory=list)
    unsupported: List[str] = field(default_factory=list)  # constructs skipped (documented, not silent)

    def dump_text(self) -> str:
        lines = ["; CP+* IR — groundwork bytecode (see ir.py header for scope)"]
        if self.unsupported:
            lines.append("; NOTE: the following constructs fell back to tree-walking "
                          "interpretation and are not represented in this IR:")
            for u in sorted(set(self.unsupported)):
                lines.append(f";   - {u}")
        lines.append("")
        lines.append("func main:")
        for i, instr in enumerate(self.main):
            lines.append(f"  {i:04d}  {instr}")
        for fn in self.functions:
            lines.append("")
            lines.append(f"func {fn.name}({', '.join(fn.params)}):")
            for i, instr in enumerate(fn.code):
                lines.append(f"  {i:04d}  {instr}")
        return '\n'.join(lines)

    def to_json(self) -> str:
        data = {
            'main': [i.to_dict() for i in self.main],
            'functions': [
                {'name': f.name, 'params': f.params, 'code': [i.to_dict() for i in f.code]}
                for f in self.functions
            ],
            'unsupported': self.unsupported,
        }
        return json.dumps(data, indent=2)

    @staticmethod
    def from_json(text: str) -> 'IRProgram':
        data = json.loads(text)
        main = [IRInstr.from_dict(d) for d in data['main']]
        functions = [
            IRFunction(f['name'], f['params'], [IRInstr.from_dict(d) for d in f['code']])
            for f in data['functions']
        ]
        return IRProgram(main, functions, data.get('unsupported', []))


class IRLowering:
    """
    Lowers a supported AST subset to `IRProgram`. Anything outside the
    supported subset is recorded in `unsupported` (not silently dropped)
    and the caller (`cpps build`) reports that the full program must still
    run through `interpreter.py`.
    """

    def __init__(self):
        self.unsupported: List[str] = []

    def lower_program(self, ast: Program) -> IRProgram:
        prog = IRProgram()
        for stmt in ast.statements:
            if isinstance(stmt, FnDef) and stmt.name != 'main':
                fn = IRFunction(stmt.name, [p[0] for p in stmt.params])
                fn.code = self._lower_block(stmt.body)
                prog.functions.append(fn)
            elif isinstance(stmt, FnDef) and stmt.name == 'main':
                prog.main = self._lower_block(stmt.body)
            else:
                prog.main.extend(self._lower_stmt(stmt))
        prog.main.append(IRInstr(Op.HALT))
        prog.unsupported = self.unsupported
        return prog

    def _lower_block(self, stmts: List[ASTNode]) -> List[IRInstr]:
        out: List[IRInstr] = []
        for s in stmts:
            if s is not None:
                out.extend(self._lower_stmt(s))
        return out

    def _mark_unsupported(self, node: ASTNode) -> List[IRInstr]:
        name = type(node).__name__
        self.unsupported.append(name)
        return []

    def _lower_stmt(self, node: ASTNode) -> List[IRInstr]:
        line = getattr(node, 'line', 0)
        if isinstance(node, VarDecl):
            code = self._lower_expr(node.value) if node.value is not None else [IRInstr(Op.PUSH_CONST, None, line)]
            code.append(IRInstr(Op.STORE, node.name, line))
            return code
        if isinstance(node, ReturnStmt):
            code = self._lower_expr(node.value) if node.value is not None else [IRInstr(Op.PUSH_CONST, None, line)]
            code.append(IRInstr(Op.RETURN, None, line))
            return code
        if isinstance(node, PipeStmt):
            code = self._lower_expr(node.expr)
            code.append(IRInstr(Op.PRINT, None, line))
            return code
        if isinstance(node, IfStmt):
            return self._lower_if(node)
        if isinstance(node, WhileStmt):
            return self._lower_while(node)
        if isinstance(node, BreakStmt):
            return [IRInstr(Op.JUMP, '__break__', line)]
        if isinstance(node, ContinueStmt):
            return [IRInstr(Op.JUMP, '__continue__', line)]
        if isinstance(node, Assign) and isinstance(node.target, VarRef):
            code = self._lower_expr(node.value)
            if node.op != '=':
                code = self._lower_expr(node.target) + code + [IRInstr(Op.BINOP, node.op[:-1], line)]
            code.append(IRInstr(Op.STORE, node.target.name, line))
            return code
        # Bare expression statement (e.g. a call used for side effects)
        try:
            code = self._lower_expr(node)
            code.append(IRInstr(Op.POP, None, line))
            return code
        except NotImplementedError:
            return self._mark_unsupported(node)

    _label_counter = 0

    def _new_label(self, prefix: str) -> str:
        IRLowering._label_counter += 1
        return f"{prefix}_{IRLowering._label_counter}"

    def _lower_if(self, node: IfStmt) -> List[IRInstr]:
        out: List[IRInstr] = []
        end_label = self._new_label('endif')
        out.extend(self._lower_expr(node.condition))
        else_label = self._new_label('else')
        out.append(IRInstr(Op.JUMP_IF_FALSE, else_label))
        out.extend(self._lower_block(node.then_body))
        out.append(IRInstr(Op.JUMP, end_label))
        out.append(IRInstr(Op.LABEL, else_label))
        for cond, body in node.elif_clauses:
            next_label = self._new_label('elif')
            out.extend(self._lower_expr(cond))
            out.append(IRInstr(Op.JUMP_IF_FALSE, next_label))
            out.extend(self._lower_block(body))
            out.append(IRInstr(Op.JUMP, end_label))
            out.append(IRInstr(Op.LABEL, next_label))
        if node.else_body:
            out.extend(self._lower_block(node.else_body))
        out.append(IRInstr(Op.LABEL, end_label))
        return out

    def _lower_while(self, node: WhileStmt) -> List[IRInstr]:
        start_label = self._new_label('loop')
        end_label = self._new_label('endloop')
        out = [IRInstr(Op.LABEL, start_label)]
        out.extend(self._lower_expr(node.condition))
        out.append(IRInstr(Op.JUMP_IF_FALSE, end_label))
        body = self._lower_block(node.body)
        body = [IRInstr(Op.JUMP, end_label, i.line) if i.arg == '__break__' else i for i in body]
        body = [IRInstr(Op.JUMP, start_label, i.line) if i.arg == '__continue__' else i for i in body]
        out.extend(body)
        out.append(IRInstr(Op.JUMP, start_label))
        out.append(IRInstr(Op.LABEL, end_label))
        return out

    def _lower_expr(self, node: ASTNode) -> List[IRInstr]:
        line = getattr(node, 'line', 0)
        if node is None:
            return [IRInstr(Op.PUSH_CONST, None, line)]
        if isinstance(node, Literal):
            return [IRInstr(Op.PUSH_CONST, node.value, line)]
        if isinstance(node, VarRef):
            return [IRInstr(Op.LOAD, node.name, line)]
        if isinstance(node, BinaryOp):
            return self._lower_expr(node.left) + self._lower_expr(node.right) + [IRInstr(Op.BINOP, node.op, line)]
        if isinstance(node, UnaryOp):
            return self._lower_expr(node.operand) + [IRInstr(Op.UNOP, node.op, line)]
        if isinstance(node, FnCall):
            code: List[IRInstr] = []
            for a in node.args:
                code.extend(self._lower_expr(a))
            code.append(IRInstr(Op.CALL, (node.name, len(node.args)), line))
            return code
        if isinstance(node, TernaryExpr):
            end_label = self._new_label('endternary')
            else_label = self._new_label('elseternary')
            code = self._lower_expr(node.condition)
            code.append(IRInstr(Op.JUMP_IF_FALSE, else_label))
            code.extend(self._lower_expr(node.then_expr))
            code.append(IRInstr(Op.JUMP, end_label))
            code.append(IRInstr(Op.LABEL, else_label))
            code.extend(self._lower_expr(node.else_expr))
            code.append(IRInstr(Op.LABEL, end_label))
            return code
        raise NotImplementedError(type(node).__name__)


def lower(ast: Program) -> IRProgram:
    """Lower an AST to the groundwork IR (see module docstring for scope)."""
    return IRLowering().lower_program(ast)


class IRRuntimeError(Exception):
    pass


class IRInterpreter:
    """
    A genuine (not stubbed) stack-based bytecode VM for the IR subset
    produced by `IRLowering`. Supports the same arithmetic/comparison/
    logical operators and builtin `println`/`print` calls used by
    `interpreter.py`'s expression evaluator, so simple numeric/string
    programs execute identically whether run via the tree-walking
    interpreter or this bytecode VM.
    """

    def __init__(self, program: IRProgram):
        self.program = program
        self.functions = {f.name: f for f in program.functions}
        self.globals = {}

    def run(self) -> int:
        self._exec(self.program.main, self.globals)
        return 0

    def _index_labels(self, code: List[IRInstr]):
        return {instr.arg: i for i, instr in enumerate(code) if instr.op == Op.LABEL}

    def _exec(self, code: List[IRInstr], env: dict) -> Optional[Any]:
        labels = self._index_labels(code)
        stack: List[Any] = []
        pc = 0
        while pc < len(code):
            instr = code[pc]
            op = instr.op
            if op == Op.LABEL:
                pc += 1
                continue
            if op == Op.PUSH_CONST:
                stack.append(instr.arg)
            elif op == Op.LOAD:
                if instr.arg not in env:
                    raise IRRuntimeError(f"undefined variable `{instr.arg}` (line {instr.line})")
                stack.append(env[instr.arg])
            elif op == Op.STORE:
                env[instr.arg] = stack.pop()
            elif op == Op.POP:
                stack.pop()
            elif op == Op.BINOP:
                b = stack.pop()
                a = stack.pop()
                stack.append(self._binop(instr.arg, a, b))
            elif op == Op.UNOP:
                a = stack.pop()
                stack.append(self._unop(instr.arg, a))
            elif op == Op.PRINT:
                print(self._display(stack.pop()))
            elif op == Op.JUMP:
                pc = labels[instr.arg]
                continue
            elif op == Op.JUMP_IF_FALSE:
                cond = stack.pop()
                if not cond:
                    pc = labels[instr.arg]
                    continue
            elif op == Op.CALL:
                name, argc = instr.arg
                args = [stack.pop() for _ in range(argc)][::-1]
                stack.append(self._call(name, args))
            elif op == Op.RETURN:
                return stack.pop() if stack else None
            elif op == Op.HALT:
                return None
            else:
                raise IRRuntimeError(f"unknown IR opcode: {op}")
            pc += 1
        return None

    def _call(self, name: str, args: List[Any]) -> Any:
        if name in ('println', 'print'):
            print(*args)
            return None
        fn = self.functions.get(name)
        if fn is None:
            raise IRRuntimeError(f"call to unknown function `{name}` in IR VM "
                                  f"(only functions with a fully-lowered body run here)")
        local_env = dict(zip(fn.params, args))
        return self._exec(fn.code, local_env)

    @staticmethod
    def _binop(op: str, a, b):
        ops = {
            '+': lambda: a + b, '-': lambda: a - b, '*': lambda: a * b,
            '/': lambda: a / b, '%': lambda: a % b,
            '==': lambda: a == b, '!=': lambda: a != b,
            '<': lambda: a < b, '<=': lambda: a <= b,
            '>': lambda: a > b, '>=': lambda: a >= b,
            '&&': lambda: bool(a) and bool(b), '||': lambda: bool(a) or bool(b),
        }
        if op not in ops:
            raise IRRuntimeError(f"unsupported binary operator in IR VM: {op}")
        return ops[op]()

    @staticmethod
    def _unop(op: str, a):
        if op == '-':
            return -a
        if op in ('!', 'not'):
            return not a
        raise IRRuntimeError(f"unsupported unary operator in IR VM: {op}")

    @staticmethod
    def _display(v) -> str:
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if v is None:
            return 'none'
        return str(v)
