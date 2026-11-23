"""Import the user's exact vendor updater as data; never execute it."""
import hashlib
import os
from pathlib import Path
import tempfile
from app_paths import DATA_DIR, stock_resource_path
from patch_wallpaper import UPDATER_SHA256, RESOURCE_OFFSET, RESOURCE_LENGTH, validate_resource

STOCK_SHA256 = '71a09fb94b656de17028ee35441dcbd0ba1b37735330eea4ea8f3f1911dab825'
UPDATER_NAME = 'Flysky_Noble+Plus+EN_UpdateFirmware_1.0.31-4.exe'


def read_stock_resource():
    data = stock_resource_path().read_bytes()
    if hashlib.sha256(data).hexdigest() != STOCK_SHA256:
        raise ValueError('Reference data does not match Noble NB4+ EN 1.0.31-4. Import the original updater again.')
    validate_resource(data)
    return data


def import_updater(path, data_directory=None):
    updater = Path(path).read_bytes()
    if hashlib.sha256(updater).hexdigest() != UPDATER_SHA256:
        raise ValueError('Choose the unchanged Noble NB4+ EN 1.0.31-4 updater. This file does not match the supported version.')
    data = updater[RESOURCE_OFFSET:RESOURCE_OFFSET+RESOURCE_LENGTH]
    if hashlib.sha256(data).hexdigest() != STOCK_SHA256:
        raise ValueError('The updater resource does not match the supported reference.')
    validate_resource(data)
    folder = Path(data_directory or DATA_DIR)/'reference'
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in [(UPDATER_NAME, updater), ('resource_10_901_1033.bin', data)]:
        fd, temporary = tempfile.mkstemp(prefix='.reference-', dir=folder)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
            os.replace(temporary, folder/name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return folder
