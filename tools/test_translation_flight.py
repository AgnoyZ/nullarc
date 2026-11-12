"""Execute actual base-shader translation entry and sharing on macOS with a fake translator."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def extract_entry(source):
    signature = 'NSData *nvmtl_compile_library_entry('
    matches = re.findall(r'^' + re.escape(signature) + r'.*?^}', source, re.M | re.S)
    if len(matches) != 1:
        raise RuntimeError('Expected one actual base translation entry')
    entry = matches[0]
    if 'nvmtl_translation_share(' not in entry or 'nvmtl_translation_key(air, ll, stage, gXlateTag)' not in entry:
        raise RuntimeError('Actual entry must use full translation identity and shared producer')
    if entry.index('nvmtl_cache_data(') > entry.index('nvmtl_translation_share('):
        raise RuntimeError('Disk hits must bypass the new sharing/key path')
    return entry + '\n'


def exercise(out, sanitizer='address,undefined'):
    compiler = shutil.which('clang')
    if platform.system() != 'Darwin' or not compiler:
        raise RuntimeError('Actual Foundation sharing requires macOS Clang; not a native pass on this host')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    source = ROOT / 'src/nmplugin/NVMTLLibraryLoad.m'
    entry = extract_entry(source.read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    (out / 'translation_entry.inc').write_text(entry, encoding='utf-8')
    binary = out / 'translation-flight-test'
    subprocess.run([compiler, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-Wno-deprecated-declarations', '-fobjc-arc', '-fblocks', '-pthread',
                    '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
                    '-I' + str(out), '-I' + str(ROOT / 'src/nmplugin'),
                    str(ROOT / 'tests/test_translation_flight.m'), '-framework', 'Foundation',
                    '-o', str(binary)], check=True, timeout=120)
    completed = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=120)
    result = json.loads(completed.stdout)
    if (result.get('actual_entry') is not True or result.get('hardware_executed') is not False or
            result.get('same_shader_requests') != 32 or result.get('same_shader_translations') != 1 or
            result.get('stress_requests') != 1600):
        raise RuntimeError('Unexpected translation-sharing report')
    paths = [source, ROOT / 'src/nmplugin/nvmtl_translation_flight.h',
             ROOT / 'tests/test_translation_flight.m', Path(__file__)]
    result['inputs_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['actual_entry_sha256'] = hashlib.sha256(entry.encode()).hexdigest()
    result['sanitizer'] = sanitizer
    result['limitations'] = ('Actual sharing and base-entry control flow with fake translator, disk cache and logging. '
                             'No real AIR/SPIR-V validation, shader execution, target GPU/FPS or cold-start latency measurement.')
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sanitizer', choices=['address,undefined', 'thread'], default='address,undefined')
    args = parser.parse_args()
    exercise(args.out, args.sanitizer)
