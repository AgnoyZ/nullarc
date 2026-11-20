#!/usr/bin/env python3
"""Extract actual display copy/inline SSE; compare full bytes under ASan/UBSan."""
import hashlib
from pathlib import Path
import subprocess

from test_upstream34_framebuffer import method

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / 'src/phxaccel/accel/nvrm-accel.cpp').read_text()
    start = source.index('    const bool wide =', source.index('IOReturn NVDisplayPipe::performTransaction('))
    end = source.index('    fIopVblSeq =', start)
    copy = source[start:end]
    template = (ROOT / 'tests/build34_present_copy.cpp').read_text()
    template = template.replace('// ACTUAL_SSE', method(source, 'static void nvIopRowSSE('))
    template = template.replace('// ACTUAL_COPY', copy)
    build = ROOT / 'build/tests/build34-present-copy'
    build.mkdir(parents=True, exist_ok=True)
    generated = build / 'production.cpp'
    generated.write_text(template)
    binary = build / 'test'
    subprocess.run(['clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-fno-vectorize', '-fno-slp-vectorize', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', str(generated),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
    print('extracted_production_harness_sha256=' + hashlib.sha256(generated.read_bytes()).hexdigest())
    print('hardware_executed=false; host RAM tests do not prove scanout/cache-coherency or FPS')


if __name__ == '__main__':
    main()
