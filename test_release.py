"""Release checks use synthetic resources and never access a transmitter."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from app_paths import original_updater_path
from checksums import crc32_nonref
from editor_core import stock_project, WIDTH, HEIGHT, render, DEFAULTS
from firmware_reference import import_updater, UPDATER_NAME, STOCK_SHA256
from patch_wallpaper import patch_resource, patch_character_theme, validate_resource, SLOTS, CHARACTER_THEME_SLOT
from test_fixtures import synthetic_resource
from tools.prepare_release import prepare, PUBLIC_FILES


class ReleaseTests(unittest.TestCase):
    def test_editor_starts_without_vendor_assets(self):
        with patch('editor_core.read_stock_resource', side_effect=FileNotFoundError):
            slots = stock_project()
        self.assertEqual(set(slots), set(SLOTS))
        for entry in slots.values():
            self.assertEqual(render(entry['image'], DEFAULTS).size, (WIDTH, HEIGHT))

    def test_wrong_reference_never_creates_reference_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            updater = folder/'wrong.exe'
            updater.write_bytes(b'not the supported updater')
            with self.assertRaisesRegex(ValueError, 'does not match'):
                import_updater(updater, folder/'data')
            self.assertFalse((folder/'data').exists())

    @unittest.skipUnless(original_updater_path().is_file(), 'Optional real-reference import check.')
    def test_exact_reference_import_is_local_and_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = import_updater(original_updater_path(), temporary)
            self.assertEqual((folder/UPDATER_NAME).read_bytes(), original_updater_path().read_bytes())
            self.assertEqual(hashlib.sha256((folder/'resource_10_901_1033.bin').read_bytes()).hexdigest(), STOCK_SHA256)

    def test_public_source_contains_only_allowlisted_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = prepare(temporary)
            with zipfile.ZipFile(archive) as package:
                names = [name.split('/', 1)[1] for name in package.namelist()]
                self.assertEqual(set(names), set(PUBLIC_FILES))
                for name in names:
                    self.assertNotIn(Path(name).suffix.lower(), ('.exe', '.bin', '.png', '.nb4project'))
                    self.assertNotIn('usb_backups', name)
                self.assertIn(b'firmware 1.0.31 only', package.read(package.namelist()[names.index('README.md')]).lower())
            self.assertEqual(archive.with_suffix('.zip.sha256').read_text().split()[0],
                             hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_synthetic_patcher_bounds_and_alternate_artwork(self):
        original = synthetic_resource()
        rgb = bytes((255, 0, 0))*(WIDTH*HEIGHT)
        target, _, _ = patch_resource(original, rgb, 'model')
        start = SLOTS['model'][1]
        end = start+WIDTH*HEIGHT*2
        self.assertEqual(target[:start], original[:start])
        self.assertEqual(target[end:-4], original[end:-4])
        self.assertEqual(target[start:start+2], b'\x00\xf8')
        alternate, _, _ = patch_character_theme(target, rgb)
        start = CHARACTER_THEME_SLOT[1]
        end = start+WIDTH*HEIGHT*2
        self.assertEqual(alternate[:start], target[:start])
        self.assertEqual(alternate[end:-4], target[end:-4])
        validate_resource(alternate)
        corrupt = bytearray(alternate)
        corrupt[start] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
            validate_resource(corrupt)

    def test_independent_crc_vector(self):
        self.assertEqual(crc32_nonref(b'123456789'), 0x0376e6e7)


if __name__ == '__main__':
    unittest.main(verbosity=2)
