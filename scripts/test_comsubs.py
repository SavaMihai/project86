#!/usr/bin/env python3
"""Compare guest COMSUBS implementations and exercise real DOS utilities.

All writes use fresh private images. No host substitutes for guest DOS results.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from disk_image import FATVolume, create_floppy, create_hard_disk
from dos_artifacts import ROOT, DEFAULT_BUILD, COMSUBS_SOURCE, load_build, sha


def batch(lines):
    return ('\r\n'.join(['@echo off', *lines, 'echo P86 TEST SUCCEEDED', 'goto end',
                         ':failed', 'echo P86 TEST FAILED', ':end']) + '\r\n').encode('ascii')


def run(directory, floppy, hard, commands, limit=2000000000):
    command = [str(ROOT / '.build/p86'), '--disk', str(floppy), '--hard-disk', str(hard), '--write',
               '--until', 'P86 TEST', '--limit', str(limit), '--progress']
    for text in commands: command += ['--command', text]
    with (directory / 'screen.txt').open('w') as stdout, (directory / 'progress.log').open('w') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=180)
    screen = (directory / 'screen.txt').read_text()
    if result.returncode or 'P86 TEST SUCCEEDED' not in screen:
        raise AssertionError(f'Guest test failed in {directory}: exit {result.returncode}; see screen.txt and progress.log')
    return FATVolume(hard.read_bytes())


def corpus():
    strings = [b'', b'abc', b'abcabc', b'a:b\\c', b'\\', b'file.txt', b'AaZz09',
               b'\x80\xff\\', b'\x81\\a\\b', b'a\xe0a\\z', b'\x9f?\xfc*\\', b'\x81\\\x81\\']
    patterns = [b'', b'a', b'ab', b'ba', b'bc', b':\\', b'\\', b'?', b'*', b'\x81\\', b'\xe0a', b'\x80', b'zz']
    queries = [(s, patterns[n % len(patterns)], n) for s in strings for n in range(256)]
    queries += [(s, p, 0x1234) for s in strings for p in patterns]
    return queries


def expected(query, dbcs):
    text, pattern, word = query
    def width(s, at):
        lead = dbcs and (0x81 <= s[at] <= 0x9f or 0xe0 <= s[at] <= 0xfc)
        return 2 if lead and at + 1 < len(s) else 1
    starts, at = [], 0
    while at < len(text):
        starts.append(at); at += width(text, at)
    wanted = word & 255
    matches = [at for at in starts if width(text, at) == 1 and text[at] == wanted]
    reverse = [at for at in starts if text[at] == wanted]
    if wanted == 0:
        matches.append(len(text)); reverse.append(len(text))
    substring = len(text) if not pattern else 0xffff
    if pattern:
        for start in starts:
            a, b = start, 0
            while a < len(text) and b < len(pattern):
                step = width(text, a)
                if width(pattern, b) != step or text[a:a+step] != pattern[b:b+step]: break
                a += step; b += step
            if b == len(pattern): substring = start; break
    return (matches[0] if matches else 0xffff, reverse[-1] if reverse else 0xffff, substring,
            wanted - 32 if 97 <= wanted <= 122 else wanted, word)


def interface_tests(baseline, build, output):
    output.mkdir()
    guest = FATVolume((baseline / 'source.img').read_bytes())
    candidate = FATVolume((build / 'source.img').read_bytes())
    guest.put('NEW.LIB', candidate.read('SRC/INC/COMSUBS.LIB'))
    guest.put('PROBE.C', (COMSUBS_SOURCE / 'probe.c').read_bytes())
    guest.put('NLS.ASM', (COMSUBS_SOURCE / 'probe-nls.asm').read_bytes())
    queries = corpus()
    encoded = b''.join(struct.pack('<32s16sH', *q) for q in queries)
    guest.put('QUERY.BIN', encoded)
    lines = ['c:', 'cd \\src', 'call setenv.bat', 'cd \\',
             'cl -c -AS -Od -Zp -Ic:\\src\\h probe.c > compile.log', 'if errorlevel 1 goto failed',
             'masm -Mx -t nls.asm; >> compile.log', 'if errorlevel 1 goto failed',
             'link probe.obj+nls.obj,old.exe,,c:\\src\\inc\\comsubs.lib+c:\\src\\mapper\\mapper.lib; >> compile.log',
             'if errorlevel 1 goto failed',
             'link probe.obj+nls.obj,new.exe,,new.lib+c:\\src\\mapper\\mapper.lib; >> compile.log', 'if errorlevel 1 goto failed']
    for impl in ['old', 'new']:
        lines += [f'{impl} R 0 {impl}rc.bin', 'if errorlevel 1 goto failed']
        for mode in (0, 1):
            for start in range(0, len(queries), 8):
                lines += [f'{impl} {start} {mode} {impl}{mode}.bin', 'if errorlevel 1 goto failed']
    guest.put('RUN.BAT', batch(lines))
    hard = output / 'source.img'; hard.write_bytes(guest.image)
    # Copy the compiler floppy too: neither baseline disk is opened writable.
    floppy = output / 'boot.ima'; floppy.write_bytes((baseline / 'boot.ima').read_bytes())
    guest = run(output, floppy, hard, ['c:\\run'], limit=10000000000)
    (output / 'COMPILE.LOG').write_bytes(guest.read('COMPILE.LOG'))
    for impl in ['old', 'new']:
        data = guest.read(f'{impl}rc.bin')
        assert data == struct.pack('<65536H', *range(65536)), f'{impl} return-code map'
        (output / f'{impl}-return-codes.bin').write_bytes(data)
    records = []
    for mode in (0, 1):
        a, b = guest.read(f'old{mode}.bin'), guest.read(f'new{mode}.bin')
        for impl, data in [('old', a), ('new', b)]:
            assert len(data) == len(queries) * 60, (impl, mode, len(data))
            (output / f'{impl}-mode{mode}.bin').write_bytes(data)
        mismatches = []
        for i, q in enumerate(queries):
            oa, nb = a[i*60:(i+1)*60], b[i*60:(i+1)*60]
            predicted = struct.pack('<5H', *expected(q, bool(mode))) + encoded[i*50:(i+1)*50]
            if oa != nb or nb != predicted:
                mismatches.append({'index': i, 'query': [q[0].hex(), q[1].hex(), q[2]],
                                   'original': list(struct.unpack('<5H', oa[:10])),
                                   'replacement': list(struct.unpack('<5H', nb[:10])),
                                   'expected': list(expected(q, bool(mode))),
                                   'inputs_unchanged': oa[10:] == nb[10:] == predicted[10:]})
        (output / f'mismatches-{mode}.json').write_text(json.dumps(mismatches, indent=2) + '\n')
        if mismatches: raise AssertionError(f'{len(mismatches)} interface mismatches in mode {mode}; see {output}')
        records.append({'mode': 'synthetic DBCS ranges' if mode else 'actual DOS SBCS',
                        'queries': len(queries), 'function_results': len(queries)*5,
                        'inputs_unchanged': True, 'old_sha256': sha(a), 'new_sha256': sha(b)})
    return {'passed': True, 'modes': records, 'exhaustive_return_codes': 65536,
            'original_library_process_isolation': 'At most eight queries per guest process to bound original initialization leaks',
            'dbcs_scope': 'Guest INT 21h/6300 hook supplies lead ranges; all other services use real DOS. No localized DOS installation is claimed.'}


def utility_image(output, binaries, files, lines):
    output.mkdir()
    files = {**files, 'COMMAND.COM': binaries['COMMAND.COM'], 'RUN.BAT': batch(lines)}
    for name in ['JOIN.EXE', 'SUBST.EXE', 'BACKUP.COM', 'RESTORE.COM', 'REPLACE.EXE', 'ATTRIB.EXE', 'FORMAT.COM']:
        files.setdefault(name, binaries[name])
    hard = output / 'working.img'; hard.write_bytes(create_hard_disk(files).image)
    boot_files = {name: binaries[name] for name in ['IO.SYS', 'MSDOS.SYS', 'COMMAND.COM']}
    boot_files['CONFIG.SYS'] = b'FILES=64\r\nBUFFERS=20\r\nLASTDRIVE=Z\r\nSHELL=C:\\COMMAND.COM /P /E:1024\r\n'
    boot_files['AUTOEXEC.BAT'] = b'@echo off\r\n'
    boot_files['MARKER.TXT'] = b'PRIVATE JOIN FLOPPY\r\n'
    floppy = output / 'working.ima'; floppy.write_bytes(create_floppy(binaries['BOOT.BIN'], boot_files).image)
    guest = run(output, floppy, hard, ['c:\\run', '', '', '', ''])
    return guest, FATVolume(floppy.read_bytes())


def utility_tests(baseline, build, output):
    output.mkdir()
    old, _ = load_build(baseline); new, _ = load_build(build)
    results = {}
    for label, binaries in [('original', old), ('replacement', new)]:
        files = {'SUBDIR/INPUT.TXT': b'SUBST INPUT\r\n', 'IN/A.TXT': b'NEW A\r\n',
                 'IN/B.TXT': b'NEW B\r\n', 'DEST/A.TXT': b'OLD A\r\n',
                 'DEST/SUB/A.TXT': b'OLD CHILD A\r\n', 'RO/A.TXT': b'OLD READONLY\r\n'}
        lines = ['c:', 'cd \\', 'subst d: c:\\subdir', 'if errorlevel 1 goto failed',
                 'echo SUBST WRITE>d:\\written.txt', 'copy d:\\input.txt c:\\subread.txt > nul',
                 'subst > sublist.txt', 'subst d: /d', 'if errorlevel 1 goto failed',
                 'subst > subafter.txt', 'subst e: c:\\missing > suberr.txt',
                 'if not errorlevel 1 goto failed',
                 'md mount', 'join a: c:\\mount', 'if errorlevel 1 goto failed',
                 'copy c:\\mount\\marker.txt c:\\joinread.txt > nul',
                 'echo JOIN WRITE>c:\\mount\\joined.txt', 'join > joinlist.txt',
                 'join a: /d', 'if errorlevel 1 goto failed', 'join > joinaft.txt',
                 'replace c:\\in\\*.txt c:\\dest /s > reps.txt', 'if errorlevel 1 goto failed',
                 'replace c:\\in\\*.txt c:\\dest /a > repa.txt', 'if errorlevel 1 goto failed',
                 'attrib +r c:\\ro\\a.txt', 'replace c:\\in\\a.txt c:\\ro > reproerr.txt',
                 'if not errorlevel 1 goto failed',
                 'copy c:\\ro\\a.txt c:\\rokeep.txt > nul',
                 'replace c:\\in\\a.txt c:\\ro /r > repr.txt', 'if errorlevel 1 goto failed',
                 'replace c:\\missing\\*.txt c:\\dest > reperr.txt', 'if not errorlevel 1 goto failed']
        guest, floppy = utility_image(output / label, binaries, files, lines)
        expected_files = {'SUBDIR/WRITTEN.TXT': b'SUBST WRITE\r\n', 'SUBREAD.TXT': b'SUBST INPUT\r\n',
                          'JOINREAD.TXT': b'PRIVATE JOIN FLOPPY\r\n', 'DEST/A.TXT': b'NEW A\r\n',
                          'DEST/SUB/A.TXT': b'NEW A\r\n', 'DEST/B.TXT': b'NEW B\r\n', 'RO/A.TXT': b'NEW A\r\n'}
        expected_files['ROKEEP.TXT'] = b'OLD READONLY\r\n'
        for name, contents in expected_files.items(): assert guest.read(name) == contents, (label, name)
        assert floppy.read('JOINED.TXT') == b'JOIN WRITE\r\n'
        assert not guest.read('SUBAFTER.TXT').strip() and not guest.read('JOINAFT.TXT').strip()
        diagnostics = {name: guest.read(name) for name in ['SUBERR.TXT', 'REPROERR.TXT', 'REPERR.TXT']}
        # SUBST writes its error to stderr, which DOS 4's > does not redirect.
        diagnostics['SCREEN.TXT'] = (output / label / 'screen.txt').read_bytes()
        for name, data in diagnostics.items(): (output / label / name).write_bytes(data)
        assert b'Path not found' in diagnostics['SCREEN.TXT']
        assert diagnostics['REPROERR.TXT'] and diagnostics['REPERR.TXT']
        results[label] = {'passed': True, 'files_checked': len(expected_files)+1,
                          'error_output_sha256': {name: sha(data) for name, data in diagnostics.items()}}
    assert results['original']['error_output_sha256'] == results['replacement']['error_output_sha256']
    backup_data = {'DATA/A.TXT': b'BACKUP TEXT\r\n', 'DATA/SUB/B.BIN': bytes(range(256))*3}
    for label, writer, reader in [('old-old', old, old), ('new-new', new, new), ('old-new', old, new), ('new-old', new, old)]:
        files = {**backup_data, 'BACKUP.COM': writer['BACKUP.COM'], 'RESTORE.COM': reader['RESTORE.COM']}
        lines = ['c:', 'cd \\', 'backup c:\\data\\*.* a: /s > back.txt', 'if errorlevel 1 goto failed',
                 'del c:\\data\\a.txt', 'del c:\\data\\sub\\b.bin',
                 'restore a: c:\\data\\*.* /s > rest.txt', 'if errorlevel 1 goto failed']
        guest, floppy = utility_image(output / label, new, files, lines)
        for name, data in backup_data.items(): assert guest.read(name) == data, (label, name)
        for name in ['BACK.TXT', 'REST.TXT']: (output / label / name).write_bytes(guest.read(name))
        results[label] = {'passed': True, 'restored_files': {name: sha(data) for name, data in backup_data.items()},
                          'backup_program_sha256': sha(writer['BACKUP.COM']), 'restore_program_sha256': sha(reader['RESTORE.COM'])}
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, default=ROOT / '.build/dos-second-generation')
    parser.add_argument('--dos-build', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', choices=['interfaces', 'utilities'])
    args = parser.parse_args()
    _, original = load_build(args.baseline); _, replacement = load_build(args.dos_build)
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'baseline': original, 'replacement': replacement, 'passed': False}
    try:
        if args.only != 'utilities': report['interfaces'] = interface_tests(args.baseline, args.dos_build, args.output / 'interfaces')
        if args.only != 'interfaces': report['utilities'] = utility_tests(args.baseline, args.dos_build, args.output / 'utilities')
        report['passed'] = True
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMSUBS tests passed:', args.output)


if __name__ == '__main__': main()
