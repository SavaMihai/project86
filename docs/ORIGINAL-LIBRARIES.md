# Original libraries as the default

Preserved milestone, completed 2026-10-26. The current default adds the
[COMMAND editor](COMMAND-EDITOR.md) while retaining these original libraries. The owner chose to use the original COMSUBS, CASSFAR,
SLIBCE and MEM libraries after weighing compatibility and the cost of rewriting
them. This supersedes the earlier no-original-COMSUBS rule. Further library
replacement is deferred; source access elsewhere already permits DOS features.

The milestone build is `.build/dos-original-libraries/`, variant
`project86-original-libraries-v1`, report schema 6. Original compiler tools still
rebuild DOS inside Project86. This restores library inputs, not downloaded DOS
executables. The kernel, shell, boot code and utility build process are retained,
including the Project86 VER message and source-built CuteMouse.

## Results

- A full build booted the preserved CASSFAR floppy. Only JOIN, SUBST, BACKUP,
  RESTORE, REPLACE and SELECT change from that seed. All 63 outputs and the output
  ZIP exactly match the pre-replacement `.build/dos-second-generation/` baseline.
- All 61 LINK invocations were replayed on a private disk. The original archives
  supplied COMSUBS's six members, CASSFAR's 24, SLIBCE's 97 and MEM's 40. These
  counts are object modules, not unique functions. The four libraries affect
  11 distinct utilities.
- COMSUBS guest tests pass 6,456 query records, all 65,536 return codes and real
  SUBST/JOIN/REPLACE operations plus all four tested BACKUP/RESTORE combinations.
- SELECT passes 345 key searches, 57 help topics and 17 character/attribute screen
  comparisons. Both private FAT16 installations produce 69 identical files;
  configuration, invalid-path rejection and preservation checks pass. Installed
  COMMAND.COM executes after restarting the machine.
- The default passes 30 packaging/provenance tests, with two replacement-only
  classes skipped. The preserved source variant passes 32 tests, with the
  original-only class skipped. Five new cases cover pinned original library
  bytes, conflicting provenance, cache selection and stale source packaging.
- The native Mac build and full bundled-resource verification pass. A separate
  fresh `--libraries source` build reproduces all 63 experimental outputs and its
  ZIP exactly, confirming that the optional path remains usable.

App-floppy SHA-256:
`bd13775e9e09fee63eaed521031610839644aeffb5634938d4496a0ba3f29f0f`.

Evidence: [build](evidence/dos-original-libraries-build.json),
[linker audit](evidence/dos-original-libraries-audit.json),
[COMSUBS](evidence/original-libraries-comsubs-tests.json),
[SELECT](evidence/original-libraries-select-tests.json),
[packaged floppy](evidence/dos-original-libraries-boot.json),
[optional source rebuild](evidence/dos-source-option-build.json), and
[validation summary](evidence/original-libraries-validation.json).

## Selection and preservation

```sh
make mac DOS_SHELL=original DOS_BUILD=.build/dos-original-libraries APPLE_BUILD=.build/apple-original-libraries
python3 scripts/test_comsubs.py --output .build/original-comsubs-check-new
python3 scripts/test_cassfar.py --output .build/original-select-check-new
```

The native app is
`.build/apple-original-libraries/Build/Products/Debug/Project86.app`.
`APPLE_BUILD` selects another native build directory. The prior app under
`.build/apple/`, both replacement implementations, their tests, builds and
historical evidence remain intact. The three BIOS compatibility fixes discovered
while testing original SELECT/KEYB and their device regressions are retained.

For a fresh seeded original-library build:

```sh
make dos DOS_SHELL=original DOS_BUILD=.build/dos-original-new \
  DOS_SEED=.build/dos-seed-original-libraries DOS_SEED_BUILD=.build/dos-original-libraries
```

To explicitly use both source replacements:

```sh
make dos DOS_SHELL=original DOS_LIBRARIES=source DOS_BUILD=.build/dos-source-new \
  DOS_SEED=.build/dos-seed-original-libraries DOS_SEED_BUILD=.build/dos-original-libraries
make mac DOS_SHELL=original DOS_LIBRARIES=source DOS_BUILD=.build/dos-source-new APPLE_BUILD=.build/apple-source-new
```

Use the same library selection for subsequent Make commands on that build.
Direct script selection is `--libraries original` (default) or `--libraries source`.
The cache rejects a different selection; it never silently substitutes libraries.
Schema 6 checks all four original hashes on the guest build disk. Seed comparisons
account for implementation changes in either direction and reject other changes.

The app's `dos-library-sources.zip` contains build information and only the
corresponding source packages for replacements actually linked. The original
default contains build information alone. Packaging removes stale individual
replacement ZIPs and verifies the aggregate's exact contents and hashes. Older
receipts and build reports remain readable without rewriting historical evidence.

The default packaged image is `.build/guest-boot/project86.ima`. Managed user disks
were not switched or modified, and the app was not relaunched. To adopt the bundle,
use **Boot rebuilt MS-DOS (new floppy)**; the prior floppy remains recoverable and
C: is preserved. Native-window interaction, physical hardware, optional DOS Shell
media and hard-disk BIOS boot were not validated here. CPU semantics did not change;
hardware fixtures were not rerun. The compiler still reports 11 unsupported I/O
accesses, last port 06F7h. Original toolchain and library dependencies remain.
