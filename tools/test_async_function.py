"""Run actual async function API bodies with real Metal snapshots on macOS."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

from test_async_library import extract as extract_library

ROOT = Path(__file__).resolve().parents[1]
METHODS = (
    '- (void)newFunctionWithName:(NSString *)name constantValues:(MTLFunctionConstantValues *)cv\n          completionHandler:',
    '- (void)newFunctionWithDescriptor:(id)desc completionHandler:',
)


def extract(source, device):
    methods = []
    for signature in METHODS:
        matches = re.findall(r'^' + re.escape(signature) + r'[^\{]*\{.*?^}', source, re.M | re.S)
        if len(matches) != 1:
            raise RuntimeError('Expected one actual async function method: ' + signature)
        method = matches[0]
        if ('completionHandler:' not in method or 'if (!handler) return;' not in method or
                'addOperationWithBlock:' not in method or 'dispatch_async(' not in method or
                'copy]' not in method or method.index('copy]') > method.index('addOperationWithBlock:')):
            raise RuntimeError('Expected nil-handler refusal, snapshot, shared queue and dispatched callback')
        methods.append(method)
    # This plugin is built as one translation unit; do not accidentally create a second pool.
    if device.index('static NSOperationQueue *nvmtl_pipeline_compile_queue(void) {') > device.index('#import "NVMTLObjects.m"'):
        raise RuntimeError('Function methods must see the existing static compile queue')
    _, helpers = extract_library(device)
    return '\n'.join(methods) + '\n', helpers


def exercise(out, sanitizer='address,undefined'):
    compiler = shutil.which('clang')
    if platform.system() != 'Darwin' or not compiler:
        raise RuntimeError('Actual Foundation/Metal function execution requires macOS Clang')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    source = ROOT / 'src/nmplugin/NVMTLObjects.m'
    device = ROOT / 'src/nmplugin/NVMTLDevice.m'
    methods, helpers = extract(source.read_text(encoding='utf-8'), device.read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    (out / 'async_function_methods.inc').write_text(methods, encoding='utf-8')
    (out / 'async_function_queue.inc').write_text(helpers, encoding='utf-8')
    binary = out / 'async-function-test'
    subprocess.run([compiler, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-Wno-deprecated-declarations', '-fobjc-arc', '-fblocks', '-pthread',
                    '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
                    '-I' + str(out), str(ROOT / 'tests/test_async_function.m'),
                    '-framework', 'Foundation', '-framework', 'Metal', '-o', str(binary)],
                   check=True, timeout=120)
    reports = []
    for width in (1, 2):
        completed = subprocess.run([str(binary), str(width)], capture_output=True, text=True, timeout=120)
        if completed.returncode:
            raise RuntimeError('Native async-function fixture failed: ' + completed.stderr)
        report = json.loads(completed.stdout)
        if (report.get('actual_methods') != 2 or report.get('actual_queue') is not True or
                report.get('hardware_executed') is not False or report.get('stress_requests') != 1600 or
                report.get('width') != width or report.get('peak_active') != width or
                any(report.get(flag) is not True for flag in ('snapshot_and_return_before_build',
                    'callback_reentry', 'retained_owner', 'error_and_warning_propagation',
                    'nil_handler_skips_work', 'native_descriptor_subclass'))):
            raise RuntimeError('Unexpected async-function report')
        reports.append(report)
    paths = [source, device, ROOT / 'tests/test_async_function.m', Path(__file__),
             ROOT / 'tools/test_async_library.py']
    result = {'sanitizer': sanitizer, 'runs': reports,
              'actual_methods_sha256': hashlib.sha256(methods.encode()).hexdigest(),
              'actual_queue_sha256': hashlib.sha256(helpers.encode()).hexdigest(),
              'inputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'limitations': 'Actual async API/queue bodies with real Foundation/Metal constants and descriptors; synchronous function creation and logging are synthetic. No translator, GPU execution, target latency or FPS benchmark.'}
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sanitizer', choices=['address,undefined', 'thread'], default='address,undefined')
    args = parser.parse_args()
    exercise(args.out, args.sanitizer)
