#!/usr/bin/env python3
"""Native FAT12/16 image preparation and inspection; never executes guest code."""
import argparse
import math
from pathlib import Path, PurePosixPath
import struct
import zipfile

def u16(data, offset): return struct.unpack_from("<H", data, offset)[0]
def u32(data, offset): return struct.unpack_from("<I", data, offset)[0]
def w16(data, offset, value): struct.pack_into("<H", data, offset, value)
def w32(data, offset, value): struct.pack_into("<I", data, offset, value)

def dos_name(name):
    if name in (".", ".."):
        return name.ljust(11).encode("ascii")
    parts = name.upper().rsplit(".", 1)
    stem, ext = parts if len(parts) == 2 else (parts[0], "")
    if not stem or len(stem)>8 or len(ext)>3 or any(c in ' /\\:*?"<>|' for c in stem+ext):
        raise ValueError(f"Requires an 8.3 DOS filename: {name}")
    return (stem.ljust(8)+ext.ljust(3)).encode("ascii")

class FATVolume:
    def __init__(self, image):
        self.image = bytearray(image)
        self.start = 0 if u16(image,11)==512 else u32(image,454)*512
        b = self.start
        if u16(image,b+11)!=512: raise ValueError("Expected 512-byte FAT sectors")
        self.spc = image[b+13]
        if not self.spc or self.spc&(self.spc-1): raise ValueError("Invalid cluster size")
        self.cluster_size = self.spc*512
        self.fat_count = image[b+16]
        self.fat_sectors = u16(image,b+22)
        self.fat_start = b+u16(image,b+14)*512
        self.root_entries = u16(image,b+17)
        self.root_start = self.fat_start+self.fat_count*self.fat_sectors*512
        self.data_start = self.root_start+((self.root_entries*32+511)//512)*512
        sectors = u16(image,b+19) or u32(image,b+32)
        self.cluster_count = (sectors-(self.data_start-b)//512)//self.spc
        self.bits = 12 if self.cluster_count<4085 else 16
        self.eoc = 0xfff if self.bits==12 else 0xffff

    def fat(self, cluster, value=None):
        offset = cluster*2 if self.bits==16 else cluster+cluster//2
        if value is None:
            v = u16(self.image,self.fat_start+offset)
            return v if self.bits==16 else (v>>4 if cluster&1 else v&0xfff)
        for copy in range(self.fat_count):
            at = self.fat_start+copy*self.fat_sectors*512+offset
            if self.bits==16: w16(self.image,at,value)
            else:
                old = u16(self.image,at)
                w16(self.image,at,(old&15)|(value<<4) if cluster&1 else (old&0xf000)|value)

    def cluster_offset(self, cluster):
        if cluster<2 or cluster>=self.cluster_count+2: raise ValueError("Invalid FAT cluster")
        return self.data_start+(cluster-2)*self.cluster_size

    def chain(self, start):
        seen = set()
        while start>=2 and start < (0xff8 if self.bits==12 else 0xfff8):
            if start in seen: raise ValueError("FAT chain loop")
            self.cluster_offset(start)
            seen.add(start); yield start; start=self.fat(start)

    def allocate(self, data):
        count = math.ceil(len(data)/self.cluster_size)
        clusters = []
        for c in range(2,self.cluster_count+2):
            if self.fat(c)==0:
                clusters.append(c)
                if len(clusters)==count: break
        if not count: return 0
        if len(clusters)!=count: raise ValueError("Disk full")
        for index, cluster in enumerate(clusters):
            self.fat(cluster,clusters[index+1] if index+1<count else self.eoc)
            offset=self.cluster_offset(cluster)
            block=data[index*self.cluster_size:(index+1)*self.cluster_size]
            self.image[offset:offset+self.cluster_size]=block.ljust(self.cluster_size,b"\0")
        return clusters[0]

    def entries(self, cluster=0):
        if cluster:
            locations=[(self.cluster_offset(c),self.cluster_size//32) for c in self.chain(cluster)]
        else: locations=[(self.root_start,self.root_entries)]
        for start,count in locations:
            for index in range(count):
                offset=start+index*32
                if self.image[offset]==0: return
                if self.image[offset]==0xe5 or self.image[offset+11]==0x0f: continue
                yield offset

    def find(self, path):
        cluster=0;entry=None
        for part in PurePosixPath(path.replace("\\","/")).parts:
            if part in ("/", "."): continue
            name=dos_name(part)
            entry=next((e for e in self.entries(cluster) if self.image[e:e+11]==name),None)
            if entry is None: raise FileNotFoundError(path)
            cluster=u16(self.image,entry+26)
        if entry is None: raise ValueError("Expected a file path")
        return entry

    def read(self,path):
        entry=self.find(path);size=u32(self.image,entry+28)
        return b"".join(self.image[self.cluster_offset(c):self.cluster_offset(c)+self.cluster_size]
                        for c in self.chain(u16(self.image,entry+26)))[:size]

    def put(self,path,data):
        path=PurePosixPath(path.replace("\\","/"));parent=0
        if str(path.parent)!=".":
            p=self.find(str(path.parent));parent=u16(self.image,p+26)
            if not self.image[p+11]&16: raise ValueError("Parent is not a directory")
        try:
            entry=self.find(str(path))
            for c in list(self.chain(u16(self.image,entry+26))): self.fat(c,0)
        except FileNotFoundError:
            locations=[(self.cluster_offset(c),self.cluster_size//32) for c in self.chain(parent)] if parent else [(self.root_start,self.root_entries)]
            entry=next((start+i*32 for start,count in locations for i in range(count) if self.image[start+i*32] in (0,0xe5)),None)
            if entry is None: raise ValueError("Directory full")
        self.image[entry:entry+32]=directory_entry(path.name,self.allocate(data),len(data),False)

def directory_entry(name,cluster,size,is_dir):
    entry=bytearray(32);entry[:11]=dos_name(name);entry[11]=16 if is_dir else 32
    w16(entry,24,((2026-1980)<<9)|(10<<5)|25);w16(entry,26,cluster);w32(entry,28,size)
    return entry

def create_floppy(boot_sector, files):
    """Fresh 1.44 MiB FAT12 disk using assembled DOS boot code.

    Bytes 11..61 are the media-specific BPB/extended BPB. No downloaded disk
    supplies geometry, FAT entries, directory contents, padding or boot code.
    """
    if len(boot_sector) != 512 or boot_sector[510:512] != b"\x55\xaa":
        raise ValueError("Expected a 512-byte assembled DOS boot sector")
    if boot_sector[:3] != b"\xeb\x3c\x90":
        raise ValueError("Unexpected MS-DOS 4 boot code layout")
    image = bytearray(1440 * 1024)
    image[:512] = boot_sector
    image[11:62] = bytes(51)
    w16(image,11,512); image[13]=1; w16(image,14,1); image[16]=2
    w16(image,17,224); w16(image,19,2880); image[21]=0xf0; w16(image,22,9)
    w16(image,24,18); w16(image,26,2); w32(image,28,0); w32(image,32,0)
    image[36]=0; image[37]=0; image[38]=0x29; w32(image,39,0x86040001)
    image[43:54]=b"PROJECT86  "; image[54:62]=b"FAT12   "
    volume=FATVolume(image); volume.fat(0,0xff0); volume.fat(1,0xfff)
    # This boot loader requires IO.SYS / MSDOS.SYS in the first two entries,
    # with the initial IO.SYS loader contiguous at the beginning of data.
    for name in ['IO.SYS','MSDOS.SYS']:
        if name not in files: raise ValueError(f"Missing boot system file {name}")
        volume.put(name,files[name]); volume.image[volume.find(name)+11]=7
    for name in sorted(set(files)-{'IO.SYS','MSDOS.SYS'}):
        volume.put(name,files[name])
    return volume


def root_files(volume):
    result={}
    for entry in volume.entries():
        if volume.image[entry+11]&0x18:
            raise ValueError("Unexpected directory or label in the app boot image")
        raw=bytes(volume.image[entry:entry+11]).decode('ascii')
        name=raw[:8].rstrip()+('.'+raw[8:].rstrip() if raw[8:].strip() else '')
        if name in result: raise ValueError(f"Duplicate boot file {name}")
        result[name]=volume.read(name)
    return result

def create_hard_disk(files):
    image=bytearray(32*1024*1024)
    partition=32;sectors=len(image)//512-partition
    image[446:462]=struct.pack("<B3sB3sII",0,b"\x01\x01\x00",4,b"\x03\x60\xff",partition,sectors)
    image[510:512]=b"\x55\xaa"
    boot=partition*512;image[boot:boot+3]=b"\xeb\x3c\x90";image[boot+3:boot+11]=b"P86FAT16"
    w16(image,boot+11,512);image[boot+13]=4;w16(image,boot+14,1);image[boot+16]=2
    w16(image,boot+17,512);w16(image,boot+19,sectors);image[boot+21]=0xf8;w16(image,boot+22,64)
    w16(image,boot+24,32);w16(image,boot+26,4);w32(image,boot+28,partition)
    image[boot+36]=0x80;image[boot+38]=0x29;w32(image,boot+39,0x86000001)
    image[boot+43:boot+54]=b"PROJECT86  ";image[boot+54:boot+62]=b"FAT16   ";image[boot+62]=0xf4;image[boot+510:boot+512]=b"\x55\xaa"
    volume=FATVolume(image);volume.fat(0,0xfff8);volume.fat(1,0xffff)
    tree={}
    for name,data in files.items():
        parts=PurePosixPath(name).parts;node=tree
        for part in parts[:-1]: node=node.setdefault(part,{})
        node[parts[-1]]=data
    def emit(node,parent=0,is_root=False):
        cluster=0 if is_root else volume.allocate(bytes(max(1,math.ceil((len(node)+2)*32/volume.cluster_size))*volume.cluster_size))
        entries=[] if is_root else [directory_entry(".",cluster,0,True),directory_entry("..",parent,0,True)]
        for name,child in sorted(node.items()):
            if isinstance(child,dict): start=emit(child,cluster);size=0
            else: start=volume.allocate(child);size=len(child)
            entries.append(directory_entry(name,start,size,isinstance(child,dict)))
        content=b"".join(entries)
        if is_root:
            if len(content)>volume.root_entries*32: raise ValueError("Root directory full")
            volume.image[volume.root_start:volume.root_start+len(content)]=content
        else:
            for index,c in enumerate(volume.chain(cluster)):
                offset=volume.cluster_offset(c);chunk=content[index*volume.cluster_size:(index+1)*volume.cluster_size]
                volume.image[offset:offset+volume.cluster_size]=chunk.ljust(volume.cluster_size,b"\0")
        return cluster
    emit(tree,is_root=True)
    return volume

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="command",required=True)
    create=sub.add_parser("create");create.add_argument("output",type=Path);create.add_argument("--zip",type=Path);create.add_argument("--directory",type=Path);create.add_argument("--dos-build",action="store_true")
    read=sub.add_parser("read");read.add_argument("image",type=Path);read.add_argument("path");read.add_argument("--output",type=Path)
    put=sub.add_parser("put");put.add_argument("image",type=Path);put.add_argument("path");put.add_argument("source",type=Path)
    args=parser.parse_args()
    if args.command=="create":
        if args.output.exists(): raise SystemExit("Output exists; choose a new filename")
        files={}
        if args.zip:
            with zipfile.ZipFile(args.zip) as archive:
                files={i.filename.upper():archive.read(i) for i in archive.infolist() if not i.is_dir()}
        if args.directory:
            files.update({str(p.relative_to(args.directory)).upper():p.read_bytes() for p in args.directory.rglob("*") if p.is_file()})
        if args.dos_build:
            files["SRC/SETENV.BAT"]=files["SRC/SETENV.BAT"].replace(b"set BAKROOT=d:",b"set BAKROOT=c:")
            files["BUILD.BAT"]=b"@echo off\r\nc:\r\ncd \\src\r\ncall setenv.bat\r\nnmake > c:\\build.log\r\nif errorlevel 1 goto failed\r\necho P86 BUILD SUCCEEDED\r\ngoto end\r\n:failed\r\necho P86 BUILD FAILED\r\n:end\r\n"
        volume=create_hard_disk(files);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(volume.image)
        print(f"Created {args.output}: {len(files)} files; 32 MiB FAT16, 4 heads, 32 sectors")
    else:
        volume=FATVolume(args.image.read_bytes())
        if args.command=="read":
            data=volume.read(args.path)
            if args.output: args.output.write_bytes(data)
            else: print(data.decode("cp437"))
        else: volume.put(args.path,args.source.read_bytes());args.image.write_bytes(volume.image)

if __name__=="__main__":main()
