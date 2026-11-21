#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import plistlib
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build34_map_observation as observation


class MapObservationTests(unittest.TestCase):
    def setUp(self):
        self.node = {'phx-build': 34, 'phx-fb-aper-len': 256 << 20}

    def decode(self, node=None):
        return observation.decode_snapshot(plistlib.dumps([self.node if node is None else node]), '26.7.2', '25G332')

    def metadata(self, cache=0, flags=0):
        self.node.update({observation.VERSION: 1, observation.OPTION: flags | cache << 8,
                          observation.CACHE: cache})

    def test_missing_metadata_is_not_acceptance(self):
        result = self.decode()
        self.assertEqual(result['status'], 'mapping-metadata-unavailable')
        self.assertFalse(result['native_reader_admitted'])
        self.assertNotIn('map_options', result)

    def test_all_cache_nibbles_and_other_option_bits(self):
        for cache in range(16):
            for flags in (0, 1, 0xfffff0ff):
                with self.subTest(cache=cache, flags=flags):
                    self.metadata(cache, flags)
                    result = self.decode()
                    self.assertEqual(result['cache_option'], cache)
                    self.assertEqual(result['cache_option_known_to_pinned_SDK'], cache <= 9)
                    self.assertEqual(result['default_cache_option'], cache == 0)
                    self.assertFalse(result['native_reader_admitted'])
                    self.assertFalse(result['effective_cache_proven'])
                    self.assertFalse(result['mapping_coherency_proven'])
                    self.assertFalse(result['loaded_image_identity_checked'])

    def test_partial_schema_refuses(self):
        for mask in range(1, 7):
            self.node = {'phx-build': 34, 'phx-fb-aper-len': 4096}
            for i, name in enumerate((observation.OPTION, observation.CACHE, observation.VERSION)):
                if mask & (1 << i):
                    self.node[name] = 1 if name == observation.VERSION else 0
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                self.decode()

    def test_unknown_schema_refuses(self):
        self.metadata()
        for value in (0, 2, True, '1', -1, 1 << 32):
            self.node[observation.VERSION] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.decode()

    def test_inconsistent_cache_field_refuses(self):
        self.metadata(4)
        self.node[observation.CACHE] = 1
        with self.assertRaises(ValueError):
            self.decode()

    def test_strict_unsigned_types_and_nonempty_aperture(self):
        self.metadata()
        original = copy.deepcopy(self.node)
        for name, values in [('phx-build', [41, 42, True, '34', -1, 1 << 32]),
                             ('phx-fb-aper-len', [0, True, -1]),
                             (observation.OPTION, [True, '0', -1, 1 << 32]),
                             (observation.CACHE, [True, '0', -1, 1 << 32])]:
            for value in values:
                self.node = copy.deepcopy(original)
                self.node[name] = value
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    self.decode()

    def test_unsigned_64_overflow_in_actual_xml_refuses(self):
        # plistlib's writer itself refuses this value; exercise reader input.
        blob = plistlib.dumps([self.node]).replace(b'<integer>268435456</integer>',
                                                   b'<integer>18446744073709551616</integer>')
        with self.assertRaises(ValueError):
            observation.decode_snapshot(blob, '26.7.2', '25G332')

    def test_no_or_multiple_root_services_refuse(self):
        for roots in ([], [self.node, self.node], self.node, ['PhxBringup']):
            with self.subTest(roots=type(roots).__name__), self.assertRaises(ValueError):
                observation.decode_snapshot(plistlib.dumps(roots), '26.7.2', '25G332')

    def test_child_metadata_does_not_substitute_for_root(self):
        child = copy.deepcopy(self.node)
        child.update({observation.VERSION: 1, observation.OPTION: 0x400, observation.CACHE: 4})
        self.node['IORegistryEntryChildren'] = [child]
        self.assertEqual(self.decode()['status'], 'mapping-metadata-unavailable')

    def test_raw_private_fields_never_leave_decoder(self):
        self.metadata(4)
        self.node.update({'IORegistryEntryID': 123, 'serial-number': b'PRIVATE_SENTINEL',
                          'phx-fb-aper-phys': 0xabcdef, 'IORegistryEntryChildren': [{'secret': 'PRIVATE_SENTINEL'}]})
        result = json.dumps(self.decode())
        self.assertNotIn('PRIVATE_SENTINEL', result)
        for name in ('IORegistryEntryID', 'serial-number', 'phx-fb-aper-phys', 'IORegistryEntryChildren'):
            self.assertNotIn(name, result)

    def test_invalid_or_oversize_input_refuses(self):
        for blob in ('<plist/>', b'x' * (8 * 1024 * 1024 + 1), b'not a plist'):
            with self.assertRaises(Exception):
                observation.decode_snapshot(blob, '26.7.2', '25G332')

    def test_collector_uses_only_absolute_readonly_commands(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs['timeout'], 15)
            self.assertTrue(kwargs['capture_output'])
            self.assertEqual(kwargs['stdin'], observation.subprocess.DEVNULL)
            data = (plistlib.dumps([self.node]) if args[0] == '/usr/sbin/ioreg' else
                    b'26.7.2\n' if args[-1] == '-productVersion' else b'25G332\n')
            return observation.subprocess.CompletedProcess(args, 0, stdout=data)

        with patch.object(observation.platform, 'system', return_value='Darwin'), patch.object(observation.subprocess, 'run', side_effect=run):
            result = observation.collect()
        self.assertEqual(calls, [['/usr/bin/sw_vers', '-productVersion'], ['/usr/bin/sw_vers', '-buildVersion'],
                                 ['/usr/sbin/ioreg', '-r', '-c', 'PhxBringup', '-a']])
        self.assertEqual(result['GPU_submissions'], 0)

    def test_source_delta_is_only_observation(self):
        source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text()
        proposed = observation.stage_baseline(source)
        self.assertEqual(proposed.replace(observation.OBSERVATION, '', 1), source)
        self.assertEqual(proposed.count(observation.OBSERVATION), 1)
        for changed in (source + '\n', proposed, source.replace('PHX_KEXT_BUILD 34u', 'PHX_KEXT_BUILD 42u')):
            with self.assertRaises(ValueError):
                observation.stage_baseline(changed)


if __name__ == '__main__':
    unittest.main()
