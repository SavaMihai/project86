"""Seed provenance, no-fallback and generation-comparison regressions.

These tests use completed build artifacts; the full compiler run is separate.
"""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from dos_artifacts import DEFAULT_BUILD, CATALOG, load_build, sha
import fetch_bootstrap
from prepare_guests import OUTPUT
from rebuild_dos import load_seed, main

BUILD = Path(os.environ.get('P86_DOS_BUILD_DIR', str(DEFAULT_BUILD)))
IMAGE = Path(os.environ.get('P86_GUEST_BOOT_DIR', str(OUTPUT)))


class DOSSeedTests(unittest.TestCase):
    def copy_seed(self, target):
        for name in ['dos-project-sources.zip', 'dos-library-sources.zip', 'project86.ima', 'project86-boot.json', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt', 'comsubs-source.zip', 'cassfar-source.zip']:
            if (IMAGE / name).exists(): shutil.copyfile(IMAGE / name, target / name)

    def test_seed_verifies_without_access_to_downloaded_floppy(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            if path.name == 'msdos400.ima':
                raise AssertionError('Seed selection accessed downloaded floppy')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            data, outputs, record, snapshots = load_seed(IMAGE, BUILD)
        self.assertEqual(set(outputs), set(CATALOG))
        self.assertEqual(record['image_sha256'], sha(data))
        self.assertEqual(record['build']['report_sha256'], sha(snapshots['seed-build-report.json']))

    def test_source_only_fetch_never_requests_floppy(self):
        # Exercise an empty cache, including real checksum/ZIP validation.
        responses = {fetch_bootstrap.FILES[name]: (ROOT / 'assets/bootstrap' / name).read_bytes()
                     for name in ['restored-source.zip', 'MICROSOFT-LICENSE.txt']}
        urls = []
        def download(url, **kwargs):
            urls.append(url)
            return io.BytesIO(responses[url])
        with tempfile.TemporaryDirectory() as folder, patch.object(fetch_bootstrap, 'DEST', Path(folder)), \
                patch('urllib.request.urlopen', side_effect=download), contextlib.redirect_stdout(io.StringIO()):
            fetch_bootstrap.fetch(source_only=True)
            self.assertEqual(set(urls), set(responses))
            self.assertFalse((Path(folder) / 'msdos400.ima').exists())

    def test_missing_seed_has_no_fallback_or_partial_build(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'new-build'
            argv = ['rebuild_dos.py', '--seed', str(Path(folder) / 'missing'),
                    '--seed-build', str(BUILD), '--output', str(target), '--fetch']
            with patch.object(sys, 'argv', argv), patch('fetch_bootstrap.fetch') as fetch, \
                    patch('rebuild_dos.subprocess.run') as run:
                with self.assertRaises(OSError): main()
            fetch.assert_not_called()
            run.assert_not_called()
            self.assertFalse(target.exists())

    def test_requires_seed_and_build_together(self):
        for flag in ['--seed', '--seed-build']:
            with self.subTest(flag=flag), patch.object(sys, 'argv', ['rebuild_dos.py', flag, str(IMAGE)]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)

    def test_rejects_corrupt_seed_and_receipt_only_hash_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            seed = Path(folder); self.copy_seed(seed)
            data = bytearray((seed / 'project86.ima').read_bytes()); data[-1] ^= 1
            (seed / 'project86.ima').write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'packaging receipt'): load_seed(seed, BUILD)
            receipt = json.loads((seed / 'project86-boot.json').read_text())
            receipt['image_sha256'] = sha(data)
            (seed / 'project86-boot.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'free space'): load_seed(seed, BUILD)

    def test_rejects_seed_from_different_build(self):
        with tempfile.TemporaryDirectory() as folder:
            seed = Path(folder); self.copy_seed(seed)
            receipt = json.loads((seed / 'project86-boot.json').read_text())
            receipt['build']['report_sha256'] = '0' * 64
            (seed / 'project86-boot.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'different DOS build'): load_seed(seed, BUILD)

    def test_ensure_does_not_silently_reuse_different_seed(self):
        # The current build cannot already have been built from its own report.
        argv = ['rebuild_dos.py', '--ensure', '--fetch', '--output', str(BUILD),
                '--seed', str(IMAGE), '--seed-build', str(BUILD)]
        with patch.object(sys, 'argv', argv), patch('fetch_bootstrap.fetch') as fetch, \
                patch('rebuild_dos.subprocess.run') as run:
            with self.assertRaisesRegex(SystemExit, 'different seed|different library selection'): main()
        fetch.assert_not_called()
        run.assert_not_called()

    def test_cached_generation_requires_all_exact_comparisons(self):
        report = json.loads((BUILD / 'report.json').read_text())
        if report.get('seed', {}).get('kind') != 'rebuilt-dos':
            self.skipTest('Select a second-generation build to test retained comparison evidence')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for name in ['report.json', 'source.img', 'dos-files.zip', 'command-source.zip', 'seed.ima', 'boot.ima',
                         'seed-receipt.json', 'seed-build-report.json', 'COMSUBS.LIB', 'comsubs-source.zip', 'CASSFAR.LIB', 'cassfar-source.zip']:
                if (BUILD / name).exists(): shutil.copyfile(BUILD / name, target / name)
            for mode in ['missing', 'different', 'dishonest-flag']:
                changed = json.loads(json.dumps(report))
                if mode == 'missing': del changed['seed_artifact_comparisons']['BOOT.BIN']
                elif mode == 'different': changed['seed_artifact_comparisons']['COMMAND.COM']['identical'] = not changed['seed_artifact_comparisons']['COMMAND.COM']['identical']
                else: changed['seed_artifact_comparisons']['BOOT.BIN']['seed_sha256'] = '0' * 64
                (target / 'report.json').write_text(json.dumps(changed))
                with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'seed artifact comparisons|differs from the verified seed'):
                    load_build(target)

    def test_cached_generation_rejects_missing_or_changed_seed_evidence(self):
        report = json.loads((BUILD / 'report.json').read_text())
        if report.get('seed', {}).get('kind') != 'rebuilt-dos':
            self.skipTest('Select a second-generation build to test retained seed evidence')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            names = ['report.json', 'source.img', 'dos-files.zip', 'command-source.zip', 'seed.ima', 'boot.ima',
                     'seed-receipt.json', 'seed-build-report.json', 'COMSUBS.LIB', 'comsubs-source.zip', 'CASSFAR.LIB', 'cassfar-source.zip']
            for name in names:
                if (BUILD / name).exists(): shutil.copyfile(BUILD / name, target / name)
            for name in ['seed.ima', 'boot.ima', 'seed-receipt.json', 'seed-build-report.json']:
                original = (target / name).read_bytes()
                for data in [None, bytes([original[0] ^ 1]) + original[1:]]:
                    if data is None: (target / name).unlink()
                    else: (target / name).write_bytes(data)
                    with self.subTest(name=name, missing=data is None), self.assertRaises(ValueError):
                        load_build(target)
                (target / name).write_bytes(original)


if __name__ == '__main__': unittest.main()
