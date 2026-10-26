"""Reject original CASSFAR fallback and stale SELECT packaging."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from dos_artifacts import DEFAULT_BUILD, load_build, sha
from prepare_guests import OUTPUT, verify_image
from disk_image import FATVolume
BUILD=Path(os.environ.get('P86_DOS_BUILD_DIR',str(DEFAULT_BUILD)))
IMAGE=Path(os.environ.get('P86_GUEST_BOOT_DIR',str(OUTPUT)))


class CASSFARBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((BUILD/'report.json').read_text())
        if 'SRC/SELECT/CASSFAR.LIB' not in cls.report.get('rebuilt_libraries',{}):raise unittest.SkipTest('Requires a CASSFAR source build')

    def copy_build(self,target):
        for name in ['report.json','source.img','dos-files.zip','command-source.zip','seed.ima','boot.ima',
                     'seed-receipt.json','seed-build-report.json','COMSUBS.LIB','comsubs-source.zip',
                     'CASSFAR.LIB','cassfar-source.zip']:
            if (BUILD/name).exists():shutil.copyfile(BUILD/name,target/name)

    def test_rejects_original_cassfar_as_retained_input(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder);self.copy_build(target)
            report=json.loads((target/'report.json').read_text())
            report['retained_binary_libraries']['SRC/SELECT/CASSFAR.LIB']={}
            (target/'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'Original binary CASSFAR'):load_build(target)

    def test_rejects_old_select_even_when_its_output_hashes_are_refreshed(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder);self.copy_build(target)
            report=json.loads((target/'report.json').read_text())
            old=FATVolume((target/'seed.ima').read_bytes()).read('SELECT.EXE')
            disk=FATVolume((target/'source.img').read_bytes());disk.put('SRC/SELECT/SELECT.EXE',old)
            (target/'source.img').write_bytes(disk.image)
            with zipfile.ZipFile(BUILD/'dos-files.zip') as source,zipfile.ZipFile(target/'dos-files.zip','w') as output:
                for name in source.namelist():output.writestr(name,old if name=='SELECT.EXE' else source.read(name))
            report['outputs_archive_sha256']=sha((target/'dos-files.zip').read_bytes())
            report['artifacts']['SELECT.EXE'].update(sha256=sha(old),bytes=len(old))
            report['seed_artifact_comparisons']['SELECT.EXE'].update(built_sha256=sha(old),identical=True)
            report['all_seed_artifacts_identical']=True
            (target/'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'seed artifact comparisons'):load_build(target)

    def test_packaged_cassfar_source_is_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            for name in ['dos-project-sources.zip','dos-library-sources.zip','project86.ima','project86-boot.json','cutemouse-source.zip',
                         'CUTEMOUSE-COPYING.txt','comsubs-source.zip','cassfar-source.zip']:
                if (IMAGE/name).exists(): shutil.copyfile(IMAGE/name,target/name)
            (target/'cassfar-source.zip').write_bytes(b'wrong corresponding source')
            with self.assertRaisesRegex(ValueError,'CASSFAR corresponding source'):verify_image(target)


if __name__=='__main__':unittest.main()
