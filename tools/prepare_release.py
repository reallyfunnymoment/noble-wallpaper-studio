"""Create a public source archive from an explicit allowlist, never the worktree."""
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_version import VERSION

PUBLIC_FILES = (
    '.gitignore', '.github/workflows/build.yml', 'LICENSE', 'README.md',
    'USER_GUIDE.md', 'CHANGELOG.md', 'RELEASING.md', 'RELEASE_NOTES.md',
    'CONTRIBUTING.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md',
    'requirements.txt', 'requirements-build.txt', 'Start Editor.cmd',
    'app_paths.py', 'app_version.py', 'firmware_reference.py', 'png_codec.py',
    'wallpaper_editor.py', 'editor_core.py', 'transfer_progress.py',
    'patch_wallpaper.py', 'checksums.py', 'wallpaper_usb.py',
    'usb_wallpaper_plan.py', 'radio_info_probe.py', 'inspect_connected_radio.py',
    'test_fixtures.py', 'test_editor.py', 'test_editor_ui.py', 'test_release.py',
    'test_radio_protocol.py', 'test_transfer_progress.py',
    'test_usb_wallpaper_plan.py', 'test_wallpaper_usb.py',
    'tools/prepare_release.py', 'tools/build_windows.py', 'docs/THEME_FINDINGS.txt',
)


def prepare(output=None):
    output = Path(output or ROOT/'dist')
    output.mkdir(parents=True, exist_ok=True)
    archive = output/f'NobleWallpaperStudio-{VERSION}-source.zip'
    prefix = f'NobleWallpaperStudio-{VERSION}'
    missing = [name for name in PUBLIC_FILES if not (ROOT/name).is_file()]
    if missing:
        raise FileNotFoundError(f'Release files missing: {missing}')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for name in sorted(PUBLIC_FILES):
            package.write(ROOT/name, f'{prefix}/{name}')
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
    print(f'Prepared {archive} ({len(PUBLIC_FILES)} public files)')
    return archive


if __name__ == '__main__':
    prepare()
