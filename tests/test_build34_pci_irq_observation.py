#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import plistlib
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build34_pci_irq_observation as obs


class PCIDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.phx = {obs.CLASS: 'PhxBringup', obs.REGISTRY_ID: 75241, 'phx-build': 34}
        self.pci = {obs.CLASS: 'IOPCIDevice', obs.REGISTRY_ID: 75240, 'vendor-id': b'\x02\x10\x00\x00',
                    'device-id': b'\x00\x19\x00\x00', obs.CHILDREN: [self.phx.copy()],
                    obs.CONTROLLERS: ['other-private-name', obs.MESSAGED],
                    obs.SPECIFIERS: [b'private-specifier-a', b'private-specifier-b']}

    def summarize(self, after=None, before=None):
        return obs.summarize(plistlib.dumps([self.pci] if before is None else before), plistlib.dumps([self.phx]),
                             plistlib.dumps([self.pci if after is None else after]), '26.7.2', '25G332')

    def test_counters_only(self):
        report = self.summarize()
        self.assertEqual((report['descriptor_count'], report['messaged_controller_count'],
                          report['other_controller_count']), (2, 1, 1))
        self.assertEqual((report['msi_registry_marker'], report['irq_accounting_legend_count']), ('absent', 0))
        self.assertEqual(report['start_time_config_classification'], 'unavailable')
        self.assertFalse(any(report[k] for k in ('active_interrupt_mode_proved', 'active_isr_proved', 'eop_delivery_proved',
                                               'ih_consumer_ownership_proved', 'fence_visibility_proved')))
        rendered = json.dumps(report)
        for private in ('75240', '75241', 'private', obs.MESSAGED):
            self.assertNotIn(private, rendered)

    def test_absent_is_not_inactive(self):
        del self.pci[obs.CONTROLLERS], self.pci[obs.SPECIFIERS]
        report = self.summarize()
        self.assertEqual(report['status'], 'no-cached-descriptors-visible')
        self.assertFalse(report['active_interrupt_mode_proved'])

    def test_malformed_or_asymmetric_pair(self):
        for specifiers in (None, [], [b'', b'nonempty'], [45, b'nonempty'], b'blob'):
            with self.subTest(specifiers=specifiers), self.assertRaises(ValueError):
                if specifiers is None:
                    del self.pci[obs.SPECIFIERS]
                else:
                    self.pci[obs.SPECIFIERS] = specifiers
                self.summarize()

    def test_same_counts_with_changed_payload_are_refused(self):
        with self.assertRaises(ValueError):
            self.summarize(after={**self.pci, obs.SPECIFIERS: [b'different', b'value']})

    def test_marker_and_legend_are_hints_only(self):
        self.pci[obs.REPORT_LEGEND] = [{obs.REPORT_GROUP: obs.IRQ_ACCOUNTING, 'private-channel': 99189},
                                      {obs.REPORT_GROUP: 'private-other-group'}]
        for marker in (True, False):
            with self.subTest(marker=marker):
                self.pci[obs.MSI_MARKER] = marker
                report = self.summarize()
                self.assertEqual(report['msi_registry_marker'], str(marker).lower())
                self.assertEqual(report['irq_accounting_legend_count'], 1)
                self.assertFalse(report['active_interrupt_mode_proved'])
                self.assertFalse(report['active_isr_proved'])
                self.assertFalse(report['ih_consumer_ownership_proved'])
                rendered = json.dumps(report)
                for private in ('99189', 'private-channel', 'private-other-group'):
                    self.assertNotIn(private, rendered)

    def test_changing_or_malformed_hints_are_refused(self):
        for extra in ({obs.MSI_MARKER: True}, {obs.MSI_MARKER: 1},
                      {obs.REPORT_LEGEND: [{obs.REPORT_GROUP: obs.IRQ_ACCOUNTING}]},
                      {obs.REPORT_LEGEND: ['bad-entry']}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.summarize(after={**self.pci, **extra})

    def test_start_configuration_never_proves_live_interrupts(self):
        child = self.pci[obs.CHILDREN][0]
        for mode in obs.START_CLASSES:
            with self.subTest(mode=mode):
                self.phx[obs.START_CONFIG] = child[obs.START_CONFIG] = mode
                report = self.summarize()
                self.assertEqual(report['status'], 'start-time-pci-config-classification')
                self.assertEqual(report['start_time_config_classification'], mode)
                self.assertFalse(any(report[key] for key in ('loaded_image_identity_checked',
                                 'active_interrupt_mode_proved', 'active_isr_proved', 'eop_delivery_proved')))

    def test_start_configuration_must_match_both_provider_snapshots(self):
        self.phx[obs.START_CONFIG] = 'msi-enable-set'
        with self.assertRaises(ValueError):
            self.summarize()
        child = self.pci[obs.CHILDREN][0]
        child[obs.START_CONFIG] = self.phx[obs.START_CONFIG]
        with self.assertRaises(ValueError):
            self.summarize(after={**self.pci, obs.CHILDREN: [{**child, obs.START_CONFIG: 'both-message-enables-clear'}]})
        self.phx[obs.START_CONFIG] = child[obs.START_CONFIG] = 'private-or-unrecognized'
        with self.assertRaises(ValueError):
            self.summarize()

    def test_duplicate_identity_is_refused(self):
        with self.assertRaises(ValueError):
            self.summarize(before=[self.pci, self.pci])

    def test_other_service_is_refused(self):
        self.phx[obs.REGISTRY_ID] += 1
        with self.assertRaises(ValueError):
            self.summarize()

    def test_other_build_is_refused(self):
        for build in (41, 42, True, '34'):
            with self.subTest(build=build), self.assertRaises(ValueError):
                self.phx['phx-build'] = build
                self.summarize()


if __name__ == '__main__':
    unittest.main()
