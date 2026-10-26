# Project86

An independent x86 PC interpreter running real MS-DOS 4.00 in a native Apple Silicon app. The C++20 core, BIOS services, video, input, disk and audio devices are written here. No QEMU, DOSBox, other emulator engine, reference runtime, or JIT is used.

The Mac prototype boots DOS, runs its original tools, rebuilds the restored DOS source, and runs the supplied Wolfenstein 3D shareware v1.4 through gameplay and save/load. The shared iPad app builds; physical testing on the owner's M4 iPad Pro is deferred while Mac development continues.

## Run on this Mac

Requires Xcode with macOS/iOS SDKs, XcodeGen, Python 3, and NASM for the assembled guest tests. Native `clang++`, Swift and Make build the project. There are no runtime package dependencies.

```sh
make all test
make guest-tests
make mac
open .build/apple-speed-control/Build/Products/Release/Project86.app
```

`make mac` verifies a completed DOS source build (or runs it inside Project86 when absent), creates a fresh FAT12 floppy with its assembled boot sector and all 62 DOS files, generates the Xcode project, and builds the native app. It downloads checksum-pinned DOS bootstrap artifacts plus CuteMouse and JWasm source as needed. `make mouse` builds the driver with a native ARM assembler built from source. Downloads are cached under `assets/`; originals remain unchanged. The first source build takes longer; later builds reuse verified outputs. `project.yml` is authoritative; generated Xcode projects are ignored.

The app starts with `MS-DOS 4.0 (Project86)` and the `A:\>` prompt. CuteMouse loads quietly; an installation failure produces a brief warning. Click the display to type. `VER` prints `MS-DOS Version 4.00 (Project86 - built from source)` from our compiled COMMAND.COM. Try `DIR` or `ECHO HELLO>HELLO.TXT` too. The sound button enables PC speaker, AdLib and Sound Blaster audio. Pause and quit flush disks; periodic checkpoints run every five seconds. Command-V pastes text into DOS.

The app copies imported disks into its Application Support directory, keeping `original.ima` beside a writable `working.ima`. The last disks reopen on launch. To switch an existing installation, choose **Boot rebuilt MS-DOS (new floppy)** in the menu. This keeps C: attached and retains the previous floppy; **Open previous boot floppy** brings its contents back in a separate working copy. Existing user disks are never patched automatically. `TYPE P86BUILD.TXT` explains the build; `TYPE P86FILES.TXT` lists all DOS output hashes. The menu also provides **Attach hard disk and reboot**, **Reboot computer**, and diagnostics. The initial app uses the supported 286 real-mode subset; protected mode is unavailable.

## Verify and rebuild DOS

```sh
make test
python3 scripts/test_dos.py
make guest-tests
make packaging-tests
make mouse
python3 scripts/hardware_tests.py --output .build/cpu-main.json
python3 scripts/hardware_tests.py --extended --output .build/cpu-extended.json
python3 scripts/rebuild_dos.py --output .build/dos-rebuild-new
```

The app uses `.build/dos-command-editor-v2/` by default, with history/Tab completion in COMMAND.COM and all four original binary libraries. `make mac` writes the native app under `.build/apple-speed-control/` in Release (`APPLE_BUILD` and `BUILD_CONFIGURATION` override these). To build and package a fresh source build, use `make mac DOS_BUILD=.build/dos-rebuild-new` (choose a directory that does not already contain a partial build). Packaging and Xcode reject missing, inconsistent or stale outputs; there is no fallback to downloaded DOS files. `assets/dos-files.json` maps every file to its guest build output. The bundled `project86-boot.json` records hashes for the build report, retained guest disk, output archive, installed boot sector and every file.

The original MASM, LINK, C compiler and NMAKE execute **inside Project86**. We assemble the boot sector and generate 60 DOS files; the two text profiles, GRAPHICS.PRO and SELECT.PRT, are copied unchanged from source. Our initial unmodified build matched all 62 restoration files byte for byte. The current build changes only COMMAND.COM, adding session history, filename completion and the earlier VER message; the other 61 distribution files and boot code match the preserved original-library build. Unexpected differences are rejected. Boot code matches outside the media-specific BPB/EBPB, which we generate for a 1.44 MiB disk. FAT tables, directories and free space are created from scratch. No content is copied from the downloaded floppy during app packaging. It is the initial compiler-stage seed; subsequent builds can boot our verified rebuilt floppy instead.

Before the COMSUBS change, a second-generation build booted that rebuilt floppy with access to the downloaded floppy and network blocked. All 63 artifacts and the output ZIP matched the first generation exactly. See [the historical second-generation report](docs/evidence/dos-second-generation.json). The default retains original COMSUBS, CASSFAR, SLIBCE and MEM libraries while rebuilding the executables that link them. Our tested COMSUBS/CASSFAR implementations remain optional: `make dos DOS_LIBRARIES=source DOS_BUILD=.build/dos-source-new`. Use the same selection for subsequent Make commands on that build. See [the restored default and validation](docs/ORIGINAL-LIBRARIES.md), [COMSUBS](docs/COMSUBS.md) and [CASSFAR](docs/CASSFAR.md).

To repeat using the preserved first-generation seed:

```sh
make dos DOS_BUILD=.build/dos-next-generation \
  DOS_SEED=.build/dos-seed-first-generation DOS_SEED_BUILD=.build/dos-full-build
make packaging-tests DOS_BUILD=.build/dos-next-generation
make mac DOS_BUILD=.build/dos-next-generation
```

For another seed, first package its completed DOS build to a separate directory with `scripts/prepare_guests.py --dos-build BUILD --output SEED` (also pass `--mouse-build` for a nondefault driver build). `DOS_SEED` names that directory, including the image, receipt and corresponding sources/license; `DOS_SEED_BUILD` names its DOS build. Direct script flags are `--seed SEED --seed-build BUILD`; add `--fetch` for missing pinned source/tools and license. Seeded compilation never fetches or reads the downloaded floppy and invalid seeds never fall back. Only private CONFIG.SYS/AUTOEXEC.BAT copies change for compiler startup. Schema-7 reports retain the COMMAND editor source and patch provenance, plus selected library/seed evidence. Moving from the original-library VER baseline permits only COMMAND.COM to change. Matching shell/library variants require every artifact to match. `DOS_SHELL=original` selects the preserved VER-only shell; `DOS_LIBRARIES=source` independently selects our two optional library replacements. Initial builds without a seed still use the restoration floppy. Older reports remain readable as seeds/evidence; caches must match both selections.

Build repairs include the backup drive change from `D:` to `C:` and assembly wrappers for the published printer data, whose original makefiles do not rebuild their CPI files. Original product switches are preserved. The default build uses original tools, COMSUBS.LIB, CASSFAR.LIB, SLIBCE.LIB and MEM.LIB; every installed DOS program is a build output, but not every linked library is rebuilt from source. Their hashes and this boundary are recorded. CuteMouse 2.1 beta4 is also assembled from source; the app includes its corresponding sources and build recipe. The [source completeness audit](docs/SOURCE-COMPLETENESS.md) identifies the remaining binary-only code.

Including every distribution file does not imply every driver can run: EMM386 and other protected-mode/extended-memory paths remain unsupported. See [validation](docs/VALIDATION.md), [architecture](docs/ARCHITECTURE.md), and [guest provenance](THIRD_PARTY.md).

The CASSFAR replacement was tested against all 57 help topics, key-search cases,
17 complete character/attribute screens, and real SELECT installations on private
disks. Run `python3 scripts/test_cassfar.py --output .build/cassfar-check-new` to
test the selected build against the preserved original-library baseline. Pass
`--dos-build .build/dos-cassfar --baseline .build/dos-comsubs` to repeat the
replacement milestone comparison. Launch the
installer with `SELECT.EXE MENU`; tests use minimum DOS without the optional DOS
Shell installation media. They never install onto the app's managed working disks.

The bundled prompt shows the current drive and directory, for example `C:\WOLF>`.
For an existing session, enter `PROMPT $P$G` to enable it immediately.

At the DOS prompt, Up/Down recalls up to 16 commands and restores your unfinished
line. Tab completes filenames/directories; repeat it to cycle matches. Completed
directories have no trailing separator so `CD` works; type `\` explicitly to
continue a nested path. History
survives external programs but is not saved across shell restarts. The 127-character
DOS limit remains. See [COMMAND editor behavior and validation](docs/COMMAND-EDITOR.md).
Run `python3 scripts/test_command.py --output .build/command-check-new` for real
guest editing, completion, transient reload, batch, pipe and redirection checks.

The Mac app now uses an optimized Release build, 8× CPU throughput and 60 Hz
updates. The bottom toolbar has direct **CPU** buttons for 1× (compatibility), 4×,
8× (default) and 16×; device/audio time remains unchanged. Small mouse movements are retained
and motion events are combined without dropping button transitions. Controlled
Wolfenstein render-rate measurements increased from about 8–10 to 65–70 per guest
second; these are not native-window FPS measurements. See
[performance results and validation](docs/PERFORMANCE.md). Use
`make mac BUILD_CONFIGURATION=Debug` when an unoptimized debugging build is needed.

## iPad later

```sh
make ios
```

This builds for the iOS simulator. For the M4 iPad Pro, open the generated project, choose the Project86iPad scheme, select your development team and physical device, and build/install with Xcode. No JIT entitlement, jailbreak or remote computer is required by the runtime design. Physical signing/install, external input, lifecycle reliability and gameplay performance remain unverified. The current iPad UI has a keyboard button, touch trackpad, tap for left click and two-finger tap for right click.

## License

Project86's own source code is available under the [MIT License](LICENSE).
Third-party guest software, tools, datasets and game content retain their own
licenses and notices; see [THIRD_PARTY.md](THIRD_PARTY.md). Game files are supplied
separately by the user.
