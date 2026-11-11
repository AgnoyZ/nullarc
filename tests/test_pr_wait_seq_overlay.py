from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from pr_wait_seq_overlay import deterministic_wait, transform


class WaitOverlayTests(unittest.TestCase):
    def test_unreviewed_inputs_refused(self):
        for data in (b'', b'not reviewed', b'\x00', b'\xff'):
            with self.assertRaises((RuntimeError, UnicodeDecodeError)):
                transform(data)
        with self.assertRaisesRegex(RuntimeError, 'disposable'):
            with deterministic_wait(ROOT):
                self.fail('main checkout must not be written')

    def test_reviewed_overlay_and_exception_restoration(self):
        original = subprocess.run(['git', 'show', '8aba872560a3c9b7dc7a0ddebfad001c6dddf315:tests/test_wait_seq.cpp'],
                                  cwd=ROOT, capture_output=True).stdout
        if not original:
            self.skipTest('Pinned upstream object absent in shallow checkout; matrix validates actual overlay')
        changed = transform(original)
        # The modeled wait algorithm is byte-for-byte unchanged. Only its test clock/schedule changes.
        def engine(data):
            return data.split(b'struct WaitSeqEngine {', 1)[1].split(b'static void test_immediate_retirement()', 1)[0]
        self.assertEqual(engine(original), engine(changed))
        self.assertNotIn(b'std::thread t(', changed)
        self.assertIn(b'assert(g_sleep_calls > 0)', changed)
        self.assertIn(b'g_virtual_ns == PHXN_WAIT_CAP_NS', changed)
        self.assertEqual(transform(original.replace(b'\n', b'\r\n')), changed)
        for modified in (original + b' ', original.replace(b'wait_seq(', b'other(')):
            with self.assertRaises(RuntimeError):
                transform(modified)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'tests').mkdir(); path = root / 'tests/test_wait_seq.cpp'
            path.write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'forced'):
                with deterministic_wait(root) as info:
                    self.assertFalse(info['production_sources_modified'])
                    self.assertEqual(path.read_bytes(), changed)
                    raise ValueError('forced')
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaisesRegex(RuntimeError, 'externally'):
                with deterministic_wait(root):
                    path.write_bytes(b'other edit')
            self.assertEqual(path.read_bytes(), b'other edit')


if __name__ == '__main__':
    unittest.main()
