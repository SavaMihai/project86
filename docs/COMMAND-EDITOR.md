# COMMAND.COM history and filename completion

COMMAND.COM now provides a 16-entry interactive history and Tab completion for
DOS filenames and directories. These are guest assembly routines compiled into
COMMAND.COM with the original MASM/LINK tools. The four original binary libraries
remain selected; no emulator, BIOS or DOS kernel behavior was changed.

## Using the prompt

The bundled startup uses `PROMPT $P$G`, so the prompt includes the drive and current
directory, such as `C:\WOLF>`. Run that command in an existing session to apply it
immediately. It uses DOS's built-in prompt support. The configuration change and
longer-prompt editing were [checked in the guest](evidence/path-prompt-tests.json).

| Key | Behavior |
|---|---|
| Up / Down | Browse history; Down past the newest entry restores the unfinished line and its cursor |
| Tab | Complete the filename at the cursor; repeated Tab cycles matches and wraps to the first |
| Left / Right, Home / End | Move the cursor; Right at the end can recall the next template character |
| Backspace / Delete | Remove the previous/current character |
| Insert | Toggle insertion and overwrite; insertion is the default |
| Escape / Ctrl-X | Clear the line and reset history navigation |
| Ctrl-C | Cancel without recording or executing the pending command |
| F1 / F3 | Copy one character / the rest of the previous-command template |
| F2 / F4 | Copy template text up to a requested character / delete current text up to a requested character |
| F5 / F6 | Save the current line as the editing template and start a new line / insert Ctrl-Z |

For example, `TYPE C:\AL` followed by Tab selects `TYPE C:\ALPHA.TXT`; another
Tab selects the next matching name. Directory completion inserts only the name:
DOS 4 rejects a trailing `\` in commands such as `CD SUBDIR\`. To continue a
nested path, type `\` explicitly after the completed directory name. Completion
supports current-directory, drive-relative and explicit paths, extensions,
redirection targets and a token before later arguments. It replaces the token's
untyped remainder and retains subsequent arguments.

History is private to each shell session and is not written to disk. Blank lines,
consecutive duplicates, AUTOEXEC and other batch-file lines are excluded. Editing
a recalled command does not mutate its stored entry. External programs may
overwrite COMMAND's transient code; the resident history survives its reload.

The existing 127-character input limit remains. Completion does not search PATH or
built-in command names, provide long filenames, or expand wildcard/quoted tokens.
It uses ordinary DOS 8.3 directory searches, excluding hidden/system entries and
the `.`/`..` entries. No-match and overlong expansions leave the line intact.

## Implementation and compatibility

`scripts/command_source.py` patches the pinned original TCODE, RDATA, TSPC and
makefile in the private build inputs. It includes `guest-build/command/editor.asm`,
`history.inc` and `work.inc`; the original source archive remains unchanged.
Interactive REGCOM calls the editor, while batch processing and `COMMAND /C`
keep their existing paths. Redirected input/output, non-console handles, graphics
modes and active DBCS lead-byte tables use DOS's original buffered-input routine.
The new editor's character movement is single-byte; localized DBCS editing is
not claimed as a new feature.

Keyboard reads and character output use real DOS services. BIOS calls position
the cursor and scroll text rows; wrapped redraw includes caret display of Ctrl-Z.
FindFirst/FindNext use a private DTA, restored before every subsequent key read.
A resident cleanup record also restores it after a DOS Ctrl-C non-local return.
Resident data grows by 2,055 bytes before paragraph alignment. Mutable editor
scratch space lives outside the transient checksum region.

Schema-7 build records retain corresponding source, patch-recipe and patched-file
hashes. Verification checks them against the retained guest build disk and checks
the compiled editor marker. The app includes `command-source.zip` inside the
verified `dos-project-sources.zip`, alongside any explicitly selected library
replacement sources. Historical build reports and source packages remain readable.

The default is `DOS_SHELL=enhanced`; `DOS_SHELL=original` retains the earlier
VER-only shell. `DOS_LIBRARIES=original` remains the default independently.
Choose a separate `DOS_BUILD` when changing either selection; cache verification
rejects a different selection or stale editor source.

```sh
make mac
python3 scripts/test_command.py --output .build/command-check-new
```

The test script's `--command` option is only for development before a full build;
release evidence uses the validated default build without an override. All write
tests use private images. Source and build success do not establish native-window
interaction, physical-device behavior or complete localized DOS compatibility.

## Directory completion correction (v2), 2026-10-26

A user report exposed a v1 bug: Tab produced `CD SUBDIR\`, and DOS 4 returned
`Invalid directory` while leaving the current directory unchanged. Typing
`CD SUBDIR` succeeded. The original tests checked the completed text and nested
file access, but did not execute a completed directory with CD.

V2 removes the automatic trailing separator for every completed directory. The
user types `\` explicitly to continue a nested path. Seven new guest regression
checks execute CD after cycling, mixed-case CHDIR with an absolute path, nested
relative paths, dotted directory names, DIR and RD, and verify that explicit root
paths still work. They check DOS's actual current directory and filesystem results.
All existing 19 editing/history groups, nine completion groups and eight shell
output comparisons also pass. All 37 packaging/provenance tests pass (two
inapplicable replacement classes skipped), including rejection of a v1 binary
mislabelled as v2. The native Mac build and full bundled-resource verification
also pass.

The default build is `.build/dos-command-editor-v2/`, variant
`project86-command-editor-v2`, schema 7. It boots the preserved v1 seed and changes
only COMMAND.COM; the other 62 artifacts match v1. Original libraries and the DOS
kernel remain unchanged. V1 reports/images remain readable with revision-specific
marker verification. The v1 subsequent-build result below remains historical;
it is not a repeated v2 second-generation build.

COMMAND.COM: 41,940 bytes, SHA-256
`2f4aa05f10a69c728567389cdbc941296e1bfd5b0096b164735e122e8215c034`.
Original v2 packaged floppy SHA-256 (before the path-prompt configuration):
`e0658eb774fc13c08087a2284377343b9240b69ba4ec898ee29464c985140ef3`.

Evidence: [original failure](evidence/command-directory-reproduction.json),
[build](evidence/dos-command-directory-build.json),
[guest regressions](evidence/command-directory-tests.json),
[floppy receipt](evidence/dos-command-directory-boot.json) and
[validation](evidence/command-directory-validation.json).

The updated app is
`.build/apple-command-editor-v2/Build/Products/Debug/Project86.app`.
Quit the older app before opening it, then choose **Boot rebuilt MS-DOS (new floppy)**
to adopt its bundle. Managed user disks were not modified or switched by this fix.

## Initial v1 validation (historical)

The initial build was `.build/dos-command-editor-v1/`. Its tests missed execution
of a completed directory with CD; the v2 correction above addresses that gap. Only COMMAND.COM differs
from the original-library baseline; the other 61 distribution files and BOOT.BIN
match exactly. COMMAND.COM grows from 37,588 to 41,958 bytes. Its linker response
is unchanged and it still links no external library. The four original library
hashes remain pinned and verified on the build disk.

- Nineteen editing/history groups cover recall/draft restoration, navigation
  limits, duplicate/blank suppression, Escape, editing, F1–F6, Ctrl-C, a 16-entry
  ring, long wrapped/scrolled lines, batch exclusion and nested-shell isolation.
  A source-assembled COM deliberately overwrites the transient portion, proving
  that resident history survives its reload.
- Nine completion groups cover case-insensitive cycling/wrap, nested directories,
  drive-relative and explicit paths, extensions, redirection targets, later
  arguments, token replacement, no-match/quoted/wildcard cases, overflow and
  Ctrl-C with BREAK ON. Subsequent directory output verifies normal DOS searches.
- Eight output files match the original shell exactly after batch/FOR/IF, /C,
  pipes, input/output redirection, VER and DIR tests.
- All 36 packaging/provenance cases pass; two replacement-only classes are
  skipped. The preserved library-source variant also passes its 32 cases with
  two inapplicable classes skipped. Original source/binary snapshots remain valid.
- The assembled CPU program and real CuteMouse guest integration pass. The native
  Mac build and complete bundled-resource verification pass.
- A second full DOS build boots the enhanced floppy and reproduces all 63 outputs
  and the output ZIP exactly. This tests the modified shell as the compiler's
  runtime, not just as an interactive prompt.

A private timing diagnostic measured approximately 3.2, 13.2 and 26.3 ms of the
emulator's functional virtual clock for appending after 10, 60 and 125 characters.
These are not physical-hardware or native-window latency measurements.

COMMAND.COM SHA-256:
`30bc3019ec3c7116288bbdb75f1da2d42c956400dead855ee1f36b08dafc8114`.
Packaged-floppy SHA-256:
`f9394d23f044bdaf4614983c5616c103bd82761217771e7f531bcd4dae7a3346`.

Evidence: [full build](evidence/dos-command-editor-build.json),
[guest tests](evidence/command-editor-tests.json),
[packaged image](evidence/dos-command-editor-boot.json),
[assembled guests](evidence/command-editor-assembled-guests.json),
[subsequent build](evidence/dos-command-editor-second-generation.json) and
[validation summary](evidence/command-editor-validation.json).

The historical v1 app remains at `.build/apple-command-editor/Build/Products/Debug/Project86.app`.
Older apps and DOS builds are preserved. No managed user disk was switched or
modified, and the app was not relaunched. Use **Boot rebuilt MS-DOS (new floppy)**
in the new app to adopt the bundle; C: and the previous floppy remain recoverable.
