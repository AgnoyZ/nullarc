#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CPU-only R3 ownership prototype and extracted legacy native contracts.

No kernel build, native selector, service open, runtime installation, GPU work,
job or power action. The prototype is not included by any production source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DRIVER = 'src/phxbringup/PhxBringup.cpp'
PROTOTYPE = 'tools/build34_exact_ownership.h'
FIXTURE = 'tests/test_build34_exact_ownership.cpp'
NATIVE = 'tests/test_build34_exact_native_contract.cpp'
PINNED = {
    DRIVER: '81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699',
    'src/phxbringup/PhxNativeABI.h': 'cb37e93dcab4faf8c9e672ad04793f2e363ae1e815c9913251cebcff5cd42c90',
    'src/amd/phx_topology.h': '28445bee8fc0f13a08aa52f114e4570ab6d6b8c068421dd10cf16023c06014d5',
}


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def method(text, signature):
    if text.count(signature) != 1:
        raise ValueError('Require one exact reviewed method: ' + signature)
    start = text.index(signature)
    return text[start:text.index('\n}\n', start) + 3]


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build directory ending -private')
    paths = [*PINNED, PROTOTYPE, FIXTURE, NATIVE, 'tools/test_build34_exact_ownership.py',
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    if any(sha(inputs[name]) != digest for name, digest in PINNED.items()):
        raise ValueError('Accepted build34 native source or ABI drift')
    if b'#define PHX_KEXT_BUILD 34u\n' not in inputs[DRIVER]:
        raise ValueError('Only default build34 is admissible')
    protected_names = subprocess.check_output([
        'git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
        cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in protected_names}
    included = subprocess.run(['git', 'grep', '-l', 'build34_exact_ownership.h', '--',
                               'src', 'tools/phxctl', 'tools/build_kext.py'],
                              cwd=ROOT, capture_output=True, text=True, timeout=15)
    if included.returncode != 1 or included.stdout or included.stderr:
        raise ValueError('Prototype must have no production inclusion')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, data in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run(args, label):
        p = subprocess.run([str(x) for x in args], stdin=subprocess.DEVNULL,
                           capture_output=True, cwd=out, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode:
            raise RuntimeError(label + ' failed; see private logs')
        return p.stdout.decode()

    source = inputs[DRIVER].decode()
    extracted = '\n'.join(method(source, signature) for signature in [
        'uint64_t PhxBringup::queueFence(', 'uint64_t PhxBringup::gpuRetired(',
        'IOReturn PhxBringup::adoptQueue(', 'IOReturn IOAccelPhxNativeClient::doWaitSeq('])
    marker = '// PHX34_EXTRACTED_NATIVE_CONTRACT_METHODS'
    native_text = inputs[NATIVE].decode()
    if native_text.count(marker) != 1:
        raise ValueError('Native fixture extraction marker drift')
    native = out / 'native-contract.cpp'
    native.write_text(native_text.replace(marker, extracted))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(frozen / 'tools'), '-I' + str(frozen / 'src/phxbringup')]
    outputs = {}
    for label, code in [('native-contract', native), ('ownership', frozen / FIXTURE)]:
        binary = out / (label + '-CPU-only')
        dep = out / (label + '.d')
        run([*cc, '-MMD', '-MF', dep, code, '-o', binary], label + '-compile')
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((frozen / name).resolve()) for name in inputs} | {str(code.resolve())}
        if not dependencies or any(str(Path(n).resolve()) not in allowed for n in dependencies):
            raise ValueError('Unfrozen non-system compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('CPU executable linked a device runtime')
        outputs[label] = run([binary], label + '-test')
        if (out / (label + '-test.stderr')).read_bytes():
            raise ValueError('CPU test or sanitizer emitted diagnostics')
    if outputs['native-contract'] != ('PASS actual legacy native contract: upper bound is not ownership; '
                                      'readoption seeds fence and clears history; GPU_executed=false\n'):
        raise ValueError('Actual legacy native method contracts were not reproduced')
    match = re.fullmatch(r'PASS R3 ownership prototype: (\d+) checks; 128 gaps, 128 independent model rounds, '
                         r'bounded admission, epochs, reuse, close, three callback interleavings; '
                         r'GPU_executed=false\n', outputs['ownership'])
    if not match:
        raise ValueError('Ownership prototype suite incomplete')
    # This proves only a restricted C++ language subset, not Kernel SDK linkage.
    subset = out / 'header-subset.cpp'
    subset.write_text('#include "build34_exact_ownership.h"\n'
                      'static_assert(phx34_exact::Registry::capacity == 64, "capacity");\n')
    run(['/usr/bin/xcrun', 'clang++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
         '-fno-exceptions', '-fno-rtti', '-I' + str(frozen / 'tools'),
         '-c', subset, '-o', out / 'header-subset.o'], 'header-subset-compile')
    if any((ROOT / name).read_bytes() != blob or (frozen / name).read_bytes() != blob
           for name, blob in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in protected_names}:
        raise ValueError('Production source/driver/plugin/ABI/tool drift')
    report = dict(status='passed-CPU-only-unintegrated-ownership-prototype',
                  kernel_build=34, actual_legacy_native_methods_extracted=4,
                  ownership_upper_bound_and_readoption_contracts_reproduced=True,
                  prototype_checks=int(match[1]), gap_cases=128, independent_reference_rounds=128,
                  callback_interleavings=3, asan_ubsan=True, fixed_capacity=64,
                  no_dynamic_prototype_allocation=True, pending_or_lost_records_never_evicted=True,
                  closed_or_generation_lost_targets_never_complete=True,
                  CXX14_without_exceptions_or_RTTI_compiles=True,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()},
                  protected_production_file_count=len(protected),
                  production_source_driver_plugin_ABI_tool_unchanged=True,
                  native_ownership_integration_implemented=False,
                  native_capability_negotiation_implemented=False,
                  coherent_hardware_fence_read_implemented=False,
                  native_teardown_drain_implemented=False,
                  prototype_internally_thread_safe=False,
                  external_serialization_required=True,
                  native_resource_release_authorized_by_metadata_forget=False,
                  native_kernel_compiled=False, installed=False, loaded=False,
                  GPU_executed=False, R3_hardware_accepted=False, R4_R6_started=False,
                  physical_FPS_measured=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
