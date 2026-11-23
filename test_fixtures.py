"""Synthetic resource fixture; contains no vendor firmware or artwork."""
import struct
from checksums import crc32_nonref, reverse_words
from patch_wallpaper import RESOURCE_LENGTH, WALLPAPER_ARTWORK, WIDTH, HEIGHT


def synthetic_resource():
    data = bytearray(RESOURCE_LENGTH)
    struct.pack_into('<HI', data, 0, 0x5a5a, RESOURCE_LENGTH-4)
    struct.pack_into('<H', data, 18, (sum(data[:18]) & 0xffff) ^ 0xffff)
    for descriptor, offset in WALLPAPER_ARTWORK.values():
        struct.pack_into('<IIII', data, descriptor, WIDTH, HEIGHT, 0xa897, 0xc0280000+offset)
    struct.pack_into('<I', data, len(data)-4, crc32_nonref(reverse_words(data[:-4])))
    return bytes(data)
