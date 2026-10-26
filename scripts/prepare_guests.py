#!/usr/bin/env python3
"""Create the app floppy entirely from our DOS build and explicit guest additions."""
import argparse
import io
import json
from pathlib import Path
import zipfile
from disk_image import FATVolume, create_floppy, root_files
from dos_artifacts import DEFAULT_BUILD, ROOT, CATALOG, DOS_FILES, SYSTEM_FILES, load_build, sha
from cutemouse_artifacts import DEFAULT_MOUSE_BUILD, load_mouse_build

OUTPUT = ROOT / '.build/guest-boot'
ADDITIONS = {'CTMOUSE.EXE', 'CONFIG.SYS', 'AUTOEXEC.BAT', 'P86BUILD.TXT', 'P86FILES.TXT'}
LIBRARY_SOURCES = {'SRC/INC/COMSUBS.LIB': 'comsubs-source.zip',
                   'SRC/SELECT/CASSFAR.LIB': 'cassfar-source.zip'}


def verify_image(directory):
    directory = Path(directory)
    receipt = json.loads((directory / 'project86-boot.json').read_bytes())
    data = (directory / 'project86.ima').read_bytes()
    if receipt['schema'] != 3 or receipt['system_origin'] != 'Project86 complete DOS source rebuild':
        raise ValueError('A complete rebuilt-DOS boot-image receipt is required')
    if sha(data) != receipt['image_sha256']:
        raise ValueError('Boot image does not match its packaging receipt')
    volume = FATVolume(data)
    files = root_files(volume)
    if set(files) != set(DOS_FILES) | ADDITIONS or set(receipt['files']) != set(files):
        raise ValueError('Missing or unaccounted-for files in the DOS boot image')
    if sha(data[:512]) != receipt['boot_sector']['installed_sha256']:
        raise ValueError('Boot sector does not match the packaging receipt')
    for name, contents in files.items():
        expected = receipt['files'][name]
        if sha(contents) != expected['sha256'] or len(contents) != expected['bytes']:
            raise ValueError(f'Packaged {name} does not match its build output')
        if name in DOS_FILES and expected['origin'] != DOS_FILES[name]['kind']:
            raise ValueError(f'Unexpected origin for {name}')
    if receipt['files']['CTMOUSE.EXE']['origin'] != 'source-built-driver':
        raise ValueError('CuteMouse must come from our source build')
    for name, field in [('cutemouse-source.zip', 'corresponding_source_sha256'), ('CUTEMOUSE-COPYING.txt', 'license_sha256')]:
        if sha((directory / name).read_bytes()) != receipt['mouse_build'][field]:
            raise ValueError(f'{name} does not match the CuteMouse build receipt')
    replacements = receipt['build'].get('rebuilt_libraries', {})
    package_field = 'project_sources_sha256' if 'project_sources_sha256' in receipt else 'library_sources_sha256'
    package_name = 'dos-project-sources.zip' if package_field == 'project_sources_sha256' else 'dos-library-sources.zip'
    if 'command_editor' in receipt['build'] and package_field not in receipt:
        raise ValueError('COMMAND corresponding source package is required')
    if package_field in receipt:
        archive_data = (directory / package_name).read_bytes()
        if sha(archive_data) != receipt[package_field]:
            raise ValueError('DOS library source package does not match the receipt')
        expected = {'BUILD-INFO.txt'} | {name for path, name in LIBRARY_SOURCES.items() if path in replacements}
        if 'command_editor' in receipt['build']: expected.add('command-source.zip')
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            if len(archive.namelist()) != len(expected) or set(archive.namelist()) != expected:
                raise ValueError('Unexpected DOS library source package contents')
            if archive.read('BUILD-INFO.txt') != (receipt['build']['binary_library_boundary'] + '\n').encode():
                raise ValueError('DOS library source package has stale build information')
            for path, name in LIBRARY_SOURCES.items():
                if path in replacements and sha(archive.read(name)) != replacements[path]['source_archive_sha256']:
                    raise ValueError(f'{Path(path).stem} corresponding source does not match the build receipt')
            if 'command_editor' in receipt['build']:
                if sha(archive.read('command-source.zip')) != receipt['build']['command_editor']['source_archive_sha256']:
                    raise ValueError('COMMAND corresponding source does not match the build receipt')
    for path, name in LIBRARY_SOURCES.items():
        # Legacy receipts require the individual ZIPs. New app bundles carry
        # the verified aggregate; development/seed directories may retain both.
        source = directory / name
        if path in replacements and (source.exists() or package_field not in receipt):
            if sha(source.read_bytes()) != replacements[path]['source_archive_sha256']:
                raise ValueError(f'{Path(path).stem} corresponding source does not match the build receipt')
        elif source.exists() and package_field in receipt:
            raise ValueError(f'Unused library source package: {name}')
    return receipt


def verify_dos_build_image(directory, dos_build):
    receipt = verify_image(directory)
    binaries, build_record = load_build(dos_build)
    if receipt['build'] != build_record:
        raise ValueError('Boot image belongs to a different DOS build; run make guests')
    if receipt['boot_sector']['source_sha256'] != sha(binaries['BOOT.BIN']):
        raise ValueError('Boot image has stale boot code; run make guests')
    data = (Path(directory) / 'project86.ima').read_bytes()
    files = root_files(FATVolume(data))
    for name in DOS_FILES:
        if files[name] != binaries[name]:
            raise ValueError(f'Boot image has stale {name}; run make guests')
    # Reconstruct independently from declared inputs, including blank free space.
    expected = create_floppy(binaries['BOOT.BIN'], files)
    if bytes(expected.image) != data:
        raise ValueError('Boot sector, filesystem layout or free space differs from the source-built image')
    return receipt


def verify_build_image(directory, dos_build, mouse_build=DEFAULT_MOUSE_BUILD):
    receipt = verify_dos_build_image(directory, dos_build)
    driver, mouse_record = load_mouse_build(mouse_build)
    files = root_files(FATVolume((Path(directory) / 'project86.ima').read_bytes()))
    if receipt['mouse_build'] != mouse_record or files['CTMOUSE.EXE'] != driver:
        raise ValueError('Boot image belongs to a different CuteMouse build; run make guests')
    return receipt


def prepare(dos_build=DEFAULT_BUILD, output=OUTPUT, mouse_build=DEFAULT_MOUSE_BUILD):
    binaries, build_record = load_build(dos_build)
    driver, mouse_record = load_mouse_build(mouse_build)
    files = {name: binaries[name] for name in DOS_FILES}
    files['CTMOUSE.EXE'] = driver
    files['CONFIG.SYS'] = b'FILES=64\r\nBUFFERS=20\r\nLASTDRIVE=C\r\n'
    files['AUTOEXEC.BAT'] = (b'@echo off\r\nPROMPT $P$G\r\nSET BLASTER=A220 I5 D1 T3\r\n'
                             b'a:\\ctmouse /s1 /y >nul\r\n'
                             b'if errorlevel 3 echo Mouse driver unavailable.\r\n'
                             b'echo.\r\necho MS-DOS 4.0 (Project86)\r\n')
    note = ['Project86: complete MS-DOS built inside our own emulator.',
            'Boot sector, kernel, commands, drivers and data use our source build.',
            '62 DOS files: 60 rebuilt outputs and 2 unchanged text source profiles.',
            'Build uses original tools and supplied binary support/runtime libraries.',
            'COMMAND.COM VER identifies this Project86 source build.',
            'No DOS content is copied from the downloaded bootstrap image.',
            'P86FILES.TXT lists every DOS file and its SHA-256 hash.',
            'CuteMouse 2.1 beta4 is also assembled from source on this ARM Mac.', '']
    if 'rebuilt_libraries' in build_record:
        note += ['COMSUBS is compiled from our source.', '']
    if 'SRC/SELECT/CASSFAR.LIB' in build_record.get('rebuilt_libraries', {}):
        note += ['CASSFAR also uses our source; SLIBCE and MEM remain binary libraries.', '']
    if 'command_editor' in build_record:
        note += ['COMMAND.COM adds 16-entry session history (Up/Down) and Tab filename completion.', '']
    for name in ['BOOT.BIN', *SYSTEM_FILES]: note += [name + ' SHA-256:', sha(binaries[name]), '']
    files['P86BUILD.TXT'] = ('\r\n'.join(note) + '\r\n').encode('ascii')
    files['P86FILES.TXT'] = ('\r\n'.join(f'{name:<12} {sha(data)}' for name, data in {**binaries, 'CTMOUSE.EXE': driver}.items()) + '\r\n').encode('ascii')
    volume = create_floppy(binaries['BOOT.BIN'], files)
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    build_path = Path(dos_build).resolve()
    try: source_directory = str(build_path.relative_to(ROOT))
    except ValueError: source_directory = str(build_path)
    receipt = {
        'schema': 3, 'system_origin': 'Project86 complete DOS source rebuild',
        'build_directory': source_directory, 'build': build_record,
        'mouse_build': mouse_record,
        'retained_from_bootstrap': [], 'dos_file_count': len(DOS_FILES),
        'boot_sector': {'source_sha256': sha(binaries['BOOT.BIN']), 'installed_sha256': sha(volume.image[:512]),
                        'guest_output': CATALOG['BOOT.BIN']['guest_output'],
                        'extraction_offset': 0x7c00, 'extraction_bytes': 512,
                        'media_parameter_bytes': [11, 62],
                        'media_configuration': 'Generated 1.44 MiB FAT12 BPB/EBPB; all other bytes use assembled boot code'},
        'files': {name: {'sha256': sha(data), 'bytes': len(data),
                         'origin': DOS_FILES[name]['kind'] if name in DOS_FILES else 'source-built-driver' if name == 'CTMOUSE.EXE' else 'project-configuration',
                         **({'guest_output': DOS_FILES[name]['guest_output']} if name in DOS_FILES else {})} for name, data in files.items()},
        'image_sha256': sha(volume.image),
    }
    source_data = {'BUILD-INFO.txt': (build_record['binary_library_boundary'] + '\n').encode()}
    for path, name in LIBRARY_SOURCES.items():
        if path in build_record.get('rebuilt_libraries', {}):
            source_data[name] = (Path(dos_build) / name).read_bytes()
    if 'command_editor' in build_record:
        source_data['command-source.zip'] = (Path(dos_build) / 'command-source.zip').read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in source_data.items():
            archive.writestr(zipfile.ZipInfo(name, (1988, 10, 6, 0, 0, 0)), data)
    receipt['project_sources_sha256'] = sha(buffer.getvalue())
    outputs = [('project86.ima', bytes(volume.image)), ('project86-boot.json', (json.dumps(receipt, indent=2)+'\n').encode()),
               ('dos-project-sources.zip', buffer.getvalue())]
    outputs += [(name, (Path(mouse_build)/name).read_bytes()) for name in ['cutemouse-source.zip', 'CUTEMOUSE-COPYING.txt']]
    if 'rebuilt_libraries' in build_record:
        outputs.append(('comsubs-source.zip', (Path(dos_build) / 'comsubs-source.zip').read_bytes()))
    if 'SRC/SELECT/CASSFAR.LIB' in build_record.get('rebuilt_libraries', {}):
        outputs.append(('cassfar-source.zip', (Path(dos_build) / 'cassfar-source.zip').read_bytes()))
    # Xcode's script sandbox needs individual files, including the optional
    # schema-3 seed evidence. Legacy build directories do not have these files.
    seed_inputs = []
    if 'seed' in build_record:
        seed_inputs = ['seed.ima', 'boot.ima']
        if build_record['seed']['kind'] == 'rebuilt-dos':
            seed_inputs += ['seed-receipt.json', 'seed-build-report.json']
    if 'rebuilt_libraries' in build_record:
        seed_inputs += ['COMSUBS.LIB', 'comsubs-source.zip']
    if 'SRC/SELECT/CASSFAR.LIB' in build_record.get('rebuilt_libraries', {}):
        seed_inputs += ['CASSFAR.LIB', 'cassfar-source.zip']
    if 'command_editor' in build_record:
        seed_inputs += ['command-source.zip']
    input_list = ''.join(f'$(P86_DOS_BUILD_DIR)/{name}\n' for name in seed_inputs)
    outputs.append(('dos-build-inputs.xcfilelist', input_list.encode()))
    for path, name in LIBRARY_SOURCES.items():
        if path not in build_record.get('rebuilt_libraries', {}):
            (output / name).unlink(missing_ok=True)
    (output / 'dos-library-sources.zip').unlink(missing_ok=True)
    for name, data in outputs:
        target = output / name; temp = target.with_suffix(target.suffix + '.tmp')
        temp.write_bytes(data); temp.replace(target)
    verify_build_image(output, dos_build, mouse_build)
    print(f'Prepared {output / "project86.ima"}: assembled boot sector and {len(DOS_FILES)} DOS files from {source_directory}')
    return output / 'project86.ima'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dos-build', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--mouse-build', type=Path, default=DEFAULT_MOUSE_BUILD)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--verify', type=Path, metavar='DIRECTORY')
    parser.add_argument('--check-build', action='store_true')
    args = parser.parse_args()
    try:
        if args.verify:
            verify_build_image(args.verify, args.dos_build, args.mouse_build) if args.check_build else verify_image(args.verify)
            print(f'Verified complete rebuilt-DOS boot image: {args.verify}')
        else: prepare(args.dos_build, args.output, args.mouse_build)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
