"""Apply the reproducible interactive COMMAND.COM source changes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'guest-build/command'
FILES = {'PCEDIT.ASM': 'editor.asm', 'PCHIST.INC': 'history.inc', 'PCWORK.INC': 'work.inc'}
PREFIX = 'SRC/CMD/COMMAND/'


def patch_command(files):
    sources = {name: (SOURCE / local).read_text().replace('\n', '\r\n').encode('ascii')
               for name, local in FILES.items()}
    def replace(name, old, new):
        path = PREFIX + name
        if files[path].count(old) != 1:
            raise ValueError(f'Expected unique COMMAND source anchor: {name}')
        files[path] = files[path].replace(old, new)
    replace('TCODE.ASM', b'\tMOV\tAH,STD_CON_STRING_INPUT\r\n\tINT\tint_command\t\t\t; Get a command',
            b'\tCALL\tP86READ\t\t\t; Project86 interactive history/completion')
    replace('TCODE.ASM', b'TRANCODE\tENDS\r\n\tEND', b'\tINCLUDE PCEDIT.ASM\r\nTRANCODE\tENDS\r\n\tEND')
    replace('RDATA.ASM', b'DATARES SEGMENT PUBLIC BYTE\r\n',
            b'DATARES SEGMENT PUBLIC BYTE\r\n\tINCLUDE PCHIST.INC\r\n')
    replace('TSPC.ASM', b'TRANSPACEEND\tLABEL\tBYTE',
            b'\tINCLUDE PCWORK.INC\r\nTRANSPACEEND\tLABEL\tBYTE')
    # Includes must invalidate their owner objects during incremental DOS builds.
    replace('MAKEFILE', b'tcode.obj:  tcode.asm ', b'tcode.obj:  tcode.asm PCEDIT.ASM ')
    replace('MAKEFILE', b'rdata.obj:  rdata.asm ', b'rdata.obj:  rdata.asm PCHIST.INC ')
    replace('MAKEFILE', b'tspc.obj:  tspc.asm ', b'tspc.obj:  tspc.asm PCWORK.INC ')
    for name, data in sources.items(): files[PREFIX + name] = data
    return sources
