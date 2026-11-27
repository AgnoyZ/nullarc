from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build34_uma_host_map import classify_host_map

PAGE = 4096
BASE = 1 << 32
RUNTIME = 1 << 63


def descriptor(kind=0, base=BASE, pages=2, attrs=0):
    return struct.pack('<IIQQQQ', kind, 0, base, 0, pages, attrs)


class UmaHostMapTests(unittest.TestCase):
    def test_reserved_coverage_spans_unsorted_adjacent_descriptors(self):
        blob = b''.join(entry + b'\xA5' * 8 for entry in (
            descriptor(base=BASE + PAGE), descriptor(kind=7, base=BASE + 3 * PAGE),
            descriptor(base=BASE - PAGE),
        ))
        self.assertEqual(classify_host_map(blob, 48, 1, BASE, 3 * PAGE), 'reserved-type-only')

    def test_xnu_usable_types_refuse_even_a_single_page_overlap(self):
        for kind in (1, 2, 3, 4, 7):
            with self.subTest(kind=kind):
                blob = descriptor(pages=1) + descriptor(kind=kind, base=BASE + PAGE)
                self.assertEqual(classify_host_map(blob, 40, 1, BASE, 2 * PAGE), 'host-usable-type-overlap')

    def test_runtime_and_other_firmware_types_are_not_reserved_only(self):
        for kind, attrs in ((0, RUNTIME), (7, RUNTIME), (5, 0), (6, 0), (8, 0), (9, 0), (10, 0), (11, 0),
                            (15, 0), (0x80000000, 0)):
            with self.subTest(kind=kind, attrs=attrs):
                self.assertEqual(classify_host_map(descriptor(kind, attrs=attrs), 40, 1, BASE, 2 * PAGE),
                                 'other-descriptor-overlap')

    def test_hole_or_absence_is_not_a_reservation(self):
        blob = descriptor(pages=1) + descriptor(base=BASE + 2 * PAGE)
        self.assertEqual(classify_host_map(blob, 40, 1, BASE, 3 * PAGE), 'coverage-incomplete')
        self.assertEqual(classify_host_map(blob, 40, 1, BASE + 4 * PAGE, PAGE), 'coverage-incomplete')

    def test_other_overlap_does_not_hide_usable_type(self):
        blob = descriptor(kind=10, pages=1) + descriptor(kind=7, base=BASE + PAGE)
        self.assertEqual(classify_host_map(blob, 40, 1, BASE, 3 * PAGE), 'host-usable-type-overlap')

    def test_refuses_invalid_shape(self):
        good = descriptor()
        for blob, stride, version in ((b'', 40, 1), (good[:-1], 40, 1), (good + b'\0', 41, 1),
                                      (good, 32, 1), (good, 0, 1), (good, 40, 2), (good, 40, True),
                                      (bytes(1 << 21), 40, 1), (bytearray(good), 40, 1)):
            with self.subTest(size=len(blob), stride=stride, version=version), self.assertRaises(ValueError):
                classify_host_map(blob, stride, version, BASE, PAGE)

    def test_refuses_invalid_window(self):
        for base, length in ((0, PAGE), (True, PAGE), (BASE + 1, PAGE), (BASE, 0), (BASE, PAGE + 1),
                             (BASE, (64 << 20) + PAGE), ((1 << 48) - PAGE, 2 * PAGE)):
            with self.subTest(base=base, length=length), self.assertRaises(ValueError):
                classify_host_map(descriptor(), 40, 1, base, length)

    def test_invalid_descriptors_anywhere_refuse_even_with_full_reserved_coverage(self):
        for bad in (descriptor(base=BASE + PAGE), descriptor(pages=0), descriptor(base=BASE - 1),
                    descriptor(base=(1 << 64) - PAGE), descriptor(base=0, pages=1 << 53)):
            with self.assertRaises(ValueError):
                classify_host_map(descriptor() + bad, 40, 1, BASE, 2 * PAGE)

    def test_exact_address_limits_do_not_wrap(self):
        base = (1 << 48) - PAGE
        blob = descriptor(base=base, pages=1) + descriptor(base=(1 << 64) - PAGE, pages=1)
        self.assertEqual(classify_host_map(blob, 40, 1, base, PAGE), 'reserved-type-only')


if __name__ == '__main__':
    unittest.main()
