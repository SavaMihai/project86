# Project86 status

Updated 2026-10-26. This document summarizes the current implementation and its
recorded validation. Historical reports describe their original build and test
runs; they do not establish validation of later changes.

## Implementation

Project86 is an independent C++20 x86 interpreter with native SwiftUI, Metal,
input and audio integration on Apple Silicon. It boots real Microsoft MS-DOS
4.00 and executes DOS programs and drivers as guest code. No existing emulator
engine, external reference runtime, JIT or host replacement for DOS system calls
is used. The shared C API is [project86.h](../core/include/project86.h).

- The app uses a supported 286 real-mode subset; hardware fixtures use explicit
  8086 semantics. Unsupported instructions, services and device accesses remain
  diagnostic events. See [architecture](ARCHITECTURE.md).
- The default DOS build uses the original COMSUBS, CASSFAR, SLIBCE and MEM binary
  libraries and period compiler tools. DOS executables are rebuilt inside
  Project86, but not every linked byte or the compiler toolchain is source-built.
  Optional COMSUBS/CASSFAR replacements are selected with `DOS_LIBRARIES=source`.
  See [source completeness](SOURCE-COMPLETENESS.md) and
  [original libraries](ORIGINAL-LIBRARIES.md).
- COMMAND.COM includes 16-entry session history, cursor editing and Tab
  completion. History survives transient reloads; redirected input, batch files
  and `/C` retain DOS behavior. Directory completion adds no trailing separator,
  because DOS 4 CD rejects it. See [COMMAND](COMMAND-EDITOR.md).
- Source-built CuteMouse 2.1 beta4 handles the emulated COM1 mouse. Serial reset
  gates input until identification and a neutral packet have been emitted.
  See [serial mouse behavior](SERIAL-MOUSE.md).
- Native builds default to optimized Release, 8x CPU throughput and 60 Hz display
  updates. The C API defaults to 1x. CPU speed is independent of device/audio time
  and is selectable with four toolbar buttons: 1x, 4x, 8x and 16x. Frame updates
  are observed separately from control state. See [performance](PERFORMANCE.md).
- Startup loads CuteMouse quietly, displays `MS-DOS 4.0 (Project86)` and uses
  `PROMPT $P$G`. Manual VER retains the compiled version message.

## Build and packaging

`project.yml` is authoritative for Xcode configuration. Generated Xcode projects,
compiled products, downloaded guest assets and writable disks are not committed.
The [README](../README.md) contains prerequisites and reproduction commands.

| Artifact | Default location |
|---|---|
| Native Mac app | `.build/apple-speed-control/Build/Products/Release/Project86.app` |
| DOS build | `.build/dos-command-editor-v2/` |
| Mouse build | `.build/cutemouse-build/` |
| Packaged floppy and receipt | `.build/guest-boot/` |

The recorded packaged floppy SHA-256 is
`273a9ac86fc1e9a1f9ff4d16062fea4b95aa53e128b225fcaa5a94d4f33f6e3c`.
COMMAND.COM SHA-256 is
`2f4aa05f10a69c728567389cdbc941296e1bfd5b0096b164735e122e8215c034`.
See the [packaging receipt](evidence/simple-banner-boot.json).

Packaging verifies DOS and mouse build outputs and creates a fresh FAT12 disk.
It has no downloaded-executable fallback. Corresponding mouse sources, required
licenses and the project's guest modifications accompany the app. Pinned inputs
and third-party terms are recorded in [THIRD_PARTY.md](../THIRD_PARTY.md).

Fresh builds need a new `DOS_BUILD` directory. Rebuilt-floppy bootstrapping also
requires a preserved packaged seed and its matching DOS build, selected through
`DOS_SEED` and `DOS_SEED_BUILD`. Preserve expensive build inputs and receipts;
avoid routine deletion of `.build/`, `.cache/` or downloaded originals.

## Validation and limits

Recorded checks cover core/devices, native pointer accumulation, shell history
and completion, mouse startup, packaging, private-disk persistence, and Release
Mac and iPad simulator builds. See [validation](VALIDATION.md),
[performance results](evidence/performance-validation.json) and
[CPU control checks](evidence/cpu-speed-control-validation.json).

Historical CPU testing covers 386,000 physical-8086 fixture cases. Earlier
subsequent DOS builds reproduced 63 artifacts exactly; that result applies to
the specific builds in their reports. It does not rebuild the compiler toolchain
or eliminate the original binary-library dependencies.

User-supplied Wolfenstein 3D shareware v1.4 passed short headless gameplay,
movement/fire, serial mouse, audio generation, save/restart/load and framebuffer
checks. Game files are not included. The
[game manifest](evidence/wolf-shareware-manifest.json) identifies the tested files.
The measured 65-70 VGA page switches per guest second at 8x are a render proxy,
not native-window FPS. Native interaction and audio fidelity require separate
acceptance. Prince of Persia and Monkey Island remain untested targets.

Mac development has priority. Physical iPad testing, 386 protected mode,
Doom-era support, networking, save-state snapshots and App Store submission
remain deferred. See [roadmap](ROADMAP.md).

## Development checks and disk safety

Run checks appropriate to the changed subsystem:

```sh
make all test input-tests ui-state-tests
python3 scripts/test_dos.py
make guest-tests packaging-tests
make mac
make ios
```

Choose private disks for write tests. The app preserves imported originals and
writable working copies under its Application Support directory. Pause or quit
normally to flush disk changes. Import a new bundled floppy as a new working disk,
keep the previous floppy recoverable and preserve the attached hard disk.
