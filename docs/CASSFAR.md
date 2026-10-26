# CASSFAR source replacement and SELECT validation

Status changed 2026-10-26: the default now uses all four original libraries.
This document records the preserved optional source replacement and its historical
validation. Use `DOS_LIBRARIES=source` with a separate build directory to rebuild
both replacements. See [the original-library default](ORIGINAL-LIBRARIES.md).


Completed 2026-10-26. The experimental SELECT links our own CASSFAR implementation from
`guest-build/cassfar/cassfar.c` and `bridge.asm`. The original CASSFAR.LIB is
removed before creating the guest build disk. The period C compiler, MASM, LIB
and LINK execute inside Project86 to produce the replacement and SELECT.EXE.
No executable bytes or guest results are patched by the host.

## Implemented interface

The original link loaded 24 archive members. SELECT directly calls ten public
entry points; the other members were internal dependencies. Our two objects
replace those ten interfaces and implement their supporting operations directly:

| Entry point | Responsibility |
|---|---|
| DISPQ | Parent/child panel queues, saved queues, overrides and return keys |
| GVIDO | BIOS-declared display capabilities and text-screen geometry |
| INSTRN | String/key-list searches |
| MBEEP | Guest PIT/PC-speaker tone |
| SLCTP | Menus, inactive-row skipping, wraparound, paging and scroll indicators |
| PANEL | Panel/child composition, colors, logical video buffer and refresh breaks |
| HLPRD | Help-file lookup and DOS file/error handling |
| INPUT | Editable fields, allowed characters, delimiters and horizontal windows |
| INCHA | Guest keyboard input and ASCII case conversion |
| WWRAP | In-place wrapping of SELECT's help text and formatting markers |

SELECT's published ES:DI far-call interface is preserved by assembly adapters.
Large-model C handles far data and SELECT's separate stack/data segments. The
compiler uses `-AL -Gs -Zl -Os -Zp`; our routines require no CRT startup or heap
allocation. An 8 KiB work area permits in-place help wrapping even when a DOS
caller owns the remaining memory. Oversized input is rejected through the help
buffer error field. This covers SELECT's 80×25 text interfaces and shipped data;
it is not a replacement for every historical CASSFAR API, graphics mode or caller.

`scripts/cassfar_layout.py` derives offsets and flags from the pinned released
DATA.MAC, CASTRUC.INC and PCEQUATE.INC declarations. The source package contains the
resulting LAYOUT.H, our C/assembly and the librarian response file. The report pins
their hashes, the source archive and layout-generator hash. The original header,
callers and data formats, guest comparisons, and limited original-object
inspection informed implementation; this is not a formal clean-room claim.

## Validation

- The full build changes **only SELECT.EXE** from the COMSUBS baseline; the other
  61 distribution files and BOOT.BIN match exactly.
- All 61 linker invocations were replayed on a private disk. SELECT loads only
  `cbridge.asm` and `cassfar.c` from our CASSFAR archive. The original 24 members
  are gone from the link. SELECT.DAT still loads no CASSFAR members.
- 345 key-search cases match both the original library and an independent
  expected-result model.
- All 57 help topics have identical returned text, wrapping, line counts and
  error results against the original library. Both probes execute in Project86.
- 13 navigation snapshots, three parameter-review snapshots and the missing-help
  error dialog match all **4,000 character/attribute bytes per screen**. This
  covers inactive menu rows, wraparound, help/F9, paging, restoration, cancellation
  and editable-field display.
- Both original and rebuilt SELECT complete an actual minimum-DOS installation
  to a private FAT16 target. Tests type `C:\P86TEST`, reject `*` in that field,
  swap private INSTALL/SELECT COPY disks as requested, and let real DOS programs
  perform the copies. Of 69 installed/test files, 68 are identical. The sole
  expected difference is the installed SELECT.EXE, checked against each build.
  CONFIG.SYS and AUTOEXEC.BAT match exactly, an unrelated marker survives, and the
  installed COMMAND.COM executes successfully after a machine restart.
- All 32 packaging/provenance tests, core/device regressions, the COMSUBS guest
  regression suite, Mac build and bundled-image verification pass.

GVIDO intentionally differs in four metadata byte positions: it reports the
BIOS-declared VGA/EGA-compatible adapter rather than phantom extra adapters from
speculative port probes, and supplies character width, cursor width and the
current attribute where the original returned zero. Geometry, mode and video
buffer addresses agree. The probe validates these intentional values separately.

Evidence: [build](evidence/dos-cassfar-build.json),
[linker audit](evidence/dos-cassfar-library-audit.json),
[guest comparisons and installations](evidence/cassfar-tests.json),
[packaging/core/native validation](evidence/cassfar-validation.json),
[boot receipt](evidence/dos-cassfar-boot.json).

These are headless guest and build checks. Native-window interaction, physical-PC
or iPad operation, hard-disk BIOS boot, all printer/localization configurations,
and sound fidelity are not certified. Installation was tested without the
optional DOS Shell, whose installation media is not part of this package.

## BIOS compatibility uncovered by the baseline

The original SELECT and KEYB stopped at three previously unsupported probes.
Project86 now handles their defined capability checks:

- INT 10h/AH=15h leaves the caller's null display-table pointer unchanged on our
  VGA machine, which has no IBM Convertible display table.
- INT 10h/AH=FEh leaves the physical video-buffer pointer unchanged when no
  TopView shadow-buffer manager is installed.
- INT 16h/AH=92h returns AH=80h, identifying the already implemented enhanced
  keyboard services 10h–12h.

References: [Convertible display query](https://www.delorie.com/djgpp/doc/rbinter/id/20/2.html),
[TopView query index](https://www.delorie.com/djgpp/doc/rbinter/ix/10/FE.html), and
the [HP 95LX Developer's Guide](https://literature.hpcalc.org/community/hp95lx-dev-guide.pdf),
whose keyboard compatibility section documents KEYB's AH=92h probe and AH-minus-12h
response. These paths have a guest-instruction device regression. Other unknown
services still stop with diagnostics; no DOS service is replaced in host code.
CPU instruction semantics did not change, so the hardware-fixture suite was not
rerun. The full compiler run retains 11 unsupported I/O accesses, last port 06F7h.

## Reproduce and recover

```sh
make dos DOS_SHELL=original DOS_LIBRARIES=source DOS_BUILD=.build/dos-cassfar
python3 scripts/test_comsubs.py --dos-build .build/dos-cassfar --output .build/comsubs-check-new
python3 scripts/test_cassfar.py --dos-build .build/dos-cassfar --baseline .build/dos-comsubs --output .build/cassfar-check-new
python3 scripts/audit_dos_libraries.py --dos-build .build/dos-cassfar --output .build/source-library-audit-new
make packaging-tests DOS_SHELL=original DOS_LIBRARIES=source DOS_BUILD=.build/dos-cassfar
make mac DOS_SHELL=original DOS_LIBRARIES=source DOS_BUILD=.build/dos-cassfar APPLE_BUILD=.build/apple-source-check
```

The original-library build is the default. These explicit commands select the
preserved experimental variant, `project86-cassfar-v1`, schema 5. Both replacements
are compiled together; the earlier COMSUBS-only milestone remains readable as a
baseline. Test/audit output directories must be new. For a fresh source build:

```sh
make dos DOS_SHELL=original DOS_LIBRARIES=source DOS_BUILD=.build/dos-source-new \
  DOS_SEED=.build/dos-seed-original-libraries DOS_SEED_BUILD=.build/dos-original-libraries
```

The builder preserves the original source archives and prior builds. It retains
both rebuilt libraries and corresponding source ZIPs beside the guest disk. The
experimental app bundles both source packages inside `dos-project-sources.zip`
and checks them in Xcode's script sandbox. Cache verification requires the
explicitly selected library variant.

Final guest evidence is under `.build/cassfar-validation-final/`; linker logs are
under `.build/dos-cassfar-library-audit/`. `.build/cassfar-dev/` and
`.build/dos-cassfar-initial/` retain development diagnostics and are not the
delivered build. No managed user disk was changed, switched or force-closed.
SLIBCE.LIB, MEM.LIB and the original compiler tools remain binary dependencies.
