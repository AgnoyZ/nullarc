"""Outer-ring build admission checks; never compile or install a kernel."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.upstream34_layout import outer_memsync_candidate as m


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cpu = Path(self.tmp.name) / 'CPU.json'
        self.record = {
            'result': 'passed', 'sanitizers': 'ASan/UBSan', 'GPU_executed': False,
            'kernel_built': False, 'production_source_modified': False,
            'real_IOKit_linked': False, 'equal_footprint_NOP_control': True, 'prefix_dwords': 8,
            'complete_source_sha256': dict(m.SOURCE_SHA),
            'policies': {p: {'passed': True, 'GPU_executed': False, 'scenarios': 36111}
                         for p in m.outer_memsync.POLICIES},
            'recipe_sha256': {p: m.file_sha(m.ROOT / p) for p in (
                'tools/upstream34_layout/outer_memsync.py', 'tests/test_build34_outer_memsync.cpp',
                'tests/test_upstream34_outer_memsync.py', 'tools/upstream34_layout/ring_padding.py',
                'tools/upstream34_layout/mec_range.py')}}

    def put(self, row=None):
        self.cpu.write_text(json.dumps(self.record if row is None else row))

    def test_pinned_complete_source_for_both_policies(self):
        source = m.mec_range.read_base(m.DRIVER)
        for policy, digest in m.SOURCE_SHA.items():
            result = m.reviewed_source(source, policy)
            self.assertEqual(m.sha(result), digest)
            self.assertNotEqual(result, source)
            with self.assertRaises(ValueError):
                m.reviewed_source(result, policy)
        with self.assertRaises(ValueError):
            m.reviewed_source(source, 'original')

    def test_valid_CPU_record_is_only_offline_build_admission(self):
        self.put()
        for policy in m.SOURCE_SHA:
            self.assertFalse(m.verify_CPU_record(self.cpu, policy)['GPU_executed'])

    def test_incomplete_or_changed_policy_record_refused(self):
        for policy in m.outer_memsync.POLICIES:
            for key, value in [('passed', False), ('GPU_executed', True), ('scenarios', 1)]:
                row = copy.deepcopy(self.record)
                row['policies'][policy][key] = value
                self.put(row)
                with self.assertRaises(ValueError):
                    m.verify_CPU_record(self.cpu, 'acquire-prefix')

    def test_sanitizer_source_or_recipe_drift_refused(self):
        rows = []
        for key, value in [('sanitizers', 'none'), ('prefix_dwords', 4),
                           ('GPU_executed', True), ('equal_footprint_NOP_control', False)]:
            row = copy.deepcopy(self.record); row[key] = value; rows.append(row)
        row = copy.deepcopy(self.record)
        row['complete_source_sha256']['acquire-prefix'] = '0' * 64; rows.append(row)
        row = copy.deepcopy(self.record)
        row['recipe_sha256']['tests/test_build34_outer_memsync.cpp'] = '0' * 64; rows.append(row)
        for row in rows:
            self.put(row)
            with self.assertRaises(ValueError):
                m.verify_CPU_record(self.cpu, 'acquire-prefix')

    def test_native_platform_required_before_writing_output(self):
        self.put()
        with patch.object(m.platform, 'system', return_value='Linux'):
            with self.assertRaises(RuntimeError):
                m.build(Path(self.tmp.name) / 'no-output', Path(self.tmp.name), 'nop-prefix', self.cpu)
        self.assertFalse((Path(self.tmp.name) / 'no-output').exists())

    def test_existing_or_outside_build_destination_refused(self):
        self.put()
        for destination in (m.ROOT / 'build', Path(self.tmp.name) / 'no-output'):
            with self.assertRaises(ValueError):
                m.build(destination, Path(self.tmp.name), 'nop-prefix', self.cpu)
        self.assertFalse((Path(self.tmp.name) / 'no-output').exists())

    def test_unknown_policy_refused_before_output(self):
        self.put()
        with self.assertRaises(ValueError):
            m.build(m.ROOT / 'build/no-outer-output', Path(self.tmp.name), 'original', self.cpu)
        self.assertFalse((m.ROOT / 'build/no-outer-output').exists())


if __name__ == '__main__':
    unittest.main()
