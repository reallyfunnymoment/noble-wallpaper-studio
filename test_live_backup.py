"""No USB device required: verify unfamiliar baseline backup and exact recovery."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from checksums import crc32_nonref, reverse_words
from crc_readback import crc
from live_backup import recover_resource
from test_fixtures import synthetic_resource
from patch_wallpaper import SLOTS
import wallpaper_usb as usb


class LiveBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = synthetic_resource()
        data = bytearray(cls.stock)
        data[SLOTS['scenery'][1]+17:SLOTS['scenery'][1]+25] = bytes.fromhex('12345678abcdef01')
        struct.pack_into('<I', data, len(data)-4, crc32_nonref(reverse_words(data[:-4])))
        cls.custom = bytes(data)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.reads = []
        self.device = bytearray(self.custom)

    def query(self, address, length):
        start = address-usb.RESOURCE_FLASH_START
        self.assertGreaterEqual(start, 0)
        self.assertLessEqual(start+length, len(self.device))
        self.reads.append((start, length))
        return {'returned_crc_word': f'{crc(self.device[start:start+length]):08x}'}

    def test_unknown_custom_data_and_resume_preserve_every_byte(self):
        result = recover_resource(self.stock, self.query, self.temp.name)
        self.assertEqual(result, self.custom)
        initial_reads = sum(length == 4 for _, length in self.reads)
        self.assertGreater(initial_reads, 100)
        self.reads.clear()
        self.assertEqual(recover_resource(self.stock, self.query, self.temp.name), self.custom)
        self.assertEqual(sum(length == 4 for _, length in self.reads), 0)

    def test_unrelated_data_stops_before_wallpaper_readback(self):
        self.device[0x3000] ^= 1
        with self.assertRaisesRegex(ValueError, 'Non-wallpaper'):
            recover_resource(self.stock, self.query, self.temp.name)
        self.assertEqual(sum(length == 4 for _, length in self.reads), 0)

    def test_unknown_baseline_is_saved_then_used_on_next_pc_session(self):
        folder = Path(self.temp.name)
        with patch.object(usb, 'BACKUPS', folder), \
                patch.object(usb, 'candidates', return_value=[(Path('stock'), self.stock)]), \
                patch.object(usb, 'read_stock_resource', return_value=self.stock), \
                patch.object(usb, 'probe', return_value=dict(application_version_word='0000001f', application_variant_word='00010000')), \
                patch.object(usb, 'probe_resource_crc', side_effect=self.query), \
                patch.object(usb, '_exchange_validated') as writes:
            path, result, _ = usb.identify_baseline()
            writes.assert_not_called()
        self.assertEqual(result, self.custom)
        self.assertEqual(path.read_bytes(), self.custom)

    def test_corrupt_four_byte_response_is_rejected(self):
        def query(address, length):
            response = self.query(address, length)
            if length == 4:
                response['returned_crc_word'] = '12345678'
            return response
        with self.assertRaisesRegex(ValueError, 'block verification'):
            recover_resource(self.stock, query, self.temp.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
