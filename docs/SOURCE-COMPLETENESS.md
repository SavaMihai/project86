# Guest source completeness

Checked 2026-10-26. The default again uses the original **COMSUBS, CASSFAR,
SLIBCE and MEM** binary libraries, by the owner's choice. The boot sector and all
62 DOS distribution files are still our build outputs (two profiles are unchanged
source text). CuteMouse is built from source. Our COMSUBS/CASSFAR implementations
are preserved as an optional experimental variant; replacing the remaining
libraries is deferred. See [the decision and validation](ORIGINAL-LIBRARIES.md).

The current default changes only COMMAND.COM relative to the restoration
distribution: it includes our history/Tab-completion editor and the earlier VER
message. The other 61 distribution files and boot code retain the original-library
baseline. The kernel version is unchanged. See [COMMAND](COMMAND-EDITOR.md).

## Default binary dependencies

The [preserved original-library linker audit](evidence/dos-original-libraries-audit.json)
replayed all 61 LINK invocations on a private build disk. The enhanced shell changes
only COMMAND.COM, which links no library; the affected utility outputs remain identical. These four
supplied archives contribute code to 11 distinct utilities; no utility is missing.

| Supplied library | Loaded members / links | Affected guest files | Purpose |
|---|---|---|---|
| `INC/COMSUBS.LIB` | 6 / 5 | JOIN, SUBST, BACKUP, RESTORE, REPLACE | String/DBCS helpers and return-code conversion |
| `SELECT/CASSFAR.LIB` | 24 / 1 | SELECT | Panels, menus, input, video and help interfaces |
| `TOOLS/BLD/LIB/SLIBCE.LIB` | 97 / 10 | ATTRIB, FC, JOIN, SUBST, FILESYS, BACKUP, FDISK, RESTORE, REPLACE, SELECT | C startup, strings, memory, I/O, DOS calls, arithmetic and software floating point |
| `LIB/MEM.LIB` | 40 / 1 | MEM | C runtime variant and startup |

Counts describe object modules, not unique functions. Modules overlap between the
runtime variants. FDISK names COMSUBS but loads no members; SELECT.DAT names
CASSFAR but loads none. The audit records exact archive hashes and loaded members.
Schemas 6 and 7 with original libraries validate all four original library bytes against pinned hashes on the
retained guest build disk. Cache selection cannot silently switch implementations.

MAPPER, SERVICES and EMMLIB are still source-built. The boot sector, IO.SYS,
MSDOS.SYS, COMMAND.COM and CuteMouse use none of these four supplied libraries.
The original MASM, LINK, C compiler and build helpers remain binary build tools.
Rebuilding those tools is a separate compiler-bootstrap task. Every shipped DOS
executable is a build output; this is not a source rebuild of every linked byte.

## Preserved source replacements

`DOS_LIBRARIES=source` builds both our COMSUBS and CASSFAR implementations in a
separate DOS build directory. Only SLIBCE and MEM remain binary libraries in that
variant, affecting the same 11 utilities. These replacements cover the interfaces
used by this distribution, not every historical library API. Their sources,
builds and earlier evidence remain intact:

- [COMSUBS](COMSUBS.md): five public interfaces; 6,456 guest queries, all 65,536
  return codes, SUBST/JOIN/REPLACE and cross-version BACKUP/RESTORE tests.
- [CASSFAR](CASSFAR.md): ten SELECT interfaces; 345 key queries, 57 help topics,
  17 screen states and real private-disk installations.

The app's `dos-project-sources.zip` describes the selected binary boundary and
contains corresponding source ZIPs only when replacements are linked. The default
package contains build information and COMMAND editor source, with no library
replacement source. Original guest
binaries are never substituted for the newly rebuilt DOS executables.

The earlier [second-generation build](evidence/dos-second-generation.json)
reproduced all 63 artifacts using our rebuilt floppy while accesses to the original
floppy and network were blocked. The restored-library milestone booted the preserved
CASSFAR floppy and reproduces the earlier original-library output. These results
establish DOS boot-seed reproduction, not a source-built compiler toolchain.

## Source search result

We checked the complete [Microsoft repository tree](https://github.com/microsoft/MS-DOS/tree/2d04cacc5322951f187bb17e017c12920ac8ebe2/v4.0/src), the pinned restoration archive, and targeted GitHub/web searches for library names, original build targets and member names. No matching, verifiably open-source release of these missing implementations was located. This does not prove that no copy exists elsewhere. [Search evidence](evidence/source-search.json) records the scope.

The search did find a later DOS repository whose own description says it is leaked MS-DOS 6.0 beta source and which exposes no repository license. We inspected metadata/directory names and did not import its implementation. It is not a verified source for the released DOS 4 libraries.

Complete guest-source coverage would require the optional COMSUBS/CASSFAR replacements plus verified source or compatible implementations for SLIBCE and MEM. That work is deferred; it is not required to develop DOS features or the emulator.

## CuteMouse rebuild completed

We moved from the prebuilt 1.9.1 alpha 1 driver to **CuteMouse 2.1 beta4**, whose [upstream release documents JWasm support](https://cutemouse.sourceforge.net/). This is a version change; its default sensitivity differs. Serial input, button reporting and gameplay are tested against the new driver.

`make mouse` compiles pinned JWasm source into a native ARM assembler using Apple Clang, then assembles the published driver/macro source. Small syntax repairs make uninitialized aggregates and the message-pointer operand explicit for modern JWasm. A native Python step writes the DOS MZ header with a 512-byte stack; it adds no executable stub. No prebuilt TLINK, COM2EXE or CuteMouse executable is executed or installed by this build.

The 5,829-byte result differs from the published 2.1 beta4 driver at only 11 register-register XCHG encodings. Each difference swaps the encoded register operands of the symmetric XCHG operation; every other byte, including the MZ header, is identical. The build rejects any other difference. [Build report](evidence/cutemouse-build.json).

The app bundles the rebuilt driver in its floppy and a `cutemouse-source.zip` containing corresponding source, notices, patches and the reproduction recipe. Original downloaded executables are excluded from that source archive. A second build from only this source package reproduces the exact driver SHA-256 `74200ce10a70d3e33cfc65dcb988998e643aac637e0419151c54a8649a87e140`.

## Reproduce

```sh
make mouse
make guests
make packaging-tests
make guest-tests
python3 scripts/audit_dos_libraries.py --output .build/dos-library-audit-new
```

A fresh mouse build can be selected with `make mac MOUSE_BUILD=.build/cutemouse-new`. The app packages that build's matching source and license. Missing, changed or stale driver outputs fail packaging; no downloaded-driver fallback exists. Existing working disks remain untouched until the user chooses a fresh boot floppy.
