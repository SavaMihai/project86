"""Keep the enhanced COMMAND, its source and the packaged receipt consistent."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from disk_image import FATVolume
from dos_artifacts import DEFAULT_BUILD, BUILD_VARIANT, load_build, sha
from prepare_guests import OUTPUT, verify_image
from command_source import SOURCE, FILES
from rebuild_dos import main

BUILD = Path(os.environ.get('P86_DOS_BUILD_DIR', str(DEFAULT_BUILD)))
IMAGE = Path(os.environ.get('P86_GUEST_BOOT_DIR', str(OUTPUT)))


class CommandBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((BUILD / 'report.json').read_text())
        if 'command_editor' not in cls.report: raise unittest.SkipTest('Requires the enhanced COMMAND build')

    def copy_build(self, target):
        for name in ['report.json', 'source.img', 'dos-files.zip', 'command-source.zip',
                     'seed.ima', 'boot.ima', 'seed-receipt.json', 'seed-build-report.json',
                     'COMSUBS.LIB', 'CASSFAR.LIB', 'comsubs-source.zip', 'cassfar-source.zip']:
            if (BUILD / name).exists(): shutil.copyfile(BUILD / name, target / name)

    def test_command_corresponding_source_is_required(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            (target / 'command-source.zip').unlink()
            with self.assertRaises(ValueError): load_build(target)

    def test_command_guest_source_cannot_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            guest = FATVolume((target / 'source.img').read_bytes())
            guest.put('SRC/CMD/COMMAND/TCODE.ASM', b'wrong source')
            (target / 'source.img').write_bytes(guest.image)
            with self.assertRaisesRegex(ValueError, 'patched source differs'): load_build(target)

    def test_old_command_rejected_even_after_output_hash_refresh(self):
        baseline, _ = load_build(ROOT / '.build/dos-original-libraries')
        old = baseline['COMMAND.COM']
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            report = json.loads((target / 'report.json').read_text())
            disk = FATVolume((target / 'source.img').read_bytes())
            disk.put('SRC/CMD/COMMAND/COMMAND.COM', old)
            (target / 'source.img').write_bytes(disk.image)
            with zipfile.ZipFile(BUILD / 'dos-files.zip') as source, zipfile.ZipFile(target / 'dos-files.zip', 'w') as output:
                for name in source.namelist(): output.writestr(name, old if name == 'COMMAND.COM' else source.read(name))
            report['outputs_archive_sha256'] = sha((target / 'dos-files.zip').read_bytes())
            report['artifacts']['COMMAND.COM'].update(sha256=sha(old), bytes=len(old))
            if 'seed_artifact_comparisons' in report:
                record = report['seed_artifact_comparisons']['COMMAND.COM']
                record.update(built_sha256=sha(old), identical=sha(old) == record['seed_sha256'])
            (target / 'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'seed artifact comparisons|compiled command editor|unexpected differences'):
                load_build(target)

    def test_cache_rejects_current_source_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for local in FILES.values(): (target / local).write_bytes((SOURCE / local).read_bytes() + b'\n; changed\n')
            argv = ['rebuild_dos.py', '--ensure', '--output', str(BUILD)]
            with patch.object(sys, 'argv', argv), patch('rebuild_dos.COMMAND_SOURCE', target):
                with self.assertRaisesRegex(SystemExit, 'COMMAND editor source is stale'): main()

    def test_nested_command_package_is_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for name in ['project86.ima', 'project86-boot.json', 'cutemouse-source.zip',
                         'CUTEMOUSE-COPYING.txt', 'dos-project-sources.zip']:
                shutil.copyfile(IMAGE / name, target / name)
            with zipfile.ZipFile(IMAGE / 'dos-project-sources.zip') as source, zipfile.ZipFile(target / 'dos-project-sources.zip', 'w') as output:
                for name in source.namelist(): output.writestr(name, b'wrong source' if name == 'command-source.zip' else source.read(name))
            receipt = json.loads((target / 'project86-boot.json').read_text())
            receipt['project_sources_sha256'] = sha((target / 'dos-project-sources.zip').read_bytes())
            (target / 'project86-boot.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'COMMAND corresponding source'): verify_image(target)

    def test_editor_receipt_cannot_omit_corresponding_source(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for name in ['project86.ima', 'project86-boot.json', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt']:
                shutil.copyfile(IMAGE / name, target / name)
            receipt = json.loads((target / 'project86-boot.json').read_text())
            del receipt['project_sources_sha256']
            (target / 'project86-boot.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'COMMAND corresponding source package is required'):
                verify_image(target)

    def test_v1_binary_cannot_claim_directory_fix_revision(self):
        old = ROOT / '.build/dos-command-editor-v1'
        if not old.exists(): self.skipTest('Requires the preserved editor v1 baseline')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for name in ['report.json', 'source.img', 'dos-files.zip', 'command-source.zip',
                         'seed.ima', 'boot.ima', 'seed-receipt.json', 'seed-build-report.json']:
                shutil.copyfile(old / name, target / name)
            report = json.loads((target / 'report.json').read_text())
            report['build_variant'] = BUILD_VARIANT
            (target / 'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'compiled command editor'):
                load_build(target)


if __name__ == '__main__': unittest.main()
