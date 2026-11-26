#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build34_dcn_firmware_home_stage as firmware
import build34_dcn_firmware_observation_stage as observation


class DcnFirmwareObservationStageTests(unittest.TestCase):
    def test_stage_is_hash_pinned_and_adds_one_read_only_sample(self):
        original = (ROOT / firmware.FRAMEBUFFER).read_bytes()
        with self.assertRaisesRegex(ValueError, 'source drift'):
            observation.stage(original + b'\n')
        staged = observation.stage(original)
        self.assertEqual(staged.count('sampleDcnFirmware(expectedPci, sample)'), 1)
        self.assertEqual(staged.count('fDcnFirmwareObservationAttempted = true;'), 1)
        self.assertEqual(staged.count('if (on) observeDcnFirmwareOnce();'), 1)
        self.assertEqual(staged.count('observeDcnFirmwareOnce();'), 2)
        for key in (observation.SCHEMA, observation.ATTEMPTED, observation.VALID,
                    observation.ROUTE_PROVEN, observation.DOMAIN_PROVEN):
            self.assertEqual(staged.count(f'setProperty("{key}"'), 1)
        self.assertIn('setProperty("phx-dcn-route-provider-proven", false);', staged)
        self.assertIn('setProperty("phx-dcn-device-dma-domain-proven", false);', staged)
        self.assertNotIn('setProperty("phx-dcn-scanout-address"', staged)
        self.assertNotIn('PFBLOG("dcn-firmware', staged)

    def test_observation_occurs_after_power_lock_release_and_ready_publication(self):
        staged = observation.stage((ROOT / firmware.FRAMEBUFFER).read_bytes())
        note = staged[staged.index('    void noteDcnFirmwarePower('):]
        note = note[:note.index('\n    }\n') + len('\n    }\n')]
        self.assertLess(note.index('IOLockUnlock(fDcnFirmwareLock);'), note.index('observeDcnFirmwareOnce();'))
        ready = staged.rindex('fDcnFirmwareReady = true;')
        self.assertLess(ready, staged.index('    observeDcnFirmwareOnce();', ready))
        observer = staged[staged.index('    void observeDcnFirmwareOnce()'):]
        observer = observer[:observer.index('\n    }\n') + len('\n    }\n')]
        self.assertLess(observer.index('fDcnFirmwareObservationAttempted = true;'),
                        observer.index('sampleDcnFirmware(expectedPci, sample)'))
        self.assertLess(observer.index('sampleDcnFirmware(expectedPci, sample)'),
                        observer.index('setProperty("phx-dcn-firmware-sample-valid"'))


if __name__ == '__main__':
    unittest.main()
