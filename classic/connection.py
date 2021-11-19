"""
Classic protocol parsing utilities
"""
import asyncio
import logging
import typing as t
from struct import Struct
from functools import partialmethod
from asyncio import StreamReader, StreamWriter
from .util import decode_classic_string, encode_classic_string
from .__version__ import __version__


class Extension(t.NamedTuple):
    name: str
    version: int = 1


ExtPlayerList2 = Extension("ExtPlayerList", 2)
EntityPositions = Extension("ExtEntityPositions")
HeldBlock = Extension("HeldBlock")
FullCP437 = Extension("FullCP437")
MessageTypes = Extension("MessageTypes")
LongerMessages = Extension("LongerMessages")
TextColors = Extension("TextColors")
BlockPermissions = Extension("BlockPermissions")
PlayerClick = Extension("PlayerClick")


NO_VENDOR = "(no vendor)"
UNKNOWN_VENDOR = "(unknown)"
PARSER_DEBUG = True


_PacketHandler = t.Callable[['BaseConnection'], t.Awaitable]


class BaseConnection:
    def __init__(self, reader: StreamReader, writer: StreamWriter, handler_factory):
        self.reader = reader
        self.writer = writer

        self.handler_factory = handler_factory
        self.handler = None
        self.logger = logging.getLogger(self.__class__.__name__)

        self._handlers: t.List[_PacketHandler] = self.handlers()
        self.supported_extensions: t.Tuple[Extension] = tuple(self.supported_extensions())

        self.alive = True
        self.vendor = NO_VENDOR
        self.extensions: t.Set[Extension] = set()

        self.current_opcode = None
        self.last_opcode = None

        self._text_encoding = "ascii"
        self._location_struct = "3h2B"
        self._ext_left = 0

    async def read_struct(self, fmt) -> tuple:
        """Read the given struct format from the stream."""
        _struct = Struct("!" + fmt)
        data = await self.reader.readexactly(_struct.size)
        return _struct.unpack(data)

    def write_struct(self, fmt, *args) -> None:
        """Write the given struct format to the stream."""
        _struct = Struct("!" + fmt)
        buff = _struct.pack(*args)
        self.writer.write(buff)

    async def read_byte(self) -> int:
        """Read an unsigned 8-bit integer."""
        data = await self.reader.readexactly(1)
        return int.from_bytes(data, 'big')

    def write_byte(self, x: int) -> None:
        """Write an unsigned 8-bit integer."""
        buff = int.to_bytes(x, 1, 'big')
        self.writer.write(buff)

    async def read_short(self) -> int:
        """Read a signed 16-bit integer."""
        data = await self.reader.readexactly(2)
        return int.from_bytes(data, 'big', signed=True)

    def write_short(self, x: int) -> None:
        """Write a signed 16-bit integer."""
        buff = x.to_bytes(2, 'big', signed=True)
        self.writer.write(buff)

    async def read_int(self) -> int:
        """Read an unsigned 32-bit integer."""
        data = await self.reader.readexactly(4)
        return int.from_bytes(data, 'big')

    def write_int(self, x: int) -> None:
        """Write an unsigned 32-bit integer."""
        buff = x.to_bytes(4, 'big')
        self.writer.write(buff)

    async def read_string(self) -> str:
        """Read a space-padding string."""
        data = await self.reader.readexactly(64)
        return decode_classic_string(data, self._text_encoding)

    def write_string(self, x: str) -> None:
        """Write a space-padded string."""
        self.writer.write(encode_classic_string(x, self._text_encoding))

    async def read_location(self):
        """Read a fractional-space location (32 units/block, yaw/pitch)"""
        return await self.read_struct(self._location_struct)

    def write_location(self, x, y, z, yaw, pitch):
        """Write a fractional-space location (32 units/block, yaw/pitch)"""
        self.write_struct(self._location_struct, x, y, z, yaw, pitch)

    async def read_position(self):
        """Read a block-space position (1 unit/block)"""
        return await self.read_struct("3H")

    def write_position(self, x, y, z):
        """Write a block-space position (1 unit/block)"""
        self.write_struct("3H", x, y, z)

    def write_extensions(self):
        """Write all members of supported_extensions to the string."""
        self.write_byte(OPCODE_EXT_INFO)
        self.write_string(self.agent)
        self.write_short(len(self.supported_extensions))
        for extension in self.supported_extensions:
            self.write_byte(OPCODE_EXT_ENTRY)
            self.write_string(extension.name)
            self.write_int(extension.version)

    def received_extensions(self):
        """Handle receipt of all extensions from the remote peer."""
        if EntityPositions in self.extensions:
            self._location_struct = "3i2B"
        if FullCP437 in self.extensions:
            self._text_encoding = "cp437"

    def close(self):
        self.alive = False

    async def handle_unknown(self):
        self.close()

    async def handle_ext_info(self):
        self.vendor = await self.read_string()
        self._ext_left = await self.read_short()

    async def handle_ext_entry(self):
        ext_name = await self.read_string()
        version = await self.read_int()
        if not self._ext_left:
            self.close()
        ext = Extension(ext_name, version)
        self.extensions.add(ext)
        self._ext_left -= 1
        if not self._ext_left:
            self.received_extensions()

    async def handle_next(self):
        opcode = await self.read_byte()
        self.current_opcode = opcode
        await self._handlers[opcode](self)
        self.current_opcode = None
        self.last_opcode = opcode

    async def handle_forever(self):
        try:
            while self.alive:
                await self.handle_next()
        except (ConnectionResetError, EOFError):
            self.close()

    @property
    def agent(self):
        return self.__class__.__name__ + "/" + __version__

    @staticmethod
    def supported_extensions() -> t.Iterable[Extension]:
        yield EntityPositions
        yield FullCP437

    @classmethod
    def handlers(cls) -> t.List[_PacketHandler]:
        p = [cls.handle_unknown] * 256
        p[OPCODE_EXT_INFO] = cls.handle_ext_info
        p[OPCODE_EXT_ENTRY] = cls.handle_ext_entry
        return p


# TODO: DO NOT FORGET DECORATOR ON BASE WHICH EXPANDS HANDLERS
#       AND SUPPORTED EXTENSIONS AS SUBCLASSABLE HANDLERS AT RUNTIME
#       AND THEN START WORKING ON CLASSICUBED AND RELEASE THIS SHIT
#       ITS BEEN A MONTH ALMOST FUCKS SAKE.

# OPCODES
OPCODE_HELLO = 0x00
OPCODE_HEARTBEAT = 0x01
OPCODE_START_LEVEL = 0x02
OPCODE_LEVEL_CHUNK = 0x03
OPCODE_FINISH_LEVEL = 0x04
OPCODE_CHANGE_BLOCK = 0x05
OPCODE_SET_BLOCK = 0x06
OPCODE_ADD_ENTITY = 0x07
OPCODE_REMOVE_ENTITY = 0x0C
OPCODE_ABSOLUTE_LOCATION = 0x08
OPCODE_RELATIVE_LOCATION = 0x09
OPCODE_RELATIVE_POSITION = 0x0A
OPCODE_RELATIVE_ORIENTATION = 0x0B
OPCODE_MESSAGE = 0x0D
OPCODE_DISCONNECT = 0x0E
OPCODE_ADMIN_STATUS = 0x0F
OPCODE_EXT_INFO = 0x10
OPCODE_EXT_ENTRY = 0x11


# CPE OPCODES
OPCODE_HOLD_THIS = 0x14
OPCODE_ADD_PLAYER = 0x16
OPCODE_REMOVE_PLAYER = 0x18
OPCODE_ADD_ENTITY_EXT = 0x21
OPCODE_SET_TEXT_COLOR = 0x27
OPCODE_SET_BLOCK_PERMISSION = 0x1C
OPCODE_CLICK = 0x22
