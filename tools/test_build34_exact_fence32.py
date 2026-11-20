#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Freeze and test the original fence32 arithmetic primitive on the CPU only."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_submit import once
from test_build34_exact_wait import PRIOR as WAIT_PRIOR
from test_build34_exact_ownership import PINNED, ROOT, sha

PRIOR = {
    **WAIT_PRIOR,
    'tools/build34_exact_wait.py': '3342e090cb38695524283d5c31f63452f3a7d7b36109479c7e05c60e75549f0f',
    'tools/test_build34_exact_wait.py': '7a4e88d59360b37396712ed0530424a6b58808e545b8ae7eedcf1946214a60d0',
    'tests/test_build34_exact_wait.cpp': 'f8c44f01dae4d9777fa1c0e0454900f7fe1174c0d05ef0ac04e3e918c456f992',
}
HEADER = 'tools/build34_exact_fence32.h'
FIXTURE = 'tests/test_build34_exact_fence32.cpp'
RUNNER = 'tools/test_build34_exact_fence32.py'


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    paths = [*PINNED, *PRIOR, HEADER, FIXTURE, RUNNER, 'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production/prior input drift: ' + name)
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    source, header = inputs[FIXTURE].decode(), inputs[HEADER].decode()
    compiled = out / 'cpu'
    compiled.mkdir()
    target = compiled / Path(FIXTURE).name
    target.write_text(source)
    header_path = compiled / Path(HEADER).name
    header_path.write_text(header)
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++14', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-fno-exceptions', '-fno-rtti', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if p.returncode == 0 or b'failed ' not in p.stderr:
                raise ValueError(label + ' did not detect the intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return p.stdout.decode()

    def exercise(label, proposed, broken=False):
        header_path.write_text(proposed)
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-fsanitize=address,undefined', '-MMD', '-MF', dep, target, '-o', binary], label + '-compile')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if {str(Path(p).resolve()) for p in deps} != {str(target), str(header_path)}:
            raise ValueError('Unexpected unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search('IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    result = re.fullmatch(r'PASS fence32 window: (\d+) checks; exhaustive widths 2/3/4; '
                          r'20000 sustained steps; GPU_executed=false\n', exercise('window', header))
    if not result:
        raise ValueError('Missing complete CPU suite result')
    changes = {
        'full-wrap-span-admitted': ('sequence - floor_ < modulus', 'sequence - floor_ <= modulus'),
        'global-gap-confused-with-outstanding-count': ('sequence - floor_ < modulus', 'sequence - submitted_ < modulus'),
        'half-wrap-only-refusal': ('sequence - floor_ < modulus', 'sequence - floor_ < modulus / 2'),
        'live-generation-reseeded': ('if (ready_ || !generation ||', 'if (!generation ||'),
        'same-generation-reused': ('generation <= generation_', 'generation < generation_'),
        'duplicate-submission-accepted': ('sequence > submitted_', 'sequence >= submitted_'),
        'wrong-generation-observed': ('!ready_ || generation != generation_ || uint64_t{raw} > mask',
                                      '!ready_ || (generation - generation) || uint64_t{raw} > mask'),
        'invalidated-window-observed': ('!ready_ || generation != generation_ || uint64_t{raw} > mask',
                                       'generation != generation_ || uint64_t{raw} > mask'),
        'future-or-regressing-read-accepted': ('if (distance > submitted_ - floor_) return false;',
                                             '(void)distance;'),
        'refused-observation-clobbers-output': ('if (!ready_ || generation != generation_ || uint64_t{raw} > mask) return false;',
                                               'if (!ready_ || generation != generation_ || uint64_t{raw} > mask) { completed=0; return false; }'),
        'modular-wrap-lost': ('(uint64_t{raw} - (floor_ & mask)) & mask', 'uint64_t{raw} - (floor_ & mask)'),
        'observed-floor-not-retained': ('floor_ += distance;\n        completed = floor_;',
                                       'completed = floor_ + distance;'),
    }
    for label, (old, new) in changes.items():
        exercise(label, once(header, old, new), broken=True)
    header_path.write_text(header)
    if target.read_text() != source or any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production drift')
    report = dict(status='passed-CPU-only-fence32-window', kernel_build=34, checks=int(result[1]),
                  asan_ubsan=True, cxx14_no_exceptions_no_rtti=True, exhaustive_widths=[2, 3, 4],
                  sustained_steps=20000, detected_mutations=list(changes),
                  exact_full_wrap_and_cross_queue_global_gaps_refused=True,
                  output_and_window_preserved_on_refusal=True, device_reader_implemented=False,
                  coherent_nonregressing_same_generation_read_is_unproved_precondition=True,
                  missing_coherency_counterexample_reproduced=True,
                  production_or_staged_driver_calls_this_primitive=False,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()},
                  protected_production_file_count=len(names), production_ABI_prior_transforms_runtime_unchanged=True,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
