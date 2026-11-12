from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_translation_flight import extract_entry, exercise


class TranslationFlightSourceTests(unittest.TestCase):
    def test_actual_entry_extraction_fails_closed(self):
        source = (ROOT / 'src/nmplugin/NVMTLLibraryLoad.m').read_text(encoding='utf-8')
        entry = extract_entry(source)
        for token in ('xlate(', 'nvmtl_cache_save(', '@finally', 'xlate_free(', 'nvmtl_translation_share('):
            self.assertIn(token, entry)
        for text in ('', source + source, source.replace('nvmtl_translation_share(', 'missing_share('),
                     source.replace('nvmtl_translation_key(air, ll, stage, gXlateTag)', 'missing_key()')):
            with self.assertRaises(RuntimeError):
                extract_entry(text)

    def test_other_hosts_do_not_claim_foundation_execution(self):
        for system in ('Windows', 'Linux'):
            with tempfile.TemporaryDirectory() as temp, mock.patch('test_translation_flight.platform.system', return_value=system):
                out = Path(temp) / 'fresh'
                with self.assertRaises(RuntimeError):
                    exercise(out)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
