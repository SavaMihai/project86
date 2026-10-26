#!/usr/bin/env python3
"""Ask the original linker which archive members it uses, inside Project86.

Relinks a private copy of the completed build disk. It never changes the app
image or authoritative DOS outputs. /INFORMATION distinguishes libraries merely
named on a command line from members actually loaded into each executable.
"""
import argparse
import json
from pathlib import Path
import posixpath
import re
import subprocess
from disk_image import FATVolume
from dos_artifacts import DEFAULT_BUILD, ROOT, load_build, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dos-build', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/dos-library-audit-final')
    args = parser.parse_args()
    _, provenance = load_build(args.dos_build)
    retained = json.loads((args.dos_build / 'report.json').read_text())['retained_binary_libraries']
    if args.output.exists(): raise SystemExit('Choose a fresh output directory')
    args.output.mkdir(parents=True)
    cwd = 'SRC'; links = []
    for line in (args.dos_build / 'BUILD.LOG').read_text(encoding='cp437').splitlines():
        command = line.strip()
        if not line[:1].isspace(): continue
        if command.lower().startswith('cd '):
            cwd = posixpath.normpath(posixpath.join(cwd, command[3:].strip().replace('\\', '/')))
        elif re.match(r'link\s', command, re.I):
            links.append({'directory': cwd.upper(), 'command': command})
    if not links: raise ValueError('No recorded linker invocations')
    guest = FATVolume((args.dos_build / 'source.img').read_bytes())
    batch = ['@echo off', 'c:', 'cd \\src', 'call setenv.bat']
    for index, entry in enumerate(links):
        entry['log'] = f'L{index:03}.TXT'
        batch += ['cd \\' + entry['directory'].replace('/', '\\'),
                  re.sub(r'^link\s+', 'link /information ', entry['command'], flags=re.I) + ' > c:\\' + entry['log'],
                  'if errorlevel 1 goto failed']
    batch += ['echo P86 AUDIT SUCCEEDED', 'goto end', ':failed', 'echo P86 AUDIT FAILED', ':end']
    guest.put('AUDIT.BAT', ('\r\n'.join(batch)+'\r\n').encode('ascii'))
    disk = args.output / 'source.img'; disk.write_bytes(guest.image)
    command = [str(ROOT / '.build/p86'), '--disk', str(args.dos_build / 'boot.ima'), '--hard-disk', str(disk),
               '--write', '--command', '', '--command', '', '--command', 'c:\\audit', '--until', 'P86 AUDIT', '--limit', '2000000000']
    result = subprocess.run(command, capture_output=True, timeout=180)
    (args.output / 'screen.txt').write_bytes(result.stdout)
    (args.output / 'progress.log').write_bytes(result.stderr)
    if result.returncode or b'P86 AUDIT SUCCEEDED' not in result.stdout: raise SystemExit('Guest library audit failed')
    guest = FATVolume(disk.read_bytes()); libraries = {}
    for entry in links:
        data = guest.read(entry['log']); (args.output / entry['log']).write_bytes(data)
        entry['log_sha256'] = sha(data); entry['libraries'] = {}
        for lib, member in re.findall(r'^([^\r\n]+\.LIB)\(([^\r\n]+)\)$', data.decode('cp437').replace('\r', ''), re.M | re.I):
            path = lib.strip().upper().replace('\\', '/')
            if path.startswith('C:/'): path = path[3:]
            else: path = posixpath.normpath(posixpath.join(entry['directory'], path))
            members = entry['libraries'].setdefault(path, [])
            if member not in members: members.append(member)
            record = libraries.setdefault(path, {'sha256': sha(guest.read(path)), 'members': [], 'link_steps': [],
                                                'origin': 'supplied binary' if path in retained else 'rebuilt from source'})
            if member not in record['members']: record['members'].append(member)
            if entry['log'] not in record['link_steps']: record['link_steps'].append(entry['log'])
    report = {'schema': 1, 'build': provenance, 'method': 'Original LINK 3.65 /INFORMATION in Project86; private copy of completed build disk',
              'link_steps': links, 'libraries_actually_loaded': libraries}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({path: {'members': len(r['members']), 'link_steps': len(r['link_steps'])} for path,r in libraries.items()},indent=2))

if __name__ == '__main__': main()
