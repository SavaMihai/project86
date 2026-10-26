#!/usr/bin/env python3
"""Exercise COMMAND.COM editing and execution using real guest keyboard input."""
import argparse
import ctypes as C
import json
from pathlib import Path
import subprocess
from disk_image import FATVolume, create_floppy, create_hard_disk
from dos_artifacts import ROOT, DEFAULT_BUILD, load_build, sha
from p86 import Machine


class Session:
    def __init__(self, binaries, directory, extra=None, cpu_speed=1):
        directory.mkdir();self.directory=directory
        files={name:data for name,data in binaries.items() if name!='BOOT.BIN'}
        files['CONFIG.SYS']=b'FILES=64\r\nBUFFERS=20\r\nLASTDRIVE=Z\r\n'
        files['AUTOEXEC.BAT']=b'@echo off\r\nprompt P86$G\r\n'
        self.floppy=directory/'boot.ima';self.hard=directory/'working.img'
        self.floppy.write_bytes(create_floppy(binaries['BOOT.BIN'],files).image)
        self.hard.write_bytes(create_hard_disk(extra or {}).image)
        self.m=Machine(self.floppy,self.hard,True,cpu_speed=cpu_speed);self.m.seconds(2)
    def send(self,s):self.m.type(s);self.m.seconds(.8)
    def key(self,scan,ascii=0):self.m.key(scan,ascii,hold=.02);self.m.seconds(.5)
    def line(self):
        cells=(C.c_uint8*4000)();self.m.call('copy_text',cells,4000)
        text=bytes(cells)[::2].decode('cp437')
        row=self.m.call('read_memory',0x451);col=self.m.call('read_memory',0x450)
        end=row*80+col;start=text.rfind('P86>',0,end)
        assert start>=0, self.m.text()
        return text[start+4:end]
    def expect(self,text):assert self.line()==text,(repr(self.line()),repr(text),self.m.text())
    def clear(self):self.key(1,27)
    def files(self):
        assert self.m.call('flush_disks');return FATVolume(self.hard.read_bytes())
    def close(self):
        (self.directory/'screen.txt').write_text(self.m.text()+'\n')
        self.m.call('flush_disks');self.m.close()


def editing(binaries,out,clobber,cpu_speed=1):
    s=Session(binaries,out,{'CLOBBER.COM':clobber,
                          'HISTORY.BAT':b'@echo off\r\necho batch-history-excluded\r\n'},cpu_speed=cpu_speed); checks=[]
    try:
        s.key(0x48);s.expect('');checks.append('empty history; AUTOEXEC excluded')
        s.send('echo first\r');s.send('echo second\r')
        s.key(0x48);s.expect('echo second');s.key(0x48);s.expect('echo first')
        s.key(0x48);s.expect('echo first');s.key(0x50);s.expect('echo second')
        s.key(0x50);s.expect('');checks.append('Up/Down bounds')
        s.key(0x48);s.key(0x48);s.clear();s.key(0x48);s.expect('echo second');s.clear()
        checks.append('Escape resets history navigation')
        s.send('echo draft');s.key(0x4b);s.key(0x48);s.expect('echo second')
        s.key(0x50);s.expect('echo draf');s.key(0x4f);s.expect('echo draft')
        checks.append('unfinished draft and cursor restored');s.clear()
        s.key(0x48);s.send(' changed');s.key(0x1c,13)
        s.key(0x48);s.expect('echo second changed');s.key(0x48);s.expect('echo second')
        checks.append('editing recalled command does not mutate history');s.clear()
        s.send('echo second changed\r');s.key(0x48);s.key(0x48);s.expect('echo second')
        checks.append('consecutive duplicate suppression');s.clear()
        s.send('   \r');s.key(0x48);s.expect('echo second changed');checks.append('blank lines excluded');s.clear()
        s.send('echo abc');s.key(0x4b);s.send('X');s.key(0x4f);s.expect('echo abXc')
        s.key(0x4b);s.key(0x53);s.expect('echo abX');s.key(0x0e,8);s.expect('echo ab')
        s.key(0x47);s.key(0x52);s.send('E');s.key(0x4f);s.expect('Echo ab')
        checks.append('Left Right Home End Insert Delete Backspace');s.clear()
        s.key(0x3d);s.expect('echo second changed');s.clear();s.key(0x3b);s.expect('e')
        checks.append('F1 and F3 template recall');s.clear()
        s.key(0x3c);s.send('s');s.expect('echo ');checks.append('F2 template prefix');s.clear()
        s.send('echo remove keep');s.key(0x47)
        for _ in range(5):s.key(0x4d)
        s.key(0x3e);s.send('k');s.key(0x4f);s.expect('echo keep');checks.append('F4 delete to character');s.clear()
        s.send('echo template');s.key(0x3f)
        row=s.m.call('read_memory',0x451)
        assert s.m.text().splitlines()[row]==''
        s.key(0x3d);assert s.m.text().splitlines()[row]=='echo template'
        checks.append('F5 updates template without execution');s.clear();s.key(0x1c,13)
        s.key(0x40);s.expect('^Z');s.clear();checks.append('F6 control-Z display')
        # Ctrl-C must abandon a pending command and not commit it to history.
        s.send('echo should-not-run');s.key(0x2e,3);s.m.seconds(.2);s.expect('')
        s.key(0x48);s.expect('echo second changed');s.clear();checks.append('Ctrl-C cancellation')
        s.send('c:\\clobber\r');s.m.seconds(2);assert 'TRANSIENT CLOBBERED' in s.m.text()
        s.key(0x48);s.expect('c:\\clobber');s.key(0x48);s.expect('echo second changed');s.clear()
        checks.append('history survives external program and transient reload')
        s.send('c:\\history\r');s.key(0x48);s.expect('c:\\history')
        s.key(0x48);s.expect('c:\\clobber');s.clear();checks.append('batch lines excluded')
        s.send('command\r');s.key(0x48);s.expect('')
        s.send('echo nested-shell\r');s.send('exit\r')
        s.key(0x48);s.expect('command');s.key(0x48);s.expect('c:\\history');s.clear()
        checks.append('nested shells keep independent history')
        for i in range(20):s.send(f'rem hist{i:02}\r')
        for _ in range(20):s.key(0x48)
        s.expect('rem hist04');checks.append('16-entry ring eviction')
        for _ in range(20):s.key(0x50)
        s.expect('')
        # Force bottom-row wrapping and compare all visible bytes at the prompt.
        line='rem '+('x'*123);s.send(line+'ignored');s.expect(line)
        s.key(0x0e,8);s.send('Y');s.expect(line[:-1]+'Y')
        s.key(0x1c,13);s.key(0x48);s.expect(line[:-1]+'Y');s.clear();s.expect('')
        cells=(C.c_uint8*4000)();s.m.call('copy_text',cells,4000)
        screen=bytes(cells)[::2].decode('cp437');assert not screen[screen.rfind('P86>')+4:].strip()
        checks.append('127-byte bound, wrapped redraw and scroll')
    finally:s.close()
    return checks


def completion(binaries,out,cpu_speed=1):
    files={'ALPHA.TXT':b'alpha\r\n','ALPINE.TXT':b'alpine\r\n','OTHER.BIN':b'other',
           'SUBDIR/INNER.TXT':b'inner\r\n','SUBDIR/SECOND.TXT':b'second\r\n'}
    s=Session(binaries,out,files,cpu_speed=cpu_speed);checks=[]
    try:
        s.send('type c:\\al');s.key(0x0f,9);s.expect('type c:\\ALPHA.TXT')
        s.key(0x0f,9);s.expect('type c:\\ALPINE.TXT');s.key(0x0f,9);s.expect('type c:\\ALPHA.TXT')
        s.key(0x1c,13);assert 'alpha' in s.m.text();checks.append('case-insensitive prefix, cycling, wrap and execution')
        s.send('type c:\\sub');s.key(0x0f,9);s.expect('type c:\\SUBDIR')
        s.send('\\in');s.key(0x0f,9);s.expect('type c:\\SUBDIR\\INNER.TXT')
        s.key(0x1c,13);assert 'inner' in s.m.text();checks.append('explicit directory separator and nested path')
        s.send('c:\r');s.send('type al');s.key(0x0f,9);s.expect('type ALPHA.TXT');s.clear()
        s.send('type c:al');s.key(0x0f,9);s.expect('type c:ALPHA.TXT');s.clear()
        s.send('type .\\al');s.key(0x0f,9);s.expect('type .\\ALPHA.TXT');s.clear()
        s.send('type ALPHA.T');s.key(0x0f,9);s.expect('type ALPHA.TXT');s.clear()
        checks.append('current directory, drive-relative, explicit relative and extension prefixes')
        s.send('echo keep>al');s.key(0x0f,9);s.expect('echo keep>ALPHA.TXT');s.key(0x1c,13)
        assert s.files().read('ALPHA.TXT')==b'keep\r\n';checks.append('redirection target completion')
        s.send('copy al other.bin');s.key(0x47)
        for _ in range(7):s.key(0x4d)
        s.key(0x0f,9);s.key(0x4f);s.expect('copy ALPHA.TXT other.bin');s.clear()
        s.send('type alzz');s.key(0x4b);s.key(0x4b);s.key(0x0f,9);s.expect('type ALPHA.TXT');s.clear()
        checks.append('completion preserves later arguments and replaces token remainder')
        s.send('type no_match');s.key(0x0f,9);s.expect('type no_match');s.clear()
        for text in ['type *.txt','type "al','type subdir\\..\\no_match']:
            s.send(text);s.key(0x0f,9);s.expect(text);s.clear()
        checks.append('no-match, wildcard and quote inputs remain intact')
        # Completion expansion must reject a result exceeding the DOS buffer.
        prefix='rem '+('x'*118)+' ';s.send(prefix+'al');s.key(0x0f,9);s.expect(prefix+'al');s.clear()
        checks.append('completion overflow preserves original line')
        s.send('break on\r');s.send('type al')
        s.m.call('key',9,0x0f,1);s.m.call('key',3,0x2e,1);s.m.seconds(2)
        s.expect('');s.send('break off\r');checks.append('Ctrl-C during completion with BREAK ON')
        s.send('dir > c:\\files.txt\r');s.m.seconds(4);data=s.files().read('FILES.TXT')
        assert b'ALPHA' in data and b'SUBDIR' in data;checks.append('search DTA restored before next command')
    finally:s.close()
    return checks


def directories(binaries,out,cpu_speed=1):
    """Execute completed paths; matching the edited line alone missed DOS CD's rules."""
    s=Session(binaries,out,{'SUBDIR/INNER/FILE.TXT':b'nested\r\n',
                          'SUBTWO/FILE.TXT':b'second\r\n','SETUP.V1/FILE.TXT':b'dotted\r\n'},cpu_speed=cpu_speed)
    checks=[]
    def cwd(expected):
        s.send('cd > c:\\cwd.txt\r')
        assert s.files().read('CWD.TXT')==expected.encode()+b'\r\n'
    try:
        s.send('c:\r');s.send('cd su');s.key(15,9);s.expect('cd SUBDIR')
        s.key(15,9);s.expect('cd SUBTWO');s.key(15,9);s.expect('cd SUBDIR')
        s.key(0x1c,13);cwd('C:\\SUBDIR');checks.append('CD executes completed directory after cycling')
        s.send('cd \\\r');cwd('C:\\')
        s.send('cHdIr c:\\su');s.key(15,9);s.expect('cHdIr c:\\SUBDIR')
        s.key(0x1c,13);cwd('C:\\SUBDIR');checks.append('CHDIR executes completed absolute path')
        s.send('cd in');s.key(15,9);s.expect('cd INNER');s.key(0x1c,13)
        cwd('C:\\SUBDIR\\INNER');s.send('cd \\\r')
        s.send('cd su');s.key(15,9);s.send('\\in');s.key(15,9)
        s.expect('cd SUBDIR\\INNER');s.key(0x1c,13);cwd('C:\\SUBDIR\\INNER')
        checks.append('nested relative paths and explicit separator after completion')
        s.send('cd \\\r');s.send('cd se');s.key(15,9);s.expect('cd SETUP.V1')
        s.key(0x1c,13);cwd('C:\\SETUP.V1');s.send('cd \\\r')
        checks.append('directory name containing an extension')
        s.send('dir c:\\su');s.key(15,9);s.send(' > c:\\listing.txt\r');s.m.seconds(4)
        assert b'INNER' in s.files().read('LISTING.TXT');checks.append('DIR accepts completed directory')
        s.send('md c:\\empty\r');s.send('rd c:\\em');s.key(15,9);s.expect('rd c:\\EMPTY')
        s.key(0x1c,13)
        try:s.files().find('EMPTY')
        except FileNotFoundError:pass
        else:raise AssertionError('RD did not remove completed directory')
        checks.append('RD accepts completed empty directory')
        cwd('C:\\');checks.append('root separator remains valid')
    finally:s.close()
    return checks


def execution(binaries,out,cpu_speed=1):
    files={'INPUT.TXT':b'beta\r\nalpha\r\n','RUN.BAT':b'@echo off\r\necho batch one>c:\\batch.txt\r\nfor %%x in (A B) do echo %%x>>c:\\batch.txt\r\nif exist c:\\batch.txt echo batch two>>c:\\batch.txt\r\n',
           'STDIN.TXT':b'echo redirected>c:\\stdin.out\r\nexit\r\n',
           'STDIN2.TXT':b'echo input-only>c:\\stdin2.out\r\nexit\r\n'}
    s=Session(binaries,out,files,cpu_speed=cpu_speed)
    try:
        for command in ['c:\\run','command /c echo child>c:\\child.txt',
                        'type c:\\input.txt | sort > c:\\sorted.txt',
                        'command < c:\\stdin.txt > c:\\console.txt',
                        'command < c:\\stdin2.txt',
                        'command > c:\\stdout.txt','echo output-only>c:\\stdout.out','exit',
                        'ver > c:\\ver.txt','dir c:\\ > c:\\dir.txt']:
            s.send(command+'\r')
        s.m.seconds(5)
        volume=s.files();result={name:volume.read(name) for name in ['BATCH.TXT','CHILD.TXT','SORTED.TXT','STDIN.OUT','STDIN2.OUT','STDOUT.OUT','VER.TXT','DIR.TXT']}
        assert result['BATCH.TXT']==b'batch one\r\nA\r\nB\r\nbatch two\r\n',result
        assert result['CHILD.TXT']==b'child\r\n'
        assert result['SORTED.TXT']==b'alpha\r\nbeta\r\n'
        assert result['STDIN.OUT']==b'redirected\r\n'
        assert result['STDIN2.OUT']==b'input-only\r\n' and result['STDOUT.OUT']==b'output-only\r\n'
        assert b'MS-DOS Version 4.00 (Project86 - built from source)' in result['VER.TXT']
        return {name:sha(data) for name,data in result.items()}
    finally:s.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dos-build',type=Path,default=DEFAULT_BUILD)
    parser.add_argument('--cpu-speed',type=int,choices=[1,4,8,16],default=1)
    parser.add_argument('--baseline',type=Path,default=ROOT/'.build/dos-original-libraries')
    parser.add_argument('--command',type=Path,help='Development-only candidate COMMAND.COM before a full provenance build')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    binaries,record=load_build(args.dos_build)
    if args.command:binaries['COMMAND.COM']=args.command.read_bytes()
    baseline,old_record=load_build(args.baseline)
    args.output.mkdir(parents=True,exist_ok=False)
    program=args.output/'CLOBBER.COM'
    subprocess.run(['nasm','-f','bin',str(ROOT/'tests/guests/command_clobber.asm'),'-o',str(program)],check=True)
    report={'passed':False,'cpu_speed':args.cpu_speed,'build':record,'baseline':old_record,'command_sha256':sha(binaries['COMMAND.COM']),
            'development_override':str(args.command) if args.command else None}
    try:
        report['editing']=editing(binaries,args.output/'editing',program.read_bytes(),args.cpu_speed)
        report['completion']=completion(binaries,args.output/'completion',args.cpu_speed)
        report['directories']=directories(binaries,args.output/'directories',args.cpu_speed)
        report['execution_original']=execution(baseline,args.output/'execution-original',args.cpu_speed)
        report['execution_candidate']=execution(binaries,args.output/'execution-candidate',args.cpu_speed)
        assert report['execution_original']==report['execution_candidate'], 'Execution differs from baseline'
        report['passed']=True
    finally:(args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('COMMAND.COM guest tests passed:',args.output)


if __name__=='__main__':main()
