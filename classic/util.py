
__all__ = (
    "chunked",
    "index_chunked",
    "decode_classic_string",
    "encode_classic_string"
)


def chunked(seq, size):
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def index_chunked(seq, size):
    return ((pos, seq[pos:pos + size]) for pos in range(0, len(seq), size))


def decode_classic_string(data: bytes, encoding: str = 'ascii') -> str:
    """Convert a string of bytes encoded as a space-padded string into a str."""
    return str(data.rstrip(), encoding=encoding)


def encode_classic_string(data: str, encoding: str = 'ascii') -> bytes:
    """Convert a str into 64-character space-padded bytes."""
    if len(data) > 64:
        raise ValueError("The string must fit within 64 characters")
    return bytes(data, encoding=encoding).ljust(64)
