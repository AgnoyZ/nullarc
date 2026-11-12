"""Run actual base-shader entry, bounded writer and atomic file I/O on macOS."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

from test_translation_flight import extract_entry, extract_save

ROOT = Path(__file__).resolve().parents[1]


def exercise(out, sanitizer='address,undefined'):
    compiler = shutil.which('clang')
    if platform.system() != 'Darwin' or not compiler:
        raise RuntimeError('Actual async Foundation/cache I/O requires macOS Clang')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    source = ROOT / 'src/nmplugin/NVMTLLibraryLoad.m'
    text = source.read_text(encoding='utf-8')
    actual = extract_save(text) + extract_entry(text)
    out.mkdir(parents=True)
    (out / 'translation_entry.inc').write_text(actual, encoding='utf-8')
    binary = out / 'async-cache-test'
    subprocess.run([compiler, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-Wno-deprecated-declarations', '-fobjc-arc', '-fblocks', '-pthread',
                    '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
                    '-I' + str(out), '-I' + str(ROOT / 'src/nmplugin'),
                    str(ROOT / 'tests/test_async_cache.m'), '-framework', 'Foundation',
                    '-o', str(binary)], check=True, timeout=120)
    completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    if completed.returncode:
        raise RuntimeError('Native async-cache fixture failed: ' + completed.stderr)
    result = json.loads(completed.stdout)
    if (result.get('actual_entry') is not True or result.get('actual_cache_io') is not True or
            result.get('hardware_executed') is not False or result.get('stress_requests') != 1600):
        raise RuntimeError('Unexpected async-cache report')
    paths = [source, ROOT / 'src/nmplugin/nvmtl_async_cache.h', ROOT / 'src/nmplugin/nvmtl_cache_io.h',
             ROOT / 'src/nmplugin/nvmtl_translation_flight.h', ROOT / 'tests/test_async_cache.m',
             ROOT / 'tools/test_translation_flight.py', Path(__file__)]
    result['inputs_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['actual_body_sha256'] = hashlib.sha256(actual.encode()).hexdigest()
    result['sanitizer'] = sanitizer
    result['limitations'] = ('Real atomic host-file I/O and actual base-entry/writer control flow with synthetic '
                             'translator output; no real shader execution, target GPU, FPS or latency measurement.')
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sanitizer', choices=['address,undefined', 'thread'], default='address,undefined')
    args = parser.parse_args()
    exercise(args.out, args.sanitizer)
