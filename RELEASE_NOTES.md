# Noble Wallpaper Studio 0.1.0-beta.2

A native Windows editor for the three stock FlySky Noble NB4+ wallpaper slots.

**Currently for firmware 1.0.31 only. Other firmware versions are unsupported.**

## Download

Download `NobleWallpaperStudio-0.1.0-beta.2-windows-x64.zip`, extract the entire
folder, and run `NobleWallpaperStudio.exe`. Python is included in the package.
The source archive and SHA-256 files are supplied separately.

## Before uploading

Import your own unchanged Noble NB4+ EN 1.0.31-4 updater as the reference. It is
read as data and never executed. No vendor firmware, artwork, or personal images
are included in the public package. Put the transmitter in its built-in update
mode for USB uploads. Read USER_GUIDE.md for preparation and recovery.

## What's included

New in beta.2: shrink images down to 0.1× with the slider, typed zoom values,
or mouse wheel. Smaller images can be positioned on the black wallpaper canvas.
Existing projects remain compatible.

- Three-slot photo editor with crop, zoom, fine rotation, mirror, and color controls.
- Typed numeric adjustments, embedded-image projects, and 320 × 398 PNG export.
- Direct USB uploads, verified recovery snapshots, and centered progress.
- Theme matching and optional consistent Character artwork.

## Beta validation and limits

The saved-baseline requirement remains in this update. Direct backup that
preserves previous custom wallpapers is under investigation and has not yet
been verified on hardware. When moving to another PC, transfer your recovery
sessions as described in USER_GUIDE.md.

The original three-slot USB route was hardware tested: all 65 changed blocks
and the complete resource passed CRC verification, and the Scenery display was
confirmed. This release's theme compensation and alternate Character write need
a device display check. Recovery after an interrupted write is tested in
simulation only. Other firmware versions and hardware models are unsupported.
Changing transmitter themes after upload requires another wallpaper upload for
matching photo colors. Five/ten slots and custom radio menu names are deferred.

This is an independent community utility, not an official FlySky product.
