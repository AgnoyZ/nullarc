from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_submit_begin import extract_submit


class SubmitExtractionTests(unittest.TestCase):
    def test_current_bodies_and_duplicate_refusal(self):
        source = (ROOT / 'src/nmplugin/nvmtl_vk.c').read_text(encoding='utf-8')
        result = extract_submit(source)
        self.assertEqual(result.count('int nvmtl_vk_submit_begin_at('), 1)
        self.assertEqual(result.count('static void nvmtl_pre_drop('), 1)
        self.assertNotIn('int nvmtl_vk_submit_finish(', result)
        self.assertNotIn('struct nvmtl_inflight {', result)
        for changed in ('', source + source, source.replace('int nvmtl_vk_submit_begin_at(', 'int missing('),
                        source.replace('static void nvmtl_pre_drop(', 'static void missing(')):
            with self.assertRaises(RuntimeError):
                extract_submit(changed)


if __name__ == '__main__':
    unittest.main()
