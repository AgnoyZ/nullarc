"""Execute actual disposable-cache helpers; Foundation LRU requires macOS."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def extract_wrapper(source):
    start = 'static NSData *nvmtl_address_shader_g(const void *data, size_t len, uint32_t flags, uint32_t *info) {'
    end = 'static NSData *nvmtl_address_shader_g_uncached(const void *data, size_t len, uint32_t flags, uint32_t *info) {'
    if source.count(start) != 1 or source.count(end) != 1:
        raise RuntimeError('Expected unique actual shader cache wrapper and following definition')
    a, b = source.index(start), source.index(end)
    if b <= a:
        raise RuntimeError('Shader cache definitions reordered')
    return source[a:b]


def exercise(out):
    compiler = shutil.which('clang')
    system = platform.system()
    if system not in ('Linux', 'Darwin') or not compiler:
        raise RuntimeError('Cache I/O execution requires POSIX Clang; not a pass on this host')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    out.mkdir(parents=True)
    root = ROOT / 'src/nmplugin'
    common = [compiler, '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
              '-fno-sanitize-recover=all', '-I' + str(root), '-I' + str(out)]
    binary = out / 'cache-io-test'
    subprocess.run(common + ['-std=c11', '-pthread', str(ROOT / 'tests/test_cache_io.c'), '-o', str(binary)], check=True, timeout=120)
    work = out / 'files'
    work.mkdir()
    io = json.loads(subprocess.check_output([str(binary), str(work)], text=True, timeout=60))
    if not io.get('io_contract') or io.get('concurrent_writes') != 480 or io.get('hardware_executed') is not False:
        raise RuntimeError('Unexpected I/O report')
    wrapper = extract_wrapper((root / 'nvmtl_vk.c').read_text(encoding='utf-8'))
    (out / 'cache_wrapper.inc').write_text(wrapper, encoding='utf-8')
    report = {'io': io, 'foundation': 'not executed: requires macOS'}
    if system == 'Darwin':
        binary = out / 'cache-lru-test'
        subprocess.run(common + ['-fobjc-arc', '-framework', 'Foundation', str(ROOT / 'tests/test_cache_lru.m'), '-o', str(binary)], check=True, timeout=120)
        report['foundation'] = json.loads(subprocess.check_output([str(binary)], text=True, timeout=60))
        if report['foundation'].get('lru_operations') != 20000 or report['foundation'].get('actual_wrapper') is not True:
            raise RuntimeError('Unexpected LRU report')
    inputs = [root / n for n in ('nvmtl_cache_io.h', 'nvmtl_lru_cache.h', 'nvmtl_vk.c', 'NVMTLLibraryLoad.m')]
    inputs += [ROOT / 'tests' / n for n in ('test_cache_io.c', 'test_cache_lru.m')]
    report['inputs_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    report['limitation'] = 'Host cache correctness only; no target shader execution, performance or power-loss durability claim.'
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
