#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a private PhxAccel control/firmware-observer pair; never install it."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import time

import build34_dcn_firmware_observation_stage as observer_stage
import check_build34_cache_metadata as cache_metadata
from upstream34_layout import ring_padding_candidate as common


ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = 'd182b7695fe24b061cce08361838ab41d8fea2cf'
TOOL_SOURCE_COMMIT = 'c76dae221fd8db91ced4db7698c1e327aba73174'
EVIDENCE = ROOT / 'docs/validation/build34-dcn-firmware-observer-source-20261126.json'
SOURCE_ROOTS = ('src/phxaccel',)
LICENSE_PATHS = ('LICENSE', 'LICENSES', 'THIRD_PARTY_NOTICES.md')
FRAMEBUFFER = 'src/phxaccel/accel/phxfb.cpp'
BUNDLE = 'PhxAccel.kext'
EXECUTABLE = 'Contents/MacOS/PhxAccel'
INSTALLED_EXECUTABLE = Path('/Library/Extensions/PhxAccel.kext') / EXECUTABLE
INSTALLED_BUNDLE = INSTALLED_EXECUTABLE.parent.parent.parent
BOOT_CACHE = Path('/System/Library/KernelCollections/BootKernelExtensions.kc')
SYSTEM_CACHE = Path('/System/Library/KernelCollections/SystemKernelExtensions.kc')
AUX_CACHE = Path('/Library/KernelCollections/AuxiliaryKernelExtensions.kc')
REPOSITORIES = (Path('/Library/Extensions'), Path('/Library/Apple/System/Library/Extensions'))
LINK_LOCK = Path('/var/run/nullarc-build34-dcn-firmware-observer-link.lock')
SCANOUT_GATE = ROOT / 'tools/build34_scanout_mode_gate.swift'
SCANOUT_OUTPUT = 'build34 scanout baseline: 1280x800 logical / 2560x1600 pixels / 120 Hz / 2x'
SCANOUT_MAX_AGE_NS = 120_000_000_000
TOOLS = (
    ROOT / 'tools/build34_dcn_firmware_observation_stage.py',
    ROOT / 'tools/build34_dcn_firmware_home_stage.py',
    ROOT / 'tools/build34_dcn_route_observation.py',
    ROOT / 'tools/build34_exact_submit.py',
    SCANOUT_GATE,
    EVIDENCE,
)
SUPPORT_HEADERS = (
    'build34_dcn_descriptor_backing.h',
    'build34_dcn_firmware_aperture.h',
    'build34_dcn_firmware_home.h',
    'build34_dcn_flat_context.h',
    'build34_dcn_flip_geometry.h',
    'build34_dcn_flip_program.h',
    'build34_dcn_flip_readback.h',
    'build34_dcn_page_layout.h',
    'build34_dcn_render_lease.h',
    'build34_dcn_scanout_pin.h',
)
TOOL_INPUTS = tuple(ROOT / 'tools' / name for name in (
    'build34_dcn_firmware_observation_stage.py',
    'build34_dcn_firmware_home_stage.py',
    'build34_dcn_route_observation.py',
    'build34_exact_submit.py',
    'build34_scanout_mode_gate.swift',
    *SUPPORT_HEADERS,
))


def git(*args):
    return subprocess.check_output(['/usr/bin/git', *args], cwd=ROOT, timeout=30)


def private_output(out):
    out = out.resolve()
    if ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Use a named ignored output below the worktree build directory')
    git('check-ignore', '-q', str(out))
    if git('branch', '--show-current').strip() != b'upstream34/vram-layout-fix':
        raise ValueError('Require default build34 branch')
    return out


def source_names():
    names = set()
    for root in SOURCE_ROOTS + LICENSE_PATHS:
        names.update(git('ls-tree', '-r', '--name-only', SOURCE_COMMIT, '--', root).decode().splitlines())
    if not names or FRAMEBUFFER not in names:
        raise ValueError('Incomplete pinned PhxAccel input set')
    return tuple(sorted(names))


def read_sources():
    if git('diff', '--name-only', SOURCE_COMMIT, '--', *SOURCE_ROOTS, *LICENSE_PATHS).strip():
        raise ValueError('PhxAccel source or license inputs drifted from the reviewed checkpoint')
    baseline = {name: git('show', SOURCE_COMMIT + ':' + name) for name in source_names()}
    for name, blob in baseline.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != blob:
            raise ValueError('Working input differs from the pinned PhxAccel source tree')
    candidate = dict(baseline)
    candidate[FRAMEBUFFER] = observer_stage.stage(baseline[FRAMEBUFFER]).encode()
    return baseline, candidate


def read_tool_inputs():
    result = {}
    for path in TOOL_INPUTS:
        relative = path.relative_to(ROOT).as_posix()
        pinned = git('show', TOOL_SOURCE_COMMIT + ':' + relative)
        if path.is_symlink() or not path.is_file() or path.read_bytes() != pinned:
            raise ValueError('Pinned observer support input drifted')
        result[relative] = pinned
    return result


def validate_evidence(baseline, candidate):
    evidence = json.loads(EVIDENCE.read_text())
    checks = (
        evidence['status'] == 'private-native-build-one-shot-firmware-hubp-observer-not-loaded',
        evidence['based_on_commit'] == SOURCE_COMMIT,
        evidence['phxfb_source_sha256'] == common.sha(baseline[FRAMEBUFFER]),
        evidence['overlay_phxfb_source_sha256'] == common.sha(candidate[FRAMEBUFFER]),
        evidence['observer_stage_sha256'] == common.file_sha(TOOL_INPUTS[0]),
        evidence['route_reader_sha256'] == common.file_sha(TOOLS[2]),
        evidence['control_binary_sha256'] == '8e677b77caa23f404e3a011ca0648fd839bd6ab9264d8697e27f8e2e70997564',
        evidence['observer_binary_sha256'] == '6543861256208467f1833be11176be9a83207bd2a348f7fa3159645e10790ff0',
    )
    if not all(checks):
        raise ValueError('Observer source/evidence pin mismatch')
    if not INSTALLED_EXECUTABLE.is_file() or INSTALLED_EXECUTABLE.is_symlink():
        raise ValueError('Accepted on-disk PhxAccel executable unavailable')
    if common.file_sha(INSTALLED_EXECUTABLE) != evidence['control_binary_sha256']:
        raise ValueError('Installed PhxAccel differs from the exact control build')
    return evidence


def materialize(root, blobs):
    for name, blob in blobs.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)


def import_set(binary):
    output = subprocess.check_output(['/usr/bin/nm', '-arch', 'x86_64', '-u', str(binary)], timeout=15)
    return sorted(line.split()[-1].decode() for line in output.splitlines() if line.split())


def complete_cache_capture(auxiliary):
    result = subprocess.run(['/usr/bin/kmutil', 'inspect', '-a', 'x86_64', '-B', str(BOOT_CACHE),
        '-S', str(SYSTEM_CACHE), '-A', str(auxiliary), '--show-prelink-info'],
        capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Complete boot/system/auxiliary cache inspection refused')
    return result.stdout


def protected_disk_snapshot():
    paths = (BOOT_CACHE, SYSTEM_CACHE, AUX_CACHE, INSTALLED_BUNDLE / 'Contents/Info.plist', INSTALLED_EXECUTABLE)
    snapshot = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError('Protected installed cache or PhxAccel input is not a regular file')
        snapshot[str(path)] = common.file_sha(path)
    for repository in REPOSITORIES:
        if repository.is_symlink() or not repository.is_dir():
            raise ValueError('Standard extension repository unavailable')
    return snapshot


def bundle_nodes(root):
    root = Path(root)
    nodes = {'': root.lstat()}
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories + files:
            path = current_path / name
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError('Only regular files and directories are admitted in PhxAccel bundles')
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError('Hard-linked PhxAccel files are refused')
            if getattr(info, 'st_flags', 0):
                raise ValueError('Flagged PhxAccel bundle inputs are refused for temporary replacement')
            nodes[relative] = info
    return nodes


def apply_bundle_metadata(source, destination, reference):
    nodes = bundle_nodes(reference)
    if set(nodes) != set(bundle_nodes(source)):
        raise ValueError('Candidate bundle node set differs from installed bundle')
    for relative, info in sorted(nodes.items(), key=lambda item: item[0].count('/'), reverse=True):
        path = destination if not relative else destination / relative
        os.chown(path, info.st_uid, info.st_gid, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            os.chmod(path, stat.S_IMODE(info.st_mode))
        else:
            os.chmod(path, stat.S_IMODE(info.st_mode))


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def mode_report_path(out, report):
    out = private_output(out)
    output_info = out.lstat()
    if not stat.S_ISDIR(output_info.st_mode) or stat.S_IMODE(output_info.st_mode) != 0o700 or \
            output_info.st_uid != os.getuid():
        raise ValueError('Private candidate directory must be user-owned with mode 0700')
    report = Path(report)
    if report.is_symlink() or report.parent.resolve() != out or not report.name.endswith('-private.json'):
        raise ValueError('Native 2x report must be a private JSON file in the candidate directory')
    return report


def write_scanout_mode_report(out, report):
    out = private_output(out)
    report = mode_report_path(out, report)
    if not out.is_dir() or out.is_symlink() or report.exists() or report.is_symlink():
        raise ValueError('Fresh private output and unused native 2x report path required')
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Native 2x mode preflight requires the target macOS host')
    result = subprocess.run(['/usr/bin/xcrun', 'swift', str(SCANOUT_GATE)], cwd=ROOT,
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    if result.returncode or result.stdout.decode(errors='replace').strip() != SCANOUT_OUTPUT:
        raise ValueError('Native 2x scanout gate refused or returned unexpected output')
    version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], timeout=10).decode().strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], timeout=10).decode().strip()
    created_ns = time.time_ns()
    payload = json.dumps(dict(status='passed-native-2x-scanout-mode-preflight',
        gate_source_sha256=common.file_sha(SCANOUT_GATE),
        gate_output_sha256=common.sha(SCANOUT_OUTPUT.encode()),
        os_version=version, os_build=os_build, created_unix_ns=created_ns,
        logical_width=1280, logical_height=800, backing_width=2560,
        backing_height=1600, refresh_hz=120.0, appkit_backing_scale=2.0),
        sort_keys=True, separators=(',', ':')).encode() + b'\n'
    temporary = report.with_name(report.name + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb', closefd=False) as output:
            output.write(payload)
            output.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.rename(temporary, report)
    sync_directory(out)
    return dict(status='passed-native-2x-scanout-mode-preflight',
                report=str(report), report_sha256=common.sha(payload))


def validate_scanout_mode_report(report, version, os_build, now_ns=None):
    descriptor = os.open(report, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or \
                info.st_uid != os.getuid() or info.st_size > 4096:
            raise ValueError('Native 2x report must be a private regular file')
        payload = os.read(descriptor, 4097)
    finally:
        os.close(descriptor)
    if len(payload) != info.st_size:
        raise ValueError('Native 2x report changed or exceeded its size bound')
    data = json.loads(payload)
    expected = dict(status='passed-native-2x-scanout-mode-preflight',
        gate_source_sha256=common.file_sha(SCANOUT_GATE),
        gate_output_sha256=common.sha(SCANOUT_OUTPUT.encode()),
        os_version=version, os_build=os_build, logical_width=1280,
        logical_height=800, backing_width=2560, backing_height=1600,
        refresh_hz=120.0, appkit_backing_scale=2.0)
    if type(data) is not dict or set(data) != set(expected) | {'created_unix_ns'}:
        raise ValueError('Native 2x report has an unexpected schema')
    created_ns = data.pop('created_unix_ns')
    if type(created_ns) is not int or any(data.get(key) != value for key, value in expected.items()):
        raise ValueError('Native 2x report does not match the current gate and OS')
    now_ns = time.time_ns() if now_ns is None else now_ns
    if created_ns > now_ns + 1_000_000_000 or now_ns - created_ns > SCANOUT_MAX_AGE_NS or \
            abs(info.st_mtime_ns - created_ns) > 5_000_000_000:
        raise ValueError('Native 2x report is stale or has an invalid timestamp')
    return dict(report_sha256=common.sha(payload), created_unix_ns=created_ns)


def restore_standard_bundle(installed, backup, staged, baseline_manifest, candidate_manifest):
    if not backup.exists():
        if not installed.exists() or common.tree_files(installed) != baseline_manifest:
            raise RuntimeError('Original PhxAccel bundle is not at its accepted path and backup is missing')
        if staged.exists():
            if common.tree_files(staged) != candidate_manifest:
                raise RuntimeError('Unexpected staged bundle prevents safe cleanup')
            shutil.rmtree(staged)
        return
    if installed.exists():
        if common.tree_files(installed) != candidate_manifest:
            raise RuntimeError('Unexpected bundle occupies the accepted PhxAccel path')
        if staged.exists():
            raise RuntimeError('Temporary restore target already exists')
        os.rename(installed, staged)
    os.rename(backup, installed)
    sync_directory(installed.parent)
    if common.tree_files(installed) != baseline_manifest:
        raise RuntimeError('Original PhxAccel bundle failed exact restoration readback')
    subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(installed)],
                   capture_output=True, check=True, timeout=20)
    if staged.exists():
        if common.tree_files(staged) != candidate_manifest:
            raise RuntimeError('Staged observer bundle changed before cleanup')
        shutil.rmtree(staged)


def link_with_temporary_standard_bundle(installed, candidate, backup, staged,
                                       baseline_manifest, candidate_manifest, link):
    try:
        shutil.copytree(candidate, staged, copy_function=shutil.copy2)
        apply_bundle_metadata(candidate, staged, installed)
        if common.tree_files(staged) != candidate_manifest:
            raise ValueError('Staged observer bundle differs from its sealed candidate')
        os.rename(installed, backup)
        os.rename(staged, installed)
        sync_directory(installed.parent)
        subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(installed)],
                       capture_output=True, check=True, timeout=20)
        return link()
    finally:
        restore_standard_bundle(installed, backup, staged, baseline_manifest, candidate_manifest)


def link_auxkc(out, kdk, mode_report):
    out = private_output(out)
    if os.geteuid() != 0:
        raise PermissionError('Temporary standard-path AuxKC input requires the scoped root wrapper')
    os.umask(0o077)
    if not out.is_dir() or out.is_symlink():
        raise ValueError('Private candidate build directory unavailable')
    if not kdk.is_dir() or not (kdk / 'System/Library/KernelCollections').is_dir():
        raise ValueError('Matching installed KDK bundle unavailable')
    version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], timeout=10).decode().strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], timeout=10).decode().strip()
    if (version, os_build) != ('26.7.2', '25G332'):
        raise ValueError('AuxKC link scope requires the reviewed OS/KDK build')
    mode_report = mode_report_path(out, mode_report)
    mode_preflight = validate_scanout_mode_report(mode_report, version, os_build)
    verified = verify(out)
    if verified['status'] != 'passed-independent-private-dcn-firmware-observer-readback':
        raise ValueError('Independent candidate bundle readback required before cache link')
    control = out / 'control' / BUNDLE
    candidate = out / 'observer' / BUNDLE
    if common.tree_files(control) != common.tree_files(INSTALLED_BUNDLE):
        raise ValueError('Installed PhxAccel bundle differs from exact control bundle')
    if common.tree_files(candidate).get(EXECUTABLE) != '6543861256208467f1833be11176be9a83207bd2a348f7fa3159645e10790ff0':
        raise ValueError('Observer executable identity changed before cache link')
    snapshot = protected_disk_snapshot()
    baseline = complete_cache_capture(AUX_CACHE)
    collections, entries = cache_metadata.parse_capture(baseline)
    if len(entries) != 416 or sum('OSBundleUUID' not in row for row in entries.values()) != 29:
        raise ValueError('Accepted complete AuxKC baseline is not 416 records/29 codeless entries')
    auxiliary_rows = collections[2]['_PrelinkInfoDictionary']
    identifiers = [row.get('CFBundleIdentifier') for row in auxiliary_rows]
    if len(identifiers) != 4 or identifiers.count('com.luuumi.PhxAccel') != 1:
        raise ValueError('Accepted auxiliary collection does not have the exact expected four records')
    output = out / 'observer-AuxiliaryKernelExtensions.kc'
    if output.exists() or output.is_symlink():
        raise ValueError('Refusing to overwrite a private auxiliary collection')
    command = ['/usr/bin/kmutil', 'create', '-a', 'x86_64', '-n', 'aux', '--volume-root', '/',
        '--kernel', '/System/Library/Kernels/kernel', '--boot-path', str(BOOT_CACHE),
        '--system-path', str(SYSTEM_CACHE), '--auxiliary-path', str(output),
        '--explicit-only', '--no-system-collection',
        '--kdk', str(kdk), '--build', os_build, '--authentication']
    for identifier in identifiers:
        if identifier != 'com.luuumi.PhxAccel':
            command.extend(['--bundle-identifier', identifier])
    for repository in REPOSITORIES:
        command.extend(['--repository', str(repository)])
    baseline_manifest = common.tree_files(INSTALLED_BUNDLE)
    candidate_manifest = common.tree_files(candidate)
    backup = INSTALLED_BUNDLE.with_name(INSTALLED_BUNDLE.name + '.nullarc-dcn-observer-restore')
    staged = INSTALLED_BUNDLE.with_name(INSTALLED_BUNDLE.name + '.nullarc-dcn-observer-next')
    if backup.exists() or backup.is_symlink() or staged.exists() or staged.is_symlink():
        raise ValueError('Stale standard-path swap artifacts require manual inspection')
    lock_descriptor = os.open(LINK_LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if protected_disk_snapshot() != snapshot:
            raise ValueError('Installed baseline changed after AuxKC preflight')
        result = link_with_temporary_standard_bundle(
            INSTALLED_BUNDLE, candidate, backup, staged, baseline_manifest,
            candidate_manifest,
            lambda: subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   capture_output=True, timeout=180))
        if result.returncode:
            raise RuntimeError('Private standard-path AuxKC link failed and exact PhxAccel restoration passed')
    finally:
        os.close(lock_descriptor)
        if LINK_LOCK.exists():
            LINK_LOCK.unlink()
    if not output.is_file() or output.is_symlink():
        raise ValueError('Private AuxKC output unavailable after link')
    os.chmod(output, 0o600)
    candidate_capture = complete_cache_capture(output)
    comparison = cache_metadata.compare_captures(baseline, candidate_capture,
                                                  ['com.luuumi.PhxAccel'])
    if comparison['combined_records'] != 416 or comparison['codeless_records'] != 29:
        raise ValueError('Private AuxKC complete metadata counts changed')
    after = protected_disk_snapshot()
    if after != snapshot or common.tree_files(INSTALLED_BUNDLE) != baseline_manifest:
        raise ValueError('Installed caches or PhxAccel differ after temporary input restoration')
    link_report = dict(status='private-auxkc-passed-exact-phxaccel-image-delta',
        source_commit=SOURCE_COMMIT, os_version=version, os_build=os_build,
        scanout_mode_report_sha256=mode_preflight['report_sha256'],
        scanout_mode_report_created_unix_ns=mode_preflight['created_unix_ns'],
        scanout_mode_gate_rechecked_after_link=False,
        candidate_binary_sha256='6543861256208467f1833be11176be9a83207bd2a348f7fa3159645e10790ff0',
        candidate_bundle_sha256=common.file_sha(candidate / EXECUTABLE),
        private_auxkc_sha256=common.file_sha(output),
        baseline_capture_sha256=common.sha(baseline), candidate_capture_sha256=common.sha(candidate_capture),
        combined_records=comparison['combined_records'], codeless_records=comparison['codeless_records'],
        changed_images=comparison['changed_images'],
        automatic_matching_and_load_policy_preserved=comparison['automatic_matching_and_explicit_load_policy_preserved'],
        dependencies_and_bundle_paths_preserved=comparison['bundle_paths_personalities_and_dependencies_preserved'],
        installed_auxkc_unchanged=True, installed_phxaccel_unchanged=True,
        installed=False, loaded=False, restart_requested=False, nvram_or_efi_changed=False,
        gpu_work_submitted=False)
    (out / 'auxkc-link-report-private.json').write_text(json.dumps(link_report, indent=2, sort_keys=True) + '\n')
    return dict(status=link_report['status'], complete_416_29_metadata_passed=True,
                only_phxaccel_image_changed=True, installed_caches_unchanged=True,
                installed=False, loaded=False, restart_requested=False)


def validate_bundle_pair(control, candidate):
    if set(control) != set(candidate) or {name for name in control if control[name] != candidate[name]} != {EXECUTABLE}:
        raise ValueError('Observer bundle must differ from control only at its executable')


def inspect_bundle_pair(out, runner):
    manifests, identities, imports = {}, {}, {}
    for role in ('control', 'observer'):
        bundle = out / role / BUNDLE
        binary = bundle / EXECUTABLE
        runner(role + '-signature', '/usr/bin/codesign', '--verify', '--strict', bundle)
        runner(role + '-architecture', '/usr/bin/lipo', binary, '-verify_arch', 'x86_64')
        manifests[role] = common.tree_files(bundle)
        identities[role] = common.macho_identity(binary.read_bytes())
        if manifests[role][EXECUTABLE] != identities[role]['binary_sha256']:
            raise ValueError('Bundle image identity changed during readback')
        imports[role] = import_set(binary)
    validate_bundle_pair(manifests['control'], manifests['observer'])
    if identities['control']['binary_sha256'] != '8e677b77caa23f404e3a011ca0648fd839bd6ab9264d8697e27f8e2e70997564':
        raise ValueError('Control build does not reproduce the accepted PhxAccel image')
    if identities['observer']['binary_sha256'] != '6543861256208467f1833be11176be9a83207bd2a348f7fa3159645e10790ff0':
        raise ValueError('Observer binary differs from the reviewed private build')
    added = sorted(set(imports['observer']) - set(imports['control']))
    removed = sorted(set(imports['control']) - set(imports['observer']))
    if (added != ['__ZN11IOPCIDevice20extendedConfigRead32Ey', '__ZNK9IOService10isInactiveEv'] or
            removed != ['__ZN13IOFramebuffer4freeEv']):
        raise ValueError('Observer import delta differs from reviewed evidence')
    return dict(control_bundle_files_private=manifests['control'],
                observer_bundle_files_private=manifests['observer'],
                control_identity_private=identities['control'],
                observer_identity_private=identities['observer'],
                added_imports=added, removed_imports=removed,
                strict_signatures_passed=True, x86_64_architecture_passed=True,
                sole_bundle_delta=EXECUTABLE)


def build(sdk, out):
    out = private_output(out)
    if out.exists() or platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Require Intel macOS and a fresh private output directory')
    version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], timeout=10).decode().strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], timeout=10).decode().strip()
    baseline, candidate = read_sources()
    evidence = validate_evidence(baseline, candidate)
    if (version, os_build) != (evidence['os_version'], evidence['os_build']):
        raise ValueError('Native build host differs from the reviewed OS/KDK build')
    sdk_blobs = common.sdk_inputs(sdk)
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'], timeout=15).decode().strip()).resolve()
    tools = {str(path): common.file_sha(path) for path in
             (compiler, Path('/usr/bin/codesign'), Path('/usr/bin/lipo'), Path('/usr/bin/nm'))}
    recipe_sha = common.file_sha(Path(__file__))
    tool_hashes = {str(path): common.file_sha(path) for path in TOOLS}
    out.mkdir(mode=0o700)
    tmp = out / 'tmp-private'
    tmp.mkdir(mode=0o700)
    sdk_copy = out / 'MacKernelSDK-pinned-private'
    materialize(sdk_copy, sdk_blobs)
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin:' + str(compiler.parent),
           'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def run(label, *args):
        result = subprocess.run([str(arg) for arg in args], cwd=out, env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=180)
        (out / (label + '.log-private')).write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(label + ' failed; preserve private build output')
        return result

    source_sets = {'control': baseline, 'observer': candidate}
    tool_inputs = read_tool_inputs()
    for role, blobs in source_sets.items():
        source = out / role / 'source'
        materialize(source, blobs)
        if role == 'observer':
            for name in SUPPORT_HEADERS:
                target = source / 'src/phxaccel/accel' / name
                if target.exists() or target.is_symlink():
                    raise ValueError('Unexpected conflicting private support header')
                target.write_bytes(tool_inputs['tools/' + name])
        run(role + '-build', '/bin/sh', source / 'src/phxaccel/build.sh', sdk_copy)
        built = source / 'src/phxaccel/build' / BUNDLE
        bundle = out / role / BUNDLE
        shutil.copytree(built, bundle)
        if any((source / name).read_bytes() != blob for name, blob in blobs.items()):
            raise ValueError('Frozen source changed during native compilation')
    checks = inspect_bundle_pair(out, run)
    if (read_sources() != (baseline, candidate) or read_tool_inputs() != tool_inputs or
            validate_evidence(baseline, candidate) != evidence or
            common.sdk_inputs(sdk) != sdk_blobs or
            common.tree_files(sdk_copy) != {name: common.sha(blob) for name, blob in sdk_blobs.items()} or
            {str(path): common.file_sha(path) for path in TOOLS} != tool_hashes or
            common.file_sha(Path(__file__)) != recipe_sha or
            {str(path): common.file_sha(path) for path in
             (compiler, Path('/usr/bin/codesign'), Path('/usr/bin/lipo'), Path('/usr/bin/nm'))} != tools):
        raise ValueError('Source, SDK, toolchain or recipe changed during native build')
    report = dict(status='built-private-dcn-firmware-observer-awaiting-auxkc-link',
                  source_commit=SOURCE_COMMIT, os_version=version, os_build=os_build,
                  sdk_commit=common.SDK_PIN, recipe_sha256=recipe_sha,
                  source_inputs_private={name: common.sha(blob) for name, blob in candidate.items()},
                  source_stage_sha256=common.sha(candidate[FRAMEBUFFER]),
                  tool_input_sha256={name: common.sha(blob) for name, blob in tool_inputs.items()},
                  support_header_sha256={name: common.sha(tool_inputs['tools/' + name]) for name in SUPPORT_HEADERS},
                  tool_hashes_private=tools, **checks,
                  auxkc_linked=False, installed=False, loaded=False, restart_requested=False,
                  nvram_or_efi_changed=False, dma_mapping_created=False, gpu_work_submitted=False)
    (out / 'build-report-private.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return dict(status=report['status'], control_reproduced=True, observer_reproduced=True,
                imports_match_reviewed_delta=True, signed_x86_64_bundles=True,
                auxkc_linked=False, installed=False, loaded=False)


def verify(out):
    out = private_output(out)
    report_path = out / 'build-report-private.json'
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError('Private build report unavailable')
    report = json.loads(report_path.read_text())
    if report['status'] != 'built-private-dcn-firmware-observer-awaiting-auxkc-link':
        raise ValueError('Unexpected private build state')
    if report['recipe_sha256'] != common.file_sha(Path(__file__)):
        raise ValueError('Private candidate was built by a different recipe version')
    def read(label, *args):
        result = subprocess.run([str(arg) for arg in args], cwd=out, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError(label + ' readback failed')
        return result
    checks = inspect_bundle_pair(out, read)
    if any(report.get(key) != value for key, value in checks.items()):
        raise ValueError('Independent private bundle readback differs from build report')
    baseline, candidate = read_sources()
    tool_inputs = read_tool_inputs()
    validate_evidence(baseline, candidate)
    if report['tool_input_sha256'] != {name: common.sha(blob) for name, blob in tool_inputs.items()}:
        raise ValueError('Recorded tool input set differs from the pinned support closure')
    for role, blobs in (('control', baseline), ('observer', candidate)):
        source = out / role / 'source'
        if any((source / name).read_bytes() != blob for name, blob in blobs.items()):
            raise ValueError('Private source snapshot drift')
        for name in SUPPORT_HEADERS if role == 'observer' else ():
            if (source / 'src/phxaccel/accel' / name).read_bytes() != tool_inputs['tools/' + name]:
                raise ValueError('Private observer support header drift')
    if report['support_header_sha256'] != {
            name: common.sha(tool_inputs['tools/' + name]) for name in SUPPORT_HEADERS}:
        raise ValueError('Recorded observer support-header set changed')
    return dict(status='passed-independent-private-dcn-firmware-observer-readback',
                control_reproduced=True, observer_reproduced=True,
                auxkc_linked=False, installed=False, loaded=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sdk', type=Path, help='Build using the exact reviewed MacKernelSDK checkout')
    mode.add_argument('--verify', action='store_true', help='Independently read back private bundles')
    mode.add_argument('--link-auxkc', action='store_true', help='Create and verify a private AuxKC only')
    mode.add_argument('--scanout-preflight', action='store_true', help='Write a fresh native 2x mode report')
    parser.add_argument('--kdk', type=Path, help='Matching installed KDK root required for private AuxKC link')
    parser.add_argument('--mode-report', type=Path, help='Private fresh native 2x report path')
    arguments = parser.parse_args()
    if arguments.link_auxkc:
        if not arguments.kdk or not arguments.mode_report:
            parser.error('--kdk and --mode-report are required with --link-auxkc')
        result = link_auxkc(arguments.out, arguments.kdk.resolve(), arguments.mode_report)
    elif arguments.scanout_preflight:
        if arguments.kdk or not arguments.mode_report:
            parser.error('--mode-report is required with --scanout-preflight; --kdk is not used')
        result = write_scanout_mode_report(arguments.out, arguments.mode_report)
    elif arguments.verify:
        if arguments.kdk or arguments.mode_report:
            parser.error('--kdk and --mode-report are not used with --verify')
        result = verify(arguments.out)
    else:
        if arguments.kdk or arguments.mode_report:
            parser.error('--kdk and --mode-report are only used for an offline AuxKC operation')
        result = build(arguments.sdk, arguments.out)
    print(json.dumps(result, sort_keys=True))
