# Noble NB4+ EN / EU 1.0.31-4 reference comparison

The user-supplied EU updater was inspected as data, never executed.

| Property | EN | EU |
|---|---|---|
| Updater SHA-256 | `522eeaeecc4ba120d08229ba6f12c828935c6ae61a45f002681d64c60bdfb4c5` | `1b119de1e2a0efa9787f3db3fd9abe01cd16b4a7f4069d254dcf8b9e46b90b72` |
| Data resource file offset | 908680 | 908688 |
| Data resource length | 5695344 | 5695344 |
| Application resource length | 894642 | 894650 |
| Application metadata version / variant | `0000001f` / `00010000` | `0000001f` / `00010000` |

Both data resources have SHA-256
`71a09fb94b656de17028ee35441dcbd0ba1b37735330eea4ea8f3f1911dab825`.
Thus the entire resource, including descriptors, image dictionary, artwork,
and checksum layout, is byte-for-byte identical. The application resources
are different; the EU application SHA-256 is
`750c9eac7689785e88910ce5ceb72bde2e07d26f019b00c54e8c6cace27e4f1c`.

Import and export select an explicit profile by the full updater hash. The
active reference is stored as `reference/original_updater.exe`; exported
packages retain the selected profile's canonical EN or EU filename. The
updater is copied unchanged and never executed by the editor. Legacy EN
reference paths remain readable. Only wallpaper/resource data is patched;
no application or RF-region settings are modified by this feature.

Existing USB metadata checks cover the version and variant above but do not
identify the RF region. Resource and address checks remain unchanged because
the data is identical. EU transmitter display and live USB upload still need
a device check; the package comparison alone does not prove hardware behavior.

Optional integration test (with your local EU updater):

    $env:NB4_EU_UPDATER = 'C:\path\Flysky_Noble+Plus+EU_UpdateFirmware_1.0.31-4.exe'
    python -B -m unittest test_eu_reference -v
