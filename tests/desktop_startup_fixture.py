"""File-only executable fixture for the actual desktop/coordinator process chain.

Only this fixture replaces host/native I/O and shortens waits. It cannot run a
real native helper or perform a system write. Production defaults are unchanged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import allocation_capture as capture
import allocation_observer as observer
import allocation_startup as startup
import desktop_startup as desktop

parser = argparse.ArgumentParser()
parser.add_argument('--packet', type=Path, required=True)
parser.add_argument('--role', required=True)
args = parser.parse_args()
# Only for running these offline fakes under Apple's older test interpreter.
# The production loader refuses it and the delivery must use Python 3.13+.
if sys.platform == 'darwin' and sys.version_info < (3, 13):
    absolute_ns = lambda: time.clock_gettime_ns(time.CLOCK_UPTIME_RAW)
    time.monotonic_ns = absolute_ns
    time.monotonic = lambda: absolute_ns() / 1_000_000_000
packet = json.loads(args.packet.read_text())
work = Path(packet['scope'])
pins = {**packet['pins'], str(args.packet): hashlib.sha256(args.packet.read_bytes()).hexdigest()}
capture.host_check = lambda: None
desktop.load_packet = lambda *_args, **_kwargs: (packet, pins)
desktop.CONTROL_DIR = work / 'controls'
desktop.PENDING_MARKER = work / 'legacy.pending'
desktop.STAGE_TIMEOUTS = {role: 2 for role in startup.ROLES}
desktop.STAGE_TIMEOUTS['initialize'] = 2
(work / (args.role + '.pid')).write_text(str(os.getpid()))
real_sleep = time.sleep
real_monotonic = time.monotonic


class FixtureRecovery(startup.Recovery):
    def __init__(self, root, commands, watchdog_seconds, identity, **kwargs):
        super().__init__(root, commands, min(watchdog_seconds, 10), identity, **kwargs)


startup.Recovery = FixtureRecovery
actual_observe = observer.observe


def observe(reports, out, reader, digest, build, image, seconds, on_ready):
    def baseline(out, *_args):
        out.mkdir(mode=0o700)
        reasons = [dict(reason=name, count=0, records=[])
                   for name in capture.REASONS]
        value = dict(format=1, phase='baseline', saved_at='2026-11-14T00:00:00+00:00',
                     identity=packet['fixture_identity'], spec=packet['spec'],
                     snapshot=dict(version=1, kext_build=39, observed=0, samples_per_reason=4, reasons=reasons))
        capture.write_json(out / 'baseline.json', value)

    class Watch:
        def __init__(self, _path): pass
        def scan(self): return {}
        def wait(self, seconds): real_sleep(seconds); return False
        def close(self): pass

    return actual_observe(reports, out, reader, digest, build, image, seconds,
                          baseline=baseline, watch_factory=Watch, on_ready=on_ready, clock=time.monotonic)


observer.observe = observe


class FixtureNative(desktop.Native):
    def identity(self):
        return packet['fixture_identity'].copy()

    def call(self, label, argv, allowed=(0,), timeout=5):
        # Closed whitelist: an unfamiliar invocation cannot escape to the OS.
        self.last_returncode, self.last_stderr = 0, b''
        with (work / ('calls-' + args.role)).open('a') as stream:
            stream.write(label + '\n')
        if label == 'firmware-power' and packet['fixture_mode'] in ('init-fail', 'recovery-display-blocked'):
            raise capture.CaptureError('fixture-power-refused')
        if label.startswith('recover-') and packet['fixture_mode'] == 'recovery-display-blocked':
            (work / 'recovery-display-blocked').write_text('blocked')
            real_sleep(20)
        if label in ('firmware-power', 'desktop-init', 'desktop-claim'):
            return b'fixture checked native completion\n'
        if label == 'boot-bringup': return plistlib.dumps([{'phx-build': 39}])
        if label == 'boot-framebuffer': return plistlib.dumps([{}])
        if label == 'boot-firmware': return plistlib.dumps([])
        if label == 'display-history':
            on = packet['fixture_hold_ns']
            stamp = work / 'fixture-release-ns'
            released = int(stamp.read_text()) if stamp.exists() else 0
            value = dict(version=1, bytes=144, framebuffer_id=17, preparations=1,
                         prepared_ns=on - 1, hold_on_ns=on, hold_deadline_ns=on + 120_000_000_000,
                         first_release_ns=released, release_reason=1 if released else 0, hold_on_count=1,
                         release_count=int(bool(released)), first_server_request_ns=released + 1 if released else 0,
                         server_requests=int(bool(released)), first_server_success_ns=released + 2 if released else 0,
                         server_successes=int(bool(released)), read_ns=time.monotonic_ns(), held=int(not released), invalid=0)
            return struct.pack('<18Q', *(value[name] for name in desktop.HISTORY_FIELDS))
        if label == 'framebuffer':
            children = [dict(IOObjectClass='IOFramebufferUserClient')] if (work / 'fixture-release-ns').exists() else []
            return plistlib.dumps([dict(IORegistryEntryID=17, IORegistryEntryChildren=children)])
        if label == 'accelerator': return plistlib.dumps([{}])
        if label.startswith('write-') or label == 'arm-agdc':
            key, value = argv[-1].split('=')
            if key == 'debug.phxfb_hold':
                (work / 'fixture-release-ns').write_text(str(time.monotonic_ns()))
            (work / key).write_text('1' if key == 'debug.nvaccelfb' else value)
            return b'fixture gate write\n'
        if label.startswith('read-'):
            key = argv[-1]
            if key == 'debug.nvaccel_iop_ok':
                return b'100\n' if (work / 'fixture-release-ns').exists() else b'0\n'
            path = work / key
            return (path.read_text() if path.exists() else '0').encode()
        if label == 'windowserver': return b''
        if label in ('disarm-nvram', 'sync-nvram'): return b''
        if label == 'check-nvram':
            self.last_returncode, self.last_stderr = 1, b'phxfb-boot: data was not found'
            return b''
        if label.startswith('recover-'): return b'fixture teardown\n'
        if label == 'fallback-reboot':
            (work / 'fixture-reboot-requested').write_text(str(time.monotonic_ns()))
            return b''
        raise RuntimeError('Fixture refused unrecognized command: ' + label)

    def watch(self):
        # Later-watch policy/dispatch is tested separately. This process fixture
        # tests the complete initial monitor and recovery handoff, then exits.
        (work / 'fixture-later-watch-entered').write_text('yes')


desktop.Native = FixtureNative
if args.role == 'display':
    desktop.time.sleep = lambda _seconds: None
if args.role == 'monitor':
    clock = [real_monotonic()]
    desktop.time.monotonic = lambda: clock[0]
    desktop.time.sleep = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
raise SystemExit(desktop.main())
