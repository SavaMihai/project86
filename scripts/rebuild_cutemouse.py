#!/usr/bin/env python3
"""Build CuteMouse from pinned upstream source using a native ARM assembler.

No upstream executable is executed or copied into the result. JWasm is compiled
from source with Apple Clang. Its flat 16-bit output receives a data-only DOS MZ
header generated here, replacing the historical TLINK/EXE2BIN/COM2EXE tool chain.
"""
import argparse
import difflib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import struct
import subprocess
import urllib.request
import zipfile
from dos_artifacts import ROOT, sha
from cutemouse_artifacts import DEFAULT_MOUSE_BUILD, MANIFEST, MANIFEST_PATH, load_mouse_build


def download(spec, target):
    if not target.exists():
        with urllib.request.urlopen(spec['url'], timeout=60) as response: data = response.read()
        if sha(data) != spec['sha256']: raise ValueError('Upstream archive checksum mismatch')
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    if sha(target.read_bytes()) != spec['sha256']: raise ValueError(f'Cached checksum mismatch: {target}')


def source_members(archive):
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe archive path')
        if entry.is_dir() or path.suffix.lower() in {'.exe', '.com', '.obj', '.bin'}: continue
        yield entry.filename, archive.read(entry)


def mz_wrap(payload):
    # COM load image at PSP:100h, 512-byte stack; no machine-code wrapper.
    if not payload or len(payload) > 0xf000: raise ValueError('Unexpected COM image size')
    size = len(payload) + 32
    stack = ((len(payload)+15)//16)*16 + 0x100 + 512 - 2
    return struct.pack('<16H', 0x5a4d, size % 512, (size+511)//512, 0, 2,
                       32, 32, 0xfff0, stack, 0, 0x100, 0xfff0, 0x1c, 0, 0, 0) + payload


def compare_encoding(built, published):
    """Allow only symmetric register-register XCHG encodings, not behavior edits."""
    if len(built) != len(published): raise ValueError('Rebuilt CuteMouse size differs from upstream')
    changes = []
    for offset, (new, old) in enumerate(zip(built, published)):
        if new == old: continue
        if not (offset > 32 and built[offset-1] == published[offset-1]
                and built[offset-1] in (0x86, 0x87) and new & 0xc0 == old & 0xc0 == 0xc0
                and new & 7 == (old >> 3) & 7 and old & 7 == (new >> 3) & 7):
            raise ValueError(f'Unexplained CuteMouse difference at file offset {offset}')
        changes.append(offset)
    return changes


def fixed_zip(path, files):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2008, 7, 1, 0, 0, 0)); entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT_MOUSE_BUILD)
    parser.add_argument('--ensure', action='store_true')
    args = parser.parse_args(); directory = args.output.resolve()
    if directory.exists():
        if not args.ensure: raise SystemExit('Choose a fresh output directory')
        load_mouse_build(directory); print('Verified source-built CuteMouse:', directory); return
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('This build recipe currently targets Apple Silicon macOS')
    directory.mkdir(parents=True)
    cached = ROOT / 'assets/guests/cutemouse21b4.zip'
    assembler_zip = ROOT / '.cache/tools/jwasm-source.zip'
    download(MANIFEST['source'], cached); download(MANIFEST['assembler'], assembler_zip)
    with zipfile.ZipFile(cached) as archive:
        sources = dict(source_members(archive)); published = archive.read('bin/ctmouse.exe')
    original = dict(sources)
    name = 'source/ctmouse/ctmouse.asm'; code = sources[name]
    # Current JWasm requires explicit uninitialized structure members. In
    # particular POINT <> would initialize zeros below the COM entry point.
    code, count = re.subn(rb'\bPOINT\s+\?(?=[\t ;\r\n])', b'POINT <?,?>', code)
    if count != 13: raise ValueError('Unexpected POINT declarations')
    code = code.replace(b'BUTTLASTSTATE ?,?,?', b'BUTTLASTSTATE 3 dup(<>)')
    code = code.replace(b'BUTTLASTSTATE ?\t', b'BUTTLASTSTATE <>\t')
    if code.count(b'say\tS_mousetype[si]') != 1: raise ValueError('Unexpected message table operand')
    code = code.replace(b'say\tS_mousetype[si]', b'mov di,S_mousetype[si]\r\n\t\tcall sayASCIIZ')
    sources[name] = code
    name = 'source/ctmouse/asmlib/bios/area0.def'
    sources[name], count = re.subn(rb'\b(HWLIST|KBDFLAGS|VIDEOCONTROL|VIDEOSWITCHES|VGAOPTIONS|KBDSTATUS) \?', rb'\1 <>', sources[name])
    if count != 6: raise ValueError('Unexpected BIOS record declarations')
    patches = ''.join(''.join(difflib.unified_diff(original[n].decode('cp437').splitlines(True), data.decode('cp437').splitlines(True), fromfile=n+'.upstream', tofile=n)) for n,data in sources.items() if data != original[n])
    source_dir = directory / 'sources'
    for name, data in sources.items():
        path = source_dir / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    with zipfile.ZipFile(assembler_zip) as archive:
        assembler_sources = dict(source_members(archive))
    assembler_dir = directory / 'assembler'; assembler_dir.mkdir()
    for name, data in assembler_sources.items():
        relative = PurePosixPath(*PurePosixPath(name).parts[1:])
        path = assembler_dir / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    header = assembler_dir / 'src/H/memalloc.h'; code = header.read_bytes()
    token = b'#include <malloc.h>  /* added v2.07 */'
    if code.count(token) != 1: raise ValueError('Unexpected JWasm allocation header')
    header.write_bytes(code.replace(token, b'#if defined(__APPLE__)\r\n#include <stdlib.h>\r\n#include <alloca.h>\r\n#else\r\n#include <malloc.h>\r\n#endif'))
    units = re.findall(r'\$\(OUTD\)/([a-zA-Z0-9_]+)\.o', (assembler_dir / 'gccmod.inc').read_text())
    compile_command = ['clang', '-D__UNIX__', '-DNDEBUG', '-O2', '-std=gnu99', '-Isrc/H', 'src/main.c'] + [f'src/{u}.c' for u in units if u != 'main'] + ['-o', 'jwasm']
    with (directory / 'compiler.log').open('w') as log:
        subprocess.run(compile_command, cwd=assembler_dir, stdout=log, stderr=log, check=True, timeout=120)
    assemble_command = [str(assembler_dir / 'jwasm'), '-mt', '-bin', '-Foctmouse.bin', 'ctmouse.asm']
    driver_dir = source_dir / 'source/ctmouse'
    with (directory / 'assembler.log').open('w') as log:
        subprocess.run(assemble_command, cwd=driver_dir, stdout=log, stderr=log, check=True, timeout=30)
    driver = mz_wrap((driver_dir / 'ctmouse.bin').read_bytes())
    differences = compare_encoding(driver, published)
    (directory / 'CTMOUSE.EXE').write_bytes(driver)
    license_name = next(n for n in sources if n.lower().endswith('/copying'))
    (directory / 'CUTEMOUSE-COPYING.txt').write_bytes(sources[license_name])
    bundle = dict(sources)
    bundle['project86/changes.patch'] = patches.encode('utf-8')
    for name in ['rebuild_cutemouse.py', 'cutemouse_artifacts.py', 'dos_artifacts.py', 'disk_image.py']:
        bundle['project86/scripts/'+name] = (ROOT / 'scripts' / name).read_bytes()
    for name in ['cutemouse-manifest.json', 'dos-files.json']:
        bundle['project86/assets/'+name] = (ROOT / 'assets' / name).read_bytes()
    bundle['project86/README.txt'] = ("Project86 builds CuteMouse 2.1 beta4 from upstream source using a native ARM JWasm built with Apple Clang.\n"
        "All EXE/COM/OBJ/BIN files from upstream were excluded from this source bundle and build inputs.\n"
        "The source/ tree includes our documented syntax repairs; changes.patch records them.\n"
        "To reproduce on an Apple Silicon Mac with Xcode command-line tools, run:\n"
        "cd project86\npython3 scripts/rebuild_cutemouse.py\n"
        "The recipe downloads checksum-pinned CuteMouse and JWasm sources, applies the documented repairs, assembles a flat payload, and generates a data-only MZ header.\n"
        "The original published driver is read only to validate encoding equivalence; it is never executed or installed.\n").encode()
    fixed_zip(directory / 'cutemouse-source.zip', bundle)
    outputs = {name: {'sha256': sha((directory/name).read_bytes()), 'bytes': (directory/name).stat().st_size}
               for name in ['CTMOUSE.EXE', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt']}
    report = {'schema': 1, 'build_succeeded': True, 'version': MANIFEST['version'],
              'manifest_sha256': sha(MANIFEST_PATH.read_bytes()), 'recipe_sha256': sha(Path(__file__).read_bytes()),
              'source': MANIFEST['source'], 'assembler': MANIFEST['assembler'],
              'host': platform.machine(), 'compiler': subprocess.check_output(['clang','--version'],text=True).splitlines()[0],
              'compiler_command': compile_command, 'assembler_command': ['jwasm', *assemble_command[1:]],
              'assembler_binary_sha256': sha((assembler_dir/'jwasm').read_bytes()),
              'patches': ['Explicit uninitialized POINT/array and BIOS record syntax for modern JWasm',
                          'Load mouse-type string pointer into DI before sayASCIIZ, as intended by original macro',
                          'JWasm host header uses stdlib.h/alloca.h on macOS'],
              'mz_header': 'Generated locally; 512-byte stack, PSP-relative CS/SS, no executable stub or relocations',
              'published_driver_sha256': sha(published), 'identical_to_published': driver == published,
              'equivalence': 'Same length and identical bytes except register-register XCHG operand-order encodings',
              'equivalent_xchg_file_offsets': differences, 'outputs': outputs}
    (directory / 'report.json').write_text(json.dumps(report,indent=2)+'\n')
    load_mouse_build(directory)
    print(f'Built CuteMouse {MANIFEST["version"]}: {len(driver)} bytes; {len(differences)} equivalent XCHG encodings differ from upstream')


if __name__ == '__main__': main()
