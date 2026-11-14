#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Checked one-attempt desktop adapters. No installer, default packet or arming.

A private root-owned packet binds these commands to the owner's single request.
Running this file by itself neither installs nor initializes anything. Every
native call is explicit; the old full.sh/bringup5.sh/phxboot.sh are never run.
"""
import argparse
import hashlib
import os
from pathlib import Path
import plistlib
import re
import stat
import struct
import subprocess
import sys
import time

import allocation_capture as capture
import allocation_observer as observer
import allocation_startup as startup

HISTORY_FIELDS = ('version bytes framebuffer_id preparations prepared_ns hold_on_ns '
                  'hold_deadline_ns first_release_ns release_reason hold_on_count release_count '
                  'first_server_request_ns server_requests first_server_success_ns server_successes '
                  'read_ns held invalid').split()
STAGE_TIMEOUTS = dict(initialize=65, claim=10, display=30, release=10, monitor=100)
NATIVE_ROLES = (*startup.ROLES, 'watch', 'disarm', 'recover-display', 'reboot')
CONTROL_DIR = Path('/Users/Shared/gpu')
PENDING_MARKER = Path('/private/var/db/phxboot.pending')


def ioreg_nodes(raw):
    # ioreg -a emits zero bytes, not an empty XML array, when no class matches.
    # This is normal only at the explicitly bounded service-discovery points.
    value = plistlib.loads(raw) if raw.strip() else []
    capture.require(type(value) is list and all(type(node) is dict for node in value), 'desktop-service-schema')
    return value


def check_runtime(path, interpreter):
    """Verify the delivered interpreter/import tree, including large libpython.

    The private delivery pins this manifest in both command sets. Its complete
    file set is checked; executable pins alone do not authenticate Python's
    dynamically loaded runtime. System libraries remain tied to the OS build.
    """
    manifest = capture.decode(capture.read_file(path, 4 * 1024 * 1024))
    capture.keys(manifest, 'format root files')
    root = capture.checked_path(manifest['root'])
    capture.require(capture.integer(manifest['format']) == 1
                    and type(manifest['files']) is dict and 0 < len(manifest['files']) <= 4096
                    and Path(interpreter).is_relative_to(root)
                    and Path(sys.executable).resolve() == Path(interpreter), 'desktop-runtime')
    for parent in (root, *root.parents):
        info = parent.stat()
        capture.require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.geteuid())
                        and not info.st_mode & 0o022, 'desktop-runtime-parent')
    actual = set()
    total = 0
    for count, item in enumerate(root.rglob('*'), 1):
        capture.require(count <= 8192, 'desktop-runtime-size')
        info = item.lstat()
        capture.require(not stat.S_ISLNK(info.st_mode) and info.st_uid == os.geteuid()
                        and not info.st_mode & 0o022, 'desktop-runtime-file')
        if stat.S_ISDIR(info.st_mode):
            continue
        capture.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                        and info.st_size <= 64 * 1024 * 1024, 'desktop-runtime-file')
        name = item.relative_to(root).as_posix()
        expected = manifest['files'].get(name)
        capture.require(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected), 'desktop-runtime-file')
        total += info.st_size
        capture.require(total <= 256 * 1024 * 1024, 'desktop-runtime-size')
        digest = hashlib.sha256()
        with item.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        capture.require(digest.hexdigest() == expected, 'desktop-runtime-file')
        actual.add(name)
    capture.require(actual == set(manifest['files']), 'desktop-runtime-file-set')


def history(raw):
    capture.require(type(raw) is bytes and len(raw) == 8 * len(HISTORY_FIELDS), 'display-history-size')
    value = dict(zip(HISTORY_FIELDS, struct.unpack('<18Q', raw)))
    capture.require(value['version'] == 1 and value['bytes'] == len(raw)
                    and value['framebuffer_id'] > 0 and value['preparations'] == 1
                    and value['invalid'] == 0 and value['held'] in (0, 1)
                    and 0 < value['prepared_ns'] <= value['hold_on_ns'] <= value['read_ns']
                    and value['hold_deadline_ns'] - value['hold_on_ns'] == 120_000_000_000
                    and value['hold_on_count'] == 1, 'display-history-invalid')
    capture.require((value['server_requests'] == 0) == (value['first_server_request_ns'] == 0)
                    and (value['server_successes'] == 0) == (value['first_server_success_ns'] == 0)
                    and value['server_successes'] <= value['server_requests'], 'display-history-invalid')
    return value


def check_history(value, ready, release=None):
    capture.require(value['hold_on_ns'] <= ready['baseline_completed_ns'] <= value['read_ns'],
                    'display-baseline-order')
    if release is None:
        capture.require(value['held'] == 1 and value['release_count'] == 0
                        and value['first_release_ns'] == 0 and value['release_reason'] == 0
                        and value['server_requests'] == value['server_successes'] == 0
                        and value['read_ns'] < value['hold_deadline_ns'], 'display-early-panel-or-expiry')
    else:
        capture.keys(release, 'before_ns after_ns reports_before frames_before')
        for key in release:
            capture.integer(release[key])
        capture.require(value['held'] == 0 and value['release_count'] == 1
                        and value['release_reason'] == 1
                        and ready['ready_ns'] <= release['before_ns'] <= value['first_release_ns']
                        <= release['after_ns'] <= value['read_ns']
                        and value['first_release_ns'] < value['hold_deadline_ns'], 'display-release-order')
        if value['server_requests']:
            capture.require(value['first_release_ns'] <= value['first_server_request_ns']
                            <= value['read_ns'], 'display-early-panel-or-expiry')
        if value['server_successes']:
            capture.require(value['first_server_request_ns'] <= value['first_server_success_ns']
                            <= value['read_ns'], 'display-history-invalid')
    return {'framebuffer_id': value['framebuffer_id'], 'held': bool(value['held']),
            'panel_open': bool(value['server_successes'])}


def count_reports(path, later=False):
    """Reference count policy: all WindowServer[-_] initially, hyphen .ips later."""
    count = 0
    with os.scandir(path) as entries:
        for number, entry in enumerate(entries, 1):
            capture.require(number <= observer.MAX_ENTRIES, 'report-entry-limit')
            # Reference ls counts names, including .spin reports in the first
            # window. Do not turn the observer's first arrival into a threshold.
            count += int(entry.name.startswith('WindowServer-') and entry.name.endswith('.ips')
                         if later else entry.name.startswith(('WindowServer-', 'WindowServer_')))
    return count


class CrashPolicy:
    """Original 90 s/3 reports; later 2 .ips reports within 5 minutes."""
    def __init__(self, baseline):
        self.baseline = baseline
        self.first = None

    def initial(self, count):
        return count - self.baseline >= 3

    def later(self, count, now):
        if count <= self.baseline:
            return False
        if self.first is None:
            self.first = now
        # Ordering matches phxboot.sh: test the second report before resetting
        # the window on this 15-second scan.
        if count - self.baseline >= 2:
            return True
        if now - self.first > 300:
            self.baseline, self.first = count, None
        return False


def load_packet(path, recovery_only=False):
    # These timestamps cross exec boundaries and are compared with kernel
    # mach-uptime nanoseconds. The system 3.9 interpreter has a per-process
    # monotonic epoch on macOS; do not silently accept its plausible numbers.
    capture.require(sys.version_info >= (3, 13), 'desktop-clock-runtime')
    path = capture.checked_path(path)
    packet = capture.decode(capture.read_file(path))
    capture.keys(packet, 'format request_sha256 scope preparation_boot_uuid os_build spec '
                 'accel_image_uuid interpreter runtime_manifest entrypoint phxctl mesboot firmware_dir psp_layout desktop_layout reports pins recovery_pins')
    capture.require(capture.integer(packet['format']) == 1 and packet['os_build'] == '25G332'
                    and re.fullmatch('[0-9a-f]{64}', packet['request_sha256']), 'desktop-packet')
    startup.validate_spec(packet['spec'])
    capture.require(packet['spec']['expected_build'] == 39, 'desktop-packet-build')
    capture.canonical_uuid(packet['preparation_boot_uuid'])
    capture.require(capture.canonical_uuid(packet['accel_image_uuid']) == packet['accel_image_uuid'], 'desktop-packet')
    capture.directory(packet['scope'])
    for name in ('interpreter', 'entrypoint', 'phxctl', 'mesboot', 'firmware_dir', 'reports'):
        capture.checked_path(packet[name])
    for key, length in (('psp_layout', 5), ('desktop_layout', 12)):
        capture.require(type(packet[key]) is list and len(packet[key]) == length, 'desktop-layout')
        for value in packet[key]:
            capture.integer(value)
    # The packet itself is an input of every child, as are the executable,
    # launcher, all adapters, firmware, reader, installed stack and runtime
    # closure reviewed by the private delivery. No automatic dependency claim.
    for name in ('pins', 'recovery_pins'):
        capture.require(type(packet[name]) is dict and 0 < len(packet[name]) <= 60, 'desktop-pins')
    capture.require(all(packet['pins'].get(name) == digest for name, digest in packet['recovery_pins'].items()), 'desktop-pins')
    pins = {**packet['pins'], str(path): hashlib.sha256(capture.read_file(path)).hexdigest()}
    recovery_pins = {**packet['recovery_pins'], str(path): pins[str(path)]}
    for key in ('interpreter', 'entrypoint', 'runtime_manifest'):
        capture.require(packet[key] in recovery_pins, 'desktop-pins')
    for key in ('interpreter', 'entrypoint', 'phxctl', 'mesboot'):
        capture.require(packet[key] in pins, 'desktop-pins')
    startup.Command([packet['interpreter']], recovery_pins if recovery_only else pins).check()
    check_runtime(packet['runtime_manifest'], packet['interpreter'])
    return packet, pins


class Native:
    def __init__(self, packet, pins, packet_path):
        self.p = packet
        self.pins = pins
        self.packet_path = str(packet_path)
        self.scope = Path(packet['scope'])
        self.sequence = 0
        self.evidence = self.scope / 'native'
        self.evidence.mkdir(mode=0o700, exist_ok=True)
        capture.directory(self.evidence)

    def command(self, role):
        pins = self.pins
        if role in ('watch', 'disarm', 'recover-display', 'reboot'):
            pins = {**self.p['recovery_pins'], self.packet_path: self.pins[self.packet_path]}
        return startup.Command([self.p['interpreter'], '-B', '-I', '-S', self.p['entrypoint'],
                                '--packet', self.packet_path, '--role', role], pins)

    def call(self, label, argv, allowed=(0,), timeout=5):
        # Per-process files, bounded output and a single invocation. A timed-out
        # IOKit process is never retried or assumed cancelled.
        folder = self.evidence / ('%d-%03d-%s' % (os.getpid(), self.sequence, label))
        self.sequence += 1
        folder.mkdir(mode=0o700)
        try:
            raw = capture.run_command(argv, folder, 'command', time.monotonic() + timeout)
        except capture.CaptureError:
            status_path = folder / 'command.status.json'
            if status_path.exists():
                status = capture.decode(capture.read_file(status_path))
                if status['returncode'] in allowed and status['timed_out'] is False:
                    raw = capture.read_file(folder / 'command.stdout')
                else:
                    raise
            else:
                raise
        status = capture.decode(capture.read_file(folder / 'command.status.json'))
        capture.require(status['returncode'] in allowed, 'desktop-command-status')
        self.last_returncode = status['returncode']
        self.last_stderr = capture.read_file(folder / 'command.stderr')
        return raw

    def sysread(self, name):
        return int(self.call('read-' + name, ['/usr/sbin/sysctl', '-n', 'debug.' + name]).strip())

    def syswrite(self, name, value, expected=None):
        self.call('write-' + name, ['/usr/sbin/sysctl', '-w', 'debug.' + name + '=' + str(value)])
        capture.require(self.sysread(name) == (value if expected is None else expected), 'display-gate-readback')

    def identity(self):
        folder = self.evidence / ('%d-%03d-identity' % (os.getpid(), self.sequence))
        self.sequence += 1
        folder.mkdir(mode=0o700)
        result = capture.identity(folder, 'live', time.monotonic() + 5, self.p['spec'], capture.run_command)
        raw = self.call('accel-image', ['/usr/sbin/kextstat', '-l', '-b', 'com.luuumi.PhxAccel']).decode()
        lines = [line for line in raw.splitlines() if 'com.luuumi.PhxAccel' in line.split()]
        images = re.findall(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b', '\n'.join(lines))
        capture.require(len(lines) == len(images) == 1
                        and capture.canonical_uuid(images[0]) == self.p['accel_image_uuid'], 'display-accel-image')
        return result

    def await_services(self):
        # Bounded boot metadata discovery only, before the observer and any GPU
        # initialization. The independent metadata recovery already owns time.
        deadline = time.monotonic() + 60
        for _ in range(60):
            capture.require(not any(os.path.lexists(path) for path in
                                    (CONTROL_DIR / 'phxboot-off', CONTROL_DIR / 'phxboot-m2', PENDING_MARKER)),
                            'desktop-boot-control')
            driver = ioreg_nodes(self.call('boot-bringup', ['/usr/sbin/ioreg', '-a', '-r', '-c', 'PhxBringup', '-d', '1']))
            framebuffer = ioreg_nodes(self.call('boot-framebuffer', ['/usr/sbin/ioreg', '-a', '-r', '-c', 'PhxAMDFB', '-d', '1']))
            capture.require(type(driver) is list and len(driver) <= 1
                            and type(framebuffer) is list and len(framebuffer) <= 1, 'desktop-boot-services')
            if driver:
                capture.require(type(driver[0]) is dict and type(driver[0].get('phx-build')) is int
                                and driver[0]['phx-build'] == self.p['spec']['expected_build'], 'desktop-boot-build')
            if driver and framebuffer:
                firmware = ioreg_nodes(self.call('boot-firmware', ['/usr/sbin/ioreg', '-a', '-r', '-c', 'IONDRVFramebuffer', '-d', '1']))
                capture.require(type(firmware) is list and not firmware, 'desktop-boot-framebuffer')
                return
            capture.require(time.monotonic() < deadline, 'desktop-boot-services')
            time.sleep(1)
        raise capture.CaptureError('desktop-boot-services')

    def read_history(self):
        value = history(self.call('display-history', ['/usr/sbin/sysctl', '-b', 'debug.phxfb_history']))
        raw = self.call('framebuffer', ['/usr/sbin/ioreg', '-a', '-r', '-c', 'PhxAMDFB', '-d', '2'])
        nodes = plistlib.loads(raw)
        capture.require(type(nodes) is list and len(nodes) == 1
                        and nodes[0].get('IORegistryEntryID') == value['framebuffer_id'], 'display-framebuffer-identity')
        children = nodes[0].get('IORegistryEntryChildren', [])
        capture.require(type(children) is list and all(type(node) is dict for node in children), 'display-framebuffer-identity')
        self.panel_open = any(node.get('IOObjectClass') == 'IOFramebufferUserClient' for node in children)
        capture.require(not self.panel_open or value['server_successes'] > 0, 'display-history-invalid')
        capture.publish_json(self.evidence / ('%d-%03d-history.json' % (os.getpid(), self.sequence)),
                             {'history': value, 'panel_open': self.panel_open})
        self.sequence += 1
        return value

    def boundary(self):
        ready = capture.decode(capture.read_file(self.scope / 'observer-ready.json'))
        release_path = self.scope / 'release-completed.json'
        release = capture.decode(capture.read_file(release_path)) if release_path.exists() else None
        result = check_history(self.read_history(), ready, release)
        result['panel_open'] = self.panel_open
        return result

    def guard(self, released=False):
        expected = capture.decode(capture.read_file(self.scope / 'identity.json'))
        startup.identity_matches(self.identity, expected, self.p['spec'])
        capture.require(self.boundary()['held'] is not released, 'display-panel-boundary')

    def claim_role(self, role):
        # The coordinator's durable claim must exist; standalone mutable stages
        # cannot create it. Each stage has its own non-replayable claim as well.
        capture.read_file(self.scope / 'startup.started')
        capture.write_json(self.scope / (role + '.started'), {'format': 1, 'monotonic_ns': time.monotonic_ns()})

    def initialize(self):
        self.guard()
        self.call('firmware-power', [self.p['phxctl'], 'gfx-power-sequence', self.p['firmware_dir'],
                  *map(str, self.p['psp_layout'])], timeout=40)
        self.guard()
        self.call('desktop-init', [self.p['mesboot'], 'desktop-init',
                  *map(str, self.p['desktop_layout'])], timeout=20)

    def claim(self):
        capture.read_file(self.scope / 'initialize-completed.json')
        self.guard()
        self.call('desktop-claim', [self.p['mesboot'], 'desktop-claim', *map(str, self.p['desktop_layout'])])

    def display(self):
        capture.read_file(self.scope / 'claim-completed.json')
        self.guard()
        self.syswrite('phxbos_flush', 0)
        deadline = time.monotonic() + 20
        while True:
            raw = self.call('accelerator', ['/usr/sbin/ioreg', '-a', '-r', '-c', 'NMXAccel', '-d', '1'])
            if len(ioreg_nodes(raw)) == 1:
                break
            capture.require(time.monotonic() < deadline, 'display-no-accelerator')
            time.sleep(1)
        self.syswrite('nvaccelfb', 1, expected=1); time.sleep(1)
        self.syswrite('nvaccel_iop', 1)
        self.syswrite('nvaccelfb', 3, expected=1); time.sleep(1)
        # phxagdc schedules its worker asynchronously. Its write does not prove
        # creation; observe the actual state before admitting display release.
        self.call('arm-agdc', ['/usr/sbin/sysctl', '-w', 'debug.phxagdc=1'])
        time.sleep(1)
        capture.require(self.sysread('phxagdc') == 1, 'display-agdc-not-up')
        self.syswrite('nvaccel_iop_sse', 1)
        self.syswrite('nvaccel_iop_vsync', 1)
        self.guard()

    def release(self):
        capture.read_file(self.scope / 'display-completed.json')
        self.guard()
        reports_before = count_reports(self.p['reports'])
        frames_before = self.sysread('nvaccel_iop_ok')
        before = time.monotonic_ns()
        self.syswrite('phxfb_hold', 0)
        result = {'before_ns': before, 'after_ns': time.monotonic_ns(),
                  'reports_before': reports_before, 'frames_before': frames_before}
        ready = capture.decode(capture.read_file(self.scope / 'observer-ready.json'))
        check_history(self.read_history(), ready, result)
        return result

    def monitor(self):
        release = capture.decode(capture.read_file(self.scope / 'release-completed.json'))
        policy = CrashPolicy(release['reports_before'])
        began = time.monotonic()
        for number in range(1, 19):
            time.sleep(max(0, began + number * 5 - time.monotonic()))
            count = count_reports(self.p['reports'])
            capture.require(not policy.initial(count), 'display-three-reports-in-90-seconds')
        self.call('windowserver', ['/usr/bin/pgrep', '-qx', 'WindowServer'])
        self.guard(released=True)
        frames = self.sysread('nvaccel_iop_ok')
        return {'format': 1, 'seconds': time.monotonic() - began,
                'report_delta': count - policy.baseline, 'frames_before': release['frames_before'],
                'frames_after': frames, 'panel_copy_progress': frames > release['frames_before'],
                'usable_accelerated_desktop_proven': False}

    def watch(self):
        capture.read_file(self.scope / 'run/startup.json')
        capture.write_json(self.scope / 'watch.started', {'pid': os.getpid(), 'monotonic_ns': time.monotonic_ns()})
        policy = CrashPolicy(count_reports(self.p['reports'], later=True))
        while True:
            time.sleep(15)
            if policy.later(count_reports(self.p['reports'], later=True), time.time()):
                # Retain the reference 3 reboot records/hour policy. This packet
                # never creates phxboot-m2 or rearms phxfb-boot on success.
                path = CONTROL_DIR / 'hang-reboots'
                now = int(time.time())
                previous = []
                if path.exists():
                    raw = self.call('hang-history', ['/bin/cat', str(path)])
                    capture.require(len(raw) < 65536, 'display-hang-history')
                    previous = [int(line) for line in raw.splitlines()]
                fd = os.open(capture.checked_path(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'a') as stream:
                    stream.write(str(now) + '\n'); stream.flush(); os.fsync(stream.fileno())
                capture.publish_json(self.scope / 'watch-trigger.json', {
                    'format': 1, 'at': now, 'two_reports': True,
                    'three_reboots_within_hour': sum(t > now - 3600 for t in (*previous, now)) >= 3})
                # There is no persistent M2 marker in a one-attempt delivery;
                # disarming is therefore also correct below the third reboot.
                self.fallback()
                return

    def fallback(self):
        # Same independent dispatcher as startup; no observer/stage wait and
        # no synchronous AGDC dependency before the reboot deadline.
        folder = self.scope / 'later-recovery'
        folder.mkdir(mode=0o700)
        recovery = startup.Recovery(folder, {
            'disarm': self.command('disarm'), 'display': self.command('recover-display'),
            'reboot': self.command('reboot')}, 240, capture.decode(capture.read_file(self.scope / 'identity.json')))
        recovery.arm(time.monotonic() + 2)
        recovery.request()
        recovery.close()

    def disarm(self):
        off = CONTROL_DIR / 'phxboot-off'
        if not off.exists():
            capture.write_file(capture.checked_path(off), b'')
        marker = capture.checked_path(CONTROL_DIR / 'phxboot-m2')
        if marker.exists():
            marker.unlink()
        self.call('disarm-nvram', ['/usr/sbin/nvram', '-d', 'phxfb-boot'], allowed=(0, 1))
        self.call('sync-nvram', ['/usr/sbin/nvram', 'IONVRAM-FORCESYNCNOW-PROPERTY=phxfb'])
        raw = self.call('check-nvram', ['/usr/sbin/nvram', 'phxfb-boot'], allowed=(1,))
        capture.require(not raw and self.last_returncode == 1
                        and b'not found' in self.last_stderr.lower()
                        and b'phxfb-boot' in self.last_stderr, 'display-disarm-readback')

    def recover_display(self):
        # This helper may block; recovery never waits for it to request reboot.
        for name in ('nvaccel_iop', 'nvaccelfb', 'phxagdc', 'phxfb_hold'):
            self.call('recover-' + name, ['/usr/sbin/sysctl', '-w', 'debug.' + name + '=0'], allowed=(0, 1))

    def reboot(self):
        # Exclusive marker also prevents competing initial/later recovery owners
        # from dispatching the one permitted fallback restart twice.
        capture.write_json(self.scope / 'reboot.started', {'monotonic_ns': time.monotonic_ns()})
        self.call('fallback-reboot', ['/sbin/shutdown', '-r', 'now'])

    def run(self):
        capture.write_json(self.scope / 'boot-entry.started', {
            'format': 1, 'request_sha256': self.p['request_sha256'], 'monotonic_ns': time.monotonic_ns()})
        commands = {'disarm': self.command('disarm'), 'display': self.command('recover-display'),
                    'reboot': self.command('reboot')}
        early_root = self.scope / 'metadata-recovery'
        early_root.mkdir(mode=0o700)
        # Guard identity/framebuffer discovery too. This context deliberately
        # records an unverified boot, rather than inventing its service/UUID.
        early = startup.Recovery(early_root, commands, 240, {
            'metadata_pending': True, 'expected_build': self.p['spec']['expected_build'],
            'expected_image_uuid': self.p['spec']['expected_image_uuid']},
            claim_path=self.scope / 'boot-entry.started', dismissal_outcome='handed-to-coordinator-recovery')
        handed = False

        def handoff():
            nonlocal handed
            # Called only after the coordinator's own recovery acknowledged
            # arming. Its remaining deadline preserves this original 240 s.
            early.dismiss(time.monotonic() + 2)
            handed = True

        def observe(out, on_ready):
            def ready(value):
                capture.publish_json(self.scope / 'observer-ready.json', value)
                on_ready(value)
            spec = self.p['spec']
            return observer.observe(self.p['reports'], out, spec['reader'], spec['reader_sha256'],
                                    spec['expected_build'], spec['expected_image_uuid'], 180, on_ready=ready)

        try:
            early.arm(time.monotonic() + 2)
            capture.publish_json(self.scope / 'metadata-recovery-armed.json', {
                'pid': early.pid, 'deadline_monotonic': early.deadline,
                'claim_sha256': early.claim_sha256, 'boot_metadata_verified': False})
            self.await_services()
            expected = self.identity()
            capture.require(expected['boot_uuid'] != self.p['preparation_boot_uuid']
                            and expected['os_build'] == self.p['os_build'], 'desktop-wrong-boot')
            capture.write_json(self.scope / 'identity.json', expected)
            result = startup.supervise(self.scope, self.p['spec'], expected, self.identity, self.boundary,
                                       observe, {role: self.command(role) for role in startup.ROLES}, commands,
                                       stage_timeouts=STAGE_TIMEOUTS,
                                       watchdog_deadline=early.deadline, on_recovery_armed=handoff)
        except BaseException:
            if not handed:
                early.request()
            raise
        finally:
            early.close()
        # Keep the launchd entry process alive for the original later-watch
        # policy, like the reference monitor. No detached child's survival is
        # inferred from successful spawn or daemon exit.
        self.watch()
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', required=True, type=Path)
    parser.add_argument('--role', required=True, choices=('run', *NATIVE_ROLES))
    args = parser.parse_args(argv)
    capture.host_check()
    os.umask(0o077)
    packet, pins = load_packet(args.packet, recovery_only=args.role in ('watch', 'disarm', 'recover-display', 'reboot'))
    native = Native(packet, pins, args.packet)
    try:
        if args.role in startup.ROLES:
            native.claim_role(args.role)
        result = getattr(native, args.role.replace('-', '_'))()
        if args.role in startup.ROLES:
            capture.publish_json(native.scope / (args.role + '-completed.json'), result or {'format': 1})
        return 0
    except (OSError, capture.CaptureError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as exc:
        if args.role in ('watch', 'run') and (native.scope / 'run/startup.json').exists():
            native.fallback()
        print('desktop-startup refused: ' + (str(exc) if isinstance(exc, capture.CaptureError) else 'input-or-io'), file=sys.stderr)
        return 74


if __name__ == '__main__':
    raise SystemExit(main())
