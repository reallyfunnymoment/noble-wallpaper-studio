"""Four-byte readback through the existing bounded CRC query.

The CRC of exactly four unknown bytes is an invertible 32-bit mapping. This
recovers those bytes, not an arbitrary-length CRC preimage. No device access on
import. Hardware proof verifies header and custom wallpaper bytes against
independent longer CRC queries. Used for unfamiliar wallpaper backup only.
"""
import struct
import zlib


def crc(data):
    return zlib.crc32(data, 0xffffffff) & 0xffffffff


ZERO_CRC = crc(bytes(4))


def _basis():
    pivots = {}
    for bit in range(32):
        value = crc(struct.pack('<I', 1 << bit)) ^ ZERO_CRC
        source = 1 << bit
        while value:
            pivot = value.bit_length()-1
            if pivot not in pivots:
                pivots[pivot] = (value, source)
                break
            other, mask = pivots[pivot]
            value ^= other
            source ^= mask
        else:
            raise AssertionError('Four-byte CRC mapping is not invertible.')
    return pivots


BASIS = _basis()


def decode_four_bytes(checksum):
    """Invert this protocol's CRC for an input of exactly four bytes."""
    if type(checksum) is not int or not 0 <= checksum <= 0xffffffff:
        raise ValueError('Expected a 32-bit CRC word.')
    value = checksum ^ ZERO_CRC
    source = 0
    while value:
        pivot = value.bit_length()-1
        other, mask = BASIS[pivot]
        value ^= other
        source ^= mask
    result = struct.pack('<I', source)
    if crc(result) != checksum:
        raise AssertionError('CRC inversion verification failed.')
    return result


def read_four_bytes(address, query=None):
    """Read four resource bytes using only the already-bounded command 6."""
    from radio_info_probe import resource_crc_request
    resource_crc_request(1, address, 4)  # Enforce bounds before calling transport.
    if query is None:
        from radio_info_probe import probe_resource_crc
        query = probe_resource_crc
    reply = query(address, 4)
    return decode_four_bytes(int(reply['returned_crc_word'], 16))
