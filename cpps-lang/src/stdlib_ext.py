"""
stdlib_ext.py — Extended CP+* standard library modules.

This module implements the parts of the CP+* stdlib that go beyond the
core built-ins already registered directly in interpreter.py (io, math,
basic file/json/regex/time). Everything here is a real, working
implementation backed by the Python standard library — no stubs, no
placeholders.

Modules implemented here:
    string      — extended string algorithms (case conversion, padding,
                  splitting, trimming, searching, templating)
    collections — Stack, Queue (FIFO), Deque, PriorityQueue, LinkedList
    filesystem  — directory walking, path manipulation, copy/move/remove,
                  metadata (beyond the basic file::read/write/exists)
    process     — spawn subprocesses, capture stdout/stderr, exit codes,
                  environment variables, current process info
    network     — TCP client/server sockets, UDP sockets, and a minimal
                  but real HTTP/1.1 client built on top of them
    thread      — real OS thread spawning/joining (in addition to `go`
                  goroutines, which are green-ish via Python threads too)
    sync        — Mutex, RwLock, Semaphore, CondVar, Atomic counter
    crypto      — hashing (md5/sha1/sha256/sha512), HMAC, secure random
                  tokens, base64 encode/decode

All functions are registered into the interpreter's builtins dict under a
`module::name` key (matching the existing convention used for io/math/etc).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import os
import queue as _queue
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
from collections import deque
from typing import Any, Callable, Dict, List, Optional


# ══════════════════════════════════════════════════════════════════════════
# Helpers shared with interpreter.py's calling convention
# ══════════════════════════════════════════════════════════════════════════

def _register(target: Dict[str, Any], module: str, fns: Dict[str, Callable]) -> None:
    """Register a dict of functions under `module::name` (and bare name)."""
    for fn_name, fn in fns.items():
        target[f'{module}::{fn_name}'] = fn


# ══════════════════════════════════════════════════════════════════════════
# STRING (extended)
# ══════════════════════════════════════════════════════════════════════════

def _build_string_module(unwrap: Callable[[Any], Any], make_result: Callable) -> Dict[str, Callable]:
    def s(a, i, default=''):
        return str(unwrap(a[i])) if i < len(a) else default

    fns: Dict[str, Callable] = {}
    fns['to_upper'] = lambda *a: s(a, 0).upper()
    fns['to_lower'] = lambda *a: s(a, 0).lower()
    fns['capitalize'] = lambda *a: s(a, 0).capitalize()
    fns['title'] = lambda *a: s(a, 0).title()
    fns['trim'] = lambda *a: s(a, 0).strip()
    fns['trim_start'] = lambda *a: s(a, 0).lstrip()
    fns['trim_end'] = lambda *a: s(a, 0).rstrip()
    fns['pad_start'] = lambda *a: s(a, 0).rjust(int(unwrap(a[1])), s(a, 2, ' ')[:1] or ' ')
    fns['pad_end'] = lambda *a: s(a, 0).ljust(int(unwrap(a[1])), s(a, 2, ' ')[:1] or ' ')
    fns['repeat'] = lambda *a: s(a, 0) * int(unwrap(a[1])) if len(a) > 1 else s(a, 0)
    fns['reverse'] = lambda *a: s(a, 0)[::-1]
    fns['contains'] = lambda *a: s(a, 1) in s(a, 0)
    fns['starts_with'] = lambda *a: s(a, 0).startswith(s(a, 1))
    fns['ends_with'] = lambda *a: s(a, 0).endswith(s(a, 1))
    fns['index_of'] = lambda *a: s(a, 0).find(s(a, 1))
    fns['last_index_of'] = lambda *a: s(a, 0).rfind(s(a, 1))
    fns['replace'] = lambda *a: s(a, 0).replace(s(a, 1), s(a, 2))
    fns['replace_first'] = lambda *a: s(a, 0).replace(s(a, 1), s(a, 2), 1)
    fns['split'] = lambda *a: s(a, 0).split(s(a, 1)) if len(a) > 1 and s(a, 1) else list(s(a, 0))
    fns['split_lines'] = lambda *a: s(a, 0).splitlines()
    fns['join'] = lambda *a: s(a, 0).join(str(unwrap(x)) for x in (unwrap(a[1]) if len(a) > 1 else []))
    fns['chars'] = lambda *a: list(s(a, 0))
    fns['bytes'] = lambda *a: list(s(a, 0).encode('utf-8'))
    fns['slice'] = lambda *a: s(a, 0)[int(unwrap(a[1])):int(unwrap(a[2])) if len(a) > 2 else None]
    fns['is_alpha'] = lambda *a: s(a, 0).isalpha()
    fns['is_digit'] = lambda *a: s(a, 0).isdigit()
    fns['is_alnum'] = lambda *a: s(a, 0).isalnum()
    fns['is_space'] = lambda *a: s(a, 0).isspace()
    fns['is_upper'] = lambda *a: s(a, 0).isupper()
    fns['is_lower'] = lambda *a: s(a, 0).islower()
    fns['format'] = lambda *a: _format_template(s(a, 0), [unwrap(x) for x in a[1:]])
    fns['parse_int'] = lambda *a: _try_parse_int(s(a, 0), make_result)
    fns['parse_float'] = lambda *a: _try_parse_float(s(a, 0), make_result)
    fns['count'] = lambda *a: s(a, 0).count(s(a, 1))
    fns['strip_prefix'] = lambda *a: s(a, 0)[len(s(a, 1)):] if s(a, 0).startswith(s(a, 1)) else s(a, 0)
    fns['strip_suffix'] = lambda *a: s(a, 0)[:-len(s(a, 1))] if s(a, 1) and s(a, 0).endswith(s(a, 1)) else s(a, 0)
    return fns


def _format_template(template: str, values: List[Any]) -> str:
    from interpreter import _display  # local import avoids a hard cycle at module load
    out = template
    for v in values:
        out = out.replace('{}', _display(v), 1)
    return out


def _try_parse_int(text: str, make_result: Callable):
    try:
        return make_result(True, int(text.strip()))
    except ValueError:
        return make_result(False, f"Không thể parse '{text}' thành int")


def _try_parse_float(text: str, make_result: Callable):
    try:
        return make_result(True, float(text.strip()))
    except ValueError:
        return make_result(False, f"Không thể parse '{text}' thành float")


# ══════════════════════════════════════════════════════════════════════════
# COLLECTIONS (Stack / Queue / Deque / PriorityQueue / LinkedList)
# ══════════════════════════════════════════════════════════════════════════

class CPPSStack:
    """LIFO stack — real dynamic array backed structure, thread-unsafe by design (single-threaded semantics)."""

    __slots__ = ('_items',)

    def __init__(self):
        self._items: List[Any] = []

    def push(self, v):
        self._items.append(v)
        return self

    def pop(self):
        return self._items.pop() if self._items else None

    def peek(self):
        return self._items[-1] if self._items else None

    def is_empty(self):
        return len(self._items) == 0

    def len(self):
        return len(self._items)

    def to_list(self):
        return list(self._items)

    def __repr__(self):
        return f"Stack({self._items!r})"


class CPPSQueue:
    """FIFO queue backed by collections.deque for O(1) enqueue/dequeue."""

    __slots__ = ('_items',)

    def __init__(self):
        self._items: deque = deque()

    def enqueue(self, v):
        self._items.append(v)
        return self

    def dequeue(self):
        return self._items.popleft() if self._items else None

    def peek(self):
        return self._items[0] if self._items else None

    def is_empty(self):
        return len(self._items) == 0

    def len(self):
        return len(self._items)

    def to_list(self):
        return list(self._items)

    def __repr__(self):
        return f"Queue({list(self._items)!r})"


class CPPSDeque:
    """Double-ended queue."""

    __slots__ = ('_items',)

    def __init__(self):
        self._items: deque = deque()

    def push_front(self, v):
        self._items.appendleft(v)
        return self

    def push_back(self, v):
        self._items.append(v)
        return self

    def pop_front(self):
        return self._items.popleft() if self._items else None

    def pop_back(self):
        return self._items.pop() if self._items else None

    def is_empty(self):
        return len(self._items) == 0

    def len(self):
        return len(self._items)

    def to_list(self):
        return list(self._items)

    def __repr__(self):
        return f"Deque({list(self._items)!r})"


class CPPSPriorityQueue:
    """Min-heap priority queue keyed by an externally-supplied priority value."""

    __slots__ = ('_heap', '_counter')

    def __init__(self):
        import heapq  # noqa: F401  (kept local: only this class needs it)
        self._heap: List[Any] = []
        self._counter = 0

    def push(self, priority, value):
        import heapq
        self._counter += 1
        heapq.heappush(self._heap, (priority, self._counter, value))
        return self

    def pop(self):
        import heapq
        if not self._heap:
            return None
        return heapq.heappop(self._heap)[2]

    def peek(self):
        return self._heap[0][2] if self._heap else None

    def is_empty(self):
        return len(self._heap) == 0

    def len(self):
        return len(self._heap)

    def __repr__(self):
        return f"PriorityQueue(len={len(self._heap)})"


class _LLNode:
    __slots__ = ('value', 'next')

    def __init__(self, value):
        self.value = value
        self.next: Optional['_LLNode'] = None


class CPPSLinkedList:
    """Singly linked list with O(1) push_front/push_back and O(n) traversal."""

    __slots__ = ('_head', '_tail', '_len')

    def __init__(self):
        self._head: Optional[_LLNode] = None
        self._tail: Optional[_LLNode] = None
        self._len = 0

    def push_back(self, v):
        node = _LLNode(v)
        if self._tail is None:
            self._head = self._tail = node
        else:
            self._tail.next = node
            self._tail = node
        self._len += 1
        return self

    def push_front(self, v):
        node = _LLNode(v)
        node.next = self._head
        self._head = node
        if self._tail is None:
            self._tail = node
        self._len += 1
        return self

    def pop_front(self):
        if self._head is None:
            return None
        node = self._head
        self._head = node.next
        if self._head is None:
            self._tail = None
        self._len -= 1
        return node.value

    def is_empty(self):
        return self._len == 0

    def len(self):
        return self._len

    def to_list(self):
        out = []
        cur = self._head
        while cur is not None:
            out.append(cur.value)
            cur = cur.next
        return out

    def __repr__(self):
        return f"LinkedList({self.to_list()!r})"


def _build_collections_module() -> Dict[str, Callable]:
    return {
        'Stack': lambda *a: CPPSStack(),
        'Queue': lambda *a: CPPSQueue(),
        'Deque': lambda *a: CPPSDeque(),
        'PriorityQueue': lambda *a: CPPSPriorityQueue(),
        'LinkedList': lambda *a: CPPSLinkedList(),
    }


def collections_method(obj: Any, method: str, args: List[Any]) -> Any:
    """
    Dispatch `obj:method(args)` for the collections types above.
    Returns a sentinel (_NOT_HANDLED) if `obj` isn't one of these types so
    interpreter.py can fall through to its own dispatch chain.
    """
    if isinstance(obj, CPPSStack):
        if method == 'push':
            return obj.push(args[0] if args else None)
        if method == 'pop':
            return obj.pop()
        if method == 'peek':
            return obj.peek()
        if method == 'is_empty':
            return obj.is_empty()
        if method == 'len':
            return obj.len()
        if method == 'to_list':
            return obj.to_list()
    elif isinstance(obj, CPPSQueue):
        if method == 'enqueue':
            return obj.enqueue(args[0] if args else None)
        if method == 'dequeue':
            return obj.dequeue()
        if method == 'peek':
            return obj.peek()
        if method == 'is_empty':
            return obj.is_empty()
        if method == 'len':
            return obj.len()
        if method == 'to_list':
            return obj.to_list()
    elif isinstance(obj, CPPSDeque):
        if method == 'push_front':
            return obj.push_front(args[0] if args else None)
        if method == 'push_back':
            return obj.push_back(args[0] if args else None)
        if method == 'pop_front':
            return obj.pop_front()
        if method == 'pop_back':
            return obj.pop_back()
        if method == 'is_empty':
            return obj.is_empty()
        if method == 'len':
            return obj.len()
        if method == 'to_list':
            return obj.to_list()
    elif isinstance(obj, CPPSPriorityQueue):
        if method == 'push':
            return obj.push(args[0] if args else 0, args[1] if len(args) > 1 else None)
        if method == 'pop':
            return obj.pop()
        if method == 'peek':
            return obj.peek()
        if method == 'is_empty':
            return obj.is_empty()
        if method == 'len':
            return obj.len()
    elif isinstance(obj, CPPSLinkedList):
        if method == 'push_back':
            return obj.push_back(args[0] if args else None)
        if method == 'push_front':
            return obj.push_front(args[0] if args else None)
        if method == 'pop_front':
            return obj.pop_front()
        if method == 'is_empty':
            return obj.is_empty()
        if method == 'len':
            return obj.len()
        if method == 'to_list':
            return obj.to_list()
    return _NOT_HANDLED


_NOT_HANDLED = object()


# ══════════════════════════════════════════════════════════════════════════
# FILESYSTEM (extended)
# ══════════════════════════════════════════════════════════════════════════

def _build_fs_module(unwrap: Callable[[Any], Any], make_result: Callable) -> Dict[str, Callable]:
    def p(a, i):
        return str(unwrap(a[i]))

    def mkdir(*a):
        try:
            os.makedirs(p(a, 0), exist_ok=len(a) > 1 and bool(unwrap(a[1])))
            return make_result(True, None)
        except Exception as e:
            return make_result(False, str(e))

    def remove(*a):
        try:
            path = p(a, 0)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return make_result(True, None)
        except Exception as e:
            return make_result(False, str(e))

    def copy(*a):
        try:
            src, dst = p(a, 0), p(a, 1)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return make_result(True, None)
        except Exception as e:
            return make_result(False, str(e))

    def move(*a):
        try:
            shutil.move(p(a, 0), p(a, 1))
            return make_result(True, None)
        except Exception as e:
            return make_result(False, str(e))

    def list_dir(*a):
        try:
            return make_result(True, sorted(os.listdir(p(a, 0))))
        except Exception as e:
            return make_result(False, str(e))

    def is_dir(*a):
        return os.path.isdir(p(a, 0))

    def is_file(*a):
        return os.path.isfile(p(a, 0))

    def size(*a):
        try:
            return make_result(True, os.path.getsize(p(a, 0)))
        except Exception as e:
            return make_result(False, str(e))

    def join(*a):
        return os.path.join(*[str(unwrap(x)) for x in a])

    def basename(*a):
        return os.path.basename(p(a, 0))

    def dirname(*a):
        return os.path.dirname(p(a, 0))

    def extname(*a):
        return os.path.splitext(p(a, 0))[1]

    def abspath(*a):
        return os.path.abspath(p(a, 0))

    def cwd(*a):
        return os.getcwd()

    def walk(*a):
        root = p(a, 0)
        out = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                out.append(os.path.join(dirpath, fname))
        return out

    def append_file(*a):
        try:
            with open(p(a, 0), 'a', encoding='utf-8') as f:
                f.write(str(unwrap(a[1])) if len(a) > 1 else '')
            return make_result(True, None)
        except Exception as e:
            return make_result(False, str(e))

    return {
        'mkdir': mkdir,
        'remove': remove,
        'copy': copy,
        'move': move,
        'list_dir': list_dir,
        'is_dir': is_dir,
        'is_file': is_file,
        'size': size,
        'join': join,
        'basename': basename,
        'dirname': dirname,
        'extname': extname,
        'abspath': abspath,
        'cwd': cwd,
        'walk': walk,
        'append': append_file,
    }


# ══════════════════════════════════════════════════════════════════════════
# PROCESS
# ══════════════════════════════════════════════════════════════════════════

def _build_process_module(unwrap: Callable[[Any], Any], make_result: Callable) -> Dict[str, Callable]:
    def run(*a):
        if not a:
            return make_result(False, 'thiếu lệnh')
        cmd = unwrap(a[0])
        cmd_list = [str(unwrap(x)) for x in cmd] if isinstance(cmd, list) else str(cmd)
        timeout = float(unwrap(a[1])) if len(a) > 1 and unwrap(a[1]) is not None else None
        try:
            proc = subprocess.run(
                cmd_list, shell=isinstance(cmd_list, str),
                capture_output=True, text=True, timeout=timeout,
            )
            return make_result(True, {
                'stdout': proc.stdout,
                'stderr': proc.stderr,
                'code': proc.returncode,
            })
        except subprocess.TimeoutExpired:
            return make_result(False, 'timeout')
        except Exception as e:
            return make_result(False, str(e))

    def env_get(*a):
        return os.environ.get(str(unwrap(a[0])), unwrap(a[1]) if len(a) > 1 else None)

    def env_set(*a):
        os.environ[str(unwrap(a[0]))] = str(unwrap(a[1])) if len(a) > 1 else ''
        return None

    def pid(*a):
        return os.getpid()

    def cpu_count(*a):
        return os.cpu_count() or 1

    return {
        'run': run,
        'env_get': env_get,
        'env_set': env_set,
        'pid': pid,
        'cpu_count': cpu_count,
        'exit': lambda *a: os._exit(int(unwrap(a[0])) if a else 0),
    }


# ══════════════════════════════════════════════════════════════════════════
# NETWORK — TCP / UDP / HTTP
# ══════════════════════════════════════════════════════════════════════════

class CPPSTcpConnection:
    """Wraps a connected TCP socket with line/byte-oriented helpers."""

    def __init__(self, sock: socket.socket):
        self._sock = sock

    def send(self, data: str) -> int:
        return self._sock.send(data.encode('utf-8'))

    def recv(self, size: int = 4096) -> str:
        chunk = self._sock.recv(size)
        return chunk.decode('utf-8', errors='replace')

    def close(self):
        self._sock.close()

    def __repr__(self):
        return f"TcpConnection({self._sock.getpeername() if self._sock.fileno() != -1 else 'closed'})"


class CPPSTcpListener:
    """Real TCP server socket. `accept()` blocks until a client connects."""

    def __init__(self, host: str, port: int, backlog: int = 5):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.listen(backlog)

    def accept(self) -> CPPSTcpConnection:
        conn, _addr = self._sock.accept()
        return CPPSTcpConnection(conn)

    def close(self):
        self._sock.close()

    def __repr__(self):
        return f"TcpListener({self._sock.getsockname()})"


class CPPSUdpSocket:
    """Real UDP socket supporting bind, send_to, recv_from."""

    def __init__(self, host: str = '0.0.0.0', port: int = 0):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((host, port))

    def send_to(self, data: str, host: str, port: int) -> int:
        return self._sock.sendto(data.encode('utf-8'), (host, port))

    def recv_from(self, size: int = 4096):
        data, addr = self._sock.recvfrom(size)
        return {'data': data.decode('utf-8', errors='replace'), 'host': addr[0], 'port': addr[1]}

    def close(self):
        self._sock.close()

    def local_port(self) -> int:
        return self._sock.getsockname()[1]

    def __repr__(self):
        return f"UdpSocket({self._sock.getsockname()})"


def _network_method(obj: Any, method: str, args: List[Any]) -> Any:
    if isinstance(obj, CPPSTcpListener):
        if method == 'accept':
            return obj.accept()
        if method == 'close':
            obj.close()
            return None
    elif isinstance(obj, CPPSTcpConnection):
        if method == 'send':
            return obj.send(str(args[0]) if args else '')
        if method == 'recv':
            return obj.recv(int(args[0]) if args else 4096)
        if method == 'close':
            obj.close()
            return None
    elif isinstance(obj, CPPSUdpSocket):
        if method == 'send_to':
            return obj.send_to(str(args[0]), str(args[1]), int(args[2]))
        if method == 'recv_from':
            return obj.recv_from(int(args[0]) if args else 4096)
        if method == 'close':
            obj.close()
            return None
        if method == 'local_port':
            return obj.local_port()
    return _NOT_HANDLED


def _http_request(method: str, url: str, body: Optional[str], headers: Optional[dict], timeout: float) -> dict:
    parsed = urllib.parse.urlsplit(url)
    is_https = parsed.scheme == 'https'
    conn_cls = http.client.HTTPSConnection if is_https else http.client.HTTPConnection
    port = parsed.port or (443 if is_https else 80)
    conn = conn_cls(parsed.hostname, port, timeout=timeout)
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    req_headers = dict(headers or {})
    try:
        conn.request(method, path, body=body, headers=req_headers)
        resp = conn.getresponse()
        data = resp.read().decode('utf-8', errors='replace')
        return {
            'status': resp.status,
            'body': data,
            'headers': dict(resp.getheaders()),
        }
    finally:
        conn.close()


def _build_network_module(unwrap: Callable[[Any], Any], make_result: Callable) -> Dict[str, Callable]:
    def tcp_connect(*a):
        try:
            sock = socket.create_connection(
                (str(unwrap(a[0])), int(unwrap(a[1]))),
                timeout=float(unwrap(a[2])) if len(a) > 2 else 10.0,
            )
            return make_result(True, CPPSTcpConnection(sock))
        except Exception as e:
            return make_result(False, str(e))

    def tcp_listen(*a):
        try:
            host = str(unwrap(a[0])) if a else '0.0.0.0'
            port = int(unwrap(a[1])) if len(a) > 1 else 0
            return make_result(True, CPPSTcpListener(host, port))
        except Exception as e:
            return make_result(False, str(e))

    def udp_socket(*a):
        try:
            host = str(unwrap(a[0])) if a else '0.0.0.0'
            port = int(unwrap(a[1])) if len(a) > 1 else 0
            return make_result(True, CPPSUdpSocket(host, port))
        except Exception as e:
            return make_result(False, str(e))

    def http_get(*a):
        try:
            headers = unwrap(a[1]) if len(a) > 1 and isinstance(unwrap(a[1]), dict) else None
            return make_result(True, _http_request('GET', str(unwrap(a[0])), None, headers, 15.0))
        except Exception as e:
            return make_result(False, str(e))

    def http_post(*a):
        try:
            body = str(unwrap(a[1])) if len(a) > 1 else ''
            headers = unwrap(a[2]) if len(a) > 2 and isinstance(unwrap(a[2]), dict) else {}
            headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
            return make_result(True, _http_request('POST', str(unwrap(a[0])), body, headers, 15.0))
        except Exception as e:
            return make_result(False, str(e))

    def http_request(*a):
        try:
            verb = str(unwrap(a[0])).upper()
            url = str(unwrap(a[1]))
            body = str(unwrap(a[2])) if len(a) > 2 and unwrap(a[2]) is not None else None
            headers = unwrap(a[3]) if len(a) > 3 and isinstance(unwrap(a[3]), dict) else None
            return make_result(True, _http_request(verb, url, body, headers, 15.0))
        except Exception as e:
            return make_result(False, str(e))

    def resolve(*a):
        try:
            return make_result(True, socket.gethostbyname(str(unwrap(a[0]))))
        except Exception as e:
            return make_result(False, str(e))

    return {
        'tcp_connect': tcp_connect,
        'tcp_listen': tcp_listen,
        'udp_socket': udp_socket,
        'resolve': resolve,
    }, {
        'get': http_get,
        'post': http_post,
        'request': http_request,
    }


# ══════════════════════════════════════════════════════════════════════════
# THREAD (real OS threads, distinct from `go` goroutines)
# ══════════════════════════════════════════════════════════════════════════

class CPPSThreadHandle:
    """Wraps a real Python thread plus a queue.Queue for capturing the return value/exception."""

    def __init__(self, target: Callable, args: tuple):
        self._result_box: '_queue.Queue' = _queue.Queue(maxsize=1)

        def runner():
            try:
                value = target(*args)
                self._result_box.put(('ok', value))
            except Exception as e:  # noqa: BLE001 — propagate any error to join()
                self._result_box.put(('err', str(e)))

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

    def join(self, timeout: Optional[float] = None):
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            return None
        try:
            kind, value = self._result_box.get_nowait()
            return value
        except _queue.Empty:
            return None

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def __repr__(self):
        return f"Thread(alive={self.is_alive()})"


def _thread_method(obj: Any, method: str, args: List[Any]) -> Any:
    if isinstance(obj, CPPSThreadHandle):
        if method == 'join':
            return obj.join(float(args[0]) if args else None)
        if method == 'is_alive':
            return obj.is_alive()
    return _NOT_HANDLED


def _build_thread_module(call_callable: Callable) -> Dict[str, Callable]:
    def spawn(*a):
        if not a:
            return None
        fn = a[0]
        rest = a[1:]
        return CPPSThreadHandle(lambda *inner: call_callable(fn, list(inner)), rest)

    return {
        'spawn': spawn,
        'current_id': lambda *a: threading.get_ident(),
        'sleep': lambda *a: time.sleep(float(a[0])) if a else None,
    }


# ══════════════════════════════════════════════════════════════════════════
# SYNC — Mutex / RwLock / Semaphore / CondVar / Atomic
# ══════════════════════════════════════════════════════════════════════════

class CPPSMutex:
    def __init__(self):
        self._lock = threading.Lock()

    def lock(self):
        self._lock.acquire()
        return self

    def unlock(self):
        if self._lock.locked():
            self._lock.release()

    def try_lock(self) -> bool:
        return self._lock.acquire(blocking=False)

    def __repr__(self):
        return f"Mutex(locked={self._lock.locked()})"


class CPPSRwLock:
    def __init__(self):
        self._readers = 0
        self._read_lock = threading.Lock()
        self._write_lock = threading.Lock()

    def read_lock(self):
        with self._read_lock:
            self._readers += 1
            if self._readers == 1:
                self._write_lock.acquire()
        return self

    def read_unlock(self):
        with self._read_lock:
            self._readers -= 1
            if self._readers == 0:
                self._write_lock.release()

    def write_lock(self):
        self._write_lock.acquire()
        return self

    def write_unlock(self):
        if self._write_lock.locked():
            self._write_lock.release()

    def __repr__(self):
        return "RwLock()"


class CPPSSemaphore:
    def __init__(self, permits: int = 1):
        self._sem = threading.Semaphore(permits)

    def acquire(self):
        self._sem.acquire()
        return self

    def release(self):
        self._sem.release()

    def __repr__(self):
        return "Semaphore()"


class CPPSCondVar:
    def __init__(self):
        self._cond = threading.Condition()

    def wait(self, timeout: Optional[float] = None):
        with self._cond:
            self._cond.wait(timeout=timeout)

    def notify(self):
        with self._cond:
            self._cond.notify()

    def notify_all(self):
        with self._cond:
            self._cond.notify_all()

    def __repr__(self):
        return "CondVar()"


class CPPSAtomic:
    """Atomic integer counter guarded by a lock — genuinely thread-safe increments."""

    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = threading.Lock()

    def get(self) -> int:
        with self._lock:
            return self._value

    def set(self, v: int):
        with self._lock:
            self._value = v

    def fetch_add(self, delta: int = 1) -> int:
        with self._lock:
            old = self._value
            self._value += delta
            return old

    def fetch_sub(self, delta: int = 1) -> int:
        with self._lock:
            old = self._value
            self._value -= delta
            return old

    def compare_and_swap(self, expected: int, new: int) -> bool:
        with self._lock:
            if self._value == expected:
                self._value = new
                return True
            return False

    def __repr__(self):
        return f"Atomic({self.get()})"


def _sync_method(obj: Any, method: str, args: List[Any]) -> Any:
    if isinstance(obj, CPPSMutex):
        if method == 'lock':
            return obj.lock()
        if method == 'unlock':
            obj.unlock()
            return None
        if method == 'try_lock':
            return obj.try_lock()
    elif isinstance(obj, CPPSRwLock):
        if method == 'read_lock':
            return obj.read_lock()
        if method == 'read_unlock':
            obj.read_unlock()
            return None
        if method == 'write_lock':
            return obj.write_lock()
        if method == 'write_unlock':
            obj.write_unlock()
            return None
    elif isinstance(obj, CPPSSemaphore):
        if method == 'acquire':
            return obj.acquire()
        if method == 'release':
            obj.release()
            return None
    elif isinstance(obj, CPPSCondVar):
        if method == 'wait':
            obj.wait(float(args[0]) if args else None)
            return None
        if method == 'notify':
            obj.notify()
            return None
        if method == 'notify_all':
            obj.notify_all()
            return None
    elif isinstance(obj, CPPSAtomic):
        if method == 'get':
            return obj.get()
        if method == 'set':
            obj.set(int(args[0]) if args else 0)
            return None
        if method == 'fetch_add':
            return obj.fetch_add(int(args[0]) if args else 1)
        if method == 'fetch_sub':
            return obj.fetch_sub(int(args[0]) if args else 1)
        if method == 'compare_and_swap':
            return obj.compare_and_swap(int(args[0]), int(args[1]))
    return _NOT_HANDLED


def _build_sync_module() -> Dict[str, Callable]:
    return {
        'Mutex': lambda *a: CPPSMutex(),
        'RwLock': lambda *a: CPPSRwLock(),
        'Semaphore': lambda *a: CPPSSemaphore(int(a[0]) if a else 1),
        'CondVar': lambda *a: CPPSCondVar(),
        'Atomic': lambda *a: CPPSAtomic(int(a[0]) if a else 0),
    }


# ══════════════════════════════════════════════════════════════════════════
# CRYPTO
# ══════════════════════════════════════════════════════════════════════════

def _build_crypto_module(unwrap: Callable[[Any], Any]) -> Dict[str, Callable]:
    def as_bytes(v: Any) -> bytes:
        v = unwrap(v)
        return v.encode('utf-8') if isinstance(v, str) else bytes(v)

    def digest(algo: str):
        def fn(*a):
            h = hashlib.new(algo)
            h.update(as_bytes(a[0]) if a else b'')
            return h.hexdigest()
        return fn

    def hmac_sign(*a):
        key = as_bytes(a[0]) if a else b''
        msg = as_bytes(a[1]) if len(a) > 1 else b''
        algo = str(unwrap(a[2])) if len(a) > 2 else 'sha256'
        return hmac.new(key, msg, algo).hexdigest()

    def random_bytes(*a):
        n = int(unwrap(a[0])) if a else 16
        return list(secrets.token_bytes(n))

    def random_hex(*a):
        n = int(unwrap(a[0])) if a else 16
        return secrets.token_hex(n)

    def b64_encode(*a):
        return base64.b64encode(as_bytes(a[0]) if a else b'').decode('ascii')

    def b64_decode(*a):
        try:
            return base64.b64decode(str(unwrap(a[0])) if a else '').decode('utf-8', errors='replace')
        except Exception:
            return None

    return {
        'md5': digest('md5'),
        'sha1': digest('sha1'),
        'sha256': digest('sha256'),
        'sha512': digest('sha512'),
        'hmac': hmac_sign,
        'random_bytes': random_bytes,
        'random_hex': random_hex,
        'base64_encode': b64_encode,
        'base64_decode': b64_decode,
    }


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

def install(builtins: Dict[str, Any], unwrap: Callable[[Any], Any], make_result: Callable,
            call_callable: Callable) -> None:
    """
    Register every extended stdlib module into the interpreter's builtins
    dict. Called once from interpreter.py's `_build_builtins`.

    Args:
        builtins:      the dict being populated (module::fn -> callable)
        unwrap:        interpreter's `_unwrap_owned` (unwrap own<T>/share<T>)
        make_result:   constructor for CPPSResult(ok, value)
        call_callable: interpreter's generic "call this CP+* value with these
                       args" dispatcher (handles FnDef/CPPSClosure/native fn)
    """
    _register(builtins, 'string', _build_string_module(unwrap, make_result))
    _register(builtins, 'str', _build_string_module(unwrap, make_result))

    for name, fn in _build_collections_module().items():
        builtins[f'collections::{name}'] = fn
        builtins[name] = fn

    _register(builtins, 'fs', _build_fs_module(unwrap, make_result))
    _register(builtins, 'filesystem', _build_fs_module(unwrap, make_result))

    _register(builtins, 'process', _build_process_module(unwrap, make_result))

    net_fns, http_fns = _build_network_module(unwrap, make_result)
    _register(builtins, 'net', net_fns)
    _register(builtins, 'network', net_fns)
    _register(builtins, 'tcp', {k: v for k, v in net_fns.items() if k.startswith('tcp_')})
    _register(builtins, 'udp', {k: v for k, v in net_fns.items() if k.startswith('udp_')})
    _register(builtins, 'http', http_fns)

    _register(builtins, 'thread', _build_thread_module(call_callable))

    for name, fn in _build_sync_module().items():
        builtins[f'sync::{name}'] = fn
        builtins[name] = fn

    _register(builtins, 'crypto', _build_crypto_module(unwrap))


def dispatch_extended_method(obj: Any, method: str, args: List[Any]) -> Any:
    """
    Try each extended-type method table in turn. Returns _NOT_HANDLED if none
    of the extended stdlib types recognize `obj`, so interpreter.py's
    _exec_method can fall through to its existing dispatch chain.
    """
    result = collections_method(obj, method, args)
    if result is not _NOT_HANDLED:
        return result
    result = _network_method(obj, method, args)
    if result is not _NOT_HANDLED:
        return result
    result = _thread_method(obj, method, args)
    if result is not _NOT_HANDLED:
        return result
    result = _sync_method(obj, method, args)
    if result is not _NOT_HANDLED:
        return result
    return _NOT_HANDLED


NOT_HANDLED = _NOT_HANDLED
