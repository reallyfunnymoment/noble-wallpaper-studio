import json
import struct
import tempfile
import unittest
from pathlib import Path
from editor_core import (ROOT, DEFAULTS, SLOTS, WIDTH, HEIGHT, Image, render,
                         normalize_image, quantize_preview, stock_project,
                         save_project, load_project, export_package, theme_transform, project_theme)
from patch_wallpaper import RESOURCE_OFFSET, RESOURCE_LENGTH, validate_resource, CHARACTER_THEME_SLOT
from app_paths import original_updater_path

UPDATER = original_updater_path()


class EditorTests(unittest.TestCase):
    def test_shrinking_image_keeps_black_padding_and_positioning(self):
        image = Image.new('RGB', (WIDTH, HEIGHT), 'red')
        for fit in ('Fill', 'Fit'):
            with self.subTest(fit=fit):
                centered = render(image, dict(DEFAULTS, zoom=0.5, fit=fit))
                self.assertEqual(centered.size, (WIDTH, HEIGHT))
                self.assertEqual(centered.getpixel((0, 0)), (0, 0, 0))
                self.assertEqual(centered.getpixel((160, 199)), (255, 0, 0))
                self.assertEqual(centered.getbbox(), (80, 100, 240, 299))
                corner = render(image, dict(DEFAULTS, zoom=0.5, fit=fit, x=0, y=0))
                self.assertEqual(corner.getbbox(), (0, 0, 160, 199))

    def test_small_zoom_project_roundtrip_and_lower_bound(self):
        slots = stock_project()
        slots['model']['settings']['zoom'] = 0.1
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'small.nb4project'
            save_project(path, slots)
            self.assertEqual(load_project(path)['model']['settings']['zoom'], 0.1)
            payload = json.loads(path.read_text())
            payload['slots']['model']['settings']['zoom'] = 0.09
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, 'zoom'):
                load_project(path)

    def test_crop_position_and_fit_padding(self):
        image = Image.new('RGB', (640, 398), 'red')
        image.paste('blue', (320, 0, 640, 398))
        self.assertEqual(render(image, dict(DEFAULTS, x=0)).getpixel((0, 100)), (255, 0, 0))
        self.assertEqual(render(image, dict(DEFAULTS, x=1)).getpixel((0, 100)), (0, 0, 255))
        fitted = render(image, dict(DEFAULTS, fit='Fit'))
        self.assertEqual(fitted.size, (WIDTH, HEIGHT))
        self.assertEqual(fitted.getpixel((160, 0)), (0, 0, 0))
        self.assertEqual(fitted.getpixel((10, 199)), (255, 0, 0))

    def test_alpha_is_composited_over_black(self):
        image = normalize_image(Image.new('RGBA', (1, 1), (255, 0, 0, 0)))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))

    def test_rotation_and_mirror(self):
        image = Image.new('RGB', (WIDTH, HEIGHT), 'red')
        image.paste('blue', (WIDTH//2, 0, WIDTH, HEIGHT))
        mirrored = render(image, dict(DEFAULTS, flip=True))
        self.assertEqual(mirrored.getpixel((0, 0)), (0, 0, 255))
        rotated = render(image, dict(DEFAULTS, rotation=180))
        self.assertEqual(rotated.getpixel((0, 0)), (0, 0, 255))

    def test_fractional_rotation_resamples_and_preserves_output_size(self):
        image = Image.new('RGB', (WIDTH, HEIGHT), 'black')
        image.paste('white', (150, 30, 170, 368))
        rotated = render(image, dict(DEFAULTS, rotation=12.35))
        self.assertEqual(rotated.size, (WIDTH, HEIGHT))
        self.assertNotEqual(rotated.tobytes(), render(image, DEFAULTS).tobytes())
        # A tilted line moves left at its top and right at its bottom.
        self.assertLess(max(range(WIDTH), key=lambda x: rotated.getpixel((x, 80))[0]), 150)
        self.assertGreater(max(range(WIDTH), key=lambda x: rotated.getpixel((x, 318))[0]), 170)
        self.assertTrue(any(0 < r < 255 for r, _, _ in rotated.get_flattened_data()))

    def test_theme_colors_and_transparent_key_after_compensation(self):
        # Cover every RGB565 value, including the transparent key under each transform.
        colors = []
        for value in range(65536):
            r, g, b = value >> 11, (value >> 5) & 63, value & 31
            colors.append(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
        image = Image.new('RGB', (WIDTH, HEIGHT))
        image.putdata((colors*2)[:WIDTH*HEIGHT])
        for theme in range(4):
            transformed = theme_transform(image, theme)
            self.assertEqual(theme_transform(transformed, theme).tobytes(), image.tobytes())
            displayed = quantize_preview(image, theme=theme)
            stored = theme_transform(displayed, theme)
            for expected, actual in zip(image.get_flattened_data(), displayed.get_flattened_data()):
                self.assertLessEqual(max(abs(a-b) for a, b in zip(expected, actual)), 9)
            self.assertNotIn((173, 16, 189), list(stored.get_flattened_data()))  # RGB565 0xa897
        red = Image.new('RGB', (WIDTH, HEIGHT), 'red')
        self.assertEqual(theme_transform(red, 1).getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(theme_transform(red, 2).getpixel((0, 0)), (0, 255, 255))
        self.assertEqual(theme_transform(red, 3).getpixel((0, 0)), (255, 255, 0))

    def test_project_is_self_contained_and_roundtrips(self):
        slots = stock_project()
        slots['scenery']['name'] = 'Custom mountain 🌄'
        slots['scenery']['settings'].update(x=.25, brightness=1.3, rotation=12.35)
        for entry in slots.values():
            entry['radio_theme'] = 3
        slots['character']['sync_theme_variant'] = False
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'project.nb4project'
            save_project(path, slots)
            loaded = load_project(path)
            self.assertEqual(project_theme(loaded), 3)
            self.assertFalse(loaded['character']['sync_theme_variant'])
            for slot in SLOTS:
                self.assertEqual(loaded[slot]['name'], slots[slot]['name'])
                self.assertEqual(loaded[slot]['settings'], slots[slot]['settings'])
                self.assertEqual(render(**{k: loaded[slot][k] for k in ('image', 'settings')}).tobytes(),
                                 render(slots[slot]['image'], slots[slot]['settings']).tobytes())
            payload = json.loads(path.read_text())
            payload['slots']['model']['settings']['zoom'] = float('nan')
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_project(path)

    def test_legacy_project_and_invalid_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'legacy.nb4project'
            save_project(path, stock_project())
            payload = json.loads(path.read_text())
            del payload['radio_theme']
            payload['slots']['model']['settings']['rotation'] = 270
            path.write_text(json.dumps(payload))
            self.assertEqual(load_project(path)['model']['settings']['rotation'], 270)
            self.assertEqual(project_theme(load_project(path)), 0)
            for value in (float('nan'), float('inf'), -361, 361, '12'):
                payload['slots']['model']['settings']['rotation'] = value
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    load_project(path)

    @unittest.skipUnless(UPDATER.is_file(), 'Optional integration check requires the original vendor updater.')
    def test_export_three_slots_exact_previews_boundaries_and_no_overwrite(self):
        slots = stock_project()
        for slot, color in zip(SLOTS, ('red', 'green', 'blue')):
            slots[slot]['image'] = Image.new('RGB', (WIDTH, HEIGHT), color)
            slots[slot]['radio_theme'] = 3
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'package'
            report = export_package(destination, slots, UPDATER)
            result = (destination / 'FS_FG4_CN_Data.bin').read_bytes()
            original = UPDATER.read_bytes()[RESOURCE_OFFSET:RESOURCE_OFFSET+RESOURCE_LENGTH]
            validate_resource(result)
            cursor = 0
            for slot, (_, offset) in SLOTS.items():
                self.assertEqual(result[cursor:offset], original[cursor:offset])
                cursor = offset + WIDTH*HEIGHT*2
                values = struct.unpack_from('<' + str(WIDTH*HEIGHT) + 'H', result, offset)
                decoded = bytearray()
                for value in values:
                    r, g, b = value >> 11, (value >> 5) & 63, value & 31
                    decoded.extend(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
                with Image.open(destination / f'{slot}_preview.png') as preview:
                    stored = Image.frombytes('RGB', (WIDTH, HEIGHT), bytes(decoded))
                    self.assertEqual(preview.tobytes(), theme_transform(stored, 3).tobytes())
                    self.assertEqual(quantize_preview(render(slots[slot]['image'], slots[slot]['settings']),
                                                     theme=3).tobytes(), preview.tobytes())
            _, alternate = CHARACTER_THEME_SLOT
            main = SLOTS['character'][1]
            self.assertEqual(result[alternate:alternate+WIDTH*HEIGHT*2], result[main:main+WIDTH*HEIGHT*2])
            self.assertEqual(result[cursor:alternate], original[cursor:alternate])
            cursor = alternate+WIDTH*HEIGHT*2
            self.assertEqual(result[cursor:-4], original[cursor:-4])
            self.assertFalse(report['device_tested'])
            self.assertEqual((destination / UPDATER.name).read_bytes(), UPDATER.read_bytes())
            self.assertEqual(set(load_project(destination / 'wallpapers.nb4project')), set(SLOTS))
            with self.assertRaisesRegex(ValueError, 'already exists'):
                export_package(destination, slots, UPDATER)

    def test_wrong_updater_leaves_no_partial_package(self):
        with tempfile.TemporaryDirectory() as folder:
            wrong = Path(folder) / 'wrong.exe'
            wrong.write_bytes(b'wrong')
            destination = Path(folder) / 'package'
            with self.assertRaisesRegex(ValueError, 'Updater must match'):
                export_package(destination, stock_project(), wrong)
            self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
