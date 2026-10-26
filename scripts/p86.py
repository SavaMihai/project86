"""Small ctypes client for this repository's own core, used by integration checks."""
import ctypes as C
from pathlib import Path
import struct
import zlib
from hardware_tests import CPU
ROOT = Path(__file__).resolve().parents[1]
class Snapshot(C.Structure):
    _fields_ = [('cpu',CPU),('instructions',C.c_uint64),('cycles',C.c_uint64),('status',C.c_int),('video_mode',C.c_uint8),('reserved',C.c_uint8*3),('message',C.c_char*256)]
class Machine:
    def __init__(self, floppy, hard=None, writable=False, library=None, cpu_speed=1):
        self.lib=C.CDLL(str(library or ROOT/'.build/libproject86.dylib'))
        signatures={
            'create':([],C.c_void_p),'destroy':([C.c_void_p],None),
            'set_cpu286':([C.c_void_p,C.c_int],None),'boot':([C.c_void_p],C.c_int),
            'attach_floppy':([C.c_void_p,C.c_char_p,C.c_int],C.c_int),'attach_hard_disk':([C.c_void_p,C.c_char_p,C.c_int],C.c_int),
            'run':([C.c_void_p,C.c_uint64],C.c_int),'run_cycles':([C.c_void_p,C.c_uint64],C.c_int),
            'get_snapshot':([C.c_void_p,C.POINTER(Snapshot)],None),'key':([C.c_void_p,C.c_uint8,C.c_uint8,C.c_int],None),
            'mouse':([C.c_void_p,C.c_int,C.c_int,C.c_uint8],None),'flush_disks':([C.c_void_p],C.c_int),
            'enable_audio':([C.c_void_p,C.c_int],None),'read_audio':([C.c_void_p,C.POINTER(C.c_float),C.c_size_t],C.c_size_t),
            'copy_text':([C.c_void_p,C.POINTER(C.c_uint8),C.c_size_t],C.c_size_t),
            'copy_pixels':([C.c_void_p,C.POINTER(C.c_uint32),C.c_size_t,C.POINTER(C.c_uint32),C.POINTER(C.c_uint32)],C.c_size_t),
            'read_memory':([C.c_void_p,C.c_uint32],C.c_uint8)
        }
        for name,(args,result) in signatures.items():
            f=getattr(self.lib,'p86_'+name);f.argtypes=args;f.restype=result
        self.handle=self.lib.p86_create()
        if not self.handle: raise MemoryError()
        self.call('set_cpu286',1)
        if cpu_speed!=1:
            self.lib.p86_set_cpu_speed.argtypes=[C.c_void_p,C.c_uint32]
            self.lib.p86_set_cpu_speed.restype=None
            self.call('set_cpu_speed',cpu_speed)
        if hard: assert self.call('attach_hard_disk',str(hard).encode(),writable)
        assert self.call('attach_floppy',str(floppy).encode(),writable)
        assert self.call('boot')
    def call(self,name,*args): return getattr(self.lib,'p86_'+name)(self.handle,*args)
    def close(self):
        if self.handle: self.call('destroy');self.handle=None
    def snapshot(self):
        s=Snapshot();self.call('get_snapshot',C.byref(s));return s
    def check(self):
        s=self.snapshot()
        if s.status==3: raise RuntimeError(s.message.decode())
        return s
    def text(self):
        data=(C.c_uint8*4000)();self.call('copy_text',data,4000)
        return '\n'.join(bytes(data[r*160:r*160+160:2]).decode('cp437').rstrip() for r in range(25))
    def type(self,text):
        for ch in text:
            for _ in range(10000):
                result=self.call('run',10000);self.check()
                if result==2: break
            else: raise RuntimeError('Guest did not request keyboard input')
            self.call('key',ord(ch),0x1c if ch=='\r' else 0,1)
    def seconds(self,value):
        for _ in range(round(value*50)):
            self.call('run_cycles',95455);self.check()
    def key(self,scan,ascii=0,hold=0.1):
        self.call('key',ascii,scan,1);self.seconds(hold);self.call('key',0,scan,0);self.seconds(.1)
    def capture(self,path):
        w=C.c_uint32();h=C.c_uint32();n=self.call('copy_pixels',None,0,C.byref(w),C.byref(h))
        if not n: Path(path).with_suffix('.txt').write_text(self.text());return
        data=(C.c_uint32*n)();self.call('copy_pixels',data,n,C.byref(w),C.byref(h))
        pixels=bytes(data);raw=b''.join(b'\0'+pixels[y*w.value*4:(y+1)*w.value*4] for y in range(h.value))
        def chunk(name,data): return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data))
        Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',w.value,h.value,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
    def debug(self):
        s=self.check();c=s.cpu
        code=bytes(self.call('read_memory',(c.cs<<4)+((c.ip+i)&65535)) for i in range(32))
        print(f'{c.cs:04x}:{c.ip:04x} AX={c.ax:04x} BX={c.bx:04x} CX={c.cx:04x} DX={c.dx:04x} FLAGS={c.flags:04x} cycles={s.cycles} instructions={s.instructions}',code.hex(' '),flush=True)
