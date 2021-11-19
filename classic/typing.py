"""
Type hint aliases.
"""
import typing as t
from abc import ABC


class BaseSession:
    vendor: str
    extensions: set


class ServerConnection:
    """Protocol for server-bound messages."""

    def disconnect(self):
        """Handle the disconnection"""
        pass

    def click(self, button, action, yaw, pitch, target, x, y, z, face):
        """Handle a click event."""
        pass

    def change_held(self, block: int):
        pass

    def change_block(self, x, y, z, placed: bool, holding: int):
        """Handle the given block being changed"""
        pass

    def change_location(self, x, y, z, yaw, pitch, holding=None):
        """Handle this session changing location"""
        pass

    def submit_message(self, message: str):
        """Handle an incoming chat message."""
        pass


class ServerSession(ServerConnection, BaseSession):
    """Session object for a connection to a remote server."""
    server_name: str
    server_message: str


class ClientConnection:
    """Protocol for client-bound messages."""

    def disconnect(self):
        """Handle a disconnect."""
        pass

    def kick(self, message: str):
        """Handle a kick message."""
        pass

    def set_block_permission(self, block, create: bool, destroy: bool):
        pass

    def set_block(self, x: int, y: int, z: int, block: int):
        """Handle a block modification."""
        pass

    def set_color_code(self, number, r, g, b, a=255):
        pass

    def add_player(self, number: int, name: str, display_name: str, order: int, group=""):
        """Handle a new player list entry."""
        pass

    def remove_player(self, number: int):
        """Handle a player list entry removal"""
        pass

    def add_entity(self, number: int, name: str, x: int, y: int, z: int,
                   yaw: int, pitch: int, skin: str = None):
        """Handle a new entity."""
        pass

    def remove_entity(self, number: int):
        """Handle a entity removal."""
        pass

    def send_level(self, x: int, y: int, z: int, data: bytes):
        """Handle a new level."""
        pass

    def world_info(self, name, motd, operator=False):
        """Handle a world information update."""
        pass

    def move_entity(self, number, x, y, z, yaw, pitch):
        """Handle the given entity moving to the given coordinates."""
        pass

    def shift_entity(self, number, dx=0, dy=0, dz=0, dh=0, dp=0):
        """Handle the given entity being offset by the given coordinates."""
        pass

    def send_message(self, message: str):
        """Handle a chat message."""
        pass


class ClientSession(ClientConnection, BaseSession):
    """Session object for a connection to a client."""
    username: t.Optional[str]
    token: t.Optional[str]
    pass


class ServerHandler(ServerConnection):
    def __init__(self, session: ClientSession):
        self.session = session


class ClientHandler(ClientConnection):
    def __init__(self, session: ServerSession):
        self.session = session
