# Project86 COMSUBS replacement

Status changed 2026-10-26: the default now uses all four original libraries.
This document records the preserved optional source replacement and its historical
validation. Use `DOS_LIBRARIES=source` with a separate build directory to rebuild
both replacements. See [the original-library default](ORIGINAL-LIBRARIES.md).


Completed 2026-10-25. The experimental distribution uses our own source in
`guest-build/comsubs/comsubs.c` and `dbcstab.asm`. The original COMSUBS.LIB is
removed before creating the guest build disk. Microsoft C 5.10 and MASM compile
the replacement inside Project86; the original LIB tool archives its two objects
before NMAKE builds DOS. No executable bytes are patched.

This supplies the five public routines actually linked into this DOS build. It
does not implement every unused interface in the historical COMSUB.H header.

| Routine | Compatibility behavior |
|---|---|
| `com_substr` | Finds a substring at character boundaries; an empty pattern returns the source terminator, matching the original |
| `com_strchr` | Finds the first single-byte character; skips both bytes of a DBCS pair; searching for NUL returns the terminator |
| `com_strrchr` | Finds the last matching byte at a character boundary, including a DBCS lead byte; never matches its trail byte |
| `com_toupper` | Maps ASCII `a`–`z` to uppercase; other byte values are unchanged, matching the supplied DosCaseMap |
| `rctomid` | Returns the input 16-bit code unchanged; all 65,536 inputs were checked |

The assembly helper obtains active lead-byte ranges through real guest DOS
INT 21h/6300h. The replacement has no heap allocation or explicit C runtime
calls. The period C compiler still emits runtime stack-check calls; SLIBCE and
the compiler toolchain remain documented dependencies.

## Evidence and scope

- [Full build](evidence/dos-comsubs-build.json): only JOIN.EXE, SUBST.EXE,
  BACKUP.COM, RESTORE.COM and REPLACE.EXE differ from the preserved
  `project86-ver-v1` baseline. The other 57 distribution files and BOOT.BIN match
  exactly. Against the restoration originals, COMMAND.COM also differs due to
  the earlier VER source patch.
- [Linker audit](evidence/dos-comsubs-library-audit.json): all 61 LINK steps were
  replayed on a private disk with `/INFORMATION`. The five affected programs load
  `comsubs.c` and `dbcstab.asm` from our archive. Its hash is
  `289fa53f8c4cee0848c2ee4f743a9306cfd70c207200a89a6300be98f5e7f974`.
- [Guest comparisons and utilities](evidence/comsubs-tests.json): 6,456 query
  records provide 32,280 function-result comparisons against both the original
  library and an independent expected-result model. Every input record is also
  checked for unintended modification. All 65,536 return codes are compared
  separately for each implementation.
- [Packaging/native build validation](evidence/comsubs-validation.json): 29
  packaging/provenance regressions, Mac build and bundled-resource verification.

The interface tests cover actual DOS SBCS operation and synthetic DBCS lead
ranges supplied by a guest-only INT 21h hook. All other interrupts continue to
the real kernel. This is function-level DBCS coverage, not a localized Japanese
DOS installation test. The reference programs and replacement programs both run
inside Project86; no other emulator runtime is used.

Characterization used the published header, released callers and MAPPER source,
guest behavior, and limited inspection of the original object code to diagnose
the reference harness. The implementation is newly authored; this is not a claim
of a formally separated clean-room process. The original initialization can
repeatedly allocate case tables because the supplied DosCaseMap wrapper leaves
AX nonzero. The comparison harness runs at most eight queries per process so this
baseline behavior does not exhaust its heap or corrupt later measurements. Our
implementation does not use those tables or that wrapper.

Utility tests exercise SUBST creation, access, writing, removal and invalid paths;
JOIN mounting a private floppy, reading/writing through its directory and removing
the join; REPLACE recursive replacement, add-only operation, read-only refusal,
read-only replacement and missing-source errors. Refused replacement is checked
to leave the original file contents intact. BACKUP/RESTORE preserve a text file
and nested binary file in all four old/new writer-reader combinations. Assertions
read the persisted disks after the emulator exits. Native app interaction,
localized utility filenames and long storage stress remain separate validation.

## Reproduction and preservation

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

The preserved COMSUBS milestone build is `.build/dos-comsubs`, variant
`project86-comsubs-v1`, report schema 4. Its report records the removed original
library, replacement hash, source hashes and the exact permitted artifact changes.
Same-variant seeded builds still require all artifacts to match. Older schemas
remain readable as seeds and evidence; the current default uses original libraries. See [the decision](ORIGINAL-LIBRARIES.md).

The build retains `COMSUBS.LIB` and `comsubs-source.zip` alongside the guest disk.
Validation compares both with the recorded source/build outputs. Packaging
includes that source ZIP inside `dos-project-sources.zip` for the experimental
app and verifies it in Xcode's script sandbox.
The original archives, first/second-generation builds and seed images remain
intact. An initial development build before the DBCS reverse-search correction
is retained at `.build/dos-comsubs-before-dbcs`; it is not the delivered build.
No managed user disk was replaced or modified for this work.
