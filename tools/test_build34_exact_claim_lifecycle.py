# SPDX-License-Identifier: MIT
"""Exercise actual build34 claim, queue adoption and power bodies offline."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess

from build34_exact_claim_lifecycle import ANCHOR, CLAIM, FIELDS, change, previous_stage, stage, stage_header
from build34_exact_submit import once
from build34_native_object_check import check as native_check
from test_build34_exact_claim import (FACTORY, FIXTURE as CLAIM_FIXTURE, MOCK, PRIOR as SMU, PSP, REFERENCE,
                                      SMU_FIXTURE, claim_fixture, firmware_fixture, git, xcrun)
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


PRIOR = 'docs/validation/build34-r3-claim-offline-20261121.json'
FIXTURE = 'tests/test_build34_exact_claim_lifecycle.cpp'
NEW = (PRIOR, FIXTURE, 'tools/build34_exact_claim_lifecycle.py', 'tools/test_build34_exact_claim_lifecycle.py')

MOCK_REGISTRY = '''static thread_local Pause *beforeLookup, *duringProperty, *duringMatch;
struct OSObject {};
static const OSObject booleanTrue, foreignProperty;
static const OSObject *const kOSBooleanTrue = &booleanTrue;
struct IOService {};
static constexpr IOReturn IOPMAckImplied = kIOReturnSuccess;
struct IOPCIDevice {
    phx34_exact::CallbackGate<> *checkLease = nullptr;
    const OSObject *marker = nullptr;
    unsigned refs = 1, properties = 0, matches = 0, removals = 0;
    bool propertyOK = true;
    void retain() { ++refs; }
    void release() { --refs; }
    void publicationCheck() const {
        CHECK(!locksHeld);
        if (checkLease) CHECK(checkLease->active() == 1 && refs == 2);
    }
    const OSObject *getProperty(const char *name) const {
        if (locksHeld || std::strcmp(name, "nmxgpu-claimed")) std::abort();
        pauseOnce(beforeLookup);
        return marker;
    }
    bool setProperty(const char *name, const OSObject *value) {
        publicationCheck();
        CHECK(!std::strcmp(name, "nmxgpu-claimed") && value == kOSBooleanTrue);
        ++properties;
        if (propertyOK) marker = value;
        pauseOnce(duringProperty);
        return propertyOK;
    }
    void removeProperty(const char *name) {
        publicationCheck();
        CHECK(!std::strcmp(name, "nmxgpu-claimed") && marker == kOSBooleanTrue);
        ++removals;
        marker = nullptr;
    }
    void registerService() { publicationCheck(); ++matches; pauseOnce(duringMatch); }
};
'''


def fixture(source, frozen):
    text = claim_fixture(source, frozen)
    text = once(text, '#define CHECK(expr) do { ++checks;',
                '#define CHECK(expr) do { __atomic_fetch_add(&checks, 1u, __ATOMIC_RELAXED);')
    text = once(text, MOCK[MOCK.index('static constexpr bool kOSBooleanTrue'):], MOCK_REGISTRY)
    epoch = '    uint64_t exactInvalidationEpoch{0};\n'
    if source.count(epoch) != 1:
        raise ValueError('Unexpected epoch field')
    text = once(text, '    IOReturn claimAccel();\n', epoch + '    IOReturn claimAccel();\n')
    text = once(text, '    IOReturn claimAccel();\n', '    IOReturn claimAccel();\n'
                '    IOReturn setPowerState(unsigned long, IOService *);\n    void invalidateExactQueues();\n')
    if FIELDS not in text:  # The regression fixture also compiles against the prior method.
        text = once(text, ANCHOR, FIELDS + ANCHOR)
    power = once(method(source, 'IOReturn PhxBringup::setPowerState('), 'IOService *whichDevice', 'IOService *')
    return text + '\n' + power + '\n' + method(source, 'void PhxBringup::invalidateExactQueues(')


def test(out, sdk, kdk):
    out = out.resolve()
    if ((platform.system(), platform.machine()) != ('Darwin', 'x86_64') or out.exists() or ROOT / 'build' not in out.parents
            or not out.name.endswith('-private') or git('symbolic-ref', '--short', 'HEAD').strip() != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 on x86_64 macOS and a fresh private output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').splitlines()
    if len(protected) != 172 or git('status', '--porcelain', '--', *protected):
        raise ValueError('Production input drift')
    baseline = {n: sha((ROOT / n).read_bytes()) for n in protected}
    factory, psp, smu, prior = (json.loads((ROOT / n).read_bytes()) for n in (FACTORY, PSP, SMU, PRIOR))
    pins = factory['input_sha256'] | psp['frozen_new_input_sha256'] | smu['new_input_sha256'] | prior['new_input_sha256']
    frozen = {n: (ROOT / n).read_bytes() for n in (*pins, *NEW)}
    if any(r['GPU_executed'] for r in (factory, psp, smu, prior)) or any(sha(frozen[n]) != h for n, h in pins.items()):
        raise ValueError('Prior inputs drifted')
    original = frozen[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    header = stage_header(frozen['tools/build34_exact_ownership.h'].decode())
    restored = once(proposed, method(proposed, CLAIM), method(previous, CLAIM))
    if (sha(previous.encode()) != prior['staged_driver_sha256'] or once(restored, FIELDS, '') != previous
            or sha(header.encode()) != factory['staged_header_sha256']):
        raise ValueError('Unexpected staged claim change')

    out.mkdir(mode=0o700)
    for name, blob in frozen.items():
        path = out / 'frozen' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    (out / 'firmware-fixture.inc').write_text(firmware_fixture(frozen[SMU_FIXTURE]))
    compiler, host_sdk, otool = (xcrun('--find', 'clang++'), xcrun('--show-sdk-path'), xcrun('--find', 'otool'))
    tmp = out / 'tmp'
    tmp.mkdir()
    env = dict(PATH=str(compiler.parent) + ':/usr/bin:/bin', LANG='C', LC_ALL='C', TMPDIR=str(tmp),
               TSAN_OPTIONS='halt_on_error=1:abort_on_error=0:exitcode=66')

    def run(args, label, expected=0):
        result = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if result.returncode != expected:
            raise RuntimeError(f'{label} exited {result.returncode} (expected {expected}); preserved private diagnostics')
        return result

    def exercise(label, source, sanitizer, *modes, fixture_path=FIXTURE, broken=False):
        (out / 'claim-fixture.inc').write_text(fixture(source, frozen))
        binary = out / label
        build = run([compiler, '--driver-mode=g++', '-std=c++17', '-arch', 'x86_64', '-isysroot', host_sdk,
                     '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all',
                     '-I' + str(out), '-I' + str(out / 'frozen/tools'), '-I' + str(out / 'frozen/src/phxbringup'),
                     out / 'frozen' / fixture_path, '-o', binary], label + '-compile')
        if build.stderr or re.search(rb'IOKit|Metal|vulkan|PhxAccel', run([otool, '-L', binary], label + '-links').stdout, re.I):
            raise ValueError('Unexpected CPU diagnostics or device linkage')
        counts = []
        for mode in modes:
            result = run([binary, *([mode] if mode else [])], label + '-' + (mode or 'test'), expected=86 if broken else 0)
            if broken:
                if not result.stderr.startswith(b'failed '):
                    raise ValueError('Broken variant did not fail a fixture assertion')
                continue
            number = re.fullmatch(rb'PASS (\d+) (?:claim lifecycle|native claim|firmware) checks\n', result.stdout)
            if not number or result.stderr:
                raise ValueError('Invalid check output')
            counts.append(int(number[1]))
        return counts

    before = exercise('prior', previous, 'address,undefined', 'prior')
    suites = []
    for label, sanitizer in [('asan', 'address,undefined'), ('tsan', 'thread')]:
        suites.append(exercise(label, proposed, sanitizer, '', 'smu', 'psp') +
                      exercise(label + '-claim', proposed, sanitizer, '', fixture_path=CLAIM_FIXTURE))
    if suites[0] != suites[1] or suites[0][1:] != [prior['SMU_regression_checks_each'],
                                                   prior['PSP_regression_checks_each'], prior['claim_checks_each_sanitizer']]:
        raise ValueError('Sanitizer or inherited regression counts drifted')
    mutations = {
        'stale_epoch_accepted': ('exactInvalidationEpoch == epoch', 'epoch < UINT64_MAX'),
        'skip_prepublication_recheck': ('        if (!stillCurrent()) return kIOReturnNotReady;\n', ''),
        'omit_stale_marker_removal': ('        if (device->getProperty(key) == kOSBooleanTrue) device->removeProperty(key);\n', ''),
    }
    for label, edit in mutations.items():
        exercise(label, change(proposed, CLAIM, edit), 'address,undefined', '', broken=True)
    native = native_check(out / 'native', frozen, previous, proposed, header, sdk, kdk, prior['native_import_count'],
                          prior['compiler_warnings']['proposed'], json.loads(frozen[REFERENCE]), compiler)
    if any(sha((ROOT / n).read_bytes()) != h for n, h in baseline.items()) or any(
            (ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in frozen.items()):
        raise ValueError('Source became dirty during verification')
    report = dict(status='passed-staged-claim-registry-revalidation', kernel_build=34,
                  preceding_driver_sha256=sha(previous.encode()), staged_driver_sha256=sha(proposed.encode()),
                  frozen_input_count=len(frozen), new_input_sha256={n: sha(frozen[n]) for n in NEW},
                  old_inflight_claim_checks=before[0], lifecycle_checks_each_sanitizer=suites[0][0],
                  synchronized_lifecycle_scenarios=6, SMU_regression_checks_each=suites[0][1],
                  PSP_regression_checks_each=suites[0][2], claim_regression_checks_each=suites[0][3],
                  broken_variants_detected=list(mutations), production_inputs_unchanged=len(protected),
                  native_async_matching_admission_proved=False, external_writer_drain_proved=False,
                  IOKit_opened=False, GPU_executed=False, installed=False, native_reader_bound=False, R3_complete=False, **native)
    (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
