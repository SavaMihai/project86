#!/usr/bin/env python3
"""Run original/replacement CASSFAR probes and actual SELECT installations.

Only fresh private disks are writable. SELECT, DOS, DISKCOPY and all file
operations execute as guest programs in Project86's own interpreter.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import struct
import subprocess
from disk_image import FATVolume, create_floppy, create_hard_disk, u16
from dos_artifacts import ROOT, DEFAULT_BUILD, CASSFAR_SOURCE, ORIGINAL_LIBRARIES, load_build, sha
from p86 import Machine

KEYS = bytes([13,27,0,59,0,67,65,97])
QUERIES = [*range(256), *(scan << 8 for scan in range(1,90))]


def key_result(value):
    i = 0
    while i < len(KEYS):
        start = i; key = KEYS[i]; i += 1
        if not key: key = KEYS[i] << 8; i += 1
        if key == value: return start + 1
    return 0


def parse_probe(data):
    assert data[:4] == b'CAS1'
    keys_end = 89 + len(QUERIES)*2
    keys = list(struct.unpack_from('<' + str(len(QUERIES)) + 'H', data, 89))
    assert keys == [key_result(k) for k in QUERIES]
    at = keys_end; helps = []
    for ident in range(1,58):
        h = struct.unpack_from('<4H', data, at); at += 8
        assert h[0] == ident and h[1:3] == (0,0), h
        text = data[at:at+h[3]]; at += h[3]
        lines, error = struct.unpack_from('<2H', data, at); at += 4
        assert error == 0 and 0 < lines*54 <= 8192, (ident, lines, error)
        wrapped = data[at:at+lines*54]; at += len(wrapped)
        helps.append({'id':ident,'source_text_sha256':sha(text),'wrapped_sha256':sha(wrapped),'lines':lines})
    assert at == len(data), (at,len(data))
    return data[4:89], helps


def make_boot(binaries):
    files = {name:data for name,data in binaries.items() if name != 'BOOT.BIN'}
    files['CONFIG.SYS'] = b'FILES=64\r\nBUFFERS=20\r\nLASTDRIVE=C\r\n'
    files['AUTOEXEC.BAT'] = b'@echo off\r\n'
    return bytes(create_floppy(binaries['BOOT.BIN'],files).image)


def probes(baseline, build, original, candidate, output):
    output.mkdir()
    guest = FATVolume((baseline/'source.img').read_bytes())
    guest.put('PROBE.ASM',(CASSFAR_SOURCE/'probe.asm').read_bytes())
    library = FATVolume((build/'source.img').read_bytes()).read('SRC/SELECT/CASSFAR.LIB')
    guest.put('NEW.LIB',library)
    cases = ['keystext db '+','.join(str(b) for b in KEYS),'cases label word']
    cases += [f'dw 1,{k},0,0,{len(KEYS)},offset keystext,0' for k in QUERIES]
    cases += [f'case_count equ {len(QUERIES)}']
    guest.put('CASES.INC',('\r\n'.join(cases)+'\r\n').encode())
    commands = ['@echo off','c:','cd \\src','call setenv.bat','cd \\',
                'masm -Mx -t probe.asm; > c:\\probe.log','if errorlevel 1 goto bad',
                'link probe.obj,oldprob.exe,,c:\\src\\select\\cassfar.lib; >> c:\\probe.log','if errorlevel 1 goto bad',
                'link probe.obj,newprob.exe,,new.lib; >> c:\\probe.log','if errorlevel 1 goto bad',
                'oldprob > old.bin','if errorlevel 1 goto bad','newprob > new.bin','if errorlevel 1 goto bad',
                'echo P86 PROBE SUCCEEDED','goto end',':bad','echo P86 PROBE FAILED',':end']
    guest.put('RUN.BAT',('\r\n'.join(commands)+'\r\n').encode())
    hard = output/'source.img'; hard.write_bytes(guest.image)
    floppy = output/'boot.ima'; floppy.write_bytes(make_boot(original))
    with (output/'screen.txt').open('w') as out,(output/'progress.log').open('w') as err:
        result = subprocess.run([str(ROOT/'.build/p86'),'--disk',str(floppy),'--hard-disk',str(hard),
                                 '--write','--command','c:\\run','--until','P86 PROBE',
                                 '--limit','1000000000'],stdout=out,stderr=err,timeout=120)
    guest = FATVolume(hard.read_bytes());(output/'PROBE.LOG').write_bytes(guest.read('PROBE.LOG'))
    assert not result.returncode and 'P86 PROBE SUCCEEDED' in (output/'screen.txt').read_text()
    a,b = guest.read('OLD.BIN'),guest.read('NEW.BIN')
    (output/'original.bin').write_bytes(a);(output/'replacement.bin').write_bytes(b)
    va,ha = parse_probe(a); vb,hb = parse_probe(b)
    assert ha == hb and a[89:] == b[89:]
    # The new library reports the BIOS-declared VGA, not phantom PGA/MDA
    # adapters detected by the original's speculative I/O probes. It also
    # supplies character/cursor width and current attribute instead of zero.
    differences = {i for i in range(85) if va[i] != vb[i]}
    original_library = sha(library) == ORIGINAL_LIBRARIES['SRC/SELECT/CASSFAR.LIB']
    if original_library:
        assert va == vb, 'Original-library video metadata changed'
    else:
        assert differences <= {0,30,74,76}, differences
        assert struct.unpack_from('<H',vb,0)[0] == 0x2024 and vb[30] == 8
    assert struct.unpack_from('<HH',vb,4) == (160,4000) and vb[9] == 3
    assert struct.unpack_from('<H',vb,18)[0] == 0xb800
    return {'passed':True,'key_search_cases':len(QUERIES),'help_topics':len(ha),
            'all_help_text_and_wrapped_bytes_equal':True,'help_records':ha,
            'video_geometry_equal':True,'video_intentional_changed_offsets':sorted(differences),
            'video_difference_reason':('Original video metadata preserved' if original_library else
                                       'BIOS-declared VGA capabilities and explicit character/cursor metadata'),
            'original_probe_sha256':sha(a),'replacement_probe_sha256':sha(b)}


def capture(machine, path):
    machine.seconds(.6)
    text = machine.text();path.with_suffix('.txt').write_text(text+'\n')
    data = (C.c_uint8*4000)();machine.call('copy_text',data,4000)
    path.with_suffix('.cells').write_bytes(bytes(data))
    return text, bytes(data)


def navigation(binaries, output):
    output.mkdir();(output/'boot.ima').write_bytes(make_boot(binaries))
    (output/'hard.img').write_bytes(create_hard_disk({'KEEP.TXT':b'private SELECT target\r\n'}).image)
    m=Machine(output/'boot.ima',output/'hard.img',True);screens={}
    try:
        m.type('select.exe menu\r');m.seconds(.6)
        for name in ['welcome','introduction','workspace']:
            screens[name]=capture(m,output/name)
            if name!='workspace':m.key(0x1c,13)
        m.key(0x50);screens['workspace-down']=capture(m,output/'workspace-down')
        m.key(0x50);screens['workspace-wrap-down']=capture(m,output/'workspace-wrap-down')
        m.key(0x48);screens['workspace-wrap-up']=capture(m,output/'workspace-wrap-up')
        m.key(0x48);screens['workspace-up']=capture(m,output/'workspace-up')
        m.key(0x3b);screens['help']=capture(m,output/'help')
        assert 'Help' in screens['help'][0]
        m.key(0x43);screens['help-keys']=capture(m,output/'help-keys')
        assert 'Key Assignments' in screens['help-keys'][0]
        m.key(0x51);screens['help-page-down']=capture(m,output/'help-page-down')
        m.key(0x49);screens['help-page-up']=capture(m,output/'help-page-up')
        m.key(1,27);capture(m,output/'help-back')
        # F9 help can return directly to the original panel or its help parent.
        if 'Specify Function and Workspace' not in m.text():m.key(1,27)
        screens['help-return']=capture(m,output/'help-return')
        assert 'Specify Function and Workspace' in screens['help-return'][0]
        m.key(0x3d);screens['cancel']=capture(m,output/'cancel')
        assert 'exit' in screens['cancel'][0].lower() or 'quit' in screens['cancel'][0].lower()
        m.key(1,27);capture(m,output/'cancel-return');assert m.call('flush_disks')
    finally:m.close()
    return screens


def file_tree(volume, cluster=0, prefix=''):
    result={}
    for e in volume.entries(cluster):
        attr=volume.image[e+11]
        if attr&8:continue
        base=bytes(volume.image[e:e+8]).decode('ascii').rstrip();ext=bytes(volume.image[e+8:e+11]).decode('ascii').rstrip()
        if base in ('.','..'):continue
        name=base+('.'+ext if ext else '');path=prefix+name
        if attr&16:result.update(file_tree(volume,u16(volume.image,e+26),path+'/'))
        else:result[path]={'sha256':sha(volume.read(path)),'bytes':len(volume.read(path))}
    return result


def review_parameters(binaries, output):
    output.mkdir();(output/'boot.ima').write_bytes(make_boot(binaries))
    (output/'hard.img').write_bytes(create_hard_disk({'KEEP.TXT':b'private review disk\r\n'}).image)
    m=Machine(output/'boot.ima',output/'hard.img',True);screens={}
    try:
        m.type('select.exe menu\r');m.seconds(1)
        for _ in range(12):
            if 'Installation Options' in m.text():break
            m.key(0x1c,13);m.seconds(.6)
        assert 'Installation Options' in m.text()
        m.key(3,ord('2'));m.key(0x1c,13)
        for name,title in [('dos-parameters','DOS Parameters'),('fastopen','FASTOPEN Parameters'),('configuration','Configuration Parameters')]:
            screens[name]=capture(m,output/name);assert title in screens[name][0]
            if name!='configuration':m.key(0x1c,13)
        assert m.call('flush_disks')
    finally:m.close()
    return screens


def missing_help(binaries, output):
    output.mkdir();(output/'boot.ima').write_bytes(make_boot(binaries))
    (output/'wrong.ima').write_bytes(create_floppy(binaries['BOOT.BIN'],{'IO.SYS':b'','MSDOS.SYS':b''}).image)
    (output/'hard.img').write_bytes(create_hard_disk({'KEEP.TXT':b'private error test\r\n'}).image)
    m=Machine(output/'boot.ima',output/'hard.img',True)
    try:
        m.type('select.exe menu\r');m.seconds(1)
        for _ in range(2):m.key(0x1c,13);m.seconds(.3)
        assert m.call('flush_disks') and m.call('attach_floppy',str(output/'wrong.ima').encode(),1)
        m.key(0x3b);result=capture(m,output/'missing-help')
        assert 'diskette' in result[0].lower(), 'Missing help did not produce an installer error'
        assert m.call('flush_disks')
    finally:m.close()
    return result


def installation(binaries, output):
    output.mkdir();source=output/'source.ima';copy_disk=output/'copy.ima';hard=output/'hard.img'
    source.write_bytes(make_boot(binaries));copy_disk.write_bytes(create_floppy(binaries['BOOT.BIN'],{'IO.SYS':b'','MSDOS.SYS':b''}).image)
    marker=b'preserve unrelated private test data\r\n';hard.write_bytes(create_hard_disk({'KEEP.TXT':marker}).image)
    m=Machine(source,hard,True);current=source;swaps=[];edited=False;complete=False;screens=[]
    try:
        m.type('select.exe menu\r');m.seconds(1)
        for step in range(65):
            text,_=capture(m,output/f'step-{step:02}');screens.append(text)
            if 'Installation Complete' in text:complete=True;break
            if 'Specify Function and Workspace' in text:m.key(0x02,ord('1'));m.seconds(.4)
            if 'MS-DOS Shell Option' in text:m.key(0x03,ord('2'));m.seconds(.4)
            if 'Specify DOS Location' in text and not edited:
                m.key(0x47)
                for _ in range(3):m.key(0x53)
                for scan,ch in [(0x19,'p'),(0x09,'8'),(0x07,'6'),(0x14,'t'),(0x12,'e'),(0x1f,'s'),(0x14,'t')]:m.key(scan,ord(ch))
                m.key(0x37,ord('*'))  # Not in the published path-field allow list.
                field,_=capture(m,output/'edited-directory');assert 'P86TEST' in field and 'P86TEST*' not in field
                edited=True
            disk=copy_disk if 'Insert the SELECT COPY diskette' in text else source if ('Insert the INSTALL diskette' in text or 'Insert OPERATING diskette' in text) else None
            if disk and disk!=current:
                assert m.call('flush_disks') and m.call('attach_floppy',str(disk).encode(),1)
                current=disk;swaps.append(disk.name)
            m.key(0x1c,13);m.seconds(.7)
        assert complete and edited, 'SELECT did not finish the private installation'
        assert m.call('flush_disks')
    finally:m.close()
    volume=FATVolume(hard.read_bytes());assert volume.read('KEEP.TXT')==marker
    assert volume.read('P86TEST/COMMAND.COM')==binaries['COMMAND.COM']
    assert volume.read('P86TEST/SELECT.EXE')==binaries['SELECT.EXE']
    config=volume.read('CONFIG.SYS');autoexec=volume.read('AUTOEXEC.BAT')
    assert b'C:\\P86TEST\\COMMAND.COM' in config and b'PATH C:\\P86TEST' in autoexec
    (output/'CONFIG.SYS').write_bytes(config);(output/'AUTOEXEC.BAT').write_bytes(autoexec)
    installed=file_tree(volume)
    for path, record in installed.items():
        if path.startswith('P86TEST/') and path[8:] in binaries:
            assert record['sha256'] == sha(binaries[path[8:]]), f'Installed artifact differs: {path}'
    # Reopen the persisted target and execute its installed COMMAND.COM.
    m=Machine(source,hard,True)
    try:
        m.type('c:\\p86test\\command.com /c ver > c:\\verify.txt\r');m.seconds(.5);assert m.call('flush_disks')
    finally:m.close()
    assert b'MS-DOS Version 4.00 (Project86 - built from source)' in FATVolume(hard.read_bytes()).read('VERIFY.TXT')
    return {'passed':True,'installer_announced_complete':True,'disk_swaps':swaps,
            'typed_directory':'C:\\P86TEST','invalid_path_character_rejected':True,
            'unrelated_file_preserved':True,'installed_files':installed,
            'config_sha256':sha(config),'autoexec_sha256':sha(autoexec),
            'installed_command_executed_after_restart':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path,default=ROOT/'.build/dos-second-generation')
    parser.add_argument('--dos-build',type=Path,default=DEFAULT_BUILD)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    old,old_record=load_build(args.baseline);new,new_record=load_build(args.dos_build)
    report={'schema':1,'baseline':old_record,'replacement':new_record,'passed':False}
    try:
        report['interfaces']=probes(args.baseline,args.dos_build,old,new,args.output/'interfaces')
        a=navigation(old,args.output/'navigation-original');b=navigation(new,args.output/'navigation-replacement')
        report['navigation']={name:{'text_equal':a[name][0]==b[name][0],
                                  'cells_equal':a[name][1]==b[name][1],
                                  'original_cells_sha256':sha(a[name][1]),'replacement_cells_sha256':sha(b[name][1])} for name in a}
        assert all(v['cells_equal'] for v in report['navigation'].values()), 'SELECT navigation cells differ'
        a=review_parameters(old,args.output/'review-original');b=review_parameters(new,args.output/'review-replacement')
        report['parameter_review']={name:{'cells_equal':a[name][1]==b[name][1],
                                         'original_sha256':sha(a[name][1]),'replacement_sha256':sha(b[name][1])} for name in a}
        assert all(v['cells_equal'] for v in report['parameter_review'].values()), 'SELECT parameter-review cells differ'
        a=missing_help(old,args.output/'error-original');b=missing_help(new,args.output/'error-replacement')
        assert a[1]==b[1], 'SELECT missing-help error screen differs'
        report['missing_help_error']={'cells_equal':True,'original_sha256':sha(a[1]),'replacement_sha256':sha(b[1])}
        report['installation_original']=installation(old,args.output/'installation-original')
        report['installation_replacement']=installation(new,args.output/'installation-replacement')
        a=report['installation_original']['installed_files'];b=report['installation_replacement']['installed_files']
        changed={name for name in set(a)|set(b) if a.get(name)!=b.get(name)}
        expected={'P86TEST/'+name for name in old if old[name]!=new[name] and 'P86TEST/'+name in a}
        assert changed==expected and set(a)==set(b), 'Unexpected installed file differences'
        report['installation_comparison']={'changed_files':sorted(changed),'identical_files':len(a)-len(changed),
                                          'installed_select_matches_each_build':True}
        report['passed']=True
    finally:(args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('CASSFAR/SELECT guest tests passed:',args.output)


if __name__=='__main__':main()
