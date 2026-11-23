# Contributing

Use Python 3.14 on Windows and install `requirements-build.txt`. See RELEASING.md
for the test/build commands. Most checks use synthetic resources and simulated
flash; they require no transmitter or vendor firmware. The optional export
integration test runs only when the exact original updater is locally available.

Keep changes within the three-slot scope. Protocol changes must retain explicit
confirmation, bounded data-only writes, baseline verification, and saved recovery
sessions. Never add code-write or whole-application erase commands to this flow.

Include a reproducible description and relevant offline checks in pull requests.
Do not attach firmware packages, personal photos, projects, serial identifiers,
or raw USB/device logs to public issues. Contributions use the MIT license.
