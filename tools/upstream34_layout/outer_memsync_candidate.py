#!/usr/bin/env python3
"""Build a pinned private outer-ring NOP/ACQUIRE experiment; never install/load."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess

if __package__:
    from . import mec_range, outer_memsync, ring_padding_candidate as common
else:
    import mec_range
    import outer_memsync
    import ring_padding_candidate as common

ROOT = Path(__file__).resolve().parents[2]
SDK_PIN, DRIVER, SOURCE_INPUTS = common.SDK_PIN, common.DRIVER, common.SOURCE_INPUTS
ORIGINAL_SHA = common.ORIGINAL_SHA
SOURCE_PLIST_SHA, CONTROL_PLIST_SHA = common.SOURCE_PLIST_SHA, common.CONTROL_PLIST_SHA
sha, file_sha = common.sha, common.file_sha
control_metadata, sdk_inputs = common.control_metadata, common.sdk_inputs
macho_identity, tree_files = common.macho_identity, common.tree_files
SOURCE_SHA = {
    'nop-prefix': '5c010ac379266cd7ac47292d5037e586baef50479a92286a5c6357b836de04d1',
    'acquire-prefix': 'fffd2bdfea25ca87312679e194949f2538807b43610d157f06c9dde0d33a70d0'}
RECIPE_INPUTS = (
    'tools/upstream34_layout/outer_memsync_candidate.py',
    'tools/upstream34_layout/outer_memsync.py',
    'tools/upstream34_layout/ring_padding_candidate.py',
    'tools/upstream34_layout/ring_padding.py',
    'tools/upstream34_layout/mec_range.py',
    'tests/test_build34_outer_memsync.cpp',
    'tests/test_upstream34_outer_memsync.py',
    'tests/test_upstream34_outer_memsync_candidate.py')


def reviewed_source(original, policy):
    if policy not in SOURCE_SHA:
        raise ValueError('Choose one separately pinned experimental prefix')
    result = outer_memsync.candidate_source(original, policy)
    if sha(result) != SOURCE_SHA[policy]:
        raise ValueError('Outer-ring complete candidate source hash drift')
    return result


def verify_CPU_record(path, policy):
    if policy not in SOURCE_SHA:
        raise ValueError('Unknown candidate policy')
    record = json.loads(Path(path).read_text())
    if (record.get('result') != 'passed' or record.get('sanitizers') != 'ASan/UBSan' or
            record.get('GPU_executed') is not False or record.get('kernel_built') is not False or
            record.get('production_source_modified') is not False or
            record.get('real_IOKit_linked') is not False or
            record.get('equal_footprint_NOP_control') is not True or
            record.get('prefix_dwords') != 8 or
            record.get('complete_source_sha256', {}).get(policy) != SOURCE_SHA[policy]):
        raise ValueError('Requires the reviewed CPU-only actual-function comparison')
    for role in outer_memsync.POLICIES:
        row = record['policies'][role]
        if row.get('passed') is not True or row.get('GPU_executed') is not False or row.get('scenarios') != 36111:
            raise ValueError('Incomplete original/NOP/ACQUIRE CPU comparison')
    for name in ('tools/upstream34_layout/outer_memsync.py',
                 'tests/test_build34_outer_memsync.cpp', 'tests/test_upstream34_outer_memsync.py',
                 'tools/upstream34_layout/ring_padding.py', 'tools/upstream34_layout/mec_range.py'):
        if record['recipe_sha256'].get(name) != file_sha(ROOT / name):
            raise ValueError('CPU-tested recipe drift: ' + name)
    return record


def build(destination, sdk, policy, cpu_record):
    cpu_blob = Path(cpu_record).read_bytes()
    verify_CPU_record(cpu_record, policy)
    if Path(cpu_record).read_bytes() != cpu_blob:
        raise ValueError('CPU record changed during verification')
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise RuntimeError('Requires native Intel macOS; no cross-target fallback')
    destination = Path(destination).resolve()
    if ROOT / 'build' not in destination.parents or destination.exists():
        raise ValueError('Use a fresh private destination inside this worktree build directory')
    protected_blobs = mec_range.protected_base_inputs()
    protected = mec_range.verify_current_inputs(protected_blobs, ROOT)
    source_blobs = {name: mec_range.read_base(name) for name in SOURCE_INPUTS}
    for name, blob in source_blobs.items():
        if (ROOT / name).read_bytes() != blob:
            raise ValueError('Source input drift: ' + name)
    proposed = reviewed_source(source_blobs[DRIVER], policy)
    packaged_plist = control_metadata(source_blobs['src/phxbringup/Info.plist'])
    sdk_blobs = sdk_inputs(sdk)
    recipe_paths = tuple(ROOT / name for name in RECIPE_INPUTS)
    recipes = {path: path.read_bytes() for path in recipe_paths}
    destination.mkdir(parents=True, mode=0o700)
    (destination / 'CPU-report-private.json').write_bytes(cpu_blob)
    source = destination / 'source'
    sdk_copy = destination / 'MacKernelSDK-pinned-private'
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang'], text=True,
                                           timeout=15).strip()).resolve()
    linker = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'ld'], text=True,
                                         timeout=15).strip()).resolve()
    resource = Path(subprocess.check_output([str(compiler), '-print-resource-dir'], text=True,
                                           timeout=15).strip()).resolve()
    host_sdk = Path(subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-path'], text=True,
                                           timeout=15).strip()).resolve()
    tool_paths = (compiler, linker, Path('/usr/bin/codesign'), Path('/usr/bin/lipo'), Path('/bin/sh'),
                  resource / 'lib/darwin/libclang_rt.cc_kext.a', compiler.parent.parent / 'lib/libLTO.dylib',
                  host_sdk / 'SDKSettings.json', host_sdk / 'SDKSettings.plist')
    tools = {path: file_sha(path) for path in tool_paths}
    environment = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin',
                   'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(destination / 'tmp-private')}
    (destination / 'tmp-private').mkdir()
    for name, blob in source_blobs.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(proposed if name == DRIVER else blob)
    for name, blob in sdk_blobs.items():
        path = sdk_copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    for path, blob in recipes.items():
        frozen = destination / 'recipe-private' / path.relative_to(ROOT)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_bytes(blob)
    report = {'result': 'source-frozen', 'identity_class': 'original34-derived-outer-' + policy + '-experimental',
              'base_commit': mec_range.BASE, 'sdk_commit': SDK_PIN,
              'policy': policy, 'CPU_record_sha256': sha(cpu_blob),
              'original_driver_sha256': ORIGINAL_SHA, 'candidate_driver_sha256': SOURCE_SHA[policy],
              'production_protected_sha256': protected,
              'source_sha256': {name: sha(proposed if name == DRIVER else blob)
                                for name, blob in source_blobs.items()},
              'recipe_sha256': {str(path.relative_to(ROOT)): sha(blob) for path, blob in recipes.items()},
              'sdk_files_sha256': {name: sha(blob) for name, blob in sdk_blobs.items()},
              'toolchain_sha256_private': {str(path): digest for path, digest in tools.items()},
              'checks': [], 'kernel_built': False, 'installed': False, 'loaded': False,
              'GPU_executed': False, 'hardware_scope_armed': False,
              'untouched_original_admission_changed': False, 'production_source_modified': False,
              'metadata_build_marker_unchanged': True,
              'packaging_metadata': {'source_plist_sha256': SOURCE_PLIST_SHA,
                                     'control_matching_plist_sha256': CONTROL_PLIST_SHA,
                                     'only_change': 'IOPCIMatch restricted to 0x19001002, byte-identical to the original deployed control bundle',
                                     'production_plist_modified': False},
              'limitation': 'Build and static identity only. The unchanged build marker is not candidate admission. No installation, load, initialization, GPU test or repair acceptance.'}
    def save():
        (destination / 'build-report-private.json').write_text(json.dumps(report, indent=2) + '\n')
    def command(name, argv):
        result = subprocess.run(argv, cwd=source, env=environment, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=120)
        log = result.stdout + result.stderr
        (destination / (name + '-private.log')).write_bytes(log)
        report['checks'].append({'name': name, 'exit_code': result.returncode, 'log_sha256': sha(log)})
        save()
        if result.returncode:
            raise RuntimeError(name + ' failed; inspect the retained private build log')
    save()
    try:
        command('compile', ['/bin/sh', str(source / 'src/phxbringup/build.sh'), str(sdk_copy)])
        bundle = destination / ('original34-derived-outer-' + policy + '-experimental.kext')
        shutil.copytree(source / 'src/phxbringup/build/PhxBringup.kext', bundle)
        (bundle / 'Contents/Info.plist').write_bytes(packaged_plist)
        binary = bundle / 'Contents/MacOS/PhxBringup'
        before_sign = macho_identity(binary.read_bytes())
        command('sign', ['/usr/bin/codesign', '--force', '--sign', '-', str(bundle)])
        command('signature', ['/usr/bin/codesign', '--verify', '--strict', str(bundle)])
        command('architecture', ['/usr/bin/lipo', str(binary), '-verify_arch', 'x86_64'])
        identity = macho_identity(binary.read_bytes())
        if before_sign['image_uuid_private'] != identity['image_uuid_private']:
            raise ValueError('Image identity changed across signing')
        for name, blob in source_blobs.items():
            if (source / name).read_bytes() != (proposed if name == DRIVER else blob):
                raise ValueError('Frozen source changed during compilation')
            if (ROOT / name).read_bytes() != blob:
                raise ValueError('Production source changed during compilation')
        if (bundle / 'Contents/Info.plist').read_bytes() != packaged_plist:
            raise ValueError('Candidate bundle metadata drift')
        for name, blob in sdk_blobs.items():
            if (sdk_copy / name).read_bytes() != blob:
                raise ValueError('SDK changed during compilation')
        mec_range.verify_current_inputs(protected_blobs, ROOT)
        if any(path.read_bytes() != blob for path, blob in recipes.items()):
            raise ValueError('Recipe changed during compilation')
        if Path(cpu_record).read_bytes() != cpu_blob:
            raise ValueError('CPU record changed during compilation')
        if any(file_sha(path) != digest for path, digest in tools.items()):
            raise ValueError('Toolchain changed during compilation')
        report.update(result='built-and-statically-verified-not-installed', kernel_built=True,
                      candidate_identity_private=identity, candidate_bundle_files_sha256=tree_files(bundle))
        save()
    except BaseException as error:
        report.update(result='failed-retained-for-review', error_type=type(error).__name__)
        save()
        raise
    print(json.dumps({key: report[key] for key in ('result', 'identity_class', 'kernel_built',
                      'installed', 'loaded', 'GPU_executed', 'hardware_scope_armed')}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--policy', choices=tuple(SOURCE_SHA), required=True)
    parser.add_argument('--CPU-record', type=Path, required=True)
    args = parser.parse_args()
    build(args.out, args.sdk, args.policy, args.CPU_record)
