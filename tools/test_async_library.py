"""Execute actual async library API bodies and their existing compile queue on macOS."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
METHODS = (
    '- (void)newLibraryWithSource:(NSString *)src options:(MTLCompileOptions *)opt completionHandler:',
    '- (void)newLibraryWithStitchedDescriptor:(id)desc completionHandler:',
)


def extract(source):
    methods, helpers = [], []
    for signature in METHODS:
        matches = re.findall(r'^' + re.escape(signature) + r'[^\n]*\{.*?^}', source, re.M | re.S)
        if len(matches) != 1:
            raise RuntimeError('Expected one actual async method: ' + signature)
        method = matches[0]
        if ('addOperationWithBlock:' not in method or 'dispatch_async(' not in method or
                'copy]' not in method or method.index('copy]') > method.index('addOperationWithBlock:')):
            raise RuntimeError('Expected input snapshot, queued compilation and dispatched completion')
        methods.append(method)
    for signature in ('static int nvmtl_sysctl_int(const char *name)',
                      'static NSInteger nvmtl_pipeline_compile_width(void)',
                      'static NSOperationQueue *nvmtl_pipeline_compile_queue(void)'):
        matches = re.findall(r'^' + re.escape(signature) + r' \{.*?^}', source, re.M | re.S)
        if len(matches) != 1:
            raise RuntimeError('Expected one actual existing compile helper: ' + signature)
        helpers.append(matches[0])
    return '\n'.join(methods) + '\n', '\n'.join(helpers) + '\n'


def exercise(out, sanitizer='address,undefined'):
    compiler = shutil.which('clang')
    if platform.system() != 'Darwin' or not compiler:
        raise RuntimeError('Actual Foundation/Metal descriptor execution requires macOS Clang')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    source = ROOT / 'src/nmplugin/NVMTLDevice.m'
    methods, helpers = extract(source.read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    (out / 'async_library_methods.inc').write_text(methods, encoding='utf-8')
    (out / 'async_library_queue.inc').write_text(helpers, encoding='utf-8')
    binary = out / 'async-library-test'
    subprocess.run([compiler, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-Wno-deprecated-declarations', '-fobjc-arc', '-fblocks', '-pthread',
                    '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
                    '-I' + str(out), str(ROOT / 'tests/test_async_library.m'),
                    '-framework', 'Foundation', '-framework', 'Metal', '-o', str(binary)],
                   check=True, timeout=120)
    reports = []
    for width in (1, 2):
        completed = subprocess.run([str(binary), str(width)], capture_output=True, text=True, timeout=120)
        if completed.returncode:
            raise RuntimeError('Native async-library fixture failed: ' + completed.stderr)
        report = json.loads(completed.stdout)
        if (report.get('actual_methods') != 2 or report.get('actual_queue') is not True or
                report.get('hardware_executed') is not False or report.get('stress_requests') != 1600 or
                report.get('width') != width or report.get('peak_active') != width or
                any(report.get(flag) is not True for flag in ('snapshot_and_return_before_build',
                    'callback_reentry', 'retained_owner', 'error_and_warning_propagation'))):
            raise RuntimeError('Unexpected async-library report')
        reports.append(report)
    paths = [source, ROOT / 'tests/test_async_library.m', Path(__file__)]
    result = {'sanitizer': sanitizer, 'runs': reports,
              'actual_methods_sha256': hashlib.sha256(methods.encode()).hexdigest(),
              'actual_queue_sha256': hashlib.sha256(helpers.encode()).hexdigest(),
              'inputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'limitations': 'Actual API/queue bodies with real Foundation/Metal descriptors, synthetic synchronous compilation and logging; no Apple shader compiler, translator, target GPU, latency or FPS benchmark.'}
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sanitizer', choices=['address,undefined', 'thread'], default='address,undefined')
    args = parser.parse_args()
    exercise(args.out, args.sanitizer)
