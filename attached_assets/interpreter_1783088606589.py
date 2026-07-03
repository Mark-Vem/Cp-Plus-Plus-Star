"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CP+* (C-Plus-Plus-Star) Language — Interpreter                             ║
║  File: src/interpreter.py                                                    ║
║  Version: 2.0 — Advanced Edition                                             ║
║                                                                              ║
║  Tree-walking interpreter đầy đủ chức năng cho ngôn ngữ CP+*:               ║
║  - Environment / scope chain (lexical scoping)                               ║
║  - Built-in types: int, float, string, bool, list, dict, set, tuple         ║
║  - Built-in functions: io, math, string, list, map, set, time, channel      ║
║  - OOP: class, struct, trait, impl, inheritance, @@override                 ║
║  - Ownership system: own, share, borrow                                     ║
║  - Concurrency: go goroutines, channels (unbuffered & buffered)             ║
║  - Pattern matching: literal, binding, wildcard, tuple, range, or           ║
║  - Error handling: try/catch, Result<Ok, Err>, panic                        ║
║  - Generics: type-erased at runtime                                          ║
║  - Macros: @macro_tok, @macro_ast                                            ║
║  - Reflection: @reflect                                                      ║
║  - Module system: import, export                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝

Architecture Overview
=====================

Env: Lexical scope environment (chained scopes)
  - get(name): lookup variable in scope chain
  - set(name, value): define in current scope
  - assign(name, value): update nearest scope with binding
  - child(): create child scope
  - snapshot(): capture current bindings (for closures)

Runtime Values:
  - Python native: int, float, str, bool, None, list, dict, set, tuple
  - CPPSInstance: OOP class instance
  - CPPSOwned: Ownership wrapper (own/share/borrow)
  - CPPSResult: Result<Ok, Err>
  - CPPSChannel: Goroutine communication channel
  - CPPSClosure: Captured function with environment
  - CPPSIterator: Lazy iterator

Control Flow Exceptions:
  - ReturnException: Propagates return value
  - BreakException: Breaks out of loop
  - ContinueException: Continues to next iteration

Interpreter: Main tree-walking interpreter
  - eval(node, env): evaluate expression, return value
  - exec(node, env): execute statement, return None
  - execute(ast): run full program
"""

import math as math_module
import random
import threading
import queue
import time as time_module
import sys
import os
import json
import re
from typing import Any, Dict, List, Optional, Union, Callable

from parser import (
    # AST Nodes
    Program, ModuleDecl, ImportStmt, ExportStmt,
    VarDecl, FnDef, OverrideDecl, ClassDef, StructDef, TraitDef, ImplBlock,
    ReturnStmt, BreakStmt, ContinueStmt, PanicStmt, PipeStmt, GoStmt,
    IfStmt, ForStmt, WhileStmt, MatchStmt, MatchArm, TryCatch, MacroInvoke,
    Literal, VarRef, SelfRef, BinaryOp, UnaryOp, Assign,
    FnCall, MethodCall, FieldAccess, IndexAccess,
    ListLiteral, TupleLiteral, MapLiteral,
    OwnershipExpr, ResultOk, ResultErr, AwaitExpr, PipeExpr,
    LambdaExpr, ReflectExpr, TypeCastExpr, RangeExpr,
    # Patterns
    WildcardPattern, LiteralPattern, BindingPattern,
    TuplePattern, RangePattern, OrPattern, StructPattern, EnumPattern,
    ASTNode,
)


# ══════════════════════════════════════════════════════════════════════════════
# CONTROL FLOW EXCEPTIONS
# ══════════════════════════════════════════════════════════════════════════════

class ReturnException(Exception):
    """
    Exception để propagate return value ra khỏi function body.
    Được bắt trong _call_fn và _call_closure.
    """
    def __init__(self, value: Any = None):
        self.value = value
        super().__init__()


class BreakException(Exception):
    """
    Exception để thoát khỏi vòng lặp.
    Được bắt trong for/while exec handlers.
    """
    def __init__(self, label: Optional[str] = None):
        self.label = label
        super().__init__()


class ContinueException(Exception):
    """
    Exception để tiếp tục vòng lặp tiếp theo.
    Được bắt trong for/while exec handlers.
    """
    def __init__(self, label: Optional[str] = None):
        self.label = label
        super().__init__()


# ══════════════════════════════════════════════════════════════════════════════
# RUNTIME EXCEPTIONS
# ══════════════════════════════════════════════════════════════════════════════

class CPPSPanic(Exception):
    """
    Panic! — chương trình abort với thông báo.
    Tương đương với !! trong CP+*.
    """
    def __init__(self, msg: str = "explicit panic"):
        self.msg = msg
        super().__init__(msg)

    def __str__(self) -> str:
        return self.msg


class CPPSError(Exception):
    """
    Runtime error có thể bắt được bằng try/catch.
    Khác với CPPSPanic — không abort ngay.
    """
    def __init__(self, message: str, code: str = '', line: int = 0):
        self.message = message
        self.code = code
        self.line = line
        super().__init__(message)

    def __str__(self) -> str:
        if self.line:
            return f"{self.message} (tại dòng {self.line})"
        return self.message


class CPPSTypeError(CPPSError):
    """Lỗi kiểu dữ liệu không phù hợp."""
    def __init__(self, expected: str, got: str, context: str = ''):
        msg = f"Kiểu không phù hợp: mong đợi {expected}, nhận {got}"
        if context:
            msg += f" trong {context}"
        super().__init__(msg, 'TYPE_ERROR')


class CPPSIndexError(CPPSError):
    """Lỗi index ngoài phạm vi."""
    def __init__(self, index: Any, length: int):
        super().__init__(
            f"Index {index} ngoài phạm vi (độ dài: {length})",
            'INDEX_ERROR'
        )


class CPPSAttributeError(CPPSError):
    """Lỗi truy cập field/method không tồn tại."""
    def __init__(self, obj_type: str, attr: str):
        super().__init__(
            f"'{obj_type}' không có field/method '{attr}'",
            'ATTRIBUTE_ERROR'
        )


class CPPSNameError(CPPSError):
    """Lỗi biến/hàm không tồn tại."""
    def __init__(self, name: str):
        super().__init__(f"Tên chưa được định nghĩa: '{name}'", 'NAME_ERROR')


class CPPSDivisionByZero(CPPSError):
    """Lỗi chia cho 0."""
    def __init__(self):
        super().__init__("Chia cho 0", 'DIVISION_BY_ZERO')


# ══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT (SCOPE CHAIN)
# ══════════════════════════════════════════════════════════════════════════════

class Env:
    """
    Lexical scope environment cho CP+*.

    Tổ chức dạng chuỗi (parent chain):
        global → function → block → ...

    Variables được tra cứu từ scope hiện tại lên scope cha,
    theo quy tắc lexical scoping.

    Attributes:
        _vars (Dict): Biến trong scope hiện tại
        parent (Optional[Env]): Scope cha
        _closed (bool): True nếu scope đã bị đóng (cho closures)

    Usage:
        >>> global_env = Env()
        >>> global_env.set('x', 42)
        >>> child = global_env.child()
        >>> child.set('y', 10)
        >>> print(child.get('x'))  # 42 (from parent)
        >>> print(child.get('y'))  # 10 (local)
    """

    __slots__ = ('_vars', 'parent', '_closed', 'name')

    def __init__(self, parent: Optional['Env'] = None, name: str = ''):
        """
        Khởi tạo scope mới.

        Args:
            parent: Scope cha (None cho global scope)
            name: Tên scope (debug)
        """
        self._vars: Dict[str, Any] = {}
        self.parent = parent
        self._closed = False
        self.name = name

    def get(self, name: str) -> Any:
        """
        Tra cứu biến trong scope chain.

        Args:
            name: Tên biến

        Returns:
            Giá trị biến, hoặc None nếu không tìm thấy
        """
        if name in self._vars:
            return self._vars[name]
        if self.parent is not None:
            return self.parent.get(name)
        return None

    def set(self, name: str, value: Any) -> None:
        """
        Định nghĩa biến trong scope hiện tại.

        Args:
            name: Tên biến
            value: Giá trị
        """
        self._vars[name] = value

    def assign(self, name: str, value: Any) -> bool:
        """
        Cập nhật biến trong scope gần nhất có binding.

        Args:
            name: Tên biến
            value: Giá trị mới

        Returns:
            True nếu tìm thấy và cập nhật, False nếu không
        """
        if name in self._vars:
            self._vars[name] = value
            return True
        if self.parent is not None:
            return self.parent.assign(name, value)
        # Not found — create in current scope
        self._vars[name] = value
        return True

    def has(self, name: str) -> bool:
        """
        Kiểm tra biến có tồn tại trong scope chain không.

        Args:
            name: Tên biến

        Returns:
            True nếu tồn tại
        """
        if name in self._vars:
            return True
        if self.parent is not None:
            return self.parent.has(name)
        return False

    def has_local(self, name: str) -> bool:
        """Kiểm tra biến chỉ trong scope hiện tại (không parent)."""
        return name in self._vars

    def child(self, name: str = '') -> 'Env':
        """
        Tạo scope con mới.

        Args:
            name: Tên scope con (debug)

        Returns:
            Scope con mới
        """
        return Env(parent=self, name=name)

    def snapshot(self) -> 'Env':
        """
        Tạo snapshot của scope chain hiện tại (cho closures).
        Snapshot là shallow copy của tất cả bindings visible.

        Returns:
            Env mới với tất cả bindings hiện tại
        """
        snap = Env(name=f'snapshot({self.name})')
        # Collect all visible bindings (from current to root)
        chain = []
        env = self
        while env is not None:
            chain.append(env._vars)
            env = env.parent
        # Apply from root to current (current overrides parent)
        for scope_vars in reversed(chain):
            snap._vars.update(scope_vars)
        return snap

    def all_names(self) -> List[str]:
        """Lấy tất cả tên trong scope chain."""
        names = set(self._vars.keys())
        if self.parent:
            names |= set(self.parent.all_names())
        return sorted(names)

    def local_names(self) -> List[str]:
        """Lấy tên trong scope hiện tại."""
        return sorted(self._vars.keys())

    def depth(self) -> int:
        """Tính chiều sâu của scope chain."""
        if self.parent is None:
            return 0
        return 1 + self.parent.depth()

    def __repr__(self) -> str:
        return f"Env({self.name!r}, vars={list(self._vars.keys())})"


# ══════════════════════════════════════════════════════════════════════════════
# RUNTIME TYPES
# ══════════════════════════════════════════════════════════════════════════════

class CPPSInstance:
    """
    Runtime instance của CP+* class.

    Attributes:
        class_name (str): Tên class
        fields (Dict): Tất cả fields và methods của instance
                        Methods lưu với key '__method_{name}'

    Usage:
        >>> inst = CPPSInstance('Dog')
        >>> inst.set('name', 'Rex')
        >>> print(inst.get('name'))  # 'Rex'
    """

    __slots__ = ('class_name', 'fields')

    def __init__(self, class_name: str):
        """
        Khởi tạo instance.

        Args:
            class_name: Tên class
        """
        self.class_name = class_name
        self.fields: Dict[str, Any] = {}

    def get(self, name: str) -> Any:
        """Lấy giá trị field."""
        return self.fields.get(name)

    def set(self, name: str, value: Any) -> None:
        """Đặt giá trị field."""
        self.fields[name] = value

    def has(self, name: str) -> bool:
        """Kiểm tra field tồn tại."""
        return name in self.fields

    def get_method(self, name: str) -> Any:
        """Lấy method từ instance."""
        return self.fields.get(f'__method_{name}')

    def has_method(self, name: str) -> bool:
        """Kiểm tra method tồn tại."""
        return f'__method_{name}' in self.fields

    def method_names(self) -> List[str]:
        """Lấy tất cả tên method."""
        return [k[9:] for k in self.fields if k.startswith('__method_')]

    def field_names(self) -> List[str]:
        """Lấy tất cả tên field (không method)."""
        return [k for k in self.fields if not k.startswith('__method_')]

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển instance thành dict (chỉ fields)."""
        return {k: v for k, v in self.fields.items()
                if not k.startswith('__method_')}

    def __repr__(self) -> str:
        field_strs = ', '.join(
            f"{k}={v!r}" for k, v in self.fields.items()
            if not k.startswith('__method_')
        )
        return f"{self.class_name}({{{field_strs}}})"

    def __str__(self) -> str:
        return repr(self)


class CPPSOwned:
    """
    Ownership wrapper cho giá trị trong CP+*.

    Attributes:
        kind (str): 'own' | 'share' | 'borrow'
        value: Giá trị được own/share/borrow

    Semantics:
        - own:    Sole owner — value bị move khi assign
        - share:  Shared reference — counted references
        - borrow: Temporary borrow — cannot outlive owner
    """

    __slots__ = ('kind', 'value', '_ref_count', '_borrowed')

    def __init__(self, kind: str, value: Any):
        """
        Khởi tạo ownership wrapper.

        Args:
            kind: 'own' | 'share' | 'borrow'
            value: Giá trị
        """
        self.kind = kind
        self.value = value
        self._ref_count = 1
        self._borrowed = False

    def move(self) -> 'CPPSOwned':
        """
        Move ownership. Trả về wrapper mới, invalidate cái cũ.
        (Trong runtime, chỉ là copy; ownership semantics là conceptual.)
        """
        new = CPPSOwned(self.kind, self.value)
        return new

    def clone(self) -> 'CPPSOwned':
        """Deep clone giá trị."""
        import copy
        return CPPSOwned(self.kind, copy.deepcopy(self.value))

    def borrow(self) -> 'CPPSOwned':
        """Tạo borrow reference."""
        self._borrowed = True
        return CPPSOwned('borrow', self.value)

    def unwrap(self) -> Any:
        """Lấy giá trị bên trong."""
        return self.value

    def __repr__(self) -> str:
        return f"CPPSOwned({self.kind}, {self.value!r})"


class CPPSResult:
    """
    Result type — biểu diễn thành công (Ok) hoặc lỗi (Err).
    Tương tự Rust's Result<T, E>.

    Attributes:
        ok (bool): True nếu Ok, False nếu Err
        value: Giá trị Ok hoặc thông tin lỗi Err

    Usage:
        >>> r = CPPSResult(True, 42)   # Ok(42)
        >>> r.unwrap()  # 42
        >>> e = CPPSResult(False, "not found")  # Err("not found")
        >>> e.unwrap_or(0)  # 0
    """

    __slots__ = ('ok', 'value')

    def __init__(self, ok: bool, value: Any = None):
        """
        Khởi tạo Result.

        Args:
            ok: True nếu thành công
            value: Giá trị thành công hoặc thông tin lỗi
        """
        self.ok = ok
        self.value = value

    @classmethod
    def success(cls, value: Any = None) -> 'CPPSResult':
        """Tạo Result thành công."""
        return cls(True, value)

    @classmethod
    def failure(cls, error: Any = None) -> 'CPPSResult':
        """Tạo Result lỗi."""
        return cls(False, error)

    def unwrap(self) -> Any:
        """
        Lấy giá trị Ok, panic nếu là Err.

        Returns:
            Giá trị Ok

        Raises:
            CPPSPanic: Nếu là Err
        """
        if self.ok:
            return self.value
        raise CPPSPanic(f"unwrap() trên Err: {self.value}")

    def unwrap_or(self, default: Any) -> Any:
        """Lấy giá trị Ok, hoặc default nếu Err."""
        return self.value if self.ok else default

    def unwrap_or_else(self, fn: Callable) -> Any:
        """Lấy Ok, hoặc gọi fn(err) nếu Err."""
        if self.ok:
            return self.value
        return fn(self.value)

    def map(self, fn: Callable) -> 'CPPSResult':
        """Transform Ok value, để nguyên Err."""
        if self.ok:
            return CPPSResult(True, fn(self.value))
        return self

    def map_err(self, fn: Callable) -> 'CPPSResult':
        """Transform Err value, để nguyên Ok."""
        if not self.ok:
            return CPPSResult(False, fn(self.value))
        return self

    def and_then(self, fn: Callable) -> 'CPPSResult':
        """Chain: nếu Ok, gọi fn(value) trả về Result mới."""
        if self.ok:
            result = fn(self.value)
            if isinstance(result, CPPSResult):
                return result
            return CPPSResult(True, result)
        return self

    def __repr__(self) -> str:
        if self.ok:
            return f"Ok({self.value!r})"
        return f"Err({self.value!r})"

    def __bool__(self) -> bool:
        return self.ok

    def __eq__(self, other) -> bool:
        if isinstance(other, CPPSResult):
            return self.ok == other.ok and self.value == other.value
        return NotImplemented


class CPPSChannel:
    """
    Channel cho giao tiếp giữa goroutines.
    Tương tự Go channels.

    Attributes:
        capacity (int): Kích thước buffer (0 = unbuffered)
        _queue: Queue nội bộ
        _closed (bool): Đã đóng chưa

    Usage:
        >>> ch = CPPSChannel(10)  # buffered channel, capacity=10
        >>> ch.send(42)
        >>> value = ch.recv()  # blocks until data available
        >>> print(value)  # 42
    """

    def __init__(self, capacity: int = 0):
        """
        Khởi tạo Channel.

        Args:
            capacity: Kích thước buffer.
                      0 = unbuffered (synchronous)
                      >0 = buffered
        """
        self.capacity = capacity
        self._queue: queue.Queue = queue.Queue(maxsize=capacity if capacity > 0 else 0)
        self._closed = False

    def send(self, value: Any, timeout: float = 5.0) -> None:
        """
        Gửi giá trị vào channel.

        Args:
            value: Giá trị cần gửi
            timeout: Timeout tính bằng giây

        Raises:
            CPPSPanic: Nếu channel đã đóng hoặc timeout
        """
        if self._closed:
            raise CPPSPanic("send() trên channel đã đóng")
        try:
            if self.capacity == 0:
                self._queue.put(value, timeout=timeout)
            else:
                self._queue.put(value, timeout=timeout)
        except queue.Full:
            raise CPPSPanic(f"Channel đầy (capacity={self.capacity})")

    def recv(self, timeout: float = 5.0) -> Any:
        """
        Nhận giá trị từ channel.

        Args:
            timeout: Timeout tính bằng giây

        Returns:
            Giá trị nhận được

        Raises:
            CPPSPanic: Nếu timeout hoặc channel đóng và rỗng
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            if self._closed:
                return None
            raise CPPSPanic("Channel recv() timeout")

    def try_recv(self) -> Optional[Any]:
        """
        Nhận không chờ (non-blocking).

        Returns:
            Giá trị nếu có, None nếu rỗng
        """
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def close(self) -> None:
        """Đóng channel."""
        self._closed = True

    def is_closed(self) -> bool:
        """Kiểm tra channel đã đóng chưa."""
        return self._closed

    def len(self) -> int:
        """Số lượng phần tử đang chờ."""
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """Kiểm tra channel rỗng."""
        return self._queue.empty()

    def is_full(self) -> bool:
        """Kiểm tra channel đầy."""
        return self._queue.full()

    def __repr__(self) -> str:
        status = 'closed' if self._closed else 'open'
        return f"Channel(capacity={self.capacity}, len={self.len()}, {status})"


class CPPSClosure:
    """
    Closure — hàm với captured environment.

    Attributes:
        fn_def (FnDef): Function definition node
        captured_env (Env): Environment tại thời điểm tạo closure
        name (str): Tên closure (debug)
    """

    __slots__ = ('fn_def', 'captured_env', 'name')

    def __init__(self, fn_def: FnDef, captured_env: Env, name: str = '<closure>'):
        """
        Khởi tạo closure.

        Args:
            fn_def: FnDef AST node
            captured_env: Môi trường được capture
            name: Tên gợi nhớ
        """
        self.fn_def = fn_def
        self.captured_env = captured_env
        self.name = name

    def __repr__(self) -> str:
        params = ', '.join(p[0] for p in self.fn_def.params)
        return f"Closure({self.name})({params})"


class CPPSNativeFunction:
    """
    Native (Python) function được expose vào CP+*.

    Attributes:
        name (str): Tên hàm
        fn (Callable): Python callable
        arity (Optional[int]): Số tham số (None = variadic)
        doc (str): Documentation
    """

    def __init__(self, name: str, fn: Callable,
                 arity: Optional[int] = None, doc: str = ''):
        self.name = name
        self.fn = fn
        self.arity = arity
        self.doc = doc

    def call(self, args: List[Any]) -> Any:
        """Gọi native function."""
        try:
            return self.fn(*args)
        except CPPSPanic:
            raise
        except CPPSError:
            raise
        except Exception as e:
            raise CPPSError(f"Lỗi trong native function '{self.name}': {e}")

    def __repr__(self) -> str:
        return f"<native fn {self.name}>"


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _display(value: Any) -> str:
    """
    Chuyển giá trị CP+* thành chuỗi hiển thị.
    Tương tự Display trait trong Rust.

    Args:
        value: Giá trị bất kỳ

    Returns:
        Chuỗi biểu diễn

    Examples:
        >>> _display(42)         # '42'
        >>> _display(3.14)       # '3.14'
        >>> _display(True)       # 'true'
        >>> _display(None)       # 'none'
        >>> _display([1, 2, 3])  # '[1, 2, 3]'
        >>> _display({'a': 1})   # '{a: 1}'
    """
    if value is None:
        return 'none'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        # Clean float display
        if value == int(value) and not math_module.isinf(value):
            return str(int(value)) + '.0'
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        inner = ', '.join(_display(x) for x in value)
        return f'[{inner}]'
    if isinstance(value, dict):
        pairs = ', '.join(f'{k}: {_display(v)}' for k, v in value.items())
        return '{' + pairs + '}'
    if isinstance(value, set):
        inner = ', '.join(_display(x) for x in sorted(value, key=str))
        return '{' + inner + '}'
    if isinstance(value, tuple):
        inner = ', '.join(_display(x) for x in value)
        return f'({inner})'
    if isinstance(value, CPPSInstance):
        return repr(value)
    if isinstance(value, CPPSOwned):
        return _display(value.value)
    if isinstance(value, CPPSResult):
        return repr(value)
    if isinstance(value, CPPSChannel):
        return repr(value)
    if isinstance(value, CPPSClosure):
        return repr(value)
    if isinstance(value, FnDef):
        return f'<fn {value.name}>'
    if isinstance(value, CPPSNativeFunction):
        return f'<native fn {value.name}>'
    return str(value)


def _type_of(value: Any) -> str:
    """
    Lấy tên kiểu dữ liệu của giá trị CP+*.

    Args:
        value: Giá trị

    Returns:
        Tên kiểu (string)
    """
    if value is None:
        return 'none'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'List'
    if isinstance(value, dict):
        return 'Map'
    if isinstance(value, set):
        return 'Set'
    if isinstance(value, tuple):
        return 'Tuple'
    if isinstance(value, CPPSInstance):
        return value.class_name
    if isinstance(value, CPPSOwned):
        return f'{value.kind}<{_type_of(value.value)}>'
    if isinstance(value, CPPSResult):
        return 'Result'
    if isinstance(value, CPPSChannel):
        return 'Channel'
    if isinstance(value, CPPSClosure):
        return 'Closure'
    if isinstance(value, FnDef):
        return 'Function'
    if isinstance(value, CPPSNativeFunction):
        return 'NativeFunction'
    return type(value).__name__


def _is_truthy(value: Any) -> bool:
    """
    Kiểm tra giá trị có "truthy" không theo CP+* rules.

    Falsy values: None, False, 0, 0.0, "", [], {}, set(), Err(_)
    Everything else is truthy.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return len(value) > 0
    if isinstance(value, (list, dict, set)):
        return len(value) > 0
    if isinstance(value, tuple):
        return len(value) > 0
    if isinstance(value, CPPSResult):
        return value.ok
    if isinstance(value, CPPSOwned):
        return _is_truthy(value.value)
    return True


def _unwrap_owned(value: Any) -> Any:
    """Unwrap CPPSOwned wrapper nếu có."""
    if isinstance(value, CPPSOwned):
        return value.value
    return value


# ══════════════════════════════════════════════════════════════════════════════
# BUILT-IN FUNCTION REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

def _build_builtins(interpreter: 'Interpreter') -> Dict[str, Any]:
    """
    Tạo dictionary các built-in functions của CP+*.

    Args:
        interpreter: Interpreter instance (để access classes, etc.)

    Returns:
        Dict mapping name -> callable hoặc value
    """
    builtins: Dict[str, Any] = {}

    # ── I/O ──────────────────────────────────────────────────────────────
    def println(*args):
        if not args:
            print()
            return None
        template = _display(args[0])
        for a in args[1:]:
            template = template.replace('{}', _display(a), 1)
        print(template)
        return None

    def print_fn(*args):
        if not args:
            return None
        template = _display(args[0])
        for a in args[1:]:
            template = template.replace('{}', _display(a), 1)
        print(template, end='')
        return None

    def eprintln(*args):
        if not args:
            print(file=sys.stderr)
            return None
        template = _display(args[0])
        for a in args[1:]:
            template = template.replace('{}', _display(a), 1)
        print(template, file=sys.stderr)
        return None

    def input_fn(*args):
        prompt = _display(args[0]) if args else ''
        try:
            return input(prompt)
        except EOFError:
            return None

    for name in ('println', 'io::println', 'io.println'):
        builtins[name] = println
    for name in ('print', 'io::print', 'io.print'):
        builtins[name] = print_fn
    for name in ('eprintln', 'io::eprintln', 'io.eprintln'):
        builtins[name] = eprintln
    for name in ('input', 'io::input', 'io.input', 'readline'):
        builtins[name] = input_fn

    # ── Math functions ────────────────────────────────────────────────────
    math_fns = {
        'abs':      lambda *a: abs(a[0]),
        'sqrt':     lambda *a: math_module.sqrt(a[0]),
        'cbrt':     lambda *a: a[0] ** (1/3) if a[0] >= 0 else -((-a[0]) ** (1/3)),
        'pow':      lambda *a: a[0] ** a[1],
        'sin':      lambda *a: math_module.sin(a[0]),
        'cos':      lambda *a: math_module.cos(a[0]),
        'tan':      lambda *a: math_module.tan(a[0]),
        'asin':     lambda *a: math_module.asin(a[0]),
        'acos':     lambda *a: math_module.acos(a[0]),
        'atan':     lambda *a: math_module.atan(a[0]),
        'atan2':    lambda *a: math_module.atan2(a[0], a[1]),
        'sinh':     lambda *a: math_module.sinh(a[0]),
        'cosh':     lambda *a: math_module.cosh(a[0]),
        'tanh':     lambda *a: math_module.tanh(a[0]),
        'log':      lambda *a: math_module.log(a[0]) if len(a)==1 else math_module.log(a[0], a[1]),
        'log2':     lambda *a: math_module.log2(a[0]),
        'log10':    lambda *a: math_module.log10(a[0]),
        'exp':      lambda *a: math_module.exp(a[0]),
        'floor':    lambda *a: int(math_module.floor(a[0])),
        'ceil':     lambda *a: int(math_module.ceil(a[0])),
        'round':    lambda *a: round(a[0], int(a[1]) if len(a) > 1 else 0),
        'trunc':    lambda *a: int(math_module.trunc(a[0])),
        'sign':     lambda *a: (1 if a[0] > 0 else -1 if a[0] < 0 else 0),
        'clamp':    lambda *a: max(a[1], min(a[2], a[0])),
        'lerp':     lambda *a: a[0] + (a[1] - a[0]) * a[2],
        'hypot':    lambda *a: math_module.hypot(a[0], a[1]),
        'gcd':      lambda *a: math_module.gcd(int(a[0]), int(a[1])),
        'lcm':      lambda *a: abs(int(a[0]) * int(a[1])) // math_module.gcd(int(a[0]), int(a[1])) if a[0] and a[1] else 0,
        'factorial': lambda *a: math_module.factorial(int(a[0])),
        'is_nan':   lambda *a: math_module.isnan(float(a[0])),
        'is_inf':   lambda *a: math_module.isinf(float(a[0])),
        'is_finite': lambda *a: math_module.isfinite(float(a[0])),
        'random':   lambda *a: random.random(),
        'randint':  lambda *a: random.randint(int(a[0]), int(a[1])),
        'randf':    lambda *a: random.uniform(float(a[0]), float(a[1])),
        'seed':     lambda *a: random.seed(a[0]) or None,
        'shuffle':  lambda *a: (random.shuffle(a[0]), a[0])[1],
        'choice':   lambda *a: random.choice(a[0]) if a[0] else None,
        'sample':   lambda *a: random.sample(a[0], int(a[1])),
    }

    # Register both with and without 'math::' prefix
    for name, fn in math_fns.items():
        builtins[name] = fn
        builtins[f'math::{name}'] = fn
        builtins[f'math.{name}'] = fn

    # Math constants
    builtins['math::PI'] = math_module.pi
    builtins['math::E'] = math_module.e
    builtins['math::TAU'] = math_module.tau
    builtins['math::INF'] = math_module.inf
    builtins['math::NAN'] = math_module.nan
    builtins['PI'] = math_module.pi
    builtins['E'] = math_module.e
    builtins['INF'] = math_module.inf
    builtins['NAN'] = math_module.nan

    # ── Type conversion ───────────────────────────────────────────────────
    def to_int(*a):
        if not a:
            return 0
        v = _unwrap_owned(a[0])
        try:
            if isinstance(v, bool):
                return int(v)
            return int(v)
        except (ValueError, TypeError):
            return CPPSResult(False, f"Không thể chuyển {v!r} sang int")

    def to_float(*a):
        if not a:
            return 0.0
        v = _unwrap_owned(a[0])
        try:
            return float(v)
        except (ValueError, TypeError):
            return CPPSResult(False, f"Không thể chuyển {v!r} sang float")

    def to_string(*a):
        if not a:
            return ''
        return _display(_unwrap_owned(a[0]))

    def to_bool(*a):
        if not a:
            return False
        return _is_truthy(_unwrap_owned(a[0]))

    builtins['int'] = to_int
    builtins['float'] = to_float
    builtins['str'] = to_string
    builtins['string'] = to_string
    builtins['bool'] = to_bool
    builtins['to_int'] = to_int
    builtins['to_float'] = to_float
    builtins['to_string'] = to_string
    builtins['to_bool'] = to_bool

    # ── Collection utilities ──────────────────────────────────────────────
    def fn_len(*a):
        if not a:
            return 0
        v = _unwrap_owned(a[0])
        if hasattr(v, '__len__'):
            return len(v)
        if isinstance(v, CPPSInstance):
            # Check if instance has a len method
            return 0
        return 0

    def fn_range(*a):
        if not a:
            return []
        args = [int(_unwrap_owned(x)) for x in a]
        return list(range(*args))

    def fn_enumerate(*a):
        if not a:
            return []
        items = _unwrap_owned(a[0])
        start = int(_unwrap_owned(a[1])) if len(a) > 1 else 0
        return [(i + start, v) for i, v in enumerate(items)]

    def fn_zip(*a):
        lists = [_unwrap_owned(x) for x in a]
        return [tuple(items) for items in zip(*lists)]

    def fn_map(*a):
        if len(a) < 2:
            return []
        fn, lst = _unwrap_owned(a[0]), _unwrap_owned(a[1])
        if isinstance(fn, FnDef):
            return [interpreter._call_fn(fn, [x], interpreter.global_env) for x in lst]
        if callable(fn):
            return [fn(x) for x in lst]
        return []

    def fn_filter(*a):
        if len(a) < 2:
            return []
        fn, lst = _unwrap_owned(a[0]), _unwrap_owned(a[1])
        if isinstance(fn, FnDef):
            return [x for x in lst if _is_truthy(interpreter._call_fn(fn, [x], interpreter.global_env))]
        if callable(fn):
            return [x for x in lst if _is_truthy(fn(x))]
        return []

    def fn_reduce(*a):
        if len(a) < 2:
            return None
        fn, lst = _unwrap_owned(a[0]), _unwrap_owned(a[1])
        if not lst:
            return _unwrap_owned(a[2]) if len(a) > 2 else None
        acc = lst[0]
        for x in lst[1:]:
            if isinstance(fn, FnDef):
                acc = interpreter._call_fn(fn, [acc, x], interpreter.global_env)
            elif callable(fn):
                acc = fn(acc, x)
        return acc

    def fn_sorted(*a):
        if not a:
            return []
        lst = list(_unwrap_owned(a[0]))
        reverse = bool(_unwrap_owned(a[1])) if len(a) > 1 else False
        try:
            lst.sort(reverse=reverse)
        except TypeError:
            pass
        return lst

    def fn_reversed(*a):
        if not a:
            return []
        lst = list(_unwrap_owned(a[0]))
        lst.reverse()
        return lst

    def fn_sum(*a):
        if not a:
            return 0
        lst = _unwrap_owned(a[0])
        return sum(lst) if lst else 0

    def fn_min(*a):
        if not a:
            return None
        lst = _unwrap_owned(a[0])
        if isinstance(lst, (list, tuple, set)):
            return min(lst) if lst else None
        return min(_unwrap_owned(x) for x in a)

    def fn_max(*a):
        if not a:
            return None
        lst = _unwrap_owned(a[0])
        if isinstance(lst, (list, tuple, set)):
            return max(lst) if lst else None
        return max(_unwrap_owned(x) for x in a)

    def fn_any(*a):
        if not a:
            return False
        lst = _unwrap_owned(a[0])
        return any(_is_truthy(x) for x in lst)

    def fn_all(*a):
        if not a:
            return True
        lst = _unwrap_owned(a[0])
        return all(_is_truthy(x) for x in lst)

    def fn_count(*a):
        if not a:
            return 0
        lst = _unwrap_owned(a[0])
        if len(a) > 1:
            # count(list, value) — count occurrences
            target = _unwrap_owned(a[1])
            return sum(1 for x in lst if x == target)
        return len(lst)

    def fn_flat(*a):
        if not a:
            return []
        lst = _unwrap_owned(a[0])
        result = []
        for x in lst:
            if isinstance(x, (list, tuple)):
                result.extend(x)
            else:
                result.append(x)
        return result

    def fn_unique(*a):
        if not a:
            return []
        lst = _unwrap_owned(a[0])
        seen = []
        seen_set = set()
        for x in lst:
            key = repr(x)
            if key not in seen_set:
                seen_set.add(key)
                seen.append(x)
        return seen

    for fname, fn in [
        ('len', fn_len), ('range', fn_range),
        ('enumerate', fn_enumerate), ('zip', fn_zip),
        ('map', fn_map), ('filter', fn_filter), ('reduce', fn_reduce),
        ('sorted', fn_sorted), ('reversed', fn_reversed),
        ('sum', fn_sum), ('min', fn_min), ('max', fn_max),
        ('any', fn_any), ('all', fn_all),
        ('count', fn_count), ('flat', fn_flat), ('unique', fn_unique),
    ]:
        builtins[fname] = fn

    # ── Type checking ─────────────────────────────────────────────────────
    builtins['type_of'] = lambda *a: _type_of(_unwrap_owned(a[0])) if a else 'none'
    builtins['is_int'] = lambda *a: isinstance(_unwrap_owned(a[0]), int) and not isinstance(_unwrap_owned(a[0]), bool) if a else False
    builtins['is_float'] = lambda *a: isinstance(_unwrap_owned(a[0]), float) if a else False
    builtins['is_string'] = lambda *a: isinstance(_unwrap_owned(a[0]), str) if a else False
    builtins['is_bool'] = lambda *a: isinstance(_unwrap_owned(a[0]), bool) if a else False
    builtins['is_list'] = lambda *a: isinstance(_unwrap_owned(a[0]), list) if a else False
    builtins['is_dict'] = lambda *a: isinstance(_unwrap_owned(a[0]), dict) if a else False
    builtins['is_none'] = lambda *a: _unwrap_owned(a[0]) is None if a else True
    builtins['is_ok'] = lambda *a: isinstance(_unwrap_owned(a[0]), CPPSResult) and _unwrap_owned(a[0]).ok if a else False
    builtins['is_err'] = lambda *a: isinstance(_unwrap_owned(a[0]), CPPSResult) and not _unwrap_owned(a[0]).ok if a else False

    # ── Result constructors ───────────────────────────────────────────────
    builtins['Ok'] = lambda *a: CPPSResult(True, a[0] if a else None)
    builtins['Err'] = lambda *a: CPPSResult(False, a[0] if a else 'error')

    # ── Channel constructors ──────────────────────────────────────────────
    builtins['Channel'] = lambda *a: CPPSChannel(int(_unwrap_owned(a[0])) if a else 0)
    builtins['Channel::new'] = lambda *a: CPPSChannel(int(_unwrap_owned(a[0])) if a else 0)
    builtins['chan'] = lambda *a: CPPSChannel(int(_unwrap_owned(a[0])) if a else 0)

    # ── Collection constructors ───────────────────────────────────────────
    builtins['List'] = lambda *a: list(a[0]) if a else []
    builtins['List::new'] = lambda *a: list(a[0]) if a else []
    builtins['Map'] = lambda *a: dict(a[0]) if a else {}
    builtins['Map::new'] = lambda *a: {}
    builtins['Set'] = lambda *a: set(a[0]) if a else set()
    builtins['Set::new'] = lambda *a: set()
    builtins['Tuple'] = lambda *a: tuple(a[0]) if a else ()

    # ── String utilities ──────────────────────────────────────────────────
    def string_format(*a):
        if not a:
            return ''
        tmpl = str(_unwrap_owned(a[0]))
        for x in a[1:]:
            tmpl = tmpl.replace('{}', _display(_unwrap_owned(x)), 1)
        return tmpl

    def string_parse_int(*a):
        if not a:
            return CPPSResult(False, 'no input')
        try:
            return int(str(_unwrap_owned(a[0])))
        except ValueError:
            return CPPSResult(False, f"Không thể parse '{a[0]}' sang int")

    def string_parse_float(*a):
        if not a:
            return CPPSResult(False, 'no input')
        try:
            return float(str(_unwrap_owned(a[0])))
        except ValueError:
            return CPPSResult(False, f"Không thể parse '{a[0]}' sang float")

    def string_join(*a):
        if not a:
            return ''
        lst = _unwrap_owned(a[0])
        sep = str(_unwrap_owned(a[1])) if len(a) > 1 else ''
        return sep.join(_display(x) for x in lst)

    for fname, fn in [
        ('string::format', string_format),
        ('string::parse_int', string_parse_int),
        ('string::parse_float', string_parse_float),
        ('string::join', string_join),
        ('format', string_format),
    ]:
        builtins[fname] = fn

    # ── Assertions ────────────────────────────────────────────────────────
    def assert_fn(*a):
        cond = _is_truthy(_unwrap_owned(a[0])) if a else False
        msg = _display(_unwrap_owned(a[1])) if len(a) > 1 else 'assertion failed'
        if not cond:
            raise CPPSPanic(f"Assertion thất bại: {msg}")
        return None

    def assert_eq(*a):
        if len(a) < 2:
            raise CPPSPanic("assert_eq cần 2 arguments")
        v1, v2 = _unwrap_owned(a[0]), _unwrap_owned(a[1])
        if v1 != v2:
            raise CPPSPanic(f"assert_eq thất bại: {_display(v1)} != {_display(v2)}")
        return None

    def assert_ne(*a):
        if len(a) < 2:
            raise CPPSPanic("assert_ne cần 2 arguments")
        v1, v2 = _unwrap_owned(a[0]), _unwrap_owned(a[1])
        if v1 == v2:
            raise CPPSPanic(f"assert_ne thất bại: {_display(v1)} == {_display(v2)}")
        return None

    builtins['assert'] = assert_fn
    builtins['assert_eq'] = assert_eq
    builtins['assert_ne'] = assert_ne

    # ── Time ──────────────────────────────────────────────────────────────
    builtins['time::now'] = lambda *a: time_module.time()
    builtins['time::sleep'] = lambda *a: time_module.sleep(float(_unwrap_owned(a[0])) if a else 0)
    builtins['time::millis'] = lambda *a: int(time_module.time() * 1000)
    builtins['time::format'] = lambda *a: time_module.strftime(str(_unwrap_owned(a[0])) if a else '%Y-%m-%d %H:%M:%S')
    builtins['now'] = builtins['time::now']
    builtins['sleep'] = builtins['time::sleep']

    # ── System ────────────────────────────────────────────────────────────
    builtins['sys::exit'] = lambda *a: sys.exit(int(_unwrap_owned(a[0])) if a else 0)
    builtins['sys::args'] = lambda *a: sys.argv[1:]
    builtins['sys::env'] = lambda *a: os.environ.get(str(_unwrap_owned(a[0])), None) if a else dict(os.environ)
    builtins['sys::platform'] = lambda *a: sys.platform
    builtins['exit'] = builtins['sys::exit']

    # ── File I/O ──────────────────────────────────────────────────────────
    def file_read(*a):
        if not a:
            return CPPSResult(False, 'no filename')
        try:
            with open(str(_unwrap_owned(a[0])), 'r', encoding='utf-8') as f:
                return CPPSResult(True, f.read())
        except FileNotFoundError:
            return CPPSResult(False, f"File không tìm thấy: {a[0]}")
        except Exception as e:
            return CPPSResult(False, str(e))

    def file_write(*a):
        if len(a) < 2:
            return CPPSResult(False, 'thiếu args')
        try:
            mode = str(_unwrap_owned(a[2])) if len(a) > 2 else 'w'
            with open(str(_unwrap_owned(a[0])), mode, encoding='utf-8') as f:
                f.write(str(_unwrap_owned(a[1])))
            return CPPSResult(True, None)
        except Exception as e:
            return CPPSResult(False, str(e))

    def file_exists(*a):
        if not a:
            return False
        return os.path.exists(str(_unwrap_owned(a[0])))

    builtins['file::read'] = file_read
    builtins['file::write'] = file_write
    builtins['file::exists'] = file_exists
    builtins['read_file'] = file_read
    builtins['write_file'] = file_write

    # ── JSON ──────────────────────────────────────────────────────────────
    def json_parse(*a):
        if not a:
            return CPPSResult(False, 'no input')
        try:
            return CPPSResult(True, json.loads(str(_unwrap_owned(a[0]))))
        except json.JSONDecodeError as e:
            return CPPSResult(False, str(e))

    def json_stringify(*a):
        if not a:
            return 'null'
        try:
            return json.dumps(_unwrap_owned(a[0]),
                              indent=int(_unwrap_owned(a[1])) if len(a) > 1 else None,
                              ensure_ascii=False)
        except Exception as e:
            return CPPSResult(False, str(e))

    builtins['json::parse'] = json_parse
    builtins['json::stringify'] = json_stringify
    builtins['json_parse'] = json_parse
    builtins['json_stringify'] = json_stringify

    # ── Regex ─────────────────────────────────────────────────────────────
    def regex_match(*a):
        if len(a) < 2:
            return False
        pattern = str(_unwrap_owned(a[0]))
        text = str(_unwrap_owned(a[1]))
        return bool(re.match(pattern, text))

    def regex_search(*a):
        if len(a) < 2:
            return None
        pattern = str(_unwrap_owned(a[0]))
        text = str(_unwrap_owned(a[1]))
        m = re.search(pattern, text)
        return m.group(0) if m else None

    def regex_find_all(*a):
        if len(a) < 2:
            return []
        pattern = str(_unwrap_owned(a[0]))
        text = str(_unwrap_owned(a[1]))
        return re.findall(pattern, text)

    def regex_replace(*a):
        if len(a) < 3:
            return _unwrap_owned(a[0]) if a else ''
        text = str(_unwrap_owned(a[0]))
        pattern = str(_unwrap_owned(a[1]))
        repl = str(_unwrap_owned(a[2]))
        return re.sub(pattern, repl, text)

    builtins['regex::match'] = regex_match
    builtins['regex::search'] = regex_search
    builtins['regex::find_all'] = regex_find_all
    builtins['regex::replace'] = regex_replace

    # ── Debug / Inspection ────────────────────────────────────────────────
    builtins['dbg'] = lambda *a: (print(f"[dbg] {_display(_unwrap_owned(a[0]))}"), _unwrap_owned(a[0]))[1] if a else None
    builtins['dump'] = lambda *a: print(repr(_unwrap_owned(a[0]))) or None if a else None
    builtins['print_type'] = lambda *a: print(f"type: {_type_of(_unwrap_owned(a[0]))}") or None if a else None

    return builtins


# ══════════════════════════════════════════════════════════════════════════════
# INTERPRETER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Interpreter:
    """
    Tree-walking interpreter cho ngôn ngữ CP+*.

    Nhận AST từ Parser và thực thi từng node.

    Features:
        - Full OOP với class, struct, trait, impl, inheritance
        - Ownership semantics (own, share, borrow)
        - Goroutines với channels
        - Pattern matching đầy đủ
        - Error handling (try/catch, Result)
        - Built-in standard library
        - REPL mode
        - Verbose/debug mode

    Usage:
        >>> from lexer import tokenize
        >>> from parser import Parser
        >>> tokens = tokenize(source, 'main.cpps')
        >>> ast = Parser(tokens, 'main.cpps').parse()
        >>> interp = Interpreter()
        >>> interp.execute(ast)

    Attributes:
        global_env (Env): Global scope
        classes (Dict): Đăng ký class definitions
        structs (Dict): Đăng ký struct definitions
        traits (Dict): Đăng ký trait definitions
        impls (Dict): Đăng ký impl blocks
        current_module (str): Module hiện tại
        verbose (bool): Chế độ verbose (debug)
        _go_threads (List): Goroutine threads đang chạy
    """

    def __init__(self, verbose: bool = False, max_depth: int = 1000):
        """
        Khởi tạo Interpreter.

        Args:
            verbose: In debug info trong quá trình thực thi
            max_depth: Độ sâu call stack tối đa
        """
        self.verbose = verbose
        self.max_depth = max_depth
        self._call_depth = 0

        # Global scope
        self.global_env = Env(name='global')

        # Type registries
        self.classes: Dict[str, ClassDef] = {}
        self.structs: Dict[str, StructDef] = {}
        self.traits: Dict[str, TraitDef] = {}
        self.impls: Dict[str, Dict[str, FnDef]] = {}  # type_name -> method_name -> FnDef

        # Module system
        self.current_module = '<main>'
        self.modules: Dict[str, Dict[str, Any]] = {}

        # Concurrency
        self._go_threads: List[threading.Thread] = []
        self._channels: Dict[str, CPPSChannel] = {}

        # Built-ins registration
        builtins = _build_builtins(self)
        for name, value in builtins.items():
            self.global_env.set(name, value)

        # Register built-in types in global env
        self.global_env.set('true', True)
        self.global_env.set('false', False)
        self.global_env.set('none', None)
        self.global_env.set('null', None)
        self.global_env.set('nil', None)

        if self.verbose:
            print("[Interpreter] Khởi tạo xong, built-ins đã đăng ký")

    # ══════════════════════════════════════════════════════════════════════
    # MAIN EVALUATION
    # ══════════════════════════════════════════════════════════════════════

    def eval(self, node: Optional[ASTNode], env: Env) -> Any:
        """
        Evaluate một expression node và trả về giá trị.

        Args:
            node: ASTNode expression cần evaluate
            env: Scope hiện tại

        Returns:
            Giá trị Python tương ứng

        Raises:
            CPPSPanic: Khi gặp lệnh !!
            CPPSError: Khi gặp runtime error
            ReturnException: Khi gặp lệnh <-
        """
        if node is None:
            return None

        # ── Literal ────────────────────────────────────────────────────
        if isinstance(node, Literal):
            return node.value

        # ── Variable reference ─────────────────────────────────────────
        if isinstance(node, VarRef):
            val = env.get(node.name)
            if val is None and not env.has(node.name):
                if self.verbose:
                    print(f"  [warn] Biến '{node.name}' không tìm thấy tại dòng {node.line}")
            return val

        # ── Self reference ─────────────────────────────────────────────
        if isinstance(node, SelfRef):
            val = env.get('self')
            return val

        # ── Binary operation ───────────────────────────────────────────
        if isinstance(node, BinaryOp):
            return self._eval_binary(node, env)

        # ── Unary operation ────────────────────────────────────────────
        if isinstance(node, UnaryOp):
            val = self.eval(node.operand, env)
            if node.op == '-':
                val = _unwrap_owned(val)
                return -val if val is not None else 0
            if node.op == '!':
                return not _is_truthy(val)
            if node.op == '~':
                val = _unwrap_owned(val)
                return ~int(val) if isinstance(val, int) else val
            return val

        # ── Assignment ─────────────────────────────────────────────────
        if isinstance(node, Assign):
            return self._exec_assign(node, env)

        # ── Function call ──────────────────────────────────────────────
        if isinstance(node, FnCall):
            return self._exec_fn_call(node.name, node.args, env)

        # ── Method call ────────────────────────────────────────────────
        if isinstance(node, MethodCall):
            obj = self.eval(node.obj, env)
            args = [self.eval(a, env) for a in node.args]
            return self._exec_method(obj, node.method, args, env)

        # ── Field access ───────────────────────────────────────────────
        if isinstance(node, FieldAccess):
            obj = self.eval(node.obj, env)
            return self._get_field(obj, node.field)

        # ── Index access ───────────────────────────────────────────────
        if isinstance(node, IndexAccess):
            obj = self.eval(node.obj, env)
            idx = self.eval(node.index, env)
            obj = _unwrap_owned(obj)
            idx = _unwrap_owned(idx)
            try:
                if isinstance(obj, (list, tuple)):
                    return obj[int(idx)]
                if isinstance(obj, dict):
                    return obj.get(idx)
                if isinstance(obj, str):
                    return obj[int(idx)]
                if isinstance(obj, CPPSInstance):
                    return self._get_field(obj, str(idx))
            except (IndexError, KeyError):
                if isinstance(obj, list):
                    raise CPPSIndexError(idx, len(obj))
                return None
            except TypeError:
                return None
            return None

        # ── List literal ───────────────────────────────────────────────
        if isinstance(node, ListLiteral):
            return [self.eval(e, env) for e in node.elements]

        # ── Tuple literal ──────────────────────────────────────────────
        if isinstance(node, TupleLiteral):
            return tuple(self.eval(e, env) for e in node.elements)

        # ── Map literal ────────────────────────────────────────────────
        if isinstance(node, MapLiteral):
            return {k: self.eval(v, env) for k, v in node.pairs}

        # ── Ownership expression ───────────────────────────────────────
        if isinstance(node, OwnershipExpr):
            val = self.eval(node.inner, env)
            return CPPSOwned(node.kind, val)

        # ── Result: Ok / Err ───────────────────────────────────────────
        if isinstance(node, ResultOk):
            val = self.eval(node.value, env)
            return CPPSResult(True, val)

        if isinstance(node, ResultErr):
            val = self.eval(node.value, env)
            return CPPSResult(False, val)

        # ── Await expression ───────────────────────────────────────────
        if isinstance(node, AwaitExpr):
            val = self.eval(node.expr, env)
            if isinstance(val, CPPSChannel):
                return val.recv()
            if isinstance(val, CPPSOwned):
                return val.value
            return val

        # ── Pipe expression ────────────────────────────────────────────
        if isinstance(node, PipeExpr):
            left = self.eval(node.left, env)
            right = node.right
            if isinstance(right, FnCall):
                args = [left] + [self.eval(a, env) for a in right.args]
                return self._exec_fn_call(right.name, [], env, pre_args=args)
            return left

        # ── Reflect expression ─────────────────────────────────────────
        if isinstance(node, ReflectExpr):
            target = self.eval(node.target, env)
            return self._reflect(target)

        # ── Type cast ─────────────────────────────────────────────────
        if isinstance(node, TypeCastExpr):
            val = self.eval(node.expr, env)
            val = _unwrap_owned(val)
            cast = node.cast_type.lower()
            try:
                if cast in ('int', 'i32', 'i64', 'i8', 'i16', 'i128', 'usize'):
                    return int(val)
                if cast in ('float', 'f32', 'f64'):
                    return float(val)
                if cast in ('string', 'str'):
                    return _display(val)
                if cast == 'bool':
                    return _is_truthy(val)
            except (ValueError, TypeError):
                raise CPPSTypeError(node.cast_type, _type_of(val), 'as')
            return val

        # ── Range expression ───────────────────────────────────────────
        if isinstance(node, RangeExpr):
            start = int(_unwrap_owned(self.eval(node.start, env)))
            end = int(_unwrap_owned(self.eval(node.end, env)))
            if node.inclusive:
                return list(range(start, end + 1))
            return list(range(start, end))

        # ── Lambda expression ──────────────────────────────────────────
        if isinstance(node, LambdaExpr):
            # Create closure
            from parser import FnDef as FnDefCls
            fn = FnDefCls('<lambda>', [], node.params, node.return_type,
                          node.body if isinstance(node.body, list) else [node.body],
                          False, False, node.line)
            return CPPSClosure(fn, env.snapshot())

        # ── Macro invocation in expression ─────────────────────────────
        if isinstance(node, MacroInvoke):
            return self._exec_macro(node, env)

        # ── Else: try executing as statement ───────────────────────────
        result = self.exec(node, env)
        return result

    def _get_field(self, obj: Any, field: str) -> Any:
        """
        Lấy field từ object.

        Args:
            obj: Object bất kỳ
            field: Tên field

        Returns:
            Giá trị field
        """
        obj = _unwrap_owned(obj)
        if isinstance(obj, CPPSInstance):
            return obj.get(field)
        if isinstance(obj, dict):
            return obj.get(field)
        if isinstance(obj, CPPSResult):
            if field == 'ok':
                return obj.ok
            if field == 'value':
                return obj.value
            if field == 'is_ok':
                return obj.ok
            if field == 'is_err':
                return not obj.ok
        if isinstance(obj, CPPSChannel):
            if field == 'len':
                return obj.len()
            if field == 'closed':
                return obj.is_closed()
        if isinstance(obj, list):
            if field == 'len':
                return len(obj)
            if field == 'first':
                return obj[0] if obj else None
            if field == 'last':
                return obj[-1] if obj else None
            if field == 'is_empty':
                return len(obj) == 0
        if isinstance(obj, str):
            if field == 'len':
                return len(obj)
            if field == 'is_empty':
                return len(obj) == 0
        return None

    def _eval_binary(self, node: BinaryOp, env: Env) -> Any:
        """
        Evaluate binary operation.

        Handles:
            - Arithmetic: + - * / % **
            - Comparison: == != < > <= >=
            - Logical: && ||
            - String concatenation: str + str
            - List concatenation: list + list
        """
        op = node.op

        # Short-circuit logical operators
        if op == '&&':
            left = self.eval(node.left, env)
            if not _is_truthy(left):
                return False
            return _is_truthy(self.eval(node.right, env))

        if op == '||':
            left = self.eval(node.left, env)
            if _is_truthy(left):
                return True
            return _is_truthy(self.eval(node.right, env))

        left = self.eval(node.left, env)
        right = self.eval(node.right, env)

        # Unwrap ownership
        left = _unwrap_owned(left)
        right = _unwrap_owned(right)

        try:
            if op == '+':
                if isinstance(left, str) or isinstance(right, str):
                    return _display(left) + _display(right)
                if isinstance(left, list) and isinstance(right, list):
                    return left + right
                if left is None:
                    return right
                if right is None:
                    return left
                return left + right

            if op == '-':
                return left - right

            if op == '*':
                if isinstance(left, str) and isinstance(right, (int, float)):
                    return left * int(right)
                if isinstance(left, (int, float)) and isinstance(right, str):
                    return right * int(left)
                if isinstance(left, list) and isinstance(right, int):
                    return left * right
                return left * right

            if op == '/':
                if right == 0:
                    raise CPPSDivisionByZero()
                result = left / right
                return result

            if op == '//':
                if right == 0:
                    raise CPPSDivisionByZero()
                return int(left // right)

            if op == '%':
                if right == 0:
                    raise CPPSDivisionByZero()
                return left % right

            if op == '**':
                return left ** right

            if op == '==':
                return left == right

            if op == '!=':
                return left != right

            if op == '<':
                return left < right

            if op == '>':
                return left > right

            if op == '<=':
                return left <= right

            if op == '>=':
                return left >= right

            if op == '&':
                if isinstance(left, int) and isinstance(right, int):
                    return left & right
                return _is_truthy(left) and _is_truthy(right)

            if op == '|':
                if isinstance(left, int) and isinstance(right, int):
                    return left | right
                return _is_truthy(left) or _is_truthy(right)

            if op == '^':
                if isinstance(left, int) and isinstance(right, int):
                    return left ^ right
                return _is_truthy(left) != _is_truthy(right)

            if op == '<<':
                return int(left) << int(right)

            if op == '>>':
                return int(left) >> int(right)

            if op == '<=>':
                if left < right:
                    return -1
                if left > right:
                    return 1
                return 0

        except CPPSPanic:
            raise
        except CPPSError:
            raise
        except ZeroDivisionError:
            raise CPPSDivisionByZero()
        except TypeError as e:
            if self.verbose:
                print(f"  [warn] Type error in binary op {op}: {e}")
            return None
        except Exception as e:
            if self.verbose:
                print(f"  [warn] Error in binary op {op}: {e}")
            return None

        return None

    def _exec_assign(self, node: Assign, env: Env) -> Any:
        """
        Execute assignment.
        Supports: = += -= *= /= %= **= &= |= ^= //=
        """
        val = self.eval(node.value, env)
        target = node.target
        op = node.op

        # Variable assignment
        if isinstance(target, VarRef):
            if op != '=':
                old = env.get(target.name) or 0
                old = _unwrap_owned(old)
                val = self._apply_aug(old, op, val)
            env.assign(target.name, val)
            return val

        # Field assignment: obj.field = val or @.field = val
        if isinstance(target, FieldAccess):
            obj = self.eval(target.obj, env)
            obj = _unwrap_owned(obj)
            if op != '=':
                old = self._get_field(obj, target.field) or 0
                old = _unwrap_owned(old)
                val = self._apply_aug(old, op, val)
            if isinstance(obj, CPPSInstance):
                obj.set(target.field, val)
            elif isinstance(obj, dict):
                obj[target.field] = val
            return val

        # Index assignment: arr[i] = val
        if isinstance(target, IndexAccess):
            obj = self.eval(target.obj, env)
            idx = self.eval(target.index, env)
            obj = _unwrap_owned(obj)
            idx = _unwrap_owned(idx)
            if op != '=':
                try:
                    old = obj[int(idx)] if isinstance(obj, (list, tuple)) else obj.get(idx, 0)
                    old = _unwrap_owned(old)
                    val = self._apply_aug(old, op, val)
                except (IndexError, KeyError, TypeError):
                    pass
            if isinstance(obj, list):
                try:
                    obj[int(idx)] = val
                except IndexError:
                    # Auto-extend
                    while len(obj) <= int(idx):
                        obj.append(None)
                    obj[int(idx)] = val
            elif isinstance(obj, dict):
                obj[idx] = val
            return val

        return val

    def _apply_aug(self, old: Any, op: str, val: Any) -> Any:
        """Apply augmented assignment operator."""
        val = _unwrap_owned(val)
        try:
            if op == '+=':
                if isinstance(old, str) or isinstance(val, str):
                    return _display(old) + _display(val)
                if isinstance(old, list) and isinstance(val, list):
                    return old + val
                return old + val
            if op == '-=':
                return old - val
            if op == '*=':
                return old * val
            if op == '/=':
                if val == 0:
                    raise CPPSDivisionByZero()
                return old / val
            if op == '%=':
                return old % val
            if op == '**=':
                return old ** val
            if op == '&=':
                return int(old) & int(val)
            if op == '|=':
                return int(old) | int(val)
            if op == '^=':
                return int(old) ^ int(val)
            if op == '//=':
                return int(old) // int(val)
        except CPPSDivisionByZero:
            raise
        except Exception:
            pass
        return val

    # ══════════════════════════════════════════════════════════════════════
    # STATEMENT EXECUTION
    # ══════════════════════════════════════════════════════════════════════

    def exec(self, node: Optional[ASTNode], env: Env) -> Any:
        """
        Execute một statement node.

        Args:
            node: ASTNode statement
            env: Scope hiện tại

        Returns:
            None (statements không trả về giá trị trực tiếp)

        Raises:
            ReturnException, BreakException, ContinueException, CPPSPanic
        """
        if node is None:
            return None

        # Program — execute all statements
        if isinstance(node, Program):
            for stmt in node.statements:
                self.exec(stmt, env)
            # Auto-call main() if defined
            if env.has('main'):
                self._exec_fn_call('main', [], env)
            return None

        # Module declaration
        if isinstance(node, ModuleDecl):
            self.current_module = node.name
            return None

        # Import statement (built-in modules pre-registered)
        if isinstance(node, ImportStmt):
            self._exec_import(node, env)
            return None

        # Export statement
        if isinstance(node, ExportStmt):
            return None

        # Variable declaration
        if isinstance(node, VarDecl):
            val = self.eval(node.value, env) if node.value else None
            if node.ownership:
                val = CPPSOwned(node.ownership, val)
            env.set(node.name, val)
            return None

        # Function definition
        if isinstance(node, FnDef):
            env.set(node.name, node)
            if self.verbose:
                print(f"  [def] Hàm '{node.name}' đã đăng ký")
            return None

        # Override declaration
        if isinstance(node, OverrideDecl):
            env.set(node.fn.name, node.fn)
            return None

        # Class definition
        if isinstance(node, ClassDef):
            self.classes[node.name] = node
            env.set(node.name, node)
            # Register static methods
            for stmt in node.body:
                fn_def = stmt.fn if isinstance(stmt, OverrideDecl) else stmt
                if isinstance(fn_def, FnDef) and fn_def.is_static:
                    sname = f"{node.name}::{fn_def.name}"
                    env.set(sname, fn_def)
            if self.verbose:
                print(f"  [def] Class '{node.name}' đã đăng ký")
            return None

        # Struct definition
        if isinstance(node, StructDef):
            self.structs[node.name] = node
            env.set(node.name, node)
            return None

        # Trait definition
        if isinstance(node, TraitDef):
            self.traits[node.name] = node
            env.set(node.name, node)
            return None

        # Impl block
        if isinstance(node, ImplBlock):
            if node.type_name not in self.impls:
                self.impls[node.type_name] = {}
            for method in node.methods:
                fn_def = method.fn if isinstance(method, OverrideDecl) else method
                if isinstance(fn_def, FnDef):
                    self.impls[node.type_name][fn_def.name] = fn_def
                    if self.verbose:
                        print(f"  [impl] {node.type_name}::{fn_def.name} đã đăng ký")
            return None

        # Return statement
        if isinstance(node, ReturnStmt):
            val = self.eval(node.value, env) if node.value else None
            raise ReturnException(val)

        # Break statement
        if isinstance(node, BreakStmt):
            raise BreakException(node.label)

        # Continue statement
        if isinstance(node, ContinueStmt):
            raise ContinueException(node.label)

        # Panic statement
        if isinstance(node, PanicStmt):
            msg = self.eval(node.message, env)
            raise CPPSPanic(str(msg) if msg is not None else 'explicit panic')

        # Pipe statement: ~> expr
        if isinstance(node, PipeStmt):
            val = self.eval(node.expr, env)
            # If it's a string, print it; otherwise just evaluate
            if isinstance(node.expr, FnCall):
                pass  # Already printed by the function
            return None

        # If statement
        if isinstance(node, IfStmt):
            cond = self.eval(node.condition, env)
            if _is_truthy(cond):
                child = env.child('if-then')
                for s in node.then_body:
                    self.exec(s, child)
            else:
                executed = False
                for elif_cond, elif_body in node.elif_clauses:
                    if _is_truthy(self.eval(elif_cond, env)):
                        child = env.child('if-elif')
                        for s in elif_body:
                            self.exec(s, child)
                        executed = True
                        break
                if not executed:
                    child = env.child('if-else')
                    for s in node.else_body:
                        self.exec(s, child)
            return None

        # For statement
        if isinstance(node, ForStmt):
            iterable = self.eval(node.iterable, env)
            iterable = _unwrap_owned(iterable)
            if iterable is None:
                return None
            if isinstance(iterable, CPPSChannel):
                # Iterate over channel
                while True:
                    val = iterable.try_recv()
                    if val is None:
                        break
                    child = env.child('for-ch')
                    child.set(node.var_name, val)
                    try:
                        for s in node.body:
                            self.exec(s, child)
                    except BreakException:
                        break
                    except ContinueException:
                        continue
                return None
            if not hasattr(iterable, '__iter__'):
                if self.verbose:
                    print(f"  [warn] For loop: {type(iterable)} không iterable")
                return None
            for item in iterable:
                child = env.child('for')
                child.set(node.var_name, item)
                try:
                    for s in node.body:
                        self.exec(s, child)
                except BreakException:
                    break
                except ContinueException:
                    continue
            return None

        # While statement
        if isinstance(node, WhileStmt):
            iteration = 0
            max_iter = 10_000_000  # Safety limit
            while _is_truthy(self.eval(node.condition, env)):
                iteration += 1
                if iteration > max_iter:
                    raise CPPSPanic(f"Vòng lặp vô hạn bị phát hiện (>{max_iter} lần)")
                child = env.child('while')
                try:
                    for s in node.body:
                        self.exec(s, child)
                except BreakException:
                    break
                except ContinueException:
                    continue
            return None

        # Pattern matching
        if isinstance(node, MatchStmt):
            return self._exec_match(node, env)

        # Try/catch
        if isinstance(node, TryCatch):
            return self._exec_try_catch(node, env)

        # Goroutine
        if isinstance(node, GoStmt):
            def run_goroutine():
                try:
                    self.eval(node.call, env.child('goroutine'))
                except CPPSPanic as e:
                    print(f"\n💥 Goroutine PANIC: {e.msg}", file=sys.stderr)
                except Exception as e:
                    if self.verbose:
                        print(f"  [goroutine error] {e}", file=sys.stderr)

            t = threading.Thread(target=run_goroutine, daemon=True)
            t.start()
            self._go_threads.append(t)
            return None

        # Macro invocation
        if isinstance(node, MacroInvoke):
            return self._exec_macro(node, env)

        # Reflect expression as statement
        if isinstance(node, ReflectExpr):
            return self._reflect(self.eval(node.target, env))

        # Expression node used as statement
        return self.eval(node, env)

    # ══════════════════════════════════════════════════════════════════════
    # FUNCTION CALLS
    # ══════════════════════════════════════════════════════════════════════

    def _exec_fn_call(self, name: str, arg_nodes: List[ASTNode],
                      env: Env, pre_args: Optional[List[Any]] = None) -> Any:
        """
        Execute function call by name.

        Args:
            name: Tên hàm (có thể bao gồm '::' namespace)
            arg_nodes: Danh sách argument nodes
            env: Scope hiện tại
            pre_args: Arguments đã evaluate trước (cho pipe)

        Returns:
            Kết quả hàm
        """
        args = list(pre_args or []) + [self.eval(a, env) for a in arg_nodes]

        # Check built-in functions first
        builtin = self.global_env.get(name)
        if callable(builtin) and not isinstance(builtin, (FnDef, ClassDef)):
            try:
                return builtin(*args)
            except CPPSPanic:
                raise
            except CPPSError:
                raise
            except Exception as e:
                if self.verbose:
                    print(f"  [builtin error] {name}: {e}")
                return None

        # Class instantiation / static method
        if '::' in name:
            result = self._exec_namespaced_call(name, args, env)
            if result is not None or name in self.classes:
                return result

        # User-defined function
        fn = env.get(name)
        if fn is not None:
            if isinstance(fn, FnDef):
                return self._call_fn(fn, args, env)
            if isinstance(fn, CPPSClosure):
                return self._call_closure(fn, args, env)
            if isinstance(fn, CPPSNativeFunction):
                return fn.call(args)
            if callable(fn):
                try:
                    return fn(*args)
                except CPPSPanic:
                    raise
                except Exception as e:
                    if self.verbose:
                        print(f"  [fn error] {name}: {e}")
                    return None
            # fn might be a value — return as-is
            return fn

        # Check in impls
        if '::' in name:
            result = self._exec_namespaced_call(name, args, env)
            return result

        if self.verbose:
            print(f"  [warn] Hàm '{name}' không tìm thấy")
        return None

    def _exec_namespaced_call(self, name: str, args: List[Any], env: Env) -> Any:
        """
        Execute namespaced call: TypeName::method(...) or std::io::println(...)

        Args:
            name: Full namespaced name
            args: Evaluated arguments
            env: Scope

        Returns:
            Result of call
        """
        parts = name.split('::')
        class_name = parts[0]
        method_name = parts[-1]

        # Class static method or constructor
        if class_name in self.classes:
            cls = self.classes[class_name]
            # Check for static method (not constructor)
            if method_name not in ('new', 'init', 'create', 'build'):
                for stmt in cls.body:
                    fn_def = stmt.fn if isinstance(stmt, OverrideDecl) else stmt
                    if isinstance(fn_def, FnDef) and fn_def.name == method_name:
                        # Check is_static or just call it as static
                        child = self.global_env.child(f'{class_name}::{method_name}')
                        for i, param in enumerate(fn_def.params):
                            child.set(param[0], args[i] if i < len(args) else None)
                        try:
                            for s in fn_def.body:
                                self.exec(s, child)
                        except ReturnException as e:
                            return e.value
                        return None
            # Constructor
            return self._instantiate(class_name, method_name, args, env)

        # Struct instantiation
        if class_name in self.structs:
            struct = self.structs[class_name]
            instance = CPPSInstance(class_name)
            for i, (fname, ftype) in enumerate(struct.fields):
                instance.set(fname, args[i] if i < len(args) else None)
            return instance

        # Registered function via full path
        fn = self.global_env.get(name)
        if fn is not None:
            if isinstance(fn, FnDef):
                return self._call_fn(fn, args, env)
            if callable(fn):
                try:
                    return fn(*args)
                except CPPSPanic:
                    raise
                except Exception:
                    return None

        return None

    def _call_fn(self, fn: FnDef, args: List[Any], caller_env: Env) -> Any:
        """
        Call a user-defined function.

        Args:
            fn: FnDef AST node
            args: Evaluated arguments
            caller_env: Caller's environment (for default arg eval)

        Returns:
            Return value of function
        """
        # Check call depth
        self._call_depth += 1
        if self._call_depth > self.max_depth:
            self._call_depth -= 1
            raise CPPSPanic(f"Stack overflow: đệ quy quá sâu (>{self.max_depth})")

        child = self.global_env.child(f'fn:{fn.name}')

        # Bind parameters
        for i, param in enumerate(fn.params):
            pname = param[0]
            default = param[3] if len(param) > 3 else None
            if i < len(args):
                val = args[i]
            elif default is not None:
                val = self.eval(default, caller_env)
            else:
                val = None
            child.set(pname, val)

        try:
            for stmt in fn.body:
                self.exec(stmt, child)
            return None
        except ReturnException as e:
            return e.value
        finally:
            self._call_depth -= 1

    def _call_closure(self, closure: CPPSClosure, args: List[Any], caller_env: Env) -> Any:
        """
        Call a closure (function + captured environment).

        Args:
            closure: CPPSClosure with fn_def and captured env
            args: Arguments
            caller_env: Caller's env (unused, captured env is used)

        Returns:
            Return value
        """
        self._call_depth += 1
        if self._call_depth > self.max_depth:
            self._call_depth -= 1
            raise CPPSPanic("Stack overflow trong closure")

        child = Env(parent=closure.captured_env, name=f'closure:{closure.name}')
        for i, param in enumerate(closure.fn_def.params):
            pname = param[0]
            child.set(pname, args[i] if i < len(args) else None)

        try:
            for stmt in closure.fn_def.body:
                self.exec(stmt, child)
            return None
        except ReturnException as e:
            return e.value
        finally:
            self._call_depth -= 1

    # ══════════════════════════════════════════════════════════════════════
    # CLASS INSTANTIATION
    # ══════════════════════════════════════════════════════════════════════

    def _instantiate(self, class_name: str, method: str,
                     args: List[Any], env: Env) -> CPPSInstance:
        """
        Instantiate a class.

        Args:
            class_name: Name of class
            method: Constructor method name (usually 'new')
            args: Constructor arguments
            env: Current environment

        Returns:
            New CPPSInstance
        """
        cls = self.classes.get(class_name)
        instance = CPPSInstance(class_name)

        # Inherit from parent classes
        if cls and cls.parents:
            for parent_name in cls.parents:
                parent_cls = self.classes.get(parent_name)
                if parent_cls:
                    parent_inst = self._instantiate(parent_name, 'new', [], env)
                    # Copy parent fields and methods
                    for k, v in parent_inst.fields.items():
                        instance.fields[k] = v

        # Register class body methods and fields
        if cls:
            for stmt in cls.body:
                fn_def = stmt.fn if isinstance(stmt, OverrideDecl) else stmt
                if isinstance(fn_def, FnDef):
                    instance.fields[f'__method_{fn_def.name}'] = fn_def
                elif isinstance(fn_def, VarDecl):
                    val = self.eval(fn_def.value, env) if fn_def.value else None
                    instance.fields[fn_def.name] = val

        # Register impl block methods
        impls = self.impls.get(class_name, {})
        for method_name, fn_def in impls.items():
            instance.fields[f'__method_{method_name}'] = fn_def

        # Also check parent impl blocks
        if cls and cls.parents:
            for parent_name in cls.parents:
                parent_impls = self.impls.get(parent_name, {})
                for method_name, fn_def in parent_impls.items():
                    key = f'__method_{method_name}'
                    if key not in instance.fields:
                        instance.fields[key] = fn_def

        # Call constructor: new, init, or create
        ctor_candidates = [
            f'__method_{method}',
            '__method_new',
            '__method_init',
            '__method_create',
        ]
        for ctor_key in ctor_candidates:
            ctor_fn = instance.fields.get(ctor_key)
            if isinstance(ctor_fn, FnDef):
                child = self.global_env.child(f'{class_name}.__init__')
                child.set('self', instance)
                for i, param in enumerate(ctor_fn.params):
                    pname = param[0]
                    child.set(pname, args[i] if i < len(args) else None)
                try:
                    for s in ctor_fn.body:
                        self.exec(s, child)
                except ReturnException:
                    pass
                break

        return instance

    # ══════════════════════════════════════════════════════════════════════
    # METHOD DISPATCH
    # ══════════════════════════════════════════════════════════════════════

    def _exec_method(self, obj: Any, method: str, args: List[Any], env: Env) -> Any:
        """
        Dispatch method call on an object.

        Args:
            obj: Target object
            method: Method name
            args: Arguments
            env: Current scope

        Returns:
            Method return value
        """
        obj = _unwrap_owned(obj)

        # CPPSInstance method call
        if isinstance(obj, CPPSInstance):
            fn = obj.get_method(method)
            if isinstance(fn, FnDef):
                child = self.global_env.child(f'{obj.class_name}.{method}')
                child.set('self', obj)
                for i, param in enumerate(fn.params):
                    child.set(param[0], args[i] if i < len(args) else None)
                try:
                    for stmt in fn.body:
                        self.exec(stmt, child)
                    return None
                except ReturnException as e:
                    return e.value

            # Try impl block
            impl_fn = self.impls.get(obj.class_name, {}).get(method)
            if impl_fn:
                child = self.global_env.child(f'{obj.class_name}(impl).{method}')
                child.set('self', obj)
                for i, param in enumerate(impl_fn.params):
                    child.set(param[0], args[i] if i < len(args) else None)
                try:
                    for stmt in impl_fn.body:
                        self.exec(stmt, child)
                    return None
                except ReturnException as e:
                    return e.value

            # Parent class impls
            cls = self.classes.get(obj.class_name)
            if cls and cls.parents:
                for parent_name in cls.parents:
                    parent_fn = self.impls.get(parent_name, {}).get(method)
                    if parent_fn:
                        child = self.global_env.child(f'{parent_name}(inherited).{method}')
                        child.set('self', obj)
                        for i, param in enumerate(parent_fn.params):
                            child.set(param[0], args[i] if i < len(args) else None)
                        try:
                            for stmt in parent_fn.body:
                                self.exec(stmt, child)
                            return None
                        except ReturnException as e:
                            return e.value

            # Field as callable
            field_val = obj.get(method)
            if callable(field_val):
                return field_val(*args)
            if isinstance(field_val, FnDef):
                return self._call_fn(field_val, args, env)
            if isinstance(field_val, CPPSClosure):
                return self._call_closure(field_val, args, env)

            if self.verbose:
                print(f"  [warn] Method '{method}' không tìm thấy trên {obj.class_name}")
            return None

        # List methods
        if isinstance(obj, list):
            return self._list_method(obj, method, args, env)

        # Dict/Map methods
        if isinstance(obj, dict):
            return self._map_method(obj, method, args)

        # Set methods
        if isinstance(obj, set):
            return self._set_method(obj, method, args)

        # String methods
        if isinstance(obj, str):
            return self._string_method(obj, method, args)

        # Result methods
        if isinstance(obj, CPPSResult):
            return self._result_method(obj, method, args, env)

        # Channel methods
        if isinstance(obj, CPPSChannel):
            if method == 'send':
                obj.send(args[0] if args else None)
                return None
            if method == 'recv':
                return obj.recv()
            if method == 'try_recv':
                return obj.try_recv()
            if method == 'close':
                obj.close()
                return None
            if method == 'len':
                return obj.len()
            if method == 'is_empty':
                return obj.is_empty()
            if method == 'is_closed':
                return obj.is_closed()

        # Callable as object
        if callable(obj):
            return obj(*args)

        if self.verbose:
            print(f"  [warn] Method '{method}' không áp dụng được cho {_type_of(obj)}")
        return None

    def _list_method(self, lst: list, method: str, args: List[Any], env: Env) -> Any:
        """Built-in methods cho list."""
        a = [_unwrap_owned(x) for x in args]

        if method == 'push' or method == 'append':
            lst.append(a[0] if a else None)
            return lst
        if method == 'pop':
            return lst.pop() if lst else None
        if method == 'pop_front':
            return lst.pop(0) if lst else None
        if method == 'pop_at':
            idx = int(a[0]) if a else -1
            return lst.pop(idx) if -len(lst) <= idx < len(lst) else None
        if method == 'len':
            return len(lst)
        if method == 'is_empty':
            return len(lst) == 0
        if method == 'contains':
            return a[0] in lst if a else False
        if method == 'index_of':
            try:
                return lst.index(a[0]) if a else -1
            except ValueError:
                return -1
        if method == 'remove':
            if a and a[0] in lst:
                lst.remove(a[0])
            return lst
        if method == 'remove_at':
            if a:
                try:
                    lst.pop(int(a[0]))
                except IndexError:
                    pass
            return lst
        if method == 'insert':
            if len(a) >= 2:
                lst.insert(int(a[0]), a[1])
            return lst
        if method == 'clear':
            lst.clear()
            return lst
        if method == 'reverse':
            lst.reverse()
            return lst
        if method == 'sort':
            try:
                reverse = bool(a[0]) if a else False
                lst.sort(reverse=reverse)
            except TypeError:
                pass
            return lst
        if method == 'sorted':
            import copy
            new_lst = copy.copy(lst)
            try:
                new_lst.sort()
            except TypeError:
                pass
            return new_lst
        if method == 'slice':
            start = int(a[0]) if a else 0
            end = int(a[1]) if len(a) > 1 else len(lst)
            step = int(a[2]) if len(a) > 2 else 1
            return lst[start:end:step]
        if method == 'get':
            idx = int(a[0]) if a else 0
            if -len(lst) <= idx < len(lst):
                return lst[idx]
            return a[1] if len(a) > 1 else None
        if method == 'set':
            if len(a) >= 2:
                try:
                    lst[int(a[0])] = a[1]
                except IndexError:
                    pass
            return lst
        if method == 'join':
            sep = str(a[0]) if a else ''
            return sep.join(_display(x) for x in lst)
        if method == 'extend':
            if a and isinstance(a[0], list):
                lst.extend(a[0])
            return lst
        if method == 'map':
            fn = a[0] if a else None
            if isinstance(fn, FnDef):
                return [self._call_fn(fn, [x], env) for x in lst]
            if isinstance(fn, CPPSClosure):
                return [self._call_closure(fn, [x], env) for x in lst]
            if callable(fn):
                return [fn(x) for x in lst]
            return lst
        if method == 'filter':
            fn = a[0] if a else None
            if isinstance(fn, FnDef):
                return [x for x in lst if _is_truthy(self._call_fn(fn, [x], env))]
            if isinstance(fn, CPPSClosure):
                return [x for x in lst if _is_truthy(self._call_closure(fn, [x], env))]
            if callable(fn):
                return [x for x in lst if _is_truthy(fn(x))]
            return lst
        if method == 'reduce':
            fn = a[0] if a else None
            init = a[1] if len(a) > 1 else None
            if not lst:
                return init
            acc = init if init is not None else lst[0]
            items = lst if init is not None else lst[1:]
            for x in items:
                if isinstance(fn, FnDef):
                    acc = self._call_fn(fn, [acc, x], env)
                elif isinstance(fn, CPPSClosure):
                    acc = self._call_closure(fn, [acc, x], env)
                elif callable(fn):
                    acc = fn(acc, x)
            return acc
        if method == 'each' or method == 'for_each':
            fn = a[0] if a else None
            for x in lst:
                if isinstance(fn, FnDef):
                    self._call_fn(fn, [x], env)
                elif isinstance(fn, CPPSClosure):
                    self._call_closure(fn, [x], env)
                elif callable(fn):
                    fn(x)
            return None
        if method == 'flat' or method == 'flatten':
            result = []
            for x in lst:
                if isinstance(x, (list, tuple)):
                    result.extend(x)
                else:
                    result.append(x)
            return result
        if method == 'unique' or method == 'dedup':
            seen = []
            seen_set = set()
            for x in lst:
                key = repr(x)
                if key not in seen_set:
                    seen_set.add(key)
                    seen.append(x)
            return seen
        if method == 'first':
            return lst[0] if lst else None
        if method == 'last':
            return lst[-1] if lst else None
        if method == 'sum':
            try:
                return sum(lst)
            except TypeError:
                return None
        if method == 'max':
            try:
                return max(lst) if lst else None
            except TypeError:
                return None
        if method == 'min':
            try:
                return min(lst) if lst else None
            except TypeError:
                return None
        if method == 'count':
            if a:
                return lst.count(a[0])
            return len(lst)
        if method == 'any':
            fn = a[0] if a else None
            if fn:
                if isinstance(fn, FnDef):
                    return any(_is_truthy(self._call_fn(fn, [x], env)) for x in lst)
                if callable(fn):
                    return any(_is_truthy(fn(x)) for x in lst)
            return any(_is_truthy(x) for x in lst)
        if method == 'all':
            fn = a[0] if a else None
            if fn:
                if isinstance(fn, FnDef):
                    return all(_is_truthy(self._call_fn(fn, [x], env)) for x in lst)
                if callable(fn):
                    return all(_is_truthy(fn(x)) for x in lst)
            return all(_is_truthy(x) for x in lst)
        if method == 'copy' or method == 'clone':
            return lst.copy()
        if method == 'to_string':
            return _display(lst)
        if method == 'zip':
            if a and isinstance(a[0], list):
                return [(x, y) for x, y in zip(lst, a[0])]
            return list(zip(lst))
        if method == 'enumerate':
            start = int(a[0]) if a else 0
            return [(i + start, v) for i, v in enumerate(lst)]
        if method == 'take':
            n = int(a[0]) if a else 0
            return lst[:n]
        if method == 'skip' or method == 'drop':
            n = int(a[0]) if a else 0
            return lst[n:]
        if method == 'chunk':
            size = int(a[0]) if a else 1
            return [lst[i:i+size] for i in range(0, len(lst), size)]
        if method == 'concat':
            result = lst.copy()
            for other in a:
                if isinstance(other, list):
                    result.extend(other)
            return result

        return None

    def _map_method(self, d: dict, method: str, args: List[Any]) -> Any:
        """Built-in methods cho dict/Map."""
        a = [_unwrap_owned(x) for x in args]

        if method == 'insert' or method == 'set' or method == 'put':
            if len(a) >= 2:
                d[a[0]] = a[1]
            return d
        if method == 'get':
            default = a[1] if len(a) > 1 else None
            return d.get(a[0], default) if a else None
        if method == 'remove' or method == 'delete':
            if a:
                d.pop(a[0], None)
            return d
        if method == 'contains' or method == 'has' or method == 'contains_key':
            return a[0] in d if a else False
        if method == 'contains_value':
            return a[0] in d.values() if a else False
        if method == 'keys':
            return list(d.keys())
        if method == 'values':
            return list(d.values())
        if method == 'entries' or method == 'items':
            return [[k, v] for k, v in d.items()]
        if method == 'len':
            return len(d)
        if method == 'is_empty':
            return len(d) == 0
        if method == 'clear':
            d.clear()
            return d
        if method == 'merge':
            if a and isinstance(a[0], dict):
                d.update(a[0])
            return d
        if method == 'clone' or method == 'copy':
            return d.copy()
        if method == 'to_list':
            return [[k, v] for k, v in d.items()]
        if method == 'get_or_insert':
            key = a[0] if a else None
            default = a[1] if len(a) > 1 else None
            if key not in d:
                d[key] = default
            return d[key]
        if method == 'map_values':
            fn = a[0] if a else None
            if callable(fn):
                return {k: fn(v) for k, v in d.items()}
            return d
        return None

    def _set_method(self, s: set, method: str, args: List[Any]) -> Any:
        """Built-in methods cho set."""
        a = [_unwrap_owned(x) for x in args]

        if method == 'add' or method == 'insert':
            if a:
                s.add(a[0])
            return s
        if method == 'remove' or method == 'discard':
            if a:
                s.discard(a[0])
            return s
        if method == 'contains' or method == 'has':
            return a[0] in s if a else False
        if method == 'len':
            return len(s)
        if method == 'is_empty':
            return len(s) == 0
        if method == 'clear':
            s.clear()
            return s
        if method == 'union':
            return s | (a[0] if a else set())
        if method == 'intersect' or method == 'intersection':
            return s & (a[0] if a else set())
        if method == 'diff' or method == 'difference':
            return s - (a[0] if a else set())
        if method == 'sym_diff' or method == 'symmetric_difference':
            return s ^ (a[0] if a else set())
        if method == 'is_subset':
            return s.issubset(a[0]) if a else True
        if method == 'is_superset':
            return s.issuperset(a[0]) if a else True
        if method == 'to_list':
            return list(s)
        if method == 'to_sorted_list':
            return sorted(list(s), key=str)
        return None

    def _string_method(self, s: str, method: str, args: List[Any]) -> Any:
        """Built-in methods cho string."""
        a = [_unwrap_owned(x) for x in args]

        if method == 'len':
            return len(s)
        if method == 'to_upper' or method == 'upper':
            return s.upper()
        if method == 'to_lower' or method == 'lower':
            return s.lower()
        if method == 'trim':
            return s.strip()
        if method == 'trim_start' or method == 'lstrip':
            return s.lstrip()
        if method == 'trim_end' or method == 'rstrip':
            return s.rstrip()
        if method == 'split':
            sep = str(a[0]) if a else None
            maxsplit = int(a[1]) if len(a) > 1 else -1
            if maxsplit >= 0:
                return s.split(sep, maxsplit)
            return s.split(sep)
        if method == 'replace':
            if len(a) >= 2:
                old, new = str(a[0]), str(a[1])
                count = int(a[2]) if len(a) > 2 else -1
                if count >= 0:
                    return s.replace(old, new, count)
                return s.replace(old, new)
            return s
        if method == 'contains':
            return str(a[0]) in s if a else False
        if method == 'starts_with' or method == 'startswith':
            return s.startswith(str(a[0])) if a else False
        if method == 'ends_with' or method == 'endswith':
            return s.endswith(str(a[0])) if a else False
        if method == 'index_of' or method == 'find':
            target = str(a[0]) if a else ''
            return s.find(target)
        if method == 'last_index_of' or method == 'rfind':
            target = str(a[0]) if a else ''
            return s.rfind(target)
        if method == 'slice' or method == 'substring':
            start = int(a[0]) if a else 0
            end = int(a[1]) if len(a) > 1 else len(s)
            return s[start:end]
        if method == 'chars':
            return list(s)
        if method == 'lines':
            return s.splitlines()
        if method == 'parse_int' or method == 'to_int':
            try:
                return int(s)
            except ValueError:
                return CPPSResult(False, f"Không parse được '{s}' sang int")
        if method == 'parse_float' or method == 'to_float':
            try:
                return float(s)
            except ValueError:
                return CPPSResult(False, f"Không parse được '{s}' sang float")
        if method == 'repeat':
            return s * (int(a[0]) if a else 1)
        if method == 'is_empty':
            return len(s) == 0
        if method == 'format':
            tmpl = s
            for x in a:
                tmpl = tmpl.replace('{}', _display(x), 1)
            return tmpl
        if method == 'to_bytes':
            return list(s.encode('utf-8'))
        if method == 'bytes':
            return list(s.encode('utf-8'))
        if method == 'is_digit' or method == 'is_numeric':
            return s.isdigit()
        if method == 'is_alpha':
            return s.isalpha()
        if method == 'is_alnum' or method == 'is_alphanumeric':
            return s.isalnum()
        if method == 'is_upper':
            return s.isupper()
        if method == 'is_lower':
            return s.islower()
        if method == 'count':
            sub = str(a[0]) if a else ''
            return s.count(sub)
        if method == 'pad_left' or method == 'rjust':
            width = int(a[0]) if a else len(s)
            char = str(a[1]) if len(a) > 1 else ' '
            return s.rjust(width, char)
        if method == 'pad_right' or method == 'ljust':
            width = int(a[0]) if a else len(s)
            char = str(a[1]) if len(a) > 1 else ' '
            return s.ljust(width, char)
        if method == 'center':
            width = int(a[0]) if a else len(s)
            char = str(a[1]) if len(a) > 1 else ' '
            return s.center(width, char)
        if method == 'to_string' or method == 'to_str':
            return s
        if method == 'encode':
            encoding = str(a[0]) if a else 'utf-8'
            try:
                return list(s.encode(encoding))
            except LookupError:
                return list(s.encode('utf-8'))
        if method == 'code_point':
            return ord(s[0]) if s else 0
        if method == 'capitalize':
            return s.capitalize()
        if method == 'title':
            return s.title()
        return None

    def _result_method(self, r: CPPSResult, method: str, args: List[Any], env: Env) -> Any:
        """Built-in methods cho Result type."""
        a = [_unwrap_owned(x) for x in args]

        if method == 'is_ok':
            return r.ok
        if method == 'is_err':
            return not r.ok
        if method == 'ok':
            return r.value if r.ok else None
        if method == 'err':
            return r.value if not r.ok else None
        if method == 'unwrap':
            return r.unwrap()
        if method == 'unwrap_or':
            return r.unwrap_or(a[0] if a else None)
        if method == 'unwrap_or_else':
            if a:
                fn = a[0]
                if not r.ok:
                    if isinstance(fn, FnDef):
                        return self._call_fn(fn, [r.value], env)
                    if callable(fn):
                        return fn(r.value)
            return r.value if r.ok else None
        if method == 'map':
            if r.ok and a:
                fn = a[0]
                if isinstance(fn, FnDef):
                    return CPPSResult(True, self._call_fn(fn, [r.value], env))
                if isinstance(fn, CPPSClosure):
                    return CPPSResult(True, self._call_closure(fn, [r.value], env))
                if callable(fn):
                    return CPPSResult(True, fn(r.value))
            return r
        if method == 'map_err':
            if not r.ok and a:
                fn = a[0]
                if isinstance(fn, FnDef):
                    return CPPSResult(False, self._call_fn(fn, [r.value], env))
                if callable(fn):
                    return CPPSResult(False, fn(r.value))
            return r
        if method == 'and_then':
            if r.ok and a:
                fn = a[0]
                if isinstance(fn, FnDef):
                    result = self._call_fn(fn, [r.value], env)
                elif isinstance(fn, CPPSClosure):
                    result = self._call_closure(fn, [r.value], env)
                elif callable(fn):
                    result = fn(r.value)
                else:
                    result = None
                if isinstance(result, CPPSResult):
                    return result
                return CPPSResult(True, result)
            return r
        if method == 'or_else':
            if not r.ok and a:
                fn = a[0]
                if isinstance(fn, FnDef):
                    result = self._call_fn(fn, [r.value], env)
                elif callable(fn):
                    result = fn(r.value)
                else:
                    result = None
                if isinstance(result, CPPSResult):
                    return result
                return CPPSResult(True, result)
            return r
        if method == 'value':
            return r.value
        if method == 'to_string' or method == 'to_str':
            return repr(r)
        return None

    # ══════════════════════════════════════════════════════════════════════
    # PATTERN MATCHING
    # ══════════════════════════════════════════════════════════════════════

    def _exec_match(self, node: MatchStmt, env: Env) -> Any:
        """Execute pattern match statement."""
        val = self.eval(node.value, env)
        val = _unwrap_owned(val)

        for arm in node.arms:
            bindings: Dict[str, Any] = {}
            if self._match_pattern(arm.pattern, val, bindings):
                # Check guard
                if arm.guard:
                    child = env.child('match-guard')
                    for k, v in bindings.items():
                        child.set(k, v)
                    if not _is_truthy(self.eval(arm.guard, child)):
                        continue

                # Execute arm body
                child = env.child('match-arm')
                for k, v in bindings.items():
                    child.set(k, v)
                try:
                    for s in arm.body:
                        self.exec(s, child)
                except ReturnException:
                    raise
                return None

        return None

    def _match_pattern(self, pattern: Any, value: Any,
                       bindings: Dict[str, Any]) -> bool:
        """
        Try to match value against pattern.

        Args:
            pattern: Pattern node
            value: Value to match
            bindings: Dict to store variable bindings

        Returns:
            True if matches, False otherwise
        """
        value = _unwrap_owned(value)

        if isinstance(pattern, WildcardPattern):
            return True

        if isinstance(pattern, LiteralPattern):
            pval = pattern.value
            if isinstance(pval, bool) and isinstance(value, bool):
                return pval == value
            if isinstance(pval, (int, float)) and isinstance(value, (int, float)):
                return pval == value
            return pval == value

        if isinstance(pattern, BindingPattern):
            bindings[pattern.name] = value
            return True

        if isinstance(pattern, TuplePattern):
            if not isinstance(value, tuple):
                if isinstance(value, list) and len(value) == len(pattern.elements):
                    for p, v in zip(pattern.elements, value):
                        if not self._match_pattern(p, v, bindings):
                            return False
                    return True
                return False
            if len(value) != len(pattern.elements):
                return False
            for p, v in zip(pattern.elements, value):
                if not self._match_pattern(p, v, bindings):
                    return False
            return True

        if isinstance(pattern, RangePattern):
            try:
                lo = pattern.lo
                hi = pattern.hi
                if isinstance(value, (int, float)):
                    if pattern.inclusive:
                        return lo <= value <= hi
                    return lo <= value < hi
            except (TypeError, ValueError):
                pass
            return False

        if isinstance(pattern, OrPattern):
            for p in pattern.patterns:
                b = {}
                if self._match_pattern(p, value, b):
                    bindings.update(b)
                    return True
            return False

        if isinstance(pattern, EnumPattern):
            # Ok(x) / Err(x) / Some(x) etc.
            if pattern.variant in ('Ok', 'Some'):
                if isinstance(value, CPPSResult) and value.ok:
                    if pattern.inner:
                        return self._match_pattern(pattern.inner, value.value, bindings)
                    return True
                if not isinstance(value, CPPSResult) and pattern.variant == 'Some':
                    if value is not None:
                        if pattern.inner:
                            return self._match_pattern(pattern.inner, value, bindings)
                        return True
            if pattern.variant in ('Err', 'None', 'none'):
                if isinstance(value, CPPSResult) and not value.ok:
                    if pattern.inner:
                        return self._match_pattern(pattern.inner, value.value, bindings)
                    return True
                if value is None and pattern.variant in ('None', 'none'):
                    return True
            # Generic variant matching
            if isinstance(value, CPPSInstance) and value.class_name == pattern.variant:
                return True
            return False

        if isinstance(pattern, StructPattern):
            if not isinstance(value, (CPPSInstance, dict)):
                return False
            for fname, fpat in pattern.fields:
                if isinstance(value, CPPSInstance):
                    fval = value.get(fname)
                elif isinstance(value, dict):
                    fval = value.get(fname)
                else:
                    return False
                if fpat is not None:
                    b = {}
                    if not self._match_pattern(fpat, fval, b):
                        return False
                    bindings.update(b)
                else:
                    bindings[fname] = fval
            return True

        if isinstance(pattern, GuardedPattern):
            if not self._match_pattern(pattern.pattern, value, bindings):
                return False
            env = Env()
            for k, v in bindings.items():
                env.set(k, v)
            return _is_truthy(self.eval(pattern.guard, env))

        # Default: no match
        return False

    # ══════════════════════════════════════════════════════════════════════
    # TRY/CATCH
    # ══════════════════════════════════════════════════════════════════════

    def _exec_try_catch(self, node: TryCatch, env: Env) -> Any:
        """Execute try/catch/finally block."""
        try:
            child = env.child('try')
            for s in node.try_body:
                self.exec(s, child)
        except (CPPSPanic, CPPSError) as e:
            child = env.child('catch')
            child.set(node.catch_var, str(e))
            for s in node.catch_body:
                self.exec(s, child)
        except ReturnException:
            raise
        except BreakException:
            raise
        except ContinueException:
            raise
        except Exception as e:
            child = env.child('catch')
            child.set(node.catch_var, str(e))
            for s in node.catch_body:
                self.exec(s, child)
        finally:
            if node.finally_body:
                child = env.child('finally')
                for s in node.finally_body:
                    self.exec(s, child)

        return None

    # ══════════════════════════════════════════════════════════════════════
    # MACROS
    # ══════════════════════════════════════════════════════════════════════

    def _exec_macro(self, node: MacroInvoke, env: Env) -> Any:
        """Execute macro invocation."""
        args = [self.eval(a, env) for a in node.args]

        if node.kind == 'macro_tok':
            # Token-level macro
            arg_str = ', '.join(_display(a) for a in args)
            print(f"[MACRO_TOK {node.name}] ({arg_str})")
            return None

        if node.kind == 'macro_ast':
            # AST-level macro (code generation)
            arg_str = ', '.join(_display(a) for a in args)
            print(f"[MACRO_AST {node.name}] ({arg_str})")
            return None

        return None

    # ══════════════════════════════════════════════════════════════════════
    # REFLECTION
    # ══════════════════════════════════════════════════════════════════════

    def _reflect(self, target: Any) -> Dict[str, Any]:
        """
        Reflection: introspect a value.

        Args:
            target: Any CP+* value

        Returns:
            Dict với thông tin về value
        """
        target = _unwrap_owned(target)

        if isinstance(target, CPPSInstance):
            return {
                'type': target.class_name,
                'fields': {k: _display(v) for k, v in target.fields.items()
                          if not k.startswith('__method_')},
                'methods': target.method_names(),
                'parent': None,
            }

        if isinstance(target, FnDef):
            return {
                'type': 'Function',
                'name': target.name,
                'params': [(p[0], p[1]) for p in target.params],
                'return_type': target.return_type,
                'is_static': target.is_static,
                'is_async': getattr(target, 'is_async', False),
            }

        if isinstance(target, CPPSClosure):
            return {
                'type': 'Closure',
                'name': target.name,
                'params': [(p[0], p[1]) for p in target.fn_def.params],
                'return_type': target.fn_def.return_type,
            }

        if isinstance(target, list):
            return {
                'type': 'List',
                'len': len(target),
                'element_type': _type_of(target[0]) if target else 'unknown',
            }

        if isinstance(target, dict):
            return {
                'type': 'Map',
                'len': len(target),
                'keys': list(target.keys())[:10],
            }

        if isinstance(target, CPPSResult):
            return {
                'type': 'Result',
                'ok': target.ok,
                'value_type': _type_of(target.value),
                'value': _display(target.value),
            }

        if isinstance(target, CPPSChannel):
            return {
                'type': 'Channel',
                'capacity': target.capacity,
                'len': target.len(),
                'closed': target.is_closed(),
            }

        return {
            'type': _type_of(target),
            'value': _display(target),
            'raw': repr(target),
        }

    # ══════════════════════════════════════════════════════════════════════
    # MODULE IMPORT
    # ══════════════════════════════════════════════════════════════════════

    def _exec_import(self, node: ImportStmt, env: Env) -> None:
        """
        Execute import statement.
        Built-in modules đã pre-registered, không cần làm gì thêm.
        Có thể mở rộng để load external .cpps files.
        """
        for mod_path in node.module:
            # Built-in modules: std::io, std::math, std::collections, ...
            if mod_path.startswith('std::') or mod_path.startswith('std.'):
                continue  # Already available

            # Try to load as .cpps file
            file_path = mod_path.replace('::', '/').replace('.', '/') + '.cpps'
            if os.path.exists(file_path):
                try:
                    from lexer import tokenize
                    from parser import Parser as Prsr
                    with open(file_path, 'r', encoding='utf-8') as f:
                        source = f.read()
                    tokens = tokenize(source, file_path)
                    ast = Prsr(tokens, file_path).parse()
                    module_env = Env(parent=self.global_env, name=f'module:{mod_path}')
                    for stmt in ast.statements:
                        self.exec(stmt, module_env)
                    # Export to parent env
                    for name, val in module_env._vars.items():
                        env.set(name, val)
                    if self.verbose:
                        print(f"  [import] Đã load module '{mod_path}' từ {file_path}")
                except Exception as e:
                    if self.verbose:
                        print(f"  [warn] Không thể load module '{mod_path}': {e}")

    # ══════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════

    def execute(self, ast: Program) -> int:
        """
        Execute full program.

        Args:
            ast: Program AST node (root)

        Returns:
            Exit code (0 = success)
        """
        try:
            self.exec(ast, self.global_env)

            # Wait for goroutines to finish
            for t in self._go_threads:
                t.join(timeout=5.0)

            return 0

        except CPPSPanic as e:
            print(f"\n💥 PANIC: {e.msg}", file=sys.stderr)
            return 1

        except ReturnException as e:
            # Top-level return (from main or script mode)
            if isinstance(e.value, int):
                return e.value
            return 0

        except KeyboardInterrupt:
            print("\n^C Ngắt bởi người dùng", file=sys.stderr)
            return 130

        except RecursionError:
            print("\n💥 Stack overflow: đệ quy quá sâu", file=sys.stderr)
            return 1

    def run_source(self, source: str, filename: str = '<script>') -> int:
        """
        Convenience method: tokenize, parse, và execute.

        Args:
            source: Source code CP+*
            filename: Tên file (cho error messages)

        Returns:
            Exit code
        """
        from lexer import tokenize
        from parser import Parser as Prsr

        tokens = tokenize(source, filename)
        ast = Prsr(tokens, filename).parse()

        if self.verbose:
            print(f"[execute] {len(tokens)} tokens, "
                  f"{len(ast.statements)} top-level statements")

        return self.execute(ast)

    def eval_expr(self, source: str) -> Any:
        """
        Evaluate single expression (for REPL).

        Args:
            source: Expression source code

        Returns:
            Evaluated value
        """
        from lexer import tokenize
        from parser import Parser as Prsr

        tokens = tokenize(source)
        parser = Prsr(tokens)
        expr = parser.parse_expr()
        if expr is None:
            return None
        return self.eval(expr, self.global_env)


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def run(source: str, filename: str = '<script>', verbose: bool = False) -> int:
    """
    Tokenize, parse, và execute CP+* source code.

    Args:
        source: Source code
        filename: Tên file
        verbose: Chế độ verbose

    Returns:
        Exit code (0 = success)
    """
    interp = Interpreter(verbose=verbose)
    return interp.run_source(source, filename)


def run_file(filepath: str, verbose: bool = False) -> int:
    """
    Đọc và execute file .cpps.

    Args:
        filepath: Đường dẫn file
        verbose: Chế độ verbose

    Returns:
        Exit code
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        return run(source, filepath, verbose)
    except FileNotFoundError:
        print(f"❌ File không tìm thấy: {filepath}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Lỗi: {e}", file=sys.stderr)
        return 1


def create_repl_interpreter() -> Interpreter:
    """
    Tạo Interpreter dùng cho REPL.
    Giữ state giữa các lần thực thi.

    Returns:
        Interpreter instance
    """
    return Interpreter(verbose=False)


# ══════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════════════════════

def _run_tests():
    """Chạy test tự động cho Interpreter."""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  CP+* Interpreter — Self Test                            ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    test_cases = [
        # (description, source, expected_output)
        ("Hello World", '~> io::println("Hello, World!")', "Hello, World!"),
        ("Variable binding", 'x := 42\n~> io::println("{}", x)', "42"),
        ("Arithmetic", 'result := 3 + 4 * 2\n~> io::println("{}", result)', "11"),
        ("String concat", 's := "Hello" + " " + "World"\n~> io::println("{}", s)', "Hello World"),
        ("Boolean logic", 'a := true\nb := false\n~> io::println("{}", a && !b)', "true"),
        ("Comparison", 'x := 10\n~> io::println("{}", x > 5)', "true"),
        ("If/else", '?? 3 > 2 ** { ~> io::println("yes") } -- else ** { ~> io::println("no") }', "yes"),
        ("For loop", '<> i :: [1, 2, 3] ** { ~> io::println("{}", i) }', "1\n2\n3"),
        ("While loop", 'i := 0\nwhile i < 3 ** { ~> io::println("{}", i)\ni += 1 }', "0\n1\n2"),
        ("Function", '++ double <~ (x: int) -> int ** { <- x * 2 }\n~> io::println("{}", double(21))', "42"),
        ("Recursion", '++ fact <~ (n: int) -> int ** { ?? n <= 1 ** { <- 1 } -- else ** { <- n * fact(n - 1) } }\n~> io::println("{}", fact(5))', "120"),
        ("List ops", 'lst := [1, 2, 3]\n~> io::println("{}", lst:len())', "3"),
        ("Map ops", 'dict := {name: "Alice", age: 30}\n~> io::println("{}", dict:get("name"))', "Alice"),
        ("Pattern match", '?~ 42 { 1 => { ~> io::println("one") }, 42 => { ~> io::println("forty-two") }, _ => { ~> io::println("other") } }', "forty-two"),
        ("Try/catch", 'try ** { !! "test error" } catch (e) ** { ~> io::println("caught: {}", e) }', "caught: test error"),
        ("Result Ok", 'r := Ok(42)\n~> io::println("{}", r:unwrap())', "42"),
        ("Result Err", 'r := Err("oops")\n~> io::println("{}", r:unwrap_or(0))', "0"),
        ("Closure", '++ make_adder <~ (n: int) -> int ** { <- n + 10 }\nadder := make_adder\n~> io::println("{}", adder(5))', "15"),
        ("Class basic", 'class Dog -> { name :: string = "Rex"\n++ speak <~ () ** { ~> io::println("{} says Woof!", @.name) } }\ndog := Dog::new()\ndog:speak()', "Rex says Woof!"),
    ]

    import io
    from contextlib import redirect_stdout

    passed = 0
    failed = 0

    for desc, source, expected in test_cases:
        f = io.StringIO()
        try:
            with redirect_stdout(f):
                interp = Interpreter()
                interp.run_source(source, 'test.cpps')
            output = f.getvalue().rstrip('\n')
            if output == expected:
                passed += 1
                print(f"  ✅ {desc:<30} → {expected!r}")
            else:
                failed += 1
                print(f"  ❌ {desc:<30}")
                print(f"     Expected: {expected!r}")
                print(f"     Actual:   {output!r}")
        except Exception as e:
            failed += 1
            print(f"  ❌ {desc:<30} → Exception: {e}")

    print()
    print(f"Results: {passed}/{len(test_cases)} passed, {failed} failed")
    print()

    # OOP test
    print("=== OOP Comprehensive Test ===")
    oop_source = '''
class Animal -> {
    name :: mut string = "Unknown"
    sound :: string = "..."

    ++ new <~ (n: string) ** {
        @.name = n
    }

    ++ speak <~ () ** {
        ~> io::println("{} says: {}", @.name, @.sound)
    }

    ++ get_name <~ () -> string ** {
        <- @.name
    }
}

class Dog : Animal -> {
    breed :: string = "Mixed"

    ++ new <~ (n: string, b: string) ** {
        @.name = n
        @.breed = b
        @.sound = "Woof!"
    }

    ++ info <~ () -> string ** {
        <- @.name
    }
}

class Cat : Animal -> {
    indoor :: bool = true

    ++ new <~ (n: string) ** {
        @.name = n
        @.sound = "Meow!"
    }
}

dog := Dog::new("Rex", "German Shepherd")
cat := Cat::new("Whiskers")

dog:speak()
cat:speak()
~> io::println("Dog breed: {}", dog.breed)
~> io::println("Cat indoor: {}", cat.indoor)
'''
    f = io.StringIO()
    with redirect_stdout(f):
        interp = Interpreter()
        interp.run_source(oop_source, 'oop_test.cpps')
    output = f.getvalue()
    print(output.rstrip())
    print()

    print("✅ Interpreter Self Test hoàn thành!")


if __name__ == '__main__':
    _run_tests()
