"""CodeAgent sandbox network guard for the subprocess backend.

Python imports `sitecustomize` at start-up from PYTHONPATH, so every Python process in a
subprocess-backed test run gets this module first. It refuses connections and name lookups
for anything but loopback and Unix sockets. It is a guard for honest test suites, not a
security boundary: code that loads a native library or execs another runtime can bypass
it. Real isolation is the Docker backend, which runs with networking disabled.
"""

import socket

# Destinations that never leave the machine (0.0.0.0 as a destination means this host).
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})  # noqa: S104
_MESSAGE = "network access is disabled in the CodeAgent sandbox"
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def _allowed(address: object) -> bool:
    if isinstance(address, (str, bytes)):
        return True  # Unix domain sockets stay inside the machine
    if isinstance(address, tuple) and address:
        host = address[0]
        return isinstance(host, str) and (host in _LOOPBACK or host.startswith("127."))
    return False


def _guarded_connect(self: socket.socket, address: object) -> None:
    if not _allowed(address):
        raise ConnectionRefusedError(_MESSAGE)
    _connect(self, address)  # type: ignore[arg-type]


def _guarded_connect_ex(self: socket.socket, address: object) -> int:
    if not _allowed(address):
        raise ConnectionRefusedError(_MESSAGE)
    return _connect_ex(self, address)  # type: ignore[arg-type]


def _guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
    if host is not None and not (
        isinstance(host, str) and (host in _LOOPBACK or host.startswith("127."))
    ):
        raise socket.gaierror(socket.EAI_NONAME, _MESSAGE)
    return _getaddrinfo(host, *args, **kwargs)  # type: ignore[arg-type]


socket.socket.connect = _guarded_connect  # type: ignore[method-assign,assignment]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign,assignment]
socket.getaddrinfo = _guarded_getaddrinfo  # type: ignore[assignment]
