#!/usr/bin/env python3
"""Measure our interpreter on user-supplied Wolf3D, using private guest disks.

VGA page switches are a proxy for completed game renders, not native-window FPS.
Core and framebuffer timings exclude the native UI and Python observer overhead.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import statistics
import time
from disk_image import create_hard_disk
from dos_artifacts import ROOT,sha
from p86 import Machine
from prepare_guests import OUTPUT

CLOCK=4772728

def page(machine):
    index=machine.lib.p86_read_port(machine.handle,0x3d4)
    machine.lib.p86_write_port(machine.handle,0x3d4,12);hi=machine.lib.p86_read_port(machine.handle,0x3d5)
    machine.lib.p86_write_port(machine.handle,0x3d4,13);lo=machine.lib.p86_read_port(machine.handle,0x3d5)
    machine.lib.p86_write_port(machine.handle,0x3d4,index)
    return hi*256+lo


def setup(machine):
    machine.type('c:\rcd wolf\rwolf3d\r')
    machine.seconds(10);machine.key(0x39,32,.3);machine.seconds(10);machine.key(0x39,32,.3);machine.seconds(20)
    machine.key(1,27,.3);machine.seconds(20);machine.key(0x31,ord('n'),.3);machine.seconds(1)
    for _ in range(3):machine.key(0x1c,13,.3);machine.seconds(12)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    parser.add_argument('--library',type=Path,default=ROOT/'.build/libproject86.dylib')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--speed',type=int,choices=[1,4,8,16],default=1)
    parser.add_argument('--seconds',type=int,default=6);parser.add_argument('--audio',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    files={'WOLF/'+p.name.upper():p.read_bytes() for p in args.directory.iterdir() if p.is_file() and not p.name.startswith('.')}
    assert 'WOLF/WOLF3D.EXE' in files
    disk=args.output/'wolf.img';disk.write_bytes(create_hard_disk(files).image)
    boot=args.output/'boot.ima';boot.write_bytes((OUTPUT/'project86.ima').read_bytes())
    machine=Machine(boot,disk,True,library=args.library)
    machine.lib.p86_read_port.argtypes=[C.c_void_p,C.c_uint16];machine.lib.p86_read_port.restype=C.c_uint8
    machine.lib.p86_write_port.argtypes=[C.c_void_p,C.c_uint16,C.c_uint8];machine.lib.p86_write_port.restype=None
    result={'passed':False,'library_sha256':sha(args.library.read_bytes()),'library':str(args.library),
            'image_sha256':sha(boot.read_bytes()),'inputs':{name:sha(data) for name,data in files.items()},
            'cpu_multiplier':args.speed,'audio':args.audio,'phases':{}}
    try:
        setup(machine);machine.capture(args.output/'start.png')
        assert machine.snapshot().video_mode==0x13
        if args.speed!=1:
            machine.lib.p86_set_cpu_speed.argtypes=[C.c_void_p,C.c_uint32]
            machine.lib.p86_set_cpu_speed.restype=None
            machine.lib.p86_set_cpu_speed(machine.handle,args.speed)
        machine.call('enable_audio',int(args.audio))
        buffer=(C.c_uint32*64000)();audio=(C.c_float*960)();width=C.c_uint32();height=C.c_uint32()
        for phase in ['idle','arrow-turn','walk','mouse-turn','interaction']:
            before=machine.snapshot();old_page=page(machine);switches=[];costs=[]
            if phase in ['arrow-turn','walk']:machine.call('key',0,0x4d if phase=='arrow-turn' else 0x48,1)
            if phase=='interaction':machine.call('key',0,0x1d,1)
            for frame in range(args.seconds*50):
                if phase=='mouse-turn':machine.call('mouse',3 if frame%100<50 else -3,0,0)
                if phase=='interaction' and frame%50==0:machine.call('key',32,0x39,1)
                if phase=='interaction' and frame%50==5:machine.call('key',0,0x39,0)
                cost=0
                for sub in range(20):
                    t=time.perf_counter_ns();machine.call('run_cycles',4773);cost+=time.perf_counter_ns()-t
                    machine.check();new_page=page(machine)
                    if new_page!=old_page:switches.append((machine.snapshot().cycles-before.cycles)/CLOCK);old_page=new_page
                t=time.perf_counter_ns();machine.call('copy_pixels',buffer,len(buffer),C.byref(width),C.byref(height))
                if args.audio:machine.call('read_audio',audio,960)
                cost+=time.perf_counter_ns()-t;costs.append(cost/1e6)
            for scan in [0x4d,0x48,0x1d,0x39]:machine.call('key',0,scan,0)
            after=machine.snapshot();elapsed=(after.cycles-before.cycles)/CLOCK
            result['phases'][phase]={'guest_seconds':elapsed,'instructions':after.instructions-before.instructions,
                'vga_page_switches':len(switches),'page_switches_per_guest_second':len(switches)/elapsed,
                'core_and_framebuffer_ms_per_20ms':{'median':statistics.median(costs),'p95':sorted(costs)[int(len(costs)*.95)],'max':max(costs)},
                'page_switch_times':switches,'frame_sha256':sha(bytes(buffer)),
                'diagnostic':after.message.decode()}
            machine.capture(args.output/(phase+'.png'))
        result['passed']=True
    finally:
        machine.close();(args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({name:{k:v for k,v in data.items() if k in ['page_switches_per_guest_second','core_and_framebuffer_ms_per_20ms']} for name,data in result['phases'].items()},indent=2))


if __name__=='__main__':main()
