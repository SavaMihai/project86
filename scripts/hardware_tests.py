#!/usr/bin/env python3
"""Compare our CPU with physical-8086 fixtures; no reference emulator runs."""
import argparse
import ctypes as C
import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = "e71c68d215a6bb8c356bd4cb3842de3bef345ca9"
BASE = f"https://raw.githubusercontent.com/SingleStepTests/8086/{REVISION}/"
CACHE = ROOT / ".cache/hardware"
DEFAULT = [f"{i:02X}" for i in range(0x40) if (i & 7) <= 5] + [f"{i:02X}" for i in range(0x40,0x60)] + [f"{i:02X}" for i in range(0x70,0x80)] + ["84","85","86","87","88","89","8A","8B","8C","8D","8E","8F","90","91","98","99","9C","9D","9E","9F","A0","A1","A2","A3","A8","A9","B0","B8","C3","C4","C5","C6","C7","CB","E0","E1","E2","E3","E8","E9","EA","EB","F5","F8","F9","FA","FB","FC","FD"]
NAMES = "ax cx dx bx sp bp si di es cs ss ds ip flags".split()
class CPU(C.Structure):
    _fields_ = [(name, C.c_uint16) for name in NAMES]

def fetch(name):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        remote = name if name == "LICENSE" else "v1/" + name
        with urllib.request.urlopen(BASE + remote, timeout=60) as response:
            data = response.read()
        temp = path.with_suffix(path.suffix + ".download")
        temp.write_bytes(data)
        temp.replace(path)
    return path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opcodes", nargs="+", default=DEFAULT)
    parser.add_argument("--max-tests", type=int, default=0)
    parser.add_argument("--output", type=Path, default=ROOT/".build/hardware-results.json")
    parser.add_argument("--extended", action="store_true")
    args = parser.parse_args()
    if args.extended:
        args.opcodes = ["27","2F","37","3F","D4","D5"] + [f"{op}.{group}" for op in ["D0","D1","D2","D3"] for group in [0,1,2,3,4,5,7]] + [f"{op}.{group}" for op in ["F6","F7"] for group in [0,2,3,4,5,6,7]]
    files = ["metadata.json", "LICENSE"] + [op + ".json.gz" for op in args.opcodes]
    print(f"Fetching/checking {len(files)-2} hardware fixture groups at {REVISION}", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch, files))
    metadata = json.loads((CACHE / "metadata.json").read_text())
    lib = C.CDLL(str(ROOT / ".build/libproject86.dylib"))
    lib.p86_create.restype = C.c_void_p
    lib.p86_destroy.argtypes = [C.c_void_p]
    lib.p86_reset.argtypes = [C.c_void_p]
    lib.p86_set_cpu.argtypes = [C.c_void_p, C.POINTER(CPU)]
    lib.p86_get_cpu.argtypes = [C.c_void_p, C.POINTER(CPU)]
    lib.p86_step_cpu.argtypes = [C.c_void_p]
    lib.p86_step_cpu.restype = C.c_int
    lib.p86_write_memory.argtypes = [C.c_void_p, C.c_uint32, C.c_uint8]
    lib.p86_read_memory.argtypes = [C.c_void_p, C.c_uint32]
    lib.p86_read_memory.restype = C.c_uint8
    machine = lib.p86_create()
    total = failed = 0
    results = []
    try:
        for op in args.opcodes:
            tests = json.loads(gzip.decompress((CACHE / (op + ".json.gz")).read_bytes()))
            if args.max_tests:
                tests = tests[:args.max_tests]
            info = metadata["opcodes"].get(op[:2], {})
            if "." in op:
                info = info.get("reg", {}).get(op.split(".")[1], {})
            mask = info.get("flags-mask", 65535)
            local_failed = 0
            for test in tests:
                lib.p86_reset(machine)
                initial = test["initial"]["regs"]
                cpu = CPU(**{k: v for k, v in initial.items() if k in NAMES})
                lib.p86_set_cpu(machine, C.byref(cpu))
                for address, value in test["initial"]["ram"]:
                    lib.p86_write_memory(machine, address, value)
                result = lib.p86_step_cpu(machine)
                after = CPU()
                lib.p86_get_cpu(machine, C.byref(after))
                expected = dict(initial)
                expected.update(test["final"]["regs"])
                errors = []
                if result == 3:
                    errors.append("unsupported/fault")
                for name in NAMES:
                    bits = mask if name == "flags" else 65535
                    if (getattr(after, name) & bits) != (expected[name] & bits):
                        errors.append(f"{name}={getattr(after,name):04x}, expected {expected[name]:04x}, mask {bits:04x}")
                for address, value in test["final"]["ram"]:
                    actual = lib.p86_read_memory(machine, address)
                    # A divide exception pushes FLAGS. Undefined arithmetic flags
                    # remain undefined in that saved word, just as in the register.
                    memory_mask = 255
                    if (op in ("F6.6","F6.7","F7.6","F7.7","D4")) and after.sp == (initial["sp"]-6)&65535:
                        low=((initial["ss"]<<4)+((initial["sp"]-2)&65535))&0xfffff
                        high=((initial["ss"]<<4)+((initial["sp"]-1)&65535))&0xfffff
                        if address==low: memory_mask=mask&255
                        if address==high: memory_mask=mask>>8
                    if (actual & memory_mask) != (value & memory_mask):
                        errors.append(f"[{address:05x}]={actual:02x}, expected {value:02x}")
                total += 1
                if errors:
                    failed += 1
                    local_failed += 1
                    if local_failed <= 2:
                        print(op, test["name"], test.get("test_num"), "; ".join(errors), flush=True)
            results.append({"opcode": op, "tests": len(tests), "failed": local_failed,
                            "sha256": hashlib.sha256((CACHE/(op+".json.gz")).read_bytes()).hexdigest()})
            print(f"{op}: {len(tests)-local_failed}/{len(tests)}", flush=True)
    finally:
        lib.p86_destroy(machine)
    report = {"fixture_revision": REVISION, "passed": total-failed, "total": total,
              "scope": "Architectural registers, defined flags and RAM; no bus/prefetch/timing validation", "groups": results}
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(f"Hardware fixtures: {total-failed}/{total} passed")
    raise SystemExit(bool(failed))

if __name__ == "__main__":
    main()
