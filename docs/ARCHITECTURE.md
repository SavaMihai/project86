# Architecture

## Core and ownership

`core/src/cpu.cpp` decodes guest instruction bytes and updates registers, flags and memory. The guest never becomes executable host code. `machine.cpp` implements the original BIOS service trampolines, PIC, PIT, keyboard, UART, video and block disk services; `audio.cpp` implements the speaker, initial OPL2 FM synthesis and Sound Blaster DSP/DMA. The Swift layer uses only the small C API in `core/include/project86.h`.

One serial worker owns each machine. UI events enter that queue; frames leave as copied `Data`. Metal displays text rasterized with CoreText or the VGA framebuffer. Audio is copied into AVFoundation PCM buffers. No Apple framework is required by the interpreter itself; the current disk checkpoint code uses POSIX APIs shared by macOS/iOS.

## CPU model and execution

The core defaults to 8086 semantics for hardware-derived tests. The app and CLI select a 286 real-mode subset: PUSH SP, FLAGS, shift count masking, divide exceptions, immediate shifts/pushes/IMUL, PUSHA/POPA, ENTER/LEAVE, BOUND and string port I/O. This is not a complete 80286, and system/protected-mode instructions stop with a diagnostic. There is no 386, x87, extended memory, EMS or XMS.

Memory is a 1 MiB address space with 20-bit wrap. Segment offsets wrap at 16 bits. VGA memory uses four planes, latches, map masks, logical operations, chain-4 and an unchained 256-colour path. Real-mode 286 segment-limit faults are not complete. The raw fixture API bypasses BIOS/device scheduling and ROM protection, and is intended only for tests.

Execution is bounded by instruction count or a 4,772,728 Hz functional device clock.
The C API defaults to 1× CPU throughput; the app defaults to 8×, selectable from
1×/4×/8×/16×. `advance_cpu_cycles` scales instruction costs with an integer
remainder, preserving monotonic device time. Boosted modes keep port I/O at a
fixed eight-device-cycle cost; the original 1x timing remains unchanged. The run-loop safety bound scales with
throughput so it can actually deliver the requested time budget. The app schedules
60 updates per second, distributes device cycles with integer carry, and drains
800 audio samples per update at 48 kHz. This is not cycle-accurate CPU timing.
REP strings still yield between iterations, HLT advances toward device events,
and STI/MOV SS interrupt shadows remain intact. See `PERFORMANCE.md`.

## BIOS and devices

The original ROM contains IRET trampolines at F000:1000 plus eight bytes per vector. Services execute only when guest control reaches a trampoline. Guest-installed handlers and chained interrupts execute normally. DOS's INT 21h services are its real kernel code; the host does not replace DOS calls or filesystem logic.

Implemented paths include INT 10h text and selected VGA functions; INT 13h CHS block I/O; INT 16h keyboard; basic equipment, clock and configuration services; PIC IRQs; PIT ticks; an AT-style keyboard input queue; COM1 Microsoft serial mouse packets; OPL timer detection and two-operator FM; and mono 8-bit Sound Blaster DMA1/IRQ5. The prepared boot disk sets `BLASTER=A220 I5 D1 T3`. CuteMouse runs inside DOS and implements INT 33h.

Unknown CPU instructions and BIOS services stop with CS:IP diagnostics. Unknown I/O ports return open bus and are counted in diagnostics; strict I/O mode is available internally for device debugging. Several generic VGA/BIOS register paths are deliberately partial. Direct floppy-controller programming, DMA floppy transfers, accurate PIT latching, VGA BIOS font glyph services, CGA graphics and many less common BIOS operations remain incomplete. Unsupported access diagnostics are not evidence of complete device coverage.

SELECT/KEYB capability probes have explicit responses: the Convertible display
table and TopView shadow-buffer queries leave their input pointers unchanged on
our plain VGA, and INT 16h/AH=92h reports the existing enhanced-keyboard services.
These are covered by a guest-instruction regression; other unknown services still
fault. References and the reason for these additions are in `CASSFAR.md`.

OPL output is a functional initial synthesizer with approximate envelopes. Rhythm percussion, tremolo/vibrato, precise key scaling and hardware-exact waveforms are not implemented. DSP support is a subset of Sound Blaster 2.x commands. Tests establish signal generation and DMA/IRQ operation, not sound fidelity.

## Building the app boot floppy

`make dos` builds the restored source inside Project86, or verifies cached outputs. Initial builds use the restoration floppy; verified rebuilt seeds can boot subsequent compiler runs. Original binary runtime/support libraries remain build dependencies; their inventory and hashes are reported. Published 4201/4208 printer data is assembled through two small wrappers instead of reusing the prebuilt CPI files. Two text profiles are copied unchanged; all other distribution files are freshly generated.

`make guests` loads all 63 artifacts from `dos-files.zip`, checking hashes, the complete catalog and their bytes on the retained guest build disk. It extracts the assembled boot sector from MSBOOT.BIN at offset 0x7C00 after verifying the leading padding. `create_floppy` starts with zeroed 1.44 MiB storage, installs this boot code, generates media fields at offsets 11..61, initializes both FAT12 copies, and writes IO.SYS/MSDOS.SYS first with system/hidden/read-only attributes and contiguous cluster chains. All remaining files follow. There is no downloaded floppy/template input to packaging.

The app bundles `project86.ima`, its `project86-boot.json` receipt and required guest licenses/source. An Xcode build phase verifies every file, the boot sector and build provenance, then reconstructs the entire disk from the declared inputs to detect unexplained FAT, layout or free-space bytes. `P86BUILD.TXT` explains the build boundary; `P86FILES.TXT` lists every DOS artifact and CuteMouse hash. The source archive's binary libraries remain a documented dependency, so this is not a compiler/library bootstrap from source.

`make mouse` builds CuteMouse 2.1 beta4 using a native ARM JWasm compiled from pinned source. Packaging validates the resulting driver and its matching source/license package; Xcode checks both against the successful build report. The app carries no downloaded driver executables as source-package extras. The four default binary DOS library dependencies are detailed in `SOURCE-COMPLETENESS.md`.

Compiler-stage boot can use a verified packaged DOS floppy with `rebuild_dos.py --seed DIRECTORY --seed-build BUILD`. Verification checks its receipt, every DOS artifact against the retained source-build disk, and a complete reconstruction of the image before creating a private compiler disk. Its CONFIG.SYS sets the build's shell/environment and AUTOEXEC.BAT omits resident app drivers. Fresh source/tools still come from the pinned archive. Seeded builds neither read nor fetch the restoration floppy; their output comparison uses all 63 artifacts of the verified seed build. Schema-3 reports retain the original seed, configured boot image, receipt and parent report with hashes. Cached builds validate those files and all generation comparisons. Older reports remain readable for seed verification and historical evidence. Packaging generates an Xcode input-file list for the optional seed evidence, preserving script sandbox enforcement.

Packaged AUTOEXEC.BAT sets `PROMPT $P$G` so DOS displays the current drive/path.
It redirects normal CuteMouse output to NUL, retains a brief failure warning, and
prints `MS-DOS 4.0 (Project86)` using DOS ECHO. Manual VER retains the compiled
detailed build identifier.
Existing working disks are retained. The menu can import a fresh rebuilt-DOS floppy while reattaching the saved C: disk; the prior floppy path is retained for recovery. Subsequent launches reopen the newly selected working disk. This avoids overwriting guest files during an app update.

The optional source variant uses our small-model C COMSUBS implementation and a guest assembly helper
that queries DOS for DBCS lead ranges. The build removes the supplied archive,
compiles our sources with the original guest tools, and archives the replacement
before linking DOS. Schema-4 reports verify its source ZIP, library bytes and
guest-disk outputs. Migration from the VER-only variant permits precisely five
changed utilities; other outputs must match. The app carries the matching COMSUBS
source archive. See `COMSUBS.md` for API scope and real utility validation.

Its CASSFAR replacement uses large-model C and an ES:DI far-call bridge for SELECT's ten direct
interfaces. Queue, panel, menu, input, help and speaker code executes in the guest;
file operations use the real DOS kernel. A bounded work area supports in-place
help wrapping. Schema 5 verifies both library/source packages and permits only
SELECT.EXE to change from the COMSUBS baseline. Full private installations and
character/attribute comparisons validate the replacement. The preserved experimental build is
`.build/dos-cassfar/`; `CASSFAR.md` records interface and validation limits.

The default is now `.build/dos-command-editor-v2/`, schema 7, with enhanced COMMAND.COM and original
COMSUBS/CASSFAR/SLIBCE/MEM inputs pinned and verified on the guest build disk.
Variant-aware comparisons permit only the affected utilities to change when
switching library implementations; matching implementations must reproduce every
artifact. `DOS_LIBRARIES=source` selects both replacements in a separate build.
The app bundles `dos-project-sources.zip`: build-boundary information, the
COMMAND editor source package and only source ZIPs for library replacements actually linked. Packaging
removes stale individual source ZIPs and verifies the aggregate's exact contents.
The default native build directory is `.build/apple-speed-control/` with Release products, preserving
the earlier apps under `.build/apple-original-libraries/` and `.build/apple/`. See `ORIGINAL-LIBRARIES.md`.

COMMAND's REGCOM input path calls our 8086 assembly editor. Its 16 history records
and DTA interruption cleanup live in resident DATARES; mutable editor state is in
TRANSPACE, outside the transient checksum. Batch and /C skip this path. Redirected
handles, non-console devices, graphics modes and active DBCS tables use DOS 0Ah
input. Text editing uses DOS reads/output and BIOS cursor/scroll calls; completion
uses guest FindFirst/FindNext with a private, restored DTA. See `COMMAND-EDITOR.md`.

## Storage and failure handling

Raw floppy images support common 160 KiB–2.88 MiB geometries. Hard disks use four heads and 32 sectors, must be 64 KiB aligned and no larger than 64 MiB. Boot currently starts from a floppy; a hard disk is the C: data/build drive. DOS reads and writes the FAT filesystem through BIOS sector services. The native Python FAT utility only prepares or inspects files; it never executes guest code.

Sector writes update an in-memory working image. Checkpoints write a sibling temporary file, fsync it and rename it over the working image. Failed checkpoints keep memory dirty and report an error; the UI stops execution and asks the user to keep the window open while resolving the storage problem. Imported originals are separate recovery copies. A process crash can lose writes since the last checkpoint; this is not a transactional storage guarantee across power loss.

## Boundaries

No pre-existing emulator implementation or runtime is a dependency or validation oracle. Validation uses Intel hardware-derived fixtures, original DOS programs, authored guest tests and direct interaction with user-supplied games. References and guest licenses are recorded separately. Metal's normal graphics shader compilation does not translate guest x86 instructions.

## Serial mouse reset and startup input

The COM1 mouse accepts host events only with DTR/RTS asserted and loopback off.
A reset/connection transition emits identification followed by a neutral state
sample before later motion; unchanged zero-motion/button notifications are dropped.
Receive interrupts are not required for packet production. This keeps boot-time
pointer events out of the reset/detection phase while preserving polled access.
The buffering/timing model remains functional rather than cycle accurate. See
[SERIAL-MOUSE.md](SERIAL-MOUSE.md) for the reproduced bug and guest tests.

## Native input and build performance

The native app builds C++ at O2 and Swift with whole-module O optimization by
default; Debug remains selectable through BUILD_CONFIGURATION. Pointer deltas
remain floating point until the worker's MouseInput accumulator emits integer
packets. Same-button movement is coalesced per update; button edges flush earlier
motion and remain ordered. Reset/import/pause clears pending movement; paused
pointer events are ignored. This preserves single-worker ownership of the core.

The UI uses separate observable state for high-frequency frames and control
settings. MachineDisplayState drives only the screen, status and diagnostic leaf
views. The root/control menu observes EmulatorModel, so frame publication cannot
continually invalidate an open SwiftUI submenu. `make ui-state-tests` checks this
notification boundary without opening user disks; it is not a native hover test.

CPU speed is a persistent toolbar control, avoiding nested menu tracking entirely.
CPUSpeedControl wraps an AppKit NSSegmentedControl on macOS and a segmented SwiftUI
Picker on iPad. Both bind to the existing model setter. The native component test
checks target/action mapping for all four multipliers without launching the app
or opening its disks.
