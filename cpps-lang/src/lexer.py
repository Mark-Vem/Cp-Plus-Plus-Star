"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CP+* (C-Plus-Plus-Star) Language — Lexer / Tokenizer                       ║
║  File: src/lexer.py                                                          ║
║  Version: 2.0 — Advanced Edition                                             ║
║                                                                              ║
║  Lexer đầy đủ chức năng cho ngôn ngữ CP+*:                                  ║
║  - Unicode identifiers (Tiếng Việt, CJK, Cyrillic, Arabic, ...)             ║
║  - Template strings với ${} interpolation                                    ║
║  - Raw strings: r"...", r#...#, r@...@                                       ║
║  - Block comments lồng nhau: --[[ ... --]]                                   ║
║  - Doc comments: --|| ... --||                                                ║
║  - Lifetime tokens: 'a, 'static, '_                                          ║
║  - Số đa hệ: 0b, 0o, 0x, decimal                                            ║
║  - Scientific notation: 1.5e10, 2.5E-3                                       ║
║  - Digit separators: 1_000_000                                                ║
║  - Type suffixes: 42i32, 3.14f64                                             ║
║  - Đầy đủ escape sequences                                                    ║
║  - Error recovery (panic mode)                                                ║
║  - Thống kê chi tiết                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Architecture Overview
=====================

LexerMode: Trạng thái hiện tại của lexer
  - NORMAL:          Chế độ bình thường
  - TEMPLATE_STRING: Bên trong template string ``
  - INTERPOLATION:   Bên trong ${...} interpolation
  - RAW_STRING:      Bên trong raw string r"..."
  - CHAR_LITERAL:    Bên trong char literal '...'
  - BLOCK_COMMENT:   Bên trong block comment --[[...--]]
  - DOC_COMMENT:     Bên trong doc comment --||...--||
  - MACRO_BODY:      Bên trong macro definition body
  - ATTRIBUTE:       Bên trong attribute @[...]

LexerConfig: Tùy chỉnh hành vi lexer
  - Bật/tắt từng tính năng
  - Threshold cho warnings

Lexer: Class chính
  - tokenize() → List[Token]
  - Xử lý từng ký tự, emit tokens

LexerError: Exception khi gặp lỗi cú pháp không thể phục hồi
LexerWarning: Warning không fatal
"""

import re
import sys
import math
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from tokens import (
    Token, TokenType, ErrorToken, TokenFactory,
    KEYWORDS, KEYWORD_TRIE,
    ESCAPE_SEQUENCES, HEX_DIGITS, OCT_DIGITS, BIN_DIGITS,
    NUM_BASES, INT_SUFFIXES, FLOAT_SUFFIXES,
    is_id_start, is_id_continue,
    ERROR_MESSAGES, WARNING_MESSAGES,
)


# ══════════════════════════════════════════════════════════════════════════════
# LEXER MODE ENUM
# ══════════════════════════════════════════════════════════════════════════════

class LexerMode(Enum):
    """
    Trạng thái (mode) của lexer trong quá trình tokenize.
    Lexer là state machine, chuyển giữa các mode khi gặp ký tự đặc biệt.
    """
    NORMAL          = auto()   # Chế độ bình thường
    TEMPLATE_STRING = auto()   # Bên trong template string (backtick hoặc double-quote với ${})
    INTERPOLATION   = auto()   # Bên trong ${...} interpolation
    RAW_STRING      = auto()   # Bên trong raw string r"...", r#...#
    CHAR_LITERAL    = auto()   # Bên trong char literal '...'
    BLOCK_COMMENT   = auto()   # Bên trong --[[ block comment ]]
    DOC_COMMENT     = auto()   # Bên trong --|| doc comment ||
    MACRO_BODY      = auto()   # Bên trong macro body
    ATTRIBUTE       = auto()   # Bên trong attribute @[...]
    LINE_DIRECTIVE  = auto()   # Bên trong #line directive
    HEREDOC         = auto()   # Bên trong heredoc <<EOF...EOF


# ══════════════════════════════════════════════════════════════════════════════
# LEXER CONFIG
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LexerConfig:
    """
    Cấu hình cho Lexer.
    Cho phép bật/tắt từng tính năng và điều chỉnh hành vi.

    Attributes:
        emit_comments:          Phát ra comment tokens (mặc định False - bỏ qua)
        emit_whitespace:        Phát ra whitespace tokens (mặc định False)
        emit_newlines:          Phát ra newline tokens (mặc định False)
        unicode_identifiers:    Cho phép Unicode trong identifiers (mặc định True)
        allow_digit_separators: Cho phép _ trong số như 1_000_000 (mặc định True)
        allow_type_suffixes:    Cho phép suffix như i32, f64 (mặc định True)
        allow_raw_strings:      Cho phép r"..." raw strings (mặc định True)
        allow_byte_strings:     Cho phép b"..." byte strings (mặc định True)
        allow_template_strings: Cho phép template strings với ${} (mặc định True)
        allow_complex_numbers:  Cho phép 3+4i complex numbers (mặc định True)
        allow_scientific:       Cho phép 1.5e10 scientific notation (mặc định True)
        allow_nested_comments:  Cho phép --[[ lồng nhau (mặc định True)
        allow_doc_comments:     Cho phép --|| doc comments (mặc định True)
        allow_lifetime_tokens:  Cho phép 'a lifetime annotations (mặc định True)
        error_recovery:         Tự phục hồi sau lỗi (mặc định True)
        max_errors:             Số lỗi tối đa trước khi dừng (mặc định 50)
        max_warnings:           Số warning tối đa (mặc định 100)
        tab_width:              Độ rộng tab để tính cột (mặc định 4)
        strict_mode:            Chế độ nghiêm ngặt - lỗi thay vì warning (mặc định False)
    """
    emit_comments:          bool = False
    emit_whitespace:        bool = False
    emit_newlines:          bool = False
    unicode_identifiers:    bool = True
    allow_digit_separators: bool = True
    allow_type_suffixes:    bool = True
    allow_raw_strings:      bool = True
    allow_byte_strings:     bool = True
    allow_template_strings: bool = True
    allow_complex_numbers:  bool = True
    allow_scientific:       bool = True
    allow_nested_comments:  bool = True
    allow_doc_comments:     bool = True
    allow_lifetime_tokens:  bool = True
    error_recovery:         bool = True
    max_errors:             int  = 50
    max_warnings:           int  = 100
    tab_width:              int  = 4
    strict_mode:            bool = False


# ══════════════════════════════════════════════════════════════════════════════
# LEXER ERRORS & WARNINGS
# ══════════════════════════════════════════════════════════════════════════════

class LexerError(Exception):
    """
    Exception khi lexer gặp lỗi không thể phục hồi.

    Attributes:
        message: Mô tả lỗi
        line: Dòng xảy ra lỗi
        column: Cột xảy ra lỗi
        filename: Tên file
        snippet: Đoạn code quanh lỗi
    """
    def __init__(self, message: str, line: int = 0, column: int = 0,
                 filename: str = '<unknown>', snippet: str = ''):
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename
        self.snippet = snippet
        super().__init__(self.format())

    def format(self) -> str:
        """Định dạng thông báo lỗi đầy đủ."""
        parts = [f"❌ LexerError [{self.filename}:{self.line}:{self.column}]: {self.message}"]
        if self.snippet:
            parts.append(f"   | {self.snippet}")
            parts.append(f"   | {' ' * (self.column - 1)}^")
        return '\n'.join(parts)


class LexerWarning:
    """
    Warning không fatal từ lexer.

    Attributes:
        message: Mô tả warning
        line: Dòng xảy ra
        column: Cột xảy ra
        filename: Tên file
        code: Mã warning
    """
    def __init__(self, message: str, line: int = 0, column: int = 0,
                 filename: str = '<unknown>', code: str = ''):
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename
        self.code = code

    def __repr__(self) -> str:
        return (f"LexerWarning[{self.code}] "
                f"[{self.filename}:{self.line}:{self.column}]: {self.message}")

    def format(self) -> str:
        code_str = f"[{self.code}] " if self.code else ""
        return (f"⚠️  Warning {code_str}"
                f"[{self.filename}:{self.line}:{self.column}]: {self.message}")


# ══════════════════════════════════════════════════════════════════════════════
# LEXER STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LexerStats:
    """
    Thống kê chi tiết về quá trình tokenize.

    Attributes:
        tokens_emitted:      Số token đã phát ra
        lines_processed:     Số dòng đã xử lý
        chars_processed:     Số ký tự đã xử lý
        comments_skipped:    Số comment đã bỏ qua
        errors_encountered:  Số lỗi gặp phải
        warnings_emitted:    Số warning đã phát ra
        strings_parsed:      Số string literal đã parse
        numbers_parsed:      Số số literal đã parse
        identifiers_parsed:  Số identifier đã parse
        keywords_found:      Số keyword đã tìm thấy
        operators_found:     Số operator đã tìm thấy
        brackets_found:      Số bracket đã tìm thấy
        whitespace_skipped:  Số whitespace đã bỏ qua
        unicode_chars:       Số ký tự Unicode đã gặp
        escape_sequences:    Số escape sequence đã xử lý
        raw_strings_parsed:  Số raw string đã parse
        template_strings_parsed: Số template string đã parse
    """
    tokens_emitted:          int = 0
    lines_processed:         int = 0
    chars_processed:         int = 0
    comments_skipped:        int = 0
    errors_encountered:      int = 0
    warnings_emitted:        int = 0
    strings_parsed:          int = 0
    numbers_parsed:          int = 0
    identifiers_parsed:      int = 0
    keywords_found:          int = 0
    operators_found:         int = 0
    brackets_found:          int = 0
    whitespace_skipped:      int = 0
    unicode_chars:            int = 0
    escape_sequences:        int = 0
    raw_strings_parsed:      int = 0
    template_strings_parsed: int = 0
    block_comments_skipped:  int = 0
    doc_comments_skipped:    int = 0

    def summary(self) -> str:
        """Tạo tóm tắt thống kê."""
        return (
            f"Lexer Statistics:\n"
            f"  Tokens emitted:     {self.tokens_emitted}\n"
            f"  Lines processed:    {self.lines_processed}\n"
            f"  Chars processed:    {self.chars_processed}\n"
            f"  Identifiers:        {self.identifiers_parsed}\n"
            f"  Keywords:           {self.keywords_found}\n"
            f"  Numbers:            {self.numbers_parsed}\n"
            f"  Strings:            {self.strings_parsed}\n"
            f"  Operators:          {self.operators_found}\n"
            f"  Comments skipped:   {self.comments_skipped}\n"
            f"  Errors:             {self.errors_encountered}\n"
            f"  Warnings:           {self.warnings_emitted}\n"
        )


# ══════════════════════════════════════════════════════════════════════════════
# LEXER CLASS — Main tokenizer
# ══════════════════════════════════════════════════════════════════════════════

class Lexer:
    """
    Lexer/Tokenizer đầy đủ cho ngôn ngữ CP+*.

    Chuyển đổi source code CP+* thành danh sách Token.

    Features:
        - Unicode identifiers
        - Template strings với ${} interpolation
        - Raw strings: r"...", r#...#, r@...@
        - Block comments lồng nhau: --[[ ... --]]
        - Doc comments: --|| ... --||
        - Lifetime tokens: 'a, 'static, '_
        - Số đa hệ: 0b, 0o, 0x
        - Scientific notation: 1.5e10
        - Digit separators: 1_000_000
        - Type suffixes: 42i32, 3.14f64
        - Đầy đủ escape sequences
        - Error recovery với panic mode

    Usage:
        >>> lexer = Lexer('name := "hello"', 'test.cpps')
        >>> tokens = lexer.tokenize()
        >>> for tok in tokens:
        ...     print(tok)

        >>> lexer2 = Lexer(source, 'main.cpps', LexerConfig(strict_mode=True))
        >>> tokens2 = lexer2.tokenize()
        >>> print(lexer2.stats.summary())

    Attributes:
        source (str): Source code đầu vào
        filename (str): Tên file
        config (LexerConfig): Cấu hình lexer
        tokens (List[Token]): Danh sách token đã emit
        errors (List[LexerWarning]): Danh sách lỗi
        warnings (List[LexerWarning]): Danh sách warning
        stats (LexerStats): Thống kê
    """

    def __init__(
        self,
        source: str,
        filename: str = '<unknown>',
        config: Optional[LexerConfig] = None
    ):
        """
        Khởi tạo Lexer.

        Args:
            source: Source code CP+*
            filename: Tên file (dùng trong error messages)
            config: Cấu hình lexer (mặc định dùng LexerConfig())
        """
        self.source = source
        self.filename = filename
        self.config = config or LexerConfig()

        # Position tracking
        self.pos = 0        # Vị trí ký tự hiện tại trong source
        self.line = 1       # Dòng hiện tại (1-indexed)
        self.column = 1     # Cột hiện tại (1-indexed)

        # State
        self.mode = LexerMode.NORMAL
        self.mode_stack: List[LexerMode] = []   # Stack cho nested modes
        self.interp_depth = 0                    # Depth của ${...} interpolation
        self.comment_depth = 0                   # Depth của nested --[[ ]]

        # Output
        self.tokens: List[Token] = []
        self.errors: List[LexerError] = []
        self.warnings: List[LexerWarning] = []

        # Statistics
        self.stats = LexerStats()

        # Factory
        self.factory = TokenFactory(filename)

        # Source as list for O(1) access
        self._src = source
        self._len = len(source)

    # ── Low-level character access ─────────────────────────────────────────

    def peek(self, offset: int = 0) -> str:
        """
        Nhìn trước ký tự tại pos+offset mà không di chuyển.

        Args:
            offset: Số ký tự cần nhìn trước

        Returns:
            Ký tự tại vị trí đó, hoặc '\\0' nếu hết
        """
        i = self.pos + offset
        if 0 <= i < self._len:
            return self._src[i]
        return '\0'

    def peek2(self) -> Tuple[str, str]:
        """Nhìn trước 2 ký tự cùng lúc."""
        return self.peek(0), self.peek(1)

    def peek3(self) -> Tuple[str, str, str]:
        """Nhìn trước 3 ký tự cùng lúc."""
        return self.peek(0), self.peek(1), self.peek(2)

    def peek_str(self, length: int) -> str:
        """Nhìn trước một chuỗi length ký tự."""
        return self._src[self.pos:self.pos + length]

    def advance(self) -> str:
        """
        Tiêu thụ và trả về ký tự hiện tại.
        Cập nhật line/column tracking.

        Returns:
            Ký tự tiêu thụ
        """
        if self.pos >= self._len:
            return '\0'
        ch = self._src[self.pos]
        self.pos += 1
        self.stats.chars_processed += 1
        if ch == '\n':
            self.line += 1
            self.column = 1
            self.stats.lines_processed += 1
        elif ch == '\t':
            # Tab advances to next tab stop
            self.column += self.config.tab_width - ((self.column - 1) % self.config.tab_width)
        else:
            self.column += 1
        return ch

    def advance_n(self, n: int) -> str:
        """Tiêu thụ n ký tự và trả về chuỗi."""
        result = []
        for _ in range(n):
            ch = self.advance()
            if ch == '\0':
                break
            result.append(ch)
        return ''.join(result)

    def is_at_end(self) -> bool:
        """Kiểm tra đã hết source chưa."""
        return self.pos >= self._len

    def match_char(self, expected: str) -> bool:
        """
        Tiêu thụ ký tự tiếp theo nếu khớp.

        Args:
            expected: Ký tự cần khớp

        Returns:
            True nếu đã tiêu thụ
        """
        if self.peek() == expected:
            self.advance()
            return True
        return False

    def match_str(self, expected: str) -> bool:
        """
        Tiêu thụ chuỗi tiếp theo nếu khớp.

        Args:
            expected: Chuỗi cần khớp

        Returns:
            True nếu đã tiêu thụ
        """
        if self.peek_str(len(expected)) == expected:
            self.advance_n(len(expected))
            return True
        return False

    def save_pos(self) -> Tuple[int, int, int]:
        """Lưu vị trí hiện tại (pos, line, col)."""
        return self.pos, self.line, self.column

    def restore_pos(self, saved: Tuple[int, int, int]) -> None:
        """Khôi phục vị trí đã lưu."""
        self.pos, self.line, self.column = saved

    def get_line_content(self, target_line: Optional[int] = None) -> str:
        """Lấy nội dung của dòng target_line (mặc định dòng hiện tại)."""
        if target_line is None:
            target_line = self.line
        lines = self.source.split('\n')
        if 1 <= target_line <= len(lines):
            return lines[target_line - 1]
        return ''

    # ── Emit helpers ───────────────────────────────────────────────────────

    def add(self, tok_type: TokenType, value=None, line: Optional[int] = None,
            col: Optional[int] = None, lexeme: str = '') -> Token:
        """
        Thêm token vào danh sách output.

        Args:
            tok_type: Loại token
            value: Giá trị token
            line: Dòng (mặc định dòng hiện tại)
            col: Cột (mặc định cột hiện tại)
            lexeme: Chuỗi gốc

        Returns:
            Token vừa thêm
        """
        tok = Token(
            tok_type, value,
            line or self.line,
            col or self.column,
            self.filename,
            lexeme
        )
        self.tokens.append(tok)
        self.stats.tokens_emitted += 1
        return tok

    def emit_error(self, message: str, line: Optional[int] = None,
                   col: Optional[int] = None, suggestion: str = '') -> None:
        """Phát ra lỗi lexer."""
        err = LexerError(
            message,
            line or self.line,
            col or self.column,
            self.filename,
            self.get_line_content(line or self.line)
        )
        self.errors.append(err)
        self.stats.errors_encountered += 1
        if len(self.errors) >= self.config.max_errors:
            raise LexerError(
                f"Quá nhiều lỗi ({len(self.errors)}). Dừng tokenize.",
                self.line, self.column, self.filename
            )

    def emit_warning(self, message: str, code: str = '',
                     line: Optional[int] = None, col: Optional[int] = None) -> None:
        """Phát ra warning."""
        warn = LexerWarning(
            message,
            line or self.line,
            col or self.column,
            self.filename,
            code
        )
        self.warnings.append(warn)
        self.stats.warnings_emitted += 1

    # ── Whitespace & comments ──────────────────────────────────────────────

    def skip_whitespace(self) -> None:
        """Bỏ qua tất cả whitespace (space, tab, CR, LF)."""
        while not self.is_at_end() and self.peek() in ' \t\r\n':
            ch = self.advance()
            if ch in ' \t\r':
                self.stats.whitespace_skipped += 1

    def try_skip_comment(self) -> bool:
        """
        Thử bỏ qua comment nếu ở vị trí hiện tại có comment.
        Xử lý: -- single line, --[[ block ]], --|| doc ||

        Returns:
            True nếu đã bỏ qua comment, False nếu không phải comment
        """
        if self.peek() != '-' or self.peek(1) != '-':
            return False

        # Check for -- else/elif/default (NOT a comment)
        look = self.pos + 2
        while look < self._len and self._src[look] in ' \t':
            look += 1
        rest = self._src[look:look + 8]
        if (rest.startswith('else') or rest.startswith('elif') or
                rest.startswith('default')):
            return False  # These are control flow, not comments

        # --[[ Block comment (possibly nested) ]]
        if self.peek(2) == '[' and self.peek(3) == '[':
            return self._skip_block_comment()

        # --|| Doc comment
        if self.peek(2) == '|' and self.peek(3) == '|':
            return self._skip_doc_comment()

        # -- Single line comment
        return self._skip_line_comment()

    def _skip_line_comment(self) -> bool:
        """Bỏ qua comment một dòng (-- ...)."""
        start_line = self.line
        content = []
        self.advance()  # first -
        self.advance()  # second -
        while not self.is_at_end() and self.peek() != '\n':
            content.append(self.advance())
        comment_text = ''.join(content).strip()

        self.stats.comments_skipped += 1
        if self.config.emit_comments:
            self.add(TokenType.LINE_COMMENT, comment_text, start_line, lexeme='--' + ''.join(content))
        return True

    def _skip_block_comment(self) -> bool:
        """
        Bỏ qua block comment --[[ ... --]].
        Hỗ trợ lồng nhau (nested comments).
        """
        start_line = self.line
        start_col = self.column
        depth = 1
        content = []

        # Skip --[[
        for _ in range(4):
            self.advance()

        while not self.is_at_end() and depth > 0:
            c0, c1, c2, c3 = self.peek(0), self.peek(1), self.peek(2), self.peek(3)

            # Nested open: --[[
            if (self.config.allow_nested_comments and
                    c0 == '-' and c1 == '-' and c2 == '[' and c3 == '['):
                depth += 1
                content.append(self.advance_n(4))
            # Close: --]]
            elif c0 == '-' and c1 == '-' and c2 == ']' and c3 == ']':
                depth -= 1
                if depth == 0:
                    self.advance_n(4)
                    break
                else:
                    content.append(self.advance_n(4))
            else:
                content.append(self.advance())

        if depth > 0:
            self.emit_error(
                ERROR_MESSAGES['unclosed_comment'].format(start_line),
                start_line, start_col
            )

        self.stats.comments_skipped += 1
        self.stats.block_comments_skipped += 1
        if self.config.emit_comments:
            self.add(TokenType.BLOCK_COMMENT, ''.join(content), start_line)
        return True

    def _skip_doc_comment(self) -> bool:
        """Bỏ qua doc comment --|| ... --||."""
        start_line = self.line
        content = []

        # Skip --||
        for _ in range(4):
            self.advance()

        while not self.is_at_end():
            c0, c1, c2, c3 = self.peek(0), self.peek(1), self.peek(2), self.peek(3)
            if c0 == '-' and c1 == '-' and c2 == '|' and c3 == '|':
                self.advance_n(4)
                break
            content.append(self.advance())

        self.stats.comments_skipped += 1
        self.stats.doc_comments_skipped += 1
        if self.config.emit_comments or self.config.allow_doc_comments:
            self.add(TokenType.DOC_COMMENT, ''.join(content), start_line)
        return True

    def skip_directive_comment(self) -> bool:
        """
        Bỏ qua directive +* ... *+ (file headers, import blocks, etc.)
        Ngoại lệ: +* import/export/module → KHÔNG bỏ qua, xử lý như keyword.

        Returns:
            True nếu đã bỏ qua directive, False nếu là keyword block
        """
        if self.peek() != '+' or self.peek(1) != '*':
            return False

        # Check if this is +* import / +* export / +* module / +* class
        look = self.pos + 2
        while look < self._len and self._src[look] in ' \t':
            look += 1
        rest = self._src[look:look + 12]

        # Keyword blocks — skip +* sigil, let content be tokenized normally
        keyword_prefixes = ('import', 'export', 'module', 'class', 'struct',
                            'trait', 'impl', 'file', 'mode')
        for kw in keyword_prefixes:
            if rest.startswith(kw):
                self.advance()  # +
                self.advance()  # *
                return False  # Don't skip — content follows

        # Regular directive comment: skip until *+
        start_line = self.line
        content = []
        self.advance()  # +
        self.advance()  # *

        while not self.is_at_end():
            if self.peek() == '*' and self.peek(1) == '+':
                self.advance()
                self.advance()
                break
            content.append(self.advance())

        if self.config.emit_comments:
            self.add(TokenType.BLOCK_COMMENT, ''.join(content).strip(), start_line)
        self.stats.comments_skipped += 1
        return True

    # ── String reading ─────────────────────────────────────────────────────

    def read_string(self) -> str:
        """
        Đọc string literal được bao bởi dấu ".

        Hỗ trợ:
          - Escape sequences: \\n, \\t, \\r, \\\\, \\", \\', \\0, \\a, \\b, \\f, \\v, \\e
          - Hex escape: \\x41
          - Unicode escapes: \\u{1F600}, \\U0001F600
          - Octal escape: \\123

        Returns:
            Nội dung string đã xử lý escape

        Raises:
            LexerError: Nếu string không đóng
        """
        start_line = self.line
        start_col = self.column
        self.advance()  # Consume opening "
        result = []

        while not self.is_at_end() and self.peek() != '"':
            ch = self.peek()

            if ch == '\n':
                # Multiline strings allowed with warning
                self.emit_warning(
                    "String literal kéo dài nhiều dòng",
                    'W001', start_line, start_col
                )
                result.append(self.advance())
            elif ch == '\\':
                self.advance()  # Consume backslash
                escaped = self._read_escape_sequence()
                result.append(escaped)
                self.stats.escape_sequences += 1
            else:
                c = self.advance()
                if ord(c) > 127:
                    self.stats.unicode_chars += 1
                result.append(c)

        if self.peek() == '"':
            self.advance()  # Consume closing "
        else:
            self.emit_error(
                ERROR_MESSAGES['unclosed_string'].format(start_line),
                start_line, start_col,
            )

        self.stats.strings_parsed += 1
        return ''.join(result)

    def _read_escape_sequence(self) -> str:
        """
        Đọc và xử lý escape sequence sau dấu \\.

        Hỗ trợ:
          - \\n \\t \\r \\\\ \\" \\' \\0 \\a \\b \\f \\v \\e
          - \\x41       (hex: 2 digits)
          - \\u{1F600}  (unicode: 1-6 hex digits in braces)
          - \\U0001F600 (unicode: 8 hex digits)
          - \\123       (octal: up to 3 digits)

        Returns:
            Ký tự đã giải mã
        """
        ch = self.advance()

        # Common escape sequences
        if ch in ESCAPE_SEQUENCES:
            return ESCAPE_SEQUENCES[ch]

        # Hex escape: \x41
        if ch == 'x':
            hex_chars = []
            for _ in range(2):
                if self.peek() in HEX_DIGITS:
                    hex_chars.append(self.advance())
                else:
                    break
            if len(hex_chars) == 2:
                return chr(int(''.join(hex_chars), 16))
            self.emit_warning(f"Chuỗi hex escape không hợp lệ \\x{''.join(hex_chars)}")
            return '\\x' + ''.join(hex_chars)

        # Unicode escape: \u{1F600}
        if ch == 'u':
            if self.peek() == '{':
                self.advance()  # consume {
                hex_chars = []
                while self.peek() in HEX_DIGITS and len(hex_chars) < 6:
                    hex_chars.append(self.advance())
                if self.peek() == '}':
                    self.advance()  # consume }
                    if hex_chars:
                        code_point = int(''.join(hex_chars), 16)
                        try:
                            return chr(code_point)
                        except (ValueError, OverflowError):
                            self.emit_warning(f"Unicode code point không hợp lệ: U+{code_point:X}")
                            return '?'
            # \uXXXX (4 hex digits)
            hex_chars = []
            for _ in range(4):
                if self.peek() in HEX_DIGITS:
                    hex_chars.append(self.advance())
            if len(hex_chars) == 4:
                return chr(int(''.join(hex_chars), 16))
            return '\\u' + ''.join(hex_chars)

        # Unicode escape: \U00001F600 (8 hex digits)
        if ch == 'U':
            hex_chars = []
            for _ in range(8):
                if self.peek() in HEX_DIGITS:
                    hex_chars.append(self.advance())
            if len(hex_chars) == 8:
                code_point = int(''.join(hex_chars), 16)
                try:
                    return chr(code_point)
                except (ValueError, OverflowError):
                    self.emit_warning(f"Unicode code point không hợp lệ")
                    return '?'
            return '\\U' + ''.join(hex_chars)

        # Octal escape: \123 (up to 3 digits)
        if ch.isdigit() and ch in OCT_DIGITS:
            oct_chars = [ch]
            for _ in range(2):
                if self.peek() in OCT_DIGITS:
                    oct_chars.append(self.advance())
            value = int(''.join(oct_chars), 8)
            if value > 255:
                self.emit_warning(f"Octal escape {value} vượt quá byte range")
            return chr(value)

        # Unknown escape — warn and return literally
        if self.config.strict_mode:
            self.emit_error(ERROR_MESSAGES['unknown_escape'].format(ch))
        else:
            self.emit_warning(f"Ký tự escape không rõ: \\{ch}")
        return '\\' + ch

    def read_raw_string(self) -> Optional[str]:
        """
        Đọc raw string literal.
        Formats: r"...", r'...', r#...#, r@...@

        Returns:
            Nội dung raw string (không xử lý escape), hoặc None nếu không phải raw string
        """
        if self.peek() != 'r':
            return None

        saved = self.save_pos()
        self.advance()  # consume 'r'

        delimiter_ch = self.peek()

        if delimiter_ch == '"':
            # r"..."
            self.advance()  # consume "
            result = []
            while not self.is_at_end() and self.peek() != '"':
                result.append(self.advance())
            if self.peek() == '"':
                self.advance()
            else:
                self.emit_error("Raw string r\"...\" chưa đóng")
            self.stats.raw_strings_parsed += 1
            return ''.join(result)

        elif delimiter_ch == "'":
            # r'...'
            self.advance()
            result = []
            while not self.is_at_end() and self.peek() != "'":
                result.append(self.advance())
            if self.peek() == "'":
                self.advance()
            else:
                self.emit_error("Raw string r'...' chưa đóng")
            self.stats.raw_strings_parsed += 1
            return ''.join(result)

        elif delimiter_ch == '#':
            # r#...#
            self.advance()
            result = []
            while not self.is_at_end() and self.peek() != '#':
                result.append(self.advance())
            if self.peek() == '#':
                self.advance()
            else:
                self.emit_error("Raw string r#...# chưa đóng")
            self.stats.raw_strings_parsed += 1
            return ''.join(result)

        elif delimiter_ch == '@':
            # r@...@
            self.advance()
            result = []
            while not self.is_at_end() and self.peek() != '@':
                result.append(self.advance())
            if self.peek() == '@':
                self.advance()
            else:
                self.emit_error("Raw string r@...@ chưa đóng")
            self.stats.raw_strings_parsed += 1
            return ''.join(result)

        # Not a raw string — restore position
        self.restore_pos(saved)
        return None

    def read_char_literal(self) -> str:
        """
        Đọc char literal 'x' hoặc '\\n'.

        Returns:
            Chuỗi ký tự (length 1 thường)
        """
        self.advance()  # consume opening '
        ch = self.peek()

        if ch == '\\':
            self.advance()
            result = self._read_escape_sequence()
        elif ch == "'":
            result = ''
        else:
            result = self.advance()

        if self.peek() == "'":
            self.advance()  # consume closing '
        else:
            self.emit_warning("Char literal chưa đóng")

        return result

    # ── Number reading ─────────────────────────────────────────────────────

    def read_number(self) -> Tuple[Any, TokenType]:
        """
        Đọc số literal.

        Hỗ trợ:
          - Decimal: 123, 1_000_000
          - Hex: 0xFF, 0x1A_2B
          - Octal: 0o77, 0o7_7
          - Binary: 0b1010, 0b1010_1100
          - Float: 3.14, 1_000.5
          - Scientific: 1.5e10, 2.5E-3, 1.0e+6
          - Suffixes: 42i32, 42u64, 3.14f32
          - Complex: 3+4i (handled separately after binary op)

        Returns:
            Tuple (value, token_type)
              value: int hoặc float
              token_type: NUMBER, FLOAT_F32, FLOAT_F64, INT_I32, etc.
        """
        result_chars = []
        is_float = False
        base = 10
        tok_type = TokenType.NUMBER

        ch = self.peek()

        # Check for base prefix: 0x, 0o, 0b
        if ch == '0' and self.peek(1) in ('x', 'X', 'o', 'O', 'b', 'B'):
            prefix_ch = self.peek(1).lower()
            result_chars.append(self.advance())  # '0'
            result_chars.append(self.advance())  # 'x'/'o'/'b'

            if prefix_ch == 'x':
                base = 16
                valid_digits = HEX_DIGITS
            elif prefix_ch == 'o':
                base = 8
                valid_digits = OCT_DIGITS
            else:  # 'b'
                base = 2
                valid_digits = BIN_DIGITS

            digit_chars = []
            while self.peek() in valid_digits or (
                    self.config.allow_digit_separators and self.peek() == '_'):
                c = self.advance()
                if c != '_':
                    digit_chars.append(c)

            if not digit_chars:
                self.emit_error(f"Số base-{base} không có chữ số")
                return 0, TokenType.NUMBER

            try:
                value = int(''.join(digit_chars), base)
            except ValueError:
                self.emit_error(f"Số base-{base} không hợp lệ")
                value = 0

            # Check for suffix
            suffix_value, tok_type = self._read_num_suffix(value, False)
            self.stats.numbers_parsed += 1
            return suffix_value, tok_type

        # Decimal integer or float
        while self.peek().isdigit() or (
                self.config.allow_digit_separators and
                self.peek() == '_' and self.peek(1).isdigit()):
            c = self.advance()
            if c != '_':
                result_chars.append(c)

        # Decimal point: 3.14
        if self.peek() == '.' and self.peek(1).isdigit():
            is_float = True
            result_chars.append(self.advance())  # '.'
            while self.peek().isdigit() or (
                    self.config.allow_digit_separators and
                    self.peek() == '_' and self.peek(1).isdigit()):
                c = self.advance()
                if c != '_':
                    result_chars.append(c)

        # Scientific notation: 1.5e10, 2.5E-3
        if self.config.allow_scientific and self.peek() in ('e', 'E'):
            is_float = True
            result_chars.append(self.advance())  # 'e'/'E'
            if self.peek() in ('+', '-'):
                result_chars.append(self.advance())  # sign
            if not self.peek().isdigit():
                self.emit_warning("Scientific notation thiếu exponent")
            while self.peek().isdigit():
                result_chars.append(self.advance())

        num_str = ''.join(result_chars)
        try:
            if is_float:
                raw_value: Any = float(num_str)
            else:
                raw_value = int(num_str)
        except ValueError:
            self.emit_error(ERROR_MESSAGES['invalid_number'].format(num_str))
            raw_value = 0

        # Check for type suffix and/or complex imaginary part
        final_value, tok_type = self._read_num_suffix(raw_value, is_float)

        self.stats.numbers_parsed += 1
        return final_value, tok_type

    def _read_num_suffix(self, value: Any, is_float: bool) -> Tuple[Any, TokenType]:
        """
        Đọc type suffix sau số.
        e.g. 42i32, 42u64, 3.14f32, 3.14f64

        Returns:
            (value, token_type)
        """
        # Check integer suffixes
        if not is_float:
            for suffix, tok_type in sorted(INT_SUFFIXES.items(), key=lambda x: -len(x[0])):
                if self.peek_str(len(suffix)) == suffix:
                    # Make sure it's not followed by more alphanumeric
                    after = self.peek(len(suffix))
                    if not (after.isalnum() or after == '_'):
                        self.advance_n(len(suffix))
                        return int(value), tok_type

        # Check float suffixes
        for suffix, tok_type in sorted(FLOAT_SUFFIXES.items(), key=lambda x: -len(x[0])):
            if self.peek_str(len(suffix)) == suffix:
                after = self.peek(len(suffix))
                if not (after.isalnum() or after == '_'):
                    self.advance_n(len(suffix))
                    return float(value), tok_type

        # No suffix
        return value, TokenType.NUMBER

    # ── Identifier reading ─────────────────────────────────────────────────

    def read_identifier(self) -> str:
        """
        Đọc identifier (bao gồm Unicode).

        Returns:
            Chuỗi identifier
        """
        result = []
        ch = self.peek()

        # First character: must be id_start
        if self.config.unicode_identifiers and is_id_start(ch):
            result.append(self.advance())
            if ord(ch) > 127:
                self.stats.unicode_chars += 1
        elif ch.isalpha() or ch == '_':
            result.append(self.advance())
        else:
            return ''

        # Remaining characters: id_continue
        while not self.is_at_end():
            ch = self.peek()
            if self.config.unicode_identifiers and is_id_continue(ch):
                result.append(self.advance())
                if ord(ch) > 127:
                    self.stats.unicode_chars += 1
            elif ch.isalnum() or ch == '_':
                result.append(self.advance())
            else:
                break

        return ''.join(result)

    # ── Lifetime annotation ────────────────────────────────────────────────

    def try_read_lifetime(self, line: int, col: int) -> bool:
        """
        Thử đọc lifetime annotation 'a, 'static, '_.

        Returns:
            True nếu đã đọc lifetime, False nếu là char literal
        """
        if not self.config.allow_lifetime_tokens:
            return False

        # Lifetime: 'identifier không có closing '
        # Char literal: 'x' hoặc '\\n'
        next_ch = self.peek(1)

        # 'static is always lifetime
        if self._src[self.pos + 1:self.pos + 7] == 'static':
            after = self.peek(7) if self.pos + 7 < self._len else '\0'
            if not (after.isalnum() or after == '_'):
                self.advance()  # consume '
                ident = self.read_identifier()
                self.add(TokenType.LIFETIME, ident, line, col, f"'{ident}")
                return True

        # '_ is always lifetime wildcard
        if next_ch == '_' and not (self.peek(2).isalnum() or self.peek(2) == '_'):
            self.advance()  # consume '
            self.advance()  # consume _
            self.add(TokenType.LIFETIME, '_', line, col, "'_")
            return True

        # If next is alpha and not followed by ' (char literal), it's a lifetime
        if next_ch.isalpha() or next_ch == '_':
            # Check if it's a char literal: 'x'
            # Look ahead for closing '
            probe = self.pos + 1
            while probe < self._len and self._src[probe] != '\n':
                if self._src[probe] == "'":
                    return False  # It's a char literal
                if not (self._src[probe].isalnum() or self._src[probe] == '_'):
                    break
                probe += 1
            # It's a lifetime
            self.advance()  # consume '
            ident = self.read_identifier()
            if ident:
                self.add(TokenType.LIFETIME, ident, line, col, f"'{ident}")
                return True

        return False

    # ── Main tokenize loop ─────────────────────────────────────────────────

    def tokenize(self) -> List[Token]:
        """
        Tokenize toàn bộ source code.

        Returns:
            Danh sách Token (kết thúc bằng EOF token)

        Raises:
            LexerError: Nếu gặp quá nhiều lỗi
        """
        self.tokens = []
        self.stats = LexerStats()

        while not self.is_at_end():
            self.skip_whitespace()
            if self.is_at_end():
                break

            # Try directive comment +* ... *+
            if self.skip_directive_comment():
                continue

            # Try regular comment --
            if self.try_skip_comment():
                continue

            # Tokenize the next token
            self._tokenize_one()

        # Add EOF
        self.add(TokenType.EOF, None, self.line, self.column, '')
        self.stats.lines_processed = max(self.stats.lines_processed, self.line)
        return self.tokens

    def _tokenize_one(self) -> None:
        """Tokenize một token tại vị trí hiện tại."""
        line = self.line
        col = self.column
        ch = self.peek()

        # ── Raw string: r"..." ────────────────────────────────────────────
        if (ch == 'r' and self.config.allow_raw_strings and
                self.peek(1) in ('"', "'", '#', '@')):
            raw = self.read_raw_string()
            if raw is not None:
                self.add(TokenType.RAW_STRING, raw, line, col)
                return

        # ── Lifetime / char literal: '... ─────────────────────────────────
        if ch == "'":
            if self.config.allow_lifetime_tokens and self.try_read_lifetime(line, col):
                return
            # Char literal
            char_val = self.read_char_literal()
            self.add(TokenType.CHAR, char_val, line, col)
            return

        # ── Double-at annotation: @@override ──────────────────────────────
        if ch == '@' and self.peek(1) == '@':
            self.advance()
            self.advance()
            ident = ''
            if self.peek().isalpha() or self.peek() == '_':
                ident = self.read_identifier()
            self.add(TokenType.DOUBLE_AT, '@@' + ident, line, col, '@@' + ident)
            return

        # ── @macro_tok @macro_ast @reflect @system @. ──────────────────────
        if ch == '@':
            self.advance()
            if self.peek() == '.':
                self.advance()
                field = self.read_identifier()
                self.add(TokenType.AT, '@', line, col, '@')
                self.add(TokenType.DOT, '.', line, col, '.')
                if field:
                    tok_type = KEYWORDS.get(field, TokenType.IDENTIFIER)
                    value = (True if field == 'true' else
                             False if field == 'false' else
                             None if field == 'none' else field)
                    self.add(tok_type, value, line, col, field)
                return
            if self.peek().isalpha() or self.peek() == '_':
                ident = self.read_identifier()
                if ident in ('macro_tok', 'macro_ast'):
                    self.add(TokenType.KW_MACRO, ident, line, col, '@' + ident)
                elif ident == 'reflect':
                    self.add(TokenType.KW_REFLECT, ident, line, col, '@reflect')
                elif ident == 'system':
                    self.add(TokenType.KW_SYSTEM, ident, line, col, '@system')
                else:
                    self.add(TokenType.AT, '@', line, col, '@')
                    self.add(KEYWORDS.get(ident, TokenType.IDENTIFIER),
                             ident, line, col, ident)
                return
            self.add(TokenType.AT, '@', line, col, '@')
            return

        # ── Three-character tokens ─────────────────────────────────────────
        three = self.peek_str(3)
        three_map = {
            '!>>': TokenType.KW_CONTINUE,
            '..=': TokenType.DOTDOTEQ,
            '<<=': TokenType.LSHIFT_EQ,
            '>>=': TokenType.RSHIFT_EQ,
            '**=': TokenType.POW_EQ,
            '//=': TokenType.FLOOR_DIV_EQ,
            '<=>': TokenType.SPACESHIP,
        }
        if three in three_map:
            self.advance_n(3)
            self.add(three_map[three], three, line, col, three)
            self.stats.operators_found += 1
            return

        # ── Two-character tokens ───────────────────────────────────────────
        two = self.peek_str(2)
        two_map = {
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
            '%=': TokenType.MOD_EQ,
            '&=': TokenType.AMP_EQ,
            '|=': TokenType.PIPE_EQ,
            '^=': TokenType.CARET_EQ,
            '**': TokenType.POW,
            '..': TokenType.DOTDOT,
            '//': TokenType.FLOOR_DIV,
            '^^': TokenType.XOR,
            '??': TokenType.KW_IF,
            '|>': TokenType.PIPE_OP,
        }
        if two in two_map:
            self.advance_n(2)
            self.add(two_map[two], two, line, col, two)
            self.stats.operators_found += 1
            return

        # ── Single-character tokens ────────────────────────────────────────
        single_map = {
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
            '^': TokenType.CARET,
            '$': TokenType.DOLLAR,
            '`': TokenType.BACKTICK,
        }
        if ch in single_map:
            self.advance()
            tok_type = single_map[ch]
            self.add(tok_type, ch, line, col, ch)
            if tok_type in (TokenType.LBRACE, TokenType.RBRACE,
                            TokenType.LPAREN, TokenType.RPAREN,
                            TokenType.LBRACKET, TokenType.RBRACKET):
                self.stats.brackets_found += 1
            else:
                self.stats.operators_found += 1
            return

        # ── String literal ─────────────────────────────────────────────────
        if ch == '"':
            s = self.read_string()
            self.add(TokenType.STRING, s, line, col, f'"{s}"')
            return

        # ── Number literal ─────────────────────────────────────────────────
        if ch.isdigit():
            value, tok_type = self.read_number()
            self.add(tok_type, value, line, col, str(value))
            return

        # ── Identifier / keyword ───────────────────────────────────────────
        if ch.isalpha() or ch == '_' or (
                self.config.unicode_identifiers and is_id_start(ch)):
            ident = self.read_identifier()
            if not ident:
                # Skip unknown unicode char
                self.advance()
                return

            tok_type = KEYWORDS.get(ident, TokenType.IDENTIFIER)

            if tok_type == TokenType.BOOLEAN:
                value = ident == 'true'
                self.add(tok_type, value, line, col, ident)
            elif tok_type == TokenType.NONE:
                self.add(tok_type, None, line, col, ident)
            elif tok_type == TokenType.IDENTIFIER:
                self.add(tok_type, ident, line, col, ident)
                self.stats.identifiers_parsed += 1
            else:
                self.add(tok_type, ident, line, col, ident)
                self.stats.keywords_found += 1
            return

        # ── Unknown character ──────────────────────────────────────────────
        if self.config.error_recovery:
            # Skip unknown character with warning
            unknown = self.advance()
            if ord(unknown) > 31:  # Printable
                self.emit_warning(
                    f"Ký tự không nhận dạng được: {unknown!r} (U+{ord(unknown):04X})",
                    'W002', line, col
                )
        else:
            unknown = self.advance()
            self.emit_error(
                ERROR_MESSAGES['invalid_char'].format(repr(unknown)),
                line, col
            )


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def tokenize(source: str, filename: str = '<unknown>',
             config: Optional[LexerConfig] = None) -> List[Token]:
    """
    Hàm tiện ích để tokenize source code CP+*.

    Args:
        source: Source code
        filename: Tên file
        config: Cấu hình lexer (tùy chọn)

    Returns:
        Danh sách Token

    Examples:
        >>> tokens = tokenize('x := 42')
        >>> for t in tokens:
        ...     print(t)
        Token(IDENTIFIER, 'x' L1:1)
        Token(KW_LET, ':=' L1:3)
        Token(NUMBER, 42 L1:6)
        Token(EOF, None L1:8)
    """
    lexer = Lexer(source, filename, config)
    return lexer.tokenize()


def tokenize_file(filepath: str, config: Optional[LexerConfig] = None) -> List[Token]:
    """
    Đọc file và tokenize.

    Args:
        filepath: Đường dẫn file .cpps
        config: Cấu hình lexer

    Returns:
        Danh sách Token

    Raises:
        FileNotFoundError: Nếu file không tồn tại
        LexerError: Nếu gặp lỗi lexer
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    return tokenize(source, filepath, config)


def tokenize_interactive(source: str) -> List[Token]:
    """
    Tokenize với cấu hình phù hợp cho REPL.
    Cho phép statement không đầy đủ.

    Args:
        source: Source code từ REPL

    Returns:
        Danh sách Token
    """
    config = LexerConfig(
        emit_comments=False,
        error_recovery=True,
        max_errors=5,
        strict_mode=False,
    )
    return tokenize(source, '<repl>', config)


# ══════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════════════════════

def _run_tests():
    """Chạy test tự động cho Lexer."""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  CP+* Lexer — Self Test                                  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    tests = [
        # (source, expected_types)
        ('x := 42',
         [TokenType.IDENTIFIER, TokenType.KW_LET, TokenType.NUMBER, TokenType.EOF]),

        ('name :: mut string = "hello"',
         [TokenType.IDENTIFIER, TokenType.DOUBLE_COLON, TokenType.KW_MUT,
          TokenType.IDENTIFIER, TokenType.ASSIGN, TokenType.STRING, TokenType.EOF]),

        ('++ main <~ () -> int **',
         [TokenType.KW_FN, TokenType.IDENTIFIER, TokenType.KW_PARAM_ARROW,
          TokenType.LPAREN, TokenType.RPAREN, TokenType.ARROW, TokenType.IDENTIFIER,
          TokenType.POW, TokenType.EOF]),

        ('?? score >= 90 **',
         [TokenType.KW_IF, TokenType.IDENTIFIER, TokenType.GTE, TokenType.NUMBER,
          TokenType.POW, TokenType.EOF]),

        ('<- a + b',
         [TokenType.KW_RETURN, TokenType.IDENTIFIER, TokenType.PLUS,
          TokenType.IDENTIFIER, TokenType.EOF]),

        ('~> io::println("Hello!")',
         [TokenType.KW_PIPE, TokenType.IDENTIFIER, TokenType.DOUBLE_COLON,
          TokenType.IDENTIFIER, TokenType.LPAREN, TokenType.STRING,
          TokenType.RPAREN, TokenType.EOF]),

        ('!>',  [TokenType.KW_BREAK, TokenType.EOF]),
        ('!>>', [TokenType.KW_CONTINUE, TokenType.EOF]),
        ('!!',  [TokenType.KW_PANIC, TokenType.EOF]),

        ('1_000_000', [TokenType.NUMBER, TokenType.EOF]),
        ('0xFF',      [TokenType.NUMBER, TokenType.EOF]),
        ('0b1010',    [TokenType.NUMBER, TokenType.EOF]),
        ('0o777',     [TokenType.NUMBER, TokenType.EOF]),
        ('3.14e10',   [TokenType.NUMBER, TokenType.EOF]),
        ('true',      [TokenType.BOOLEAN, TokenType.EOF]),
        ('false',     [TokenType.BOOLEAN, TokenType.EOF]),
        ('none',      [TokenType.NONE, TokenType.EOF]),

        ('@.field', [TokenType.AT, TokenType.DOT, TokenType.IDENTIFIER, TokenType.EOF]),
        ('@@override', [TokenType.DOUBLE_AT, TokenType.EOF]),
        ("'a", [TokenType.LIFETIME, TokenType.EOF]),
        ("'static", [TokenType.LIFETIME, TokenType.EOF]),

        ('class Dog : Animal',
         [TokenType.KW_CLASS, TokenType.IDENTIFIER, TokenType.COLON,
          TokenType.IDENTIFIER, TokenType.EOF]),

        ('?~ n',
         [TokenType.KW_MATCH, TokenType.IDENTIFIER, TokenType.EOF]),

        ('<> item :: items',
         [TokenType.KW_FOR, TokenType.IDENTIFIER, TokenType.DOUBLE_COLON,
          TokenType.IDENTIFIER, TokenType.EOF]),
    ]

    passed = 0
    failed = 0

    for source, expected_types in tests:
        tokens = tokenize(source)
        actual_types = [t.type for t in tokens]
        if actual_types == expected_types:
            passed += 1
            print(f"  ✅ {source!r:<40} → {len(tokens)-1} tokens")
        else:
            failed += 1
            print(f"  ❌ {source!r:<40}")
            print(f"     Expected: {[t.name for t in expected_types]}")
            print(f"     Actual:   {[t.name for t in actual_types]}")

    print()
    print(f"Results: {passed} passed, {failed} failed")
    print()

    # Comprehensive test
    print("=== Comprehensive Lexer Test ===")
    source_complex = '''
+* file: test.cpps *+
+* import -> {
    std::io,
    std::collections::{List, Map}
}

-- Hằng số
name := "CP+*"
version := 2.0

-- Biến mutable
age :: mut int = 25
items :: mut List = List::new()

-- Hàm
++ add <~ (a: int, b: int) -> int ** {
    <- a + b
}

++ main <~ () -> int ** {
    ~> io::println("Hello {}!", name)
    ?? age >= 18 ** {
        ~> io::println("Người lớn")
    } -- else ** {
        ~> io::println("Trẻ em")
    }
    <> i :: [1, 2, 3] ** {
        ~> io::println("{}", i)
    }
    count :: mut int = 0
    ?? count < 5 ** {
        count += 1
    }
    <- 0
}
'''
    lexer = Lexer(source_complex, 'test.cpps')
    tokens = lexer.tokenize()
    print(f"  Tokens: {len(tokens)}")
    print(f"  Errors: {lexer.stats.errors_encountered}")
    print(f"  Warnings: {lexer.stats.warnings_emitted}")
    print(f"  Keywords: {lexer.stats.keywords_found}")
    print(f"  Identifiers: {lexer.stats.identifiers_parsed}")
    print(f"  Numbers: {lexer.stats.numbers_parsed}")
    print(f"  Strings: {lexer.stats.strings_parsed}")
    print(f"  Comments skipped: {lexer.stats.comments_skipped}")
    print()

    # Unicode test
    print("=== Unicode Identifier Test ===")
    unicode_source = 'tên := "Việt Nam"\ngiá :: float = 100.0\n数字 := 42'
    lexer2 = Lexer(unicode_source, 'unicode.cpps',
                   LexerConfig(unicode_identifiers=True))
    tokens2 = lexer2.tokenize()
    for t in tokens2[:-1]:
        print(f"  {t}")
    print()

    # Escape sequence test
    print("=== Escape Sequence Test ===")
    esc_source = r'"Hello\nWorld\t!\u{1F600}"'
    lexer3 = Lexer(esc_source, 'escape.cpps')
    tokens3 = lexer3.tokenize()
    for t in tokens3[:-1]:
        print(f"  {t}")
    print()

    print("✅ Lexer Self Test hoàn thành!")


if __name__ == '__main__':
    _run_tests()
