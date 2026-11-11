"""Run the actual submit-begin and hold-release bodies with explicit API fakes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def extract_submit(source):
    pairs = [('static void nvmtl_pre_drop(nvmtl_prologue *p)\n{', 'struct nvmtl_inflight {'),
             ('int nvmtl_vk_submit_begin_at(nvk_cmdbuf *c, nvmtl_inflight *f, const char *who)\n{',
              'int nvmtl_vk_submit_finish(nvmtl_inflight *f)\n{')]
    result = []
    for start, end in pairs:
        if source.count(start) != 1 or source.count(end) != 1:
            raise RuntimeError('Expected unique actual submit/hold-release definition')
        a, b = source.index(start), source.index(end)
        if b <= a:
            raise RuntimeError('Submit definitions reordered')
        result.append(source[a:b])
    return '\n'.join(result)


def exercise(out):
    compiler = shutil.which('clang')
    if platform.system() not in ('Linux', 'Darwin') or not compiler:
        raise RuntimeError('Submit execution requires POSIX Clang; not a pass on this host')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    source = ROOT / 'src/nmplugin/nvmtl_vk.c'
    harness = ROOT / 'tests/test_submit_begin.c'
    extracted = extract_submit(source.read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    (out / 'submit_begin.inc').write_text(extracted, encoding='utf-8')
    binary = out / 'submit-begin-test'
    subprocess.run([compiler, '-std=c11', '-pthread', '-Wall', '-Wextra', '-Werror',
                    '-Wno-missing-field-initializers', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-I' + str(out), str(harness), '-o', str(binary)],
                   check=True, timeout=120)
    result = json.loads(subprocess.check_output([str(binary)], text=True, timeout=30))
    if result != {'cases': 33, 'hardware_executed': False}:
        raise RuntimeError('Unexpected submit report')
    result['actual_bodies_sha256'] = hashlib.sha256(extracted.encode()).hexdigest()
    result['inputs_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, harness)}
    result['limitation'] = 'Actual begin/release decision bodies; fake API, timing, witness and retirement observations. No real GPU, fences, reset, sleep or power validation.'
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
