#!/usr/bin/env python3
import json
from pathlib import Path
import plistlib
import sys
import unittest
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build34_uma_observation as observation

MIB = 1 << 20
BACKING_BASE = 0x120000000
UMA_BYTES = 4096 * MIB
DISCOVERY_DATA = bytes.fromhex('07142128') + b'FIRMWARE_SENTINEL'
DISCOVERY_DATA += bytes(-len(DISCOVERY_DATA) % 4)
HUBP = {
    'phx-dcn-firmware-sample-v1': 1,
    'phx-dcn-firmware-sample-attempted': True,
    'phx-dcn-firmware-sample-valid': True,
    'phx-dcn-route-provider-proven': False,
    'phx-dcn-device-dma-domain-proven': False,
}


class UmaObservationTests(unittest.TestCase):
    def setUp(self):
        self.bringup = {
            'IOObjectClass': 'PhxBringup', 'phx-build': 34, 'phx-fb-mc-base': 0x8000000000,
            'phx-fb-phys': BACKING_BASE, 'phx-fb-size': UMA_BYTES, 'phx-fb-aper-len': 256 * MIB,
        }
        self.fb = {'IOObjectClass': 'PhxAMDFB'}
        self.probe = {'IOObjectClass': 'PhxProbe'}
        self.children = [self.bringup, self.fb]
        self.target = {
            'IOObjectClass': 'IOPCIDevice', 'vendor-id': bytes.fromhex('02100000'),
            'device-id': bytes.fromhex('00190000'), 'IORegistryEntryChildren': self.children,
            'serial-number': 'REGISTRY_SENTINEL',
        }

    def decode(self, roots=None):
        return observation.decode_snapshot(plistlib.dumps([self.target] if roots is None else roots),
                                           '26.7.2', '25G332')

    def discovery(self):
        return {'phx-discovery-offset': UMA_BYTES - (64 << 10),
                'phx-discovery-signature': 0x28211407, 'phx-discovery-bin': DISCOVERY_DATA}

    def test_geometry_without_samples_is_not_admission(self):
        self.assertEqual(self.decode(), {
            'status': 'geometry-observed-ownership-unproven', 'OS_version': '26.7.2', 'OS_build': '25G332',
            'target': '1002:1900', 'PhxBringup_build': 34, 'firmware_uma_mib': 4096, 'bar0_mib': 256,
            'discovery_sample_state': 'service-absent', 'firmware_hubp_sample_state': 'not-published',
            'complete_reservation_map_proven': False, 'exclusive_ownership_proven': False,
            'pool_admission_permitted': False, 'raw_registry_saved': False,
        })

    def test_samples_cannot_prove_ownership_or_leak_values(self):
        self.children.append(self.probe)
        self.probe.update(self.discovery())
        self.fb.update(HUBP, **{'scanout-address': 'SCANOUT_SENTINEL'})
        result = self.decode()
        self.assertEqual(result['discovery_sample_state'], 'sample-present')
        self.assertEqual(result['firmware_hubp_sample_state'], 'sample-valid')
        for key in ('pool_admission_permitted', 'complete_reservation_map_proven', 'exclusive_ownership_proven'):
            self.assertIs(result[key], False)
        encoded = json.dumps(result)
        for value in ('SENTINEL', str(BACKING_BASE), str(UMA_BYTES - (64 << 10)), 'address', 'offset', 'range'):
            self.assertNotIn(value, encoded)

    def test_samples_must_be_direct_children_of_target(self):
        self.probe.update(self.discovery())
        other = dict(self.target, **{'device-id': bytes.fromhex('01190000'),
                                     'IORegistryEntryChildren': [self.probe, dict(self.fb, **HUBP)]})
        self.fb['IORegistryEntryChildren'] = [self.probe]
        result = self.decode([other, self.target])
        self.assertEqual(result['discovery_sample_state'], 'service-absent')
        self.assertEqual(result['firmware_hubp_sample_state'], 'not-published')

    def test_missing_partial_and_invalid_samples_are_distinguished(self):
        self.children.append(self.probe)
        self.assertEqual(self.decode()['discovery_sample_state'], 'not-published')
        self.probe['phx-discovery-offset'] = 0
        self.fb['phx-dcn-firmware-sample-v1'] = 1
        result = self.decode()
        self.assertEqual(result['discovery_sample_state'], 'incomplete')
        self.assertEqual(result['firmware_hubp_sample_state'], 'incomplete')
        self.fb.update(HUBP, **{'phx-dcn-route-provider-proven': True})
        self.assertEqual(self.decode()['firmware_hubp_sample_state'], 'sample-invalid')
        for key, value in (
            ('phx-discovery-offset', True), ('phx-discovery-offset', 1),
            ('phx-discovery-offset', UMA_BYTES - 4), ('phx-discovery-signature', 0),
            ('phx-discovery-bin', b''), ('phx-discovery-bin', b'not a discovery sample'),
            ('phx-discovery-bin', DISCOVERY_DATA + bytes(65536)),
        ):
            with self.subTest(key=key, value_type=type(value)):
                self.probe.update(self.discovery())
                self.probe[key] = value
                self.assertEqual(self.decode()['discovery_sample_state'], 'sample-invalid')

    def test_requires_unique_target_and_unique_known_children(self):
        for roots in ([], [self.target, self.target]):
            with self.subTest(device_count=len(roots)), self.assertRaises(ValueError):
                self.decode(roots)
        for children in ([], [self.bringup, self.bringup], [self.bringup, self.fb, self.fb],
                         [self.bringup, self.probe, self.probe], ['malformed']):
            self.target['IORegistryEntryChildren'] = children
            with self.subTest(child_count=len(children)), self.assertRaises(ValueError):
                self.decode()
        other_build = dict(self.bringup, **{'phx-build': 41})
        for children in ([other_build], [self.bringup, other_build]):
            self.target['IORegistryEntryChildren'] = children
            with self.subTest(child_count=len(children)), self.assertRaises(ValueError):
                self.decode()

    def test_rejects_missing_wrong_and_overflowing_geometry(self):
        for key, values in {
            'phx-fb-mc-base': (0, 0x8000000000 + (16 * MIB)),
            'phx-fb-phys': (0, 1, -16 * MIB, 1 << 48, (1 << 48) - UMA_BYTES + 16 * MIB),
            'phx-fb-size': (True, 0, 240 * MIB, UMA_BYTES - 1, (1 << 48) - 0x8000000000 + 16 * MIB),
            'phx-fb-aper-len': ('268435456', 128 * MIB, 512 * MIB),
        }.items():
            original = self.bringup.pop(key)
            with self.assertRaises(ValueError):
                self.decode()
            for value in values:
                self.bringup[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.decode()
            self.bringup[key] = original
        self.bringup['phx-fb-phys'] = (1 << 48) - UMA_BYTES
        self.assertEqual(self.decode()['firmware_uma_mib'], 4096)

    def test_rejects_bad_snapshot_and_os_metadata(self):
        for blob in (b'not-plist', b'x' * (observation.mapper.MAX_REGISTRY_BYTES + 1), plistlib.dumps({})):
            with self.assertRaises(ValueError):
                observation.decode_snapshot(blob, '26.7.2', '25G332')
        blob = plistlib.dumps([self.target])
        for version, build in (('PRIVATE', '25G332'), ('26.7.2', 'PRIVATE')):
            with self.assertRaises(ValueError):
                observation.decode_snapshot(blob, version, build)

    def test_collector_uses_only_timed_readonly_queries(self):
        outputs = [plistlib.dumps([self.target]), b'26.7.2\n', b'25G332\n']
        with patch.object(observation.platform, 'system', return_value='Darwin'), \
             patch.object(observation.subprocess, 'run') as run:
            run.side_effect = [observation.subprocess.CompletedProcess([], 0, stdout=data) for data in outputs]
            self.assertEqual(observation.collect(), self.decode())
        env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}
        self.assertEqual(run.call_args_list, [
            call(args, env=env, stdin=observation.subprocess.DEVNULL, capture_output=True, check=True, timeout=10)
            for args in (['/usr/sbin/ioreg', '-a', '-l', '-r', '-d', '2', '-c', 'IOPCIDevice'],
                         ['/usr/bin/sw_vers', '-productVersion'], ['/usr/bin/sw_vers', '-buildVersion'])
        ])

    def test_cli_refusal_never_prints_failure_payload(self):
        error = observation.subprocess.CalledProcessError(1, ['ioreg'], stderr=b'RAW_SENTINEL')
        with patch.object(observation, 'collect', side_effect=error), patch('builtins.print') as output:
            self.assertEqual(observation.main(), 1)
            output.assert_called_once()
            self.assertEqual(json.loads(output.call_args.args[0]), {
                'status': 'passive-uma-observation-refused', 'pool_admission_permitted': False,
            })


if __name__ == '__main__':
    unittest.main()
