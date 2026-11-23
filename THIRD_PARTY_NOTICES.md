# Third-party components

Noble Wallpaper Studio's own code is MIT licensed; see LICENSE.

The Windows bundle includes CPython and Tcl/Tk, Pillow and its image codecs,
and the PyInstaller bootloader. Their licenses remain their own. Dependency
license files are collected under `licenses/`, with runtime notices also under
`_internal/`. BUILD-DEPENDENCIES.txt records the build environment.

PyInstaller's bootloader exception permits distribution of applications built
with it under their own licenses. See the bundled PyInstaller license text.

FlySky firmware, updater executables, stock artwork, product names, and trademarks
are not covered by this project's MIT license. Public packages exclude vendor
firmware and artwork; users import their own compatible reference locally.
