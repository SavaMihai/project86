#!/usr/bin/env python3
import hashlib
import argparse
import json
from pathlib import Path
import struct
import subprocess
from disk_image import FATVolume
from p86 import Machine,ROOT
from prepare_guests import prepare
from dos_artifacts import DEFAULT_BUILD
from cutemouse_artifacts import DEFAULT_MOUSE_BUILD, load_mouse_build

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dos-build',type=Path,default=DEFAULT_BUILD)
    parser.add_argument("--mouse-build",type=Path,default=DEFAULT_MOUSE_BUILD)
    args=parser.parse_args()
    original=prepare(args.dos_build,mouse_build=args.mouse_build);disk=ROOT/'.build/guest-tests.ima';volume=FATVolume(original.read_bytes())
    for name in ['cpu','mouse']:
        binary=ROOT/f'.build/{name}.com'
        subprocess.run(['nasm','-f','bin',str(ROOT/f'tests/guests/{name}.asm'),'-o',str(binary)],check=True)
        volume.put(f'{name.upper()}.COM',binary.read_bytes())
    disk.write_bytes(volume.image)
    m=Machine(disk,writable=True)
    try:
        m.type('cpu\r');m.seconds(1)
        assert 'P86 ASSEMBLED CPU PASS' in m.text(),m.text()
        m.type('mouse\r');m.seconds(1)
        m.call('mouse',7,-3,1);m.seconds(.2);m.key(0x1c,13);m.seconds(1)
        assert m.call('flush_disks')
        report=FATVolume(disk.read_bytes()).read('MOUSE.DAT')
        buttons,x,y,dx,dy=struct.unpack('<HHHhh',report)
        assert buttons==1 and dx==12 and dy==-3,(buttons,x,y,dx,dy)
        assert x!=320 and y!=100,(x,y)
        result={'cpu_program':'NASM-built COM passed inside MS-DOS 4.00',
                'mouse_driver':'Source-built CuteMouse 2.1 beta4, COM1/IRQ4 Microsoft protocol',
                'motion_note':'CuteMouse 2.1 default sensitivity produces 12,-3 mickeys for this 7,-3 serial packet',
                'mouse_report':{'buttons':buttons,'x':x,'y':y,'dx':dx,'dy':dy},
                'ctmouse_sha256':hashlib.sha256(load_mouse_build(args.mouse_build)[0]).hexdigest()}
        (ROOT/'.build/guest-results.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Guest integration passed: assembled CPU program; real CuteMouse movement and button reporting.')
    finally: m.close()
if __name__=='__main__': main()
