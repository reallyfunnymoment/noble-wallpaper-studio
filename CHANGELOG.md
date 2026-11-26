# Changelog

## 0.1.0-beta.2

- Add explicitly verified EN and EU 1.0.31-4 updater profiles. Reference import
  uses the correct resource offset; export retains the selected regional
  updater unchanged. EU hardware operation still requires a device check.

- Automatically recover unfamiliar custom wallpaper data before upload, without
  requiring a matching saved baseline from the other PC.
- Preserve the previous custom wallpapers for recovery, with verified block
  caching for resume and a cancel button during read-only preparation.
- Retain firmware 1.0.31 and unrelated-resource protections. First-time readback
  may take 45 minutes or longer; full live backup still needs an end-to-end check.

- Allow shrinking images down to 0.1× using the zoom slider, typed values, or
  mouse wheel. Black padding fills the remaining 320 × 398 canvas.
- Preserve small-image positioning and zoom settings in saved projects.

## 0.1.0-beta.1

- Native Windows editor for the three existing NB4+ wallpaper slots.
- Photo import, crop, zoom, mirror, color adjustments, and fractional rotation.
- Typed adjustment values and self-contained editable projects.
- Direct USB data uploads with block checks, full-resource verification, and
  recovery sessions. Prominent stage/percentage/elapsed-time display.
- Selected-theme color compensation and optional alternate Character artwork.
- User-supplied reference import with exact supported-updater verification.
- Persistent user-data storage, MIT licensing, source packaging, and Windows CI.

Beta limits: theme compensation needs a device display check; interrupted-upload
recovery is simulated only. Additional slots and custom on-radio names are not included.
