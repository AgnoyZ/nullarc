#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import plistlib
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build34_dcn_mapper_observation as mapper
import build34_dcn_route_observation as observation


class DcnRouteObservationTests(unittest.TestCase):
    def setUp(self):
        self.device = {
            'IOObjectClass': 'IOPCIDevice',
            'vendor-id': mapper.TARGET_VENDOR,
            'device-id': mapper.TARGET_DEVICE,
            'IORegistryEntryChildren': [
                {'IOObjectClass': 'PhxBringup', 'phx-build': 34},
                {'IOObjectClass': 'PhxAMDFB'},
                {'IOObjectClass': 'AMDSupport'},
                {'IOObjectClass': 'NMXAccel'},
                {'IOObjectClass': 'PhxDeviceControl'},
                {'IOObjectClass': 'PrivateService', 'serial-number': 'PRIVATE_SENTINEL'},
            ],
        }

    def decode(self, device=None, roots=None):
        blob = plistlib.dumps([self.device if device is None else device] if roots is None else roots)
        return observation.decode_snapshot(blob, '26.7.2', '25G332')

    def test_counts_only_allowlisted_direct_children_and_does_not_claim_route(self):
        result = self.decode()
        self.assertEqual(result['known_direct_child_class_counts'], {
            'AMDSupport': 1, 'NMXAccel': 1, 'PhxAMDFB': 1, 'PhxBringup': 1, 'PhxDeviceControl': 1,
        })
        self.assertFalse(result['active_hubp_route_observed'])
        self.assertFalse(result['route_provider_proven'])
        self.assertFalse(result['device_dma_domain_proven'])
        encoded = json.dumps(result)
        self.assertNotIn('PRIVATE_SENTINEL', encoded)
        self.assertNotIn('PrivateService', encoded)
        self.assertNotIn('serial-number', encoded)

    def test_requires_unique_target_and_exact_build34_child(self):
        for roots in ([], [self.device, dict(self.device)]):
            with self.subTest(root_count=len(roots)), self.assertRaises(ValueError):
                self.decode(roots=roots)
        for children in ([], [{'IOObjectClass': 'PhxBringup', 'phx-build': 41}],
                         [{'IOObjectClass': 'PhxBringup', 'phx-build': 34}] * 2):
            device = dict(self.device, **{'IORegistryEntryChildren': children})
            with self.subTest(children=children), self.assertRaises(ValueError):
                self.decode(device)

    def test_rejects_malformed_or_oversized_snapshots(self):
        for blob in (b'x' * (observation.MAX_REGISTRY_BYTES + 1), b'not-a-plist', plistlib.dumps({'not': 'roots'})):
            with self.subTest(size=len(blob)), self.assertRaises(ValueError):
                observation.decode_snapshot(blob, '26.7.2', '25G332')
        device = dict(self.device, **{'IORegistryEntryChildren': 'not-a-list'})
        with self.assertRaises(ValueError):
            self.decode(device)

    def test_collector_uses_bounded_readonly_queries(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs['timeout'], 10)
            self.assertTrue(kwargs['capture_output'])
            self.assertEqual(kwargs['stdin'], observation.subprocess.DEVNULL)
            output = (plistlib.dumps([self.device]) if args == mapper.PCI_QUERY else
                      b'26.7.2\n' if args[-1] == '-productVersion' else b'25G332\n')
            return observation.subprocess.CompletedProcess(args, 0, stdout=output)

        with patch.object(observation.platform, 'system', return_value='Darwin'), \
             patch.object(observation.subprocess, 'run', side_effect=run):
            result = observation.collect()
        self.assertEqual(result['route_provider_proven'], False)
        self.assertEqual(calls, [['/usr/bin/sw_vers', '-productVersion'], ['/usr/bin/sw_vers', '-buildVersion'],
                                 mapper.PCI_QUERY])

    def test_non_macos_collector_refuses(self):
        with patch.object(observation.platform, 'system', return_value='Linux'):
            with self.assertRaisesRegex(ValueError, 'requires macOS'):
                observation.collect()


if __name__ == '__main__':
    unittest.main()
