# SPDX-License-Identifier: MIT
"""Replay stale MES command writebacks against the actual build34 bootstrap on CPU."""

import argparse
import json
from pathlib import Path
import platform
import re
import struct
import subprocess

from build34_exact_mes_status import SUBMIT, previous_bootstrap, stage_bootstrap
from test_build34_exact_bootstrap_progress import BOOT, FIXTURE, HEADERS, ROOT, git, method, once, sha, xcrun


PRIOR = 'docs/validation/build34-r3-bootstrap-progress-offline-20261121.json'
NEW_FIXTURE = 'tests/test_build34_exact_mes_status.c'
NEW = (PRIOR, NEW_FIXTURE, 'tools/build34_exact_mes_status.py', 'tools/test_build34_exact_mes_status.py')


def test(out):
    out = out.resolve()
    if ((platform.system(), platform.machine()) != ('Darwin', 'x86_64') or out.exists() or ROOT / 'build' not in out.parents
            or not out.name.endswith('-private') or git('symbolic-ref', '--short', 'HEAD').strip() != b'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 on x86_64 macOS and fresh private output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').decode().splitlines()
    if len(protected) != 172 or git('status', '--porcelain', '--', *protected):
        raise ValueError('Production inputs drifted')
    baseline = {n: sha((ROOT / n).read_bytes()) for n in protected}
    prior = json.loads((ROOT / PRIOR).read_bytes())
    pins = prior['frozen_input_sha256']
    raw = json.loads((ROOT / 'docs/validation/build34-r3-raw-handoff-offline-20261121.json').read_bytes())
    pins = raw['input_sha256'] | pins
    frozen = {n: (ROOT / n).read_bytes() for n in (*pins, *NEW)}
    if prior['GPU_executed'] or raw['GPU_executed'] or any(sha(frozen[n]) != digest for n, digest in pins.items()):
        raise ValueError('Predecessor input drift')
    before, after = (transform(frozen[BOOT].decode()) for transform in (previous_bootstrap, stage_bootstrap))
    if sha(before.encode()) != prior['checked_bootstrap_sha256'] or once(after, method(after, SUBMIT), method(before, SUBMIT)) != before:
        raise ValueError('Only the staged MES submission body may change')

    out.mkdir(mode=0o700)
    for name, data in frozen.items():
        target = out / 'frozen' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    base_fixture = once(frozen[FIXTURE].decode(), '/* Resolve the fake transport',
                        'static void completeMes(uint64_t wptr);\nstatic void injectDuringPacket(uint64_t addr);\n\n'
                        '/* Resolve the fake transport')
    base_fixture = once(base_fixture, '        *word(in[0]) = (uint32_t)in[1];',
                        '        *word(in[0]) = (uint32_t)in[1];\n        injectDuringPacket(in[0]);')
    base_fixture = once(base_fixture, '            *word(SCH_WB + 64) = mesBells == badMesStatus ? 0 : 1;',
                        '            completeMes(in[1]);')
    base_fixture = once(base_fixture, 'int main(int argc, char **argv)', 'static int progress_main(int argc, char **argv)')
    (out / 'base-fixture.inc').write_text(base_fixture)
    compiler, sdk, otool = (xcrun('--find', 'clang'), xcrun('--show-sdk-path'), xcrun('--find', 'otool'))
    includes = out / 'frozen/tools/phxctl'
    if any('tools/phxctl/' + name not in frozen for name in HEADERS):
        raise ValueError('Missing bootstrap header pin')
    common = [compiler, '-arch', 'x86_64', '-isysroot', sdk, '-I', includes, '-std=gnu11']

    def run(label, args, expected=0):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode != expected:
            raise RuntimeError(f'{label} exited {p.returncode} (expected {expected}); see private diagnostics')
        return p

    def cpu(label, source, isolated=True, broken=False):
        actual = once(source, method(source, 'static int open_kext('), 'static int open_kext(void) { return mockOpen(); }\n')
        (out / 'cpu-mesboot.inc').write_text(actual)
        program = out / (label + '-cpu')
        flags = ['-DISOLATED'] if isolated else []
        run(label + '-compile', [*common, '-I', out, '-DCHECKED_STAGE', *flags, '-O1', '-g', '-fsanitize=address,undefined',
                                 '-fno-sanitize-recover=all', out / 'frozen' / NEW_FIXTURE, '-o', program])
        linked = run(label + '-links', [otool, '-L', program]).stdout
        if re.search(rb'IOKit|Metal|vulkan', linked, re.I):
            raise ValueError('CPU executable linked a device framework')
        result = run(label + '-slots', [program, 'slots'], expected=86 if broken else 0)
        if broken:
            if not result.stderr.startswith(b'failed '):
                raise ValueError('Expected a failed test assertion')
            return None
        slots = re.fullmatch(rb'PASS (\d+) MES status checks\n', result.stdout)
        inherited = run(label + '-regression', [program])
        progress = re.fullmatch(rb'PASS (\d+) mesboot progress checks\n', inherited.stdout)
        if not slots or not progress or result.stderr or inherited.stderr:
            raise ValueError('Unexpected sanitizer output')
        for case, selector in [('doorbell', 110), ('short-reply', 2), ('second-adoption', 112)]:
            error = run(label + '-' + case, [program, case], expected=74)
            if error.stdout or not re.fullmatch(rb'upstream34-layout: selector %d transport/size failure: [^\n]+\n' % selector, error.stderr):
                raise ValueError('Unexpected wrapper error result')
        return int(slots[1]), int(progress[1])

    old, new = cpu('prior', before, isolated=False), cpu('isolated', after)
    if old[1] != new[1] or new[1] != prior['ASan_UBSan_checks']['checked']:
        raise ValueError('Baseline regression count drifted')
    check = '      for (unsigned i = 0; i < 4; ++i) if (vr(status + i * 4)) return 1;\n'
    mutations = {'reuse_slot': once(after, '      status += sch_seq * 16;\n', ''),
                 'ignore_exhaustion': once(after, '      if (sch_seq >= 4) return 1;', '      if (sch_seq > 4) return 1;'),
                 'skip_preflight': once(after, '      status += sch_seq * 16;\n' + check, '      status += sch_seq * 16;\n'),
                 'skip_prepublication': once(after, '      if (vr(SCH_WB + 32) != (uint32_t)(sch_seq - 1)) return 1;\n' + check,
                                             '      if (vr(SCH_WB + 32) != (uint32_t)(sch_seq - 1)) return 1;\n'),
                 'accept_any_nonzero': once(after, 'reached && st == 1u', 'reached && st != 0')}
    for label, source in mutations.items():
        cpu(label, source, broken=True)

    objects, warnings = {}, {}
    for label, source in [('prior', before), ('isolated', after)]:
        text, obj = out / (label + '.c'), out / (label + '.o')
        text.write_text(source)
        result = run(label + '-object', [*common, '-Wall', '-Wextra', '-c', text, '-o', obj])
        blob = obj.read_bytes()
        if struct.unpack_from('<4I', blob) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Require x86_64 MH_OBJECT')
        objects[label] = sha(blob)
        warnings[label] = re.findall(r'warning: ([^\n]+)', result.stderr.decode())
    if warnings['prior'] != warnings['isolated'] or len(warnings['isolated']) != prior['unchanged_compiler_warnings']:
        raise ValueError('Native object warnings drifted')
    if any(sha((ROOT / n).read_bytes()) != digest for n, digest in baseline.items()) or any(
            (ROOT / n).read_bytes() != blob or (out / 'frozen' / n).read_bytes() != blob for n, blob in frozen.items()):
        raise ValueError('Input changed during verification')
    evidence = dict(status='passed-staged-isolated-mes-command-status', kernel_build=34, production_inputs_unchanged=len(protected),
                    new_inputs_sha256={n: sha(frozen[n]) for n in NEW}, preceding_bootstrap_sha256=sha(before.encode()),
                    staged_bootstrap_sha256=sha(after.encode()), reproduced_replays=[2, 3, 4],
                    ASan_UBSan_checks=dict(prior_slot_checks=old[0], isolated_slot_checks=new[0], inherited_checks_each=new[1]),
                    wrapper_exit_cases_each=3, broken_variants_detected=list(mutations), x86_64_MH_OBJECT_sha256=objects,
                    IOKit_opened=False, GPU_executed=False,
                    hardware_writer_drain_proved=False, installed=False, native_reader_bound=False, R3_complete=False)
    (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    test(parser.parse_args().out)
