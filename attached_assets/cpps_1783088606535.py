#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CP+* (C-Plus-Plus-Star) Language Interpreter                               ║
║  File: cpps.py — Entry Point                                                 ║
║  Version: 2.0 — Advanced Edition                                             ║
║                                                                              ║
║  Sử dụng:                                                                    ║
║    python cpps.py hello.cpps                — Chạy file                      ║
║    python cpps.py hello.cpps --verbose      — Chạy với debug info            ║
║    python cpps.py                           — Khởi động REPL                 ║
║    python cpps.py --repl                    — Khởi động REPL (tường minh)   ║
║    python cpps.py --version                 — Hiện version                   ║
║    python cpps.py --help                    — Hiện help                      ║
║    python cpps.py --ast hello.cpps          — Hiện AST                      ║
║    python cpps.py --tokens hello.cpps       — Hiện tokens                   ║
║    python cpps.py -e 'x := 42; println(x)' — Chạy một-dòng                ║
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

  Ví dụ class:
    class Dog : Animal -> {
        name :: mut string = ""
        ++ new <~ (n: string) ** { @.name = n }
        @@override
        ++ speak <~ () -> void ** {
            ~> io::println("{} says: Woof!", @.name)
        }
    }

  Ví dụ pattern matching:
    ?~ score {
        90..=100 => { ~> io::println("Xuất sắc!") },
        70..89   => { ~> io::println("Tốt") },
        _        => { ~> io::println("Cần cố gắng") }
    }
"""

import sys
import os
import time
import traceback
import argparse
from typing import Optional

# Add src/ to path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = '/storage/emulated/0/cpps-native/src'
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Import after path setup
from lexer import Lexer, tokenize, LexerConfig
from parser import Parser, parse, ASTPrinter
from interpreter import Interpreter, run, run_file


# ══════════════════════════════════════════════════════════════════════════════
# VERSION INFORMATION
# ══════════════════════════════════════════════════════════════════════════════

VERSION = "2.0.0"
VERSION_NAME = "Advanced Edition"
LANGUAGE_NAME = "CP+*"
BUILD_DATE = "2025"
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

HELP_TEXT = f"""
CP+* (C-Plus-Plus-Star) Language Interpreter v{VERSION}
{'=' * 56}

Cú pháp:
  cpps <file.cpps>          Chạy file CP+*
  cpps <file.cpps> -v       Chạy với verbose/debug output
  cpps                      Khởi động chế độ REPL
  cpps --repl               Khởi động REPL (tường minh)
  cpps -e '<code>'          Chạy code trực tiếp
  cpps --ast <file>         Hiện AST của file
  cpps --tokens <file>      Hiện danh sách tokens
  cpps --version            Hiện thông tin version
  cpps --help               Hiện trợ giúp này

Cú pháp CP+* cơ bản:
  name := expr              Khai báo biến bất biến
  name :: mut Type = expr   Khai báo biến mutable
  ++ fn_name <~ (p: T) -> R ** {{ body }}   Hàm
  ?? condition ** {{ }}     Điều kiện if
  <> var :: iterable ** {{ }}  Vòng lặp for
  while cond ** {{ }}       Vòng lặp while
  ?~ value {{ arm => body }} Pattern matching
  ~> io::println("msg")    In ra màn hình
  <- value                  Return
  !! "error"                Panic
  go coroutine()            Goroutine

Ví dụ:
  ~> io::println("Hello, World!")
  x := 42
  ~> io::println("x = {{}}", x)
  ++ add <~ (a: int, b: int) -> int ** {{
      <- a + b
  }}

Files ví dụ:
  examples/hello.cpps       Hello World và cơ bản
  examples/game.cpps        Game số học đoán số
  examples/calculator.cpps  Máy tính đa năng
  examples/advanced.cpps    Tính năng nâng cao (OOP, patterns, concurrency)
"""


# ══════════════════════════════════════════════════════════════════════════════
# ARGUMENT PARSING
# ══════════════════════════════════════════════════════════════════════════════

def build_arg_parser() -> argparse.ArgumentParser:
    """Xây dựng argument parser cho CLI."""
    parser = argparse.ArgumentParser(
        prog='cpps',
        description=f'CP+* (C-Plus-Plus-Star) Language Interpreter v{VERSION}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cpps hello.cpps               Chạy file hello.cpps
  cpps hello.cpps --verbose     Chạy với debug output
  cpps --repl                   Khởi động REPL
  cpps -e 'x := 42'             Chạy code inline
  cpps --ast hello.cpps         Hiện AST

Cú pháp CP+* nhanh:
  x := 42                       Biến bất biến
  y :: mut int = 0              Biến mutable
  ++ fn <~ (a: int) -> int **   Định nghĩa hàm
  ?? x > 0 ** { ... }           If
  <> i :: list ** { ... }       For loop
  ?~ value { pat => body }      Pattern match
  ~> io::println("Hello")       Print
  <- value                      Return
""",
        add_help=False,
    )

    # Positional
    parser.add_argument(
        'file',
        nargs='?',
        help='File .cpps cần chạy'
    )

    # Modes
    mode_group = parser.add_argument_group('Chế độ')
    mode_group.add_argument(
        '--repl', '-r',
        action='store_true',
        help='Khởi động chế độ REPL'
    )
    mode_group.add_argument(
        '-e', '--eval',
        metavar='CODE',
        help='Chạy code CP+* trực tiếp'
    )
    mode_group.add_argument(
        '--ast',
        action='store_true',
        help='Hiện Abstract Syntax Tree'
    )
    mode_group.add_argument(
        '--tokens',
        action='store_true',
        help='Hiện danh sách tokens'
    )
    mode_group.add_argument(
        '--stats',
        action='store_true',
        help='Hiện thống kê lexer/parser'
    )

    # Options
    opt_group = parser.add_argument_group('Tùy chọn')
    opt_group.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output (debug info)'
    )
    opt_group.add_argument(
        '--no-banner',
        action='store_true',
        help='Không hiện banner trong REPL'
    )
    opt_group.add_argument(
        '--strict',
        action='store_true',
        help='Chế độ strict (lỗi thay vì warning)'
    )
    opt_group.add_argument(
        '--time',
        action='store_true',
        help='Đo thời gian thực thi'
    )
    opt_group.add_argument(
        '--max-depth',
        type=int,
        default=1000,
        metavar='N',
        help='Độ sâu call stack tối đa (mặc định: 1000)'
    )

    # Meta
    meta_group = parser.add_argument_group('Thông tin')
    meta_group.add_argument(
        '--version', '-V',
        action='store_true',
        help='Hiện thông tin version'
    )
    meta_group.add_argument(
        '--help', '-h',
        action='store_true',
        help='Hiện trợ giúp'
    )

    return parser


# ══════════════════════════════════════════════════════════════════════════════
# REPL
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
  :doc <name>        Hiện documentation
  :load <file>       Load và chạy file .cpps
  :save <file>       Lưu session history

Phím tắt:
  Ctrl+C             Ngắt lệnh hiện tại
  Ctrl+D             Thoát REPL
  ↑/↓               Duyệt history
"""

def start_repl(verbose: bool = False, show_banner: bool = True, max_depth: int = 1000):
    """
    Khởi động REPL (Read-Eval-Print Loop) của CP+*.

    Args:
        verbose: Chế độ verbose
        show_banner: Hiện banner khi khởi động
        max_depth: Độ sâu call stack tối đa
    """
    if show_banner:
        print(BANNER)
        print(SHORT_BANNER)
        print(f"  Python {sys.version.split()[0]} — Gõ ':help' để xem trợ giúp, ':quit' để thoát")
        print("  " + "─" * 54)
        print()

    interp = Interpreter(verbose=verbose, max_depth=max_depth)
    history = []
    session_source = []

    def show_repl_help():
        print(REPL_HELP)

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

    multiline_buffer = []
    in_multiline = False

    while True:
        try:
            if in_multiline:
                prompt = "...  "
            else:
                prompt = "cpps> "

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

            # Empty line
            if not line.strip():
                if in_multiline:
                    multiline_buffer.append(line)
                continue

            # REPL commands
            stripped = line.strip()

            if stripped in (':quit', ':q', ':exit', ':bye'):
                print("👋 Tạm biệt!")
                break

            if stripped in (':help', ':h'):
                show_repl_help()
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
                code = stripped[5:]
                try:
                    tokens = tokenize(code, '<repl>')
                    ast = Parser(tokens, '<repl>').parse()
                    printer = ASTPrinter()
                    print(printer.print(ast))
                except Exception as e:
                    print(f"❌ Lỗi: {e}")
                continue

            if stripped.startswith(':tokens '):
                code = stripped[8:]
                try:
                    tokens = tokenize(code, '<repl>')
                    for t in tokens[:-1]:  # skip EOF
                        print(f"  {t.type.name:<20} {t.value!r}")
                except Exception as e:
                    print(f"❌ Lỗi: {e}")
                continue

            if stripped.startswith(':time '):
                code = stripped[6:]
                t0 = time.perf_counter()
                try:
                    result = interp.eval_expr(code)
                    elapsed = time.perf_counter() - t0
                    from interpreter import _display
                    print(f"⏱ {elapsed*1000:.3f}ms → {_display(result)!r}")
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
                if not os.path.exists(filepath):
                    print(f"❌ File không tìm thấy: {filepath}")
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    t0 = time.perf_counter()
                    interp.run_source(source, filepath)
                    elapsed = time.perf_counter() - t0
                    print(f"✅ Đã load '{filepath}' ({elapsed*1000:.1f}ms)")
                except Exception as e:
                    print(f"❌ Lỗi khi load: {e}")
                continue

            # Multiline detection: ends with { or **
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

            # Add to history
            history.append(code)
            session_source.append(code)

            # Execute
            t0 = time.perf_counter()
            try:
                interp.run_source(code, '<repl>')
                elapsed = time.perf_counter() - t0
                if verbose:
                    print(f"  ⏱ {elapsed*1000:.2f}ms")
            except KeyboardInterrupt:
                print("\n  ⚠️  Bị ngắt")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                print(f"❌ {e}")
                if verbose:
                    traceback.print_exc()

        except KeyboardInterrupt:
            print("\n  Ctrl+C — gõ ':quit' để thoát")
            continue


# ══════════════════════════════════════════════════════════════════════════════
# SHOW AST
# ══════════════════════════════════════════════════════════════════════════════

def show_ast(source: str, filename: str = '<unknown>', verbose: bool = False) -> None:
    """
    Parse và hiện AST của source code.

    Args:
        source: Source code
        filename: Tên file
        verbose: Verbose mode
    """
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

        if verbose or True:
            print(f"\n  Thống kê:")
            print(f"  - Tokens: {len(tokens)}")
            print(f"  - Statements: {len(ast.statements)}")
            print(f"  - Parser errors: {len(parser.errors)}")
            if parser.errors:
                print("\n  Lỗi parser:")
                for err in parser.errors[:5]:
                    print(f"  - {err}")

    except Exception as e:
        print(f"❌ Lỗi khi parse: {e}")
        if verbose:
            traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# SHOW TOKENS
# ══════════════════════════════════════════════════════════════════════════════

def show_tokens(source: str, filename: str = '<unknown>') -> None:
    """
    Tokenize và hiện danh sách tokens.

    Args:
        source: Source code
        filename: Tên file
    """
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
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """
    Entry point chính của CP+* interpreter.

    Returns:
        Exit code (0 = success)
    """
    # Parse arguments
    arg_parser = build_arg_parser()

    try:
        args, remaining = arg_parser.parse_known_args()
    except SystemExit:
        return 1

    # --help
    if args.help or (not args.file and not args.eval and not args.repl
                     and not args.version and '-h' in sys.argv):
        print(HELP_TEXT)
        return 0

    # --version
    if args.version:
        print(f"{LANGUAGE_NAME} v{VERSION} ({VERSION_NAME})")
        print(f"Interpreter: Python {sys.version.split()[0]}")
        print(f"Build: {BUILD_DATE}")
        print(f"Yêu cầu Python: {PYTHON_REQUIRED}")
        return 0

    # No arguments → REPL
    if not args.file and not args.eval and not args.repl:
        start_repl(
            verbose=args.verbose,
            show_banner=not args.no_banner,
            max_depth=args.max_depth
        )
        return 0

    # --repl
    if args.repl:
        start_repl(
            verbose=args.verbose,
            show_banner=not args.no_banner,
            max_depth=args.max_depth
        )
        return 0

    # -e / --eval: run inline code
    if args.eval:
        code = args.eval
        if args.verbose:
            print(f"[eval] Chạy: {code!r}")
        try:
            t0 = time.perf_counter()
            config = LexerConfig(strict_mode=args.strict)
            lexer = Lexer(code, '<eval>', config)
            tokens = lexer.tokenize()
            parser = Parser(tokens, '<eval>')
            ast = parser.parse()

            if args.ast:
                show_ast(code, '<eval>', args.verbose)
                return 0

            if args.tokens:
                show_tokens(code, '<eval>')
                return 0

            interp = Interpreter(verbose=args.verbose, max_depth=args.max_depth)
            exit_code = interp.execute(ast)
            elapsed = time.perf_counter() - t0

            if args.time:
                print(f"\n⏱ Thời gian: {elapsed*1000:.3f}ms")

            return exit_code

        except KeyboardInterrupt:
            print("\n  Bị ngắt", file=sys.stderr)
            return 130
        except Exception as e:
            print(f"❌ {e}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            return 1

    # Run file
    filepath = args.file
    if not filepath:
        print("❌ Thiếu tên file", file=sys.stderr)
        return 1

    if not os.path.exists(filepath):
        print(f"❌ File không tìm thấy: {filepath!r}", file=sys.stderr)
        return 1

    if not filepath.endswith('.cpps') and not args.verbose:
        # Warn about non-cpps extension
        pass  # Allow any extension

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except PermissionError:
        print(f"❌ Không có quyền đọc file: {filepath}", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print(f"❌ File không phải UTF-8: {filepath}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Lỗi khi đọc file: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"[cpps] Đang chạy: {filepath}")
        print(f"[cpps] Kích thước: {len(source)} ký tự, {source.count(chr(10))+1} dòng")

    # Show AST mode
    if args.ast:
        show_ast(source, filepath, args.verbose)
        return 0

    # Show tokens mode
    if args.tokens:
        show_tokens(source, filepath)
        return 0

    # Normal execution
    try:
        t0 = time.perf_counter()

        config = LexerConfig(strict_mode=args.strict)
        lexer = Lexer(source, filepath, config)
        tokens = lexer.tokenize()

        if args.stats:
            print("\n=== Lexer Statistics ===")
            print(lexer.stats.summary())

        if lexer.errors:
            print(f"\n⚠️  {len(lexer.errors)} lexer errors:", file=sys.stderr)
            for err in lexer.errors[:5]:
                print(f"  {err}", file=sys.stderr)
            if not args.verbose:
                return 1

        parser = Parser(tokens, filepath)
        ast = parser.parse()

        if args.stats:
            print("=== Parser Info ===")
            print(f"  Statements: {len(ast.statements)}")
            print(f"  Parser errors: {len(parser.errors)}")

        if parser.errors:
            print(f"\n⚠️  {len(parser.errors)} parse errors:", file=sys.stderr)
            for err in parser.errors[:5]:
                print(f"  {err}", file=sys.stderr)

        interp = Interpreter(verbose=args.verbose, max_depth=args.max_depth)
        exit_code = interp.execute(ast)

        elapsed = time.perf_counter() - t0

        if args.time:
            print(f"\n⏱ Thời gian thực thi: {elapsed*1000:.3f}ms")

        if args.verbose:
            print(f"\n[cpps] Hoàn thành trong {elapsed*1000:.1f}ms, exit code: {exit_code}")

        return exit_code

    except KeyboardInterrupt:
        print(f"\n  Bị ngắt bởi người dùng", file=sys.stderr)
        return 130

    except SystemExit as e:
        return int(e.code) if e.code is not None else 0

    except Exception as e:
        print(f"\n❌ Lỗi nghiêm trọng: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
