#!/usr/bin/env python3
"""Real CPU child processes only; no DTrace, IOKit, driver or power access."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'R1b_trace_CPU', Path(__file__).resolve().parents[1] / 'tools/build34_ring_pressure_trace.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
REAL_POPEN = subprocess.Popen


class TraceTests(unittest.TestCase):
    def test_program_pairs_exact_sleep_caller_with_actual_block_return(self):
        text = m.trace_program(123)
        self.assertIn('pid == 123 && arg0 == 1', text)
        self.assertIn('caller == self->pc', text)
        self.assertIn('fbt:mach_kernel:thread_block_reason:return', text)
        self.assertIn('WAIT_BLOCK', text)
        self.assertLess(text.index('self->blocked = (uint64_t)0'), text.index('/pid == 123 && self->blocked/'))
        self.assertNotIn('delay_for_interval:return', text)
        self.assertNotIn('IOSleep:return', text)
        with self.assertRaises(AssertionError):
            m.trace_program(1)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.children = []
        self.addCleanup(self.stop_CPU_children)

    def stop_CPU_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=2)

    def run_capture(self, trace, probe=None, arm=0.5, retire=0.3,
                    wait_trace_done=False, trace_retire=2):
        if probe is None:
            probe = "import sys;sys.exit(0 if sys.stdin.buffer.read(1)==b'G' else 64)"
        def start(args, **kwargs):
            source = probe if args[0] == '/usr/bin/nice' else trace
            child = REAL_POPEN([sys.executable, '-c', source], **kwargs)
            self.children.append(child)
            if wait_trace_done and args[0] != '/usr/bin/nice':
                child.wait(timeout=2)
            return child
        with patch.object(m.subprocess, 'Popen', side_effect=start), \
                patch.object(m, 'ARM_SECONDS', arm), patch.object(m, 'PROBE_RETIRE_SECONDS', retire), \
                patch.object(m, 'TRACE_RETIRE_SECONDS', trace_retire):
            return m.capture(self.root)

    def read(self, name):
        return json.loads((self.root / name).read_text())

    def test_delayed_ready_dispatches_once_and_records_clean_retirement(self):
        # An arbitrary short post-READY sleep can expire while the parent is
        # descheduled. End this CPU double only after the fake probe sees G.
        ack = repr(str(self.root / 'CPU-release-received'))
        trace = ("import pathlib,time;time.sleep(.15);print('READY',flush=True);"
                 f"p=pathlib.Path({ack});end=time.monotonic()+3\n"
                 "while not p.exists() and time.monotonic()<end:time.sleep(.01)\n"
                 "assert p.exists();print('END',flush=True)")
        probe = ("import pathlib,sys;assert sys.stdin.buffer.read(1)==b'G';"
                 f"pathlib.Path({ack}).write_text('G')")
        self.assertEqual(self.run_capture(trace, probe=probe, arm=1.5, trace_retire=4), (0, 0))
        self.assertGreater(self.read('pressure-trace-ready-private.json')['elapsed_seconds'], .1)
        life = self.read('pressure-trace-lifecycle-private.json')
        self.assertEqual(life, {'trace_ready': True, 'G_dispatch_may_have_occurred': True,
                               'probe_exit': 0, 'trace_exit': 0, 'probe_terminated_by_controller': False})
        self.assertTrue((self.root / 'pressure-G-released-private.json').is_file())
        self.assertFalse((self.root / 'pressure-probe-held-private.txt').exists())

    def test_readiness_timeout_closes_probe_with_EOF_without_G(self):
        with self.assertRaisesRegex(RuntimeError, 'did not arm'):
            self.run_capture("import time;time.sleep(2)", arm=.08)
        self.assertFalse((self.root / 'pressure-G-release.intent').exists())
        life = self.read('pressure-trace-lifecycle-private.json')
        self.assertFalse(life['G_dispatch_may_have_occurred'])
        self.assertEqual(life['probe_exit'], 64)

    def test_trace_diagnostics_refuse_GPU_release(self):
        with self.assertRaisesRegex(RuntimeError, 'did not arm'):
            self.run_capture("import sys,time;print('diagnostic',file=sys.stderr,flush=True);time.sleep(2)")
        self.assertFalse((self.root / 'pressure-G-release.intent').exists())
        self.assertEqual(self.read('pressure-trace-lifecycle-private.json')['probe_exit'], 64)

    def test_early_trace_exit_refuses_GPU_release(self):
        with self.assertRaisesRegex(RuntimeError, 'did not arm'):
            self.run_capture("raise SystemExit(1)")
        self.assertFalse((self.root / 'pressure-G-release.intent').exists())
        self.assertEqual(self.read('pressure-trace-lifecycle-private.json')['probe_exit'], 64)

    def test_ready_then_exit_still_refuses_GPU_release(self):
        with self.assertRaises(RuntimeError):
            self.run_capture("print('READY',flush=True)", wait_trace_done=True)
        self.assertFalse((self.root / 'pressure-G-release.intent').exists())
        self.assertEqual(self.read('pressure-trace-lifecycle-private.json')['probe_exit'], 64)

    def test_uncertain_CPU_probe_is_retained_after_release(self):
        # Model post-release uncertainty, not parent scheduling speed. Keep the
        # fake trace alive until this CPU-only child actually receives G.
        ack = repr(str(self.root / 'CPU-uncertain-release-received'))
        trace = ("import pathlib,time;print('READY',flush=True);"
                 f"p=pathlib.Path({ack});end=time.monotonic()+3\n"
                 "while not p.exists() and time.monotonic()<end:time.sleep(.01)\n"
                 "assert p.exists();print('END',flush=True)")
        probe = ("import pathlib,sys,time\n"
                 "if sys.stdin.buffer.read(1)!=b'G':sys.exit(64)\n"
                 f"pathlib.Path({ack}).write_text('G');time.sleep(30)")
        with self.assertRaisesRegex(RuntimeError, 'keep GPU ownership'):
            self.run_capture(trace, probe=probe, retire=.05, trace_retire=4)
        life = self.read('pressure-trace-lifecycle-private.json')
        self.assertTrue(life['G_dispatch_may_have_occurred'])
        self.assertIsNone(life['probe_exit'])
        self.assertFalse(life['probe_terminated_by_controller'])
        self.assertIsNone(self.children[0].poll())
        self.assertEqual((self.root / 'pressure-probe-held-private.txt').read_text(), str(self.children[0].pid)+'\n')

    def test_trace_timeout_after_release_never_terminates_CPU_probe(self):
        trace = "import time;print('READY',flush=True);time.sleep(30)"
        probe = "import sys,time;sys.stdin.buffer.read(1);time.sleep(30)"
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_capture(trace, probe=probe, trace_retire=.1)
        life = self.read('pressure-trace-lifecycle-private.json')
        self.assertTrue(life['G_dispatch_may_have_occurred'])
        self.assertIsNone(life['probe_exit'])
        self.assertIsNone(self.children[0].poll())
        self.assertFalse(life['probe_terminated_by_controller'])


if __name__ == '__main__':
    unittest.main()
