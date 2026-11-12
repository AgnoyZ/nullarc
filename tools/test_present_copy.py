"""Execute the current display-copy bodies on x86-64 host RAM, never on a GPU."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/phxaccel/accel/nvrm-accel.cpp'


def definition(source, signature):
    matches = re.findall(r'^' + re.escape(signature) + r'.*?^}', source, re.M | re.S)
    if len(matches) != 1:
        raise RuntimeError('Expected one actual definition: ' + signature)
    return matches[0]


def extract_source(source):
    signatures = ['struct NVIopShadow {', 'static void nvIopShadowDrop(',
                  'static SInt64 nvIopCopyDamage(', 'static void nvIopRowSSE(',
                  'static void nvIopCopyFull(']
    # The one-line drop function needs its own boundary, not the next function's closing brace.
    drop = re.findall(r'^static void nvIopShadowDrop\([^\n]+', source, re.M)
    if len(drop) != 1:
        raise RuntimeError('Expected one shadow invalidation definition')
    parts = [definition(source, signatures[0]) + ';',
             'static NVIopShadow gIopShadow[kNvMaxFB];', drop[0],
             definition(source, signatures[2]),
             '#define nvIopRowSSE actualRowSSE', definition(source, signatures[3]),
             '#undef nvIopRowSSE',
             # Test-only call counting; the assembly body and full/damage methods stay unmodified.
             'static unsigned sseCalls;',
             'static void nvIopRowSSE(const void *s, void *d, unsigned long n, bool l) '
             '{ ++sseCalls; actualRowSSE(s, d, n, l); }',
             definition(source, signatures[4])]
    return '\n'.join(parts) + '\n'


def check_transaction_width(source):
    method = source.split('IOReturn NVDisplayPipe::performTransaction(', 1)[1].split(
        'static int nvacceliop_sysctl', 1)[0]
    if ('const unsigned words = w;' not in method or
            '!phx780m::visibleRowFits(w, pitch)' not in method or
            '!phx780m::visibleRowFits(w, q.pitch)' not in method or
            method.index('visibleRowFits') > method.index('nvIopCopyDamage(')):
        raise RuntimeError('Present must validate both pitches before copying only visible pixels')


def exercise(out, sanitizer='address,undefined'):
    compiler = shutil.which('clang++')
    if platform.system() not in ('Linux', 'Darwin') or platform.machine().lower() not in ('x86_64', 'amd64') or not compiler:
        raise RuntimeError('Actual streaming copy requires POSIX x86-64 Clang; not a pass on this host')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    source = SOURCE.read_text(encoding='utf-8')
    check_transaction_width(source)
    extracted = extract_source(source)
    out.mkdir(parents=True)
    (out / 'present-copy.inc').write_text(extracted, encoding='utf-8')
    binary = out / 'present-copy-test'
    flags = ['-std=c++17', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    if sanitizer == 'memory':
        flags += ['-fPIE', '-pie', '-fsanitize-memory-track-origins=2']
    subprocess.run([compiler, *flags, '-I' + str(out), '-I' + str(ROOT / 'src/phxaccel'),
                    str(ROOT / 'tests/test_present_copy.cpp'), '-o', str(binary)], check=True, timeout=120)
    completed = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=120)
    result = json.loads(completed.stdout)
    if result.get('full_cases', 0) < 20000 or result.get('damage_cases', 0) < 100 or result.get('hardware_executed') is not False:
        raise RuntimeError('Unexpected copy test report')
    inputs = [SOURCE, ROOT / 'src/phxaccel/PhxCopyPath.hpp', ROOT / 'tests/test_present_copy.cpp', Path(__file__)]
    result['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    result['actual_methods_sha256'] = hashlib.sha256(extracted.encode()).hexdigest()
    result['sanitizer'] = sanitizer
    result['limitation'] = ('Actual scalar/movnti/SSE copy on ordinary host RAM with fake allocation/atomics. '
                            'Sentinels check stores made by inline assembly, which sanitizers do not instrument. '
                            'No kernel FPU/preemption, WC/BAR mapping, display timing or target FPS evidence.')
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sanitizer', choices=['address,undefined', 'memory'], default='address,undefined')
    args = parser.parse_args()
    exercise(args.out, args.sanitizer)
