#!/usr/bin/env python3
"""Rebuild the complete DOS distribution using original tools inside Project86."""
import argparse
import json
from pathlib import Path
import subprocess
import zipfile
from disk_image import FATVolume, create_hard_disk
from dos_artifacts import ROOT, DEFAULT_BUILD, CATALOG_PATH, CATALOG, BUILD_VARIANT, VER_BANNER, guest_output, load_build, sha
from dos_artifacts import COMSUBS_SOURCE, CASSFAR_SOURCE, CASSFAR_VARIANT, expected_changes
from dos_artifacts import ORIGINAL_VARIANT, EDITOR_SOURCE_VARIANT
from cassfar_layout import layout_header
from command_source import patch_command, FILES as COMMAND_FILES, SOURCE as COMMAND_SOURCE, PREFIX as COMMAND_PREFIX
from prepare_guests import verify_dos_build_image


def load_seed(directory, build):
    """Verify a packaged, source-built floppy without consulting the original disk."""
    directory, build = Path(directory), Path(build)
    verify_dos_build_image(directory, build)
    binaries, provenance = load_build(build)
    data = (directory / 'project86.ima').read_bytes()
    receipt = (directory / 'project86-boot.json').read_bytes()
    return data, binaries, {
        'kind': 'rebuilt-dos', 'image_sha256': sha(data),
        'receipt_sha256': sha(receipt), 'build': provenance,
    }, {'seed-receipt.json': receipt, 'seed-build-report.json': (build / 'report.json').read_bytes()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--libraries', choices=['original', 'source'], default='original',
                        help='Original libraries (default), or experimental COMSUBS/CASSFAR source replacements')
    parser.add_argument('--shell', choices=['enhanced', 'original'], default='enhanced',
                        help='COMMAND history/completion (default), or the preserved VER-only shell')
    parser.add_argument('--ensure', action='store_true')
    parser.add_argument('--fetch', action='store_true', help='Fetch missing pinned inputs for a fresh build')
    parser.add_argument('--seed', type=Path, help='Verified packaged floppy directory (image, receipt and mouse source/license)')
    parser.add_argument('--seed-build', type=Path, help='DOS build that produced --seed; both options are required together')
    args = parser.parse_args()
    replacements = args.libraries == 'source'
    editor = args.shell == 'enhanced'
    variant = (EDITOR_SOURCE_VARIANT if replacements else BUILD_VARIANT) if editor else (CASSFAR_VARIANT if replacements else ORIGINAL_VARIANT)
    if (args.seed is None) != (args.seed_build is None):
        parser.error('--seed and --seed-build must be supplied together')
    directory = args.output
    selected_seed = load_seed(args.seed, args.seed_build) if args.seed else None
    if directory.exists():
        if not args.ensure:
            raise SystemExit('Output directory exists; choose a fresh --output directory')
        try:
            load_build(directory)
            cached = json.loads((directory / 'report.json').read_text())
            if cached['build_variant'] != variant:
                raise ValueError('Cached DOS build uses a different library selection or shell; choose a fresh output')
            if editor:
                command = cached['command_editor']
                for name, local in COMMAND_FILES.items():
                    data = (COMMAND_SOURCE / local).read_text().replace('\n', '\r\n').encode('ascii')
                    if sha(data) != command['source_files'][name]:
                        raise ValueError('Cached COMMAND editor source is stale; choose a fresh output')
                if sha((ROOT / 'scripts/command_source.py').read_bytes()) != command['patch_recipe_sha256']:
                    raise ValueError('Cached COMMAND editor patch recipe is stale; choose a fresh output')
            if replacements:
                for name, digest in cached['rebuilt_libraries']['SRC/INC/COMSUBS.LIB']['source_files'].items():
                    if name in ('COMSUBS.C', 'DBCSTAB.ASM') and sha((COMSUBS_SOURCE / name.lower()).read_bytes()) != digest:
                        raise ValueError('Cached COMSUBS source is stale; choose a fresh output')
                replacement = cached['rebuilt_libraries']['SRC/SELECT/CASSFAR.LIB']
                for name, local in [('CASSFAR.C', 'cassfar.c'), ('CBRIDGE.ASM', 'bridge.asm')]:
                    if sha((CASSFAR_SOURCE / local).read_bytes()) != replacement['source_files'][name]:
                        raise ValueError('Cached CASSFAR source is stale; choose a fresh output')
                if replacement['layout_generator_sha256'] != sha((ROOT / 'scripts/cassfar_layout.py').read_bytes()):
                    raise ValueError('Cached CASSFAR layout generator is stale; choose a fresh output')
            if selected_seed and json.loads((directory / 'report.json').read_text()).get('seed') != selected_seed[2]:
                raise ValueError('Cached DOS build used a different seed; choose a fresh --output directory')
        except ValueError as error:
            raise SystemExit(str(error))
        print(f'Verified complete in-emulator DOS build: {directory}')
        return
    if args.fetch:
        from fetch_bootstrap import fetch
        fetch(source_only=selected_seed is not None)
    source_data = (ROOT / 'assets/bootstrap/restored-source.zip').read_bytes()
    pinned = json.loads((ROOT / 'assets/bootstrap-manifest.json').read_text())
    if sha(source_data) != pinned['restored-source.zip']['sha256']:
        raise SystemExit('Source checksum mismatch')
    if selected_seed:
        bootstrap_data, reference_outputs, seed_record, seed_files = selected_seed
    else:
        bootstrap_data = (ROOT / 'assets/bootstrap/msdos400.ima').read_bytes()
        if sha(bootstrap_data) != pinned['msdos400.ima']['sha256']:
            raise SystemExit('Bootstrap checksum mismatch')
        seed_record = {'kind': 'restoration', 'image_sha256': sha(bootstrap_data)}
        seed_files = {}
    directory.mkdir(parents=True)
    (directory / 'seed.ima').write_bytes(bootstrap_data)
    for name, data in seed_files.items():
        (directory / name).write_bytes(data)
    bootstrap = FATVolume(bootstrap_data)
    boot = FATVolume(bootstrap_data)
    boot.put('CONFIG.SYS', b'FILES=64\r\nBUFFERS=20\r\nLASTDRIVE=C\r\nSHELL=A:\\COMMAND.COM /P /E:1024\r\n')
    # Build-only startup: no resident mouse driver or interactive app setup.
    boot.put('AUTOEXEC.BAT', b'@echo off\r\n')
    boot_path = directory / 'boot.ima'; boot_path.write_bytes(boot.image)
    with zipfile.ZipFile(ROOT / 'assets/bootstrap/restored-source.zip') as archive:
        files = {i.filename.upper(): archive.read(i) for i in archive.infolist() if not i.is_dir()}
    # Change the actual COMMAND.COM message source before the DOS tools run.
    # Keep the kernel version and its numeric substitutions intact.
    message_path = 'SRC/MESSAGES/USA-MS.MSG'
    original_message = b'1040 U 0000 "MS-DOS Version %1.%2"'
    rebuilt_message = f'1040 U 0000 "MS-DOS Version %1.%2 ({VER_BANNER})"'.encode('ascii')
    if files[message_path].count(original_message) != 1:
        raise SystemExit('Expected unique VER message not found in the pinned DOS source')
    files[message_path] = files[message_path].replace(original_message, rebuilt_message)
    if editor:
        command_sources = patch_command(files)
    text_hashes = {name: sha(files[spec['guest_output']]) for name, spec in CATALOG.items() if spec['kind'] == 'source-text'}
    removed = []
    if replacements:
        original_comsubs = files.pop('SRC/INC/COMSUBS.LIB')
        removed.append('SRC/INC/COMSUBS.LIB')
        comsubs_sources = {name.upper(): (COMSUBS_SOURCE / name).read_bytes() for name in ['comsubs.c', 'dbcstab.asm']}
        comsubs_sources['COMSUBS.LBR'] = b'..\\inc\\comsubs.lib\r\ny\r\n+comsubs.obj+dbcstab.obj\r\ncomsubs.lst;\r\n'
        for name, data in comsubs_sources.items(): files['SRC/P86COM/' + name] = data
        original_cassfar = files.pop('SRC/SELECT/CASSFAR.LIB')
        removed.append('SRC/SELECT/CASSFAR.LIB')
        cassfar_sources = {'CASSFAR.C': (CASSFAR_SOURCE / 'cassfar.c').read_bytes(),
                          'CBRIDGE.ASM': (CASSFAR_SOURCE / 'bridge.asm').read_bytes()}
        with zipfile.ZipFile(ROOT / 'assets/bootstrap/restored-source.zip') as archive:
            cassfar_sources['LAYOUT.H'] = layout_header(archive)
        cassfar_sources['CASSFAR.LBR'] = b'..\\select\\cassfar.lib\r\ny\r\n+cassfar.obj+cbridge.obj\r\ncassfar.lst;\r\n'
        for name, data in cassfar_sources.items(): files['SRC/P86CAS/' + name] = data
    # No shipped distribution outputs can satisfy NMAKE from the input.
    # Original tools and binary support/runtime libraries remain dependencies.
    for name, spec in CATALOG.items():
        if spec['kind'] != 'source-text' and spec['guest_output'] in files:
            removed.append(spec['guest_output']); del files[spec['guest_output']]
    # These archived intermediates have source; don't let their timestamps
    # accidentally bypass assembly/compilation if a build target needs them.
    for path in ['SRC/INC/PRINTF.OBJ', 'SRC/INC/STRING.OBJ']:
        if path in files:
            removed.append(path); del files[path]
    binary_libraries = {path: {'sha256': sha(data), 'bytes': len(data)}
                        for path, data in files.items()
                        if path.endswith(('.OBJ', '.LIB')) and path != 'SRC/CMD/APPEND/SYSMAC.LIB'}
    files['SRC/SETENV.BAT'] = files['SRC/SETENV.BAT'].replace(b'set BAKROOT=d:', b'set BAKROOT=c:')
    wrapper = (ROOT / 'guest-build/printer-cpi.asm').read_text()
    for printer in ['4201', '4208']:
        # Use the published .INC data, not the corresponding prebuilt .CPI.
        source = wrapper.replace('INCLUDE CPI_DATA', f'INCLUDE {printer}.INC')
        files[f'SRC/DEV/PRINTER/{printer}/P86CPI.ASM'] = source.replace('\n', '\r\n').encode('ascii')
    commands = ['@echo off', 'c:', 'cd \\src', 'call setenv.bat', 'echo Project86 DOS build > c:\\build.log']
    if replacements:
        commands += ['cd \\src\\p86com',
                'cl -c -AS -Os -Zp comsubs.c >> c:\\build.log', 'if errorlevel 1 goto failed',
                'masm -Mx -t dbcstab.asm; >> c:\\build.log', 'if errorlevel 1 goto failed',
                'lib @comsubs.lbr >> c:\\build.log', 'if errorlevel 1 goto failed',
                'cd \\src\\p86cas',
                'cl -c -AL -Gs -Zl -Os -Zp cassfar.c >> c:\\build.log', 'if errorlevel 1 goto failed',
                'masm -Mx -t cbridge.asm; >> c:\\build.log', 'if errorlevel 1 goto failed',
                'lib @cassfar.lbr >> c:\\build.log', 'if errorlevel 1 goto failed']
    commands += ['cd \\src', 'nmake >> c:\\build.log', 'if errorlevel 1 goto failed']
    for printer in ['4201', '4208']:
        commands += [f'cd \\src\\dev\\printer\\{printer}',
                     'masm P86CPI.ASM; >> c:\\build.log', 'if errorlevel 1 goto failed',
                     'link P86CPI.OBJ; >> c:\\build.log', 'if errorlevel 1 goto failed',
                     f'exe2bin P86CPI.EXE {printer}.CPI >> c:\\build.log', 'if errorlevel 1 goto failed']
    commands += ['echo P86 BUILD SUCCEEDED', 'goto end', ':failed', 'echo P86 BUILD FAILED', ':end']
    files['BUILD.BAT'] = ('\r\n'.join(commands) + '\r\n').encode('ascii')
    hard_path = directory / 'source.img'; hard_path.write_bytes(create_hard_disk(files).image)
    command = [str(ROOT / '.build/p86'), '--disk', str(boot_path), '--hard-disk', str(hard_path), '--write',
               '--command', '', '--command', '', '--command', 'c:', '--command', 'build',
               '--until', 'P86 BUILD', '--limit', '20000000000', '--progress']
    with (directory / 'screen.txt').open('w') as screen, (directory / 'progress.log').open('w') as progress:
        result = subprocess.run(command, stdout=screen, stderr=progress, timeout=900)
    volume = FATVolume(hard_path.read_bytes())
    (directory / 'BUILD.LOG').write_bytes(volume.read('BUILD.LOG'))
    success = result.returncode == 0 and 'P86 BUILD SUCCEEDED' in (directory / 'screen.txt').read_text()
    artifacts, comparisons, outputs = {}, {}, {}
    for name, spec in CATALOG.items():
        try:
            built = guest_output(volume, spec)
            outputs[name] = built
            artifacts[name] = {'sha256': sha(built), 'bytes': len(built), **spec}
            if spec['kind'] == 'source-text': artifacts[name]['source_sha256'] = text_hashes[name]
            if name != 'BOOT.BIN':
                original = bootstrap.read(name)
                comparisons[name] = {'built_sha256': sha(built), 'reference_sha256': sha(original), 'identical': built == original, 'bytes': len(built)}
        except (FileNotFoundError, ValueError) as error:
            artifacts[name] = {'error': str(error)}; success = False
    # A complete boot-sector match excludes only the media-specific BPB/EBPB.
    if 'BOOT.BIN' in outputs:
        sector = outputs['BOOT.BIN']
        boot_code_matches = sector[:11] == bootstrap_data[:11] and sector[62:] == bootstrap_data[62:512]
    else: boot_code_matches = False
    expected_differences = {name: ('Project86 CASSFAR source replacement' if replacements else 'Restore original CASSFAR library') if name == 'SELECT.EXE'
                           else ('COMMAND history/completion and Project86 VER message' if editor else 'Original shell with Project86 VER message') if name == 'COMMAND.COM'
                           else ('Project86 COMSUBS source replacement' if replacements else 'Restore original COMSUBS library')
                           for name in sorted(expected_changes(seed_record, variant))}
    changed_files = {name for name, comparison in comparisons.items() if not comparison['identical']}
    matches_expected = (len(comparisons) == len(CATALOG)-1
                        and changed_files == set(expected_differences)
                        and VER_BANNER.encode('ascii') in outputs.get('COMMAND.COM', b''))
    archive_path = directory / 'dos-files.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in outputs.items(): archive.writestr(zipfile.ZipInfo(name, (1988, 10, 6, 0, 0, 0)), data)
    report = {
        'schema': 7 if editor else 5 if replacements else 6, 'build_succeeded': success, 'emulator_exit_code': result.returncode,
        'build_variant': variant,
        'cpu_model': '286 real-mode subset', 'source_archive_sha256': sha(source_data),
        'seed': seed_record, 'compiler_boot_image_sha256': sha(boot_path.read_bytes()),
        'emulator_sha256': sha((ROOT / '.build/p86').read_bytes()),
        'build_recipe_sha256': sha(Path(__file__).read_bytes()),
        'build_log_sha256': sha((directory / 'BUILD.LOG').read_bytes()),
        'catalog_sha256': sha(CATALOG_PATH.read_bytes()),
        'outputs_archive_sha256': sha(archive_path.read_bytes()),
        'fresh_build_without_distribution_binaries': True, 'removed_prebuilt_inputs': removed,
        'retained_binary_libraries': binary_libraries,
        'binary_library_boundary': ('COMSUBS and CASSFAR use Project86 source. Original compiler tools, SLIBCE.LIB and MEM.LIB remain binary dependencies. This is not a rebuild of every linked library.' if replacements else
                                    'Original compiler tools and COMSUBS.LIB, CASSFAR.LIB, SLIBCE.LIB and MEM.LIB remain binary dependencies. DOS executables are rebuilt; these four libraries and the toolchain are not rebuilt from source.'),
        'source_patches': ['SETENV.BAT: BAKROOT d: to c:',
                           'Assemble published 4201.INC/4208.INC using P86CPI.ASM wrappers, LINK and EXE2BIN',
                           f'{message_path}: message 1040 appends ({VER_BANNER})'] + ([
                           'Remove original INC/COMSUBS.LIB; compile and archive Project86 COMSUBS.C and DBCSTAB.ASM before NMAKE',
                           'Remove original SELECT/CASSFAR.LIB; compile Project86 CASSFAR.C/CBRIDGE.ASM with layout offsets from pinned SELECT declarations'] if replacements else []) +
                          (['COMMAND: interactive history/completion in PCEDIT.ASM, resident PCHIST.INC and transient PCWORK.INC; batch and redirected input retain DOS paths'] if editor else []),
        'ver_message_source_sha256': sha(files[message_path]),
        'printer_wrapper_sha256': sha((ROOT / 'guest-build/printer-cpi.asm').read_bytes()),
        'guest_configuration': 'FILES=64, BUFFERS=20, LASTDRIVE=C, COMMAND.COM /P /E:1024',
        'artifacts': artifacts, 'comparisons': comparisons,
        'all_distribution_files_identical': len(comparisons) == len(CATALOG)-1 and all(r['identical'] for r in comparisons.values()),
        'expected_distribution_differences': expected_differences,
        'distribution_matches_expected': matches_expected,
        'boot_code_identical_outside_media_parameters': boot_code_matches,
    }
    if selected_seed:
        report['seed_artifact_comparisons'] = {
            name: {'built_sha256': sha(outputs[name]) if name in outputs else None,
                   'seed_sha256': sha(data), 'identical': outputs.get(name) == data}
            for name, data in reference_outputs.items()
        }
        report['all_seed_artifacts_identical'] = all(item['identical'] for item in report['seed_artifact_comparisons'].values())
        seed_changes = {name for name, item in report['seed_artifact_comparisons'].items() if not item['identical']}
        report['distribution_matches_expected'] &= seed_changes == set(expected_differences)
    if success and replacements:
        library = volume.read('SRC/INC/COMSUBS.LIB')
        (directory / 'COMSUBS.LIB').write_bytes(library)
        with zipfile.ZipFile(directory / 'comsubs-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in comsubs_sources.items(): archive.writestr(zipfile.ZipInfo(name, (1988, 10, 6, 0, 0, 0)), data)
        report['rebuilt_libraries'] = {'SRC/INC/COMSUBS.LIB': {
            'sha256': sha(library), 'bytes': len(library), 'original_sha256': sha(original_comsubs),
            'source_files': {name: sha(data) for name, data in comsubs_sources.items()},
            'source_archive_sha256': sha((directory / 'comsubs-source.zip').read_bytes()),
        }}
        library = volume.read('SRC/SELECT/CASSFAR.LIB')
        (directory / 'CASSFAR.LIB').write_bytes(library)
        with zipfile.ZipFile(directory / 'cassfar-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in cassfar_sources.items(): archive.writestr(zipfile.ZipInfo(name, (1988, 10, 6, 0, 0, 0)), data)
        report['rebuilt_libraries']['SRC/SELECT/CASSFAR.LIB'] = {
            'sha256': sha(library), 'bytes': len(library), 'original_sha256': sha(original_cassfar),
            'source_files': {name: sha(data) for name, data in cassfar_sources.items()},
            'source_archive_sha256': sha((directory / 'cassfar-source.zip').read_bytes()),
            'layout_generator_sha256': sha((ROOT / 'scripts/cassfar_layout.py').read_bytes()),
        }
    if success and editor:
        recipe = (ROOT / 'scripts/command_source.py').read_bytes()
        with zipfile.ZipFile(directory / 'command-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in {**command_sources, 'PATCH.PY': recipe}.items():
                archive.writestr(zipfile.ZipInfo(name, (1988, 10, 6, 0, 0, 0)), data)
        report['command_editor'] = {
            'source_files': {name: sha(data) for name, data in command_sources.items()},
            'patch_recipe_sha256': sha(recipe),
            'patched_files': {name: sha(files[COMMAND_PREFIX + name]) for name in ['TCODE.ASM','RDATA.ASM','TSPC.ASM','MAKEFILE']},
            'source_archive_sha256': sha((directory / 'command-source.zip').read_bytes()),
            'history_entries': 16, 'history_resident_bytes': 2055, 'line_limit': 127,
        }
    (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['build_succeeded', 'all_distribution_files_identical', 'distribution_matches_expected', 'boot_code_identical_outside_media_parameters']}, indent=2))
    if success: load_build(directory)
    raise SystemExit(0 if success and report['distribution_matches_expected'] and boot_code_matches else 1)


if __name__ == '__main__':
    try: main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
