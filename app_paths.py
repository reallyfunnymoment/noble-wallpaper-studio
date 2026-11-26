"""Separate read-only application files from persistent user data."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('NB4_STUDIO_DATA_DIR') or
                Path(os.environ.get('LOCALAPPDATA', Path.home()))/'NobleWallpaperStudio')


def stock_resource_path():
    installed = DATA_DIR/'reference'/'resource_10_901_1033.bin'
    legacy = ROOT/'resource_10_901_1033.bin'
    return installed if installed.is_file() or not legacy.is_file() else legacy


def original_updater_path():
    active = DATA_DIR/'reference'/'original_updater.exe'
    if active.is_file():
        return active
    installed = DATA_DIR/'reference'/'Flysky_Noble+Plus+EN_UpdateFirmware_1.0.31-4.exe'
    legacy = ROOT/'stock_restore'/'Flysky_Noble+Plus+EN_UpdateFirmware_1.0.31-4.exe'
    return installed if installed.is_file() or not legacy.is_file() else legacy


def backup_directory():
    # Keep existing development sessions accessible without moving recovery files.
    legacy = ROOT/'usb_backups'
    return legacy if legacy.is_dir() else DATA_DIR/'usb_backups'
