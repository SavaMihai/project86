"""Provenance regressions for the source-built COMSUBS dependency."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from dos_artifacts import DEFAULT_BUILD, load_build, sha
from prepare_guests import OUTPUT, verify_image

BUILD = Path(os.environ.get('P86_DOS_BUILD_DIR', str(DEFAULT_BUILD)))
IMAGE = Path(os.environ.get('P86_GUEST_BOOT_DIR', str(OUTPUT)))


class COMSUBSBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((BUILD / 'report.json').read_text())
        if 'SRC/INC/COMSUBS.LIB' not in cls.report.get('rebuilt_libraries', {}):
            raise unittest.SkipTest('Select a build with the Project86 COMSUBS replacement')

    def copy_build(self, target):
        for name in ['report.json', 'source.img', 'dos-files.zip', 'command-source.zip', 'seed.ima', 'boot.ima',
                     'seed-receipt.json', 'seed-build-report.json', 'COMSUBS.LIB', 'comsubs-source.zip', 'CASSFAR.LIB', 'cassfar-source.zip']:
            if (BUILD / name).exists(): shutil.copyfile(BUILD / name, target / name)

    def test_rejects_original_library_retained_as_input(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            report = json.loads((target / 'report.json').read_text())
            report['retained_binary_libraries']['SRC/INC/COMSUBS.LIB'] = {'sha256': report['rebuilt_libraries']['SRC/INC/COMSUBS.LIB']['original_sha256']}
            (target / 'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'Original binary COMSUBS'): load_build(target)

    def test_requires_actual_source_built_library_on_guest_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            data = (target / 'COMSUBS.LIB').read_bytes()
            changed = bytes([data[0] ^ 1]) + data[1:]
            (target / 'COMSUBS.LIB').write_bytes(changed)
            report = json.loads((target / 'report.json').read_text())
            report['rebuilt_libraries']['SRC/INC/COMSUBS.LIB']['sha256'] = sha(changed)
            (target / 'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'source-built library'): load_build(target)

    def test_corresponding_sources_are_required_and_cannot_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            (target / 'comsubs-source.zip').unlink()
            with self.assertRaises(ValueError): load_build(target)
            with zipfile.ZipFile(BUILD / 'comsubs-source.zip') as original, zipfile.ZipFile(target / 'comsubs-source.zip', 'w') as changed:
                for name in original.namelist(): changed.writestr(name, original.read(name) + b'\n')
            with self.assertRaisesRegex(ValueError, 'COMSUBS source'): load_build(target)

    def test_packaged_library_sources_are_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for name in ['dos-project-sources.zip', 'dos-library-sources.zip', 'project86.ima', 'project86-boot.json', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt', 'comsubs-source.zip', 'cassfar-source.zip']:
                if (IMAGE / name).exists(): shutil.copyfile(IMAGE / name, target / name)
            (target / 'comsubs-source.zip').write_bytes(b'changed sources')
            with self.assertRaisesRegex(ValueError, 'COMSUBS corresponding source'): verify_image(target)


if __name__ == '__main__': unittest.main()
