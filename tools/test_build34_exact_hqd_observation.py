# SPDX-License-Identifier: MIT
"""Exercise staged HQD observation with CPU doubles and nonloadable objects."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess

from build34_exact_hqd_observation import FIELDS, METHOD, NEW_ADOPTION_CHECK, SIGNATURE, previous_stage, stage, stage_header
from build34_exact_submit import once
from build34_native_object_check import check as native_check
from test_build34_exact_claim_lifecycle import FACTORY, REFERENCE, git, xcrun
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


PRIOR = 'docs/validation/build34-r3-claim-consumer-offline-20261121.json'
RAW_FIXTURE = 'tests/test_build34_exact_raw_handoff.cpp'
FIXTURE = 'tests/test_build34_exact_hqd_observation.cpp'
WRITER = 'IOReturn PhxBringup::writeReg('
ADOPT = 'IOReturn PhxBringup::adoptQueue('
NEW = (PRIOR, RAW_FIXTURE, FIXTURE, 'tools/build34_exact_hqd_observation.py', 'tools/test_build34_exact_hqd_observation.py')


def test(out, sdk, kdk):
    out = out.resolve()
    if ((platform.system(), platform.machine()) != ('Darwin', 'x86_64') or out.exists() or ROOT / 'build' not in out.parents
            or not out.name.endswith('-private') or git('symbolic-ref', '--short', 'HEAD').strip() != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 and a fresh private output on x86_64 macOS')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').splitlines()
    if len(protected) != 172 or git('status', '--porcelain', '--', *protected):
        raise ValueError('Production inputs drifted')
    prior, factory, reference = (json.loads((ROOT / n).read_bytes()) for n in (PRIOR, FACTORY, REFERENCE))
    frozen = {n: (ROOT / n).read_bytes() for n in set(protected) | set(factory['input_sha256']) | set(NEW) | {REFERENCE}}
    old, new = (transform(frozen[DRIVER].decode()) for transform in (previous_stage, stage))
    ownership = stage_header(frozen['tools/build34_exact_ownership.h'].decode())
    if (prior['GPU_executed'] or sha(old.encode()) != prior['staged_driver_sha256'] or
            sha(ownership.encode()) != factory['staged_header_sha256'] or
            any(sha(frozen[n]) != digest for n, digest in factory['input_sha256'].items()) or
            once(once(once(new, FIELDS, ''), METHOD, ''), method(new, ADOPT), method(old, ADOPT)) != old):
        raise ValueError('Unexpected staged predecessor or unrelated change')

    out.mkdir(mode=0o700)
    compiler, host_sdk, otool = [xcrun(*args) for args in (('--find', 'clang++'), ('--show-sdk-path',), ('--find', 'otool'))]

    def run(label, args, expected=0):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode != expected:
            raise RuntimeError(f'{label} exited {p.returncode}; expected {expected}. See private diagnostics.')
        return p

    for name in (FIXTURE, 'src/phxbringup/PhxNativeABI.h', 'src/amd/phx_topology.h',
                 'tools/build34_exact_callbacks.h', 'tools/build34_exact_fence32.h'):
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(frozen[name])

    def exercise(label, text, sanitizer, broken=False):
        gates_at = text.index('    mutable phx34_exact::CallbackGate<> exactCallbacks;\n')
        gates = text[gates_at:text.index('    uint64_t exactQueueSubmitted[2]', gates_at)]
        queue_at = text.index('    struct GpuQueue {')
        queue = text[queue_at:text.index('    uint64_t gSeq{', queue_at)]
        fixture = frozen[RAW_FIXTURE].decode().split('static bool raw32(', 1)[0]
        fixture = once(fixture, 'struct IOService {};', 'struct IOService {};\nstruct IOPCIDevice;')
        fixture = once(fixture, 'static void IOLockUnlock(',
                       'static bool IOLockTryLock(IOLock *p) { if (!p->mutex.try_lock()) return false; ++gpuHeld; return true; }\n'
                       'static void IOLockUnlock(')
        fixture = once(fixture, '    // PHX34_GATES', gates)
        fixture = once(fixture, '    // PHX34_QUEUE', queue)
        fixture = once(fixture, '    // PHX34_DECLARATIONS', '    uint32_t configuredQueues{0};\n'
                       '    IOReturn writeReg(uint32_t, uint32_t, uint32_t *);')
        bodies = (SIGNATURE, WRITER, ADOPT, 'uint32_t PhxBringup::rreg(', 'void PhxBringup::wreg(', 'void PhxBringup::hdpFlush(')
        (out / 'hqd-fixture.inc').write_text(once(fixture, '// PHX34_METHODS', '\n'.join(method(text, s) for s in bodies)))
        binary = out / label
        run(label + '-compile', [compiler, '--driver-mode=g++', '-std=c++17', '-isysroot', host_sdk, '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-function', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all',
                                 '-I' + str(out), '-I' + str(out / 'tools'), '-I' + str(out / 'src/phxbringup'), out / FIXTURE, '-o', binary])
        if re.search(rb'IOKit|Metal|vulkan', run(label + '-links', [otool, '-L', binary]).stdout, re.I):
            raise ValueError('CPU fixture linked a device library')
        result = run(label, [binary], expected=86 if broken else 0)
        if broken and result.stderr.startswith(b'failed '):
            return 0
        count = re.fullmatch(rb'PASS (\d+) HQD observation checks\n', result.stdout)
        if broken or not count or result.stderr:
            raise ValueError('Unexpected fixture result')
        return int(count[1])

    asan = exercise('asan', new, 'address,undefined')
    tsan = exercise('tsan', new, 'thread')
    if asan != tsan:
        raise ValueError('Sanitizer run counts differ')
    mutations = {
        'accept_changed_bank': ('if (!before || !after || !restored)', 'if (!before || (!after && !restored))'),
        'forget_restore': ('const bool restored = io->select(this, saved) && io->selector(this, &confirmed) && confirmed == saved;',
                           'const bool restored = true;'),
        'publish_after_close': ('if (!sampled || exactCallbacks.closed())', 'if (!sampled)'),
        'adopt_after_uncertainty': (NEW_ADOPTION_CHECK, '    if (__atomic_load_n(&exactFirmwareUncertain, __ATOMIC_ACQUIRE)) {\n'),
    }
    for label, pair in mutations.items():
        exercise(label, once(new, *pair), 'address,undefined', broken=True)
    native = native_check(out / 'native', frozen, old, new, ownership, sdk, kdk, prior['PhxBringup_imports'][1],
                          reference['compiler_warnings']['public'], reference, compiler)
    if any((ROOT / n).read_bytes() != blob for n, blob in frozen.items()):
        raise ValueError('Input changed during verification')
    report = dict(status='passed-staged-hqd-transaction-offline', PhxBringup_build=34, production_inputs_unchanged=len(protected),
                  predecessor_sha256=sha(old.encode()), staged_sha256=sha(new.encode()), checks_per_sanitizer=asan,
                  broken_variants_detected=list(mutations), **native,
                  GPU_executed=False, MMIO_backend_bound=False, old_writer_drain_proved=False, installed=False, R3_complete=False)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
