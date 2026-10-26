# Guest software, fixtures and reference provenance

Project86-authored code is covered by the [MIT License](LICENSE). That license
does not replace the terms or notices of third-party software, datasets or game
content described below.

Project86's emulator code is independently authored. This file records external guest software, test data and documentation, rather than emulator dependencies. No existing emulator was used as a reference runtime.

## Microsoft MS-DOS 4.00

- Microsoft source: https://github.com/microsoft/MS-DOS
- Restoration author and downloads: https://felsqualle.com/posts/2024/05/the-broken-source-code-for-ms-dos-4-has-been-restored/
- Download URLs, exact sizes and SHA-256 hashes: `assets/bootstrap-manifest.json`.
- Preserved artifacts: `assets/bootstrap/msdos400.ima`, `restored-source.zip`, `MICROSOFT-LICENSE.txt` (MIT). These are downloaded, ignored artifacts, not committed binaries.
- The app includes a newly constructed floppy containing our assembled boot sector and all 62 DOS distribution files, a packaging receipt and the Microsoft license. The downloaded image is an initial/recovery boot seed for compiling DOS; it is not a packaging input or app resource. Explicitly seeded subsequent builds boot our verified rebuilt floppy and do not access the downloaded image. The original source archive stays in the workspace. No DOS kernel patches were made.
- The supplied source contains period Microsoft tools and binary runtime/support libraries used for the rebuild. Preserve their notices; do not assume that this project's code determines their licensing.
- Our initial in-emulator rebuild matched all 62 distribution files exactly, plus boot code outside the media parameter fields. See `docs/evidence/full-dos-rebuild.json`. The earlier VER variant changed only COMMAND.COM (`docs/evidence/dos-ver-rebuild.json`). The restored-library milestone reproduced all 63 artifacts of that VER build. The current default additionally changes COMMAND.COM for history and Tab completion. The optional COMSUBS/CASSFAR variant changes six additional utilities; its earlier evidence remains historical. This establishes correspondence for pinned inputs, not an independent provenance audit of every archived file.

The complete inventory in `assets/dos-files.json` distinguishes 58 ordinary compiled/generated outputs, two assembled printer CPI data files, two unchanged text source profiles, and the boot sector. The 4201/4208 makefiles were empty; `guest-build/printer-cpi.asm` wraps the original published `.INC` byte declarations so original MASM/LINK/EXE2BIN regenerate the CPI files. The prebuilt CPI files and archived PRINTF/STRING intermediates are removed before the clean build. The other build repair is SETENV.BAT's backup drive, D: to C:.

The earlier VER customization patches message 1040 in `SRC/MESSAGES/USA-MS.MSG` before compilation, preserving the original version substitutions and copyright messages. It is recorded in `source_patches` and the patched message source hash in the build report. It does not modify the kernel's numeric DOS version.

The second-generation build booted the first generation's packaged image and reproduced all 63 artifacts and the output ZIP exactly. The first-generation image/receipt, retained source-build disk and restoration originals remain available. Its schema-3 report records the seed's image and receipt hashes, the parent build provenance, the privately configured compiler image, and every artifact comparison. Access to the downloaded floppy and network was blocked during the complete run. See `docs/evidence/dos-second-generation.json` and `docs/evidence/dos-second-generation-validation.json`. This is DOS boot-seed reproduction; the original toolchain and library dependencies below are unchanged.

The default retains original COMSUBS.LIB, CASSFAR.LIB, SLIBCE.LIB and MEM.LIB,
along with the original compiler tools. The preserved `.build/dos-original-libraries/` milestone reproduces all 63
pre-replacement VER artifacts. The current `.build/dos-command-editor-v2/` changes
only COMMAND.COM, using our assembly editor and the pinned Microsoft source.
The [preserved original-library linker audit](docs/evidence/dos-original-libraries-audit.json) verifies
actual loaded archive members. `retained_binary_libraries` records supplied inputs;
this inventory alone does not imply that every item was linked.

Our implementations in `guest-build/comsubs/` and `guest-build/cassfar/` remain
available through `DOS_LIBRARIES=source`. That variant removes both originals,
compiles the C/assembly with guest tools and records their hashes and corresponding
sources in `rebuilt_libraries`. The app's verified `dos-project-sources.zip` contains
build information plus only source packages actually used by the selected variant.
The default contains no library replacement sources; it includes the COMMAND
editor sources and patch recipe as `command-source.zip`. See
[COMMAND editor provenance](docs/COMMAND-EDITOR.md).

The replacements implement only the released interfaces used by this distribution.
CASSFAR's generated layouts come from pinned SELECT declarations. Original
libraries were executed as guest software for behavioral comparison; limited
object-code inspection diagnosed ABI and probe behavior. No external emulator
runtime or implementation was used. See [COMSUBS](docs/COMSUBS.md),
[CASSFAR](docs/CASSFAR.md) and [the restored default](docs/ORIGINAL-LIBRARIES.md).
Every shipped DOS executable is rebuilt, but the default is not a source rebuild
of the four linked libraries or the compiler toolchain.

Packaging checks all 63 extracted artifacts against the successful report and outputs on the retained guest build disk. `MSBOOT.BIN` consists of 0x7C00 leading zero bytes and a 512-byte sector; packaging verifies this layout, extracts the sector and replaces only bytes 11 through 61 with generated floppy BPB/EBPB values. A zero-filled disk receives fresh FAT12 tables, boot-critical IO.SYS/MSDOS.SYS root entries and contiguous data, then the remaining files. The downloaded image supplies no bytes at this stage. `project86-boot.json` records every installed hash and `retained_from_bootstrap: []`.

The prepared `project86.ima` also adds `P86BUILD.TXT`, the complete hash listing `P86FILES.TXT`, CONFIG.SYS (`FILES=64`, `BUFFERS=20`, `LASTDRIVE=C`), AUTOEXEC.BAT (PROMPT $P$G, BLASTER configuration, quiet CuteMouse loading and the concise ECHO startup banner), and our source-built CuteMouse driver. Distribution completeness is not driver compatibility: 386/protected-mode features remain unavailable.

## CuteMouse guest driver

- Upstream: https://cutemouse.sourceforge.net/
- Source archive: https://cutemouse.sourceforge.net/download/cutemouse21b4.zip
- SHA-256: `1d7f04687bafe20d9313db56d15c9df870c055dc63548aa91488e13dd741d50e`.
- Built version: CuteMouse 2.1 beta4, replacing our previously bundled prebuilt 1.9.1 alpha 1. Nagy Daniel, Eric Auer and upstream contributors retain their notices.
- License: GPL version 2 or later for the driver; assembler macro library notices include LGPL. Corresponding sources, notices and our documented changes/build recipe are preserved in the app's `cutemouse-source.zip`; COPYING is also bundled separately.
- `assets/cutemouse-manifest.json` pins both CuteMouse and JWasm source. JWasm is built natively on ARM with Apple Clang under its Sybase Open Watcom Public License; it is a build tool, not bundled emulator code. Its source archive/license remains in the build workspace.
- `scripts/rebuild_cutemouse.py` documents modern-assembler syntax repairs and the native data-only MZ header generator. We execute no prebuilt CuteMouse build tools. The published driver is used only for byte/encoding comparison, never as a reference runtime or packaging fallback.
- The complete original archives remain cached outside the app. No original EXE/COM/OBJ/BIN files are included in the corresponding-source package. A standalone rebuild from that package reproduced our driver exactly.
- No driver code is linked into the emulator. It executes inside DOS through our CPU, BIOS and UART.

The [source completeness report](docs/SOURCE-COMPLETENESS.md) distinguishes the source-built driver, optional replacements and four default binary DOS libraries. Its linker audit measures actual members loaded into utilities.

## Hardware-derived tests

- Dataset: https://github.com/SingleStepTests/8086
- Revision: `e71c68d215a6bb8c356bd4cb3842de3bef345ca9`.
- Fixture license is fetched and preserved at `.cache/hardware/LICENSE`.
- Each report records SHA-256 hashes of the fixture files used. The fixture generator/emulator is not run; Project86 compares its CPU's output directly with the published physical-8086 register, defined-flag and RAM data.

## User-supplied games

Wolfenstein 3D DOS shareware v1.4 exact hashes are in `docs/evidence/wolf-shareware-manifest.json`. Originals are untouched; derived disks are ignored build artifacts. Game binaries/data are not bundled or committed. Small validation screenshots are evidence of the user's supplied game running. Prince of Persia and Monkey Island have not been supplied or tested.

## Hardware references

- Intel 80286/80287 Programmer's Reference Manual: https://bitsavers.org/components/intel/80286/210498-005_80286_and_80287_Programmers_Reference_Manual_1987.pdf
- Yamaha YM3812 datasheet: https://www.ardent-tool.com/datasheets/Yamaha_YM3812.pdf
- Yamaha YM3812 application manual: https://c64.xentax.com/media/Yamaha_YM3812_Application_Manual.pdf
- Creative Sound Blaster hardware programming guide collection: https://www.phatcode.net/articles.php?id=243
- Apple runtime security: https://support.apple.com/en-ca/guide/security/sec15bfe098e/web

Native tools include Apple Clang/Swift/Xcode, XcodeGen, Python and NASM/NDISASM. Assemblers and disassemblers do not execute guest code.
