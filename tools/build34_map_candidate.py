#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build only the accepted-R1b plus BAR0 metadata observer, privately/offline.

The full quarantining R3 transforms are NOT candidates. This separate recipe
reproduces the accepted image first and changes only the tested startup block.
It never installs, mounts EFI, opens a client, loads/unloads or requests power.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import platform
import shutil
import subprocess

import build34_map_observation as observation
from upstream34_layout import ring_padding_candidate as common

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '3d26409b1b151992d0dcaeb7093ce104a5c034dd'
DRIVER = common.DRIVER
EXE = 'Contents/MacOS/PhxBringup'
ACTIVE = 'OC/Kexts/PhxBringup.kext/'
BASE_BINARY = '0414c22119bad9526a33ec97bb56b9e7a8fd26320976cf24e0cb541d0d882d10'
OBSERVER_SHA = '9826065e11adc6ec7363459210704b685d1fc5df29758271ca674163254cd0c3'
EVIDENCE = 'docs/validation/build34-r3-map-observation-offline-20261121.json'
TRANSFORM_SHA = 'ba9c8f9ff566a99f74646eaac8b2d72866b97d2d796b59e73cb8eadbce35ef4f'
WARNINGS = {"declaration shadows a field of 'PhxBringup' [-Wshadow]": 3}


def verify_sources(baseline, proposed):
    if set(baseline) != set(common.SOURCE_INPUTS) or set(proposed) != set(baseline):
        raise ValueError('Require complete reviewed kernel/license/build input set')
    if common.sha(baseline[DRIVER]) != observation.BASE_SHA or common.sha(proposed[DRIVER]) != OBSERVER_SHA:
        raise ValueError('Unreviewed baseline or mapping-observer source')
    if proposed[DRIVER].decode().replace(observation.OBSERVATION, '', 1).encode() != baseline[DRIVER]:
        raise ValueError('Observer must change only the tested startup insertion')
    if any(baseline[n] != proposed[n] for n in baseline if n != DRIVER):
        raise ValueError('Protected ABI, recipe, matching or license input changed')


def derive_efi_manifest(before, baseline_bundle, observer_bundle):
    """Prospective single-executable replacement, including every other file."""
    if len(before) != 358 or set(observer_bundle) != set(baseline_bundle):
        raise ValueError('Require complete retained 358-file EFI and bundle pair')
    if {n for n in baseline_bundle if baseline_bundle[n] != observer_bundle[n]} != {EXE}:
        raise ValueError('Only the bundle executable may differ')
    active = {n[len(ACTIVE):]: v for n, v in before.items() if n.startswith(ACTIVE)}
    if active != baseline_bundle or baseline_bundle[EXE]['sha256'] != BASE_BINARY:
        raise ValueError('EFI baseline is not the exact accepted R1b bundle')
    after = copy.deepcopy(before)
    after[ACTIVE + EXE] = copy.deepcopy(observer_bundle[EXE])
    if {n for n in before if before[n] != after[n]} != {ACTIVE + EXE} or set(before) != set(after):
        raise ValueError('Unexpected complete EFI delta')
    return after


def build(sdk, out):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Require native Intel macOS')
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require fresh ignored worktree output ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    if subprocess.check_output(['/usr/bin/git', 'symbolic-ref', '--short', 'HEAD'], cwd=ROOT, text=True, timeout=15).strip() != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 only')
    evidence_blob = (ROOT / EVIDENCE).read_bytes()
    evidence = json.loads(evidence_blob)
    pinned = {name: (ROOT / name).read_bytes() for name in evidence['input_sha256']}
    if any(common.sha(b) != evidence['input_sha256'][n] for n, b in pinned.items()):
        raise ValueError('Frozen mapping-observation prerequisite drift')
    if (common.sha(Path(observation.__file__).read_bytes()) != TRANSFORM_SHA or
            evidence['baseline_observation_driver_sha256'] != OBSERVER_SHA):
        raise ValueError('Require reviewed observation transform/evidence')
    baseline = {n: (ROOT / n).read_bytes() for n in common.SOURCE_INPUTS}
    protected_names = subprocess.check_output(['/usr/bin/git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                              cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: (ROOT / n).read_bytes() for n in protected_names}
    for name, blob in baseline.items():
        if subprocess.check_output(['/usr/bin/git', 'show', observation.BASE_COMMIT + ':' + name], cwd=ROOT, timeout=15) != blob:
            raise ValueError('Accepted R1b source/license/build input differs')
    proposed = dict(baseline)
    proposed[DRIVER] = observation.stage_baseline(baseline[DRIVER].decode()).encode()
    verify_sources(baseline, proposed)
    reference = ROOT / 'build/build34-r1b1-backpressure-20261120-private/native/source/src/phxbringup/build/PhxBringup.kext'
    reference_files = common.tree_files(reference)
    if reference_files.get(EXE) != BASE_BINARY:
        raise ValueError('Accepted R1b reference artifact differs')
    sdk_blobs = common.sdk_inputs(sdk)
    source_recipe = Path(__file__).read_bytes()
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'], text=True, timeout=15).strip()).resolve()
    tools = {p: common.file_sha(p) for p in [compiler, Path('/usr/bin/codesign'), Path('/usr/bin/nm')]}
    out.mkdir(mode=0o700, parents=True)
    sdk_copy = out / 'MacKernelSDK-pinned-private'
    for name, blob in sdk_blobs.items():
        path = sdk_copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    tmp = out / 'tmp-private'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}
    report = dict(schema_version=1, status='building-private-offline-map-observer',
                  source_checkpoint=SOURCE, accepted_R1b_source_checkpoint=observation.BASE_COMMIT,
                  kernel_build=34, sdk_commit=common.SDK_PIN,
                  baseline_driver_sha256=observation.BASE_SHA, observer_driver_sha256=OBSERVER_SHA,
                  observation_transform_sha256=TRANSFORM_SHA, recipe_sha256=common.sha(source_recipe),
                  prerequisite_evidence_sha256=common.sha(evidence_blob),
                  input_sha256={n: common.sha(b) for n, b in baseline.items()}, roles={}, checks=[],
                  protected_production_sha256_private={n: common.sha(b) for n, b in protected.items()},
                  full_R3_transforms_included=False, reader_or_exact_mode_bound=False,
                  installed=False, loaded=False, GPU_executed=False, power_actions=0,
                  deployment_admitted=False, fresh_scope_and_authorization_required=True)

    def save():
        (out / 'build-report-private.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(args, label, cwd=ROOT):
        p = subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=180)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        report['checks'].append(dict(name=label, returncode=p.returncode, stdout_sha256=common.sha(p.stdout), stderr_sha256=common.sha(p.stderr)))
        save()
        if p.returncode:
            raise RuntimeError(label + ' failed; preserve private output')
        return p

    imports = {}
    try:
        save()
        for role, blobs in [('baseline', baseline), ('observer', proposed)]:
            source = out / role / 'source'
            for name, blob in blobs.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
            compiled = run(['/bin/sh', source / 'src/phxbringup/build.sh', sdk_copy], role + '-build', source)
            warnings = dict(Counter(line.split('warning:', 1)[1].strip() for line in compiled.stderr.decode().splitlines() if 'warning:' in line))
            if warnings != WARNINGS:
                raise ValueError('Changed native compiler diagnostics')
            bundle = out / role / 'PhxBringup.kext'
            shutil.copytree(source / 'src/phxbringup/build/PhxBringup.kext', bundle)
            (bundle / 'Contents/Info.plist').write_bytes(common.control_metadata(blobs['src/phxbringup/Info.plist']))
            binary = bundle / EXE
            before_sign = common.macho_identity(binary.read_bytes())
            run(['/usr/bin/codesign', '--force', '--sign', '-', bundle], role + '-sign')
            run(['/usr/bin/codesign', '--verify', '--strict', bundle], role + '-signature')
            run(['/usr/bin/lipo', binary, '-verify_arch', 'x86_64'], role + '-architecture')
            identity = common.macho_identity(binary.read_bytes())
            if any(identity[k] != before_sign[k] for k in ['architecture', 'filetype', 'image_uuid_private']):
                raise ValueError('Unexpected signing identity delta')
            imports[role] = set(run(['/usr/bin/nm', '-arch', 'x86_64', '-uj', binary], role + '-imports').stdout.decode().splitlines())
            files = common.tree_files(bundle)
            if role == 'baseline' and files != reference_files:
                raise ValueError('Complete accepted R1b bundle was not reproduced exactly')
            records = {n: dict(sha256=h, bytes=(bundle / n).stat().st_size) for n, h in files.items()}
            report['roles'][role] = dict(binary_sha256=files[EXE], bundle_files_private=records,
                                         identity_private=identity, warnings=warnings)
            if any((source / n).read_bytes() != b for n, b in blobs.items()):
                raise ValueError('Native source snapshot drift')
            save()
        a, b = report['roles']['baseline'], report['roles']['observer']
        if (imports['baseline'] != imports['observer'] or len(imports['observer']) != 375 or
                '_thread_call_cancel_wait' not in imports['observer']):
            raise ValueError('Changed inherited native import contract')
        if (a['identity_private']['image_uuid_private'] == b['identity_private']['image_uuid_private'] or
                {n for n in a['bundle_files_private'] if a['bundle_files_private'][n] != b['bundle_files_private'].get(n)} != {EXE} or
                set(a['bundle_files_private']) != set(b['bundle_files_private'])):
            raise ValueError('Require a distinct observer image and sole executable delta')
        if (any((ROOT / n).read_bytes() != blob for n, blob in pinned.items()) or
                any((ROOT / n).read_bytes() != blob for n, blob in baseline.items()) or
                any((ROOT / n).read_bytes() != blob for n, blob in protected.items()) or
                Path(__file__).read_bytes() != source_recipe or common.sdk_inputs(sdk) != sdk_blobs or
                common.tree_files(sdk_copy) != {n: common.sha(blob) for n, blob in sdk_blobs.items()} or
                common.tree_files(reference) != reference_files or
                any(common.file_sha(p) != digest for p, digest in tools.items())):
            raise ValueError('Source/SDK/toolchain/reference drift')
        report.update(status='built-private-map-observer-not-installed-or-hardware-accepted',
                      accepted_bundle_reproduced_byte_exact=True, sole_bundle_delta=EXE,
                      native_import_count=375, import_set_unchanged=True,
                      inherited_private_cancellation_preserved_not_newly_admitted=True,
                      generic_public_KPI_or_AuxKC_admission=False,
                      original_production_file_count=len(protected), production_unchanged=True,
                      sdk_files_sha256_private={n: common.sha(blob) for n, blob in sdk_blobs.items()})
        save()
    except BaseException as error:
        report.update(status='failed-private-offline-map-observer-build', error_type=type(error).__name__)
        save()
        raise
    print(json.dumps({k: report[k] for k in ['status', 'accepted_bundle_reproduced_byte_exact', 'import_set_unchanged',
                     'native_import_count', 'installed', 'loaded', 'GPU_executed']}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.sdk, args.out)
