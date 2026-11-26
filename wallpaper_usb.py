"""Bounded three-slot, data-only USB uploader. No application-erase/code-write commands.

Bootloader data erase/program and full-resource verification succeeded in the
first three-slot hardware test. Baselines/backups are reconstructed local images
checked against device CRCs, not raw device dumps. No request is sent on import.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import time
import tempfile
import zlib
from patch_wallpaper import RESOURCE_LENGTH, validate_resource
from radio_info_probe import probe, probe_resource_crc, _exchange_validated, REPORT_BYTES
from usb_wallpaper_plan import prepare_plan, RESOURCE_FLASH_START, ERASE_BYTES
from app_paths import ROOT, backup_directory, stock_resource_path
from firmware_reference import read_stock_resource

BACKUPS = backup_directory()
RESOURCE_END = RESOURCE_FLASH_START+RESOURCE_LENGTH
ALLOWED_END = (RESOURCE_END+ERASE_BYTES-1)//ERASE_BYTES*ERASE_BYTES


def crc(data):
    # Matches all 256 entries of updater table at VA 0x004030C8 and its loop:
    # reflected EDB88320, initial register 0, final inversion.
    return f'{zlib.crc32(data, 0xffffffff)&0xffffffff:08x}'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def erase_request(sequence, address):
    if address % ERASE_BYTES or not RESOURCE_FLASH_START <= address < ALLOWED_END:
        raise ValueError('Erase is outside the fixed image-data region.')
    packet = bytearray(REPORT_BYTES)
    struct.pack_into('<IIII', packet, 1, sequence, 4, address, 0)  # 0 = 4 KiB erase
    return bytes(packet)


def program_request(sequence, address, payload):
    if (not 1 <= len(payload) <= 256 or address//256 != (address+len(payload)-1)//256
            or not RESOURCE_FLASH_START <= address or address+len(payload) > ALLOWED_END):
        raise ValueError('Program request is outside the bounded data page.')
    packet = bytearray(REPORT_BYTES)
    # Target 2 is external data. Target 1 (application code) is never emitted.
    struct.pack_into('<IIIII', packet, 1, sequence, 5, address, len(payload), 2)
    packet[25:25+len(payload)] = payload
    return bytes(packet)


def candidates():
    paths = [stock_resource_path(),
             ROOT/'custom_model_blue_car/FS_FG4_CN_Data.bin',
             ROOT/'custom_model_car_character_cat/FS_FG4_CN_Data.bin',
             ROOT/'example_car_in_scenery/FS_FG4_CN_Data.bin']
    if BACKUPS.exists():
        paths += list(BACKUPS.glob('*/baseline.bin')) + list(BACKUPS.glob('*/target.bin'))
    found = {}
    for path in paths:
        if path.is_file():
            data = path.read_bytes()
            validate_resource(data)
            # Require every baseline to be the inspected layout with changes
            # limited to stock wallpaper pixels and their trailing checksum.
            stock = read_stock_resource()
            prepare_plan(stock, data)
            found[digest(data)] = (path, data)
    return list(found.values())


def identify_baseline(progress=lambda message: None):
    info = probe()
    if (info['application_version_word'], info['application_variant_word']) != ('0000001f', '00010000'):
        raise ValueError('Radio version metadata does not match the inspected 1.0.31 reference.')
    available = candidates()
    if not available:
        raise ValueError('No validated local resource baseline is available.')
    checks = []
    total = (RESOURCE_LENGTH+65535)//65536
    for index, offset in enumerate(range(0, RESOURCE_LENGTH, 65536)):
        length = min(65536, RESOURCE_LENGTH-offset)
        result = probe_resource_crc(RESOURCE_FLASH_START+offset, length)
        actual = result['returned_crc_word']
        checks.append(dict(offset=offset, bytes=length, crc=actual))
        available = [(path, data) for path, data in available if crc(data[offset:offset+length]) == actual]
        progress(f'Checking radio data: {index+1}/{total}')
    if not available:
        from live_backup import recover_resource
        progress('Reading your current wallpapers for recovery. A first backup on this PC can take 45 minutes or longer; verified blocks are saved for resuming.')
        data = recover_resource(read_stock_resource(), probe_resource_crc, BACKUPS/'read_cache', progress)
        folder = BACKUPS/('discovered-'+digest(data)[:20])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/'baseline.bin'
        fd, temporary = tempfile.mkstemp(prefix='.baseline-', dir=folder)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path, data, checks
    path, data = available[0]
    return path, data, checks


def block_image(data, address):
    if address % ERASE_BYTES or not RESOURCE_FLASH_START <= address < ALLOWED_END:
        raise ValueError('Invalid wallpaper erase block.')
    start = address-RESOURCE_FLASH_START
    portion = data[start:min(start+ERASE_BYTES, len(data))]
    return portion + b'\xff'*(ERASE_BYTES-len(portion))


def prepare_upload(target, progress=lambda message: None):
    """Read-only preflight; save CRC-verified reconstructed block preimages."""
    validate_resource(target)
    path, baseline, checks = identify_baseline(progress)
    plan = prepare_plan(baseline, target)
    snapshots = []
    for index, block in enumerate(plan['affected_blocks']):
        address = block['flash_start']
        before, after = block_image(baseline, address), block_image(target, address)
        actual = probe_resource_crc(address, ERASE_BYTES)['returned_crc_word']
        if actual != crc(before):
            raise ValueError('Complete erase block differs from the saved baseline or expected padding. No write is allowed.')
        snapshots.append((address, before, after))
        progress(f'Checking affected blocks: {index+1}/{len(plan["affected_blocks"])}')
    BACKUPS.mkdir(parents=True, exist_ok=True)
    folder = BACKUPS/(time.strftime('%Y%m%d-%H%M%S', time.gmtime())+'-'+secrets.token_hex(3))
    folder.mkdir()
    (folder/'baseline.bin').write_bytes(baseline)
    (folder/'target.bin').write_bytes(target)
    manifest = dict(version=1, state='prepared', source_path=str(path), baseline_sha256=digest(baseline),
                    target_sha256=digest(target), plan=plan, resource_checks=checks,
                    backup_type='Verified local reference or live-read wallpaper baseline; every affected full block verified using device CRC.',
                    blocks=[dict(address=address, before_sha256=digest(before), after_sha256=digest(after),
                                 before_crc=crc(before), after_crc=crc(after)) for address, before, after in snapshots])
    for address, before, after in snapshots:
        (folder/f'{address:08x}.before.bin').write_bytes(before)
        (folder/f'{address:08x}.after.bin').write_bytes(after)
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return folder, manifest


def load_session(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    baseline, target = (folder/'baseline.bin').read_bytes(), (folder/'target.bin').read_bytes()
    if digest(baseline) != manifest['baseline_sha256'] or digest(target) != manifest['target_sha256']:
        raise ValueError('Transfer snapshot hash mismatch.')
    plan = prepare_plan(baseline, target)
    if [b['address'] for b in manifest['blocks']] != [b['flash_start'] for b in plan['affected_blocks']]:
        raise ValueError('Transfer addresses differ from validated wallpaper plan.')
    for record in manifest['blocks']:
        for kind, data in [('before', baseline), ('after', target)]:
            block = (folder/f'{record["address"]:08x}.{kind}.bin').read_bytes()
            if block != block_image(data, record['address']) or digest(block) != record[kind+'_sha256']:
                raise ValueError('Erase-block snapshot mismatch.')
    return manifest


def execute_upload(folder, *, confirmed=False, restore=False, progress=lambda message: None):
    """Only explicit callers may start verified data-block programming."""
    if not confirmed:
        raise ValueError('Explicit confirmation of the prepared transfer is required.')
    folder = Path(folder)
    manifest = load_session(folder)
    info = probe()
    if (info['application_version_word'], info['application_variant_word']) != ('0000001f', '00010000'):
        raise ValueError('Radio version differs from the inspected reference.')
    desired = 'before' if restore else 'after'
    # Check every block BEFORE the first erase. Restore can recover a partial
    # erase/program operation from the already-verified saved preimage.
    if not restore:
        for index, record in enumerate(manifest['blocks']):
            progress(f'Checking transfer: {index+1}/{len(manifest["blocks"])}')
            actual = probe_resource_crc(record['address'], ERASE_BYTES)['returned_crc_word']
            if actual not in (record['before_crc'], record['after_crc']):
                raise ValueError('Device changed since preparation. Use saved recovery only if an upload was interrupted.')
    manifest['state'] = 'restoring' if restore else 'uploading'
    _save_manifest(folder, manifest)
    sequence = secrets.randbelow(0x7fffffff)+1
    try:
        for index, record in enumerate(manifest['blocks']):
            address = record['address']
            progress(f'{"Restoring" if restore else "Uploading"} block {index+1}/{len(manifest["blocks"])}')
            expected = record[desired+'_crc']
            if probe_resource_crc(address, ERASE_BYTES)['returned_crc_word'] == expected:
                progress(f'{"Restored" if restore else "Uploaded"} block {index+1}/{len(manifest["blocks"])}')
                continue
            data = (folder/f'{address:08x}.{desired}.bin').read_bytes()
            # No commands 2/3 (mode/application erase), no target-1 code writes,
            # no reboot. Each operation is confined to a validated image block.
            _exchange_validated(erase_request(sequence, address)); sequence += 1
            for offset in range(0, ERASE_BYTES, 256):
                page = data[offset:offset+256]
                if page != b'\xff'*256:
                    _exchange_validated(program_request(sequence, address+offset, page)); sequence += 1
            if probe_resource_crc(address, ERASE_BYTES)['returned_crc_word'] != expected:
                raise RuntimeError(f'Block verification failed at {address:#x}. Stop and restore the saved session.')
            record['verified'] = desired
            _save_manifest(folder, manifest)
            progress(f'{"Restored" if restore else "Uploaded"} block {index+1}/{len(manifest["blocks"])}')
        expected_resource = (folder/('baseline.bin' if restore else 'target.bin')).read_bytes()
        for offset in range(0, RESOURCE_LENGTH, 65536):
            block = expected_resource[offset:offset+65536]
            if probe_resource_crc(RESOURCE_FLASH_START+offset, len(block))['returned_crc_word'] != crc(block):
                raise RuntimeError('Final resource verification failed. Restore the saved session.')
            progress(f'Verifying resource: {min(offset+len(block), RESOURCE_LENGTH)}/{RESOURCE_LENGTH} bytes')
        manifest['state'] = 'restored' if restore else 'complete'
        _save_manifest(folder, manifest)
    except Exception as error:
        manifest['state'] = 'failed'
        manifest['error'] = str(error)
        _save_manifest(folder, manifest)
        raise RuntimeError(f'{error}\nRecovery snapshot: {folder}\nKeep the radio in update mode and use Restore USB session.') from error
    return manifest


def _save_manifest(folder, manifest):
    temporary = folder/'manifest.pending'
    temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    temporary.replace(folder/'manifest.json')
