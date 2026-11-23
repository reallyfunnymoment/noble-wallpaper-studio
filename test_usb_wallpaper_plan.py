import hashlib
from pathlib import Path
import struct
import unittest
from checksums import crc32_nonref, reverse_words
from patch_wallpaper import SLOTS, CHARACTER_THEME_SLOT, WIDTH, HEIGHT
from usb_wallpaper_plan import prepare_plan, merge_device_block, ERASE_BYTES, RESOURCE_FLASH_START
from test_fixtures import synthetic_resource

ROOT = Path(__file__).parent


class USBPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = synthetic_resource()
        target = bytearray(cls.baseline)
        target[SLOTS['model'][1]] ^= 1
        struct.pack_into('<I', target, len(target)-4, crc32_nonref(reverse_words(target[:-4])))
        cls.target = bytes(target)
        cls.plan = prepare_plan(cls.baseline, cls.target)

    def test_plan_has_only_wallpaper_and_checksum_blocks(self):
        self.assertEqual(self.plan['changed_slots'], ['model'])
        self.assertEqual(len(self.plan['affected_blocks']), 2)
        self.assertFalse(self.plan['firmware_code_write_planned'])
        self.assertFalse(self.plan['device_transfer_implemented'])
        last = self.plan['affected_blocks'][-1]
        self.assertEqual(last['bytes_outside_resource_to_preserve'], 2192)
        self.assertTrue(last['full_device_block_backup_required'])

    def test_complete_block_merge_preserves_adjacent_bytes(self):
        for index, entry in enumerate(self.plan['affected_blocks']):
            backup = bytearray(b'\x53'*ERASE_BYTES)
            a, b = entry['resource_start'], entry['resource_end_exclusive']
            offset = RESOURCE_FLASH_START+a-entry['flash_start']
            backup[offset:offset+b-a] = self.baseline[a:b]
            merged = merge_device_block(self.plan, index, backup, self.target)
            self.assertEqual(merged[offset:offset+b-a], self.target[a:b])
            self.assertEqual(merged[:offset], backup[:offset])
            self.assertEqual(merged[offset+b-a:], backup[offset+b-a:])
            with self.assertRaises(ValueError):
                merge_device_block(self.plan, index, backup[:-1], self.target)
            backup[offset] ^= 1
            with self.assertRaisesRegex(ValueError, 'baseline'):
                merge_device_block(self.plan, index, backup, self.target)

    def test_valid_crc_does_not_allow_changes_to_unrelated_resources(self):
        bad = bytearray(self.target)
        bad[0x3000] ^= 1
        struct.pack_into('<I', bad, len(bad)-4, crc32_nonref(reverse_words(bad[:-4])))
        with self.assertRaisesRegex(ValueError, 'outside'):
            prepare_plan(self.baseline, bad)

    def test_alternate_character_artwork_is_bounded_and_reported(self):
        target = bytearray(self.baseline)
        offset = CHARACTER_THEME_SLOT[1]
        target[offset] ^= 1
        struct.pack_into('<I', target, len(target)-4, crc32_nonref(reverse_words(target[:-4])))
        plan = prepare_plan(self.baseline, target)
        self.assertEqual(plan['changed_slots'], ['character'])
        self.assertTrue(plan['character_theme_variant_changed'])
        bad = bytearray(self.baseline)
        bad[offset+WIDTH*HEIGHT*2] ^= 1
        struct.pack_into('<I', bad, len(bad)-4, crc32_nonref(reverse_words(bad[:-4])))
        with self.assertRaisesRegex(ValueError, 'outside'):
            prepare_plan(self.baseline, bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
