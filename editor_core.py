"""Image preparation and three-slot package export for the inspected NB4+ updater."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import math

ROOT = Path(__file__).resolve().parent
from PIL import Image, ImageEnhance, ImageOps
from firmware_reference import read_stock_resource
from patch_wallpaper import (SLOTS, WIDTH, HEIGHT, UPDATER_SHA256,
                             RESOURCE_OFFSET, RESOURCE_LENGTH, patch_resource,
                             validate_resource, patch_character_theme, CHARACTER_THEME_SLOT)

DEFAULTS = dict(zoom=1.0, x=0.5, y=0.5, rotation=0, flip=False,
                brightness=1.0, contrast=1.0, saturation=1.0, sharpness=1.0,
                fit='Fill')
LABELS = dict(model='Model / car', character='Character / portrait', scenery='Scenery / mountain')
THEMES = ('Technology Cyan', 'Vibrant Yellow', 'Bright Red', 'Fresh Blue')


def theme_transform(image, theme):
    """Self-inverse color compensation relative to the stock Cyan LCD mode.

    Firmware's panel callbacks swap R/B for odd themes and invert for themes
    2/3. This matches one selected theme; it cannot survive a theme switch.
    """
    if type(theme) is not int or not 0 <= theme < len(THEMES):
        raise ValueError('Invalid transmitter theme.')
    if theme & 1:
        r, g, b = image.split()
        image = Image.merge('RGB', (b, g, r))
    if theme & 2:
        image = ImageOps.invert(image)
    return image


def project_theme(slots):
    themes = {entry.get('radio_theme', 0) for entry in slots.values()}
    if len(themes) != 1:
        raise ValueError('All slots must use the same transmitter theme.')
    theme = next(iter(themes))
    if type(theme) is not int or not 0 <= theme < len(THEMES):
        raise ValueError('Invalid transmitter theme.')
    return theme


def load_image(path):
    with Image.open(path) as image:
        image.seek(0)
        return normalize_image(ImageOps.exif_transpose(image))


def normalize_image(image):
    # Flatten alpha explicitly; convert('RGB') alone would expose hidden colors.
    rgba = image.convert('RGBA')
    background = Image.new('RGBA', rgba.size, 'black')
    background.alpha_composite(rgba)
    return background.convert('RGB')


def render(image, settings):
    image = image.rotate(settings['rotation'], expand=True,
                         resample=Image.Resampling.BICUBIC, fillcolor='black')
    if settings['flip']:
        image = ImageOps.mirror(image)
    w, h = image.size
    scale = (max if settings['fit'] == 'Fill' else min)(WIDTH / w, HEIGHT / h)
    scale *= settings['zoom']
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    image = image.resize(size, Image.Resampling.LANCZOS)
    # x/y are positions within the available crop/padding range.
    left = round((WIDTH - size[0]) * settings['x'])
    top = round((HEIGHT - size[1]) * settings['y'])
    canvas = Image.new('RGB', (WIDTH, HEIGHT), 'black')
    canvas.paste(image, (left, top))
    for enhancer, key in [(ImageEnhance.Brightness, 'brightness'),
                          (ImageEnhance.Contrast, 'contrast'),
                          (ImageEnhance.Color, 'saturation'),
                          (ImageEnhance.Sharpness, 'sharpness')]:
        canvas = enhancer(canvas).enhance(settings[key])
    return canvas


def quantize_preview(image, key=0xa897, theme=0):
    rgb = bytearray(theme_transform(image, theme).tobytes())
    for i in range(0, len(rgb), 3):
        r, g, b = rgb[i:i+3]
        value = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        if value == key:
            value ^= 1
        r, g, b = value >> 11, (value >> 5) & 63, value & 31
        rgb[i:i+3] = bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
    return theme_transform(Image.frombytes('RGB', (WIDTH, HEIGHT), bytes(rgb)), theme)


def stock_project():
    try:
        data = read_stock_resource()
    except FileNotFoundError:
        data = None  # Image editing works before a firmware reference is imported.
    slots = {}
    for slot, (_, offset) in SLOTS.items():
        image = Image.new('RGB', (WIDTH, HEIGHT), '#203449')
        if data is not None:
            colors = []
            for (value,) in struct.iter_unpack('<H', data[offset:offset+WIDTH*HEIGHT*2]):
                r, g, b = value >> 11, (value >> 5) & 63, value & 31
                colors.append(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
            image.putdata(colors)
        slots[slot] = dict(name=LABELS[slot], image=image, settings=DEFAULTS.copy(), radio_theme=0)
    return slots


def save_project(path, slots):
    theme = project_theme(slots)
    records = {}
    for slot, entry in slots.items():
        buffer = io.BytesIO()
        entry['image'].save(buffer, format='PNG')
        records[slot] = dict(name=entry['name'], settings=entry['settings'],
                             png=base64.b64encode(buffer.getvalue()).decode('ascii'))
        if slot == 'character':
            records[slot]['sync_theme_variant'] = entry.get('sync_theme_variant', True)
    path = Path(path)
    # Write beside destination, then replace so an interrupted save preserves the old file.
    fd, temporary = tempfile.mkstemp(prefix='.nb4-save-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(dict(format='nb4-wallpaper-project', version=1, radio_theme=theme, slots=records), stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_project(path):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('format') != 'nb4-wallpaper-project' or payload.get('version') != 1:
        raise ValueError('This is not a supported NB4 wallpaper project.')
    if set(payload['slots']) != set(SLOTS):
        raise ValueError('Project must contain the three stock slots.')
    theme = payload.get('radio_theme', 0)
    if type(theme) is not int or not 0 <= theme < len(THEMES):
        raise ValueError('Invalid transmitter theme.')
    slots = {}
    for slot, entry in payload['slots'].items():
        settings = dict(DEFAULTS, **entry['settings'])
        ranges = dict(zoom=(1, 4), x=(0, 1), y=(0, 1), brightness=(0, 2),
                      contrast=(0, 2), saturation=(0, 2), sharpness=(0, 3))
        for key, (low, high) in ranges.items():
            if not isinstance(settings[key], (int, float)) or not low <= settings[key] <= high:
                raise ValueError(f'Invalid {key} in project.')
        angle = settings['rotation']
        if (not isinstance(angle, (int, float)) or not math.isfinite(angle)
                or not -360 <= angle <= 360 or settings['fit'] not in ('Fill', 'Fit')):
            raise ValueError('Invalid rotation or fit mode in project.')
        if not isinstance(settings['flip'], bool) or not isinstance(entry['name'], str):
            raise ValueError('Invalid name or flip setting in project.')
        with Image.open(io.BytesIO(base64.b64decode(entry['png'], validate=True))) as image:
            slots[slot] = dict(name=entry['name'][:100], image=normalize_image(image), settings=settings,
                              radio_theme=theme)
        if slot == 'character':
            sync = entry.get('sync_theme_variant', True)
            if not isinstance(sync, bool):
                raise ValueError('Invalid Character theme setting in project.')
            slots[slot]['sync_theme_variant'] = sync
    return slots


def export_package(destination, slots, updater_path):
    """Publish only a fully validated, new directory. Never runs the updater."""
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Choose a new folder name; the export folder already exists.')
    updater_path = Path(updater_path)
    updater = updater_path.read_bytes()
    if hashlib.sha256(updater).hexdigest() != UPDATER_SHA256:
        raise ValueError('Updater must match the inspected Noble NB4+ EN 1.0.31-4 package.')
    original = updater[RESOURCE_OFFSET:RESOURCE_OFFSET+RESOURCE_LENGTH]
    theme = project_theme(slots)
    result = original
    reports = {}
    previews = {}
    for slot in SLOTS:
        rgb = theme_transform(render(slots[slot]['image'], slots[slot]['settings']), theme).tobytes()
        result, preview, adjusted = patch_resource(result, rgb, slot)
        if slot == 'character' and slots[slot].get('sync_theme_variant', True):
            result, _, _ = patch_character_theme(result, rgb)
        previews[slot] = theme_transform(Image.frombytes('RGB', (WIDTH, HEIGHT), bytes(preview)), theme)
        reports[slot] = dict(name=slots[slot]['name'], pixel_offset=hex(SLOTS[slot][1]),
                             color_key_pixels_adjusted=adjusted)
    validate_resource(result)
    # Independent final boundary check for the combined patch.
    spans = sorted((offset, offset + WIDTH*HEIGHT*2) for _, offset in SLOTS.values())
    if slots['character'].get('sync_theme_variant', True):
        offset = CHARACTER_THEME_SLOT[1]
        spans.append((offset, offset+WIDTH*HEIGHT*2))
        spans.sort()
    cursor = 0
    for start, end in spans:
        if result[cursor:start] != original[cursor:start]:
            raise AssertionError('Unexpected change outside wallpaper pixels')
        cursor = end
    if result[cursor:-4] != original[cursor:-4]:
        raise AssertionError('Unexpected change outside wallpaper pixels')
    report = dict(slots=reports, source_updater_sha256=UPDATER_SHA256,
                  data_sha256=hashlib.sha256(result).hexdigest(),
                  data_crc32=hex(struct.unpack_from('<I', result, len(result)-4)[0]),
                  width=WIDTH, height=HEIGHT, device_tested=False,
                  character_theme_synced=slots['character'].get('sync_theme_variant', True),
                  transmitter_theme=THEMES[theme], theme_compensation_device_tested=False,
                  validation='Three slots and optional Character theme artwork patched; CRC and change boundaries verified.')
    staging = Path(tempfile.mkdtemp(prefix='.nb4-export-', dir=destination.parent))
    try:
        (staging / 'FS_FG4_CN_Data.bin').write_bytes(result)
        (staging / updater_path.name).write_bytes(updater)
        for slot, preview in previews.items():
            preview.save(staging / f'{slot}_preview.png')
        save_project(staging / 'wallpapers.nb4project', slots)
        (staging / 'patch_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        (staging / 'READ ME.txt').write_text(
            'Noble NB4+ EN 1.0.31-4 wallpaper package\n\n'
            'Contains an unchanged original updater and modified external Data.bin.\n'
            'Firmware 1.0.31 only. This exported package has not been display tested on your device.\n'
            'The vendor updater external-data route has not been hardware tested.\n'
            'This editor did not run the updater or access USB.\n'
            'Use only with the exact compatible hardware; back up settings and establish recovery first.\n'
            'External file lookup is relative to the updater working directory, which must be this folder.\n'
            'No external Code.bin is supplied. Project names are PC labels; radio menu names stay stock.\n', encoding='utf-8')
        with (staging / 'READ ME.txt').open('a', encoding='utf-8') as stream:
            stream.write(f'\nWallpaper colors are prepared for transmitter theme: {THEMES[theme]}.\n'
                         'Match System > Theme on the radio. If you switch themes, prepare and upload again.\n'
                         'Theme compensation is derived from firmware and has not been device tested.\n')
        # On Windows rename refuses an existing destination, including an export race.
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return report
