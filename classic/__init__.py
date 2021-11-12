"""
Minecraft Classic protocol support for Python
"""
from .typing import ClientHandler, ServerHandler
from .util import decode_classic_string, encode_classic_string
from .server import _create_server
from .client import _connect

__all__ = (
    "connect",
    "serve",
    "ClientHandler",
    "ServerHandler",
    "decode_classic_string",
    "encode_classic_string"
)

serve = _create_server
connect = _connect
