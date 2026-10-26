"""Validate all DOS distribution outputs from a source build inside Project86."""
import hashlib
import json
from pathlib import Path
import zipfile
from disk_image import FATVolume

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD = ROOT / '.build/dos-command-editor-v2'
CATALOG_PATH = ROOT / 'assets/dos-files.json'
CATALOG = json.loads(CATALOG_PATH.read_text())['files']
DOS_FILES = {name: spec for name, spec in CATALOG.items() if name != 'BOOT.BIN'}
SYSTEM_FILES = {name: CATALOG[name]['guest_output'] for name in ['IO.SYS', 'MSDOS.SYS', 'COMMAND.COM']}
BUILD_VARIANT = 'project86-command-editor-v2'
EDITOR_SOURCE_VARIANT = 'project86-command-editor-source-v2'
EDITOR_V1_VARIANT = 'project86-command-editor-v1'
EDITOR_SOURCE_V1_VARIANT = 'project86-command-editor-source-v1'
ORIGINAL_VARIANT = 'project86-original-libraries-v1'
CASSFAR_VARIANT = 'project86-cassfar-v1'
COMSUBS_VARIANT = 'project86-comsubs-v1'
LEGACY_VARIANT = 'project86-ver-v1'
COMSUBS_USERS = {'JOIN.EXE', 'SUBST.EXE', 'BACKUP.COM', 'RESTORE.COM', 'REPLACE.EXE'}
COMSUBS_SOURCE = ROOT / 'guest-build/comsubs'
CASSFAR_SOURCE = ROOT / 'guest-build/cassfar'
VER_BANNER = 'Project86 - built from source'
EDITOR_REVISIONS = {BUILD_VARIANT: 2, EDITOR_SOURCE_VARIANT: 2,
                    EDITOR_V1_VARIANT: 1, EDITOR_SOURCE_V1_VARIANT: 1}
COMSUBS_VARIANTS = (COMSUBS_VARIANT, CASSFAR_VARIANT, EDITOR_SOURCE_VARIANT, EDITOR_SOURCE_V1_VARIANT)
CASSFAR_VARIANTS = (CASSFAR_VARIANT, EDITOR_SOURCE_VARIANT, EDITOR_SOURCE_V1_VARIANT)
ORIGINAL_VARIANTS = (ORIGINAL_VARIANT, BUILD_VARIANT, EDITOR_V1_VARIANT)
ORIGINAL_LIBRARIES = {
    'SRC/INC/COMSUBS.LIB': '3a2dd4aa684508037cf552692690943e9b0f8acf44e6ddb3ef43b631940789b1',
    'SRC/SELECT/CASSFAR.LIB': '39bbbb38f58483c3bacd366a899a90b7b8764b6431032ac7f7367212d6409f3e',
    'SRC/TOOLS/BLD/LIB/SLIBCE.LIB': 'd077b91d63d051d3333ca53f81cb15b0597cfdb6ec8a7fadc60f76ab6883e24f',
    'SRC/LIB/MEM.LIB': '74c8e6ddfb52846bf176c2ff35075edeff5de4b64130f1b502d5d9605ea214ff',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def expected_changes(seed, variant=BUILD_VARIANT):
    previous = seed.get('build', {}).get('build_variant')
    changed = set()
    if seed['kind'] == 'restoration' or EDITOR_REVISIONS.get(variant, 0) != EDITOR_REVISIONS.get(previous, 0):
        changed.add('COMMAND.COM')
    if (variant in COMSUBS_VARIANTS) != (previous in COMSUBS_VARIANTS):
        changed |= COMSUBS_USERS
    if (variant in CASSFAR_VARIANTS) != (previous in CASSFAR_VARIANTS):
        changed.add('SELECT.EXE')
    return changed


def has_editor(variant):
    return variant in EDITOR_REVISIONS


def validate_command(directory, guest, report):
    from command_source import FILES, PREFIX
    editor = report['command_editor']
    if set(editor['source_files']) != set(FILES):
        raise ValueError('Incomplete COMMAND editor source')
    data = (directory / 'command-source.zip').read_bytes()
    if sha(data) != editor['source_archive_sha256']:
        raise ValueError('COMMAND editor source archive differs from the build')
    with zipfile.ZipFile(directory / 'command-source.zip') as archive:
        if set(archive.namelist()) != set(FILES) | {'PATCH.PY'} or len(archive.namelist()) != len(FILES) + 1:
            raise ValueError('Incomplete COMMAND editor source package')
        for name, digest in editor['source_files'].items():
            if sha(archive.read(name)) != digest or archive.read(name) != guest.read(PREFIX + name):
                raise ValueError('COMMAND editor source differs from the guest build disk')
        if sha(archive.read('PATCH.PY')) != editor['patch_recipe_sha256']:
            raise ValueError('COMMAND editor patch recipe differs from the build')
    if set(editor['patched_files']) != {'TCODE.ASM', 'RDATA.ASM', 'TSPC.ASM', 'MAKEFILE'}:
        raise ValueError('Incomplete COMMAND editor patch record')
    for name, digest in editor['patched_files'].items():
        if sha(guest.read(PREFIX + name)) != digest:
            raise ValueError('COMMAND editor patched source differs from the build disk')


def validate_library(directory, guest, report, path, stem, source_dir, required):
    replacement = report['rebuilt_libraries'][path]
    if set(replacement['source_files']) != set(required):
        raise ValueError(f'Incomplete {stem} corresponding source')
    if path in report['retained_binary_libraries']:
        raise ValueError(f'Original binary {stem} was retained as a build input')
    library = (directory / (stem + '.LIB')).read_bytes()
    if (sha(library) != replacement['sha256'] or len(library) != replacement['bytes']
            or library != guest.read(path) or replacement['sha256'] == replacement['original_sha256']):
        raise ValueError(f'{stem} does not match the source-built library')
    source_zip = directory / (stem.lower() + '-source.zip')
    with zipfile.ZipFile(source_zip) as sources:
        if set(sources.namelist()) != set(required) or len(sources.namelist()) != len(required):
            raise ValueError(f'Incomplete {stem} corresponding source')
        for name, digest in replacement['source_files'].items():
            if sha(sources.read(name)) != digest or sources.read(name) != guest.read(source_dir + name):
                raise ValueError(f'{stem} source does not match the build disk')
    if sha(source_zip.read_bytes()) != replacement['source_archive_sha256']:
        raise ValueError(f'{stem} source archive does not match the build report')


def guest_output(guest, spec):
    data = guest.read(spec['guest_output'])
    if 'offset' in spec:
        offset, length = spec['offset'], spec['length']
        if len(data) != offset + length or any(data[:offset]):
            raise ValueError('Unexpected layout in assembled MSBOOT.BIN')
        data = data[offset:offset + length]
    return data


def validate_seed_record(directory, report):
    """Check retained seed evidence and exact generation-to-generation comparisons."""
    seed = report['seed']
    data = (directory / 'seed.ima').read_bytes()
    if sha(data) != seed['image_sha256']:
        raise ValueError('Retained seed image does not match the build report')
    boot = FATVolume(data)
    boot.put('CONFIG.SYS', b'FILES=64\r\nBUFFERS=20\r\nLASTDRIVE=C\r\nSHELL=A:\\COMMAND.COM /P /E:1024\r\n')
    boot.put('AUTOEXEC.BAT', b'@echo off\r\n')
    configured = (directory / 'boot.ima').read_bytes()
    if bytes(boot.image) != configured or sha(configured) != report['compiler_boot_image_sha256']:
        raise ValueError('Compiler boot image differs from the configured seed')
    if seed['kind'] == 'restoration':
        pinned = json.loads((ROOT / 'assets/bootstrap-manifest.json').read_text())
        if seed['image_sha256'] != pinned['msdos400.ima']['sha256']:
            raise ValueError('Restoration seed checksum mismatch')
    elif seed['kind'] == 'rebuilt-dos':
        receipt_data = (directory / 'seed-receipt.json').read_bytes()
        parent_data = (directory / 'seed-build-report.json').read_bytes()
        if sha(receipt_data) != seed['receipt_sha256'] or sha(parent_data) != seed['build']['report_sha256']:
            raise ValueError('Retained seed provenance does not match the build report')
        receipt, parent = json.loads(receipt_data), json.loads(parent_data)
        if receipt['image_sha256'] != seed['image_sha256'] or receipt['build'] != seed['build']:
            raise ValueError('Retained seed receipt belongs to a different build')
        comparisons = report['seed_artifact_comparisons']
        if set(comparisons) != set(CATALOG):
            raise ValueError('Incomplete or differing seed artifact comparisons')
        changed = set()
        for name, comparison in comparisons.items():
            equal = comparison['built_sha256'] == comparison['seed_sha256']
            if (comparison['identical'] is not equal
                    or comparison['built_sha256'] != report['artifacts'][name]['sha256']
                    or comparison['seed_sha256'] != parent['artifacts'][name]['sha256']
                    ):
                raise ValueError(f'{name} differs from the verified seed build')
            if not equal: changed.add(name)
        allowed = expected_changes(seed, report['build_variant']) if report['schema'] >= 4 else set()
        if changed != allowed or report['all_seed_artifacts_identical'] is not (not changed):
            raise ValueError('Incomplete or differing seed artifact comparisons')
    else:
        raise ValueError('Unknown DOS build seed kind')


def load_build(directory):
    """Require every output, its report, and matching bytes on the guest disk."""
    directory = Path(directory)
    try:
        report_data = (directory / 'report.json').read_bytes()
        report = json.loads(report_data)
        if report.get('schema') not in (2, 3, 4, 5, 6, 7) or report.get('catalog_sha256') != sha(CATALOG_PATH.read_bytes()):
            raise ValueError('A complete current DOS distribution build is required')
        variant = report.get('build_variant')
        if variant not in (LEGACY_VARIANT, COMSUBS_VARIANT, CASSFAR_VARIANT, *ORIGINAL_VARIANTS, *EDITOR_REVISIONS):
            raise ValueError('The DOS build predates the Project86 VER source message')
        supported = {2: (LEGACY_VARIANT,), 3: (LEGACY_VARIANT,), 4: (COMSUBS_VARIANT,),
                     5: (CASSFAR_VARIANT,), 6: (ORIGINAL_VARIANT,), 7: tuple(EDITOR_REVISIONS)}
        if variant not in supported[report['schema']]:
            raise ValueError('Source replacement variant and report schema disagree')
        if report['build_succeeded'] is not True or report['emulator_exit_code'] != 0:
            raise ValueError('The DOS source build did not succeed')
        if (report.get('distribution_matches_expected') is not True
                or report.get('boot_code_identical_outside_media_parameters') is not True):
            raise ValueError('The DOS build has unexpected distribution or boot-code differences')
        if report.get('fresh_build_without_distribution_binaries') is not True:
            raise ValueError('Build did not exclude prebuilt DOS distribution binaries')
        if report['schema'] >= 3:
            validate_seed_record(directory, report)
        guest_data = (directory / 'source.img').read_bytes()
        guest = FATVolume(guest_data)
        if variant in COMSUBS_VARIANTS:
            validate_library(directory, guest, report, 'SRC/INC/COMSUBS.LIB', 'COMSUBS',
                             'SRC/P86COM/', {'COMSUBS.C','DBCSTAB.ASM','COMSUBS.LBR'})
        if report['schema'] >= 4:
            if set(report['expected_distribution_differences']) != expected_changes(report['seed'], report['build_variant']):
                raise ValueError('Unexpected source replacement distribution differences')
        if variant in CASSFAR_VARIANTS:
            validate_library(directory, guest, report, 'SRC/SELECT/CASSFAR.LIB', 'CASSFAR',
                             'SRC/P86CAS/', {'CASSFAR.C','CBRIDGE.ASM','LAYOUT.H','CASSFAR.LBR'})
        if variant in ORIGINAL_VARIANTS:
            if report.get('rebuilt_libraries'):
                raise ValueError('Original-library build declares replacement libraries')
            for path, digest in ORIGINAL_LIBRARIES.items():
                data = guest.read(path)
                retained = report['retained_binary_libraries'].get(path, {})
                if (sha(data) != digest or retained.get('sha256') != digest
                        or retained.get('bytes') != len(data) or path in report['removed_prebuilt_inputs']):
                    raise ValueError(f'Original library does not match pinned input: {path}')
        if has_editor(variant):
            validate_command(directory, guest, report)
        archive_data = (directory / 'dos-files.zip').read_bytes()
        if sha(archive_data) != report['outputs_archive_sha256']:
            raise ValueError('DOS artifact archive does not match the build report')
        binaries = {}
        with zipfile.ZipFile(directory / 'dos-files.zip') as archive:
            if len(archive.namelist()) != len(CATALOG) or set(archive.namelist()) != set(CATALOG):
                raise ValueError('Incomplete or unexpected DOS artifacts')
            if set(report['artifacts']) != set(CATALOG):
                raise ValueError('Incomplete DOS artifact report')
            for name, spec in CATALOG.items():
                data = archive.read(name)
                expected = report['artifacts'][name]
                if not data or sha(data) != expected['sha256'] or len(data) != expected['bytes']:
                    raise ValueError(f'{name} does not match the DOS build report')
                if data != guest_output(guest, spec):
                    raise ValueError(f'{name} does not match the output on the DOS build disk')
                if spec['kind'] == 'source-text' and sha(data) != expected['source_sha256']:
                    raise ValueError(f'{name} changed from its source text')
                binaries[name] = data
        if VER_BANNER.encode('ascii') not in binaries['COMMAND.COM']:
            raise ValueError('COMMAND.COM is missing the compiled Project86 VER message')
        if has_editor(variant) and f'Project86 command editor v{EDITOR_REVISIONS[variant]}'.encode() not in binaries['COMMAND.COM']:
            raise ValueError('COMMAND.COM is missing the compiled command editor')
        if report['schema'] >= 4:
            seed_data = (directory / 'seed.ima').read_bytes()
            seed_volume = FATVolume(seed_data)
            actual_changes = {name for name in DOS_FILES if binaries[name] != seed_volume.read(name)}
            if actual_changes != expected_changes(report['seed'], report['build_variant']):
                raise ValueError('DOS outputs have unexpected differences from the seed')
            boot = binaries['BOOT.BIN']
            if boot[:11] != seed_data[:11] or boot[62:] != seed_data[62:512]:
                raise ValueError('Assembled boot code differs from the seed')
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as error:
        raise ValueError(f'Invalid DOS build at {directory}: {error}. Run make dos with a fresh DOS_BUILD directory.') from error
    provenance = {
        'report_sha256': sha(report_data),
        'guest_disk_sha256': sha(guest_data),
        'outputs_archive_sha256': sha(archive_data),
        'source_archive_sha256': report['source_archive_sha256'],
        'build_variant': report['build_variant'],
        'source_patches': report['source_patches'],
        'binary_library_boundary': report['binary_library_boundary'],
    }
    if report['schema'] >= 3:
        provenance['seed'] = report['seed']
        provenance['compiler_boot_image_sha256'] = report['compiler_boot_image_sha256']
    if report.get('rebuilt_libraries'):
        provenance['rebuilt_libraries'] = report['rebuilt_libraries']
    if has_editor(report['build_variant']):
        provenance['command_editor'] = report['command_editor']
    return binaries, provenance
