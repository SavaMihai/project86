"""Source-built media regressions: provenance, BIOS boot layout and real DOS I/O."""
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
from disk_image import FATVolume, create_floppy, root_files, u16
from dos_artifacts import CATALOG, DEFAULT_BUILD, DOS_FILES, load_build, sha
from prepare_guests import ADDITIONS, OUTPUT, prepare, verify_image, verify_build_image
from p86 import Machine
from cutemouse_artifacts import DEFAULT_MOUSE_BUILD, load_mouse_build

BUILD = Path(os.environ.get('P86_DOS_BUILD_DIR', str(DEFAULT_BUILD)))
MOUSE_BUILD = Path(os.environ.get('P86_MOUSE_BUILD_DIR', str(DEFAULT_MOUSE_BUILD)))
OUTPUT = Path(os.environ.get('P86_GUEST_BOOT_DIR', str(OUTPUT)))


class BootImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binaries, _ = load_build(BUILD)

    def copy_build(self, destination):
        for name in ['command-source.zip', 'dos-files.zip', 'report.json', 'source.img', 'seed.ima', 'boot.ima', 'seed-receipt.json', 'seed-build-report.json', 'COMSUBS.LIB', 'comsubs-source.zip', 'CASSFAR.LIB', 'cassfar-source.zip']:
            if (BUILD / name).exists():
                shutil.copyfile(BUILD / name, destination / name)

    def copy_image(self, destination):
        for name in ['dos-project-sources.zip', 'dos-library-sources.zip', 'project86.ima', 'project86-boot.json', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt', 'comsubs-source.zip', 'cassfar-source.zip']:
            if (OUTPUT / name).exists(): shutil.copyfile(OUTPUT / name, destination / name)

    def test_all_dos_bytes_come_from_supplied_build_outputs(self):
        # Most build outputs match the published binaries, so distinct inputs
        # catch any accidental fallback to the downloaded distribution.
        distinct = {name: bytes([data[0] ^ 1]) + data[1:]
                    for name, data in self.binaries.items() if name in DOS_FILES}
        boot = bytearray(self.binaries['BOOT.BIN']); boot[100] ^= 1
        volume = create_floppy(boot, distinct)
        self.assertEqual(root_files(volume), distinct)
        self.assertEqual(volume.image[:11], boot[:11])
        self.assertEqual(volume.image[62:512], boot[62:512])

    def test_fresh_fat12_media_and_boot_layout(self):
        volume = FATVolume((OUTPUT / 'project86.ima').read_bytes())
        self.assertEqual(len(volume.image), 1440 * 1024)
        self.assertEqual((volume.bits, volume.spc, volume.fat_count), (12, 1, 2))
        self.assertEqual((u16(volume.image, 24), u16(volume.image, 26)), (18, 2))
        self.assertEqual(volume.image[510:512], b'\x55\xaa')
        entries = list(volume.entries())
        self.assertEqual(volume.find('IO.SYS'), entries[0])
        self.assertEqual(volume.find('MSDOS.SYS'), entries[1])
        self.assertEqual(u16(volume.image, entries[0]+26), 2)
        for name in ['IO.SYS', 'MSDOS.SYS']:
            entry = volume.find(name)
            self.assertEqual(volume.image[entry+11], 7)
            chain = list(volume.chain(u16(volume.image, entry+26)))
            self.assertEqual(chain, list(range(chain[0], chain[0]+len(chain))))
        for cluster in range(2, volume.cluster_count+2):
            if volume.fat(cluster) == 0:
                offset = volume.cluster_offset(cluster)
                self.assertEqual(volume.image[offset:offset+512], bytes(512))
        first = volume.fat_start
        size = volume.fat_sectors * 512
        self.assertEqual(volume.image[first:first+size], volume.image[first+size:first+2*size])

    def test_rejects_invalid_assembled_boot_sector(self):
        files = {name: self.binaries[name] for name in DOS_FILES}
        for boot in [bytes(512), self.binaries['BOOT.BIN'][:-1]]:
            with self.assertRaisesRegex(ValueError, 'assembled DOS boot sector'):
                create_floppy(boot, files)

    def test_packaging_does_not_read_downloaded_dos_image(self):
        read_bytes = Path.read_bytes
        def guarded(path):
            if path.name == 'msdos400.ima':
                raise AssertionError('Packaging attempted to read the downloaded floppy')
            return read_bytes(path)
        with tempfile.TemporaryDirectory() as folder, patch.object(Path, 'read_bytes', guarded):
            prepared = prepare(BUILD, Path(folder), MOUSE_BUILD)
            self.assertEqual(prepared.read_bytes(), (OUTPUT / 'project86.ima').read_bytes())

    def test_missing_build_has_no_fallback_or_partial_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / 'output'; output.mkdir()
            old_image = output / 'project86.ima'; old_image.write_bytes(b'previous image')
            with self.assertRaisesRegex(ValueError, 'Invalid DOS build'):
                prepare(root / 'missing-build', output)
            self.assertEqual(old_image.read_bytes(), b'previous image')

    def test_rejects_tampered_utility_boot_sector_and_missing_archive_member(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.copy_build(root)
            report = json.loads((root / 'report.json').read_text())
            for name in ['SORT.EXE', '4201.CPI', 'BOOT.BIN', None]:
                with zipfile.ZipFile(root / 'dos-files.zip', 'w') as archive:
                    for member, data in self.binaries.items():
                        if name is None and member == 'FC.EXE': continue
                        if member == name: data = bytes([data[0] ^ 1]) + data[1:]
                        archive.writestr(member, data)
                # Even a refreshed archive checksum cannot mask per-file tampering.
                report['outputs_archive_sha256'] = sha((root / 'dos-files.zip').read_bytes())
                (root / 'report.json').write_text(json.dumps(report))
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'does not match the DOS build report|Incomplete or unexpected'):
                    load_build(root)

    def test_rejects_failed_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.copy_build(root)
            report = json.loads((root / 'report.json').read_text())
            for field, value, message in [
                ('build_succeeded', False, 'did not succeed'),
                ('build_variant', None, 'predates the Project86 VER'),
                ('distribution_matches_expected', False, 'unexpected distribution'),
            ]:
                (root / 'report.json').write_text(json.dumps({**report, field: value}))
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                    load_build(root)

    def test_requires_actual_guest_utility_build_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.copy_build(root)
            guest = FATVolume((root / 'source.img').read_bytes())
            entry = guest.find(CATALOG['FC.EXE']['guest_output'])
            guest.image[guest.cluster_offset(u16(guest.image, entry+26))] ^= 1
            (root / 'source.img').write_bytes(guest.image)
            with self.assertRaisesRegex(ValueError, 'output on the DOS build disk'): load_build(root)

    def test_build_verification_rejects_missing_or_stale_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, 'Invalid DOS build'): verify_build_image(OUTPUT, root)
            self.copy_build(root)
            report = json.loads((root / 'report.json').read_text())
            report['source_patches'].append('different build provenance')
            (root / 'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'different DOS build'): verify_build_image(OUTPUT, root)

    def test_receipt_detects_image_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.copy_image(root)
            verify_image(root)
            data = bytearray((root / 'project86.ima').read_bytes()); data[-1] ^= 1
            (root / 'project86.ima').write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'packaging receipt'): verify_image(root)
            # Updating just the image receipt cannot hide nonzero unused bytes.
            receipt = json.loads((root / 'project86-boot.json').read_text())
            receipt['image_sha256'] = sha(data)
            (root / 'project86-boot.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'free space'): verify_build_image(root, BUILD, MOUSE_BUILD)

    def test_rejects_unaccounted_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.copy_image(root)
            volume = FATVolume((root / 'project86.ima').read_bytes()); volume.put('EXTRA.COM', b'\xc3')
            (root / 'project86.ima').write_bytes(volume.image)
            receipt = json.loads((root / 'project86-boot.json').read_text())
            receipt['image_sha256'] = sha(volume.image)
            (root / 'project86-boot.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'unaccounted-for'): verify_image(root)

    def test_missing_mouse_build_has_no_binary_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / 'output'; output.mkdir()
            (output / 'project86.ima').write_bytes(b'previous image')
            with self.assertRaisesRegex(ValueError, 'Invalid CuteMouse build'):
                prepare(BUILD, output, root / 'missing-mouse')
            self.assertEqual((output / 'project86.ima').read_bytes(), b'previous image')

    def test_mouse_output_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ['report.json', 'CTMOUSE.EXE', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt']:
                shutil.copyfile(MOUSE_BUILD / name, root / name)
            data = bytearray((root / 'CTMOUSE.EXE').read_bytes()); data[-1] ^= 1
            (root / 'CTMOUSE.EXE').write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'does not match the CuteMouse source build'):
                load_mouse_build(root)

    def test_mouse_corresponding_sources_have_no_upstream_executables(self):
        with zipfile.ZipFile(OUTPUT / 'cutemouse-source.zip') as archive:
            self.assertIn('source/ctmouse/ctmouse.asm', archive.namelist())
            self.assertIn('project86/scripts/rebuild_cutemouse.py', archive.namelist())
            self.assertIn('project86/changes.patch', archive.namelist())
            self.assertFalse(any(Path(n).suffix.lower() in {'.exe', '.com', '.obj', '.bin'} for n in archive.namelist()))
        driver, _ = load_mouse_build(MOUSE_BUILD)
        image = FATVolume((OUTPUT / 'project86.ima').read_bytes())
        self.assertEqual(image.read('CTMOUSE.EXE'), driver)

    def test_mouse_source_receipt_detects_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.copy_image(root)
            (root / 'cutemouse-source.zip').write_bytes(b'wrong sources')
            with self.assertRaisesRegex(ValueError, 'CuteMouse build receipt'): verify_image(root)

    def test_packaged_dos_utilities_boot_and_persist(self):
        receipt = verify_build_image(OUTPUT, BUILD, MOUSE_BUILD)
        image = FATVolume((OUTPUT / 'project86.ima').read_bytes())
        self.assertEqual(set(root_files(image)), set(DOS_FILES) | ADDITIONS)
        self.assertEqual(receipt['retained_from_bootstrap'], [])
        for name in DOS_FILES:
            self.assertEqual(image.read(name), self.binaries[name])
        with tempfile.TemporaryDirectory() as folder:
            disk = Path(folder) / 'working.ima'; disk.write_bytes(image.image)
            machine = Machine(disk, writable=True)
            try:
                # Clear AUTOEXEC's startup output: this must be VER itself.
                machine.type('cls\rver\r'); machine.seconds(.5)
                self.assertIn('MS-DOS Version 4.00 (Project86 - built from source)', machine.text())
                # Also verify DOS redirection and a separately loaded shell.
                machine.type('command /c ver > VER.TXT\r'); machine.seconds(.5)
                self.assertTrue(machine.call('flush_disks'))
                self.assertIn(b'MS-DOS Version 4.00 (Project86 - built from source)',
                              FATVolume(disk.read_bytes()).read('VER.TXT'))
                machine.type('type p86build.txt\r'); machine.seconds(.5)
                self.assertIn('62 DOS files: 60 rebuilt outputs', machine.text())
                machine.type('echo REBUILT-DOS-OK>PROOF.TXT\rcopy PROOF.TXT COPY.TXT\rfc PROOF.TXT COPY.TXT\r')
                machine.seconds(.5)
                self.assertIn('fc: no differences encountered', machine.text())
                machine.type('echo BETA>LINES.TXT\recho ALPHA>>LINES.TXT\rsort <LINES.TXT >SORTED.TXT\rfind "ALPHA" SORTED.TXT >FOUND.TXT\r')
                machine.type('md proofdir\rxcopy copy.txt proofdir\\\rattrib +r copy.txt\r')
                machine.type('chkdsk\r'); machine.seconds(1)
                self.assertIn('655360 total bytes memory', machine.text())
                self.assertTrue(machine.call('flush_disks'))
            finally: machine.close()
            saved = FATVolume(disk.read_bytes())
            self.assertIn(b'REBUILT-DOS-OK', saved.read('PROOFDIR/COPY.TXT'))
            self.assertEqual(saved.read('SORTED.TXT'), b'ALPHA\r\nBETA\r\n')
            self.assertIn(b'ALPHA', saved.read('FOUND.TXT'))
            self.assertTrue(saved.image[saved.find('COPY.TXT')+11] & 1)
            machine = Machine(disk)
            try:
                machine.type('type proofdir\\copy.txt\r'); machine.seconds(.5)
                self.assertIn('REBUILT-DOS-OK', machine.text())
            finally: machine.close()


if __name__ == '__main__': unittest.main()
