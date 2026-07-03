"""
diagnostics.py — Rust-style diagnostic rendering for CP+*.

Renders lex/parse/runtime errors as annotated source snippets, similar in
spirit to `rustc`'s error format:

    error: expected IDENTIFIER, got STRING('/tmp/x')
      --> examples/fs_demo.cpps:3:11
       |
     3 | fs::mkdir("/tmp/x", true)
       |           ^^^^^^^^ found STRING here
       |
       = help: namespaced calls look like `ns::fn(args)` — check for a stray `::`

This module is presentation-only: it does not change parsing/lexing/
interpreting behaviour, it only knows how to turn a `(message, filename,
line, column, length, severity, help_text)` tuple into readable output.
Used by the CLI (`cpps run/build/lint`) wherever errors/warnings surface.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


def _supports_color() -> bool:
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('CPPS_FORCE_COLOR'):
        return True
    return sys.stderr.isatty()


class Severity(Enum):
    ERROR = 'error'
    WARNING = 'warning'
    NOTE = 'note'


_COLOR = {
    Severity.ERROR: '\033[1;31m',
    Severity.WARNING: '\033[1;33m',
    Severity.NOTE: '\033[1;36m',
}
_BOLD = '\033[1m'
_BLUE = '\033[1;34m'
_RESET = '\033[0m'


@dataclass
class Diagnostic:
    """A single Rust-style diagnostic (error/warning/note)."""

    message: str
    filename: str
    line: int = 0
    column: int = 1
    length: int = 1
    severity: Severity = Severity.ERROR
    code: Optional[str] = None          # e.g. "E0308" style diagnostic code
    help_text: Optional[str] = None
    note_text: Optional[str] = None
    label: Optional[str] = None         # text shown next to the caret span

    def render(self, source_lines: Optional[List[str]] = None, color: Optional[bool] = None) -> str:
        """Render this diagnostic as a multi-line Rust-style string."""
        use_color = _supports_color() if color is None else color

        def c(text: str, code: str) -> str:
            return f"{code}{text}{_RESET}" if use_color else text

        sev_word = self.severity.value
        header = c(sev_word, _COLOR[self.severity])
        code_part = f"[{self.code}]" if self.code else ""
        out = [f"{header}{code_part}: {c(self.message, _BOLD)}"]

        loc = f"{self.filename}:{self.line}:{self.column}"
        out.append(f"  {c('-->', _BLUE)} {loc}")

        if source_lines and 1 <= self.line <= len(source_lines):
            line_text = source_lines[self.line - 1].rstrip('\n')
            gutter_w = len(str(self.line))
            gutter = ' ' * gutter_w
            out.append(f" {gutter} {c('|', _BLUE)}")
            out.append(f" {c(str(self.line), _BLUE)} {c('|', _BLUE)} {line_text}")

            col0 = max(self.column - 1, 0)
            length = max(self.length, 1)
            caret_line = ' ' * col0 + '^' * length
            label_suffix = f" {self.label}" if self.label else ""
            out.append(f" {gutter} {c('|', _BLUE)} {c(caret_line, _COLOR[self.severity])}{label_suffix}")
        out.append(f" {' ' * len(str(self.line))} {c('|', _BLUE)}")

        if self.help_text:
            out.append(f" {' ' * len(str(self.line))} {c('=', _BLUE)} {c('help', _BOLD)}: {self.help_text}")
        if self.note_text:
            out.append(f" {' ' * len(str(self.line))} {c('=', _BLUE)} {c('note', _BOLD)}: {self.note_text}")

        return '\n'.join(out)


@dataclass
class DiagnosticBag:
    """Collects diagnostics for a single compilation unit."""

    filename: str
    source: str = ""
    diagnostics: List[Diagnostic] = field(default_factory=list)

    def __post_init__(self):
        self._lines = self.source.splitlines() if self.source else []

    def error(self, message: str, line: int = 0, column: int = 1, length: int = 1,
              code: Optional[str] = None, help_text: Optional[str] = None,
              label: Optional[str] = None) -> None:
        self.diagnostics.append(Diagnostic(message, self.filename, line, column, length,
                                            Severity.ERROR, code, help_text, label=label))

    def warning(self, message: str, line: int = 0, column: int = 1, length: int = 1,
                code: Optional[str] = None, help_text: Optional[str] = None,
                label: Optional[str] = None) -> None:
        self.diagnostics.append(Diagnostic(message, self.filename, line, column, length,
                                            Severity.WARNING, code, help_text, label=label))

    def note(self, message: str, line: int = 0, column: int = 1) -> None:
        self.diagnostics.append(Diagnostic(message, self.filename, line, column,
                                            severity=Severity.NOTE))

    @property
    def has_errors(self) -> bool:
        return any(d.severity == Severity.ERROR for d in self.diagnostics)

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == Severity.WARNING)

    def render_all(self, color: Optional[bool] = None) -> str:
        blocks = [d.render(self._lines, color=color) for d in self.diagnostics]
        return '\n\n'.join(blocks)

    def print_all(self, file=None, color: Optional[bool] = None) -> None:
        file = file or sys.stderr
        if not self.diagnostics:
            return
        print(self.render_all(color=color), file=file)
        print(file=file)
        summary = []
        if self.error_count:
            summary.append(f"{self.error_count} error(s)")
        if self.warning_count:
            summary.append(f"{self.warning_count} warning(s)")
        print(f"{self.filename}: {', '.join(summary)}", file=file)


def diagnostic_from_parse_error(err, filename: str) -> Diagnostic:
    """
    Build a Diagnostic from a `ParseError`/`LexError`-like object.
    Accepts anything with `.message`/`.line`/`.column` attributes, or a
    plain string (in which case line/column default to 0/1).
    """
    if isinstance(err, str):
        return Diagnostic(message=err, filename=filename, line=0, column=1)
    message = getattr(err, 'message', str(err))
    line = getattr(err, 'line', 0) or 0
    column = getattr(err, 'column', 1) or 1
    return Diagnostic(message=message, filename=filename, line=line, column=column)


def print_parse_errors(errors: List, filename: str, source: str, file=None) -> None:
    """Convenience: render a list of parser/lexer error objects Rust-style."""
    bag = DiagnosticBag(filename, source)
    for e in errors:
        d = diagnostic_from_parse_error(e, filename)
        bag.diagnostics.append(d)
    bag.print_all(file=file)


def print_runtime_error(message: str, filename: str, source: str, line: int = 0,
                         column: int = 1, help_text: Optional[str] = None, file=None) -> None:
    bag = DiagnosticBag(filename, source)
    bag.error(message, line=line, column=column, help_text=help_text)
    bag.print_all(file=file)
