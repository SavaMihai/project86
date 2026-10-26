# Milestones and remaining acceptance

Updated 2026-10-26. Mac development has priority; physical M4 iPad Pro testing is explicitly deferred by the owner.

| Milestone | Current evidence | Remaining work |
|---|---|---|
| 1. CPU foundation | C++20 interpreter, NASM guest programs, core regressions, 386,000 physical-8086 fixtures passed | Broaden opcode/interrupt/string fixture coverage; improve CPU timing and 286 edge cases |
| 2. Native proof | SwiftUI/Metal Mac app and iPad simulator builds; shared core; native renderer/pipeline validated | Physical M4 iPad Pro installation and input proof; native UI automation unavailable in this session |
| 3. Real DOS boot | DOS 4.00 boots; VER, DIR, COM/EXE execution, file creation/copy and FAT12/FAT16 persistence tested | Broader BIOS/device/error-path compatibility and long-running storage tests |
| 4. DOS rebuild | Source correspondence and identical second-generation builds established. Original COMSUBS/CASSFAR/SLIBCE/MEM remain default. COMMAND adds session history and Tab completion; v2 verifies completed directory execution after removing the invalid trailing separator; other DOS artifacts are unchanged. Our replacements and their validation remain available as an optional variant | Library/toolchain replacements deferred by owner; maintain reproducible builds and native acceptance; independently repeat on iPad later |
| 5. Games | VGA planar/unchained output, source-built CuteMouse 2.1 beta4, speaker/FM/PCM, supplied Wolfenstein v1.4 gameplay and save/reload captures | Optimized Release/8x CPU/60 Hz update improvements and input coalescing are measured headlessly; native-window acceptance, audio listening/fidelity and longer sessions remain; user files for Prince of Persia and Monkey Island |
| 6. iPad usability | Shared UI, basic touch trackpad/keyboard, audio, pause/checkpoint plumbing | Physical keyboard/mouse, complete touch controls, app background/foreground and storage stress tests, measured gameplay performance |

Not implemented: 386 protected mode, Doom compatibility, networking, save-state snapshots, App Store distribution. DOS disk persistence is implemented; save-state snapshots remain separate and deferred.

Do not promote build success, a screenshot, nonzero audio samples or hardware fixture counts into claims of complete machine or game compatibility. Physical-device validation remains its own acceptance gate.
