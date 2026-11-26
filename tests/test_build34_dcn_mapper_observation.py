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
import build34_dcn_mapper_observation as observation


class DcnMapperObservationTests(unittest.TestCase):
    def setUp(self):
        self.device = {
            'IOObjectClass': 'IOPCIDevice',
            'vendor-id': observation.TARGET_VENDOR,
            'device-id': observation.TARGET_DEVICE,
            'IORegistryEntryChildren': [{'IOObjectClass': 'PhxBringup', 'phx-build': 34}],
        }

    def decode(self, device=None, roots=None):
        blob = plistlib.dumps([self.device if device is None else device] if roots is None else roots)
        return observation.decode_snapshot(blob, '26.7.2', '25G332')

    def test_absent_property_is_only_classified(self):
        result = self.decode()
        self.assertEqual(result['iommu_parent_property'], 'absent')
        self.assertEqual(result['runtime_mapper_probe_state'], 'not-published')
        self.assertIsNone(result['runtime_mapper_resolved'])
        self.assertFalse(result['device_dma_domain_proven'])

    def test_nonempty_value_is_not_emitted_or_treated_as_resolution(self):
        self.device['iommu-parent'] = 'PRIVATE_MAPPER_SERVICE_NAME'
        result = self.decode()
        encoded = json.dumps(result)
        self.assertEqual(result['iommu_parent_property'], 'present-nonempty-string')
        self.assertEqual(result['runtime_mapper_probe_state'], 'not-published')
        self.assertNotIn('PRIVATE_MAPPER_SERVICE_NAME', encoded)
        self.assertNotIn('iommu-parent', encoded)

    def test_empty_and_non_string_values_are_distinguished_without_emission(self):
        for value, expected in (('', 'present-empty-string'), (b'PRIVATE_SENTINEL', 'present-non-string'),
                                (['PRIVATE_SENTINEL'], 'present-non-string')):
            with self.subTest(value_type=type(value).__name__):
                device = copy.deepcopy(self.device)
                device['iommu-parent'] = value
                encoded = json.dumps(self.decode(device), default=str)
                self.assertIn(expected, encoded)
                self.assertNotIn('PRIVATE_SENTINEL', encoded)

    def test_requires_unique_target_and_exact_build34_child(self):
        for roots in ([], [self.device, copy.deepcopy(self.device)]):
            with self.subTest(root_count=len(roots)), self.assertRaises(ValueError):
                self.decode(roots=roots)
        for children in ([], [{'IOObjectClass': 'PhxBringup', 'phx-build': 41}],
                         [{'IOObjectClass': 'PhxBringup', 'phx-build': 34}] * 2):
            device = copy.deepcopy(self.device)
            device['IORegistryEntryChildren'] = children
            with self.subTest(children=children), self.assertRaises(ValueError):
                self.decode(device)

    def test_rejects_bad_identity_shape_and_os_metadata(self):
        for key, value in (('vendor-id', b'bad'), ('device-id', b'bad'), ('IOObjectClass', 'Other')):
            device = copy.deepcopy(self.device)
            device[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.decode(device)
        device = copy.deepcopy(self.device)
        device['IORegistryEntryChildren'] = 'not-a-list'
        with self.assertRaises(ValueError):
            self.decode(device)
        for version, build in (('26.bad', '25G332'), ('26.7.2', 'private'), ('26.7.2', '25G332\n')):
            with self.subTest(version=version, build=build), self.assertRaises(ValueError):
                observation.decode_snapshot(plistlib.dumps([self.device]), version, build)

    def test_rejects_oversized_and_malformed_registry_data(self):
        for blob in (b'x' * (observation.MAX_REGISTRY_BYTES + 1), b'not-a-plist', plistlib.dumps({'not': 'roots'})):
            with self.subTest(size=len(blob)), self.assertRaises(ValueError):
                observation.decode_snapshot(blob, '26.7.2', '25G332')

    def test_collector_uses_only_bounded_readonly_queries(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs['timeout'], 10)
            self.assertTrue(kwargs['capture_output'])
            self.assertEqual(kwargs['stdin'], observation.subprocess.DEVNULL)
            self.assertNotIn('iommu-parent', args)
            output = (plistlib.dumps([self.device]) if args == observation.PCI_QUERY else
                      b'26.7.2\n' if args[-1] == '-productVersion' else b'25G332\n')
            return observation.subprocess.CompletedProcess(args, 0, stdout=output)

        with patch.object(observation.platform, 'system', return_value='Darwin'), \
             patch.object(observation.subprocess, 'run', side_effect=run):
            result = observation.collect()
        self.assertEqual(calls, [['/usr/bin/sw_vers', '-productVersion'], ['/usr/bin/sw_vers', '-buildVersion'],
                                 observation.PCI_QUERY])
        self.assertEqual(result['iommu_parent_property'], 'absent')

    def test_mapper_probe_states_are_distinct_and_never_prove_domain(self):
        expected = (
            ({}, 'not-published', None, None, None),
            ({'requested': False, 'performed': False, 'resolved': False, 'active': False},
             'published-disabled', False, False, None),
            ({'requested': True, 'performed': False, 'resolved': False, 'active': False},
             'requested-not-performed', True, False, None),
            ({'requested': True, 'performed': True, 'resolved': False, 'active': False},
             'performed-unresolved', True, True, False),
            ({'requested': True, 'performed': True, 'resolved': True, 'active': False},
             'resolved-inactive-at-probe', True, True, True),
            ({'requested': True, 'performed': True, 'resolved': True, 'active': True},
             'active-at-probe', True, True, True),
        )
        for fields, state, requested, performed, resolved in expected:
            with self.subTest(state=state):
                device = copy.deepcopy(self.device)
                child = device['IORegistryEntryChildren'][0]
                for name, key in zip(observation.MAPPER_PROBE_PROPERTIES,
                                     ('requested', 'performed', 'resolved', 'active')):
                    if key in fields:
                        child[name] = fields[key]
                result = self.decode(device)
                self.assertEqual(result['runtime_mapper_probe_state'], state)
                self.assertEqual(result['runtime_mapper_probe_requested'], requested)
                self.assertEqual(result['runtime_mapper_probe_performed'], performed)
                self.assertEqual(result['runtime_mapper_resolved'], resolved)
                self.assertFalse(result['device_dma_domain_proven'])
                self.assertFalse(result.get('route_provider_proven', False))

    def test_mapper_probe_metadata_rejects_partial_bad_or_inconsistent_flags(self):
        invalid = (
            {'phx-dcn-mapper-probe-requested': True},
            {'phx-dcn-mapper-probe-requested': 1, 'phx-dcn-mapper-probe-performed': False,
             'phx-dcn-mapper-resolved': False, 'phx-dcn-mapper-active-at-probe': False},
            {'phx-dcn-mapper-probe-requested': False, 'phx-dcn-mapper-probe-performed': True,
             'phx-dcn-mapper-resolved': False, 'phx-dcn-mapper-active-at-probe': False},
            {'phx-dcn-mapper-probe-requested': True, 'phx-dcn-mapper-probe-performed': False,
             'phx-dcn-mapper-resolved': True, 'phx-dcn-mapper-active-at-probe': False},
            {'phx-dcn-mapper-probe-requested': True, 'phx-dcn-mapper-probe-performed': True,
             'phx-dcn-mapper-resolved': False, 'phx-dcn-mapper-active-at-probe': True},
        )
        for fields in invalid:
            device = copy.deepcopy(self.device)
            device['IORegistryEntryChildren'][0].update(fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.decode(device)

    def test_unrecognized_mapper_properties_are_not_emitted(self):
        device = copy.deepcopy(self.device)
        device['IORegistryEntryChildren'][0]['private-service-token'] = 'PRIVATE_SENTINEL'
        encoded = json.dumps(self.decode(device))
        self.assertNotIn('PRIVATE_SENTINEL', encoded)
        self.assertNotIn('private-service-token', encoded)

    def test_non_macos_collector_refuses(self):
        with patch.object(observation.platform, 'system', return_value='Linux'):
            with self.assertRaisesRegex(ValueError, 'requires macOS'):
                observation.collect()


if __name__ == '__main__':
    unittest.main()
