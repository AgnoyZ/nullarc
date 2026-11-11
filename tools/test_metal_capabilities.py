"""Exercise actual optional-capability query bodies without Metal or a GPU."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('supportsFunctionPointers', 'supportsFunctionPointersFromRender',
           'supportsDynamicLibraries', 'supportsRenderDynamicLibraries',
           'supportsShaderBarycentricCoordinates', 'areBarycentricCoordsSupported',
           'supportsFamily', 'supportsFeatureSet', 'hasUnifiedMemory')


def extract_sources(device, library, backend):
    parts = []
    for name in METHODS:
        # Bodies here have no nested braces. Fail closed if a future implementation grows one.
        pattern = r'^- \(BOOL\)' + name + r'(?::\([^)]*\)(\w+))? \{([^{}]*)\}'
        found = re.findall(pattern, device, re.M)
        if len(found) != 1:
            raise RuntimeError('Expected one simple actual capability method: ' + name)
        arg, body = found[0]
        parts.append('static int test_' + name + '(' + ('int64_t ' + arg if arg else 'void') + ') {' + body + '}')
    for source, signature in ((library, 'uint32_t nvmtl_translation_capabilities(void)'),
                              (backend, 'int nvmtl_vk_backend_ready(void)')):
        found = re.findall(r'^' + re.escape(signature) + r' \{[^{}]*\}', source, re.M)
        if len(found) != 1:
            raise RuntimeError('Expected one actual capability dependency: ' + signature)
        parts.insert(0, found[0])
    return '\n'.join(parts) + '\n'


def exercise(out):
    compiler = shutil.which('clang++')
    if platform.system() not in ('Linux', 'Darwin') or not compiler:
        raise RuntimeError('Capability execution requires POSIX Clang; not a pass on this host')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    root = ROOT / 'src/nmplugin'
    sources = [root / name for name in ('NVMTLDevice.m', 'NVMTLLibraryLoad.m', 'nvmtl_vk.c')]
    extracted = extract_sources(*(p.read_text(encoding='utf-8') for p in sources))
    out.mkdir(parents=True)
    (out / 'capabilities.inc').write_text(extracted, encoding='utf-8')
    binary = out / 'capabilities-test'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I' + str(out),
                    '-I' + str(root), str(ROOT / 'tests/test_metal_capabilities.cpp'), '-o', str(binary)], check=True, timeout=120)
    result = json.loads(subprocess.check_output([str(binary)], text=True, timeout=30))
    if result != {'dependency_combinations': 96, 'hardware_executed': False}:
        raise RuntimeError('Unexpected capability test report')
    result['actual_bodies_sha256'] = hashlib.sha256(extracted.encode()).hexdigest()
    result['inputs_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sources + [root / 'nvmtl_capabilities.h', ROOT / 'tests/test_metal_capabilities.cpp']}
    result['limitation'] = 'Actual query/dependency bodies with fake dependency presence. Does not certify shader execution, Metal family conformance or memory coherence.'
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
