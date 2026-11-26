"""Optional vendor-package integration checks; firmware is never distributed."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from firmware_reference import import_updater, UPDATER_NAME, STOCK_SHA256
from patch_wallpaper import extract_reference, validate_resource, RESOURCE_OFFSET, SUPPORTED_UPDATERS
from editor_core import export_package, stock_project
import app_paths

EU_FILE = Path(os.environ.get('NB4_EU_UPDATER', 'missing-eu-updater.exe'))


class ProfileTests(unittest.TestCase):
    def test_profile_offsets_are_explicit_and_region_specific(self):
        profiles = {p['region']: p for p in SUPPORTED_UPDATERS.values()}
        self.assertEqual(profiles['EN']['offset'], RESOURCE_OFFSET)
        self.assertEqual(profiles['EU']['offset'], RESOURCE_OFFSET+8)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            extract_reference(b'unsupported or altered updater')

    @unittest.skipUnless(EU_FILE.is_file(), 'Set NB4_EU_UPDATER for the optional EU integration check.')
    def test_eu_import_export_and_active_reference(self):
        updater = EU_FILE.read_bytes()
        resource, profile = extract_reference(updater)
        self.assertEqual(profile['region'], 'EU')
        self.assertEqual(hashlib.sha256(resource).hexdigest(), STOCK_SHA256)
        # The old EN-only offset would silently select the wrong bytes.
        self.assertNotEqual(updater[RESOURCE_OFFSET:RESOURCE_OFFSET+len(resource)], resource)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = import_updater(EU_FILE, root)
            self.assertEqual((folder/UPDATER_NAME).read_bytes(), updater)
            self.assertEqual((folder/'resource_10_901_1033.bin').read_bytes(), resource)
            with patch.object(app_paths, 'DATA_DIR', root):
                self.assertEqual(app_paths.original_updater_path(), folder/UPDATER_NAME)
                report = export_package(root/'export', stock_project(), app_paths.original_updater_path())
            self.assertEqual(report['reference_region'], 'EU')
            self.assertEqual(report['source_updater_sha256'], hashlib.sha256(updater).hexdigest())
            self.assertEqual((root/'export'/profile['filename']).read_bytes(), updater)
            validate_resource((root/'export'/'FS_FG4_CN_Data.bin').read_bytes())
        bad = bytearray(updater)
        bad[100] ^= 1
        with self.assertRaisesRegex(ValueError, 'does not match'):
            extract_reference(bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
