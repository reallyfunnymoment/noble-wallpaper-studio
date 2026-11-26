"""Recover unfamiliar wallpaper data using bounded, read-only CRC queries."""
import hashlib
import os
from pathlib import Path
import tempfile
import time
from crc_readback import crc, decode_four_bytes
from patch_wallpaper import RESOURCE_LENGTH, WALLPAPER_ARTWORK, WIDTH, HEIGHT, validate_resource
from usb_wallpaper_plan import prepare_plan, RESOURCE_FLASH_START


def recover_resource(stock, query, cache_directory, progress=lambda message: None):
    """Read changed blocks, preserve old pixels, and reject unrelated changes.

    Known blocks are reconstructed from the verified stock reference. Unknown
    blocks are recovered four bytes per CRC query and checked as whole blocks.
    Partial sessions cache only independently verified blocks for resumption.
    """
    validate_resource(stock)
    spans = sorted((offset, offset+WIDTH*HEIGHT*2) for _, offset in WALLPAPER_ARTWORK.values())
    spans.append((RESOURCE_LENGTH-4, RESOURCE_LENGTH))
    cache = Path(cache_directory)/hashlib.sha256(stock).hexdigest()
    result = bytearray(stock)
    blocks = []
    total = (len(stock)+4095)//4096
    for index, start in enumerate(range(0, len(stock), 4096)):
        end = min(start+4096, len(stock))
        actual = query(RESOURCE_FLASH_START+start, end-start)['returned_crc_word']
        if actual != f'{crc(stock[start:end]):08x}':
            allowed = [(max(start, a), min(end, b)) for a, b in spans if a < end and b > start]
            cursor = start
            for a, b in allowed+[(end, end)]:
                if cursor < a:
                    check = query(RESOURCE_FLASH_START+cursor, a-cursor)['returned_crc_word']
                    if check != f'{crc(stock[cursor:a]):08x}':
                        raise ValueError('Non-wallpaper radio data differs from the supported 1.0.31 reference. No write is allowed.')
                cursor = b
            blocks.append((start, end, actual, allowed))
        progress(f'Inspecting backup blocks: {index+1}/{total}')
    words = sum((b-a+3)//4 for _, _, _, allowed in blocks for a, b in allowed)
    done = 0
    started = time.monotonic()
    for start, end, expected, allowed in blocks:
        path = cache/f'{start:08x}-{expected}.bin'
        saved = path.read_bytes() if path.is_file() else None
        if saved is not None and len(saved) == end-start and f'{crc(saved):08x}' == expected:
            result[start:end] = saved
            done += sum((b-a+3)//4 for a, b in allowed)
        else:
            for a, b in allowed:
                for address in range(a, b, 4):
                    # Last partial word may cross a block/artwork boundary, but
                    # remains within the resource; retain only the allowed bytes.
                    address4 = min(address, RESOURCE_LENGTH-4)
                    reply = query(RESOURCE_FLASH_START+address4, 4)['returned_crc_word']
                    data = decode_four_bytes(int(reply, 16))
                    count = min(4, b-address)
                    result[address:address+count] = data[address-address4:address-address4+count]
                    done += 1
                    if done % 128 == 0 or done == words:
                        seconds = time.monotonic()-started
                        remaining = int(seconds*(words-done)/max(1, done))
                        progress(f'Backing up current wallpapers: {done}/{words} (about {remaining//60} min remaining; safe to disconnect before upload)')
            saved = bytes(result[start:end])
            if f'{crc(saved):08x}' != expected:
                raise ValueError('Live wallpaper backup failed block verification. No write is allowed; retry preparation.')
            cache.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=cache, prefix='.block-')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(saved)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    validate_resource(result)
    prepare_plan(stock, result)
    for start in range(0, len(stock), 65536):
        data = result[start:start+65536]
        actual = query(RESOURCE_FLASH_START+start, len(data))['returned_crc_word']
        if actual != f'{crc(data):08x}':
            raise ValueError('Radio changed during backup. No write is allowed; retry preparation.')
        progress(f'Checking recovered data: {min(start+len(data), len(stock))}/{len(stock)}')
    return bytes(result)
