# Serial mouse startup and input

Project86 presents a two-button Microsoft-compatible mouse on COM1 (03F8h/IRQ4).
The source-built CuteMouse driver detects it and handles INT 33h entirely in DOS.
Host pointer input becomes serial packets; the host does not implement the mouse
driver's DOS interface or fabricate its detection result.

## Startup correction, 2026-10-26

A native-window report showed `CuteMouse v2.1 beta4` followed by `Error: device
not found` after choosing Boot rebuilt MS-DOS. The same packaged image installed
the driver successfully in quiet headless tests. Injecting movement or repeated
zero-motion button notifications at the native worker's 20 ms cadence reproduced
the failure. Earlier tests sent mouse input only after installation.

The mouse API was queuing packets even while the guest had DTR/RTS deasserted.
CuteMouse lowers those lines, flushes the receive register, waits for two timer
ticks, raises them and examines the identification bytes. Host packets accumulated
during reset could therefore appear ahead of `M`. Under input stress, movement
bytes could also resemble optional Logitech/wheel identification characters.

The core now:

- Accepts mouse events only with DTR and RTS asserted and UART loopback disabled.
  It does not require receive interrupts to be enabled, so polling remains valid.
- Emits a contiguous `M` identification followed by a neutral Microsoft state
  packet (`40h 00h 00h`) on the connection/reset transition. Subsequent events
  follow this initial sample rather than becoming part of the identification.
- Ignores zero-motion notifications when the button state has not changed.
  Actual movement and button transitions still emit normal packets.

The initial neutral sample is a functional device-model choice, not a claim of
cycle-accurate startup timing for every physical mouse. UART buffering/baud timing
remain approximate. No driver-specific installation flag, delay until INT 33h,
guest output injection or DOS call interception is used.

The DTR/RTS identification sequence is described in Microsoft's
[Hardware Design Guide for Windows 95, chapter 7, page 219](https://www.bitsavers.org/pdf/microsoft/windows_95/Hardware_Design_Guide_for_Windows_95_1994.pdf).
The pinned CuteMouse source under
`.build/cutemouse-build/sources/source/ctmouse/ctmouse.asm`, procedures
`detectmouse` and `enableUART`, records the actual probing and setup sequence
used in this distribution. No external emulator runtime or implementation was used.

## Verification

`scripts/test_mouse_startup.py` uses private writable images and the current
native worker's 60 Hz cadence, distributing device cycles with integer carry.
`--frame-hz 50` retains the earlier cadence; `--cpu-speed 8` selects the app's
current CPU throughput. It reuses one core across fresh floppy attachments
and reboots, preserving a private hard-disk marker. Six input profiles run in both
paths: quiet, repeated idle notifications, small motion, large motion, right-button
dragging and button changes. All 12 cases must install in Microsoft mode without
a phantom wheel, then produce correct motion and button results through the real
driver. A fresh guest-generated MOUSE.DAT is required after every run; stale
reports cannot satisfy the test. The shipped startup is now quiet. For detection
assertions, the test redirects the same driver invocation to a private C:\MOUSE.LOG
instead of NUL and verifies both the clean visible screen and the guest-written
diagnostic log. The unmodified production NUL path is also exercised by the
assembled mouse integration test.

Core/device regressions cover powered-down input, partial control-line assertion,
the identification/state sequence, unchanged button reports, interrupt-disabled
polling, loopback isolation and duplicate control-register writes. CPU instruction
semantics did not change, so the physical-8086 fixture suite was not rerun.

```sh
make all test
python3 scripts/test_mouse_startup.py --output .build/mouse-startup-check-new
make packaging-tests
make mac
```

Evidence: [failure reproduction](evidence/mouse-startup-reproduction.json),
[guest boot/reboot checks](evidence/mouse-startup-tests.json) and
[validation](evidence/mouse-startup-validation.json).

The packaged floppy, all DOS artifacts and CTMOUSE.EXE are unchanged by this fix.
It applies when an existing DOS disk boots in the rebuilt emulator. The prior Mac
app is preserved at `.build/Project86-before-mouse-startup.app`; managed user disks
were not changed or switched. Native-window acceptance after the fix and physical
hardware remain distinct from these core/guest tests and the Mac build.
