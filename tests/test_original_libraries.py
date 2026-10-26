"""Pin restored libraries and prevent accidental build/package variant mixing."""
import contextlib
import io
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
from dos_artifacts import DEFAULT_BUILD, ORIGINAL_LIBRARIES, load_build, sha
from prepare_guests import prepare, verify_image
from rebuild_dos import main

BUILD = Path(os.environ.get('P86_DOS_BUILD_DIR', str(DEFAULT_BUILD)))


class OriginalLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = json.loads((BUILD / 'report.json').read_text())
        if report.get('rebuilt_libraries') or report['schema'] < 6:
            raise unittest.SkipTest('Requires the restored original-library build')

    def copy_build(self, target):
        for name in ['report.json', 'source.img', 'dos-files.zip', 'command-source.zip', 'seed.ima', 'boot.ima',
                     'seed-receipt.json', 'seed-build-report.json']:
            if (BUILD / name).exists(): shutil.copyfile(BUILD / name, target / name)

    def test_rejects_each_changed_library_even_with_refreshed_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            for path in ORIGINAL_LIBRARIES:
                guest = FATVolume((BUILD / 'source.img').read_bytes())
                data = guest.read(path); changed = bytes([data[0] ^ 1]) + data[1:]
                guest.put(path, changed); (target / 'source.img').write_bytes(guest.image)
                report = json.loads((BUILD / 'report.json').read_text())
                report['retained_binary_libraries'][path]['sha256'] = sha(changed)
                (target / 'report.json').write_text(json.dumps(report))
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Original library does not match pinned input'):
                    load_build(target)

    def test_rejects_replacement_provenance_in_original_build(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); self.copy_build(target)
            report = json.loads((target / 'report.json').read_text())
            report['rebuilt_libraries'] = {'SRC/INC/COMSUBS.LIB': {}}
            (target / 'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'declares replacement libraries'): load_build(target)

    def test_cache_cannot_silently_change_library_selection(self):
        argv = ['rebuild_dos.py', '--ensure', '--output', str(BUILD), '--libraries', 'source']
        with patch.object(sys, 'argv', argv), patch('rebuild_dos.subprocess.run') as run:
            with self.assertRaisesRegex(SystemExit, 'different library selection'): main()
        run.assert_not_called()

    def test_packaging_removes_stale_replacement_sources(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            target = Path(folder)
            for name in ['comsubs-source.zip', 'cassfar-source.zip']:
                (target / name).write_bytes(b'previous experimental package')
            prepare(BUILD, target)
            self.assertFalse((target / 'comsubs-source.zip').exists())
            self.assertFalse((target / 'cassfar-source.zip').exists())
            with zipfile.ZipFile(target / 'dos-project-sources.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'BUILD-INFO.txt', 'command-source.zip'} if 'command_editor' in json.loads((BUILD / 'report.json').read_text()) else {'BUILD-INFO.txt'})
                self.assertIn(b'four libraries', archive.read('BUILD-INFO.txt'))
            verify_image(target)

    def test_package_rejects_unused_source_even_with_refreshed_checksum(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            target = Path(folder); prepare(BUILD, target)
            with zipfile.ZipFile(target / 'dos-project-sources.zip', 'a') as archive:
                archive.writestr('cassfar-source.zip', b'unused replacement source')
            receipt = json.loads((target / 'project86-boot.json').read_text())
            receipt['project_sources_sha256'] = sha((target / 'dos-project-sources.zip').read_bytes())
            (target / 'project86-boot.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'Unexpected DOS library source package contents'):
                verify_image(target)


if __name__ == '__main__': unittest.main()
