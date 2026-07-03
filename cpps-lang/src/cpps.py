#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CP+* (C-Plus-Plus-Star) Language Toolchain                                  ║
║  File: cpps.py — CLI Entry Point                                             ║
║  Version: 3.0 — Enterprise Edition                                           ║
║                                                                              ║
║  Subcommands:                                                                ║
║    cpps run <file.cpps>       — Run a program (tree-walking interpreter)    ║
║    cpps build <file.cpps>     — Lex/parse/lint + lower to groundwork IR     ║
║    cpps fmt <file.cpps>       — Reformat to canonical CP+* style            ║
║    cpps lint <file.cpps>      — Static analysis (unused vars, dead code…)   ║
║    cpps test [path]           — Discover and run *_test.cpps files          ║
║    cpps bench <file.cpps>     — Benchmark execution time                    ║
║    cpps doc [path]            — Extract `--` doc comments to Markdown       ║
║    cpps package               — Bundle project into a distributable .zip   ║
║    cpps clean                 — Remove build/doc/package artifacts         ║
║    cpps repl                  — Interactive REPL                           ║
║    cpps <file.cpps>           — Shorthand for `cpps run <file.cpps>`       ║
║                                                                              ║
║  Legacy single-shot flags (still supported): --ast, --tokens, -e, -V, -v   ║
╚══════════════════════════════════════════════════════════════════════════════╝

CP+* Language Overview
=======================

CP+* (C-Plus-Plus-Star) là ngôn ngữ lập trình hiện đại với:

  Cú pháp đặc biệt:
    :=        — khai báo biến bất biến
    :: mut    — khai báo biến có thể thay đổi
    ++        — định nghĩa hàm
    <~        — mũi tên tham số
    ->        — kiểu trả về / lambda
    **        — mở đầu thân hàm/block
    ??        — câu điều kiện if
    <>        — vòng lặp for-each
    ~>        — in ra / pipe
    <-        — lệnh return
    !!        — lệnh panic
    !>        — lệnh break
    !>>       — lệnh continue
    ?~        — pattern matching
    @         — self reference
    @.field   — truy cập field của self
    ::        — gọi method / namespace
    @@        — annotation
    -- comment  — comment một dòng
    --[[ ]]   — comment nhiều dòng (có thể lồng nhau)
    own<T>    — sở hữu giá trị
    share<T>  — tham chiếu chia sẻ
    borrow<T> — mượn tạm thời
    go        — chạy goroutine
    'a        — lifetime annotation

  Ví dụ chương trình Hello World:
    ++ main <~ () -> int ** {
        name := "World"
        ~> io::println("Hello, {}!", name)
        <- 0
    }

NOTE ON SCOPE: `cpps build` lowers a real, working subset of the language
to a portable bytecode IR (see `ir.py`) and can execute it with a genuine
stack-based VM. It does NOT generate native machine code — there is no
LLVM backend and no JIT in this toolchain. Full-language semantics
(classes, traits, generics, ownership, pattern matching, goroutines,
reflection, macros) are executed by the tree-walking interpreter
(`interpreter.py`), which `cpps run` always uses.
"""

import sys
import os
import time
import glob
import shutil
import zipfile
import traceback
import argparse
from typing import Optional, List

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from lexer import Lexer, tokenize, LexerConfig
from parser import Parser, parse, ASTPrinter, FnDef, ClassDef, StructDef, TraitDef
from interpreter import Interpreter, run, run_file
from diagnostics import DiagnosticBag, print_parse_errors
from formatter import format_source
from linter import lint_source
from ir import lower as ir_lower, IRInterpreter, IRRuntimeError


VERSION = "3.0.0"
VERSION_NAME = "Enterprise Edition"
LANGUAGE_NAME = "CP+*"
BUILD_DATE = "2026"
PYTHON_REQUIRED = "3.8+"

BANNER = r"""
  ██████╗██████╗     ██╗  ██╗    ███████╗████████╗ █████╗ ██████╗
 ██╔════╝██╔══██╗   ██╔╝  ╚██╗   ██╔════╝╚══██╔══╝██╔══██╗██╔══██╗
 ██║     ██████╔╝  ██╔╝    ╚██╗  ███████╗   ██║   ███████║██████╔╝
 ██║     ██╔═══╝  ╚██╗    ██╔╝  ╚════██║   ██║   ██╔══██║██╔══██╗
 ╚██████╗██║       ╚██╗  ██╔╝   ███████║   ██║   ██║  ██║██║  ██║
  ╚═════╝╚═╝        ╚═╝  ╚═╝    ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
"""

SHORT_BANNER = f"  CP+* {VERSION} ({VERSION_NAME})"


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _read_source(filepath: str) -> Optional[str]:
    if not os.path.exists(filepath):
        print(f"❌ File không tìm thấy: {filepath!r}", file=sys.stderr)
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except PermissionError:
        print(f"❌ Không có quyền đọc file: {filepath}", file=sys.stderr)
        return None
    except UnicodeDecodeError:
        print(f"❌ File không phải UTF-8: {filepath}", file=sys.stderr)
        return None


def _lex_and_parse(source: str, filepath: str, strict: bool = False):
    config = LexerConfig(strict_mode=strict)
    lexer = Lexer(source, filepath, config)
    tokens = lexer.tokenize()
    parser = Parser(tokens, filepath)
    ast = parser.parse()
    return lexer, parser, ast


# ══════════════════════════════════════════════════════════════════════════════
# `cpps run` — execute a program
# ══════════════════════════════════════════════════════════════════════════════

def cmd_run(args) -> int:
    if args.eval is not None:
        return _run_eval(args.eval, args)
    if not args.file:
        return cmd_repl(args)

    source = _read_source(args.file)
    if source is None:
        return 1

    if args.verbose:
        print(f"[cpps] Đang chạy: {args.file}")
        print(f"[cpps] Kích thước: {len(source)} ký tự, {source.count(chr(10)) + 1} dòng")

    lexer, parser, ast = _lex_and_parse(source, args.file, strict=args.strict)

    if args.stats:
        print("\n=== Lexer Statistics ===")
        print(lexer.stats.summary())

    if lexer.errors:
        print(f"\n⚠️  {len(lexer.errors)} lexer errors:", file=sys.stderr)
        for err in lexer.errors[:5]:
            print(f"  {err}", file=sys.stderr)
        if not args.verbose:
            return 1

    if parser.errors:
        print_parse_errors(parser.errors, args.file, source)
        return 1

    if args.ast:
        _show_ast(source, args.file, args.verbose)
        return 0
    if args.tokens:
        _show_tokens(source, args.file)
        return 0

    interp = Interpreter(verbose=args.verbose, max_depth=args.max_depth)
    t0 = time.perf_counter()
    try:
        exit_code = interp.execute(ast)
    except KeyboardInterrupt:
        print("\n  Bị ngắt bởi người dùng", file=sys.stderr)
        return 130
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        print(f"\n❌ Lỗi nghiêm trọng: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1
    elapsed = time.perf_counter() - t0

    if args.time:
        print(f"\n⏱ Thời gian thực thi: {elapsed * 1000:.3f}ms")
    if args.verbose:
        print(f"\n[cpps] Hoàn thành trong {elapsed * 1000:.1f}ms, exit code: {exit_code}")
    return exit_code


def _run_eval(code: str, args) -> int:
    if args.verbose:
        print(f"[eval] Chạy: {code!r}")
    try:
        lexer, parser, ast = _lex_and_parse(code, '<eval>', strict=args.strict)
        if parser.errors:
            print_parse_errors(parser.errors, '<eval>', code)
            return 1
        if args.ast:
            _show_ast(code, '<eval>', args.verbose)
            return 0
        if args.tokens:
            _show_tokens(code, '<eval>')
            return 0
        t0 = time.perf_counter()
        interp = Interpreter(verbose=args.verbose, max_depth=args.max_depth)
        exit_code = interp.execute(ast)
        elapsed = time.perf_counter() - t0
        if args.time:
            print(f"\n⏱ Thời gian: {elapsed * 1000:.3f}ms")
        return exit_code
    except KeyboardInterrupt:
        print("\n  Bị ngắt", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def _show_ast(source: str, filename: str, verbose: bool = False) -> None:
    print(f"  {'─' * 56}")
    print(f"  AST cho: {filename}")
    print(f"  {'─' * 56}")
    try:
        lexer = Lexer(source, filename)
        tokens = lexer.tokenize()
        parser = Parser(tokens, filename)
        ast = parser.parse()
        printer = ASTPrinter(indent=2)
        print(printer.print(ast))
        print(f"\n  Thống kê:")
        print(f"  - Tokens: {len(tokens)}")
        print(f"  - Statements: {len(ast.statements)}")
        print(f"  - Parser errors: {len(parser.errors)}")
        if parser.errors:
            print_parse_errors(parser.errors, filename, source)
    except Exception as e:
        print(f"❌ Lỗi khi parse: {e}")
        if verbose:
            traceback.print_exc()


def _show_tokens(source: str, filename: str) -> None:
    print(f"  {'─' * 60}")
    print(f"  Tokens cho: {filename}")
    print(f"  {'─' * 60}")
    print(f"  {'#':<5} {'Dòng':<6} {'Cột':<5} {'Loại':<22} {'Giá trị'}")
    print(f"  {'─' * 60}")
    try:
        lexer = Lexer(source, filename)
        tokens = lexer.tokenize()
        for i, tok in enumerate(tokens):
            val_str = repr(tok.value)
            if len(val_str) > 30:
                val_str = val_str[:27] + '...'
            print(f"  {i:<5} {tok.line:<6} {tok.column:<5} {tok.type.name:<22} {val_str}")
        print(f"  {'─' * 60}")
        print(f"  Tổng: {len(tokens)} tokens")
        print(f"  Lexer stats: {lexer.stats.identifiers_parsed} identifiers, "
              f"{lexer.stats.keywords_found} keywords, "
              f"{lexer.stats.numbers_parsed} numbers, "
              f"{lexer.stats.strings_parsed} strings")
    except Exception as e:
        print(f"❌ Lỗi khi tokenize: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# `cpps build` — lex/parse/lint + lower to groundwork IR
# ══════════════════════════════════════════════════════════════════════════════

def cmd_build(args) -> int:
    source = _read_source(args.file)
    if source is None:
        return 1

    lexer, parser, ast = _lex_and_parse(source, args.file, strict=args.strict)
    if lexer.errors:
        print(f"⚠️  {len(lexer.errors)} lexer errors:", file=sys.stderr)
        for err in lexer.errors[:5]:
            print(f"  {err}", file=sys.stderr)
        return 1
    if parser.errors:
        print_parse_errors(parser.errors, args.file, source)
        return 1

    print(f"[build] {args.file}: lex+parse OK ({len(ast.statements)} top-level statements)")

    bag = lint_source(ast, args.file, source)
    if bag.diagnostics:
        bag.print_all()
        if bag.has_errors and not args.allow_warnings:
            return 1

    ir_program = ir_lower(ast)
    out_path = args.output or os.path.splitext(args.file)[0] + '.cpir'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(ir_program.to_json())
    print(f"[build] wrote groundwork bytecode IR -> {out_path}")

    if ir_program.unsupported:
        uniq = sorted(set(ir_program.unsupported))
        print(f"[build] note: {len(uniq)} construct kind(s) fell back to interpreter-only "
              f"execution (not represented in the IR): {', '.join(uniq)}")

    if args.emit_text:
        text_path = os.path.splitext(out_path)[0] + '.ir.txt'
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(ir_program.dump_text())
        print(f"[build] wrote human-readable IR listing -> {text_path}")

    if args.run_ir:
        print(f"[build] executing IR via bytecode VM (groundwork subset only)...")
        try:
            vm = IRInterpreter(ir_program)
            vm.run()
        except IRRuntimeError as e:
            print(f"❌ IR VM error: {e}", file=sys.stderr)
            print("   (this usually means the program uses a construct outside the "
                  "IR groundwork subset — run it with `cpps run` for full semantics)",
                  file=sys.stderr)
            return 1
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# `cpps fmt` — canonical source formatter
# ══════════════════════════════════════════════════════════════════════════════

def cmd_fmt(args) -> int:
    files = args.files or []
    if not files:
        print("❌ Cần ít nhất một file .cpps", file=sys.stderr)
        return 1

    exit_code = 0
    for filepath in files:
        source = _read_source(filepath)
        if source is None:
            exit_code = 1
            continue
        _, parser, ast = _lex_and_parse(source, filepath)
        if parser.errors:
            print_parse_errors(parser.errors, filepath, source)
            exit_code = 1
            continue
        formatted = format_source(ast)
        if args.check:
            if formatted != source:
                print(f"[fmt] {filepath}: would reformat")
                exit_code = 1
            else:
                print(f"[fmt] {filepath}: already formatted")
            continue
        if formatted == source:
            print(f"[fmt] {filepath}: unchanged")
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(formatted)
            print(f"[fmt] {filepath}: reformatted")
    return exit_code


# ══════════════════════════════════════════════════════════════════════════════
# `cpps lint` — static analysis
# ══════════════════════════════════════════════════════════════════════════════

def cmd_lint(args) -> int:
    files = args.files or []
    if not files:
        print("❌ Cần ít nhất một file .cpps", file=sys.stderr)
        return 1

    total_warnings = 0
    total_errors = 0
    for filepath in files:
        source = _read_source(filepath)
        if source is None:
            total_errors += 1
            continue
        _, parser, ast = _lex_and_parse(source, filepath)
        if parser.errors:
            print_parse_errors(parser.errors, filepath, source)
            total_errors += len(parser.errors)
            continue
        bag = lint_source(ast, filepath, source)
        if bag.diagnostics:
            bag.print_all()
        else:
            print(f"[lint] {filepath}: no issues found")
        total_warnings += bag.warning_count
        total_errors += bag.error_count

    print(f"\n[lint] {total_errors} error(s), {total_warnings} warning(s) across {len(files)} file(s)")
    return 1 if total_errors else 0


# ══════════════════════════════════════════════════════════════════════════════
# `cpps test` — discover and run *_test.cpps files
# ══════════════════════════════════════════════════════════════════════════════

def cmd_test(args) -> int:
    root = args.path or '.'
    if os.path.isfile(root):
        candidates = [root]
    else:
        candidates = sorted(glob.glob(os.path.join(root, '**', '*_test.cpps'), recursive=True))
        candidates += sorted(glob.glob(os.path.join(root, '**', 'test_*.cpps'), recursive=True))
        candidates = sorted(set(candidates))

    if not candidates:
        print(f"[test] no `*_test.cpps` / `test_*.cpps` files found under {root!r}")
        return 0

    passed = 0
    failed = 0
    t0 = time.perf_counter()
    for filepath in candidates:
        source = _read_source(filepath)
        if source is None:
            failed += 1
            continue
        _, parser, ast = _lex_and_parse(source, filepath)
        if parser.errors:
            print(f"FAIL  {filepath}  (parse error)")
            print_parse_errors(parser.errors, filepath, source)
            failed += 1
            continue
        interp = Interpreter(verbose=False, max_depth=args.max_depth)
        case_t0 = time.perf_counter()
        try:
            exit_code = interp.execute(ast)
            elapsed = (time.perf_counter() - case_t0) * 1000
            if exit_code == 0:
                print(f"PASS  {filepath}  ({elapsed:.1f}ms)")
                passed += 1
            else:
                print(f"FAIL  {filepath}  (exit code {exit_code}, {elapsed:.1f}ms)")
                failed += 1
        except Exception as e:
            elapsed = (time.perf_counter() - case_t0) * 1000
            print(f"FAIL  {filepath}  ({elapsed:.1f}ms): {e}")
            if args.verbose:
                traceback.print_exc()
            failed += 1

    total_elapsed = time.perf_counter() - t0
    print(f"\n[test] {passed} passed, {failed} failed, {len(candidates)} total "
          f"({total_elapsed * 1000:.1f}ms)")
    return 1 if failed else 0


# ══════════════════════════════════════════════════════════════════════════════
# `cpps bench` — benchmark execution time
# ══════════════════════════════════════════════════════════════════════════════

def cmd_bench(args) -> int:
    source = _read_source(args.file)
    if source is None:
        return 1
    _, parser, ast = _lex_and_parse(source, args.file)
    if parser.errors:
        print_parse_errors(parser.errors, args.file, source)
        return 1

    iterations = args.iterations
    times: List[float] = []
    print(f"[bench] {args.file}: {iterations} iteration(s)")
    for i in range(iterations):
        interp = Interpreter(verbose=False, max_depth=args.max_depth)
        t0 = time.perf_counter()
        try:
            interp.execute(ast)
        except Exception as e:
            print(f"❌ lỗi ở iteration {i + 1}: {e}", file=sys.stderr)
            return 1
        times.append((time.perf_counter() - t0) * 1000)

    times.sort()
    n = len(times)
    mean = sum(times) / n
    median = times[n // 2] if n % 2 else (times[n // 2 - 1] + times[n // 2]) / 2
    print(f"  min:    {times[0]:.3f}ms")
    print(f"  max:    {times[-1]:.3f}ms")
    print(f"  mean:   {mean:.3f}ms")
    print(f"  median: {median:.3f}ms")
    if n >= 20:
        p95 = times[int(n * 0.95)]
        print(f"  p95:    {p95:.3f}ms")
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# `cpps doc` — extract `--` doc comments to Markdown
# ══════════════════════════════════════════════════════════════════════════════

def cmd_doc(args) -> int:
    root = args.path or '.'
    files = [root] if os.path.isfile(root) else sorted(glob.glob(os.path.join(root, '**', '*.cpps'), recursive=True))
    if not files:
        print(f"❌ Không tìm thấy file .cpps nào trong {root!r}", file=sys.stderr)
        return 1

    out_lines = [f"# CP+* API Documentation", ""]
    documented = 0
    for filepath in files:
        source = _read_source(filepath)
        if source is None:
            continue
        _, parser, ast = _lex_and_parse(source, filepath)
        if parser.errors:
            continue
        entries = []
        for stmt in ast.statements:
            entries.extend(_doc_entries(stmt))
        if entries:
            out_lines.append(f"## {filepath}")
            out_lines.append("")
            for kind, name, sig, doc in entries:
                out_lines.append(f"### `{kind} {name}`")
                out_lines.append("")
                out_lines.append(f"```")
                out_lines.append(sig)
                out_lines.append(f"```")
                out_lines.append("")
                if doc:
                    out_lines.append(doc)
                    out_lines.append("")
                documented += 1

    output = '\n'.join(out_lines)
    out_path = args.output or 'DOCS.md'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"[doc] documented {documented} item(s) from {len(files)} file(s) -> {out_path}")
    return 0


def _doc_entries(stmt):
    entries = []
    if isinstance(stmt, FnDef):
        params = ', '.join(f'{p[0]}: {p[1]}' for p in stmt.params)
        sig = f"++ {stmt.name} <~ ({params}) -> {stmt.return_type}"
        entries.append(('fn', stmt.name, sig, getattr(stmt, 'doc', None)))
    elif isinstance(stmt, ClassDef):
        parents = f' : {", ".join(stmt.parents)}' if stmt.parents else ''
        sig = f"class {stmt.name}{parents}"
        entries.append(('class', stmt.name, sig, getattr(stmt, 'doc', None)))
        for m in stmt.body:
            entries.extend(_doc_entries(m))
    elif isinstance(stmt, StructDef):
        fields = ', '.join(f'{f[0]}: {f[1]}' for f in stmt.fields)
        sig = f"struct {stmt.name} {{ {fields} }}"
        entries.append(('struct', stmt.name, sig, getattr(stmt, 'doc', None)))
    elif isinstance(stmt, TraitDef):
        sig = f"trait {stmt.name}"
        entries.append(('trait', stmt.name, sig, getattr(stmt, 'doc', None)))
    return entries


# ══════════════════════════════════════════════════════════════════════════════
# `cpps package` — bundle project into a distributable .zip
# ══════════════════════════════════════════════════════════════════════════════

def cmd_package(args) -> int:
    root = args.path or '.'
    out_path = args.output or 'cpps-package.zip'
    skip_dirs = {'.git', '__pycache__', 'dist', 'build', '.pytest_cache'}
    count = 0
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if fn.endswith(('.cpps', '.cpir', '.md', '.txt')) or fn == 'manifest.json':
                    full = os.path.join(dirpath, fn)
                    arcname = os.path.relpath(full, root)
                    zf.write(full, arcname)
                    count += 1
    print(f"[package] wrote {count} file(s) -> {out_path}")
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# `cpps clean` — remove build/doc/package artifacts
# ══════════════════════════════════════════════════════════════════════════════

def cmd_clean(args) -> int:
    root = args.path or '.'
    patterns = ['**/*.cpir', '**/*.ir.txt', '**/__pycache__']
    removed = 0
    for pattern in patterns:
        for path in glob.glob(os.path.join(root, pattern), recursive=True):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                removed += 1
                if args.verbose:
                    print(f"[clean] removed {path}")
            except OSError as e:
                print(f"⚠️  không thể xóa {path}: {e}", file=sys.stderr)
    print(f"[clean] removed {removed} artifact(s)")
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# `cpps repl` — interactive REPL
# ══════════════════════════════════════════════════════════════════════════════

REPL_HELP = """
Lệnh REPL đặc biệt:
  :help, :h          Hiện trợ giúp này
  :quit, :q, :exit   Thoát REPL
  :clear, :c         Xóa màn hình
  :reset             Reset interpreter (xóa tất cả biến)
  :env               Hiện tất cả biến trong scope
  :ast <code>        Hiện AST của code
  :tokens <code>     Hiện tokens của code
  :time <code>       Đo thời gian evaluate
  :type <expr>       Hiện kiểu dữ liệu
  :load <file>       Load và chạy file .cpps

Phím tắt:
  Ctrl+C             Ngắt lệnh hiện tại
  Ctrl+D             Thoát REPL
"""


def cmd_repl(args) -> int:
    show_banner = not getattr(args, 'no_banner', False)
    verbose = getattr(args, 'verbose', False)
    max_depth = getattr(args, 'max_depth', 1000)

    if show_banner:
        print(BANNER)
        print(SHORT_BANNER)
        print(f"  Python {sys.version.split()[0]} — Gõ ':help' để xem trợ giúp, ':quit' để thoát")
        print("  " + "─" * 54)
        print()

    interp = Interpreter(verbose=verbose, max_depth=max_depth)

    def show_env():
        print("\n📦 Biến trong scope hiện tại:")
        for name in sorted(interp.global_env.local_names()):
            val = interp.global_env.get(name)
            if callable(val) and not isinstance(val, type):
                print(f"  {name:<20} : <function>")
            else:
                from interpreter import _display, _type_of
                type_str = _type_of(val)
                val_str = _display(val)
                if len(val_str) > 50:
                    val_str = val_str[:47] + '...'
                print(f"  {name:<20} : {type_str:<12} = {val_str}")
        print()

    multiline_buffer: List[str] = []
    in_multiline = False

    while True:
        try:
            prompt = "...  " if in_multiline else "cpps> "
            try:
                line = input(prompt)
            except EOFError:
                print("\n👋 Tạm biệt!")
                break
            except KeyboardInterrupt:
                print()
                if in_multiline:
                    multiline_buffer = []
                    in_multiline = False
                continue

            if not line.strip():
                if in_multiline:
                    multiline_buffer.append(line)
                continue

            stripped = line.strip()

            if stripped in (':quit', ':q', ':exit', ':bye'):
                print("👋 Tạm biệt!")
                break
            if stripped in (':help', ':h'):
                print(REPL_HELP)
                continue
            if stripped in (':clear', ':c'):
                os.system('clear' if os.name == 'posix' else 'cls')
                continue
            if stripped == ':reset':
                interp = Interpreter(verbose=verbose, max_depth=max_depth)
                print("✅ Interpreter đã reset")
                continue
            if stripped == ':env':
                show_env()
                continue
            if stripped.startswith(':ast '):
                _show_ast(stripped[5:], '<repl>')
                continue
            if stripped.startswith(':tokens '):
                _show_tokens(stripped[8:], '<repl>')
                continue
            if stripped.startswith(':time '):
                code = stripped[6:]
                t0 = time.perf_counter()
                try:
                    result = interp.eval_expr(code)
                    elapsed = time.perf_counter() - t0
                    from interpreter import _display
                    print(f"⏱ {elapsed * 1000:.3f}ms → {_display(result)!r}")
                except Exception as e:
                    print(f"❌ {e}")
                continue
            if stripped.startswith(':type '):
                code = stripped[6:]
                try:
                    result = interp.eval_expr(code)
                    from interpreter import _type_of, _display
                    print(f"  {_type_of(result)} = {_display(result)}")
                except Exception as e:
                    print(f"❌ {e}")
                continue
            if stripped.startswith(':load '):
                filepath = stripped[6:].strip()
                source = _read_source(filepath)
                if source is None:
                    continue
                try:
                    t0 = time.perf_counter()
                    interp.run_source(source, filepath)
                    elapsed = time.perf_counter() - t0
                    print(f"✅ Đã load '{filepath}' ({elapsed * 1000:.1f}ms)")
                except Exception as e:
                    print(f"❌ Lỗi khi load: {e}")
                continue

            if stripped.endswith('{') or stripped.endswith('**') or stripped.endswith(','):
                multiline_buffer.append(line)
                in_multiline = True
                continue

            if in_multiline:
                multiline_buffer.append(line)
                if stripped == '}' or stripped.endswith('}'):
                    code = '\n'.join(multiline_buffer)
                    multiline_buffer = []
                    in_multiline = False
                else:
                    continue
            else:
                code = line

            t0 = time.perf_counter()
            try:
                interp.run_source(code, '<repl>')
                elapsed = time.perf_counter() - t0
                if verbose:
                    print(f"  ⏱ {elapsed * 1000:.2f}ms")
            except KeyboardInterrupt:
                print("\n  ⚠️  Bị ngắt")
            except Exception as e:
                print(f"❌ {e}")
                if verbose:
                    traceback.print_exc()

        except KeyboardInterrupt:
            print("\n  Ctrl+C — gõ ':quit' để thoát")
            continue
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# ARGUMENT PARSING
# ══════════════════════════════════════════════════════════════════════════════

def _add_common_exec_args(p: argparse.ArgumentParser) -> None:
    p.add_argument('--verbose', '-v', action='store_true', help='Verbose output (debug info)')
    p.add_argument('--strict', action='store_true', help='Chế độ strict (lỗi thay vì warning)')
    p.add_argument('--time', action='store_true', help='Đo thời gian thực thi')
    p.add_argument('--max-depth', type=int, default=1000, metavar='N',
                    help='Độ sâu call stack tối đa (mặc định: 1000)')
    p.add_argument('--ast', action='store_true', help='Hiện Abstract Syntax Tree thay vì chạy')
    p.add_argument('--tokens', action='store_true', help='Hiện danh sách tokens thay vì chạy')
    p.add_argument('--stats', action='store_true', help='Hiện thống kê lexer/parser')


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='cpps',
        description=f'CP+* (C-Plus-Plus-Star) Language Toolchain v{VERSION}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--version', '-V', action='store_true', help='Hiện thông tin version')

    sub = parser.add_subparsers(dest='command')

    p_run = sub.add_parser('run', help='Chạy một file .cpps')
    p_run.add_argument('file', nargs='?', help='File .cpps cần chạy')
    p_run.add_argument('-e', '--eval', metavar='CODE', help='Chạy code CP+* trực tiếp')
    _add_common_exec_args(p_run)

    p_build = sub.add_parser('build', help='Lex/parse/lint + lower sang bytecode IR (groundwork)')
    p_build.add_argument('file', help='File .cpps cần build')
    p_build.add_argument('-o', '--output', help='Đường dẫn file .cpir đầu ra')
    p_build.add_argument('--emit-text', action='store_true', help='Ghi thêm bản IR dạng text đọc được')
    p_build.add_argument('--run-ir', action='store_true', help='Chạy chương trình bằng bytecode VM sau khi build')
    p_build.add_argument('--allow-warnings', action='store_true', help='Không fail build khi chỉ có warning')
    p_build.add_argument('--strict', action='store_true')

    p_fmt = sub.add_parser('fmt', help='Định dạng lại file .cpps theo chuẩn')
    p_fmt.add_argument('files', nargs='+', help='File(s) .cpps cần định dạng')
    p_fmt.add_argument('--check', action='store_true', help='Chỉ kiểm tra, không ghi đè file')

    p_lint = sub.add_parser('lint', help='Phân tích tĩnh: biến không dùng, code chết, v.v.')
    p_lint.add_argument('files', nargs='+', help='File(s) .cpps cần lint')

    p_test = sub.add_parser('test', help='Tìm và chạy các file *_test.cpps')
    p_test.add_argument('path', nargs='?', help='Thư mục hoặc file để tìm test (mặc định: .)')
    p_test.add_argument('--verbose', '-v', action='store_true')
    p_test.add_argument('--max-depth', type=int, default=1000, metavar='N')

    p_bench = sub.add_parser('bench', help='Đo benchmark thời gian thực thi')
    p_bench.add_argument('file', help='File .cpps cần benchmark')
    p_bench.add_argument('-n', '--iterations', type=int, default=10, help='Số lần lặp (mặc định: 10)')
    p_bench.add_argument('--max-depth', type=int, default=1000, metavar='N')

    p_doc = sub.add_parser('doc', help='Trích xuất doc comment (--) thành Markdown')
    p_doc.add_argument('path', nargs='?', help='Thư mục hoặc file (mặc định: .)')
    p_doc.add_argument('-o', '--output', help='File Markdown đầu ra (mặc định: DOCS.md)')

    p_package = sub.add_parser('package', help='Đóng gói project thành file .zip')
    p_package.add_argument('path', nargs='?', help='Thư mục project (mặc định: .)')
    p_package.add_argument('-o', '--output', help='File .zip đầu ra (mặc định: cpps-package.zip)')

    p_clean = sub.add_parser('clean', help='Xóa artifact build/doc/package (*.cpir, *.ir.txt, __pycache__)')
    p_clean.add_argument('path', nargs='?', help='Thư mục project (mặc định: .)')
    p_clean.add_argument('--verbose', '-v', action='store_true')

    p_repl = sub.add_parser('repl', help='Khởi động REPL tương tác')
    p_repl.add_argument('--no-banner', action='store_true')
    p_repl.add_argument('--verbose', '-v', action='store_true')
    p_repl.add_argument('--max-depth', type=int, default=1000, metavar='N')

    return parser


COMMANDS = {
    'run': cmd_run,
    'build': cmd_build,
    'fmt': cmd_fmt,
    'lint': cmd_lint,
    'test': cmd_test,
    'bench': cmd_bench,
    'doc': cmd_doc,
    'package': cmd_package,
    'clean': cmd_clean,
    'repl': cmd_repl,
}


def main() -> int:
    argv = sys.argv[1:]
    parser = build_arg_parser()

    # Back-compat: `cpps file.cpps [flags]` / `cpps -e code` / bare `cpps` -> REPL,
    # without requiring the explicit `run`/`repl` subcommand.
    if not argv:
        return cmd_repl(argparse.Namespace(no_banner=False, verbose=False, max_depth=1000))

    if argv[0] not in COMMANDS and argv[0] not in ('-h', '--help', '-V', '--version'):
        argv = ['run'] + argv

    args = parser.parse_args(argv)

    if args.version:
        print(f"{LANGUAGE_NAME} v{VERSION} ({VERSION_NAME})")
        print(f"Interpreter: Python {sys.version.split()[0]}")
        print(f"Build: {BUILD_DATE}")
        print(f"Yêu cầu Python: {PYTHON_REQUIRED}")
        return 0

    if not args.command:
        return cmd_repl(argparse.Namespace(no_banner=False, verbose=False, max_depth=1000))

    handler = COMMANDS[args.command]
    return handler(args)


if __name__ == '__main__':
    sys.exit(main())
