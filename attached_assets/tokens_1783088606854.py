"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CP+* (C-Plus-Plus-Star) Language — Token Types & Token System              ║
║  File: src/tokens.py                                                         ║
║  Version: 2.0 — Advanced Edition                                             ║
║                                                                              ║
║  Định nghĩa toàn bộ hệ thống token cho ngôn ngữ CP+*                        ║
║  Bao gồm: TokenType enum, Token class, TokenStream, TokenFactory,           ║
║           operator precedence, keyword tables, error messages, helpers       ║
╚══════════════════════════════════════════════════════════════════════════════╝

CP+* Token System — Architecture Overview
==========================================

Token Types:
  - KEYWORDS:       `:=`, `:: mut`, `++`, `<~`, `->`, `**`, `??`, `<>`, `~>`, `<-`, etc.
  - LITERALS:       NUMBER, STRING, BOOLEAN, NONE, LIFETIME
  - IDENTIFIERS:    Unicode-aware identifier tokens
  - OPERATORS:      Arithmetic, Comparison, Logical, Bitwise, Assignment
  - SYMBOLS:        Brackets, punctuation, separators
  - SPECIAL:        EOF, ERROR, COMMENT, WHITESPACE

Operator Precedence (lowest to highest):
  1. Assignment:     = += -= *= /=
  2. Logical OR:     ||
  3. Logical AND:    &&
  4. Comparison:     == != < > <= >=
  5. Additive:       + -
  6. Multiplicative: * / %
  7. Unary:          - ! not
  8. Postfix:        () [] : .

Special CP+* Syntax Tokens:
  - := (KW_LET)          — immutable binding
  - :: mut (KW_VAR)      — mutable declaration
  - ++ (KW_FN)           — function definition
  - <~ (KW_PARAM_ARROW)  — parameter arrow
  - -> (ARROW)           — return type / map
  - ** (POW)             — body delimiter
  - ?? (KW_IF)           — conditional
  - <> (KW_FOR)          — loop
  - ~> (KW_PIPE)         — pipe / print statement
  - <- (KW_RETURN)       — return
  - !! (KW_PANIC)        — panic
  - !> (KW_BREAK)        — break
  - !>> (KW_CONTINUE)    — continue
  - ?~ (KW_MATCH)        — pattern match
  - @. (self field)      — self-field access
  - :: (DOUBLE_COLON)    — method call / module path
  - @@ (DOUBLE_AT)       — annotation (@@override)
"""

import json
import re
from enum import Enum, auto
from typing import Optional, List, Dict, Any, Tuple


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN TYPE ENUM — 120+ token types
# ══════════════════════════════════════════════════════════════════════════════

class TokenType(Enum):
    """
    Toàn bộ các loại token trong ngôn ngữ CP+*.
    Được phân thành các nhóm:
      - KW_*:   Keywords và special syntax của CP+*
      - LITERAL types: NUMBER, STRING, BOOLEAN, NONE
      - Operators: PLUS, MINUS, STAR, SLASH, etc.
      - Symbols: LBRACE, RBRACE, LPAREN, etc.
      - Special: EOF, ERROR
    """

    # ── Variable declaration keywords ──────────────────────────────────────
    KW_LET          = auto()   # :=   immutable binding
    KW_VAR          = auto()   # :: mut  mutable declaration
    KW_MUT          = auto()   # mut   mutability modifier
    KW_CONST        = auto()   # const  compile-time constant

    # ── Control flow keywords ──────────────────────────────────────────────
    KW_IF           = auto()   # ??   conditional
    KW_ELSE         = auto()   # -- else
    KW_ELIF         = auto()   # -- elif
    KW_FOR          = auto()   # <>   for-each / while loop
    KW_WHILE        = auto()   # while (parsed from identifier)
    KW_BREAK        = auto()   # !>   break
    KW_CONTINUE     = auto()   # !>>  continue
    KW_RETURN       = auto()   # <-   return
    KW_MATCH        = auto()   # ?~   pattern match
    KW_PIPE         = auto()   # ~>   pipe / print statement

    # ── Conditional & matching ─────────────────────────────────────────────
    KW_THEN         = auto()   # then
    KW_IN           = auto()   # in   (for-in loops)
    KW_OF           = auto()   # of   (iteration)
    KW_AS           = auto()   # as   (type cast / alias)

    # ── Function keywords ──────────────────────────────────────────────────
    KW_FN           = auto()   # ++   function definition
    KW_PARAM_ARROW  = auto()   # <~   parameter arrow
    KW_ASYNC        = auto()   # async
    KW_AWAIT        = auto()   # await
    KW_YIELD        = auto()   # yield (generator)
    KW_EXTERN       = auto()   # extern (foreign functions)
    KW_INLINE       = auto()   # inline (hint)
    KW_PURE         = auto()   # pure (no side effects)

    # ── Type system keywords ───────────────────────────────────────────────
    KW_CLASS        = auto()   # class
    KW_STRUCT       = auto()   # struct
    KW_TRAIT        = auto()   # trait
    KW_IMPL         = auto()   # impl
    KW_ENUM         = auto()   # enum
    KW_UNION        = auto()   # union
    KW_TYPE         = auto()   # type (type alias)
    KW_INTERFACE    = auto()   # interface
    KW_ABSTRACT     = auto()   # abstract
    KW_SEALED       = auto()   # sealed (no subclassing)
    KW_FINAL        = auto()   # final (no override)
    KW_VIRTUAL      = auto()   # virtual

    # ── OOP keywords ──────────────────────────────────────────────────────
    KW_SELF         = auto()   # @ (self reference)
    KW_SUPER        = auto()   # super
    KW_NEW          = auto()   # new
    KW_DELETE       = auto()   # delete
    KW_STATIC       = auto()   # static
    KW_OVERRIDE     = auto()   # @@override
    KW_VIRTUAL_FN   = auto()   # virtual function marker

    # ── Ownership & memory keywords ────────────────────────────────────────
    KW_OWN          = auto()   # own<T>   sole owner
    KW_SHARE        = auto()   # share<T> shared reference
    KW_BORROW       = auto()   # borrow<T> temporary borrow
    KW_MOVE         = auto()   # move   transfer ownership
    KW_CLONE        = auto()   # clone  deep copy
    KW_DROP         = auto()   # drop   explicit deallocation
    KW_WEAK         = auto()   # weak   weak reference
    KW_SYSTEM       = auto()   # @system  unsafe raw pointer region
    KW_UNSAFE       = auto()   # unsafe   unsafe block

    # ── Error handling keywords ────────────────────────────────────────────
    KW_PANIC        = auto()   # !!   panic / abort
    KW_TRY          = auto()   # try
    KW_CATCH        = auto()   # catch
    KW_FINALLY      = auto()   # finally
    KW_THROW        = auto()   # throw
    KW_RAISES       = auto()   # raises (error annotation)
    KW_PROPAGATE    = auto()   # ? (error propagation)

    # ── Module system keywords ─────────────────────────────────────────────
    KW_MODULE       = auto()   # module
    KW_IMPORT       = auto()   # import
    KW_EXPORT       = auto()   # export
    KW_FROM         = auto()   # from
    KW_USE          = auto()   # use (bring into scope)
    KW_PUB          = auto()   # pub (public visibility)
    KW_PRIV         = auto()   # priv (private visibility)
    KW_PROT         = auto()   # prot (protected visibility)
    KW_PKG          = auto()   # pkg (package)
    KW_NAMESPACE    = auto()   # namespace

    # ── Concurrency keywords ───────────────────────────────────────────────
    KW_GO           = auto()   # go   spawn goroutine
    KW_CHAN         = auto()   # chan / Channel type
    KW_SELECT       = auto()   # select  channel select
    KW_SEND         = auto()   # send
    KW_RECV         = auto()   # recv
    KW_LOCK         = auto()   # lock   mutex
    KW_UNLOCK       = auto()   # unlock mutex
    KW_SPAWN        = auto()   # spawn thread
    KW_JOIN         = auto()   # join  wait for thread
    KW_ATOMIC       = auto()   # atomic operation

    # ── Generics & templates ───────────────────────────────────────────────
    KW_WHERE        = auto()   # where  generic constraints
    KW_FORALL       = auto()   # forall universal quantifier
    KW_EXIST        = auto()   # exist  existential
    KW_TYPEOF       = auto()   # typeof type introspection
    KW_SIZEOF       = auto()   # sizeof size introspection
    KW_ALIGNOF      = auto()   # alignof alignment
    KW_OFFSETOF     = auto()   # offsetof field offset

    # ── Macros & metaprogramming ───────────────────────────────────────────
    KW_MACRO        = auto()   # @macro_tok / @macro_ast
    KW_REFLECT      = auto()   # @reflect compile-time reflection
    KW_COMPILE      = auto()   # compile-time evaluation
    KW_CONSTEXPR    = auto()   # constexpr
    KW_QUOTE        = auto()   # quote (AST quoting)
    KW_UNQUOTE      = auto()   # unquote (AST splicing)

    # ── Lifetime annotations ───────────────────────────────────────────────
    LIFETIME        = auto()   # 'a  'static  '_  lifetime marker

    # ── Literal types ──────────────────────────────────────────────────────
    IDENTIFIER      = auto()   # user-defined names
    NUMBER          = auto()   # integer or float literal
    STRING          = auto()   # string literal (double-quoted)
    CHAR            = auto()   # char literal (single-quoted)
    BOOLEAN         = auto()   # true / false
    NONE            = auto()   # none / null / nil
    TEMPLATE_STR    = auto()   # template string with interpolation
    RAW_STRING      = auto()   # r"..." raw string
    BYTE_STRING     = auto()   # b"..." byte string
    COMPLEX         = auto()   # 3+4i complex number

    # ── Integer literal suffixes ───────────────────────────────────────────
    INT_I8          = auto()   # 42i8
    INT_I16         = auto()   # 42i16
    INT_I32         = auto()   # 42i32
    INT_I64         = auto()   # 42i64
    INT_I128        = auto()   # 42i128
    INT_U8          = auto()   # 42u8
    INT_U16         = auto()   # 42u16
    INT_U32         = auto()   # 42u32
    INT_U64         = auto()   # 42u64
    INT_U128        = auto()   # 42u128
    INT_USIZE       = auto()   # 42usize
    FLOAT_F32       = auto()   # 3.14f32
    FLOAT_F64       = auto()   # 3.14f64

    # ── Bracket symbols ────────────────────────────────────────────────────
    LBRACE          = auto()   # {
    RBRACE          = auto()   # }
    LPAREN          = auto()   # (
    RPAREN          = auto()   # )
    LBRACKET        = auto()   # [
    RBRACKET        = auto()   # ]
    LANGLE          = auto()   # <  (generic open, also less-than)
    RANGLE          = auto()   # >  (generic close, also greater-than)

    # ── Punctuation & separators ───────────────────────────────────────────
    COLON           = auto()   # :
    DOUBLE_COLON    = auto()   # ::  method call / module path
    COMMA           = auto()   # ,
    DOT             = auto()   # .
    DOTDOT          = auto()   # ..  range
    DOTDOTEQ        = auto()   # ..= inclusive range
    DOTDOTDOT       = auto()   # ... variadic / spread
    AT              = auto()   # @   self reference
    DOUBLE_AT       = auto()   # @@  attribute/annotation
    ARROW           = auto()   # ->  return type / map / lambda
    FAT_ARROW       = auto()   # =>  match arm
    SEMICOLON       = auto()   # ;
    QUESTION        = auto()   # ?   optional / propagate error
    EXCLAMATION     = auto()   # !   negation (single)
    HASH            = auto()   # #   attribute / preprocessor
    BACKTICK        = auto()   # `   raw identifier
    DOLLAR          = auto()   # $   template interpolation
    CARET           = auto()   # ^   bitwise XOR / power
    TILDE           = auto()   # ~   bitwise NOT
    PIPE            = auto()   # |   bitwise OR / type union
    AMP             = auto()   # &   bitwise AND / reference
    BACKSLASH       = auto()   # \   escape / continuation

    # ── Arithmetic operators ───────────────────────────────────────────────
    PLUS            = auto()   # +
    MINUS           = auto()   # -
    STAR            = auto()   # *
    SLASH           = auto()   # /
    MOD             = auto()   # %   modulo
    POW             = auto()   # **  power / body delimiter
    FLOOR_DIV       = auto()   # //  floor division

    # ── Assignment operators ───────────────────────────────────────────────
    ASSIGN          = auto()   # =
    PLUS_EQ         = auto()   # +=
    MINUS_EQ        = auto()   # -=
    STAR_EQ         = auto()   # *=
    SLASH_EQ        = auto()   # /=
    MOD_EQ          = auto()   # %=
    POW_EQ          = auto()   # **=
    AMP_EQ          = auto()   # &=
    PIPE_EQ         = auto()   # |=
    CARET_EQ        = auto()   # ^=
    LSHIFT_EQ       = auto()   # <<=
    RSHIFT_EQ       = auto()   # >>=
    FLOOR_DIV_EQ    = auto()   # //=
    COALESCE_EQ     = auto()   # ??= null coalescing assign

    # ── Comparison operators ───────────────────────────────────────────────
    EQ              = auto()   # ==  equals
    NEQ             = auto()   # !=  not equals
    LT              = auto()   # <   less than
    GT              = auto()   # >   greater than
    LTE             = auto()   # <=  less than or equal
    GTE             = auto()   # >=  greater than or equal
    SPACESHIP       = auto()   # <=> three-way comparison

    # ── Logical operators ──────────────────────────────────────────────────
    AND             = auto()   # &&  logical and
    OR              = auto()   # ||  logical or
    NOT             = auto()   # !   logical not (unary)
    XOR             = auto()   # ^^  logical xor

    # ── Bitwise operators ──────────────────────────────────────────────────
    BIT_AND         = auto()   # &   bitwise and
    BIT_OR          = auto()   # |   bitwise or
    BIT_XOR         = auto()   # ^   bitwise xor
    BIT_NOT         = auto()   # ~   bitwise not
    LSHIFT          = auto()   # <<  left shift
    RSHIFT          = auto()   # >>  right shift

    # ── Special operators ──────────────────────────────────────────────────
    WALRUS          = auto()   # :=  (also used for let binding)
    COALESCE        = auto()   # ??  null coalescing (also KW_IF context)
    SAFE_NAV        = auto()   # ?.  safe navigation
    SPREAD          = auto()   # ... spread operator
    PIPE_OP         = auto()   # |>  pipeline operator (alternative)
    COMPOSE         = auto()   # >>  function composition
    PARTIAL         = auto()   # _   partial application placeholder

    # ── Comment tokens (normally skipped) ─────────────────────────────────
    LINE_COMMENT    = auto()   # --  single line comment
    BLOCK_COMMENT   = auto()   # --[[ ... --]]  multi-line comment
    DOC_COMMENT     = auto()   # --|| ... --||  documentation comment
    SHEBANG         = auto()   # #!  shebang line

    # ── Directive tokens ───────────────────────────────────────────────────
    DIRECTIVE_OPEN  = auto()   # +*  directive / header open
    DIRECTIVE_CLOSE = auto()   # *+  directive / header close

    # ── Error & special ────────────────────────────────────────────────────
    ERROR           = auto()   # Invalid/unknown token
    WHITESPACE      = auto()   # Whitespace (normally skipped)
    NEWLINE         = auto()   # Newline (significant in some modes)
    EOF             = auto()   # End of file


# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD MAPPING TABLE
# Maps keyword strings → TokenType
# ══════════════════════════════════════════════════════════════════════════════

KEYWORDS: Dict[str, TokenType] = {
    # Literals
    "true":      TokenType.BOOLEAN,
    "false":     TokenType.BOOLEAN,
    "none":      TokenType.NONE,
    "null":      TokenType.NONE,
    "nil":       TokenType.NONE,

    # Mutability
    "mut":       TokenType.KW_MUT,
    "const":     TokenType.KW_CONST,

    # OOP
    "new":       TokenType.KW_NEW,
    "delete":    TokenType.KW_DELETE,
    "static":    TokenType.KW_STATIC,
    "super":     TokenType.KW_SUPER,
    "self":      TokenType.KW_SELF,
    "abstract":  TokenType.KW_ABSTRACT,
    "sealed":    TokenType.KW_SEALED,
    "final":     TokenType.KW_FINAL,
    "virtual":   TokenType.KW_VIRTUAL,

    # Types
    "class":     TokenType.KW_CLASS,
    "struct":    TokenType.KW_STRUCT,
    "trait":     TokenType.KW_TRAIT,
    "impl":      TokenType.KW_IMPL,
    "enum":      TokenType.KW_ENUM,
    "union":     TokenType.KW_UNION,
    "type":      TokenType.KW_TYPE,
    "interface": TokenType.KW_INTERFACE,

    # Ownership
    "own":       TokenType.KW_OWN,
    "share":     TokenType.KW_SHARE,
    "borrow":    TokenType.KW_BORROW,
    "move":      TokenType.KW_MOVE,
    "clone":     TokenType.KW_CLONE,
    "drop":      TokenType.KW_DROP,
    "weak":      TokenType.KW_WEAK,
    "unsafe":    TokenType.KW_UNSAFE,

    # Error handling
    "try":       TokenType.KW_TRY,
    "catch":     TokenType.KW_CATCH,
    "finally":   TokenType.KW_FINALLY,
    "throw":     TokenType.KW_THROW,
    "raises":    TokenType.KW_RAISES,

    # Modules
    "module":    TokenType.KW_MODULE,
    "import":    TokenType.KW_IMPORT,
    "export":    TokenType.KW_EXPORT,
    "from":      TokenType.KW_FROM,
    "use":       TokenType.KW_USE,
    "pub":       TokenType.KW_PUB,
    "priv":      TokenType.KW_PRIV,

    # Concurrency
    "go":        TokenType.KW_GO,
    "chan":      TokenType.KW_CHAN,
    "select":    TokenType.KW_SELECT,
    "spawn":     TokenType.KW_SPAWN,
    "join":      TokenType.KW_JOIN,
    "atomic":    TokenType.KW_ATOMIC,
    "lock":      TokenType.KW_LOCK,
    "unlock":    TokenType.KW_UNLOCK,

    # Generics
    "where":     TokenType.KW_WHERE,
    "typeof":    TokenType.KW_TYPEOF,
    "sizeof":    TokenType.KW_SIZEOF,

    # Async
    "async":     TokenType.KW_ASYNC,
    "await":     TokenType.KW_AWAIT,
    "yield":     TokenType.KW_YIELD,

    # Control
    "while":     TokenType.KW_WHILE,
    "else":      TokenType.KW_ELSE,
    "elif":      TokenType.KW_ELIF,
    "then":      TokenType.KW_THEN,
    "in":        TokenType.KW_IN,
    "of":        TokenType.KW_OF,
    "as":        TokenType.KW_AS,
    "extern":    TokenType.KW_EXTERN,
    "inline":    TokenType.KW_INLINE,
    "pure":      TokenType.KW_PURE,
}


# ══════════════════════════════════════════════════════════════════════════════
# OPERATOR PRECEDENCE TABLE
# Each entry: (precedence_level, associativity, arity)
#   precedence: higher = binds tighter
#   associativity: 'L' = left, 'R' = right, 'N' = none
#   arity: 'binary' | 'unary_prefix' | 'unary_postfix' | 'ternary'
# ══════════════════════════════════════════════════════════════════════════════

OPERATOR_PRECEDENCE: Dict[str, Tuple[int, str, str]] = {
    # Assignment (lowest precedence, right-associative)
    '=':    (1,  'R', 'binary'),
    '+=':   (1,  'R', 'binary'),
    '-=':   (1,  'R', 'binary'),
    '*=':   (1,  'R', 'binary'),
    '/=':   (1,  'R', 'binary'),
    '%=':   (1,  'R', 'binary'),
    '**=':  (1,  'R', 'binary'),
    '&=':   (1,  'R', 'binary'),
    '|=':   (1,  'R', 'binary'),
    '^=':   (1,  'R', 'binary'),
    '<<=':  (1,  'R', 'binary'),
    '>>=':  (1,  'R', 'binary'),
    '//=':  (1,  'R', 'binary'),
    '??=':  (1,  'R', 'binary'),

    # Ternary (conditional expression)
    '?:':   (2,  'R', 'ternary'),

    # Null coalescing
    '??':   (3,  'L', 'binary'),

    # Logical OR
    '||':   (4,  'L', 'binary'),

    # Logical XOR
    '^^':   (5,  'L', 'binary'),

    # Logical AND
    '&&':   (6,  'L', 'binary'),

    # Bitwise OR
    '|':    (7,  'L', 'binary'),

    # Bitwise XOR
    '^':    (8,  'L', 'binary'),

    # Bitwise AND
    '&':    (9,  'L', 'binary'),

    # Equality / inequality
    '==':   (10, 'L', 'binary'),
    '!=':   (10, 'L', 'binary'),

    # Three-way comparison
    '<=>':  (11, 'L', 'binary'),

    # Relational
    '<':    (12, 'L', 'binary'),
    '>':    (12, 'L', 'binary'),
    '<=':   (12, 'L', 'binary'),
    '>=':   (12, 'L', 'binary'),

    # Shifts
    '<<':   (13, 'L', 'binary'),
    '>>':   (13, 'L', 'binary'),

    # Additive
    '+':    (14, 'L', 'binary'),
    '-':    (14, 'L', 'binary'),

    # Multiplicative
    '*':    (15, 'L', 'binary'),
    '/':    (15, 'L', 'binary'),
    '%':    (15, 'L', 'binary'),
    '//':   (15, 'L', 'binary'),

    # Unary prefix (right-associative by convention)
    'u-':   (16, 'R', 'unary_prefix'),
    'u!':   (16, 'R', 'unary_prefix'),
    'u~':   (16, 'R', 'unary_prefix'),
    'u&':   (16, 'R', 'unary_prefix'),
    'u*':   (16, 'R', 'unary_prefix'),

    # Power (right-associative)
    '**':   (17, 'R', 'binary'),

    # Postfix / call / index / field
    '()':   (18, 'L', 'unary_postfix'),
    '[]':   (18, 'L', 'unary_postfix'),
    '.':    (18, 'L', 'unary_postfix'),
    ':':    (18, 'L', 'unary_postfix'),
    '::':   (18, 'L', 'unary_postfix'),

    # Pipe operator (function chaining)
    '|>':   (0,  'L', 'binary'),
    '~>':   (0,  'L', 'binary'),
}


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN CATEGORIES — for batch testing
# ══════════════════════════════════════════════════════════════════════════════

KEYWORDS_SET = frozenset(KEYWORDS.keys())

ASSIGNMENT_OPS = frozenset({
    '=', '+=', '-=', '*=', '/=', '%=', '**=',
    '&=', '|=', '^=', '<<=', '>>=', '//=', '??='
})

COMPARISON_OPS = frozenset({'==', '!=', '<', '>', '<=', '>=', '<=>'})

ARITHMETIC_OPS = frozenset({'+', '-', '*', '/', '%', '//', '**'})

LOGICAL_OPS = frozenset({'&&', '||', '!', '^^'})

BITWISE_OPS = frozenset({'&', '|', '^', '~', '<<', '>>'})

UNARY_OPS = frozenset({'-', '!', '~', '&', '*', 'not', '+'})

OVERLOADABLE_OPS = frozenset({
    '+', '-', '*', '/', '%', '**',
    '==', '!=', '<', '>', '<=', '>=',
    '<<', '>>', '&', '|', '^', '~',
    '[]', '()', '++', '--'
})

RIGHT_ASSOCIATIVE_OPS = frozenset({'=', '+=', '-=', '*=', '/=', '%=',
                                    '**=', '&=', '|=', '^=', '?:', '**'})

BRACKET_PAIRS = {
    TokenType.LBRACE:   TokenType.RBRACE,
    TokenType.LPAREN:   TokenType.RPAREN,
    TokenType.LBRACKET: TokenType.RBRACKET,
    TokenType.LANGLE:   TokenType.RANGLE,
}

OPENING_BRACKETS = frozenset({
    TokenType.LBRACE, TokenType.LPAREN, TokenType.LBRACKET, TokenType.LANGLE
})

CLOSING_BRACKETS = frozenset({
    TokenType.RBRACE, TokenType.RPAREN, TokenType.RBRACKET, TokenType.RANGLE
})

LITERAL_TYPES = frozenset({
    TokenType.NUMBER, TokenType.STRING, TokenType.CHAR,
    TokenType.BOOLEAN, TokenType.NONE, TokenType.TEMPLATE_STR,
    TokenType.RAW_STRING, TokenType.BYTE_STRING, TokenType.COMPLEX,
    TokenType.FLOAT_F32, TokenType.FLOAT_F64,
    TokenType.INT_I8, TokenType.INT_I16, TokenType.INT_I32, TokenType.INT_I64,
    TokenType.INT_U8, TokenType.INT_U16, TokenType.INT_U32, TokenType.INT_U64,
})


# ══════════════════════════════════════════════════════════════════════════════
# ERROR MESSAGES (Tiếng Việt)
# ══════════════════════════════════════════════════════════════════════════════

TOKEN_DESCRIPTIONS: Dict[TokenType, str] = {
    TokenType.KW_LET:         "khai báo biến bất biến ':='",
    TokenType.KW_MUT:         "từ khóa 'mut' (biến đổi được)",
    TokenType.KW_CONST:       "từ khóa 'const' (hằng số)",
    TokenType.KW_IF:          "điều kiện '??'",
    TokenType.KW_ELSE:        "nhánh 'else'",
    TokenType.KW_ELIF:        "nhánh 'elif'",
    TokenType.KW_FOR:         "vòng lặp '<>'",
    TokenType.KW_WHILE:       "vòng lặp 'while'",
    TokenType.KW_BREAK:       "lệnh thoát vòng lặp '!>'",
    TokenType.KW_CONTINUE:    "lệnh tiếp tục vòng lặp '!>>'",
    TokenType.KW_RETURN:      "lệnh trả về '<-'",
    TokenType.KW_MATCH:       "pattern matching '?~'",
    TokenType.KW_PIPE:        "lệnh pipe/in ra '~>'",
    TokenType.KW_FN:          "định nghĩa hàm '++'",
    TokenType.KW_PARAM_ARROW: "mũi tên tham số '<~'",
    TokenType.KW_CLASS:       "từ khóa 'class'",
    TokenType.KW_STRUCT:      "từ khóa 'struct'",
    TokenType.KW_TRAIT:       "từ khóa 'trait'",
    TokenType.KW_IMPL:        "từ khóa 'impl'",
    TokenType.KW_OWN:         "sở hữu 'own<T>'",
    TokenType.KW_SHARE:       "tham chiếu chia sẻ 'share<T>'",
    TokenType.KW_BORROW:      "mượn tạm 'borrow<T>'",
    TokenType.KW_PANIC:       "lệnh panic '!!'",
    TokenType.KW_TRY:         "khối try",
    TokenType.KW_CATCH:       "khối catch",
    TokenType.KW_MODULE:      "khai báo module",
    TokenType.KW_IMPORT:      "khai báo import",
    TokenType.KW_EXPORT:      "khai báo export",
    TokenType.KW_GO:          "goroutine 'go'",
    TokenType.KW_STATIC:      "phương thức static",
    TokenType.KW_ASYNC:       "hàm bất đồng bộ 'async'",
    TokenType.KW_AWAIT:       "chờ đợi 'await'",
    TokenType.IDENTIFIER:     "tên định danh",
    TokenType.NUMBER:         "số",
    TokenType.STRING:         "chuỗi ký tự",
    TokenType.BOOLEAN:        "boolean (true/false)",
    TokenType.NONE:           "giá trị none",
    TokenType.LIFETIME:       "lifetime annotation ('a)",
    TokenType.LBRACE:         "dấu mở ngoặc nhọn '{'",
    TokenType.RBRACE:         "dấu đóng ngoặc nhọn '}'",
    TokenType.LPAREN:         "dấu mở ngoặc tròn '('",
    TokenType.RPAREN:         "dấu đóng ngoặc tròn ')'",
    TokenType.LBRACKET:       "dấu mở ngoặc vuông '['",
    TokenType.RBRACKET:       "dấu đóng ngoặc vuông ']'",
    TokenType.COLON:          "dấu hai chấm ':'",
    TokenType.DOUBLE_COLON:   "dấu hai chấm đôi '::'",
    TokenType.COMMA:          "dấu phẩy ','",
    TokenType.DOT:            "dấu chấm '.'",
    TokenType.DOTDOT:         "phạm vi '..'",
    TokenType.DOTDOTEQ:       "phạm vi bao gồm '..='",
    TokenType.ARROW:          "mũi tên '->'",
    TokenType.FAT_ARROW:      "mũi tên dày '=>'",
    TokenType.AT:             "ký hiệu self '@'",
    TokenType.DOUBLE_AT:      "annotation '@@'",
    TokenType.PLUS:           "phép cộng '+'",
    TokenType.MINUS:          "phép trừ '-'",
    TokenType.STAR:           "phép nhân '*'",
    TokenType.SLASH:          "phép chia '/'",
    TokenType.MOD:            "phép chia lấy dư '%'",
    TokenType.POW:            "dấu thân hàm '**'",
    TokenType.ASSIGN:         "phép gán '='",
    TokenType.PLUS_EQ:        "cộng và gán '+='",
    TokenType.MINUS_EQ:       "trừ và gán '-='",
    TokenType.STAR_EQ:        "nhân và gán '*='",
    TokenType.SLASH_EQ:       "chia và gán '/='",
    TokenType.EQ:             "so sánh bằng '=='",
    TokenType.NEQ:            "so sánh khác '!='",
    TokenType.LT:             "nhỏ hơn '<'",
    TokenType.GT:             "lớn hơn '>'",
    TokenType.LTE:            "nhỏ hơn hoặc bằng '<='",
    TokenType.GTE:            "lớn hơn hoặc bằng '>='",
    TokenType.AND:            "logic và '&&'",
    TokenType.OR:             "logic hoặc '||'",
    TokenType.NOT:            "logic phủ định '!'",
    TokenType.SEMICOLON:      "dấu chấm phẩy ';'",
    TokenType.QUESTION:       "dấu hỏi '?'",
    TokenType.HASH:           "dấu thăng '#'",
    TokenType.PIPE:           "dấu sổ dọc '|'",
    TokenType.AMP:            "dấu và '&'",
    TokenType.TILDE:          "dấu ngã '~'",
    TokenType.EOF:            "kết thúc file",
    TokenType.ERROR:          "token không hợp lệ",
}

# Error messages in Vietnamese
ERROR_MESSAGES = {
    'unexpected_token':     "Token không mong đợi: {}. Mong đợi: {}",
    'unclosed_string':      "Chuỗi chưa đóng tại dòng {}",
    'unclosed_comment':     "Comment nhiều dòng chưa đóng tại dòng {}",
    'unknown_escape':       "Ký tự escape không hợp lệ: \\{}",
    'invalid_number':       "Số không hợp lệ: '{}'",
    'invalid_identifier':   "Tên định danh không hợp lệ: '{}'",
    'unexpected_eof':       "Kết thúc file không mong đợi",
    'invalid_char':         "Ký tự không hợp lệ: '{}'",
    'overflow':             "Số quá lớn: '{}'",
    'unclosed_bracket':     "Dấu ngoặc chưa đóng: '{}'",
    'mismatched_bracket':   "Dấu ngoặc không khớp: mở '{}', đóng '{}'",
    'duplicate_param':      "Tham số bị trùng lặp: '{}'",
    'invalid_type':         "Kiểu dữ liệu không hợp lệ: '{}'",
    'undefined_var':        "Biến chưa được khai báo: '{}'",
    'undefined_fn':         "Hàm chưa được định nghĩa: '{}'",
    'undefined_class':      "Lớp chưa được định nghĩa: '{}'",
    'type_mismatch':        "Kiểu không phù hợp: mong đợi '{}', nhận '{}'",
    'division_by_zero':     "Lỗi chia cho 0",
    'index_out_of_bounds':  "Chỉ số ngoài phạm vi: {} (độ dài: {})",
    'stack_overflow':       "Stack overflow: đệ quy quá sâu",
    'infinite_loop':        "Phát hiện vòng lặp vô hạn",
    'null_pointer':         "Truy cập giá trị null/none",
    'immutable_assign':     "Không thể gán lại biến bất biến: '{}'",
    'use_after_move':       "Sử dụng giá trị sau khi đã move: '{}'",
    'lifetime_error':       "Lỗi lifetime: borrow '{}' vượt quá lifetime của owner",
    'borrow_conflict':      "Xung đột borrow: không thể mượn '{}' cả mutable và immutable",
}

# Warning messages
WARNING_MESSAGES = {
    'unused_var':        "Biến '{}' khai báo nhưng không sử dụng",
    'unused_fn':         "Hàm '{}' khai báo nhưng không sử dụng",
    'shadow_var':        "Biến '{}' che khuất biến cùng tên bên ngoài scope",
    'unreachable_code':  "Code không thể đến được sau dòng {}",
    'implicit_return':   "Hàm '{}' có thể không trả về giá trị",
    'narrowing_conv':    "Chuyển đổi thu hẹp: {} → {}",
    'float_compare':     "So sánh số float không ổn định tại dòng {}",
    'deprecated':        "Tính năng '{}' đã cũ, dùng '{}' thay thế",
    'missing_override':  "Phương thức '{}' ghi đè nhưng thiếu @@override",
}


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Token:
    """
    Biểu diễn một token trong luồng token của CP+*.

    Attributes:
        type (TokenType): Loại token
        value: Giá trị của token (string, int, float, bool, None)
        line (int): Dòng trong source code (1-indexed)
        column (int): Cột trong source code (1-indexed)
        filename (str): Tên file source
        lexeme (str): Chuỗi gốc trong source (trước khi xử lý)
        length (int): Độ dài của lexeme

    Examples:
        >>> t = Token(TokenType.NUMBER, 42, line=1, column=5)
        >>> print(t)
        Token(NUMBER, 42 L1:5)

        >>> t2 = Token(TokenType.IDENTIFIER, 'myVar', line=3, column=10, lexeme='myVar')
        >>> print(t2.to_dict())
        {'type': 'IDENTIFIER', 'value': 'myVar', 'line': 3, 'column': 10}
    """

    __slots__ = ('type', 'value', 'line', 'column', 'filename', 'lexeme', 'length')

    def __init__(
        self,
        type: TokenType,
        value,
        line: int = 0,
        column: int = 0,
        filename: str = '<unknown>',
        lexeme: str = '',
        length: int = 0
    ):
        """
        Khởi tạo Token.

        Args:
            type: Loại token (TokenType enum)
            value: Giá trị đã xử lý (e.g. Python int/float/str/bool)
            line: Dòng trong source (1-indexed)
            column: Cột trong source (1-indexed)
            filename: Tên file nguồn
            lexeme: Chuỗi gốc từ source
            length: Độ dài của lexeme
        """
        self.type = type
        self.value = value
        self.line = line
        self.column = column
        self.filename = filename
        self.lexeme = lexeme if lexeme else (str(value) if value is not None else '')
        self.length = length if length > 0 else len(self.lexeme)

    def __repr__(self) -> str:
        """Biểu diễn debug của token."""
        return f"Token({self.type.name}, {self.value!r} L{self.line}:{self.column})"

    def __str__(self) -> str:
        """Biểu diễn chuỗi ngắn gọn của token."""
        if self.value is not None and self.value != self.type.name:
            return f"{self.type.name}({self.value!r})"
        return self.type.name

    def __eq__(self, other) -> bool:
        """So sánh bằng: chỉ so sánh type và value."""
        if isinstance(other, Token):
            return self.type == other.type and self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        """Hash của token."""
        return hash((self.type, str(self.value)))

    def is_keyword(self) -> bool:
        """Kiểm tra xem token có phải là keyword không."""
        return self.type.name.startswith('KW_')

    def is_literal(self) -> bool:
        """Kiểm tra xem token có phải là literal không."""
        return self.type in LITERAL_TYPES

    def is_operator(self) -> bool:
        """Kiểm tra xem token có phải là operator không."""
        return self.type in (
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR,
            TokenType.SLASH, TokenType.MOD, TokenType.POW,
            TokenType.EQ, TokenType.NEQ, TokenType.LT, TokenType.GT,
            TokenType.LTE, TokenType.GTE, TokenType.AND, TokenType.OR,
            TokenType.NOT, TokenType.ASSIGN, TokenType.PLUS_EQ,
            TokenType.MINUS_EQ, TokenType.STAR_EQ, TokenType.SLASH_EQ,
            TokenType.AMP, TokenType.PIPE, TokenType.CARET, TokenType.TILDE,
        )

    def is_delimiter(self) -> bool:
        """Kiểm tra xem token có phải là dấu phân cách không."""
        return self.type in (
            TokenType.LBRACE, TokenType.RBRACE,
            TokenType.LPAREN, TokenType.RPAREN,
            TokenType.LBRACKET, TokenType.RBRACKET,
            TokenType.SEMICOLON, TokenType.COMMA,
        )

    def is_eof(self) -> bool:
        """Kiểm tra xem token có phải EOF không."""
        return self.type == TokenType.EOF

    def is_error(self) -> bool:
        """Kiểm tra xem token có phải lỗi không."""
        return self.type == TokenType.ERROR

    def get_description(self) -> str:
        """Lấy mô tả tiếng Việt của token."""
        return TOKEN_DESCRIPTIONS.get(self.type, self.type.name)

    def position_str(self) -> str:
        """Chuỗi vị trí dạng 'file.cpps:3:10'."""
        return f"{self.filename}:{self.line}:{self.column}"

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển token thành dict (để serialization)."""
        return {
            'type': self.type.name,
            'value': self.value,
            'line': self.line,
            'column': self.column,
            'filename': self.filename,
            'lexeme': self.lexeme,
        }

    def to_json(self) -> str:
        """Chuyển token thành JSON string."""
        d = self.to_dict()
        # Handle non-serializable values
        if isinstance(d['value'], bool):
            d['value'] = d['value']
        elif d['value'] is None:
            d['value'] = None
        else:
            try:
                json.dumps(d['value'])
            except (TypeError, ValueError):
                d['value'] = str(d['value'])
        return json.dumps(d, ensure_ascii=False)

    def clone(self) -> 'Token':
        """Tạo bản sao của token."""
        return Token(
            self.type, self.value,
            self.line, self.column,
            self.filename, self.lexeme, self.length
        )

    @classmethod
    def eof(cls, line: int = 0, column: int = 0, filename: str = '<unknown>') -> 'Token':
        """Tạo token EOF."""
        return cls(TokenType.EOF, None, line, column, filename, '', 0)

    @classmethod
    def error(cls, message: str, line: int = 0, column: int = 0,
              filename: str = '<unknown>') -> 'Token':
        """Tạo token lỗi."""
        return cls(TokenType.ERROR, message, line, column, filename, message, len(message))


# ══════════════════════════════════════════════════════════════════════════════
# ERROR TOKEN — kế thừa từ Token
# ══════════════════════════════════════════════════════════════════════════════

class ErrorToken(Token):
    """
    Token đặc biệt biểu diễn lỗi lexer.

    Attributes:
        message (str): Mô tả lỗi
        severity (str): Mức độ nghiêm trọng ('error' | 'warning' | 'hint')
        suggestion (str): Gợi ý sửa lỗi
    """

    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int = 0,
        filename: str = '<unknown>',
        severity: str = 'error',
        suggestion: str = ''
    ):
        super().__init__(TokenType.ERROR, message, line, column, filename)
        self.message = message
        self.severity = severity
        self.suggestion = suggestion

    def __repr__(self) -> str:
        return (f"ErrorToken({self.severity.upper()}: {self.message!r} "
                f"at {self.filename}:{self.line}:{self.column})")

    def format_error(self) -> str:
        """Định dạng thông báo lỗi đầy đủ."""
        lines = [
            f"{'❌' if self.severity == 'error' else '⚠️'} {self.severity.upper()} "
            f"[{self.position_str()}]: {self.message}"
        ]
        if self.suggestion:
            lines.append(f"   💡 Gợi ý: {self.suggestion}")
        return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN FACTORY — tạo token theo loại
# ══════════════════════════════════════════════════════════════════════════════

class TokenFactory:
    """
    Factory class để tạo các token phổ biến.

    Usage:
        >>> factory = TokenFactory('hello.cpps')
        >>> tok = factory.make_number(42, line=1, col=5)
        >>> tok2 = factory.make_ident('myVar', line=2, col=1)
    """

    def __init__(self, filename: str = '<unknown>'):
        """Khởi tạo factory với tên file."""
        self.filename = filename

    def make(self, tok_type: TokenType, value, line: int, col: int,
             lexeme: str = '') -> Token:
        """Tạo token cơ bản."""
        return Token(tok_type, value, line, col, self.filename, lexeme)

    def make_number(self, value, line: int, col: int, lexeme: str = '') -> Token:
        """Tạo token số (int hoặc float)."""
        return Token(TokenType.NUMBER, value, line, col, self.filename,
                     lexeme or str(value))

    def make_string(self, value: str, line: int, col: int, lexeme: str = '') -> Token:
        """Tạo token chuỗi."""
        return Token(TokenType.STRING, value, line, col, self.filename,
                     lexeme or f'"{value}"')

    def make_ident(self, name: str, line: int, col: int) -> Token:
        """Tạo token định danh (kiểm tra keyword trước)."""
        tok_type = KEYWORDS.get(name, TokenType.IDENTIFIER)
        if tok_type == TokenType.BOOLEAN:
            value = name == 'true'
        elif tok_type == TokenType.NONE:
            value = None
        else:
            value = name
        return Token(tok_type, value, line, col, self.filename, name)

    def make_bool(self, value: bool, line: int, col: int) -> Token:
        """Tạo token boolean."""
        return Token(TokenType.BOOLEAN, value, line, col, self.filename,
                     'true' if value else 'false')

    def make_none(self, line: int, col: int) -> Token:
        """Tạo token none."""
        return Token(TokenType.NONE, None, line, col, self.filename, 'none')

    def make_eof(self, line: int, col: int) -> Token:
        """Tạo token EOF."""
        return Token.eof(line, col, self.filename)

    def make_error(self, message: str, line: int, col: int,
                   severity: str = 'error', suggestion: str = '') -> ErrorToken:
        """Tạo token lỗi."""
        return ErrorToken(message, line, col, self.filename, severity, suggestion)

    def make_symbol(self, sym: str, line: int, col: int) -> Token:
        """Tạo token ký hiệu từ chuỗi (tra bảng two_map / single_map)."""
        type_map = {
            ':=': TokenType.KW_LET,
            '::': TokenType.DOUBLE_COLON,
            '->': TokenType.ARROW,
            '=>': TokenType.FAT_ARROW,
            '<-': TokenType.KW_RETURN,
            '<~': TokenType.KW_PARAM_ARROW,
            '??': TokenType.KW_IF,
            '?~': TokenType.KW_MATCH,
            '~>': TokenType.KW_PIPE,
            '<>': TokenType.KW_FOR,
            '!>': TokenType.KW_BREAK,
            '!!': TokenType.KW_PANIC,
            '++': TokenType.KW_FN,
            '==': TokenType.EQ,
            '!=': TokenType.NEQ,
            '<=': TokenType.LTE,
            '>=': TokenType.GTE,
            '&&': TokenType.AND,
            '||': TokenType.OR,
            '+=': TokenType.PLUS_EQ,
            '-=': TokenType.MINUS_EQ,
            '*=': TokenType.STAR_EQ,
            '/=': TokenType.SLASH_EQ,
            '**': TokenType.POW,
            '..': TokenType.DOTDOT,
            '..=': TokenType.DOTDOTEQ,
            '!>>': TokenType.KW_CONTINUE,
            '{': TokenType.LBRACE,
            '}': TokenType.RBRACE,
            '(': TokenType.LPAREN,
            ')': TokenType.RPAREN,
            '[': TokenType.LBRACKET,
            ']': TokenType.RBRACKET,
            ':': TokenType.COLON,
            ',': TokenType.COMMA,
            '.': TokenType.DOT,
            ';': TokenType.SEMICOLON,
            '?': TokenType.QUESTION,
            '|': TokenType.PIPE,
            '&': TokenType.AMP,
            '~': TokenType.TILDE,
            '#': TokenType.HASH,
            '+': TokenType.PLUS,
            '-': TokenType.MINUS,
            '*': TokenType.STAR,
            '/': TokenType.SLASH,
            '%': TokenType.MOD,
            '=': TokenType.ASSIGN,
            '<': TokenType.LT,
            '>': TokenType.GT,
            '!': TokenType.NOT,
            '@': TokenType.AT,
        }
        tok_type = type_map.get(sym, TokenType.ERROR)
        return Token(tok_type, sym, line, col, self.filename, sym)


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN STREAM — luồng token với peek/advance/expect
# ══════════════════════════════════════════════════════════════════════════════

class TokenStream:
    """
    Wrapper xung quanh danh sách token cung cấp interface phong phú
    để parser tiêu thụ token.

    Cung cấp:
        - peek(offset): nhìn trước không tiêu thụ
        - advance(): tiêu thụ và trả về token hiện tại
        - expect(type): tiêu thụ token nếu khớp, raise ParseError nếu không
        - match(*types): tiêu thụ nếu khớp bất kỳ type nào
        - check(*types): kiểm tra không tiêu thụ
        - consume(*types): như match nhưng trả về bool
        - is_at_end(): kiểm tra hết token
        - remaining(): số token còn lại
        - get_slice(start, end): lấy slice token
        - seek(pos): nhảy đến vị trí
        - save() / restore(mark): bookmark vị trí
        - context_window(n): lấy n token xung quanh vị trí hiện tại

    Usage:
        >>> tokens = Lexer(source).tokenize()
        >>> stream = TokenStream(tokens)
        >>> while not stream.is_at_end():
        ...     tok = stream.advance()
        ...     print(tok)
    """

    def __init__(self, tokens: List[Token]):
        """
        Khởi tạo TokenStream.

        Args:
            tokens: Danh sách token từ Lexer
        """
        self._tokens = [t for t in tokens if t is not None]
        self._pos = 0
        self._marks = []  # Stack of saved positions

    def __len__(self) -> int:
        """Tổng số token."""
        return len(self._tokens)

    def __getitem__(self, idx: int) -> Optional[Token]:
        """Truy cập token theo index."""
        if 0 <= idx < len(self._tokens):
            return self._tokens[idx]
        return None

    def __iter__(self):
        """Duyệt qua tất cả token."""
        return iter(self._tokens)

    @property
    def pos(self) -> int:
        """Vị trí hiện tại."""
        return self._pos

    @pos.setter
    def pos(self, value: int):
        """Đặt vị trí."""
        self._pos = max(0, min(value, len(self._tokens)))

    def peek(self, offset: int = 0) -> Optional[Token]:
        """
        Nhìn trước token mà không tiêu thụ.

        Args:
            offset: Số token cần nhìn trước (0 = hiện tại, 1 = tiếp theo, ...)

        Returns:
            Token tại vị trí pos+offset, hoặc None nếu hết
        """
        idx = self._pos + offset
        if 0 <= idx < len(self._tokens):
            return self._tokens[idx]
        return None

    def peek_type(self, offset: int = 0) -> Optional[TokenType]:
        """Nhìn trước loại token."""
        t = self.peek(offset)
        return t.type if t else None

    def advance(self) -> Optional[Token]:
        """
        Tiêu thụ và trả về token hiện tại.

        Returns:
            Token hiện tại, hoặc None nếu hết
        """
        t = self.peek()
        if t is not None:
            self._pos += 1
        return t

    def check(self, *types: TokenType) -> bool:
        """
        Kiểm tra token hiện tại có thuộc một trong các types không.
        Không tiêu thụ token.

        Args:
            *types: Các TokenType cần kiểm tra

        Returns:
            True nếu token hiện tại thuộc một trong types
        """
        t = self.peek()
        return t is not None and t.type in types

    def check_value(self, *values) -> bool:
        """
        Kiểm tra giá trị của token hiện tại.

        Args:
            *values: Các giá trị cần kiểm tra

        Returns:
            True nếu token hiện tại có giá trị thuộc values
        """
        t = self.peek()
        return t is not None and t.value in values

    def match(self, *types: TokenType) -> Optional[Token]:
        """
        Tiêu thụ token nếu khớp bất kỳ type nào.

        Args:
            *types: Các TokenType cần khớp

        Returns:
            Token tiêu thụ nếu khớp, None nếu không
        """
        if self.check(*types):
            return self.advance()
        return None

    def match_value(self, *values) -> Optional[Token]:
        """
        Tiêu thụ token nếu giá trị khớp.

        Args:
            *values: Các giá trị cần khớp

        Returns:
            Token tiêu thụ nếu khớp, None nếu không
        """
        if self.check_value(*values):
            return self.advance()
        return None

    def consume(self, *types: TokenType) -> bool:
        """
        Tiêu thụ token nếu khớp (chỉ trả về bool).

        Returns:
            True nếu đã tiêu thụ
        """
        return self.match(*types) is not None

    def expect(self, typ: TokenType, error_msg: str = '') -> Token:
        """
        Tiêu thụ token của đúng type, raise lỗi nếu không khớp.

        Args:
            typ: TokenType mong đợi
            error_msg: Thông báo lỗi tùy chọn

        Returns:
            Token tiêu thụ

        Raises:
            SyntaxError: Nếu token không khớp
        """
        t = self.peek()
        if t is None or t.type != typ:
            loc = f"L{t.line}:{t.column}" if t else "EOF"
            got = f"{t.type.name}({t.value!r})" if t else "EOF"
            expected = TOKEN_DESCRIPTIONS.get(typ, typ.name)
            msg = error_msg or f"Mong đợi {expected}, nhận được {got} tại {loc}"
            raise SyntaxError(msg)
        return self.advance()

    def expect_name(self) -> Token:
        """
        Tiêu thụ bất kỳ token nào có value là alphanumeric (identifier hoặc keyword).
        Dùng để đọc tên khi keyword được dùng như identifier.

        Returns:
            Token tên

        Raises:
            SyntaxError: Nếu không có tên hợp lệ
        """
        t = self.peek()
        if t is None:
            raise SyntaxError("Kết thúc file không mong đợi, cần tên")
        # Accept identifiers and keywords (keywords can be used as field names, method names)
        if t.type == TokenType.IDENTIFIER:
            return self.advance()
        if t.value and isinstance(t.value, str) and re.match(r'^[a-zA-Z_]\w*$', str(t.value)):
            return self.advance()
        raise SyntaxError(
            f"Mong đợi tên, nhận được {t.type.name}({t.value!r}) tại L{t.line}:{t.column}"
        )

    def is_at_end(self) -> bool:
        """
        Kiểm tra xem đã hết token chưa.

        Returns:
            True nếu hết token hoặc token hiện tại là EOF
        """
        t = self.peek()
        return t is None or t.type == TokenType.EOF

    def remaining(self) -> int:
        """
        Số token còn lại chưa tiêu thụ.

        Returns:
            Số token còn lại
        """
        return max(0, len(self._tokens) - self._pos)

    def get_slice(self, start: int, end: int) -> List[Token]:
        """
        Lấy slice token.

        Args:
            start: Index bắt đầu (inclusive)
            end: Index kết thúc (exclusive)

        Returns:
            Danh sách token trong slice
        """
        return self._tokens[start:end]

    def seek(self, pos: int) -> None:
        """
        Nhảy đến vị trí pos.

        Args:
            pos: Vị trí cần nhảy đến
        """
        self._pos = max(0, min(pos, len(self._tokens)))

    def save(self) -> int:
        """
        Lưu vị trí hiện tại.

        Returns:
            Vị trí đã lưu (để restore sau)
        """
        mark = self._pos
        self._marks.append(mark)
        return mark

    def restore(self, mark: Optional[int] = None) -> None:
        """
        Khôi phục vị trí đã lưu.

        Args:
            mark: Vị trí cần khôi phục (None = dùng vị trí cuối stack)
        """
        if mark is not None:
            self._pos = mark
        elif self._marks:
            self._pos = self._marks.pop()

    def discard_mark(self) -> None:
        """Bỏ mark cuối cùng mà không restore."""
        if self._marks:
            self._marks.pop()

    def context_window(self, n: int = 3) -> List[Token]:
        """
        Lấy n token xung quanh vị trí hiện tại (để hiển thị lỗi).

        Args:
            n: Số token mỗi phía

        Returns:
            Danh sách token trong cửa sổ ngữ cảnh
        """
        start = max(0, self._pos - n)
        end = min(len(self._tokens), self._pos + n + 1)
        return self._tokens[start:end]

    def all_tokens(self) -> List[Token]:
        """Trả về tất cả token."""
        return self._tokens[:]

    def consumed(self) -> List[Token]:
        """Trả về các token đã tiêu thụ."""
        return self._tokens[:self._pos]

    def not_consumed(self) -> List[Token]:
        """Trả về các token chưa tiêu thụ."""
        return self._tokens[self._pos:]

    def current_line(self) -> int:
        """Dòng hiện tại."""
        t = self.peek()
        return t.line if t else 0

    def current_col(self) -> int:
        """Cột hiện tại."""
        t = self.peek()
        return t.column if t else 0


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_precedence(op: str) -> int:
    """
    Lấy mức độ ưu tiên của operator.

    Args:
        op: Chuỗi operator (e.g. '+', '==', '&&')

    Returns:
        Mức độ ưu tiên (cao hơn = ưu tiên hơn). 0 nếu không tìm thấy.

    Examples:
        >>> get_precedence('+')  # 14
        14
        >>> get_precedence('*')  # 15
        15
        >>> get_precedence('==')  # 10
        10
    """
    entry = OPERATOR_PRECEDENCE.get(op)
    return entry[0] if entry else 0


def is_right_associative(op: str) -> bool:
    """
    Kiểm tra operator có phải right-associative không.

    Args:
        op: Chuỗi operator

    Returns:
        True nếu right-associative

    Examples:
        >>> is_right_associative('=')   # True
        True
        >>> is_right_associative('+')   # False
        False
        >>> is_right_associative('**')  # True
        True
    """
    return op in RIGHT_ASSOCIATIVE_OPS


def get_arity(op: str) -> str:
    """
    Lấy arity của operator.

    Args:
        op: Chuỗi operator

    Returns:
        'binary' | 'unary_prefix' | 'unary_postfix' | 'ternary' | 'unknown'
    """
    entry = OPERATOR_PRECEDENCE.get(op)
    return entry[2] if entry else 'unknown'


def is_overloadable(op: str) -> bool:
    """
    Kiểm tra operator có thể overload không.

    Args:
        op: Chuỗi operator

    Returns:
        True nếu operator có thể overload trong class CP+*
    """
    return op in OVERLOADABLE_OPS


def get_token_description(tok_type: TokenType) -> str:
    """
    Lấy mô tả tiếng Việt của token type.

    Args:
        tok_type: TokenType

    Returns:
        Chuỗi mô tả
    """
    return TOKEN_DESCRIPTIONS.get(tok_type, tok_type.name)


def tokens_to_string(tokens: List[Token], sep: str = ' ') -> str:
    """
    Chuyển danh sách token thành chuỗi (join lexemes).

    Args:
        tokens: Danh sách token
        sep: Ký tự phân cách

    Returns:
        Chuỗi ghép các lexeme
    """
    return sep.join(str(t.lexeme or t.value or '') for t in tokens)


def find_tokens_by_type(tokens: List[Token], tok_type: TokenType) -> List[Token]:
    """
    Tìm tất cả token của một type.

    Args:
        tokens: Danh sách token
        tok_type: TokenType cần tìm

    Returns:
        Danh sách token khớp
    """
    return [t for t in tokens if t.type == tok_type]


def count_tokens_by_type(tokens: List[Token]) -> Dict[str, int]:
    """
    Đếm số token theo từng type.

    Args:
        tokens: Danh sách token

    Returns:
        Dict mapping type_name -> count
    """
    counts: Dict[str, int] = {}
    for t in tokens:
        key = t.type.name
        counts[key] = counts.get(key, 0) + 1
    return counts


def format_token_list(tokens: List[Token], max_display: int = 10) -> str:
    """
    Định dạng danh sách token để hiển thị.

    Args:
        tokens: Danh sách token
        max_display: Số token tối đa hiển thị

    Returns:
        Chuỗi biểu diễn
    """
    lines = []
    for i, tok in enumerate(tokens[:max_display]):
        lines.append(f"  [{i:3d}] L{tok.line:3d}:{tok.column:<3d} {tok.type.name:<20} {tok.value!r}")
    if len(tokens) > max_display:
        lines.append(f"  ... và {len(tokens) - max_display} token nữa")
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# UNICODE SUPPORT
# ══════════════════════════════════════════════════════════════════════════════

# Unicode categories allowed in identifiers
# Tiếng Việt, CJK, Arabic, Cyrillic, Latin Extended, etc.
UNICODE_ID_START_PATTERN = re.compile(
    r'[a-zA-Z_'
    r'\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF'   # Latin Extended
    r'\u0300-\u036F'                                # Combining Diacritical Marks (Vietnamese)
    r'\u0370-\u037D\u037F-\u1FFF'                  # Greek, Coptic, Cyrillic, etc.
    r'\u200C-\u200D'                                # Zero-width non-joiner/joiner
    r'\u2070-\u218F'                                # Superscript/Subscript
    r'\u2C00-\u2FEF'                                # Various scripts
    r'\u3001-\uD7FF'                                # CJK, Hangul
    r'\uF900-\uFDCF\uFDF0-\uFFFD'                  # Private use, CJK compat
    r']'
)

UNICODE_ID_CONTINUE_PATTERN = re.compile(
    r'[a-zA-Z0-9_'
    r'\u00B7'                                        # Middle dot
    r'\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u037D'     # Latin Extended
    r'\u037F-\u1FFF'                                 # Various
    r'\u200C-\u200D'                                 # Zero-width
    r'\u203F-\u2040'                                 # Connector punctuation
    r'\u2070-\u218F\u2C00-\u2FEF'                  # Various scripts
    r'\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD'    # CJK etc.
    r']'
)


def is_id_start(ch: str) -> bool:
    """Kiểm tra ký tự có thể bắt đầu identifier không."""
    if not ch:
        return False
    return bool(UNICODE_ID_START_PATTERN.match(ch))


def is_id_continue(ch: str) -> bool:
    """Kiểm tra ký tự có thể tiếp tục identifier không."""
    if not ch:
        return False
    return bool(UNICODE_ID_CONTINUE_PATTERN.match(ch))


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANT TABLES
# ══════════════════════════════════════════════════════════════════════════════

# Escape sequence mapping
ESCAPE_SEQUENCES: Dict[str, str] = {
    'n':  '\n',   # newline
    't':  '\t',   # tab
    'r':  '\r',   # carriage return
    '\\': '\\',   # backslash
    '"':  '"',    # double quote
    "'":  "'",    # single quote
    '0':  '\0',   # null character
    'a':  '\a',   # bell
    'b':  '\b',   # backspace
    'f':  '\f',   # form feed
    'v':  '\v',   # vertical tab
    'e':  '\x1B', # escape
    '{':  '{',    # literal brace (in templates)
    '}':  '}',    # literal brace
}

# Numeric base prefixes
NUM_BASES: Dict[str, int] = {
    '0b': 2,   # binary
    '0B': 2,
    '0o': 8,   # octal
    '0O': 8,
    '0x': 16,  # hexadecimal
    '0X': 16,
}

# Integer type suffixes
INT_SUFFIXES = {
    'i8': TokenType.INT_I8,
    'i16': TokenType.INT_I16,
    'i32': TokenType.INT_I32,
    'i64': TokenType.INT_I64,
    'i128': TokenType.INT_I128,
    'u8': TokenType.INT_U8,
    'u16': TokenType.INT_U16,
    'u32': TokenType.INT_U32,
    'u64': TokenType.INT_U64,
    'u128': TokenType.INT_U128,
    'usize': TokenType.INT_USIZE,
}

# Float type suffixes
FLOAT_SUFFIXES = {
    'f32': TokenType.FLOAT_F32,
    'f64': TokenType.FLOAT_F64,
}

# Hex digit characters
HEX_DIGITS = frozenset('0123456789abcdefABCDEF')

# Octal digit characters
OCT_DIGITS = frozenset('01234567')

# Binary digit characters
BIN_DIGITS = frozenset('01')


# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD TRIE — tra cứu nhanh O(k) thay vì O(1) hash table
# (Hữu ích khi source lớn và có nhiều keyword dài)
# ══════════════════════════════════════════════════════════════════════════════

class KeywordTrie:
    """
    Cấu trúc Trie để tra cứu keyword nhanh.
    Mỗi node là dict mapping char -> child node.
    Node lá có thêm '_type' key chứa TokenType.

    Usage:
        >>> trie = KeywordTrie()
        >>> trie.insert('true', TokenType.BOOLEAN)
        >>> result = trie.search('true')
        >>> print(result)  # TokenType.BOOLEAN
    """

    def __init__(self):
        """Khởi tạo Trie rỗng."""
        self._root: Dict[str, Any] = {}
        self._build()

    def _build(self):
        """Build trie từ bảng KEYWORDS."""
        for keyword, tok_type in KEYWORDS.items():
            self.insert(keyword, tok_type)

    def insert(self, keyword: str, tok_type: TokenType) -> None:
        """
        Thêm keyword vào trie.

        Args:
            keyword: Chuỗi keyword
            tok_type: TokenType tương ứng
        """
        node = self._root
        for ch in keyword:
            if ch not in node:
                node[ch] = {}
            node = node[ch]
        node['_type'] = tok_type

    def search(self, word: str) -> Optional[TokenType]:
        """
        Tìm kiếm word trong trie.

        Args:
            word: Chuỗi cần tìm

        Returns:
            TokenType nếu tìm thấy, None nếu không
        """
        node = self._root
        for ch in word:
            if ch not in node:
                return None
            node = node[ch]
        return node.get('_type')

    def starts_with(self, prefix: str) -> bool:
        """
        Kiểm tra có keyword nào bắt đầu bằng prefix không.

        Args:
            prefix: Chuỗi tiền tố

        Returns:
            True nếu có
        """
        node = self._root
        for ch in prefix:
            if ch not in node:
                return False
            node = node[ch]
        return True

    def all_keywords(self) -> List[str]:
        """Lấy tất cả keyword trong trie."""
        result = []
        def dfs(node, current):
            if '_type' in node:
                result.append(current)
            for ch, child in node.items():
                if ch != '_type':
                    dfs(child, current + ch)
        dfs(self._root, '')
        return sorted(result)


# Global trie instance
KEYWORD_TRIE = KeywordTrie()


# ══════════════════════════════════════════════════════════════════════════════
# TOKENIZE UTILITY
# ══════════════════════════════════════════════════════════════════════════════

def tokenize_string(source: str, filename: str = '<string>') -> List[Token]:
    """
    Tokenize một chuỗi source code CP+*.
    Tiện ích đơn giản (cho macro expansion, REPL, test).

    Args:
        source: Source code CP+*
        filename: Tên file (cho error messages)

    Returns:
        Danh sách Token

    Examples:
        >>> tokens = tokenize_string('name := "hello"')
        >>> for t in tokens:
        ...     print(t)
    """
    from lexer import Lexer
    lexer = Lexer(source, filename)
    return lexer.tokenize()


# ══════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  CP+* Token System — Self Test                           ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # Test TokenType count
    all_types = list(TokenType)
    print(f"✅ TokenType count: {len(all_types)} types")
    print(f"✅ Keywords: {len(KEYWORDS)} entries")
    print(f"✅ Operators with precedence: {len(OPERATOR_PRECEDENCE)} entries")
    print(f"✅ Token descriptions: {len(TOKEN_DESCRIPTIONS)} entries")
    print()

    # Test Token creation
    print("=== Token Creation ===")
    t1 = Token(TokenType.NUMBER, 42, line=1, column=5, filename='test.cpps')
    print(f"  {repr(t1)}")
    print(f"  is_literal: {t1.is_literal()}")
    print(f"  to_dict: {t1.to_dict()}")
    print(f"  to_json: {t1.to_json()}")

    t2 = Token(TokenType.IDENTIFIER, 'myVar', line=2, column=1)
    print(f"\n  {repr(t2)}")
    print(f"  is_keyword: {t2.is_keyword()}")

    t3 = Token(TokenType.BOOLEAN, True, line=3, column=1)
    print(f"\n  {repr(t3)}")
    print(f"  is_literal: {t3.is_literal()}")
    print()

    # Test TokenFactory
    print("=== TokenFactory ===")
    factory = TokenFactory('test.cpps')
    tok = factory.make_ident('true', 1, 1)
    print(f"  make_ident('true') → {tok}")
    tok2 = factory.make_ident('myVar', 2, 1)
    print(f"  make_ident('myVar') → {tok2}")
    tok3 = factory.make_number(3.14, 3, 1, '3.14')
    print(f"  make_number(3.14) → {tok3}")
    print()

    # Test TokenStream
    print("=== TokenStream ===")
    tokens = [
        Token(TokenType.IDENTIFIER, 'x', 1, 1),
        Token(TokenType.KW_LET, ':=', 1, 3),
        Token(TokenType.NUMBER, 42, 1, 6),
        Token(TokenType.EOF, None, 1, 8),
    ]
    stream = TokenStream(tokens)
    print(f"  length: {len(stream)}")
    print(f"  peek: {stream.peek()}")
    tok = stream.advance()
    print(f"  advance: {tok}")
    print(f"  check(KW_LET): {stream.check(TokenType.KW_LET)}")
    matched = stream.match(TokenType.KW_LET)
    print(f"  match(KW_LET): {matched}")
    print(f"  remaining: {stream.remaining()}")
    print()

    # Test keyword trie
    print("=== KeywordTrie ===")
    print(f"  search('true') → {KEYWORD_TRIE.search('true')}")
    print(f"  search('class') → {KEYWORD_TRIE.search('class')}")
    print(f"  search('unknown') → {KEYWORD_TRIE.search('unknown')}")
    print(f"  starts_with('im') → {KEYWORD_TRIE.starts_with('im')}")
    print(f"  total keywords: {len(KEYWORD_TRIE.all_keywords())}")
    print()

    # Test precedence
    print("=== Operator Precedence ===")
    for op in ['+', '*', '==', '&&', '=', '**']:
        prec = get_precedence(op)
        assoc = 'R' if is_right_associative(op) else 'L'
        overload = '✓' if is_overloadable(op) else '✗'
        print(f"  '{op:4s}': prec={prec:2d}, assoc={assoc}, overloadable={overload}")
    print()

    # Test escape sequences
    print("=== Escape Sequences ===")
    for esc, char in list(ESCAPE_SEQUENCES.items())[:5]:
        print(f"  '\\{esc}' → {repr(char)}")
    print()

    # Test unicode helpers
    print("=== Unicode Support ===")
    tests = ['a', 'α', 'ñ', 'あ', '한', '5', '_', ' ', '\n']
    for ch in tests:
        start = is_id_start(ch)
        cont = is_id_continue(ch)
        print(f"  {repr(ch):6s}: id_start={start}, id_continue={cont}")
    print()

    # Test error token
    print("=== Error Tokens ===")
    err = ErrorToken("Unclosed string", line=5, column=3,
                     severity='error', suggestion="Thêm dấu \" để đóng chuỗi")
    print(f"  {repr(err)}")
    print(f"  {err.format_error()}")
    print()

    print("✅ Tất cả tests đã qua!")
    print(f"📊 Tổng số TokenType: {len(all_types)}")
    print(f"📊 Tổng số Keyword: {len(KEYWORDS)}")
    print(f"📊 Tổng số Operator: {len(OPERATOR_PRECEDENCE)}")
