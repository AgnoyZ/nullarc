# SPDX-License-Identifier: MIT
"""Run the staged firmware handoff methods with CPU doubles and compile native objects."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess

from build34_exact_smu_uncertainty import MAILBOX, RESPONSE, SMU, WRITE, change, previous_stage, shared_latch, stage, stage_header
from build34_exact_submit import once
from build34_native_object_check import check as native_check
from test_build34_exact_ownership import DRIVER, ROOT, method, sha
from test_build34_exact_psp_uncertainty import FIXTURE as PSP_FIXTURE, METHODS, PRIOR as FACTORY, REFERENCE, git, xcrun


PRIOR = 'docs/validation/build34-r3-psp-uncertainty-offline-20261121.json'
FIXTURE = 'tests/test_build34_exact_smu_uncertainty.cpp'
NEW = (PRIOR, FIXTURE, 'tools/build34_exact_smu_uncertainty.py', 'tools/test_build34_exact_smu_uncertainty.py')
SIGNATURES = METHODS + (WRITE, SMU, 'uint32_t PhxBringup::smuPoll(')


def fixture_for(source, fixture):
    def members(start, end):
        first = source.index(start)
        return source[first:source.index(end, first)]

    bodies = [method(source, sig) for sig in SIGNATURES]
    for mark, text in {
        '// PHX34_FRAME': members('struct PhxGfxRbFrame {', '// Canned'),
        '    // PHX34_FIELDS': members('    mutable phx34_exact::CallbackGate<> exactCallbacks;',
                                     '    uint64_t exactQueueSubmitted[2]'),
        '    // PHX34_QUEUE': members('    struct GpuQueue {', '    uint64_t gSeq{'),
        '    // PHX34_DECLS': '\n'.join('    ' + f.split('{', 1)[0].replace('PhxBringup::', '').strip() + ';' for f in bodies),
        '// PHX34_METHODS': '\n'.join(bodies),
        '    mutable uint32_t ctrl =': '''    bool smuUsed = false;
    uint32_t smuAck = 0;
    mutable uint32_t smuResponse = 0, smuArg = 0;
    mutable unsigned smuPublications = 0, smuArgReads = 0, registerWrites = 0;
    mutable uint32_t ctrl =''',
        'registers{16};': 'registers{0x16400 * 4};',
        'static void IODelay(unsigned) {}': 'static void IOSleep(unsigned);\nstatic void IODelay(unsigned us) { IOSleep(us); }',
        '        return reg == PHX_PSP_C2PMSG_64 ? ctrl : reg == PHX_PSP_C2PMSG_67 ? pointer : 0;': '''        if (reg == PHX_SMU_RESP_REG) return smuResponse;
        if (reg == PHX_SMU_ARG_REG) { ++smuArgReads; return smuArg; }
        return reg == PHX_PSP_C2PMSG_64 ? ctrl : reg == PHX_PSP_C2PMSG_67 ? pointer : registers.words.at(reg);''',
        '        if (reg == PHX_PSP_C2PMSG_64) {': '''        ++registerWrites;
        if (reg == PHX_SMU_RESP_REG) smuResponse = value;
        else if (reg == PHX_SMU_ARG_REG) smuArg = value;
        else if (reg == PHX_SMU_MSG_REG) {
            ++smuPublications;
            smuResponse = smuAck;
            if (smuAck) smuArg = 17;
        } else if (reg == PHX_PSP_C2PMSG_64) {''',
        '                fbAper->at(fenceOff) = fenceCounter;\n            }\n        }':
            '                fbAper->at(fenceOff) = fenceCounter;\n            }\n        } else const_cast<Map &>(registers).at(uint64_t(reg) * 4) = value;',
        '    std::printf("PASS %u PSP handoff checks\\n", checks);\n}':
            '    std::printf("PASS %u PSP handoff checks\\n", checks);\n    return 0;\n}',
    }.items():
        fixture = once(fixture, mark, text)
    return fixture


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
    prior = json.loads((ROOT / PRIOR).read_bytes())
    factory = json.loads((ROOT / FACTORY).read_bytes())
    pins = factory['input_sha256'] | prior['frozen_new_input_sha256']
    frozen = {n: (ROOT / n).read_bytes() for n in (*pins, *NEW)}
    if prior['GPU_executed'] or any(sha(frozen[n]) != h for n, h in pins.items()):
        raise ValueError('Prior inputs drifted')
    original = frozen[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    header = stage_header(frozen['tools/build34_exact_ownership.h'].decode())
    restored = proposed
    for sig in (WRITE, SMU):
        restored = once(restored, method(proposed, sig), method(previous, sig))
    if (sha(previous.encode()) != prior['staged_driver_sha256'] or restored != shared_latch(previous)
            or sha(header.encode()) != factory['staged_header_sha256']):
        raise ValueError('Unexpected change in compiled source')
    out.mkdir(mode=0o700)
    for n, b in frozen.items():
        p = out / 'frozen' / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    compiler, host_sdk = xcrun('--find', 'clang++'), xcrun('--show-sdk-path')
    otool = xcrun('--find', 'otool')
    tmp = out / 'tmp'
    tmp.mkdir()
    env = dict(PATH=str(compiler.parent) + ':/usr/bin:/bin', LANG='C', LC_ALL='C', TMPDIR=str(tmp),
               TSAN_OPTIONS='halt_on_error=1:abort_on_error=0:exitcode=66')

    def run(args, label, expected=0):
        p = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode != expected:
            raise RuntimeError(f'{label} exited {p.returncode} (expected {expected}); diagnostics preserved')
        return p

    def exercise(label, source, sanitizer, *modes, broken=False):
        (out / 'psp-fixture.inc').write_text(fixture_for(source, frozen[PSP_FIXTURE].decode()))
        binary = out / label
        result = run([compiler, '--driver-mode=g++', '-std=c++17', '-arch', 'x86_64', '-isysroot', host_sdk,
                      '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all',
                      '-I' + str(out), '-I' + str(out / 'frozen/tools'), '-I' + str(out / 'frozen/src/phxbringup'),
                      out / 'frozen' / FIXTURE, '-o', binary], label + '-compile')
        if result.stderr or re.search(rb'IOKit|Metal|vulkan|PhxAccel', run([otool, '-L', binary], label + '-links').stdout, re.I):
            raise ValueError('Unexpected CPU diagnostics or device linkage')
        counts = []
        for mode in modes:
            result = run([binary, *([mode] if mode else [])], label + (mode or '-test'), expected=86 if broken else 0)
            if broken:
                if not result.stderr.startswith(b'failed '):
                    raise ValueError('Broken variant did not trip a fixture assertion')
                continue
            matched = re.fullmatch(rb'PASS (\d+) firmware checks\n', result.stdout)
            if not matched or result.stderr:
                raise ValueError('Invalid test output')
            counts.append(int(matched[1]))
        return counts

    before = exercise('prior', previous, 'address,undefined', 'prior')
    checked = exercise('checked', proposed, 'address,undefined', '', 'psp')
    tsan = exercise('tsan', proposed, 'thread', '', 'psp')
    if checked != tsan or checked[1] != prior['checks']['checked_ASan_UBSan']:
        raise ValueError('SMU sanitizer or prior PSP check count drift')
    mutants = {
        'raw_mailbox_bypass': change(proposed, WRITE, (MAILBOX, '')),
        'SMU_timeout_does_not_quarantine': change(proposed, SMU, (RESPONSE, RESPONSE.replace('        quarantineFirmware();\n', ''))),
        'read_argument_after_timeout': change(proposed, SMU, ('*argAfter = 0;', '*argAfter = rreg(PHX_SMU_ARG_REG);')),
    }
    for label, source in mutants.items():
        exercise(label, source, 'address,undefined', '', broken=True)
    native = native_check(out / 'native', frozen, previous, proposed, header, sdk, kdk, prior['native_import_count'],
                          prior['compiler_warnings']['proposed'], json.loads(frozen[REFERENCE]), compiler)
    if any(sha((ROOT / n).read_bytes()) != h for n, h in baseline.items()) or any(
            (ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in frozen.items()):
        raise ValueError('Source became dirty during verification')
    report = dict(status='passed-staged-SMU-uncertainty-and-raw-mailbox-reservation', kernel_build=34,
                  preceding_driver_sha256=sha(previous.encode()), staged_driver_sha256=sha(proposed.encode()),
                  frozen_input_count=len(frozen), new_input_sha256={n: sha(frozen[n]) for n in NEW},
                  prior_checks=before[0], SMU_checks_ASan_UBSan_and_TSan=checked[0], PSP_regression_checks_each=checked[1],
                  broken_variants_detected=list(mutants), production_inputs_unchanged=len(protected),
                  IOKit_opened=False, GPU_executed=False, installed=False, external_writer_drain_proved=False,
                  native_reader_bound=False, R3_complete=False, **native)
    (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
