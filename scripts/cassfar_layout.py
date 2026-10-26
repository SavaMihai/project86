"""Generate C offsets/flags from the pinned SELECT interface declarations."""
import re
import zipfile
from pathlib import Path


def layout_header(archive):
    result = ['/* Generated from the pinned Microsoft SELECT declarations. */']
    prefixes = {'GV', 'INS', 'HRD', 'INC', 'QM', 'PM', 'IN', 'WWP', 'MB'}
    group = None
    offset = 0
    for filename in ['SRC/SELECT/DATA.MAC', 'SRC/SELECT/CASTRUC.INC']:
        for line in archive.read(filename).decode('cp437').splitlines():
            match = re.match(r'^\s*([A-Z][A-Z0-9_]+)\s+D([BW])\s+(.+?)(?:;|$)', line)
            if not match: continue
            name, kind, value = match.groups()
            prefix = name.split('_')[0]
            wanted = prefixes if filename.endswith('DATA.MAC') else {'PCB', 'SCB', 'ICB', 'CHD'}
            if prefix not in wanted: continue
            if prefix != group: group, offset = prefix, 0
            result.append(f'#define {name} {offset}')
            dup = re.search(r'(\d+)\s+DUP', value, re.I)
            if dup: count = int(dup[1])
            elif value.strip().startswith(("'", '"')): count = len(value.strip()[1:value.strip().rfind(value.strip()[0])])
            else: count = len(value.split(','))
            offset += count * (2 if kind == 'W' else 1)
    for line in archive.read('SRC/SELECT/PCEQUATE.INC').decode('cp437').splitlines():
        match = re.match(r'^\s*(\w+)\s+EQU\s+([0-9A-F]+)([BH]?)\s*(?:;|$)', line)
        if match:
            name, value, suffix = match.groups()
            # The numeric capture may consume a final B/H: disambiguate here.
            if not suffix and value.endswith('B') and set(value[:-1]) <= {'0','1'}: value, suffix = value[:-1], 'B'
            result.append(f'#define {name} {int(value, 2 if suffix == "B" else 16 if suffix == "H" else 10)}U')
    return ('\n'.join(result) + '\n').encode('ascii')


if __name__ == '__main__':
    with zipfile.ZipFile(Path(__file__).resolve().parents[1] / 'assets/bootstrap/restored-source.zip') as archive:
        print(layout_header(archive).decode(), end='')
