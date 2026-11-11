from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_bo_create import extract_source, exercise


class BoCreateTests(unittest.TestCase):
    def test_extraction_is_actual_current_source_and_fails_closed(self):
        source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text(encoding='utf-8')
        extracted = extract_source(source)
        for token in ('doBoCreate', 'doBoImportHost', 'boPageSize', 'boBudgetFits', 'PhxClientBo'):
            self.assertIn(token, extracted)
        for marker in ('struct PhxClientBo', 'static bool shape(', '::doBoCreate(', '::doBoImportHost(', 'kGttCap ='):
            with self.assertRaises(RuntimeError):
                extract_source(source.replace(marker, 'missing'))
        with self.assertRaises(RuntimeError):
            extract_source(source * 2)

    def test_unknown_profile_and_software_budgets_are_explicit(self):
        source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text(encoding='utf-8')
        query = source.split('IOReturn IOAccelPhxNativeClient::doQueryInfo(')[1].split('static constexpr uint64_t kGoldenTscUpper')[0]
        self.assertIn('PHXN_INFO_ASSUMED_PROFILE', query)
        self.assertIn('PHXN_INFO_SOFTWARE_BUDGETS', query)
        self.assertIn('phoenix-canned-unverified', source)
        self.assertIn('system-backed-software-budgets', source)

    def test_windows_cannot_report_native_pass(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch('test_bo_create.platform.system', return_value='Windows'):
            out = Path(temp) / 'fresh'
            with self.assertRaises(RuntimeError):
                exercise(out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
