"""Small read-only hardware proof. Put the radio in update mode first.

Sends only existing metadata/CRC requests, never erase/program or mode changes.
Recovers 32 header bytes, an unaligned header word, and 32 wallpaper bytes, then
cross-checks each recovered region with a separate longer CRC query.
"""
import argparse
import json
from pathlib import Path
import time
from crc_readback import read_four_bytes, crc
from firmware_reference import read_stock_resource
from patch_wallpaper import SLOTS
from radio_info_probe import probe, probe_resource_crc, RESOURCE_START


def investigate():
    info = probe()
    if (info['application_version_word'], info['application_variant_word']) != ('0000001f', '00010000'):
        raise ValueError('This proof is restricted to the supported 1.0.31 metadata.')
    stock = read_stock_resource()
    results = []
    started = time.monotonic()
    for name, offset in [('header', 0), ('scenery', SLOTS['scenery'][1])]:
        recovered = b''.join(read_four_bytes(RESOURCE_START+offset+i) for i in range(0, 32, 4))
        expected_crc = probe_resource_crc(RESOURCE_START+offset, len(recovered))['returned_crc_word']
        if f'{crc(recovered):08x}' != expected_crc:
            raise ValueError(f'{name}: recovered bytes failed the independent longer CRC check.')
        if name == 'header' and recovered != stock[:32]:
            raise ValueError('Header recovery does not match the supported reference.')
        results.append(dict(region=name, resource_offset=offset, bytes=32,
                            independent_crc_verified=True,
                            matches_stock_reference=recovered == stock[offset:offset+32]))
    if read_four_bytes(RESOURCE_START+2) != stock[2:6]:
        raise ValueError('Unaligned header readback failed.')
    seconds = time.monotonic()-started
    return dict(operation='Read-only metadata and bounded command-6 CRC requests only.',
                byte_readback_proof=True, application_version='1.0.31',
                regions=results, unaligned_read_verified=True, elapsed_seconds=seconds,
                crc_queries=19, recovered_bytes=68,
                notes='Small proof only; no complete backup, upload, erase, program, or reboot performed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('crc_readback_probe.json'))
    args = parser.parse_args()
    result = investigate()
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
