# Preparing a release

Use Windows x64 with Python 3.14 and Tk support.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-build.txt
.\.venv\Scripts\python -B -m unittest test_editor test_editor_ui test_release test_radio_protocol test_transfer_progress test_usb_wallpaper_plan test_wallpaper_usb -v
.\.venv\Scripts\python tools/prepare_release.py
.\.venv\Scripts\python tools/build_windows.py
```

The source script uses an explicit allowlist. It excludes local vendor updaters,
binary resources, extracted stock images, personal photos, projects, USB backups,
device logs, and investigation tools. The Windows build bundles the Python/Tk
runtime and Pillow. Do not upload the whole development workspace.

Start a GitHub repository using the contents of the **source zip**. The included
GitHub Actions workflow tests and builds downloadable artifacts; it does not
publish a release or require a write token.

For this release:

1. Check README, USER_GUIDE, version, changelog, and release notes.
2. Run the checks above and inspect the source archive contents.
3. Test the extracted Windows package from a folder without the development
   assets. Verify editing works without a reference and canceling setup is safe.
4. On compatible hardware, check theme-compensated display before claiming it
   is device verified. Leave the documented beta limit in place until then.
5. Create a GitHub release tagged `v0.1.0-beta.1`, mark it **Pre-release**, paste
   RELEASE_NOTES.md, and attach both zips and their `.sha256` files.

The application is not code-signed. Keep the checksum files with the artifacts.
Publishing to GitHub and a new hardware write are separate from local packaging.

Build method: [PyInstaller's Windows packaging documentation](https://pyinstaller.org/en/stable/usage.html).
