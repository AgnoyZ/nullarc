import platform
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_present_copy import check_transaction_width, exercise, extract_source


class PresentCopyTests(unittest.TestCase):
    def test_extract_current_copy_bodies(self):
        source = (ROOT / 'src/phxaccel/accel/nvrm-accel.cpp').read_text(encoding='utf-8')
        extracted = extract_source(source)
        for name in ('nvIopCopyFull', 'nvIopCopyDamage', 'movntdqa', 'movntdq', 'movnti', 'sfence'):
            self.assertIn(name, extracted)
        check_transaction_width(source)

    def test_reject_missing_or_duplicate_body(self):
        source = (ROOT / 'src/phxaccel/accel/nvrm-accel.cpp').read_text(encoding='utf-8')
        for text in ('', source + '\n' + source):
            with self.assertRaises(RuntimeError):
                extract_source(text)

    @unittest.skipUnless(platform.system() in ('Linux', 'Darwin') and
                         platform.machine().lower() in ('x86_64', 'amd64') and shutil.which('clang++'),
                         'actual streaming copies need POSIX x86-64 Clang')
    def test_actual_copy_with_sanitizers(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = exercise(Path(temporary) / 'copy')
            self.assertFalse(report['hardware_executed'])
            self.assertEqual(report['packed_2560x1600_sse_calls'], 1)


if __name__ == '__main__':
    unittest.main()
