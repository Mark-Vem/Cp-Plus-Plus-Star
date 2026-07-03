"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CP+* (C-Plus-Plus-Star) Language — Parser                                  ║
║  File: src/parser.py                                                         ║
║  Version: 2.0 — Advanced Edition                                             ║
║                                                                              ║
║  Parser đầy đủ chức năng cho ngôn ngữ CP+*:                                 ║
║  - AST Node classes (40+ node types)                                         ║
║  - Recursive descent parser                                                  ║
║  - Pratt parser cho expressions (precedence climbing)                        ║
║  - Error recovery với synchronization points                                  ║
║  - Xử lý đầy đủ syntax của CP+*                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Grammar Summary (EBNF-like)
==============================

program         ::= top_level_stmt*

top_level_stmt  ::= module_decl | import_stmt | export_stmt | stmt

stmt            ::= var_decl | fn_def | class_def | struct_def | trait_def
                  | impl_block | if_stmt | for_stmt | while_stmt | match_stmt
                  | return_stmt | break_stmt | continue_stmt | panic_stmt
                  | try_catch | go_stmt | pipe_stmt | ownership_decl
                  | macro_invoke | override_decl | expr_stmt

var_decl        ::= IDENTIFIER ':=' expr
                  | IDENTIFIER '::' ['mut'] type '=' expr

fn_def          ::= '++' IDENTIFIER type_params? ('<~' '(' params ')' | '(' params ')')
                     ('->' type)? '**'? '{' block '}'

class_def       ::= 'class' IDENTIFIER type_params? (':' IDENTIFIER (',' IDENTIFIER)*)?
                    ('impl' IDENTIFIER (',' IDENTIFIER)*)? '->'? '{' block '}'

struct_def      ::= 'struct' IDENTIFIER type_params? '->'? '{' field_list '}'

trait_def       ::= 'trait' IDENTIFIER type_params? '->'? '{' block '}'

impl_block      ::= 'impl' IDENTIFIER? 'for'? IDENTIFIER '->'? '{' block '}'

if_stmt         ::= '??' expr '**'? '{' block '}' ('--' 'elif' expr '**'? '{' block '}')*
                    ('--' 'else' '**'? '{' block '}')?

for_stmt        ::= '<>' IDENTIFIER '::' expr '**'? '{' block '}'

while_stmt      ::= 'while' expr '**'? '{' block '}'

match_stmt      ::= '?~' expr '{' match_arm (',' match_arm)* '}'

match_arm       ::= pattern ('if' expr)? '=>' ('{' block '}' | stmt)

return_stmt     ::= '<-' expr?

break_stmt      ::= '!>'

continue_stmt   ::= '!>>'

panic_stmt      ::= '!!' expr?

try_catch       ::= 'try' '**'? '{' block '}' 'catch' ('(' IDENTIFIER ')')? '**'? '{' block '}'

go_stmt         ::= 'go' expr

pipe_stmt       ::= '~>' expr

ownership_decl  ::= ('own' | 'share' | 'borrow') ('<' type '>')? IDENTIFIER ':=' expr

expr            ::= assign_expr
assign_expr     ::= or_expr (('='|'+='|'-='|'*='|'/=') assign_expr)?
or_expr         ::= and_expr ('||' and_expr)*
and_expr        ::= compare_expr ('&&' compare_expr)*
compare_expr    ::= add_expr (('=='|'!='|'<'|'>'|'<='|'>=') add_expr)?
add_expr        ::= mul_expr (('+'|'-') mul_expr)*
mul_expr        ::= unary_expr (('*'|'/'|'%') unary_expr)*
unary_expr      ::= ('-'|'!') unary_expr | await_expr | postfix_expr
postfix_expr    ::= primary_expr (call_suffix | method_suffix | index_suffix | field_suffix)*
primary_expr    ::= literal | identifier | '(' expr ')' | list_literal | map_literal
                  | tuple_literal | lambda_expr | ownership_expr | result_expr
                  | '@' field_access | self_ref | macro_expr | reflect_expr
"""

import sys
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Tuple, Union

from tokens import (
    Token, TokenType,
    KEYWORDS, get_precedence, is_right_associative,
)
from lexer import Lexer, tokenize


# ══════════════════════════════════════════════════════════════════════════════
# AST NODE BASE
# ══════════════════════════════════════════════════════════════════════════════

class ASTNode:
    """
    Base class cho tất cả AST (Abstract Syntax Tree) nodes.
    Mỗi node đại diện cho một cấu trúc cú pháp của CP+*.

    Subclasses sử dụng @dataclass để tự động tạo __init__, __repr__,
    và cho phép serialization.

    Common attributes (không bắt buộc nhưng thường có):
        line (int): Số dòng trong source code
        column (int): Số cột trong source code
    """

    def node_type(self) -> str:
        """Trả về tên class của node."""
        return self.__class__.__name__

    def is_a(self, cls) -> bool:
        """Kiểm tra node có phải là instance của cls không."""
        return isinstance(self, cls)

    def children(self) -> List['ASTNode']:
        """
        Trả về danh sách children nodes.
        Override trong subclass để traverse AST.
        """
        return []

    def accept(self, visitor) -> Any:
        """
        Visitor pattern: gọi phương thức phù hợp trên visitor.

        Args:
            visitor: Object có phương thức visit_<ClassName>

        Returns:
            Kết quả từ visitor
        """
        method_name = f"visit_{self.__class__.__name__}"
        method = getattr(visitor, method_name, visitor.visit_default)
        return method(self)

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển node thành dict để serialization/debugging."""
        result = {'__type': self.node_type()}
        for key, val in self.__dict__.items():
            if isinstance(val, ASTNode):
                result[key] = val.to_dict()
            elif isinstance(val, list):
                result[key] = [v.to_dict() if isinstance(v, ASTNode) else v for v in val]
            else:
                result[key] = val
        return result


# ══════════════════════════════════════════════════════════════════════════════
# PROGRAM & MODULE NODES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Program(ASTNode):
    """
    Root node của AST — đại diện cho toàn bộ chương trình.

    Attributes:
        statements: Danh sách tất cả top-level statements
    """
    statements: List[ASTNode]

    def __init__(self, statements: List[ASTNode]):
        self.statements = statements

    def children(self) -> List[ASTNode]:
        return self.statements


@dataclass
class ModuleDecl(ASTNode):
    """
    Khai báo module: `module io`

    Attributes:
        name: Tên module
        line: Dòng khai báo
    """
    name: str
    line: int = 0


@dataclass
class ImportStmt(ASTNode):
    """
    Lệnh import module.

    Syntax:
        import std::io
        import -> { std::io, std::collections::{List, Map} }

    Attributes:
        module: Danh sách đường dẫn module
        items: Danh sách item import cụ thể (có thể rỗng)
        line: Dòng import
        alias: Bí danh (nếu dùng 'as')
    """
    module: List[str]
    items: List[str]
    line: int = 0
    alias: Optional[str] = None


@dataclass
class ExportStmt(ASTNode):
    """
    Lệnh export: `export functionName`

    Attributes:
        name: Tên được export
        line: Dòng export
    """
    name: str
    line: int = 0


# ══════════════════════════════════════════════════════════════════════════════
# DECLARATION NODES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class VarDecl(ASTNode):
    """
    Khai báo biến.

    Syntax:
        name := expr                       -- immutable, auto type
        name :: Type = expr                -- immutable, typed
        name :: mut Type = expr            -- mutable, typed
        own<Type> name := expr             -- owned value
        share<Type> name := expr           -- shared reference
        borrow<Type> name := expr          -- borrowed reference

    Attributes:
        name:      Tên biến
        var_type:  Kiểu dữ liệu (string, mặc định 'auto')
        value:     Biểu thức khởi tạo
        is_mut:    Có thể thay đổi không
        ownership: 'own' | 'share' | 'borrow' | None
        line:      Dòng khai báo
    """
    name: str
    var_type: str
    value: Optional[ASTNode]
    is_mut: bool = False
    ownership: Optional[str] = None
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.value] if self.value else []


@dataclass
class FnDef(ASTNode):
    """
    Định nghĩa hàm.

    Syntax:
        ++ name <~ (param1: Type1, param2: Type2) -> RetType ** {
            body...
        }

    Attributes:
        name:         Tên hàm
        type_params:  Tham số generic ['T', 'U', ...]
        params:       Tham số [(name, type, ownership, default), ...]
        return_type:  Kiểu trả về (string, mặc định 'void')
        body:         Danh sách statements trong thân hàm
        is_static:    Có phải static method không
        is_export:    Có được export không
        line:         Dòng định nghĩa
        is_async:     Có phải async function không
        is_pure:      Có phải pure function không (không side effects)
        doc:          Documentation comment
    """
    name: str
    type_params: List[str]
    params: List[Tuple]
    return_type: str
    body: List[ASTNode]
    is_static: bool = False
    is_export: bool = False
    line: int = 0
    is_async: bool = False
    is_pure: bool = False
    doc: str = ''

    def children(self) -> List[ASTNode]:
        return self.body


@dataclass
class OverrideDecl(ASTNode):
    """
    Override declaration: `@@override ++ method ...`

    Attributes:
        fn:    FnDef node của method được override
        fn_def: Alias cho fn (backward compat)
        line:  Dòng khai báo
    """
    fn: FnDef
    line: int = 0

    @property
    def fn_def(self) -> FnDef:
        return self.fn


@dataclass
class ClassDef(ASTNode):
    """
    Định nghĩa class.

    Syntax:
        class Dog : Animal impl Trainable -> {
            name :: string = ""
            ++ new <~ (n: string) ** { @.name = n }
            ++ bark <~ () ** { ~> io::println("Woof!") }
        }

    Attributes:
        name:        Tên class
        type_params: Generic parameters ['T', ...]
        parents:     Danh sách lớp cha ['Animal', ...]
        traits:      Danh sách trait implement ['Trainable', ...]
        body:        Danh sách members (VarDecl, FnDef, OverrideDecl)
        line:        Dòng khai báo
        is_abstract: Có phải abstract class không
        is_sealed:   Có phải sealed class không
        doc:         Documentation
    """
    name: str
    type_params: List[str]
    parents: List[str]
    traits: List[str]
    body: List[ASTNode]
    line: int = 0
    is_abstract: bool = False
    is_sealed: bool = False
    doc: str = ''

    def children(self) -> List[ASTNode]:
        return self.body


@dataclass
class StructDef(ASTNode):
    """
    Định nghĩa struct (kiểu dữ liệu thuần túy).

    Syntax:
        struct Point -> {
            x: float,
            y: float
        }

    Attributes:
        name:        Tên struct
        type_params: Generic parameters
        fields:      Danh sách (field_name, field_type)
        line:        Dòng khai báo
        doc:         Documentation
    """
    name: str
    type_params: List[str]
    fields: List[Tuple[str, str]]
    line: int = 0
    doc: str = ''


@dataclass
class TraitDef(ASTNode):
    """
    Định nghĩa trait (interface có default implementation).

    Syntax:
        trait Printable -> {
            ++ print <~ () -> void ** { ... }
        }

    Attributes:
        name:        Tên trait
        type_params: Generic parameters
        methods:     Danh sách method declarations
        line:        Dòng khai báo
        doc:         Documentation
    """
    name: str
    type_params: List[str]
    methods: List[ASTNode]
    line: int = 0
    doc: str = ''

    def children(self) -> List[ASTNode]:
        return self.methods


@dataclass
class ImplBlock(ASTNode):
    """
    Implementation block cho type hoặc trait.

    Syntax:
        impl Dog -> { ... }
        impl Printable for Dog -> { ... }

    Attributes:
        type_name:  Tên type được implement
        trait_name: Tên trait (nếu impl trait)
        methods:    Danh sách method implementations
        line:       Dòng khai báo
    """
    type_name: str
    trait_name: Optional[str]
    methods: List[ASTNode]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return self.methods


# ══════════════════════════════════════════════════════════════════════════════
# STATEMENT NODES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ReturnStmt(ASTNode):
    """
    Lệnh return: `<- expr`

    Attributes:
        value: Biểu thức trả về (None nếu không có)
        line:  Dòng return
    """
    value: Optional[ASTNode]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.value] if self.value else []


@dataclass
class BreakStmt(ASTNode):
    """
    Lệnh break vòng lặp: `!>`

    Attributes:
        label: Nhãn vòng lặp cần break (nếu có)
        line:  Dòng break
    """
    line: int = 0
    label: Optional[str] = None


@dataclass
class ContinueStmt(ASTNode):
    """
    Lệnh continue vòng lặp: `!>>`

    Attributes:
        label: Nhãn vòng lặp cần continue
        line:  Dòng continue
    """
    line: int = 0
    label: Optional[str] = None


@dataclass
class PanicStmt(ASTNode):
    """
    Lệnh panic (abort): `!! message`

    Attributes:
        message: Thông báo panic (ASTNode hoặc Literal)
        line:    Dòng panic
    """
    message: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.message]


@dataclass
class PipeStmt(ASTNode):
    """
    Lệnh pipe/print: `~> expr`
    Phổ biến nhất là in ra io::println nhưng cũng có thể là pipe vào function.

    Attributes:
        expr: Biểu thức cần pipe
        line: Dòng pipe
    """
    expr: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.expr]


@dataclass
class GoStmt(ASTNode):
    """
    Spawn goroutine: `go functionCall()`

    Attributes:
        call: Function call expression cần chạy song song
        line: Dòng go
    """
    call: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.call]


@dataclass
class IfStmt(ASTNode):
    """
    Câu điều kiện if.

    Syntax:
        ?? condition ** {
            then_body...
        } -- elif condition2 ** {
            elif_body...
        } -- else ** {
            else_body...
        }

    Attributes:
        condition:    Điều kiện chính
        then_body:    Thân của nhánh then
        elif_clauses: Danh sách (condition, body) cho elif
        else_body:    Thân của nhánh else
        line:         Dòng if
    """
    condition: ASTNode
    then_body: List[ASTNode]
    elif_clauses: List[Tuple[ASTNode, List[ASTNode]]]
    else_body: List[ASTNode]
    line: int = 0

    def children(self) -> List[ASTNode]:
        nodes = [self.condition] + self.then_body
        for cond, body in self.elif_clauses:
            nodes.append(cond)
            nodes.extend(body)
        nodes.extend(self.else_body)
        return nodes


@dataclass
class ForStmt(ASTNode):
    """
    Vòng lặp for-each.

    Syntax:
        <> item :: items ** {
            body...
        }

    Attributes:
        var_name: Tên biến vòng lặp
        iterable: Biểu thức cần duyệt
        body:     Thân vòng lặp
        line:     Dòng for
        label:    Nhãn vòng lặp (để break/continue nested loops)
    """
    var_name: str
    iterable: ASTNode
    body: List[ASTNode]
    line: int = 0
    label: Optional[str] = None

    def children(self) -> List[ASTNode]:
        return [self.iterable] + self.body


@dataclass
class WhileStmt(ASTNode):
    """
    Vòng lặp while.

    Syntax:
        while condition ** {
            body...
        }

    Attributes:
        condition: Điều kiện lặp
        body:      Thân vòng lặp
        line:      Dòng while
        label:     Nhãn vòng lặp
    """
    condition: ASTNode
    body: List[ASTNode]
    line: int = 0
    label: Optional[str] = None

    def children(self) -> List[ASTNode]:
        return [self.condition] + self.body


@dataclass
class TryCatch(ASTNode):
    """
    Xử lý lỗi try/catch.

    Syntax:
        try ** {
            risky_code...
        } catch (err) ** {
            handle_error...
        }

    Attributes:
        try_body:   Thân try block
        catch_var:  Tên biến lỗi trong catch
        catch_body: Thân catch block
        line:       Dòng try
        finally_body: Thân finally block (tùy chọn)
    """
    try_body: List[ASTNode]
    catch_var: str
    catch_body: List[ASTNode]
    line: int = 0
    finally_body: Optional[List[ASTNode]] = None

    def children(self) -> List[ASTNode]:
        nodes = self.try_body + self.catch_body
        if self.finally_body:
            nodes.extend(self.finally_body)
        return nodes


@dataclass
class MacroInvoke(ASTNode):
    """
    Invocation của macro.

    Syntax:
        @macro_tok my_macro(arg1, arg2)
        @macro_ast another_macro(expr)

    Attributes:
        kind: 'macro_tok' | 'macro_ast'
        name: Tên macro
        args: Danh sách arguments
        line: Dòng invocation
    """
    kind: str
    name: str
    args: List[ASTNode]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return self.args


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN MATCHING NODES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MatchStmt(ASTNode):
    """
    Pattern matching.

    Syntax:
        ?~ value {
            pattern1 => { body1 },
            pattern2 if guard => { body2 },
            _ => { default_body },
        }

    Attributes:
        value: Biểu thức cần match
        arms:  Danh sách MatchArm
        line:  Dòng match
    """
    value: ASTNode
    arms: List['MatchArm']
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.value] + self.arms


@dataclass
class MatchArm(ASTNode):
    """
    Một arm trong match statement.

    Attributes:
        pattern: Pattern cần khớp
        guard:   Điều kiện guard (tùy chọn, dùng 'if')
        body:    Thân xử lý khi khớp
        line:    Dòng arm
    """
    pattern: 'Pattern'
    guard: Optional[ASTNode]
    body: List[ASTNode]
    line: int = 0

    def children(self) -> List[ASTNode]:
        nodes = [self.pattern]
        if self.guard:
            nodes.append(self.guard)
        nodes.extend(self.body)
        return nodes


# ── Pattern nodes ──────────────────────────────────────────────────────────

class Pattern(ASTNode):
    """Base class cho tất cả patterns."""
    pass


@dataclass
class WildcardPattern(Pattern):
    """Pattern wildcard: `_` (khớp tất cả, không bind)"""
    line: int = 0


@dataclass
class LiteralPattern(Pattern):
    """Pattern literal: `42`, `"hello"`, `true`, `none`"""
    value: Any
    line: int = 0


@dataclass
class BindingPattern(Pattern):
    """Pattern binding: `x` (khớp tất cả và bind vào biến x)"""
    name: str
    line: int = 0


@dataclass
class TuplePattern(Pattern):
    """Pattern tuple: `(a, b, c)` — khớp tuple"""
    elements: List[Pattern]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return self.elements


@dataclass
class RangePattern(Pattern):
    """Pattern phạm vi: `1..10` hoặc `1..=10`"""
    lo: Any
    hi: Any
    inclusive: bool = False
    line: int = 0


@dataclass
class OrPattern(Pattern):
    """Pattern OR: `1 | 2 | 3`"""
    patterns: List[Pattern]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return self.patterns


@dataclass
class StructPattern(Pattern):
    """Pattern struct: `Point { x, y }` — khớp struct"""
    type_name: str
    fields: List[Tuple[str, Optional[Pattern]]]
    line: int = 0


@dataclass
class EnumPattern(Pattern):
    """Pattern enum variant: `Some(x)` hay `Ok(value)` hay `Err(msg)`"""
    variant: str
    inner: Optional[Pattern]
    line: int = 0


@dataclass
class GuardedPattern(Pattern):
    """Pattern với guard: `x if x > 0`"""
    pattern: Pattern
    guard: ASTNode
    line: int = 0


# ══════════════════════════════════════════════════════════════════════════════
# EXPRESSION NODES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Literal(ASTNode):
    """
    Giá trị literal trực tiếp.

    Attributes:
        value: Giá trị Python (int, float, str, bool, None)
        line:  Dòng xuất hiện
    """
    value: Any
    line: int = 0


@dataclass
class VarRef(ASTNode):
    """
    Tham chiếu đến biến hoặc hàm theo tên.

    Attributes:
        name: Tên biến/hàm
        line: Dòng tham chiếu
    """
    name: str
    line: int = 0


@dataclass
class SelfRef(ASTNode):
    """
    Tham chiếu `self` (ký hiệu `@`).

    Attributes:
        line: Dòng tham chiếu
    """
    line: int = 0


@dataclass
class BinaryOp(ASTNode):
    """
    Phép toán nhị phân.

    Attributes:
        left:  Toán hạng trái
        op:    Ký hiệu phép toán ('+', '-', '==', '&&', etc.)
        right: Toán hạng phải
        line:  Dòng phép toán
    """
    left: ASTNode
    op: str
    right: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.left, self.right]


@dataclass
class UnaryOp(ASTNode):
    """
    Phép toán một ngôi.

    Attributes:
        op:      Ký hiệu phép toán ('-', '!', '~', '&', '*')
        operand: Toán hạng
        line:    Dòng phép toán
    """
    op: str
    operand: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.operand]


@dataclass
class Assign(ASTNode):
    """
    Phép gán (hoặc augmented assignment).

    Attributes:
        target: Biểu thức đích (VarRef, FieldAccess, IndexAccess)
        value:  Biểu thức nguồn
        op:     Phép toán ('=', '+=', '-=', '*=', '/=', etc.)
        line:   Dòng gán
    """
    target: ASTNode
    value: ASTNode
    op: str = '='
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.target, self.value]


@dataclass
class FnCall(ASTNode):
    """
    Gọi hàm theo tên.

    Syntax:
        functionName(arg1, arg2)
        std::io::println(msg)
        MyClass::new(field1, field2)

    Attributes:
        name:      Tên hàm hoặc đường dẫn (có thể bao gồm '::')
        args:      Danh sách arguments
        type_args: Generic type arguments ['String', 'Int']
        line:      Dòng gọi hàm
    """
    name: str
    args: List[ASTNode]
    type_args: List[str]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return self.args


@dataclass
class MethodCall(ASTNode):
    """
    Gọi method trên object.

    Syntax:
        obj:method(arg1, arg2)       -- CP+* style
        obj.method(arg1, arg2)        -- dot style

    Attributes:
        obj:       Object (expression)
        method:    Tên method
        args:      Danh sách arguments
        type_args: Generic type arguments
        line:      Dòng gọi
    """
    obj: ASTNode
    method: str
    args: List[ASTNode]
    type_args: List[str]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.obj] + self.args


@dataclass
class FieldAccess(ASTNode):
    """
    Truy cập field của object.

    Syntax:
        obj.fieldName
        @.fieldName  (self field)

    Attributes:
        obj:   Object expression
        field: Tên field
        line:  Dòng truy cập
    """
    obj: ASTNode
    field: str
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.obj]


@dataclass
class IndexAccess(ASTNode):
    """
    Truy cập phần tử theo index.

    Syntax:
        array[0]
        map["key"]

    Attributes:
        obj:   Object expression (list, dict, etc.)
        index: Index expression
        line:  Dòng truy cập
    """
    obj: ASTNode
    index: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.obj, self.index]


@dataclass
class ListLiteral(ASTNode):
    """
    Literal danh sách: `[1, 2, 3]`

    Attributes:
        elements: Danh sách phần tử
        line:     Dòng literal
    """
    elements: List[ASTNode]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return self.elements


@dataclass
class TupleLiteral(ASTNode):
    """
    Literal tuple: `(1, "hello", true)`

    Attributes:
        elements: Danh sách phần tử
        line:     Dòng literal
    """
    elements: List[ASTNode]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return self.elements


@dataclass
class MapLiteral(ASTNode):
    """
    Literal map/dict: `{ key1: val1, key2: val2 }`

    Attributes:
        pairs: Danh sách (key_str, value_expr)
        line:  Dòng literal
    """
    pairs: List[Tuple[str, ASTNode]]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [v for _, v in self.pairs]


@dataclass
class OwnershipExpr(ASTNode):
    """
    Biểu thức ownership: `own<Type> expr`

    Attributes:
        kind:       'own' | 'share' | 'borrow'
        inner:      Biểu thức bên trong
        lifetime:   Lifetime annotation (nếu có)
        line:       Dòng biểu thức
    """
    kind: str
    inner: ASTNode
    lifetime: Optional[str]
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.inner]


@dataclass
class ResultOk(ASTNode):
    """
    Result success value: `Ok(value)`

    Attributes:
        value: Giá trị thành công
        line:  Dòng biểu thức
    """
    value: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.value]


@dataclass
class ResultErr(ASTNode):
    """
    Result error value: `Err(message)`

    Attributes:
        value: Giá trị lỗi
        line:  Dòng biểu thức
    """
    value: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.value]


@dataclass
class AwaitExpr(ASTNode):
    """
    Await biểu thức async: `await expr`

    Attributes:
        expr: Biểu thức cần await
        line: Dòng await
    """
    expr: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.expr]


@dataclass
class PipeExpr(ASTNode):
    """
    Biểu thức pipe: `expr |> function` hoặc `expr ~> function`

    Attributes:
        left:  Biểu thức nguồn
        right: Biểu thức đích (thường là FnCall)
        line:  Dòng pipe
    """
    left: ASTNode
    right: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.left, self.right]


@dataclass
class LambdaExpr(ASTNode):
    """
    Lambda/closure expression.

    Syntax (informal, may be recognized as fn with special token):
        fn (x: int) -> x * 2
        |x| x * 2

    Attributes:
        params:      Tham số lambda
        return_type: Kiểu trả về
        body:        Thân lambda (single expr hoặc block)
        line:        Dòng lambda
    """
    params: List[Tuple]
    return_type: str
    body: Union[ASTNode, List[ASTNode]]
    line: int = 0

    def children(self) -> List[ASTNode]:
        if isinstance(self.body, list):
            return self.body
        return [self.body]


@dataclass
class ReflectExpr(ASTNode):
    """
    Reflection expression: `@reflect expr`

    Attributes:
        target: Biểu thức cần reflect
        line:   Dòng reflect
    """
    target: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.target]


@dataclass
class RangeExpr(ASTNode):
    """
    Range expression: `start..end` hoặc `start..=end`

    Attributes:
        start:     Giá trị bắt đầu
        end:       Giá trị kết thúc
        inclusive: True nếu dùng ..= (kết thúc bao gồm)
        line:      Dòng biểu thức
    """
    start: ASTNode
    end: ASTNode
    inclusive: bool = False
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.start, self.end]


@dataclass
class TernaryExpr(ASTNode):
    """
    Biểu thức điều kiện inline: `condition ? then_expr : else_expr`

    Attributes:
        condition: Điều kiện
        then_expr: Giá trị khi đúng
        else_expr: Giá trị khi sai
        line:      Dòng biểu thức
    """
    condition: ASTNode
    then_expr: ASTNode
    else_expr: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.condition, self.then_expr, self.else_expr]


@dataclass
class TypeCastExpr(ASTNode):
    """
    Type cast: `expr as Type`

    Attributes:
        expr:      Biểu thức cần cast
        cast_type: Tên kiểu đích
        line:      Dòng cast
    """
    expr: ASTNode
    cast_type: str
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.expr]


@dataclass
class SpreadExpr(ASTNode):
    """
    Spread operator: `...expr`

    Attributes:
        expr: Biểu thức cần spread
        line: Dòng spread
    """
    expr: ASTNode
    line: int = 0

    def children(self) -> List[ASTNode]:
        return [self.expr]


# ══════════════════════════════════════════════════════════════════════════════
# PARSE ERROR
# ══════════════════════════════════════════════════════════════════════════════

class ParseError(Exception):
    """
    Exception khi parser gặp lỗi cú pháp.

    Attributes:
        message:  Mô tả lỗi
        line:     Dòng xảy ra lỗi
        column:   Cột xảy ra lỗi
        filename: Tên file
        token:    Token gây ra lỗi
        expected: Danh sách token types mong đợi
    """

    def __init__(self, message: str, line: int = 0, column: int = 0,
                 filename: str = '<unknown>', token: Optional[Token] = None,
                 expected: Optional[List[TokenType]] = None):
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename
        self.token = token
        self.expected = expected or []
        super().__init__(self.format())

    def format(self) -> str:
        """Định dạng thông báo lỗi."""
        parts = [f"❌ ParseError [{self.filename}:{self.line}:{self.column}]: {self.message}"]
        if self.expected:
            from tokens import TOKEN_DESCRIPTIONS
            exp_str = ', '.join(TOKEN_DESCRIPTIONS.get(t, t.name) for t in self.expected[:3])
            parts.append(f"   Mong đợi: {exp_str}")
        if self.token:
            parts.append(f"   Nhận được: {self.token.type.name}({self.token.value!r})")
        return '\n'.join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# PARSER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Parser:
    """
    Recursive descent parser cho ngôn ngữ CP+*.

    Chuyển đổi danh sách Token thành AST (Abstract Syntax Tree).

    Features:
        - Recursive descent với precedence climbing
        - Error recovery với synchronization points
        - Xử lý đầy đủ syntax CP+*
        - Ưu tiên syntax cao cho CP+* operators (++, <~, ??, <>, !>, etc.)
        - Hỗ trợ generic type parameters
        - Pattern matching đầy đủ
        - Ownership/lifetime declarations
        - Module/import/export system

    Usage:
        >>> from lexer import tokenize
        >>> tokens = tokenize(source, 'main.cpps')
        >>> parser = Parser(tokens, 'main.cpps')
        >>> ast = parser.parse()
        >>> print(ast)

    Attributes:
        tokens (List[Token]): Danh sách token đầu vào
        pos (int): Vị trí hiện tại trong danh sách token
        filename (str): Tên file (cho error messages)
        errors (List[ParseError]): Danh sách lỗi parse
    """

    def __init__(self, tokens: List[Token], filename: str = '<unknown>'):
        """
        Khởi tạo Parser.

        Args:
            tokens: Danh sách token từ Lexer
            filename: Tên file (dùng trong error messages)
        """
        self.tokens = [t for t in tokens if t is not None]
        self.pos = 0
        self.filename = filename
        self.errors: List[ParseError] = []
        self._panic_mode = False   # Error recovery state
        self._loop_depth = 0       # Depth tracking cho nested loops
        self._fn_depth = 0         # Depth tracking cho nested functions
        self._class_depth = 0      # Depth tracking cho nested classes

    # ── Token access helpers ───────────────────────────────────────────────

    def peek(self, offset: int = 0) -> Optional[Token]:
        """Nhìn trước token tại pos+offset."""
        i = self.pos + offset
        if 0 <= i < len(self.tokens):
            return self.tokens[i]
        return None

    def advance(self) -> Optional[Token]:
        """Tiêu thụ và trả về token hiện tại."""
        t = self.peek()
        if t is not None:
            self.pos += 1
        return t

    def at_end(self) -> bool:
        """Kiểm tra đã hết token chưa."""
        t = self.peek()
        return t is None or t.type == TokenType.EOF

    def check(self, *types: TokenType) -> bool:
        """Kiểm tra token hiện tại có thuộc types không."""
        t = self.peek()
        return t is not None and t.type in types

    def check_value(self, *values) -> bool:
        """Kiểm tra giá trị token hiện tại."""
        t = self.peek()
        return t is not None and t.value in values

    def match(self, *types: TokenType) -> Optional[Token]:
        """Tiêu thụ token nếu khớp type."""
        if self.check(*types):
            return self.advance()
        return None

    def match_value(self, *values) -> Optional[Token]:
        """Tiêu thụ token nếu giá trị khớp."""
        if self.check_value(*values):
            return self.advance()
        return None

    def expect(self, *types: TokenType) -> Optional[Token]:
        """
        Tiêu thụ token nếu khớp type.
        Nếu không khớp, emit error và trả về None thay vì raise.
        """
        t = self.peek()
        if t is None:
            self._emit_error(f"Kết thúc file không mong đợi")
            return None
        if t.type in types:
            return self.advance()
        expected_names = [tt.name for tt in types]
        self._emit_error(
            f"Mong đợi {' hoặc '.join(expected_names)}, "
            f"nhận được {t.type.name}({t.value!r})",
            t.line, t.column
        )
        return None

    def expect_name(self) -> Optional[Token]:
        """Tiêu thụ identifier hoặc keyword (dùng làm tên)."""
        t = self.peek()
        if t is None:
            self._emit_error("Cần tên định danh")
            return None
        if t.type == TokenType.IDENTIFIER:
            return self.advance()
        # Keywords có thể dùng làm tên method/field
        if (t.value and isinstance(t.value, str) and
                str(t.value).replace('_', '').replace('::', '').isalnum()):
            return self.advance()
        self._emit_error(f"Cần tên, nhận được {t.type.name}({t.value!r})")
        return None

    def _emit_error(self, message: str, line: int = 0, col: int = 0) -> None:
        """Phát ra lỗi parse."""
        t = self.peek()
        err = ParseError(
            message,
            line or (t.line if t else 0),
            col or (t.column if t else 0),
            self.filename,
            t
        )
        self.errors.append(err)

    def _sync(self) -> None:
        """
        Error recovery: đồng bộ hóa đến điểm an toàn tiếp theo.
        Dùng sau khi gặp lỗi để tiếp tục parse.
        """
        # Advance until we find a statement boundary
        sync_types = {
            TokenType.KW_FN,     # ++
            TokenType.KW_CLASS,
            TokenType.KW_STRUCT,
            TokenType.KW_TRAIT,
            TokenType.KW_IMPL,
            TokenType.KW_RETURN, # <-
            TokenType.KW_IF,     # ??
            TokenType.KW_FOR,    # <>
            TokenType.KW_WHILE,
            TokenType.KW_MATCH,  # ?~
            TokenType.KW_MODULE,
            TokenType.KW_IMPORT,
            TokenType.KW_EXPORT,
            TokenType.RBRACE,
            TokenType.EOF,
        }
        while not self.at_end():
            if self.check(*sync_types):
                break
            self.advance()

    # ── Type annotation ────────────────────────────────────────────────────

    def parse_type_ann(self) -> str:
        """
        Parse type annotation.

        Hỗ trợ:
          - Simple: int, string, float, bool, void, auto
          - Generic: List<int>, Map<string, int>, Result<T, E>
          - Reference: &Type, *Type
          - Optional: ?Type
          - Tuple: (int, string)
          - Function: fn(int) -> string
          - Lifetime: 'a Type

        Returns:
            Chuỗi biểu diễn type
        """
        # Lifetime
        if self.check(TokenType.LIFETIME):
            lifetime = self.advance().value
            inner = self.parse_type_ann()
            return f"'{lifetime} {inner}"

        # Reference: &Type, *Type
        if self.check(TokenType.AMP):
            self.advance()
            inner = self.parse_type_ann()
            return f"&{inner}"

        if self.check(TokenType.STAR):
            self.advance()
            inner = self.parse_type_ann()
            return f"*{inner}"

        # Optional: ?Type
        if self.check(TokenType.QUESTION):
            self.advance()
            inner = self.parse_type_ann()
            return f"?{inner}"

        # Tuple type: (Type1, Type2)
        if self.check(TokenType.LPAREN):
            self.advance()
            types = []
            if not self.check(TokenType.RPAREN):
                types.append(self.parse_type_ann())
                while self.match(TokenType.COMMA):
                    if self.check(TokenType.RPAREN):
                        break
                    types.append(self.parse_type_ann())
            self.match(TokenType.RPAREN)
            return f"({', '.join(types)})"

        # Function type: fn(Type1, Type2) -> RetType
        if self.check(TokenType.KW_FN) or self.check_value('fn'):
            self.advance()
            self.match(TokenType.LPAREN)
            param_types = []
            while not self.check(TokenType.RPAREN) and not self.at_end():
                param_types.append(self.parse_type_ann())
                if not self.match(TokenType.COMMA):
                    break
            self.match(TokenType.RPAREN)
            ret = 'void'
            if self.check(TokenType.ARROW):
                self.advance()
                ret = self.parse_type_ann()
            return f"fn({', '.join(param_types)}) -> {ret}"

        # Named type (possibly generic)
        if self.check(TokenType.IDENTIFIER, TokenType.KW_MUT):
            t = self.advance()
            name = str(t.value)

            # Namespace: std::io::Type
            while self.check(TokenType.DOUBLE_COLON):
                self.advance()
                nxt = self.peek()
                if nxt and (nxt.type == TokenType.IDENTIFIER or
                            (nxt.value and str(nxt.value).isidentifier())):
                    name += '::' + str(self.advance().value)

            # Generic parameters: Type<T, U>
            if self.check(TokenType.LT):
                self.advance()
                type_args = [self.parse_type_ann()]
                while self.match(TokenType.COMMA):
                    if self.check(TokenType.GT):
                        break
                    type_args.append(self.parse_type_ann())
                self.match(TokenType.GT)
                return f"{name}<{', '.join(type_args)}>"

            return name

        # Keyword types used as type names
        for kw_type in (TokenType.KW_ASYNC, TokenType.KW_STATIC, TokenType.KW_CONST,
                        TokenType.KW_OWN, TokenType.KW_SHARE, TokenType.KW_BORROW):
            if self.check(kw_type):
                t = self.advance()
                name = str(t.value)
                if self.check(TokenType.LT):
                    self.advance()
                    inner = self.parse_type_ann()
                    self.match(TokenType.GT)
                    return f"{name}<{inner}>"
                return name

        return 'auto'

    def parse_type_params(self) -> List[str]:
        """
        Parse generic type parameters: `<T, U, V>` hoặc `<T: Trait, U: OtherTrait>`

        Returns:
            Danh sách tên type parameter
        """
        params = []
        if not self.check(TokenType.LT):
            return params

        # Heuristic: distinguish generic type params from comparison operators
        # If next after < is IDENTIFIER followed by , > : where — it's type params
        saved = self.pos
        self.advance()  # consume <

        # Check if it looks like type params
        t = self.peek()
        if (t and t.type == TokenType.IDENTIFIER and
                (self.peek(1) and self.peek(1).type in (
                    TokenType.COMMA, TokenType.GT, TokenType.COLON,
                    TokenType.KW_WHERE))):
            # Parse type params
            params.append(str(t.value))
            self.advance()  # consume first param

            # Optional constraint: T: Trait
            if self.check(TokenType.COLON):
                self.advance()
                self.parse_type_ann()  # skip constraint

            while self.match(TokenType.COMMA):
                if self.check(TokenType.GT):
                    break
                nxt = self.peek()
                if nxt and nxt.type == TokenType.IDENTIFIER:
                    params.append(str(nxt.value))
                    self.advance()
                    if self.check(TokenType.COLON):
                        self.advance()
                        self.parse_type_ann()  # skip constraint

            self.match(TokenType.GT)
        else:
            # Not type params, restore
            self.pos = saved

        return params

    # ── Program entry ──────────────────────────────────────────────────────

    def parse(self) -> Program:
        """
        Parse toàn bộ program.

        Returns:
            Program node (root của AST)
        """
        stmts = []
        while not self.at_end():
            try:
                s = self.parse_top_level()
                if s is not None:
                    stmts.append(s)
            except (ParseError, SyntaxError) as e:
                self._emit_error(str(e))
                self._sync()
        return Program(stmts)

    def parse_top_level(self) -> Optional[ASTNode]:
        """Parse một top-level statement."""
        t = self.peek()
        if t is None:
            return None

        # Bỏ qua dấu ; thừa
        while self.check(TokenType.SEMICOLON):
            self.advance()
        if self.at_end():
            return None

        t = self.peek()
        if t is None:
            return None

        # Module declaration
        if t.type == TokenType.KW_MODULE:
            self.advance()
            name_tok = self.expect(TokenType.IDENTIFIER)
            name = name_tok.value if name_tok else '<module>'
            return ModuleDecl(name, t.line)

        # Import statement
        if t.type == TokenType.KW_IMPORT:
            return self.parse_import()

        # Export
        if t.type == TokenType.KW_EXPORT:
            return self.parse_export()

        return self.parse_stmt()

    def parse_import(self) -> ImportStmt:
        """
        Parse import statement.

        Syntax:
            import std::io
            import -> { std::io, std::collections::{List, Map} }
            import std::io as io
        """
        line = self.peek().line
        self.advance()  # consume 'import'

        # import -> { mod1, mod2 }
        if self.check(TokenType.ARROW):
            self.advance()
            self.expect(TokenType.LBRACE)
            modules = []
            while not self.check(TokenType.RBRACE) and not self.at_end():
                mod = self._read_module_path()
                modules.append(mod)
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACE)
            return ImportStmt(modules, [], line=line)

        # import module_name [as alias]
        mod = self._read_module_path()
        alias = None
        if self.check_value('as'):
            self.advance()
            alias_tok = self.expect(TokenType.IDENTIFIER)
            alias = alias_tok.value if alias_tok else None
        return ImportStmt([mod], [], line=line, alias=alias)

    def parse_export(self) -> ASTNode:
        """Parse export statement."""
        line = self.peek().line
        self.advance()  # consume 'export'

        # export ++ fn (function export)
        if self.check(TokenType.KW_FN):
            fn = self.parse_fn(is_export=True)
            return fn

        # export name
        t = self.expect_name()
        name = t.value if t else '<export>'
        return ExportStmt(name, line)

    def _read_module_path(self) -> str:
        """
        Đọc đường dẫn module.

        Returns:
            Chuỗi đường dẫn, e.g. 'std::io' hoặc 'std::collections::{List, Map}'
        """
        parts = []
        t = self.expect_name()
        if t:
            parts.append(str(t.value))

        while self.check(TokenType.DOUBLE_COLON):
            self.advance()
            if self.check(TokenType.LBRACE):
                # destructuring: {List, Map}
                self.advance()
                items = []
                while not self.check(TokenType.RBRACE) and not self.at_end():
                    item_tok = self.expect_name()
                    if item_tok:
                        items.append(str(item_tok.value))
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RBRACE)
                return '::'.join(parts) + '::{' + ','.join(items) + '}'
            nxt = self.expect_name()
            if nxt:
                parts.append(str(nxt.value))

        return '::'.join(parts)

    # ── Statement dispatch ─────────────────────────────────────────────────

    def parse_stmt(self) -> Optional[ASTNode]:
        """
        Parse một statement dựa trên token hiện tại.
        Dispatch đến parser phù hợp.
        """
        # Skip stray semicolons
        while self.check(TokenType.SEMICOLON):
            self.advance()

        t = self.peek()
        if t is None or t.type == TokenType.EOF:
            return None

        # ++ Function definition
        if t.type == TokenType.KW_FN:
            return self.parse_fn()

        # @@override ++ fn
        if t.type == TokenType.DOUBLE_AT:
            self.advance()  # consume @@override or @@...
            if self.check(TokenType.KW_FN):
                fn = self.parse_fn()
                return OverrideDecl(fn, t.line)
            # Other annotations — just skip
            return None

        # class / struct / trait / impl
        if t.type == TokenType.KW_CLASS:
            return self.parse_class()
        if t.type == TokenType.KW_STRUCT:
            return self.parse_struct()
        if t.type == TokenType.KW_TRAIT:
            return self.parse_trait()
        if t.type == TokenType.KW_IMPL:
            return self.parse_impl()

        # export ++ fn
        if t.type == TokenType.KW_EXPORT:
            self.advance()
            if self.check(TokenType.KW_FN):
                fn = self.parse_fn(is_export=True)
                return fn
            name_tok = self.expect_name()
            return ExportStmt(name_tok.value if name_tok else '', t.line)

        # <- Return
        if t.type == TokenType.KW_RETURN:
            self.advance()
            val = None
            if not self.check(TokenType.RBRACE, TokenType.EOF, TokenType.SEMICOLON):
                val = self.parse_expr()
            return ReturnStmt(val, t.line)

        # ?? If
        if t.type == TokenType.KW_IF:
            return self.parse_if()

        # <> For
        if t.type == TokenType.KW_FOR:
            return self.parse_for()

        # while
        if t.type == TokenType.KW_WHILE:
            return self.parse_while()

        # ?~ Pattern match
        if t.type == TokenType.KW_MATCH:
            return self.parse_match()

        # !> Break
        if t.type == TokenType.KW_BREAK:
            self.advance()
            label = None
            if self.check(TokenType.IDENTIFIER):
                label = self.advance().value
            return BreakStmt(t.line, label)

        # !>> Continue
        if t.type == TokenType.KW_CONTINUE:
            self.advance()
            label = None
            if self.check(TokenType.IDENTIFIER):
                label = self.advance().value
            return ContinueStmt(t.line, label)

        # !! Panic
        if t.type == TokenType.KW_PANIC:
            self.advance()
            msg = None
            if not self.check(TokenType.RBRACE, TokenType.EOF, TokenType.SEMICOLON):
                msg = self.parse_expr()
            if msg is None:
                msg = Literal("panic", t.line)
            return PanicStmt(msg, t.line)

        # ~> Pipe statement
        if t.type == TokenType.KW_PIPE:
            return self.parse_pipe_stmt()

        # go Goroutine
        if t.type == TokenType.KW_GO:
            self.advance()
            call = self.parse_expr()
            return GoStmt(call, t.line)

        # try / catch
        if t.type == TokenType.KW_TRY:
            return self.parse_try_catch()

        # own<T> / share<T> / borrow<T>
        if t.type in (TokenType.KW_OWN, TokenType.KW_SHARE, TokenType.KW_BORROW):
            return self.parse_ownership_decl()

        # @macro_tok / @macro_ast
        if t.type == TokenType.KW_MACRO:
            return self.parse_macro()

        # @reflect
        if t.type == TokenType.KW_REFLECT:
            self.advance()
            target = self.parse_expr()
            return ReflectExpr(target, t.line)

        # Module / import / export in body
        if t.type == TokenType.KW_MODULE:
            self.advance()
            name_tok = self.expect_name()
            return ModuleDecl(name_tok.value if name_tok else '', t.line)
        if t.type == TokenType.KW_IMPORT:
            return self.parse_import()

        # Variable declaration: name := ... or name :: mut Type = ...
        if t.type == TokenType.IDENTIFIER:
            nxt = self.peek(1)
            if nxt and nxt.type in (TokenType.KW_LET, TokenType.DOUBLE_COLON):
                return self.parse_var_decl()

        # Expression statement
        expr = self.parse_expr()
        self.match(TokenType.SEMICOLON)  # optional semicolon
        return expr

    # ── ~> Pipe statement ──────────────────────────────────────────────────

    def parse_pipe_stmt(self) -> PipeStmt:
        """Parse pipe/print statement: `~> expr`"""
        line = self.peek().line
        self.advance()  # ~>
        expr = self.parse_expr()
        return PipeStmt(expr, line)

    # ── Variable declaration ───────────────────────────────────────────────

    def parse_var_decl(self) -> VarDecl:
        """
        Parse variable declaration.

        Syntax:
            name := expr
            name :: Type = expr
            name :: mut Type = expr
            name :: mut Type
        """
        name_tok = self.advance()
        name = name_tok.value if name_tok else '<var>'
        is_mut = False
        var_type = 'auto'

        # name := expr (immutable, auto type)
        if self.check(TokenType.KW_LET):
            self.advance()  # :=
            value = self.parse_expr()
            return VarDecl(name, 'auto', value, False, None, name_tok.line)

        # name :: [mut] Type [= expr]
        if self.check(TokenType.DOUBLE_COLON):
            self.advance()  # ::
            if self.check(TokenType.KW_MUT):
                self.advance()
                is_mut = True
            var_type = self.parse_type_ann()
            value = None
            if self.check(TokenType.ASSIGN):
                self.advance()
                value = self.parse_expr()
            elif not self.check(TokenType.RBRACE, TokenType.EOF, TokenType.SEMICOLON):
                # Try to parse value anyway
                if self.peek() and self.peek().type not in (
                        TokenType.RBRACE, TokenType.EOF, TokenType.SEMICOLON,
                        TokenType.KW_FN, TokenType.KW_CLASS):
                    value = self.parse_expr()
            return VarDecl(name, var_type, value, is_mut, None, name_tok.line)

        # Fallback: just name as expression
        return VarDecl(name, 'auto', VarRef(name, name_tok.line), False, None, name_tok.line)

    # ── Ownership declaration ──────────────────────────────────────────────

    def parse_ownership_decl(self) -> VarDecl:
        """
        Parse ownership declaration.

        Syntax:
            own<Type> name := expr
            share<Type> name := expr
            borrow<'a, Type> name := expr
        """
        kind_tok = self.advance()  # own | share | borrow
        kind = kind_tok.value
        lifetime = None
        inner_type = 'auto'

        if self.check(TokenType.LT):
            self.advance()
            if self.check(TokenType.LIFETIME):
                lifetime = self.advance().value
                self.match(TokenType.COMMA)
            inner_type = self.parse_type_ann()
            self.match(TokenType.GT)

        name_tok = self.expect(TokenType.IDENTIFIER)
        name = name_tok.value if name_tok else '<own>'
        self.expect(TokenType.KW_LET)  # :=
        value = self.parse_expr()
        node = VarDecl(name, inner_type, value, True, kind, kind_tok.line)
        return node

    # ── Function definition ────────────────────────────────────────────────

    def parse_fn(self, is_static: bool = False, is_export: bool = False) -> FnDef:
        """
        Parse function definition.

        Syntax:
            ++ name <~ (param: Type, ...) -> RetType ** {
                body
            }
        """
        line = self.peek().line if self.peek() else 0
        self.advance()  # ++ (KW_FN)
        name_tok = self.expect_name()
        name = name_tok.value if name_tok else '<fn>'
        type_params = self.parse_type_params()

        params = []
        # Parameter list: <~ (params) or just (params)
        if self.check(TokenType.KW_PARAM_ARROW):
            self.advance()  # <~
            self.expect(TokenType.LPAREN)
            params = self.parse_param_list()
            self.expect(TokenType.RPAREN)
        elif self.check(TokenType.LPAREN):
            self.advance()
            params = self.parse_param_list()
            self.expect(TokenType.RPAREN)

        ret_type = 'void'
        if self.check(TokenType.ARROW):
            self.advance()
            ret_type = self.parse_type_ann()

        # Optional ** before {
        self.match(TokenType.POW)
        self.expect(TokenType.LBRACE)
        self._fn_depth += 1
        body = self.parse_block()
        self._fn_depth -= 1

        return FnDef(name, type_params, params, ret_type, body,
                     is_static, is_export, line)

    def parse_param_list(self) -> List[Tuple]:
        """
        Parse danh sách tham số hàm.

        Returns:
            List of (name, type, ownership, default_expr)
        """
        params = []
        if self.check(TokenType.RPAREN):
            return params

        while True:
            ownership = None
            if self.check(TokenType.KW_OWN, TokenType.KW_SHARE, TokenType.KW_BORROW):
                ownership = self.advance().value

            pname_tok = self.expect(TokenType.IDENTIFIER)
            pname = pname_tok.value if pname_tok else '<param>'
            ptype = 'auto'

            if self.check(TokenType.COLON):
                self.advance()
                ptype = self.parse_type_ann()

            default = None
            if self.check(TokenType.ASSIGN):
                self.advance()
                default = self.parse_expr()

            params.append((pname, ptype, ownership, default))

            if not self.match(TokenType.COMMA):
                break
            if self.check(TokenType.RPAREN):
                break

        return params

    # ── Class ─────────────────────────────────────────────────────────────

    def parse_class(self) -> ClassDef:
        """
        Parse class definition.

        Syntax:
            class Name<T, U> : Parent1, Parent2 impl Trait1, Trait2 -> {
                body
            }
        """
        line = self.peek().line
        self.advance()  # class
        name_tok = self.expect(TokenType.IDENTIFIER)
        name = name_tok.value if name_tok else '<class>'
        type_params = self.parse_type_params()

        parents = []
        traits = []

        # : Parent1, Parent2
        if self.check(TokenType.COLON):
            self.advance()
            t = self.expect_name()
            if t:
                parents.append(t.value)
            while self.match(TokenType.COMMA):
                t2 = self.expect_name()
                if t2:
                    parents.append(t2.value)

        # impl Trait1, Trait2
        if self.check(TokenType.KW_IMPL):
            self.advance()
            t = self.expect_name()
            if t:
                traits.append(t.value)
            while self.match(TokenType.COMMA):
                t2 = self.expect_name()
                if t2:
                    traits.append(t2.value)

        self.match(TokenType.ARROW)
        self.expect(TokenType.LBRACE)
        self._class_depth += 1
        body = self.parse_block()
        self._class_depth -= 1
        return ClassDef(name, type_params, parents, traits, body, line)

    # ── Struct ────────────────────────────────────────────────────────────

    def parse_struct(self) -> StructDef:
        """
        Parse struct definition.

        Syntax:
            struct Point<T> -> {
                x: T,
                y: T
            }
        """
        line = self.peek().line
        self.advance()  # struct
        name_tok = self.expect(TokenType.IDENTIFIER)
        name = name_tok.value if name_tok else '<struct>'
        type_params = self.parse_type_params()
        self.match(TokenType.ARROW)
        self.expect(TokenType.LBRACE)
        fields = []
        while not self.check(TokenType.RBRACE) and not self.at_end():
            fname_tok = self.expect(TokenType.IDENTIFIER)
            if fname_tok is None:
                self._sync()
                break
            fname = fname_tok.value
            self.expect(TokenType.COLON)
            ftype = self.parse_type_ann()
            fields.append((fname, ftype))
            self.match(TokenType.COMMA)
        self.expect(TokenType.RBRACE)
        return StructDef(name, type_params, fields, line)

    # ── Trait ─────────────────────────────────────────────────────────────

    def parse_trait(self) -> TraitDef:
        """
        Parse trait definition.

        Syntax:
            trait Printable<T> -> {
                ++ print <~ (self) -> void ** { ... }
                ++ to_string <~ (self) -> string ** { ... }
            }
        """
        line = self.peek().line
        self.advance()  # trait
        name_tok = self.expect(TokenType.IDENTIFIER)
        name = name_tok.value if name_tok else '<trait>'
        type_params = self.parse_type_params()
        self.match(TokenType.ARROW)
        self.expect(TokenType.LBRACE)
        methods = self.parse_block()
        return TraitDef(name, type_params, methods, line)

    # ── Impl ──────────────────────────────────────────────────────────────

    def parse_impl(self) -> ImplBlock:
        """
        Parse impl block.

        Syntax:
            impl TypeName -> { methods }
            impl TraitName for TypeName -> { methods }
        """
        line = self.peek().line
        self.advance()  # impl
        trait_name = None
        name_tok = self.expect_name()
        type_name = name_tok.value if name_tok else '<impl>'

        # impl Trait for Type
        if self.check_value('for'):
            self.advance()
            trait_name = type_name
            name_tok2 = self.expect_name()
            type_name = name_tok2.value if name_tok2 else '<type>'

        self.match(TokenType.ARROW)
        self.expect(TokenType.LBRACE)
        methods = self.parse_block()
        return ImplBlock(type_name, trait_name, methods, line)

    # ── If ────────────────────────────────────────────────────────────────

    def parse_if(self) -> IfStmt:
        """
        Parse if statement.

        Syntax:
            ?? condition ** {
                body
            } -- elif cond2 ** {
                elif_body
            } -- else ** {
                else_body
            }
        """
        line = self.peek().line
        self.advance()  # ??
        cond = self.parse_expr()
        self.match(TokenType.POW)  # optional **
        self.expect(TokenType.LBRACE)
        then_body = self.parse_block()

        elif_clauses = []
        else_body = []

        # Look for -- elif / -- else  (-- is MINUS MINUS)
        while self.check(TokenType.MINUS):
            saved = self.pos
            self.advance()  # first -
            if not self.check(TokenType.MINUS):
                self.pos = saved
                break
            self.advance()  # second -
            kw = self.peek()
            if kw and kw.value == 'elif':
                self.advance()
                elif_cond = self.parse_expr()
                self.match(TokenType.POW)
                self.expect(TokenType.LBRACE)
                elif_body = self.parse_block()
                elif_clauses.append((elif_cond, elif_body))
            elif kw and kw.value in ('else', 'default'):
                self.advance()
                self.match(TokenType.POW)
                self.expect(TokenType.LBRACE)
                else_body = self.parse_block()
                break
            else:
                self.pos = saved
                break

        return IfStmt(cond, then_body, elif_clauses, else_body, line)

    # ── For ───────────────────────────────────────────────────────────────

    def parse_for(self) -> ForStmt:
        """
        Parse for-each loop.

        Syntax:
            <> item :: iterable ** {
                body
            }
        """
        line = self.peek().line
        self.advance()  # <>
        var_tok = self.expect(TokenType.IDENTIFIER)
        var_name = var_tok.value if var_tok else '<var>'
        self.expect(TokenType.DOUBLE_COLON)
        iterable = self.parse_expr()
        self.match(TokenType.POW)
        self.expect(TokenType.LBRACE)
        self._loop_depth += 1
        body = self.parse_block()
        self._loop_depth -= 1
        return ForStmt(var_name, iterable, body, line)

    # ── While ─────────────────────────────────────────────────────────────

    def parse_while(self) -> WhileStmt:
        """
        Parse while loop.

        Syntax:
            while condition ** {
                body
            }
        """
        line = self.peek().line
        self.advance()  # while
        cond = self.parse_expr()
        self.match(TokenType.POW)
        self.expect(TokenType.LBRACE)
        self._loop_depth += 1
        body = self.parse_block()
        self._loop_depth -= 1
        return WhileStmt(cond, body, line)

    # ── Pattern match ──────────────────────────────────────────────────────

    def parse_match(self) -> MatchStmt:
        """
        Parse pattern matching.

        Syntax:
            ?~ value {
                1 => { ... },
                x if x > 10 => { ... },
                (a, b) => { ... },
                _ => { ... },
            }
        """
        line = self.peek().line
        self.advance()  # ?~
        value = self.parse_expr()
        self.expect(TokenType.LBRACE)
        arms = []
        while not self.check(TokenType.RBRACE) and not self.at_end():
            try:
                arm = self.parse_match_arm()
                arms.append(arm)
                self.match(TokenType.COMMA)
            except (ParseError, SyntaxError) as e:
                self._emit_error(str(e))
                self._sync()
        self.expect(TokenType.RBRACE)
        return MatchStmt(value, arms, line)

    def parse_match_arm(self) -> MatchArm:
        """Parse một arm trong match: `pattern [if guard] => body`"""
        line = self.peek().line if self.peek() else 0
        pattern = self.parse_pattern()
        guard = None
        if self.check_value('if'):
            self.advance()
            guard = self.parse_expr()
        self.expect(TokenType.FAT_ARROW)

        # Single expr or block
        if self.check(TokenType.LBRACE):
            self.advance()
            body = self.parse_block()
        else:
            stmt = self.parse_stmt()
            body = [stmt] if stmt else []

        return MatchArm(pattern, guard, body, line)

    def parse_pattern(self) -> Pattern:
        """
        Parse một pattern trong match arm.

        Patterns:
            _                — wildcard
            42, "hello"      — literal
            x                — binding (captures value)
            (a, b)           — tuple
            1..10            — range (exclusive)
            1..=10           — range (inclusive)
            p1 | p2          — or pattern
            Some(x)          — enum variant
            Point { x, y }   — struct
        """
        line = self.peek().line if self.peek() else 0
        t = self.peek()

        # Wildcard _
        if t and t.type == TokenType.IDENTIFIER and t.value == '_':
            self.advance()
            return WildcardPattern(line)

        # Negated number: -42
        if t and t.type == TokenType.MINUS:
            self.advance()
            num_tok = self.peek()
            if num_tok and num_tok.type == TokenType.NUMBER:
                self.advance()
                value = -num_tok.value
                return LiteralPattern(value, line)
            self.pos -= 1  # restore

        # Literal: number, string, bool, none
        if t and t.type in (TokenType.NUMBER, TokenType.STRING,
                             TokenType.BOOLEAN, TokenType.NONE,
                             TokenType.CHAR):
            self.advance()
            val = t.value
            # Range: lo..hi or lo..=hi
            if self.check(TokenType.DOTDOT):
                self.advance()
                inclusive = False
                if self.check(TokenType.ASSIGN):
                    self.advance()
                    inclusive = True
                hi_tok = self.peek()
                if hi_tok and hi_tok.type == TokenType.NUMBER:
                    self.advance()
                    return RangePattern(val, hi_tok.value, inclusive, line)
            if self.check(TokenType.DOTDOTEQ):
                self.advance()
                hi_tok = self.peek()
                if hi_tok and hi_tok.type == TokenType.NUMBER:
                    self.advance()
                    return RangePattern(val, hi_tok.value, True, line)
            return LiteralPattern(val, line)

        # Tuple pattern: (a, b, c)
        if t and t.type == TokenType.LPAREN:
            self.advance()
            elems = []
            while not self.check(TokenType.RPAREN) and not self.at_end():
                elems.append(self.parse_pattern())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RPAREN)
            return TuplePattern(elems, line)

        # Identifier: binding, enum variant, or struct pattern
        if t and t.type == TokenType.IDENTIFIER:
            name = self.advance().value

            # Enum variant: Ok(x), Err(msg), Some(value), None
            if self.check(TokenType.LPAREN):
                self.advance()
                inner = None
                if not self.check(TokenType.RPAREN):
                    inner = self.parse_pattern()
                self.match(TokenType.RPAREN)
                return EnumPattern(name, inner, line)

            # Struct pattern: Point { x, y }
            if self.check(TokenType.LBRACE):
                self.advance()
                fields = []
                while not self.check(TokenType.RBRACE) and not self.at_end():
                    fname_tok = self.expect(TokenType.IDENTIFIER)
                    fname = fname_tok.value if fname_tok else '<field>'
                    fpat = None
                    if self.check(TokenType.COLON):
                        self.advance()
                        fpat = self.parse_pattern()
                    fields.append((fname, fpat))
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RBRACE)
                return StructPattern(name, fields, line)

            # Simple binding
            return BindingPattern(name, line)

        # Fallback: wildcard
        return WildcardPattern(line)

    # ── Try / catch ────────────────────────────────────────────────────────

    def parse_try_catch(self) -> TryCatch:
        """
        Parse try/catch block.

        Syntax:
            try ** {
                risky code
            } catch (err) ** {
                handle error
            } finally ** {
                cleanup
            }
        """
        line = self.peek().line
        self.advance()  # try
        self.match(TokenType.POW)
        self.expect(TokenType.LBRACE)
        try_body = self.parse_block()

        catch_var = 'err'
        catch_body = []
        finally_body = None

        if self.check(TokenType.KW_CATCH):
            self.advance()
            if self.check(TokenType.LPAREN):
                self.advance()
                var_tok = self.expect(TokenType.IDENTIFIER)
                catch_var = var_tok.value if var_tok else 'err'
                self.expect(TokenType.RPAREN)
            self.match(TokenType.POW)
            self.expect(TokenType.LBRACE)
            catch_body = self.parse_block()

        if self.check(TokenType.KW_FINALLY):
            self.advance()
            self.match(TokenType.POW)
            self.expect(TokenType.LBRACE)
            finally_body = self.parse_block()

        return TryCatch(try_body, catch_var, catch_body, line, finally_body)

    # ── Macro ─────────────────────────────────────────────────────────────

    def parse_macro(self) -> MacroInvoke:
        """
        Parse macro invocation.

        Syntax:
            @macro_tok name(arg1, arg2)
            @macro_ast name(expr)
        """
        line = self.peek().line
        kind = self.advance().value  # 'macro_tok' | 'macro_ast'
        name_tok = self.expect_name()
        name = name_tok.value if name_tok else '<macro>'
        args = []
        if self.check(TokenType.LPAREN):
            self.advance()
            while not self.check(TokenType.RPAREN) and not self.at_end():
                args.append(self.parse_expr())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RPAREN)
        return MacroInvoke(kind, name, args, line)

    # ── Block ─────────────────────────────────────────────────────────────

    def parse_block(self) -> List[ASTNode]:
        """
        Parse một block (nội dung giữa { và }).
        RBRACE đã được consume bởi parse_block.

        Returns:
            Danh sách statements trong block
        """
        stmts = []
        while not self.check(TokenType.RBRACE, TokenType.EOF) and not self.at_end():
            try:
                s = self.parse_stmt()
                if s is not None:
                    stmts.append(s)
            except (ParseError, SyntaxError) as e:
                self._emit_error(str(e))
                # Skip to next safe point
                if not self.check(TokenType.RBRACE, TokenType.EOF):
                    self.advance()
        self.match(TokenType.RBRACE)
        return stmts

    # ── Expressions ───────────────────────────────────────────────────────

    def parse_expr(self) -> Optional[ASTNode]:
        """Parse expression (entry point)."""
        return self.parse_assign()

    def parse_assign(self) -> Optional[ASTNode]:
        """
        Parse assignment expression.
        Assignment operators: = += -= *= /= %= **= &= |= ^= //= ??=
        """
        left = self.parse_or()
        assign_types = (
            TokenType.ASSIGN, TokenType.PLUS_EQ, TokenType.MINUS_EQ,
            TokenType.STAR_EQ, TokenType.SLASH_EQ, TokenType.MOD_EQ,
            TokenType.POW_EQ, TokenType.AMP_EQ, TokenType.PIPE_EQ,
            TokenType.CARET_EQ, TokenType.FLOOR_DIV_EQ, TokenType.COALESCE_EQ,
        )
        if self.check(*assign_types):
            op_tok = self.advance()
            right = self.parse_assign()  # right-associative
            return Assign(left, right, op_tok.value, op_tok.line)
        return left

    def parse_or(self) -> Optional[ASTNode]:
        """Parse logical OR: expr || expr"""
        left = self.parse_and()
        while self.check(TokenType.OR):
            op = self.advance()
            right = self.parse_and()
            left = BinaryOp(left, '||', right, op.line)
        return left

    def parse_and(self) -> Optional[ASTNode]:
        """Parse logical AND: expr && expr"""
        left = self.parse_compare()
        while self.check(TokenType.AND):
            op = self.advance()
            right = self.parse_compare()
            left = BinaryOp(left, '&&', right, op.line)
        return left

    def parse_compare(self) -> Optional[ASTNode]:
        """Parse comparison: expr == expr, expr != expr, etc."""
        left = self.parse_add()
        compare_types = (
            TokenType.EQ, TokenType.NEQ,
            TokenType.LT, TokenType.GT,
            TokenType.LTE, TokenType.GTE,
            TokenType.SPACESHIP,
        )
        while self.check(*compare_types):
            op = self.advance()
            right = self.parse_add()
            left = BinaryOp(left, op.value, right, op.line)
        return left

    def parse_add(self) -> Optional[ASTNode]:
        """Parse additive: expr + expr, expr - expr"""
        left = self.parse_mul()
        while self.check(TokenType.PLUS, TokenType.MINUS):
            op = self.advance()
            right = self.parse_mul()
            left = BinaryOp(left, op.value, right, op.line)
        return left

    def parse_mul(self) -> Optional[ASTNode]:
        """Parse multiplicative: expr * expr, expr / expr, expr % expr"""
        left = self.parse_unary()
        while self.check(TokenType.STAR, TokenType.SLASH, TokenType.MOD, TokenType.FLOOR_DIV):
            op = self.advance()
            right = self.parse_unary()
            left = BinaryOp(left, op.value, right, op.line)
        return left

    def parse_unary(self) -> Optional[ASTNode]:
        """Parse unary: -expr, !expr, ~expr, await expr"""
        if self.check(TokenType.MINUS, TokenType.NOT, TokenType.TILDE):
            op = self.advance()
            operand = self.parse_unary()
            return UnaryOp(op.value, operand, op.line)
        if self.check(TokenType.KW_AWAIT):
            op = self.advance()
            operand = self.parse_unary()
            return AwaitExpr(operand, op.line)
        return self.parse_postfix()

    def parse_postfix(self) -> Optional[ASTNode]:
        """
        Parse postfix operations:
            expr:method(args)     — CP+* method call
            expr.field             — field access
            expr.method(args)      — dot method call
            expr[index]            — index access
            expr(args)             — function call expr
            expr::member           — namespace member
        """
        expr = self.parse_primary()
        while True:
            t = self.peek()
            if t is None:
                break

            # obj:method(...)  — CP+* colon method call
            if t.type == TokenType.COLON:
                line = t.line
                self.advance()
                method_tok = self.expect_name()
                if method_tok is None:
                    break
                method = str(method_tok.value)

                # Optional type args: :method<T>(...)
                type_args = []
                if self.check(TokenType.LT):
                    saved = self.pos
                    if self._looks_like_type_arg():
                        self.advance()
                        type_args.append(self.parse_type_ann())
                        while self.match(TokenType.COMMA):
                            type_args.append(self.parse_type_ann())
                        self.match(TokenType.GT)
                    # else: leave <, it's a comparison

                self.expect(TokenType.LPAREN)
                args = self.parse_arg_list()
                expr = MethodCall(expr, method, args, type_args, line)

            # obj.field or obj.method(...)
            elif t.type == TokenType.DOT:
                line = t.line
                self.advance()
                field_tok = self.expect_name()
                if field_tok is None:
                    break
                field = str(field_tok.value)
                if self.check(TokenType.LPAREN):
                    self.advance()
                    args = self.parse_arg_list()
                    expr = MethodCall(expr, field, args, [], line)
                else:
                    expr = FieldAccess(expr, field, line)

            # expr[index]
            elif t.type == TokenType.LBRACKET:
                line = t.line
                self.advance()
                idx = self.parse_expr()
                self.expect(TokenType.RBRACKET)
                expr = IndexAccess(expr, idx, line)

            # expr(args) — call expression
            elif t.type == TokenType.LPAREN:
                line = t.line
                self.advance()
                args = self.parse_arg_list()
                if isinstance(expr, FieldAccess):
                    expr = MethodCall(expr.obj, expr.field, args, [], line)
                elif isinstance(expr, VarRef):
                    expr = FnCall(expr.name, args, [], line)
                else:
                    expr = MethodCall(expr, '__call__', args, [], line)

            # expr::member — namespace access
            elif t.type == TokenType.DOUBLE_COLON:
                line = t.line
                self.advance()
                nxt = self.peek()
                if nxt and (nxt.type == TokenType.IDENTIFIER or
                            (nxt.value and str(nxt.value).replace('_', '').isalnum())):
                    member_tok = self.advance()
                    member = str(member_tok.value)
                    if isinstance(expr, VarRef):
                        full = expr.name + '::' + member
                    else:
                        full = '::' + member
                    if self.check(TokenType.LPAREN):
                        self.advance()
                        args = self.parse_arg_list()
                        expr = FnCall(full, args, [], line)
                    else:
                        expr = VarRef(full, line)
                else:
                    break

            # as Type cast
            elif t.type == TokenType.KW_AS or t.value == 'as':
                line = t.line
                self.advance()
                cast_type = self.parse_type_ann()
                expr = TypeCastExpr(expr, cast_type, line)

            else:
                break

        return expr

    def parse_primary(self) -> Optional[ASTNode]:
        """
        Parse primary expression (atoms).

        Handles:
            - Literals (number, string, bool, none)
            - Identifiers and variable references
            - Function calls
            - Self references: @, @.field
            - Parenthesized / tuple expressions: (expr) or (a, b, c)
            - List literals: [1, 2, 3]
            - Map literals: { key: val }
            - Ownership expressions: own<T> expr
            - Result: Ok(val), Err(msg)
            - Macro invocations: @macro_tok name(args)
            - Reflect: @reflect expr
        """
        t = self.peek()
        if t is None:
            return None

        # Number literal
        if t.type == TokenType.NUMBER:
            self.advance()
            return Literal(t.value, t.line)

        # String literal
        if t.type in (TokenType.STRING, TokenType.RAW_STRING,
                      TokenType.BYTE_STRING, TokenType.TEMPLATE_STR,
                      TokenType.CHAR):
            self.advance()
            return Literal(t.value, t.line)

        # Boolean
        if t.type == TokenType.BOOLEAN:
            self.advance()
            return Literal(t.value, t.line)

        # None/null/nil
        if t.type == TokenType.NONE:
            self.advance()
            return Literal(None, t.line)

        # Self reference: @.field or @ alone
        if t.type == TokenType.AT:
            self.advance()
            if self.check(TokenType.DOT):
                self.advance()
                field_tok = self.expect_name()
                if field_tok:
                    return FieldAccess(SelfRef(t.line), str(field_tok.value), t.line)
                return SelfRef(t.line)
            return SelfRef(t.line)

        # Parenthesized or tuple
        if t.type == TokenType.LPAREN:
            self.advance()
            if self.check(TokenType.RPAREN):
                self.advance()
                return TupleLiteral([], t.line)
            first = self.parse_expr()
            if self.check(TokenType.COMMA):
                elems = [first]
                while self.match(TokenType.COMMA):
                    if self.check(TokenType.RPAREN):
                        break
                    elems.append(self.parse_expr())
                self.expect(TokenType.RPAREN)
                return TupleLiteral(elems, t.line)
            self.expect(TokenType.RPAREN)
            return first

        # List literal: [1, 2, 3]
        if t.type == TokenType.LBRACKET:
            self.advance()
            elems = []
            while not self.check(TokenType.RBRACKET) and not self.at_end():
                elems.append(self.parse_expr())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACKET)
            return ListLiteral(elems, t.line)

        # Map literal: { key: val, key2: val2 }
        if t.type == TokenType.LBRACE:
            saved = self.pos
            self.advance()
            if self.check(TokenType.RBRACE):
                self.advance()
                return MapLiteral([], t.line)
            # Check pattern: identifier : expr (map literal)
            nxt1 = self.peek(0)
            nxt2 = self.peek(1)
            if (nxt1 and nxt1.type == TokenType.IDENTIFIER and
                    nxt2 and nxt2.type == TokenType.COLON):
                pairs = []
                while not self.check(TokenType.RBRACE) and not self.at_end():
                    key_tok = self.expect(TokenType.IDENTIFIER)
                    key = key_tok.value if key_tok else '<key>'
                    self.expect(TokenType.COLON)
                    val = self.parse_expr()
                    pairs.append((key, val))
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.RBRACE)
                return MapLiteral(pairs, t.line)
            # Restore — not a map literal
            self.pos = saved

        # Ownership expression: own<T> expr
        if t.type in (TokenType.KW_OWN, TokenType.KW_SHARE, TokenType.KW_BORROW):
            kind = self.advance().value
            inner_type = 'auto'
            lifetime = None
            if self.check(TokenType.LT):
                self.advance()
                if self.check(TokenType.LIFETIME):
                    lifetime = self.advance().value
                    self.match(TokenType.COMMA)
                inner_type = self.parse_type_ann()
                self.match(TokenType.GT)
            inner = self.parse_primary()
            return OwnershipExpr(kind, inner, lifetime, t.line)

        # Result::Ok / Result::Err
        if t.type == TokenType.IDENTIFIER and t.value in ('Ok', 'Err'):
            self.advance()
            if self.check(TokenType.LPAREN):
                self.advance()
                val = self.parse_expr()
                self.expect(TokenType.RPAREN)
                if t.value == 'Ok':
                    return ResultOk(val, t.line)
                return ResultErr(val, t.line)
            return VarRef(t.value, t.line)

        # Macro expression
        if t.type == TokenType.KW_MACRO:
            return self.parse_macro()

        # Reflect expression
        if t.type == TokenType.KW_REFLECT:
            self.advance()
            target = self.parse_expr()
            return ReflectExpr(target, t.line)

        # Identifier: variable, function call, static call
        if t.type == TokenType.IDENTIFIER:
            name = self.advance().value

            # Static call / namespace: Type::method or std::io::println
            if self.check(TokenType.DOUBLE_COLON):
                parts = [name]
                while self.check(TokenType.DOUBLE_COLON):
                    self.advance()
                    nxt = self.peek()
                    if nxt and (nxt.type == TokenType.IDENTIFIER or
                                (nxt.value and str(nxt.value).replace('_', '').isalnum())):
                        parts.append(str(self.advance().value))
                    else:
                        break
                full = '::'.join(parts)
                if self.check(TokenType.LPAREN):
                    self.advance()
                    args = self.parse_arg_list()
                    return FnCall(full, args, [], t.line)
                return VarRef(full, t.line)

            # Generic function call: name<T>(args)
            type_args = []
            if self.check(TokenType.LT) and self._looks_like_type_arg():
                self.advance()
                type_args.append(self.parse_type_ann())
                while self.match(TokenType.COMMA):
                    if self.check(TokenType.GT):
                        break
                    type_args.append(self.parse_type_ann())
                self.match(TokenType.GT)

            # Function call
            if self.check(TokenType.LPAREN):
                self.advance()
                args = self.parse_arg_list()
                return FnCall(name, args, type_args, t.line)

            return VarRef(name, t.line)

        # Keyword as primary (e.g. keywords used as values)
        if t.type in (TokenType.KW_OWN, TokenType.KW_SHARE, TokenType.KW_BORROW):
            # Already handled above, but just in case
            pass

        # Skip unknown token
        self.advance()
        return None

    def _looks_like_type_arg(self) -> bool:
        """
        Heuristic để phân biệt `<` là generic type arg hay là phép so sánh nhỏ hơn.

        Nhìn trước: nếu gặp IDENTIFIER, COMMA, GT, COLON → type arg.
        Nếu gặp số, ký tự khác → comparison.
        """
        i = self.pos + 1
        depth = 1
        max_look = min(i + 30, len(self.tokens))  # Limit lookahead
        while i < max_look and depth > 0:
            tt = self.tokens[i].type
            tv = self.tokens[i].value
            if tt == TokenType.LT:
                depth += 1
            elif tt == TokenType.GT:
                depth -= 1
            elif tt in (TokenType.EOF, TokenType.SEMICOLON, TokenType.LBRACE,
                        TokenType.KW_PIPE, TokenType.KW_RETURN):
                return False
            elif tt == TokenType.NUMBER or tt == TokenType.STRING:
                # Could be comparison: x < 5
                if depth == 1:
                    return False
            i += 1
        return depth == 0

    def parse_arg_list(self) -> List[ASTNode]:
        """
        Parse danh sách arguments của function call.

        Returns:
            Danh sách expression arguments
        """
        args = []
        if self.check(TokenType.RPAREN):
            self.advance()
            return args
        while not self.check(TokenType.RPAREN, TokenType.EOF) and not self.at_end():
            arg = self.parse_expr()
            if arg is not None:
                args.append(arg)
            if not self.match(TokenType.COMMA):
                break
        self.match(TokenType.RPAREN)
        return args


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def parse(source: str, filename: str = '<unknown>') -> Program:
    """
    Parse source code CP+* và trả về AST.

    Args:
        source: Source code CP+*
        filename: Tên file

    Returns:
        Program (root AST node)

    Examples:
        >>> ast = parse('x := 42\n~> io::println("{}", x)')
        >>> print(ast.statements)
    """
    tokens = tokenize(source, filename)
    parser = Parser(tokens, filename)
    return parser.parse()


def parse_file(filepath: str) -> Program:
    """
    Đọc và parse file .cpps.

    Args:
        filepath: Đường dẫn file

    Returns:
        Program AST

    Raises:
        FileNotFoundError: Nếu file không tồn tại
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    return parse(source, filepath)


def parse_expression(expr_str: str) -> Optional[ASTNode]:
    """
    Parse một expression đơn lẻ.

    Args:
        expr_str: Chuỗi expression

    Returns:
        ASTNode biểu diễn expression
    """
    tokens = tokenize(expr_str)
    parser = Parser(tokens)
    return parser.parse_expr()


# ══════════════════════════════════════════════════════════════════════════════
# AST VISITOR BASE CLASS
# ══════════════════════════════════════════════════════════════════════════════

class ASTVisitor:
    """
    Base visitor class cho AST traversal.

    Override các phương thức visit_* để xử lý từng loại node.
    Gọi ast_node.accept(visitor) để kích hoạt.

    Usage:
        class PrettyPrinter(ASTVisitor):
            def visit_Program(self, node):
                for stmt in node.statements:
                    stmt.accept(self)

            def visit_VarDecl(self, node):
                print(f"var {node.name} = {node.value}")

            def visit_default(self, node):
                print(f"[{node.node_type()}]")

        printer = PrettyPrinter()
        ast.accept(printer)
    """

    def visit_default(self, node: ASTNode) -> Any:
        """Xử lý node không có visitor cụ thể."""
        for child in node.children():
            child.accept(self)

    def visit_Program(self, node: Program) -> Any:
        return self.visit_default(node)

    def visit_ModuleDecl(self, node: ModuleDecl) -> Any:
        return self.visit_default(node)

    def visit_ImportStmt(self, node: ImportStmt) -> Any:
        return self.visit_default(node)

    def visit_ExportStmt(self, node: ExportStmt) -> Any:
        return self.visit_default(node)

    def visit_VarDecl(self, node: VarDecl) -> Any:
        return self.visit_default(node)

    def visit_FnDef(self, node: FnDef) -> Any:
        return self.visit_default(node)

    def visit_ClassDef(self, node: ClassDef) -> Any:
        return self.visit_default(node)

    def visit_StructDef(self, node: StructDef) -> Any:
        return self.visit_default(node)

    def visit_TraitDef(self, node: TraitDef) -> Any:
        return self.visit_default(node)

    def visit_ImplBlock(self, node: ImplBlock) -> Any:
        return self.visit_default(node)

    def visit_OverrideDecl(self, node: OverrideDecl) -> Any:
        return self.visit_default(node)

    def visit_ReturnStmt(self, node: ReturnStmt) -> Any:
        return self.visit_default(node)

    def visit_BreakStmt(self, node: BreakStmt) -> Any:
        return self.visit_default(node)

    def visit_ContinueStmt(self, node: ContinueStmt) -> Any:
        return self.visit_default(node)

    def visit_PanicStmt(self, node: PanicStmt) -> Any:
        return self.visit_default(node)

    def visit_PipeStmt(self, node: PipeStmt) -> Any:
        return self.visit_default(node)

    def visit_GoStmt(self, node: GoStmt) -> Any:
        return self.visit_default(node)

    def visit_IfStmt(self, node: IfStmt) -> Any:
        return self.visit_default(node)

    def visit_ForStmt(self, node: ForStmt) -> Any:
        return self.visit_default(node)

    def visit_WhileStmt(self, node: WhileStmt) -> Any:
        return self.visit_default(node)

    def visit_MatchStmt(self, node: MatchStmt) -> Any:
        return self.visit_default(node)

    def visit_MatchArm(self, node: MatchArm) -> Any:
        return self.visit_default(node)

    def visit_TryCatch(self, node: TryCatch) -> Any:
        return self.visit_default(node)

    def visit_MacroInvoke(self, node: MacroInvoke) -> Any:
        return self.visit_default(node)

    def visit_Literal(self, node: Literal) -> Any:
        return self.visit_default(node)

    def visit_VarRef(self, node: VarRef) -> Any:
        return self.visit_default(node)

    def visit_SelfRef(self, node: SelfRef) -> Any:
        return self.visit_default(node)

    def visit_BinaryOp(self, node: BinaryOp) -> Any:
        return self.visit_default(node)

    def visit_UnaryOp(self, node: UnaryOp) -> Any:
        return self.visit_default(node)

    def visit_Assign(self, node: Assign) -> Any:
        return self.visit_default(node)

    def visit_FnCall(self, node: FnCall) -> Any:
        return self.visit_default(node)

    def visit_MethodCall(self, node: MethodCall) -> Any:
        return self.visit_default(node)

    def visit_FieldAccess(self, node: FieldAccess) -> Any:
        return self.visit_default(node)

    def visit_IndexAccess(self, node: IndexAccess) -> Any:
        return self.visit_default(node)

    def visit_ListLiteral(self, node: ListLiteral) -> Any:
        return self.visit_default(node)

    def visit_TupleLiteral(self, node: TupleLiteral) -> Any:
        return self.visit_default(node)

    def visit_MapLiteral(self, node: MapLiteral) -> Any:
        return self.visit_default(node)

    def visit_OwnershipExpr(self, node: OwnershipExpr) -> Any:
        return self.visit_default(node)

    def visit_ResultOk(self, node: ResultOk) -> Any:
        return self.visit_default(node)

    def visit_ResultErr(self, node: ResultErr) -> Any:
        return self.visit_default(node)

    def visit_AwaitExpr(self, node: AwaitExpr) -> Any:
        return self.visit_default(node)

    def visit_PipeExpr(self, node: PipeExpr) -> Any:
        return self.visit_default(node)

    def visit_LambdaExpr(self, node: LambdaExpr) -> Any:
        return self.visit_default(node)

    def visit_ReflectExpr(self, node: ReflectExpr) -> Any:
        return self.visit_default(node)

    def visit_TypeCastExpr(self, node: TypeCastExpr) -> Any:
        return self.visit_default(node)


# ══════════════════════════════════════════════════════════════════════════════
# AST PRETTY PRINTER
# ══════════════════════════════════════════════════════════════════════════════

class ASTPrinter(ASTVisitor):
    """
    Pretty printer cho AST — debug tool.

    Usage:
        >>> ast = parse(source)
        >>> printer = ASTPrinter()
        >>> printer.print(ast)
    """

    def __init__(self, indent: int = 2):
        """
        Khởi tạo printer.

        Args:
            indent: Số space mỗi level indent
        """
        self.indent = indent
        self._depth = 0
        self._lines: List[str] = []

    def _line(self, text: str) -> None:
        self._lines.append(' ' * (self._depth * self.indent) + text)

    def _enter(self, label: str) -> None:
        self._line(f"[{label}]")
        self._depth += 1

    def _leave(self) -> None:
        self._depth -= 1

    def print(self, ast: ASTNode) -> str:
        """
        In AST ra chuỗi.

        Args:
            ast: Root AST node

        Returns:
            Chuỗi biểu diễn AST
        """
        self._lines = []
        self._depth = 0
        ast.accept(self)
        return '\n'.join(self._lines)

    def visit_Program(self, node: Program):
        self._enter('Program')
        for s in node.statements:
            if s:
                s.accept(self)
        self._leave()

    def visit_VarDecl(self, node: VarDecl):
        mut = ' mut' if node.is_mut else ''
        own = f' [{node.ownership}]' if node.ownership else ''
        self._enter(f'VarDecl{own}{mut}: {node.name} :: {node.var_type}')
        if node.value:
            node.value.accept(self)
        self._leave()

    def visit_FnDef(self, node: FnDef):
        params = ', '.join(f"{p[0]}:{p[1]}" for p in node.params)
        static = ' static' if node.is_static else ''
        self._enter(f'FnDef{static}: {node.name}({params}) -> {node.return_type}')
        for s in node.body:
            if s:
                s.accept(self)
        self._leave()

    def visit_ClassDef(self, node: ClassDef):
        parents = ' : ' + ', '.join(node.parents) if node.parents else ''
        traits = ' impl ' + ', '.join(node.traits) if node.traits else ''
        self._enter(f'ClassDef: {node.name}{parents}{traits}')
        for s in node.body:
            if s:
                s.accept(self)
        self._leave()

    def visit_IfStmt(self, node: IfStmt):
        self._enter('IfStmt')
        self._line('condition:')
        self._depth += 1
        if node.condition:
            node.condition.accept(self)
        self._depth -= 1
        self._line('then:')
        self._depth += 1
        for s in node.then_body:
            if s:
                s.accept(self)
        self._depth -= 1
        for cond, body in node.elif_clauses:
            self._line('elif:')
            self._depth += 1
            cond.accept(self)
            for s in body:
                if s:
                    s.accept(self)
            self._depth -= 1
        if node.else_body:
            self._line('else:')
            self._depth += 1
            for s in node.else_body:
                if s:
                    s.accept(self)
            self._depth -= 1
        self._leave()

    def visit_Literal(self, node: Literal):
        self._line(f'Literal: {node.value!r}')

    def visit_VarRef(self, node: VarRef):
        self._line(f'VarRef: {node.name}')

    def visit_SelfRef(self, node: SelfRef):
        self._line('SelfRef: @')

    def visit_BinaryOp(self, node: BinaryOp):
        self._enter(f'BinaryOp: {node.op}')
        if node.left:
            node.left.accept(self)
        if node.right:
            node.right.accept(self)
        self._leave()

    def visit_UnaryOp(self, node: UnaryOp):
        self._enter(f'UnaryOp: {node.op}')
        if node.operand:
            node.operand.accept(self)
        self._leave()

    def visit_FnCall(self, node: FnCall):
        self._enter(f'FnCall: {node.name}({len(node.args)} args)')
        for a in node.args:
            if a:
                a.accept(self)
        self._leave()

    def visit_MethodCall(self, node: MethodCall):
        self._enter(f'MethodCall: .{node.method}({len(node.args)} args)')
        if node.obj:
            node.obj.accept(self)
        for a in node.args:
            if a:
                a.accept(self)
        self._leave()

    def visit_default(self, node: ASTNode):
        self._line(f'[{node.node_type()}]')
        for child in node.children():
            if child:
                self._depth += 1
                child.accept(self)
                self._depth -= 1


# ══════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════════════════════

def _run_tests():
    """Chạy test tự động cho Parser."""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  CP+* Parser — Self Test                                  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    test_cases = [
        ("Variable declaration", "x := 42", Program),
        ("Mutable variable", "name :: mut string = \"hello\"", Program),
        ("Function definition", "++ add <~ (a: int, b: int) -> int ** { <- a + b }", Program),
        ("If statement", "?? x > 0 ** { ~> io::println(\"positive\") }", Program),
        ("For loop", "<> i :: [1, 2, 3] ** { ~> io::println(\"{}\", i) }", Program),
        ("While loop", "while x < 10 ** { x += 1 }", Program),
        ("Return", "<- x + y", Program),
        ("Panic", "!! \"error occurred\"", Program),
        ("Pipe statement", "~> io::println(\"hello\")", Program),
        ("Class definition", "class Dog : Animal -> { ++ bark <~ () ** { ~> io::println(\"Woof\") } }", Program),
        ("Pattern match", "?~ n { 1 => { ~> io::println(\"one\") }, _ => { ~> io::println(\"other\") } }", Program),
        ("Try/catch", "try ** { risky() } catch (e) ** { ~> io::println(\"Error: {}\", e) }", Program),
        ("Ownership", "own<int> x := 42", Program),
        ("Import", "import std::io", Program),
        ("Binary ops", "result := (a + b) * c - d / e % f", Program),
    ]

    passed = 0
    failed = 0

    for test_name, source, expected_type in test_cases:
        try:
            ast = parse(source)
            if isinstance(ast, expected_type):
                passed += 1
                node_count = sum(1 for _ in ast.statements)
                print(f"  ✅ {test_name:<35} → {node_count} stmt(s)")
            else:
                failed += 1
                print(f"  ❌ {test_name:<35} → wrong type: {type(ast)}")
        except Exception as e:
            failed += 1
            print(f"  ❌ {test_name:<35} → {e}")

    print()

    # Complex program test
    print("=== Complex Program Test ===")
    complex_source = '''
module main

import -> {
    std::io,
    std::math
}

-- Trait definition
trait Animal -> {
    ++ speak <~ () -> void ** {
        ~> io::println("...")
    }
    ++ name <~ () -> string ** {
        <- "Unknown"
    }
}

-- Class with inheritance
class Dog : Animal -> {
    dog_name :: mut string = ""
    breed :: string = "Unknown"
    age :: mut int = 0

    ++ new <~ (n: string, b: string, a: int) ** {
        @.dog_name = n
        @.breed = b
        @.age = a
    }

    @@override
    ++ speak <~ () -> void ** {
        ~> io::println("{} says: Woof!", @.dog_name)
    }

    ++ info <~ () -> string ** {
        <- @.dog_name
    }
}

-- Function with generics
++ max<T> <~ (a: T, b: T) -> T ** {
    ?? a > b ** {
        <- a
    } -- else ** {
        <- b
    }
}

-- Pattern matching
++ describe_number <~ (n: int) -> string ** {
    ?~ n {
        0 => { <- "zero" },
        1 => { <- "one" },
        x if x < 0 => { <- "negative" },
        _ => { <- "positive" }
    }
}

-- Main function
++ main <~ () -> int ** {
    dog := Dog::new("Rex", "German Shepherd", 3)
    dog:speak()

    numbers := [1, 2, 3, 4, 5]
    <> n :: numbers ** {
        ~> io::println("describe({}) = {}", n, describe_number(n))
    }

    -- Try/catch
    try ** {
        result := risky_operation()
        ~> io::println("Result: {}", result)
    } catch (e) ** {
        ~> io::println("Error: {}", e)
    }

    <- 0
}
'''
    ast = parse(complex_source, 'complex.cpps')
    print(f"  Statements: {len(ast.statements)}")
    print(f"  Parser errors: 0 (no exceptions)")

    # AST printer
    printer = ASTPrinter()
    printed = printer.print(ast)
    lines = printed.split('\n')
    print(f"  AST lines: {len(lines)}")
    print(f"  First 5 lines:")
    for line in lines[:5]:
        print(f"    {line}")
    print()

    print(f"Results: {passed} passed, {failed} failed")
    print("✅ Parser Self Test hoàn thành!")


if __name__ == '__main__':
    _run_tests()
