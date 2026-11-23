# Noble Wallpaper Studio

A native Windows wallpaper editor and USB uploader for the FlySky Noble NB4+.

**Currently supports firmware 1.0.31 only.** Other firmware versions and other
transmitter models are unsupported. The exact reference package is the unchanged
Noble NB4+ EN 1.0.31-4 updater; its suffix identifies the reference package.

**Status: 0.1.0-beta.1 · Windows x64 · MIT licensed**

## Get started

1. Download the Windows x64 zip from this repository's GitHub Releases.
2. Extract the entire folder and run `NobleWallpaperStudio.exe`.
3. Choose a slot and import a photo. No Python installation is needed.
4. For USB uploads or stock images, select **Import firmware reference** and
   choose your original Noble NB4+ EN 1.0.31-4 updater. The app verifies and reads
   it as data; it never runs the updater.
5. Put the radio in **System → Firmware Update** mode, choose **Upload wallpapers
   via USB**, review the prepared changes, and confirm.

Public downloads exclude vendor firmware, stock artwork, personal images, and
device logs. Image editing works before you import a firmware reference.

## Features

- Three existing Model, Character, and Scenery wallpaper slots, at 320 × 398.
- Photo import, crop, zoom, mirror, brightness, contrast, color, and sharpness.
- Fine rotation with typed angles and 0.1-degree arrow steps.
- Typed numeric adjustments and embedded-image `.nb4project` files.
- RGB565 display previews and PNG export.
- Direct USB data-only upload with per-block and full-resource CRC checks.
- Recovery sessions and a large centered progress display.
- Selected-theme color compensation and optional consistent Character artwork.

See [USER_GUIDE.md](USER_GUIDE.md) for setup, theme matching, uploads, and recovery.

## Compatibility and beta limits

**Firmware 1.0.31 only.** The reference updater must have SHA-256:

    522eeaeecc4ba120d08229ba6f12c828935c6ae61a45f002681d64c60bdfb4c5

Version metadata is checked before USB preparation and again before programming.
Unknown resource baselines stop preparation before writes. Uploads are confined
to wallpaper data and its checksum; application-code writes are excluded.

The original data-only upload passed verification on hardware, and the Scenery
image displayed correctly. Theme compensation and alternate Character artwork
still need a device display check. Interrupted-write recovery has been tested
in simulation only. Switching transmitter themes afterward requires another
wallpaper upload for matching photo colors. Additional slots and custom on-radio
names are not included in this release.

Keep the receiver off during uploads, keep power/USB connected, and retain the
saved recovery session. Reference and recovery data live in
`%LOCALAPPDATA%\NobleWallpaperStudio`, separate from the application folder.

## Run from source

Use Windows Python 3.14 with Tk support:

    py -3.14 -m venv .venv
    .\.venv\Scripts\python -m pip install -r requirements.txt
    .\.venv\Scripts\python wallpaper_editor.py

Or use `Start Editor.cmd` after installing the dependencies.
See [CONTRIBUTING.md](CONTRIBUTING.md) for tests and
[RELEASING.md](RELEASING.md) for Windows/source packaging and GitHub preparation.

## License

[MIT](LICENSE) for this project's code. Dependencies retain their own licenses;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This is an independent
community utility and is not affiliated with or endorsed by FlySky.
