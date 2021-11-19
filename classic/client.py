"""
Classic client for Python
"""
import logging
import typing as t
import time
from .connection import *
from .util import chunked
from .typing import *
from .__version__ import __version__

from gzip import decompress


class ServerConnectionHandler(ServerSession, BaseConnection):
    handler: t.Optional[ClientConnection]

    def __init__(self, reader: StreamReader, writer: StreamWriter,
                 handler_factory):
        super().__init__(reader, writer, handler_factory)
        self.operator = False

        self.holding = 0
        self._receiving_level = False
        self._level_buffer = None
        self._last_location = None
        self._last_held = None
        self._partial_message = b''

    # ServerConnection implementation

    def hello(self, username, password):
        self.write_byte(OPCODE_HELLO)
        self.write_byte(7)  # version
        self.write_string(username)
        self.write_string(password)
        self.write_byte(66)

    def change_held(self, block):
        if HeldBlock in self.extensions:
            self.change_location(*self._last_location, block)
        self.holding = block

    def change_location(self, x, y, z, yaw, pitch, holding=0):
        self.write_byte(OPCODE_ABSOLUTE_LOCATION)
        self.write_byte(holding)
        self.write_location(x, y, z, yaw, pitch)
        self._last_location = x, y, z, yaw, pitch

    def set_block(self, x, y, z, block):
        placed = not not block
        self.holding = block
        self.change_block(x, y, z, placed, block)

    def break_block(self, x, y, z, holding=None):
        if holding:
            self.holding = holding
        else:
            holding = self.holding
        self.change_block(x, y, z, False, holding)

    def change_block(self, x, y, z, placed: bool, holding: int):
        self.write_byte(OPCODE_CHANGE_BLOCK)
        self.write_position(x, y, z)
        self.write_byte(placed)
        self.write_byte(holding)

    def submit_message(self, message: str):
        partial = 0
        for chunk in chunked(message, 64):
            self.write_byte(OPCODE_MESSAGE)
            self.write_byte(partial)
            self.write_string(chunk)
            partial = 1

    # Disconnection

    def close(self):
        if self.handler:
            self.handler.disconnect()
        super().close()

    # Incoming _handlers

    async def _handle_kick(self):
        message = await self.read_string()
        self.handler.kick(message)
        self.close()

    async def _handle_chat_message(self):
        message_type = await self.read_byte()
        message = await self.read_string()
        self.handler.send_message(message)

    async def _handle_set_block(self):
        x, y, z = await self.read_struct("3H")
        block = await self.read_byte()
        self.handler.set_block(x, y, z, block)

    async def _handle_add_entity(self):
        entity_number = await self.read_byte()
        name = await self.read_string()
        location = await self.read_location()
        self.handler.add_entity(entity_number, name, *location, skin=name)

    async def _handle_move_entity(self):
        entity_number = await self.read_byte()
        location = await self.read_position()
        yaw, pitch = await self.read_struct("2B")
        self.handler.move_entity(entity_number, *location, yaw, pitch)

    async def _handle_relative_location(self):
        number = await self.read_byte()
        delta_pos = await self.read_struct("3b2B")
        self.handler.shift_entity(number, *delta_pos)

    async def _handle_relative_position(self):
        number = await self.read_byte()
        delta_pos = await self.read_struct("3b")
        self.handler.shift_entity(number, *delta_pos)

    async def _handle_relative_orientation(self):
        number = await self.read_byte()
        dh, dp = await self.read_struct("2B")
        self.handler.shift_entity(number, dh=dh, dp=dp)

    async def _handle_remove_entity(self):
        entity_number = await self.read_byte()
        self.handler.remove_entity(entity_number)

    async def _handle_level_start(self):
        self._receiving_level = True
        self._level_buffer = bytearray()

    async def _handle_level_chunk(self):
        size = await self.read_short()
        chunk, = await self.read_struct("1024s")
        complete = await self.read_byte()
        if self._receiving_level:
            self._level_buffer += chunk[:size]

    async def _handle_level_end(self):
        x, y, z = await self.read_struct("3H")
        if self._receiving_level:
            buff = decompress(self._level_buffer)
            self.handler.send_level(x, y, z, buff[4:])
            self._receiving_level = False
            self._level_buffer = None

    async def _handle_hello(self):
        version = await self.read_byte()
        name = await self.read_string()
        motd = await self.read_string()
        operator = await self.read_byte()
        self.name = name
        self.motd = motd
        self.operator = operator
        if version != 7:
            self.close()
        self.handler = self.handler_factory(self)
        self.handler.world_info(name, motd)

    async def _handle_add_player(self):
        number = await self.read_short()
        name = await self.read_string()
        display_name = await self.read_string()
        group = await self.read_string() or None
        rank = await self.read_byte()
        self.handler.add_player(number, name, display_name, rank, group)

    async def _handle_ext_add_entity(self):
        entity_number = await self.read_byte()
        name = await self.read_string()
        skin = await self.read_string()
        location = await self.read_location()
        self.handler.add_entity(entity_number, name, *location, skin=skin)

    async def _handle_remove_player(self):
        number = await self.read_short()
        self.handler.remove_player(number)

    def received_extensions(self):
        super().received_extensions()
        self.write_extensions()

    async def _handle_heartbeat(self):
        self.last_heartbeat = time.time()

    @classmethod
    def supported_extensions(cls):
        yield EntityPositions  # TODO: yes, this is dirty. I am thinking of a way to make this not as dirty.
        yield MessageTypes
        yield HeldBlock
        yield LongerMessages
        yield ExtPlayerList2
        yield from super().supported_extensions()

    @classmethod
    def handlers(cls):
        p = super().handlers()
        p[OPCODE_HELLO] = cls._handle_hello
        p[OPCODE_START_LEVEL] = cls._handle_level_start
        p[OPCODE_LEVEL_CHUNK] = cls._handle_level_chunk
        p[OPCODE_FINISH_LEVEL] = cls._handle_level_end
        p[OPCODE_ADD_ENTITY] = cls._handle_add_entity
        p[OPCODE_REMOVE_ENTITY] = cls._handle_remove_entity
        p[OPCODE_ABSOLUTE_LOCATION] = cls._handle_move_entity
        p[OPCODE_SET_BLOCK] = cls._handle_set_block
        p[OPCODE_MESSAGE] = cls._handle_chat_message
        p[OPCODE_DISCONNECT] = cls._handle_kick
        p[OPCODE_HEARTBEAT] = cls._handle_heartbeat
        p[OPCODE_RELATIVE_POSITION] = cls._handle_relative_position
        p[OPCODE_RELATIVE_ORIENTATION] = cls._handle_relative_orientation
        p[OPCODE_RELATIVE_LOCATION] = cls._handle_relative_location
        p[OPCODE_ADD_PLAYER] = cls._handle_add_player
        p[OPCODE_ADD_ENTITY_EXT] = cls._handle_ext_add_entity
        p[OPCODE_REMOVE_PLAYER] = cls._handle_remove_player
        return p


async def _connect(handler_factory, host, port=25565, handler_class=ServerConnectionHandler, **kwargs):
    reader, writer = await asyncio.open_connection(host, port, **kwargs)
    return handler_class(reader, writer, handler_factory)
