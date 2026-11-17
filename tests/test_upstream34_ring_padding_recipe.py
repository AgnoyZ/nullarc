"""Pinned two-site CPU-only source transformation; no kernel/GPU operations."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from upstream34_layout import ring_padding as p


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text()
        self.function = p.extract(self.source)

    def test_exact_original_function(self):
        self.assertEqual(hashlib.sha256(self.function.encode()).hexdigest(), p.FUNCTION_SHA)

    def test_only_two_insertions_are_reversible(self):
        candidate = p.transform(self.function)
        self.assertNotEqual(candidate, self.function)
        self.assertEqual(candidate.replace(p.NEW_RESERVATION,p.OLD_RESERVATION).replace(p.NEW_COMMIT,p.OLD_COMMIT),self.function)
        self.assertEqual(candidate.count(p.NEW_RESERVATION),1)
        self.assertEqual(candidate.count(p.NEW_COMMIT),1)
        self.assertEqual((ROOT / 'src/phxbringup/PhxBringup.cpp').read_text(),self.source)

    def test_source_and_function_drift_rejected(self):
        for before,after in (('n * 4 + 8','n * 4 + 9'),('q.wptr += k','q.wptr += k + 1'),('return kIOReturnSuccess','return kIOReturnBusy')):
            with self.assertRaises(ValueError):p.transform(self.function.replace(before,after))
            with self.assertRaises(ValueError):p.extract(self.source.replace(before,after))

    def test_reapplication_and_ambiguous_extraction_rejected(self):
        with self.assertRaises(ValueError):p.transform(p.transform(self.function))
        with self.assertRaises(ValueError):p.extract(self.source+self.function)
        with self.assertRaises(ValueError):p.extract('')


if __name__ == '__main__':
    unittest.main()
