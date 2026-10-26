"""Validate the independently assembled CuteMouse driver and matching sources."""
import json
from pathlib import Path
from dos_artifacts import ROOT, sha

DEFAULT_MOUSE_BUILD = ROOT / '.build/cutemouse-build'
MANIFEST_PATH = ROOT / 'assets/cutemouse-manifest.json'
MANIFEST = json.loads(MANIFEST_PATH.read_text())
RECIPE = ROOT / 'scripts/rebuild_cutemouse.py'


def load_mouse_build(directory=DEFAULT_MOUSE_BUILD):
    directory = Path(directory)
    try:
        report_data = (directory / 'report.json').read_bytes()
        report = json.loads(report_data)
        if report['schema'] != 1 or report['build_succeeded'] is not True:
            raise ValueError('CuteMouse source build did not succeed')
        if report['manifest_sha256'] != sha(MANIFEST_PATH.read_bytes()) or report['recipe_sha256'] != sha(RECIPE.read_bytes()):
            raise ValueError('Stale CuteMouse build recipe or source pins')
        for name, expected in report['outputs'].items():
            if name not in {'CTMOUSE.EXE', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt'}:
                raise ValueError('Unexpected CuteMouse build output')
            data = (directory / name).read_bytes()
            if sha(data) != expected['sha256'] or len(data) != expected['bytes']:
                raise ValueError(f'{name} does not match the CuteMouse source build')
        if set(report['outputs']) != {'CTMOUSE.EXE', 'cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt'}:
            raise ValueError('Incomplete CuteMouse build outputs')
        driver = (directory / 'CTMOUSE.EXE').read_bytes()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f'Invalid CuteMouse build at {directory}: {error}. Run make mouse with a fresh MOUSE_BUILD directory.') from error
    return driver, {'report_sha256': sha(report_data), 'version': MANIFEST['version'],
                    'source_archive_sha256': MANIFEST['source']['sha256'],
                    'corresponding_source_sha256': report['outputs']['cutemouse-source.zip']['sha256'],
                    'license_sha256': report['outputs']['CUTEMOUSE-COPYING.txt']['sha256'],
                    'driver_sha256': sha(driver), 'recipe_sha256': report['recipe_sha256']}
