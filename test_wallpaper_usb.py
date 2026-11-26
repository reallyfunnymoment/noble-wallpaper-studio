"""Exercise upload and interrupted-upload recovery against simulated flash only."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from checksums import crc32_nonref, reverse_words
from patch_wallpaper import SLOTS
import wallpaper_usb as usb
from radio_info_probe import resource_crc_request, exchange_readonly
from test_fixtures import synthetic_resource


class UploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = synthetic_resource()
        target = bytearray(cls.baseline)
        target[SLOTS['model'][1]] ^= 1
        struct.pack_into('<I', target, len(target)-4, crc32_nonref(reverse_words(target[:-4])))
        cls.target = bytes(target)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.flash = bytearray(b'\xff'*(8*1024*1024))
        self.flash[usb.RESOURCE_FLASH_START:usb.RESOURCE_END] = self.baseline
        self.writes = []
        self.fail_page = None
        def read_crc(address, length):
            return {'returned_crc_word': usb.crc(self.flash[address:address+length])}
        def exchange(packet):
            seq, command, address, count = struct.unpack_from('<IIII', packet, 1)
            self.writes.append((command, address))
            self.assertGreaterEqual(address, usb.RESOURCE_FLASH_START)
            self.assertLess(address, usb.ALLOWED_END)
            if command == 4:
                self.assertEqual(count, 0)
                self.flash[address:address+4096] = b'\xff'*4096
            elif command == 5:
                self.assertEqual(struct.unpack_from('<I', packet, 17)[0], 2)
                if self.fail_page is not None and len(self.writes) >= self.fail_page:
                    raise OSError('Simulated USB disconnect')
                payload = packet[25:25+count]
                before = self.flash[address:address+count]
                self.assertTrue(all((a & b) == b for a, b in zip(before, payload)))
                self.flash[address:address+count] = payload
            else:
                self.fail(f'Prohibited command {command}')
            return bytes(packet), '284e'
        self.patches = [patch.object(usb, 'BACKUPS', Path(self.temp.name)),
                        patch.object(usb, 'candidates', lambda: [(Path('simulated-baseline'), self.baseline)]),
                        patch.object(usb, 'probe', lambda: dict(application_version_word='0000001f', application_variant_word='00010000')),
                        patch.object(usb, 'probe_resource_crc', read_crc),
                        patch.object(usb, '_exchange_validated', exchange)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_transfer_preserves_every_other_byte(self):
        before = bytes(self.flash)
        folder, _ = usb.prepare_upload(self.target)
        self.assertEqual(self.writes, [])
        with self.assertRaises(ValueError):
            usb.execute_upload(folder)
        messages = []
        result = usb.execute_upload(folder, confirmed=True, progress=messages.append)
        self.assertEqual(result['state'], 'complete')
        self.assertIn('Uploaded block 2/2', messages)
        self.assertEqual(messages[-1], f'Verifying resource: {usb.RESOURCE_LENGTH}/{usb.RESOURCE_LENGTH} bytes')
        self.assertEqual(self.flash[:usb.RESOURCE_FLASH_START], before[:usb.RESOURCE_FLASH_START])
        self.assertEqual(self.flash[usb.RESOURCE_FLASH_START:usb.RESOURCE_END], self.target)
        self.assertEqual(self.flash[usb.RESOURCE_END:], before[usb.RESOURCE_END:])

    def test_restore_recovers_interrupted_program(self):
        folder, _ = usb.prepare_upload(self.target)
        self.fail_page = 3
        with self.assertRaisesRegex(RuntimeError, 'Recovery snapshot'):
            usb.execute_upload(folder, confirmed=True)
        self.fail_page = None
        result = usb.execute_upload(folder, confirmed=True, restore=True)
        self.assertEqual(result['state'], 'restored')
        self.assertEqual(self.flash[usb.RESOURCE_FLASH_START:usb.RESOURCE_END], self.baseline)

    def test_upload_and_restore_preserve_unfamiliar_laptop_wallpapers(self):
        laptop = bytearray(self.baseline)
        laptop[SLOTS['scenery'][1]+17] = 0x7b
        struct.pack_into('<I', laptop, len(laptop)-4, crc32_nonref(reverse_words(laptop[:-4])))
        self.flash[usb.RESOURCE_FLASH_START:usb.RESOURCE_END] = laptop
        with patch.object(usb, 'read_stock_resource', return_value=self.baseline):
            folder, _ = usb.prepare_upload(self.target)
        self.assertEqual(self.writes, [])
        self.assertEqual((folder/'baseline.bin').read_bytes(), laptop)
        usb.execute_upload(folder, confirmed=True)
        self.assertEqual(self.flash[usb.RESOURCE_FLASH_START:usb.RESOURCE_END], self.target)
        usb.execute_upload(folder, confirmed=True, restore=True)
        self.assertEqual(self.flash[usb.RESOURCE_FLASH_START:usb.RESOURCE_END], laptop)

    def test_non_erased_adjacent_bytes_stop_preparation(self):
        self.flash[usb.RESOURCE_END] = 0
        with self.assertRaisesRegex(ValueError, 'padding'):
            usb.prepare_upload(self.target)
        self.assertEqual(self.writes, [])

    def test_rejects_code_and_cross_page_programming(self):
        for address, data in [(0x08008000, bytes(256)), (0, bytes(256)),
                               (usb.RESOURCE_FLASH_START+255, bytes(2)), (usb.ALLOWED_END, b'x')]:
            with self.assertRaises(ValueError):
                usb.program_request(1, address, data)
        with self.assertRaises(ValueError):
            usb.erase_request(1, 0)

    def test_readonly_transport_rejects_write_frames_before_device_access(self):
        packet = usb.erase_request(1, usb.RESOURCE_FLASH_START)
        with self.assertRaises(ValueError):
            exchange_readonly(packet)
        request = resource_crc_request(1, usb.RESOURCE_FLASH_START, 4096)
        self.assertEqual(struct.unpack_from('<IIIII', request, 1), (1, 6, usb.RESOURCE_FLASH_START, 4096, 0xffffffff))


if __name__ == '__main__':
    unittest.main(verbosity=2)
