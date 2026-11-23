# Using Noble Wallpaper Studio

**Currently supports Noble NB4+ firmware 1.0.31 only.** Do not use it with other
firmware versions or transmitter models. The exact supported reference is the
EN 1.0.31-4 updater package.

## Edit wallpapers

1. Choose one of the three slots: Model, Character, or Scenery.
2. Import a photo. PNG, JPEG, WebP, BMP, and TIFF are supported.
3. Use **Fill** to crop or **Fit** to keep the full image with black padding.
4. Drag the preview to position it. Use the wheel or slider to zoom.
5. Adjust rotation, brightness, contrast, color, and sharpness. You can type
   values and press Enter or Tab; rotation arrows step by 0.1 degrees.
6. Save a `.nb4project` to keep all three original images and adjustments.

Project labels stay on the PC. The transmitter keeps its stock slot names.
**Save selected PNG** exports the expected displayed image at 320 × 398.

## Import your reference

Choose **Import firmware reference** and select the unchanged FlySky Noble NB4+
EN 1.0.31-4 updater. The editor verifies its SHA-256 and extracts the data
locally. It never executes that updater. A different updater is rejected.
The public download contains neither vendor firmware nor vendor artwork.

Until you import a reference, slots start with neutral placeholders. You can
still import photos, edit images, save projects, and export PNGs. After importing,
**New** or **Restore stock image** loads the original wallpapers.

## Match the transmitter theme

Set **Transmitter theme** to the radio's System → Theme selection: Technology
Cyan, Vibrant Yellow, Bright Red, or Fresh Blue. This applies to all three slots.
The editor compensates for the firmware's global color changes. If you switch
themes later, prepare and upload again. This does not change the radio's theme.

**Keep Character artwork consistent** also replaces the separate portrait used
by Bright Red and Fresh Blue. Theme compensation and this additional artwork
path still need a device display check in this beta.

## Upload via USB

1. Turn off the receiver. Connect the transmitter by USB.
2. On the transmitter, select **System → Firmware Update**. Close the vendor
   updater and other software using the radio.
3. Choose **Upload wallpapers via USB** in the editor.
4. The editor checks radio metadata, identifies a known resource baseline,
   verifies affected blocks, and saves a recovery session before any writes.
5. Review the changed slots and selected theme, then confirm the upload.
6. Keep USB and transmitter power connected. The centered progress window shows
   the current stage, percentage, and elapsed time.
7. After successful verification, restart the transmitter.

Only bounded wallpaper data and its checksum are changed. Application erase,
application-code programming, and reboot commands are excluded. If the radio
does not match a locally known baseline, preparation stops before writing.

## Recovery and storage

The release stores imported references and recovery sessions under
`%LOCALAPPDATA%\NobleWallpaperStudio`. Upgrading or replacing the application
folder does not remove them. Keep recovery sessions until the radio has been
checked. Projects can be saved wherever you choose.

If an upload fails, keep the transmitter in update mode. Choose **Restore USB
session** and select the folder named in the error. Restoration writes the
previous wallpaper data and verifies it. Interrupted-write recovery has been
tested against simulated flash, not a real interrupted transmitter upload.

Snapshots are reconstructed from known local resources and checked using device
CRCs; they are not raw flash dumps. Existing development checkouts continue using
their local `usb_backups` folder so old recovery sessions remain accessible.

If you used the earlier prototype and are moving to the standalone release,
copy its existing `usb_backups` sessions into
`%LOCALAPPDATA%\NobleWallpaperStudio\usb_backups` before uploading again. Those
sessions let the release recognize your already-customized wallpapers. Keep
the original sessions until the move and the radio's display have been checked.

## Export a package

**Export radio package** creates a new folder with the patched Data.bin, your
unchanged imported updater, previews, and editable project. It does not run the
updater. The vendor updater's external-data route has not been hardware tested;
the direct USB workflow is the tested route. Exported folders contain your
reference firmware and photos and are not the public software release.
