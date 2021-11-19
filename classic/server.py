"""
Classic server for Python
"""
import logging
from .typing import *
from .connection import *
from .util import chunked, decode_classic_string, encode_classic_string
from functools import wraps
from gzip import compress


logger = logging.getLogger(__name__)


def if_alive(func):
    @wraps(func)
    def check_alive(*args, **kwargs):
        instance = args[0]
        if instance.alive:
            func(*args, **kwargs)
    return check_alive


class ClientConnectionHandler(ClientSession, BaseConnection):

    def __init__(self, reader: StreamReader, writer: StreamWriter,
                 handler_factory):
        super().__init__(reader, writer, handler_factory)
        self.username = None
        self.token = None
        self._last_location = None
        self._last_held = None
        self._partial_message = b''

    def __str__(self):
        name = self.username
        if name:
            return name
        else:
            return "idk lol"

    # ClientConnection implementation

    @if_alive
    def add_entity(self, entity_number: int, name: str, x: int, y: int, z: int,
                   yaw: int, pitch: int, skin=None):
        support_plr_list = ExtPlayerList2 in self.extensions
        opcode = OPCODE_ADD_ENTITY_EXT if support_plr_list else OPCODE_ADD_ENTITY
        self.write_byte(opcode)
        self.write_byte(entity_number)
        self.write_string(name)
        if support_plr_list:
            self.write_string(skin or name)
        self.write_location(x, y, z, yaw, pitch)

    @if_alive
    def move_entity(self, entity_number: int, x, y, z, yaw, pitch):
        self.write_byte(OPCODE_ABSOLUTE_LOCATION)
        self.write_byte(entity_number)
        self.write_location(x, y, z, yaw, pitch)

    @if_alive
    def remove_entity(self, entity_number: int):
        self.write_byte(OPCODE_REMOVE_ENTITY)
        self.write_byte(entity_number)

    @if_alive
    def world_info(self, name, message, is_operator=False):
        self.write_byte(OPCODE_HELLO)
        self.write_string(name)
        self.write_string(message)
        self.write_byte(is_operator)

    @if_alive
    def send_level(self, x: int, y: int, z: int, data: bytes, **kwargs):
        self.write_byte(OPCODE_START_LEVEL)
        volume: int = len(data)
        data = compress(volume.to_bytes(4, 'big') + data, 1)
        for chunk in chunked(data, 1024):
            self.write_byte(OPCODE_LEVEL_CHUNK)
            self.write_short(len(chunk))
            self.write_struct("1024s", chunk)
            self.write_byte(0)
        self.write_byte(OPCODE_FINISH_LEVEL)
        self.write_position(x, y, z)

    @if_alive
    def set_block(self, x, y, z, block):
        self.write_byte(OPCODE_SET_BLOCK)
        self.write_position(x, y, z)
        self.write_byte(block)

    @if_alive
    def send_message(self, message, message_type=None):
        if message_type:
            self.write_byte(OPCODE_MESSAGE)
            self.write_byte(message_type)
            self.write_string(message)
        else:
            for chunk in chunked(message, 64):
                self.write_byte(OPCODE_MESSAGE)
                self.write_byte(0)
                self.write_string(chunk)

    def set_message(self, message_type: int, message: str):
        if MessageTypes in self.extensions:
            self.send_message(message, message_type)

    @if_alive
    def set_location(self, entity_number, *loc):
        self.write_byte(OPCODE_ABSOLUTE_LOCATION)
        self.write_byte(entity_number)
        self.write_location(*loc)
        if entity_number == 255:
            self._last_location = loc

    @if_alive
    def kick(self, message="No reason given."):
        self.write_byte(OPCODE_DISCONNECT)
        self.write_string(message)
        self.close()

    @if_alive
    def set_color_code(self, number, r, g, b, a=255):
        if TextColors in self.extensions:
            self.write_struct("4Bc", r, g, b, a, number)

    @if_alive
    def set_block_permission(self, block, create: bool, destroy: bool):
        if BlockPermissions in self.extensions:
            self.write_byte(OPCODE_SET_BLOCK_PERMISSION)
            self.write_byte(block)
            self.write_byte(create)
            self.write_byte(destroy)

    @if_alive
    def add_player(self, player_id: int, name: str, display_name=None, order=None, group=""):
        if ExtPlayerList2 not in self.extensions:
            return
        self.write_byte(OPCODE_ADD_PLAYER)
        self.write_short(player_id)
        self.write_string(name)
        self.write_string(display_name or name)
        self.write_string(group)
        self.write_byte(order or player_id)

    @if_alive
    def remove_player(self, player_id: int):
        if ExtPlayerList2 not in self.extensions:
            self.write_byte(OPCODE_REMOVE_PLAYER)
            self.write_short(player_id)

    @if_alive
    def hold_this(self, block: int, force=False):
        if ExtPlayerList2 in self.extensions:
            self.write_byte(OPCODE_HOLD_THIS)
            self.write_byte(block)
            self.write_byte(force)

    # Disconnection

    def close(self):
        if self.handler:
            self.handler.disconnect()
        super().close()

    # Incoming _handlers

    async def _handle_block_change(self):
        position = await self.read_position()
        created = await self.read_byte()
        holding = await self.read_byte()
        self.handler.change_block(*position, not not created, holding)

    async def _handle_location_change(self):
        holding = await self.read_byte()
        location = await self.read_location()
        if HeldBlock in self.extensions and holding != self._last_held:
            self.handler.change_held(holding)
            self._last_held = holding
        if location != self._last_location:
            self.handler.change_location(*location)

    async def _handle_click(self):
        button, action = await self.read_struct("2B")
        yaw, pitch = await self.read_struct("2H")
        target = await self.read_byte()
        tx, ty, tz = await self.read_position()
        target_face = await self.read_byte()
        self.handler.click(button, action, yaw, pitch, target, tx, ty, tz, target_face)

    async def _handle_chat_message(self):
        partial_message = await self.read_byte()
        message_raw = await self.reader.readexactly(64)
        self._partial_message += message_raw
        if not partial_message:
            message = decode_classic_string(self._partial_message, self._text_encoding)
            self.handler.submit_message(message)
            self._partial_message = b''

    async def _handle_hello(self):
        if self.username:
            self.kick("Client hello more than once")
        version = await self.read_byte()
        if version != 7:
            self.kick(f"Unsupported protocol version {version}")
        self.username = await self.read_string()
        self.token = await self.read_string()
        magic = await self.read_byte()
        if magic == 66:
            self.vendor = UNKNOWN_VENDOR
            self.write_extensions()
        else:
            self.received_extensions()

    def received_extensions(self):
        super().received_extensions()
        self.handler = self.handler_factory(self)
        assert self.handler is not None, "handler_factory did not return a handler."

    @classmethod
    def supported_extensions(cls):
        yield ExtPlayerList2
        yield MessageTypes
        yield HeldBlock
        yield LongerMessages
        yield BlockPermissions
        yield PlayerClick
        yield from super().supported_extensions()

    @classmethod
    def handlers(cls):
        p = super().handlers()
        p[OPCODE_HELLO] = cls._handle_hello
        p[OPCODE_CHANGE_BLOCK] = cls._handle_block_change
        p[OPCODE_ABSOLUTE_LOCATION] = cls._handle_location_change
        p[OPCODE_MESSAGE] = cls._handle_chat_message
        p[OPCODE_CLICK] = cls._handle_click
        return p


async def _create_server(handler_factory, ip, port=25565, *args, handler_class=ClientConnectionHandler, **kwargs):
    async def _handle_connection(reader, writer):
        session = handler_class(reader, writer, handler_factory)
        await session.handle_forever()
    return await asyncio.start_server(_handle_connection, ip, *args, port=port, **kwargs)
