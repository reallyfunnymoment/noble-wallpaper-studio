"""Build the Windows x64 application and its release zip. Run on Windows."""
import hashlib
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_version import VERSION


def build():
    if sys.platform != 'win32':
        raise SystemExit('Build the Windows release using Windows Python.')
    # Fail before packaging if a restricted build environment hides Tcl/Tk.
    # PyInstaller can otherwise succeed while silently excluding the GUI.
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.destroy()
    output = ROOT/'dist'
    work = ROOT/'build'/'pyinstaller'
    work.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT/'build'/'cache'))
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir', '--windowed', '--name', 'NobleWallpaperStudio',
        '--distpath', str(output/'windows'), '--workpath', str(work/'work'),
        '--specpath', str(work), '--exclude-module', 'matplotlib',
        '--exclude-module', 'numpy', '--exclude-module', 'capstone',
        str(ROOT/'wallpaper_editor.py'),
    ], cwd=ROOT, check=True, env=environment)
    return package(output/'windows'/'NobleWallpaperStudio')


def package(folder):
    """Refresh docs, notices, and checksums around an existing verified build."""
    output = ROOT/'dist'
    folder = Path(folder)
    if not (folder/'NobleWallpaperStudio.exe').is_file():
        raise FileNotFoundError('Build the Windows executable before packaging.')
    for name in ('LICENSE', 'README.md', 'USER_GUIDE.md', 'RELEASE_NOTES.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name, folder/name)
    # Bundle the dependency's actual license notices, including Pillow codecs.
    licenses = folder/'licenses'
    licenses.mkdir(exist_ok=True)
    for name, relative in [('Python', 'LICENSE.txt'), ('Tcl', 'tcl/tcl8.6/license.terms'),
                           ('Tk', 'tcl/tk8.6/license.terms')]:
        source = Path(sys.base_prefix)/relative
        if source.is_file():
            (licenses/name).mkdir(exist_ok=True)
            shutil.copy2(source, licenses/name/source.name)
    for package in ('Pillow', 'PyInstaller'):
        metadata = importlib.metadata.distribution(package)
        for entry in metadata.files or ():
            if any(word in str(entry).lower() for word in ('license', 'copying', 'notice')):
                source = Path(metadata.locate_file(entry))
                if source.is_file():
                    destination = licenses/package/str(entry)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    dependencies = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
    (folder/'BUILD-DEPENDENCIES.txt').write_text(dependencies, encoding='utf-8')
    archive = output/f'NobleWallpaperStudio-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                package.write(path, path.relative_to(folder.parent))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
    print(f'Prepared {archive}')
    return archive


if __name__ == '__main__':
    if sys.argv[1:] == ['--package-only']:
        package(ROOT/'dist'/'windows'/'NobleWallpaperStudio')
    elif sys.argv[1:]:
        raise SystemExit('Usage: build_windows.py [--package-only]')
    else:
        build()
