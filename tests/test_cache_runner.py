from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_shader_cache import extract_wrapper


class CacheSourceTests(unittest.TestCase):
    def test_actual_wrapper_extraction_fails_closed(self):
        source = (ROOT / 'src/nmplugin/nvmtl_vk.c').read_text(encoding='utf-8')
        extracted = extract_wrapper(source)
        self.assertTrue(extracted.endswith('}\n'))
        self.assertNotIn('static NSData *nvmtl_address_shader_g_uncached(', extracted)
        for changed in ('', source + source, source.replace('static NSData *nvmtl_address_shader_g(', 'static NSData *missing(')):
            with self.assertRaises(RuntimeError):
                extract_wrapper(changed)

    def test_each_migrated_format_has_matching_reader_writer(self):
        source = (ROOT / 'src/nmplugin/NVMTLLibraryLoad.m').read_text(encoding='utf-8')
        for kind in ('SPIRV', 'INDEX', 'LIBKEY'):
            lines = [line for line in source.splitlines() if 'NVMTL_CACHE_' + kind in line]
            self.assertEqual(len(lines), 2, kind)
            self.assertEqual(sum('nvmtl_cache_data(' in line for line in lines), 1)
            self.assertEqual(sum('nvmtl_cache_save(' in line for line in lines), 1)
        self.assertIn('nvmtl_index_from_record(lib, rec,', source)
        self.assertIn('!memcmp(r.edge, edge, sizeof edge)', source)
        self.assertIn('spvData.length >= 20', source)


if __name__ == '__main__':
    unittest.main()
