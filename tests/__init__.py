"""Test suite of the proof pack. Offline by construction: the first thing it does is to make every
socket unusable in this process, so a test that tried to reach a network would fail, not pass."""
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*_args, **_kwargs):
    raise NetworkBlocked("the test suite runs offline: sockets are blocked")


class _NoSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        _blocked()


socket.socket = _NoSocket
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
