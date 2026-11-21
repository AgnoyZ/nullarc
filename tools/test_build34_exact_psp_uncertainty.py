# SPDX-License-Identifier: MIT
"""Exercise actual staged PSP and adoption paths without opening IOKit."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess

from build34_exact_psp_uncertainty import ADOPT, COMMAND, FIELD, HELPER, RING, SIGNATURES, change, previous_stage, stage, stage_header
from build34_exact_submit import once
from build34_native_object_check import check as native_check
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


PRIOR = 'docs/validation/build34-r3-factory-offline-20261121.json'
REFERENCE = 'docs/validation/build34-r3-public-timer-offline-20261121.json'
TRANSFORM = 'tools/build34_exact_psp_uncertainty.py'
RUNNER = 'tools/test_build34_exact_psp_uncertainty.py'
FIXTURE = 'tests/test_build34_exact_psp_uncertainty.cpp'
METHODS = SIGNATURES + ('bool PhxBringup::pspWaitTos(', 'void PhxBringup::clearRing(',
                       'IOReturn PhxBringup::pspSubmit(', 'IOReturn PhxBringup::vramWrite(')


def git(*args):
    return subprocess.check_output(['/usr/bin/git', *args], cwd=ROOT, text=True, timeout=15)


def xcrun(*args):
    return Path(subprocess.check_output(['/usr/bin/xcrun', *args], text=True, timeout=15).strip()).resolve()


def test(out, sdk, kdk):
    out = out.resolve()
    if ((platform.system(), platform.machine()) != ('Darwin', 'x86_64') or out.exists() or
            ROOT / 'build' not in out.parents or not out.name.endswith('-private') or
            git('symbolic-ref', '--short', 'HEAD').strip() != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34, x86_64 macOS and a fresh private worktree output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').splitlines()
    if len(protected) != 172 or git('status', '--porcelain', '--', *protected):
        raise ValueError('Production input drift')
    baseline = {n: sha((ROOT / n).read_bytes()) for n in protected}
    pinned = json.loads((ROOT / PRIOR).read_bytes())
    inputs = {n: (ROOT / n).read_bytes() for n in pinned['input_sha256']}
    if pinned['GPU_executed'] or any(sha(b) != pinned['input_sha256'][n] for n, b in inputs.items()):
        raise ValueError('Frozen factory inputs drifted')
    inputs.update({n: (ROOT / n).read_bytes() for n in (PRIOR, TRANSFORM, RUNNER, FIXTURE)})
    old, new = previous_stage(inputs[DRIVER].decode()), stage(inputs[DRIVER].decode())
    header = stage_header(inputs['tools/build34_exact_ownership.h'].decode())
    if sha(old.encode()) != pinned['staged_driver_sha256'] or sha(header.encode()) != pinned['staged_header_sha256']:
        raise ValueError('Factory source/ownership predecessor drift')
    reverted = once(new, FIELD + HELPER, '')
    for sig in SIGNATURES:
        reverted = once(reverted, method(new, sig), method(old, sig))
    if reverted != old or '#define PHX_KEXT_BUILD 34u\n' not in new:
        raise ValueError('Change outside the three audited methods and embedded state')

    out.mkdir(mode=0o700)
    for n, b in inputs.items():
        path = out / 'frozen' / n
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b)
    compiler = xcrun('--find', 'clang++')
    host_sdk = xcrun('--show-sdk-path')
    otool = xcrun('--find', 'otool')
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
            raise RuntimeError(f'{label} exited {result.returncode} (expected {expected}); diagnostics preserved')
        return result

    def member(text, begin, end):
        start = text.index(begin)
        return text[start:text.index(end, start)]

    def exercise(label, source, sanitizer='address,undefined', prior=False, broken=False):
        bodies = [method(source, sig) for sig in METHODS]
        fixture = inputs[FIXTURE].decode()
        for mark, body in {
            '// PHX34_FRAME': member(source, 'struct PhxGfxRbFrame {', '// Canned'),
            '    // PHX34_FIELDS': member(source, '    mutable phx34_exact::CallbackGate<> exactCallbacks;',
                                         '    uint64_t exactQueueSubmitted[2]'),
            '    // PHX34_QUEUE': member(source, '    struct GpuQueue {', '    uint64_t gSeq{'),
            '    // PHX34_DECLS': '\n'.join('    ' + f.split('{', 1)[0].replace('PhxBringup::', '').strip() + ';'
                                          for f in bodies),
            '// PHX34_METHODS': '\n'.join(bodies),
        }.items():
            fixture = once(fixture, mark, body)
        cpp, binary = out / (label + '.cpp'), out / label
        cpp.write_text(fixture)
        compiled = run([compiler, '--driver-mode=g++', '-std=c++17', '-arch', 'x86_64', '-isysroot', host_sdk, '-O1', '-g',
                        '-Wall', '-Wextra', '-Werror', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all',
                        '-I' + str(out / 'frozen/tools'), '-I' + str(out / 'frozen/src/phxbringup'),
                        cpp, '-o', binary], label + '-compile')
        if compiled.stderr or re.search(rb'IOKit|Metal|vulkan|PhxAccel', run([otool, '-L', binary], label + '-links').stdout, re.I):
            raise ValueError('Unexpected compilation diagnostics or device linkage')
        result = run([binary, *(['prior'] if prior else [])], label + '-test', expected=86 if broken else 0)
        if broken:
            if not result.stderr.startswith(b'failed '):
                raise ValueError('Broken variant did not fail an assertion')
            return None
        matched = re.fullmatch(rb'PASS (\d+) PSP handoff checks\n', result.stdout)
        if not matched or result.stderr:
            raise ValueError('Missing check count or unexpected sanitizer diagnostics')
        return int(matched[1])

    counts = {'prior_control': exercise('prior', old, prior=True), 'checked_ASan_UBSan': exercise('asan', new),
              'checked_TSan': exercise('tsan', new, sanitizer='thread')}
    if counts['checked_ASan_UBSan'] != counts['checked_TSan']:
        raise ValueError('Sanitizer runs exercised different scenarios')
    mutations = {
        'no_raw_closure': once(new, HELPER, once(HELPER, '        exactRawWriters.close();\n', '')),
        'no_adoption_veto': change(new, ADOPT, ('if (__atomic_load_n(&exactPspUncertain, __ATOMIC_ACQUIRE))', 'if (false)')),
        'no_command_quarantine': change(new, COMMAND, ('        quarantinePsp();\n', '')),
        'no_create_quarantine': change(new, RING, ('                    quarantinePsp();', '                    ringMc = 0;')),
        'clear_despite_destroy_timeout': change(new, RING, ('            quarantinePsp();\n        } else {',
                                                           '            quarantinePsp();\n            clearRing();\n        } else {')),
    }
    for label, source in mutations.items():
        exercise(label, source, broken=True)
    native = native_check(out / 'native', inputs, old, new, header, sdk, kdk, pinned['native_import_count'],
                          pinned['compiler_warnings']['proposed'], json.loads(inputs[REFERENCE]), compiler)
    if any(sha((ROOT / n).read_bytes()) != h for n, h in baseline.items()) or any(
            (ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Source or protected production inputs changed during checks')
    evidence = dict(status='passed-PSP-uncertainty-CPU-and-native-object', kernel_build=34,
                    frozen_predecessor=sha(old.encode()), staged_driver_sha256=sha(new.encode()),
                    frozen_input_count=len(inputs), frozen_new_input_sha256={n: sha(inputs[n]) for n in (PRIOR, FIXTURE, TRANSFORM, RUNNER)},
                    checks=counts, assertion_mutations_detected=list(mutations), production_inputs_unchanged=len(protected),
                    GPU_executed=False, IOKit_opened=False, installed=False, external_writer_drain_proved=False,
                    native_reader_bound=False, R3_complete=False, **native)
    (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
