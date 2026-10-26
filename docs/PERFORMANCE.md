# Mac gameplay performance

Measured and updated 2026-10-26 on an Apple M5 Mac. The user reported slow
Wolfenstein movement, turning and interaction in the native window.

## Findings and changes

The native app was built in Debug with C++ optimization disabled and Swift
`-Onone`. More importantly, the guest executed roughly one million instructions
per device second: its fixed instruction costs consumed the entire 4,772,728 Hz
functional clock budget. Wolf rendered only about 8–10 frames per guest second,
even though the host had substantial unused execution time.

- `make mac` and `make ios` now default to Release, with C++ `-O2` and Swift `-O`
  whole-module compilation. `BUILD_CONFIGURATION=Debug` remains available.
- The app defaults to 8× CPU throughput. `p86_set_cpu_speed` scales instruction
  non-I/O costs with an integer remainder; it does not multiply device time.
  Boosted modes retain a conservative eight-device-cycle port-transfer wait;
  Compatibility 1× preserves the original timing. PIT, audio,
  DMA and VGA timing continue using the original functional clock. The plain C
  API/CLI default remains 1×, preserving fixtures and build-tool behavior.
- The bottom toolbar offers direct CPU buttons for 1× (compatibility), 4×,
  8× (default), and 16×. Selection is
  saved and survives reboot. These are interpreter throughput multipliers, not
  claims of cycle-accurate historical MHz. Older CPU-speed-sensitive software can
  use Compatibility mode.
- Native execution/display updates move from 50 to 60 Hz. Integer carry keeps
  the requested device-cycle budget consistent; audio chunks are 800 samples at
  48 kHz. Instruction-boundary rounding and device timing remain approximate.
- Native pointer input retains fractional movement instead of truncating each
  event to an integer. Motion is combined per update; button transitions retain
  their order. Pausing discards pending motion and releases mouse buttons.

The C++ interpreter, original BIOS/devices and guest software remain in use.
There is no JIT, guest-code translation or external emulator component.

## Controlled Wolfenstein measurements

Fresh private images use the same user-supplied shareware v1.4 files. Each run
enters the same game at 1× before selecting its benchmark speed. Five six-second
phases sample VGA display-page changes approximately every millisecond. These are
a proxy for guest renders, **not native-window FPS or end-to-end input latency**.
The native display now updates at 60 Hz.

| Workload | Previous 1× | 4× | New 8×, host sound enabled |
|---|---:|---:|---:|
| Idle scene | 8.2 | 33.2 | 65.5 |
| Arrow turning | 8.5 | 34.5 | 68.5 |
| Walking | 9.8 | 38.0 | 69.8 |
| Mouse turning | 10.2 | 42.5 | 70.2 |
| Fire/use input | 10.2 | 41.8 | 70.0 |

Values are observed page switches per guest second. At 8× with host audio enabled,
core execution plus framebuffer conversion took roughly 3.1–3.6 ms median per
20 ms benchmark interval; phase p95 values were 3.4–4.0 ms. These host timings
exclude SwiftUI/Metal and Python observer overhead and vary with system load.
The original 1× core workload took about 2.6 ms with `-O0`, versus 0.54–0.55 ms
with `-O2`; optimization alone did not lift its guest render-rate limit.

The new 1× compatibility run exactly matches the old optimized core's guest
instruction counts, page-switch counts and final framebuffer hashes in all five
phases. Existing DOS, driver and disk-image bytes are unchanged.

## Verification and limits

- Core/device checks verify 1×/4×/8×/16× execution against a fixed device second,
  18 BIOS timer ticks and 48,000 audio samples. DMA sample advancement is checked
  at 1×/8×/16× with host sound muted. CPU arithmetic/instruction semantics did not
  change; the physical-8086 fixture suite was not rerun.
- Native Swift input tests cover accumulated fractional deltas, coalesced motion,
  button-edge ordering, reset and bounds. They do not replace native event testing.
- All command-editor checks pass at 8×. Twelve real CuteMouse boot/reboot cases
  pass at 8× with the new 60 Hz cadence and verify fresh INT 33h results.
- A separate cold-boot gameplay run at 8× enters Episode 1, walks, fires, produces
  audio, saves, destroys/restarts the machine, reloads and turns with keyboard and
  mouse. Numeric HUD fields and the saved world view must match after the loading
  fade, before further input. Captures were visually reviewed. This is a short
  compatibility check, not a full playthrough or audio-fidelity certification.
- All 37 packaging cases pass (two inapplicable library-replacement classes
  skipped). The Release Mac and iPad simulator builds and bundled-resource verification pass.

The game automation was adjusted for the faster startup: an old extra Space
press entered Help, and a long fixed post-load wait allowed enemies to kill the
restored player. Readiness checks now wait for the saved world/HUD and palette
before testing movement. Earlier failed diagnostic runs remain under `.build/`.

Native-window responsiveness still requires the owner's hands-on acceptance.
Physical iPad performance remains deferred. No managed user disks were changed,
and the app was not relaunched automatically. Save the current game and quit the
older build before opening the new app; it reopens the same working disks.

## Reproduce and evidence

For publication, the `library` field in the compatibility, 4x and 8x-with-sound
JSON reports uses a repository-relative path instead of the original workstation
prefix. Measurements, hashes and other report fields are unchanged. This path
normalization is not a new benchmark run.

```sh
make all test input-tests
make mac
open .build/apple-speed-control/Build/Products/Release/Project86.app
python3 scripts/benchmark_wolf.py /path/to/user/wolf3dsw --speed 8 --audio --output .build/wolf-benchmark-new
python3 scripts/test_wolf.py /path/to/user/wolf3dsw --cpu-speed 8 --output .build/wolf-play-check-new
python3 scripts/test_command.py --cpu-speed 8 --output .build/command-fast-check-new
python3 scripts/test_mouse_startup.py --cpu-speed 8 --output .build/mouse-fast-check-new
```

Use a fresh output directory for each test. The benchmark's `--library` option
selects an explicitly built core for comparisons; it never uses another emulator.
The pre-change source, core libraries and native app are preserved in
`.build/performance-before/` and `.build/Project86-before-performance.app`.

Evidence: [summary](evidence/performance-validation.json),
[old unoptimized core](evidence/performance-baseline-debug.json),
[old optimized core](evidence/performance-baseline-optimized.json),
[compatibility](evidence/performance-compatibility.json),
[4×](evidence/performance-speed4.json),
[8× with sound](evidence/performance-speed8-audio.json),
[gameplay/save/load](evidence/wolf-performance-gameplay.json),
[command tests](evidence/performance-command-tests.json) and
[mouse tests](evidence/performance-mouse-tests.json).

A final cold-boot check caught a timing-sensitive audio probe: scaling port I/O
with the CPU could finish the timer polling loop too early. The fixed boosted-mode
I/O wait is generic across ports and is covered by a guest-instruction regression.
A diagnostic trace of the supplied game now sees AdLib status C0 and Sound Blaster
reset reply AA at both 1× and 8×; its Sound menu enables both devices at 8×.
The published [Wolf sound-manager source](https://github.com/id-Software/wolf3d/blob/master/WOLFSRC/ID_SD.C)
describes the timed probe and Sound Blaster detection dependency. It was inspected,
not imported. Port/bus timing remains a functional model, not a physical timing
certification. Pre-bus-fix benchmark and gameplay directories remain diagnostic
artifacts; the evidence links above point to the final corrected runs.

## CPU menu follow-up

The owner reported the CPU-speed submenu closing on hover. Frame publication has
been separated from control-model observation so 60 Hz screen updates do not
invalidate the menu. The isolated observation regression and both platform builds
pass; actual native hover confirmation remains pending. The updated app is under
`.build/apple-menu-fix/`. [Evidence](evidence/cpu-menu-validation.json).

The owner confirmed that observation isolation alone did not fix the submenu.
CPU speed is now a persistent segmented control in the bottom toolbar, with no
nested menu/hover path. The macOS AppKit component's four actions are checked in
an isolated test; both platform builds pass. The current app is under
`.build/apple-speed-control/`. [Direct-control evidence](evidence/cpu-speed-control-validation.json).
