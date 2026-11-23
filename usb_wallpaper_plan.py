"""Prepare a bounded three-slot USB transfer plan. Never communicates with USB.

This is a planner, not an uploader. Live baseline verification, complete erase
block backup, command semantics, and interruption recovery remain required.
"""
import argparse
import hashlib
import json
from pathlib import Path
from patch_wallpaper import SLOTS, WALLPAPER_ARTWORK, CHARACTER_THEME_SLOT, WIDTH, HEIGHT, RESOURCE_LENGTH, validate_resource

RESOURCE_FLASH_START = 0x80000
ERASE_BYTES = 4096


def prepare_plan(baseline, target):
    """Permit changes only in stock wallpaper pixels and the resource CRC."""
    if len(baseline) != RESOURCE_LENGTH or len(target) != RESOURCE_LENGTH:
        raise ValueError('Both resources must have the original fixed length.')
    validate_resource(baseline)
    validate_resource(target)
    allowed = sorted((offset, offset+WIDTH*HEIGHT*2) for _, offset in WALLPAPER_ARTWORK.values())
    allowed.append((RESOURCE_LENGTH-4, RESOURCE_LENGTH))
    cursor = 0
    for start, end in allowed:
        if baseline[cursor:start] != target[cursor:start]:
            raise ValueError('Changes outside stock wallpaper artwork and CRC are prohibited.')
        cursor = end
    changed_offsets = [i for i, (a, b) in enumerate(zip(baseline, target)) if a != b]
    sector_starts = sorted({(RESOURCE_FLASH_START+i)//ERASE_BYTES*ERASE_BYTES for i in changed_offsets})
    sectors = []
    resource_end = RESOURCE_FLASH_START+RESOURCE_LENGTH
    for start in sector_starts:
        lo, hi = max(start, RESOURCE_FLASH_START), min(start+ERASE_BYTES, resource_end)
        a, b = lo-RESOURCE_FLASH_START, hi-RESOURCE_FLASH_START
        sectors.append(dict(flash_start=start, flash_end_exclusive=start+ERASE_BYTES,
                            resource_start=a, resource_end_exclusive=b,
                            changed_bytes=sum(x != y for x, y in zip(baseline[a:b], target[a:b])),
                            bytes_outside_resource_to_preserve=ERASE_BYTES-(hi-lo),
                            full_device_block_backup_required=True,
                            original_resource_slice_sha256=hashlib.sha256(baseline[a:b]).hexdigest(),
                            target_resource_slice_sha256=hashlib.sha256(target[a:b]).hexdigest()))
    theme_offset = CHARACTER_THEME_SLOT[1]
    theme_changed = baseline[theme_offset:theme_offset+WIDTH*HEIGHT*2] != target[theme_offset:theme_offset+WIDTH*HEIGHT*2]
    changed_slots = [slot for slot, (_, offset) in SLOTS.items()
                     if baseline[offset:offset+WIDTH*HEIGHT*2] != target[offset:offset+WIDTH*HEIGHT*2]]
    if theme_changed and 'character' not in changed_slots:
        changed_slots.append('character')
    return dict(format='nb4-three-slot-usb-plan', version=1,
                status='Offline plan only; not authorized or implemented as a device write operation.',
                resource_flash_start_inferred=RESOURCE_FLASH_START,
                resource_bytes=RESOURCE_LENGTH,
                baseline_sha256=hashlib.sha256(baseline).hexdigest(),
                target_sha256=hashlib.sha256(target).hexdigest(),
                baseline_verified_on_device=False,
                device_block_backups_complete=False,
                device_transfer_implemented=False,
                firmware_code_write_planned=False,
                changed_bytes=len(changed_offsets), erase_block_bytes=ERASE_BYTES,
                affected_blocks=sectors,
                changed_slots=changed_slots, character_theme_variant_changed=theme_changed,
                preconditions=['Verify the live resource matches the baseline before accepting this plan.',
                               'Read and back up every complete affected erase block, including bytes outside the resource.',
                               'Prove data-only command semantics and supported operating mode.',
                               'Establish interrupted-write recovery before allowing erase/program operations.'])


def merge_device_block(plan, block_index, device_block, target):
    """Offline merge preserving adjacent device bytes; never writes a device."""
    if not isinstance(block_index, int) or not 0 <= block_index < len(plan['affected_blocks']):
        raise ValueError('Invalid affected block index.')
    if len(device_block) != ERASE_BYTES:
        raise ValueError('A full 4096-byte device block backup is required.')
    if hashlib.sha256(target).hexdigest() != plan['target_sha256']:
        raise ValueError('Target does not match the plan.')
    block = plan['affected_blocks'][block_index]
    a, b = block['resource_start'], block['resource_end_exclusive']
    offset = RESOURCE_FLASH_START+a-block['flash_start']
    if hashlib.sha256(device_block[offset:offset+b-a]).hexdigest() != block['original_resource_slice_sha256']:
        raise ValueError('Device block does not match the planned baseline; stop and inspect it.')
    result = bytearray(device_block)
    result[offset:offset+b-a] = target[a:b]
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=Path(__file__).parent/'resource_10_901_1033.bin')
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare_plan(args.baseline.read_bytes(), args.target.read_bytes())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(f"Prepared offline plan: {len(result['affected_blocks'])} affected blocks, {result['changed_bytes']} changed bytes.")
    print('No device access or writes performed.')
