#!/usr/bin/env python3
"""Boot genuine DOS in Project86 and verify real FAT writes across a restart."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from disk_image import FATVolume, create_hard_disk
from prepare_guests import prepare

ROOT=Path(__file__).resolve().parents[1]
def run(disk,commands,hard=None):
    args=[str(ROOT/".build/p86"),"--disk",str(disk),"--write"]
    if hard:args += ["--hard-disk",str(hard)]
    for command in ["",""]+commands:args += ["--command",command]
    result=subprocess.run(args,capture_output=True,text=True,timeout=60)
    if result.returncode:raise AssertionError(result.stdout+result.stderr)
    return result.stdout

def main():
    prepared = prepare()
    with tempfile.TemporaryDirectory(prefix="project86-dos-") as temp:
        disk=Path(temp)/"dos.ima";shutil.copyfile(prepared,disk)
        # A guest .COM calls the real DOS INT 21h API, then exits back to COMMAND.COM.
        volume=FATVolume(disk.read_bytes())
        volume.put("HELLO.COM",bytes.fromhex("ba0c01b409cd21b8004ccd21")+b"P86 EXEC OK\r\n$")
        disk.write_bytes(volume.image)
        output=run(disk,["ver","echo P86-PERSIST>PROOF.TXT","copy PROOF.TXT COPY.TXT","hello","type COPY.TXT"])
        assert "MS-DOS Version 4.00" in output,output
        assert "P86 EXEC OK" in output,output
        volume=FATVolume(disk.read_bytes());assert b"P86-PERSIST" in volume.read("COPY.TXT")
        output=run(disk,["type COPY.TXT","chkdsk"])
        assert "P86-PERSIST" in output,output
        assert "655360 total bytes memory" in output,output
        hard=Path(temp)/"data.img";hard.write_bytes(create_hard_disk({"INPUT.TXT":b"HARD DISK INPUT\r\n"}).image)
        output=run(disk,["c:","type INPUT.TXT","echo HDD-PERSIST>OUTPUT.TXT","dir"],hard)
        assert "HARD DISK INPUT" in output and "OUTPUT" in output,output
        assert b"HDD-PERSIST" in FATVolume(hard.read_bytes()).read("OUTPUT.TXT")
        output=run(disk,["c:","type OUTPUT.TXT"],hard);assert "HDD-PERSIST" in output,output
    print("DOS integration passed: real boot/version, COM execution, CHKDSK, FAT12/FAT16 read/write/copy, persistence after restart.")

if __name__=="__main__":main()
