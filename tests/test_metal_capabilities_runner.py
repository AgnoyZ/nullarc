from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_metal_capabilities import extract_sources, METHODS


class MetalCapabilityTests(unittest.TestCase):
    def test_actual_queries_and_missing_dependencies(self):
        root = ROOT / 'src/nmplugin'
        sources = [(root / n).read_text(encoding='utf-8') for n in ('NVMTLDevice.m', 'NVMTLLibraryLoad.m', 'nvmtl_vk.c')]
        extracted = extract_sources(*sources)
        for name in METHODS:
            self.assertIn('test_' + name + '(', extracted)
        for index in range(3):
            changed = sources[:]
            changed[index] = changed[index] * 2
            with self.assertRaises(RuntimeError):
                extract_sources(*changed)
        for name in METHODS:
            changed = sources[:]
            changed[0] = changed[0].replace('(BOOL)' + name, '(BOOL)missing')
            with self.assertRaises(RuntimeError):
                extract_sources(*changed)

    def test_existing_limit_queries_stay_backend_derived(self):
        source = (ROOT / 'src/nmplugin/NVMTLDevice.m').read_text(encoding='utf-8')
        samples = source.split('- (BOOL)nvmtlSampleCountOK:')[1].split('- (BOOL)supportsTextureSampleCount:')[0]
        self.assertIn('nvmtl_vk_pubcaps', samples)
        self.assertIn('return NO', samples)
        length = source.split('- (NSUInteger)maxBufferLength')[1].split('- (NSUInteger)minimumLinearTextureAlignment')[0]
        self.assertIn('nvmtl_vk_pubcaps', length)
        self.assertIn('return 0', length)


if __name__ == '__main__':
    unittest.main()
