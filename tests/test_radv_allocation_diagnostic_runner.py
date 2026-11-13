from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_radv_allocation_diagnostic import exercise, patched_transport


class RadvAllocationDiagnosticTests(unittest.TestCase):
    def test_actual_transport_status_privacy_limit_and_concurrency(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = exercise(Path(temporary) / "result")
        self.assertEqual(54, result["cases"])
        self.assertEqual(1200, result["concurrent_calls"])
        self.assertFalse(result["hardware_executed"])

    def test_changed_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "changed.c"
            source.write_text("/* different transport */")
            with self.assertRaisesRegex(RuntimeError, "reviewed pinned"):
                patched_transport(source)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "output exists"):
                exercise(Path(temporary))


if __name__ == "__main__":
    unittest.main()
