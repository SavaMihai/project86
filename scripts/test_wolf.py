#!/usr/bin/env python3
"""Reproducible game interaction using user-supplied files and our own core.

This is an integration capture, not a claim that every game path is compatible.
Review the generated PNGs and WAV alongside report.json.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import wave
from disk_image import FATVolume,create_hard_disk
from p86 import Machine,ROOT
from prepare_guests import prepare

def digest(data): return hashlib.sha256(data).hexdigest()
def hud_fields(machine):
    width=C.c_uint32();height=C.c_uint32();pixels=(C.c_uint32*64000)()
    assert machine.call('copy_pixels',pixels,len(pixels),C.byref(width),C.byref(height))==64000
    data=bytes(pixels)
    # Fixed numeric HUD regions (floor/score/lives and health/ammo), excluding
    # the animated face and weapon. A changed/dead player must not pass reload.
    return b''.join(data[(y*320+x)*4:(y*320+end)*4]
                    for y in range(176,196) for x,end in [(0,120),(175,240)])
def saved_view(machine):
    width=C.c_uint32();height=C.c_uint32();pixels=(C.c_uint32*64000)()
    assert machine.call('copy_pixels',pixels,len(pixels),C.byref(width),C.byref(height))==64000
    data=bytes(pixels)
    # This controlled save faces a closed door. Exclude the weapon and HUD,
    # but require the world view to finish loading/fading before sending input.
    return b''.join(data[(y*320+40)*4:(y*320+280)*4] for y in range(20,100))
def start(boot,disk,cpu_speed=1):
    m=Machine(boot,disk,writable=True,cpu_speed=cpu_speed)
    m.type('c:\rcd wolf\rwolf3d\r')
    m.seconds(10);m.key(0x39,32,.3)
    if cpu_speed==1:
        m.seconds(10);m.key(0x39,32,.3);m.seconds(20)
    else:
        # At faster CPU rates the rating screen expires before the old second
        # Space press; that press opened the menu and sent later inputs to Help.
        m.seconds(20)
    return m

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path,help='User-supplied Wolfenstein 3D shareware v1.4 files')
    parser.add_argument('--output',type=Path,default=ROOT/'.build/wolf-check')
    parser.add_argument('--cpu-speed',type=int,choices=[1,4,8,16],default=1)
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Choose a fresh output directory; existing disks are never overwritten.')
    files={'WOLF/'+p.name.upper():p.read_bytes() for p in args.directory.iterdir() if p.is_file() and not p.name.startswith('.')}
    if 'WOLF/WOLF3D.EXE' not in files: raise SystemExit('WOLF3D.EXE not found')
    args.output.mkdir(parents=True)
    (args.output/'inputs.json').write_text(json.dumps({name:{'bytes':len(data),'sha256':digest(data)} for name,data in files.items()},indent=2)+'\n')
    disk=args.output/'wolf.img';disk.write_bytes(create_hard_disk(files).image)
    packaged=prepare();boot=args.output/'boot.ima';boot.write_bytes(packaged.read_bytes())
    m=start(boot,disk,args.cpu_speed)
    try:
        m.capture(args.output/'title.png')
        m.key(1,27,.3);m.seconds(20);m.key(0x31,ord('n'),.3);m.seconds(1)
        for _ in range(3): m.key(0x1c,13,.3);m.seconds(12)
        m.capture(args.output/'new-game.png');m.call('enable_audio',1)
        m.key(0x48,0,2);m.capture(args.output/'walk.png')
        m.key(0x1d,0,1);m.capture(args.output/'fire.png')
        saved_hud=hud_fields(m)
        saved_world=saved_view(m)
        sound=(C.c_float*48000)();count=m.call('read_audio',sound,len(sound))
        peak=max(abs(v) for v in sound);assert peak>0.01 and count==48000
        with wave.open(str(args.output/'audio.wav'),'wb') as output:
            output.setparams((1,2,48000,0,'NONE','not compressed'))
            output.writeframes(struct.pack('<'+'h'*count,*[max(-32768,min(32767,int(v*32767))) for v in sound[:count]]))
        m.key(0x3c);m.seconds(20);m.capture(args.output/'save-menu.png')
        m.key(0x1c,13);m.seconds(5)
        for scan,ch in [(0x19,'p'),(9,'8'),(7,'6')]:m.key(scan,ord(ch))
        m.key(0x1c,13);m.seconds(1);assert m.call('flush_disks')
    finally: m.close()
    saved=FATVolume(disk.read_bytes()).read('WOLF/SAVEGAM0.WL1')
    assert saved.startswith(b'p86\0') and len(saved)>1000
    m=start(boot,disk,args.cpu_speed)
    try:
        m.key(1,27);m.seconds(20);m.key(0x26,ord('l'));m.key(0x1c,13);m.seconds(20)
        m.capture(args.output/'load-menu.png');m.key(0x1c,13,.3)
        # Wait for the palette fade to settle, not an arbitrary long delay
        # that lets enemies kill the restored player before verification.
        for _ in range(100 if args.cpu_speed>1 else 300):
            m.seconds(.1)
            if hud_fields(m)==saved_hud and saved_view(m)==saved_world:break
        m.capture(args.output/'loaded.png')
        assert hud_fields(m)==saved_hud, 'Reload did not restore the saved numeric HUD'
        assert saved_view(m)==saved_world, 'Reload did not restore the saved world view'
        m.seconds(.1)
        m.key(0x4d,0,1);m.seconds(1);m.capture(args.output/'loaded-turn.png')
        m.call('mouse',20,0,0);m.seconds(2);m.capture(args.output/'loaded-mouse.png')
        assert (args.output/'loaded-turn.png').read_bytes()!=(args.output/'loaded-mouse.png').read_bytes()
        m.check();assert m.call('flush_disks')
    finally: m.close()
    report={'version':'Wolfenstein 3D DOS shareware v1.4 (verify input hashes)','cpu_speed':args.cpu_speed,
            'execution':'Project86 headless native ARM interpreter; no reference emulator',
            'actions':['new Episode 1 game','walk','fire','save p86','destroy machine','boot DOS again','load p86','turn','serial mouse movement'],
            'save_bytes':len(saved),'save_sha256':digest(saved),'audio_samples':count,'audio_peak':peak,
            'saved_numeric_hud_restored':True,
            'saved_world_view_restored':True,
            'visual_review':'Review title, gameplay and load-menu captures; image change alone is not a compatibility oracle.',
            'limitations':['No physical iPad test','No end-to-end macOS UI automation','Approximate timing and FM synthesis','Short gameplay sample only']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Game interaction capture finished:',args.output)
if __name__=='__main__':main()
