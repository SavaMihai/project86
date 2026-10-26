#!/usr/bin/env python3
"""Boot real CuteMouse while host pointer events arrive, including warm reboots.

Uses private disks and the same 60 Hz core slices as the native worker. Driver
installation and INT 33h results come from guest execution, never host stubs.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from disk_image import FATVolume,create_hard_disk
from dos_artifacts import DEFAULT_BUILD,ROOT
from prepare_guests import OUTPUT,verify_build_image
from p86 import Machine


def boot_input(machine,kind,frame_hz=60):
    remainder=0
    for tick in range(6*frame_hz):
        if kind=='idle-events':machine.call('mouse',0,0,0)
        elif kind=='motion':machine.call('mouse',1,0,0)
        elif kind=='large-motion':machine.call('mouse',51,-3,0)
        elif kind=='right-drag':machine.call('mouse',-100,-100,2)
        elif kind=='clicks':machine.call('mouse',0,0,tick%3)
        remainder+=4_772_728
        machine.call('run_cycles',remainder//frame_hz);remainder%=frame_hz;machine.check()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--image',type=Path,default=OUTPUT)
    parser.add_argument('--dos-build',type=Path,default=DEFAULT_BUILD)
    parser.add_argument('--cpu-speed',type=int,choices=[1,4,8,16],default=1)
    parser.add_argument('--frame-hz',type=int,choices=[50,60],default=60)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    receipt=verify_build_image(args.image,args.dos_build)
    args.output.mkdir(parents=True,exist_ok=False)
    program=args.output/'MOUSE.COM'
    subprocess.run(['nasm','-f','bin',str(ROOT/'tests/guests/mouse.asm'),'-o',str(program)],check=True)
    image=FATVolume((args.image/'project86.ima').read_bytes());image.put('MOUSE.COM',program.read_bytes())
    # Keep the shipped boot screen quiet while retaining guest-written detection
    # diagnostics in this private test's C: disk. Production redirects to NUL.
    autoexec=image.read('AUTOEXEC.BAT')
    quiet_startup=b'a:\\ctmouse /s1 /y >nul\r\n' in autoexec
    if quiet_startup:
        image.put('AUTOEXEC.BAT',autoexec.replace(b'a:\\ctmouse /s1 /y >nul\r\n',
                                                b'a:\\ctmouse /s1 /y >c:\\mouse.log\r\n'))
    first=args.output/'boot.ima';first.write_bytes(image.image)
    hard=args.output/'hard.img';marker=b'private persistent disk\r\n';hard.write_bytes(create_hard_disk({'KEEP.TXT':marker}).image)
    machine=Machine(first,hard,True,cpu_speed=args.cpu_speed)
    result={'passed':False,'cpu_speed':args.cpu_speed,'frame_hz':args.frame_hz,'image_sha256':receipt['image_sha256'],'ctmouse_sha256':receipt['files']['CTMOUSE.EXE']['sha256'],
            'cases':{},'reboot_cases':{},'private_hard_disk_preserved':False,
            'startup_diagnostics_in_private_log':quiet_startup}
    kinds=['quiet','idle-events','motion','large-motion','right-drag','clicks']
    def check(kind,floppy,group):
        boot_input(machine,kind,args.frame_hz)
        screen=machine.text();(args.output/(group+'-'+kind+'.txt')).write_text(screen+'\n')
        diagnostic=screen
        if quiet_startup:
            assert [line for line in screen.splitlines() if line.strip()]==['MS-DOS 4.0 (Project86)','A:\\>'],screen
            assert machine.call('flush_disks')
            diagnostic=FATVolume(hard.read_bytes()).read('MOUSE.LOG').decode('cp437')
            (args.output/(group+'-'+kind+'-driver.txt')).write_text(diagnostic)
        assert 'Installed at COM1 (03F8h/IRQ4) in Microsoft mode' in diagnostic,diagnostic
        assert 'device not found' not in diagnostic and 'wheel present' not in diagnostic and 'Logitech mode' not in diagnostic,diagnostic
        # End boot-time events; a fresh probe clears prior movement and sets a
        # known cursor position. Then validate actual post-install driver input.
        machine.call('mouse',0,0,0);machine.seconds(.3)
        machine.type('if exist mouse.dat del mouse.dat\r');machine.seconds(.3)
        assert machine.call('flush_disks')
        try:FATVolume(floppy.read_bytes()).read('MOUSE.DAT')
        except FileNotFoundError:pass
        else:raise AssertionError('Stale mouse probe output survived cleanup')
        machine.type('mouse\r');machine.seconds(1)
        machine.call('mouse',7,-3,1);machine.seconds(.2);machine.key(0x1c,13);machine.seconds(.5)
        assert machine.call('flush_disks')
        buttons,x,y,dx,dy=struct.unpack('<HHHhh',FATVolume(floppy.read_bytes()).read('MOUSE.DAT'))
        assert (buttons,dx,dy)==(1,12,-3) and x!=320 and y!=100,(kind,buttons,x,y,dx,dy)
        result[group][kind]={'installed':True,'mode':'Microsoft, no wheel','buttons':buttons,'x':x,'y':y,'dx':dx,'dy':dy}
    try:
        for kind in kinds:
            floppy=args.output/(kind+'.ima');floppy.write_bytes(image.image)
            # Same core is reused, just as Boot rebuilt MS-DOS attaches a fresh
            # floppy and resets the machine while preserving the hard disk.
            assert machine.call('attach_floppy',str(floppy).encode(),1)
            assert machine.call('boot')
            check(kind,floppy,'cases')
            assert machine.call('boot')
            check(kind,floppy,'reboot_cases')
        assert machine.call('flush_disks')
        assert FATVolume(hard.read_bytes()).read('KEEP.TXT')==marker
        result['private_hard_disk_preserved']=True;result['passed']=True
    finally:
        machine.close();(args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print('CuteMouse startup and reboot tests passed:',args.output)


if __name__=='__main__':main()
