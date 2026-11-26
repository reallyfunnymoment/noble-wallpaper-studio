"""Import the user's exact vendor updater as data; never execute it."""
import hashlib
import os
from pathlib import Path
import tempfile
from app_paths import DATA_DIR, stock_resource_path
from patch_wallpaper import RESOURCE_SHA256, extract_reference, validate_resource

STOCK_SHA256 = RESOURCE_SHA256
UPDATER_NAME = 'original_updater.exe'


def read_stock_resource():
    data = stock_resource_path().read_bytes()
    if hashlib.sha256(data).hexdigest() != STOCK_SHA256:
        raise ValueError('Reference data does not match Noble NB4+ EN/EU 1.0.31-4. Import the original updater again.')
    validate_resource(data)
    return data


def import_updater(path, data_directory=None):
    updater = Path(path).read_bytes()
    data, _ = extract_reference(updater)
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
