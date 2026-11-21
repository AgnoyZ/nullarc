# SPDX-License-Identifier: MIT
"""Test staged native claim with actual methods and CPU stand-ins for IOKit."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess

from build34_exact_claim import CLAIM, change, previous_stage, stage, stage_header
from build34_exact_submit import once
from build34_native_object_check import check as native_check
from test_build34_exact_ownership import DRIVER, ROOT, method, sha
from test_build34_exact_smu_uncertainty import (FACTORY, FIXTURE as SMU_FIXTURE, PRIOR as PSP,
                                             PSP_FIXTURE, REFERENCE, fixture_for, git, xcrun)


PRIOR = 'docs/validation/build34-r3-smu-uncertainty-offline-20261121.json'
FIXTURE = 'tests/test_build34_exact_claim.cpp'
NEW = (PRIOR, FIXTURE, 'tools/build34_exact_claim.py', 'tools/test_build34_exact_claim.py')

MOCK = '''static thread_local Pause *beforeGpuLock, *afterGpuUnlock;
static thread_local unsigned locksHeld;
static void pauseOnce(Pause *&point) {
    if (auto *pause = point) { point = nullptr; pause->arrive(); }
}
static void IOLockLock(IOLock *l) { pauseOnce(beforeGpuLock); l->lock(); ++locksHeld; }
static void IOLockUnlock(IOLock *l) { --locksHeld; l->unlock(); pauseOnce(afterGpuUnlock); }

static constexpr bool kOSBooleanTrue = true;
struct IOPCIDevice {
    phx34_exact::CallbackGate<> *checkLease = nullptr;
    unsigned refs = 1, properties = 0, matches = 0;
    bool propertyOK = true;
    void retain() { ++refs; }
    void release() { --refs; }
    void publicationCheck() const {
        CHECK(!locksHeld);
        if (checkLease) CHECK(checkLease->active() == 1 && refs == 2);
    }
    bool setProperty(const char *name, bool value) {
        publicationCheck();
        CHECK(!std::strcmp(name, "nmxgpu-claimed") && value);
        ++properties;
        return propertyOK;
    }
    void registerService() { publicationCheck(); ++matches; }
};
'''


def claim_fixture(source, frozen):
    text = fixture_for(source, frozen[PSP_FIXTURE].decode())
    text = once(text, 'static void IOLockLock(IOLock *l) { l->lock(); }\n'
                'static void IOLockUnlock(IOLock *l) { l->unlock(); }\n', '')
    text = once(text, 'static thread_local Pause *firstPoll;\n', 'static thread_local Pause *firstPoll;\n' + MOCK)
    text = once(text, '    IOLock gpu, smu;\n', '    IOPCIDevice pciModel, *pci = &pciModel;\n    IOLock gpu, smu;\n')
    text = once(text, '    uint32_t rreg(uint32_t reg) const {',
                '    IOReturn claimAccel();\n    uint32_t rreg(uint32_t reg) const {')
    text = once(text, 'int main(int argc, char **)', 'int psp_fixture_main(int argc, char **)')
    return text + '\n' + method(source, CLAIM)


def firmware_fixture(blob):
    text = once(blob.decode(), '#define main psp_fixture_main\n#include "psp-fixture.inc"\n#undef main\n',
                '#include "claim-fixture.inc"\n')
    text = once(text, 'int main(int argc, char **argv)', 'int firmware_fixture_main(int argc, char **argv)')
    return once(text, '    std::printf("PASS %u firmware checks\\n", checks);\n}',
                '    std::printf("PASS %u firmware checks\\n", checks);\n    return 0;\n}')


def test(out, sdk, kdk):
    out = out.resolve()
    if ((platform.system(), platform.machine()) != ('Darwin', 'x86_64') or out.exists() or ROOT / 'build' not in out.parents
            or not out.name.endswith('-private') or git('symbolic-ref', '--short', 'HEAD').strip() != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 on x86_64 macOS and fresh private output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').splitlines()
    if len(protected) != 172 or git('status', '--porcelain', '--', *protected):
        raise ValueError('Production input drift')
    baseline = {n: sha((ROOT / n).read_bytes()) for n in protected}
    records = {n: json.loads((ROOT / n).read_bytes()) for n in (FACTORY, PSP, PRIOR)}
    factory, psp, prior = (records[n] for n in (FACTORY, PSP, PRIOR))
    pins = factory['input_sha256'] | psp['frozen_new_input_sha256'] | prior['new_input_sha256']
    frozen = {n: (ROOT / n).read_bytes() for n in (*pins, *NEW)}
    if any(r['GPU_executed'] for r in records.values()) or any(sha(frozen[n]) != h for n, h in pins.items()):
        raise ValueError('Frozen prior inputs drifted')
    original = frozen[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    old, new = method(previous, CLAIM), method(proposed, CLAIM)
    header = stage_header(frozen['tools/build34_exact_ownership.h'].decode())
    if (sha(previous.encode()) != prior['staged_driver_sha256'] or old == new or once(proposed, new, old) != previous
            or sha(header.encode()) != factory['staged_header_sha256']):
        raise ValueError('Claim source or ownership predecessor drift')

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

    def exercise(label, source, sanitizer, *modes, broken=False):
        (out / 'claim-fixture.inc').write_text(claim_fixture(source, frozen))
        binary = out / label
        built = run([compiler, '--driver-mode=g++', '-std=c++17', '-arch', 'x86_64', '-isysroot', host_sdk,
                     '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all',
                     '-I' + str(out), '-I' + str(out / 'frozen/tools'), '-I' + str(out / 'frozen/src/phxbringup'),
                     out / 'frozen' / FIXTURE, '-o', binary], label + '-compile')
        if built.stderr or re.search(rb'IOKit|Metal|vulkan|PhxAccel', run([otool, '-L', binary], label + '-links').stdout, re.I):
            raise ValueError('Unexpected CPU diagnostics or device linkage')
        counts = []
        for mode in modes:
            result = run([binary, *([mode] if mode else [])], label + '-' + (mode or 'test'), expected=86 if broken else 0)
            if broken:
                if not result.stderr.startswith(b'failed '):
                    raise ValueError('Broken variant did not trip a fixture assertion')
                continue
            matched = re.fullmatch(rb'PASS (\d+) (?:native claim|firmware) checks\n', result.stdout)
            if not matched or result.stderr:
                raise ValueError('Invalid test output')
            counts.append(int(matched[1]))
        return counts

    before = exercise('prior', previous, 'address,undefined', 'prior')
    checked = exercise('checked', proposed, 'address,undefined', '', 'smu', 'psp')
    tsan = exercise('tsan', proposed, 'thread', '', 'smu', 'psp')
    if checked != tsan or checked[1:] != [prior['SMU_checks_ASan_UBSan_and_TSan'], prior['PSP_regression_checks_each']]:
        raise ValueError('Claim sanitizer or firmware regression count drift')
    mutations = {
        'only_configured': ('gq[0].ready && gq[1].ready && exactQueueLive[0] && exactQueueLive[1]', 'gpuReady()'),
        'ignore_property_refusal': ('if (device->setProperty("nmxgpu-claimed", kOSBooleanTrue)) {',
                                     'if ((device->setProperty("nmxgpu-claimed", kOSBooleanTrue), true)) {'),
        'no_closure_recheck_after_snapshot': ('if (!exactCallbacks.closed()) {', '{'),
    }
    for label, edit in mutations.items():
        exercise(label, change(proposed, CLAIM, edit), 'address,undefined', '', broken=True)
    native = native_check(out / 'native', frozen, previous, proposed, header, sdk, kdk, prior['native_import_count'],
                          prior['compiler_warnings']['proposed'], json.loads(frozen[REFERENCE]), compiler)
    if any(sha((ROOT / n).read_bytes()) != h for n, h in baseline.items()) or any(
            (ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in frozen.items()):
        raise ValueError('Source became dirty during verification')
    report = dict(status='passed-staged-paired-queue-claim-admission', kernel_build=34,
                  preceding_driver_sha256=sha(previous.encode()), staged_driver_sha256=sha(proposed.encode()),
                  frozen_input_count=len(frozen), new_input_sha256={n: sha(frozen[n]) for n in NEW},
                  prior_checks=before[0], claim_checks_each_sanitizer=checked[0], threaded_claim_scenarios=2,
                  SMU_regression_checks_each=checked[1], PSP_regression_checks_each=checked[2],
                  broken_variants_detected=list(mutations), production_inputs_unchanged=len(protected),
                  IOKit_opened=False, GPU_executed=False, installed=False, native_publication_vs_stop_proved=False,
                  external_writer_drain_proved=False, native_reader_bound=False, R3_complete=False, **native)
    (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
