from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_async_cache import exercise
from test_translation_flight import extract_entry


class AsyncCacheRunnerTests(unittest.TestCase):
    def test_disk_hits_precede_pending_and_sharing(self):
        entry = extract_entry((ROOT / 'src/nmplugin/NVMTLLibraryLoad.m').read_text(encoding='utf-8'))
        self.assertLess(entry.index('if (hit)'), entry.index('nvmtl_translation_key('))
        self.assertLess(entry.index('nvmtl_async_cache_lookup('), entry.index('xlate('))
        self.assertIn('NVMTL_SPVCACHE_ASYNC_OFF', entry)

    def test_wrong_hosts_refuse_native_claim(self):
        for system in ('Windows', 'Linux'):
            with tempfile.TemporaryDirectory() as temp, mock.patch('test_async_cache.platform.system', return_value=system):
                out = Path(temp) / 'fresh'
                with self.assertRaises(RuntimeError):
                    exercise(out)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
