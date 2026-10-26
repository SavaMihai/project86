#!/usr/bin/env python3
"""Fetch guest software only. Never invokes any third-party emulator."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "assets/bootstrap"
BASE = "https://felsqualle.com/posts/2024/05/the-broken-source-code-for-ms-dos-4-has-been-restored/"
FILES = {
    "msdos400.ima": BASE + "msdos400_1440.ima",
    "restored-source.zip": BASE + "v400_src_plain.zip",
    "MICROSOFT-LICENSE.txt": "https://raw.githubusercontent.com/microsoft/MS-DOS/main/LICENSE",
}

def fetch(source_only=False):
    DEST.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "assets/bootstrap-manifest.json"
    prior = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    records = {}
    for name, url in FILES.items():
        if source_only and name == 'msdos400.ima':
            continue
        if source_only and name not in prior:
            raise SystemExit(f'Source-only fetching requires a pinned checksum for {name}')
        path = DEST / name
        if not path.exists():
            print("Fetching", name, flush=True)
            with urllib.request.urlopen(url, timeout=90) as response:
                data = response.read()
            digest = hashlib.sha256(data).hexdigest()
            if name in prior and prior[name]["sha256"] != digest:
                raise SystemExit(f"Checksum changed for {name}; inspect upstream before updating")
            temporary = path.with_suffix(path.suffix + ".download")
            temporary.write_bytes(data)
            temporary.replace(path)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if name in prior and prior[name]["sha256"] != digest:
            raise SystemExit(f"Local checksum mismatch: {name}")
        records[name] = {"url": url, "sha256": digest, "bytes": len(data)}
        print(name, len(data), digest)
    if not source_only:
        disk = (DEST / "msdos400.ima").read_bytes()
        assert len(disk) == 1474560 and disk[510:512] == b"\x55\xaa", "Invalid boot image"
    with zipfile.ZipFile(DEST / "restored-source.zip") as archive:
        if archive.testzip():
            raise SystemExit("Source ZIP failed integrity validation")
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(records, indent=2) + "\n")
    print("Guest artifact checksums verified. Run scripts/rebuild_dos.py to independently verify source/binary correspondence.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-only', action='store_true', help='Fetch source/tools and license without the restoration floppy')
    fetch(parser.parse_args().source_only)
