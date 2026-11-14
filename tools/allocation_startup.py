#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""One-attempt startup coordinator candidate; no installer or default target commands.

The caller must supply a reviewed initializer, display/monitor adapters, live
identity and framebuffer readers, and pinned recovery commands. This module
does not make the inherited full.sh or an arbitrary command safe to execute.
"""
import hashlib
import json
import math
import mmap
import os
import select
import re
import signal
import stat
import subprocess
import time

import allocation_capture as capture

ROLES = ('initialize', 'claim', 'display', 'release', 'monitor')
RECOVERY_ROLES = ('disarm', 'display', 'reboot')
MESSAGE_LIMIT = 4096
COMMAND_INPUT_LIMIT = 256 * 1024 * 1024
POLL_SECONDS = 0.02
_OWNED_PROCESSES = {}
_OWNED_PIDS = set()


def reap_owned():
    """Nonblocking housekeeping for only workers created by this interpreter."""
    for pid, child in list(_OWNED_PROCESSES.items()):
        if child.poll() is not None:
            del _OWNED_PROCESSES[pid]
    for pid in list(_OWNED_PIDS):
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            done = pid
        if done:
            _OWNED_PIDS.remove(pid)


def seconds(value):
    capture.require(type(value) in (int, float) and math.isfinite(value)
                    and 0 < value <= 300, 'startup-duration')
    return value


class Command:
    """Exact argv and input pins; corresponding source/semantic review is external."""

    def __init__(self, argv, pins):
        capture.require(type(argv) in (list, tuple) and 0 < len(argv) <= 64
                        and all(type(arg) is str and arg and '\0' not in arg for arg in argv),
                        'startup-command')
        capture.require(type(pins) is dict and 0 < len(pins) <= 64 and argv[0] in pins,
                        'startup-command-pin')
        self.argv = list(argv)
        self.pins = dict(pins)

    def check(self):
        for name, digest in self.pins.items():
            path = capture.checked_path(name)
            for parent in path.parents:
                info = parent.stat()
                capture.require(stat.S_ISDIR(info.st_mode)
                                and info.st_uid in (0, os.geteuid())
                                and not info.st_mode & 0o022, 'startup-command-parent')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                capture.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                                and info.st_uid in (0, os.geteuid())
                                and not info.st_mode & 0o022
                                and info.st_size <= COMMAND_INPUT_LIMIT, 'startup-command-pin')
                digest_observed = hashlib.sha256()
                count = 0
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    count += len(chunk)
                    capture.require(count <= COMMAND_INPUT_LIMIT, 'startup-command-pin')
                    digest_observed.update(chunk)
            capture.require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest)
                            and count == info.st_size
                            and digest_observed.hexdigest() == digest, 'startup-command-pin')
        capture.require(os.stat(self.argv[0]).st_mode & 0o111, 'startup-command-pin')

    def start(self, stdout, stderr):
        # No shell, preexec callback or global process kill. The executable and
        # its declared inputs have been checked before this call.
        return subprocess.Popen(self.argv, stdin=subprocess.DEVNULL, stdout=stdout,
                                stderr=stderr, env=capture.ENV, close_fds=True,
                                start_new_session=True)


class Trail:
    """One writer per journal; hashes link this writer's fsynced records."""

    def __init__(self, path, identity):
        self.path = path
        self.identity = identity
        self.previous = '0' * 64
        self.sequence = 0
        self.stream = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                       | os.O_NOFOLLOW, 0o600), 'wb')

    def emit(self, event, **data):
        value = {'format': 1, 'sequence': self.sequence, 'previous_sha256': self.previous,
                 'identity': self.identity, 'monotonic_ns': time.monotonic_ns(),
                 'event': event, 'data': data}
        raw = (json.dumps(value, sort_keys=True) + '\n').encode()
        self.stream.write(raw)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.previous = hashlib.sha256(raw).hexdigest()
        self.sequence += 1
        return value

    def close(self):
        self.stream.close()


def output(path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                            | os.O_NOFOLLOW, 0o600), 'wb', buffering=0)


def receive(fd, deadline):
    raw = b''
    while b'\n' not in raw:
        remaining = deadline - time.monotonic()
        capture.require(remaining > 0, 'startup-not-ready')
        readable, _, _ = select.select([fd], [], [], remaining)
        capture.require(readable, 'startup-not-ready')
        part = os.read(fd, MESSAGE_LIMIT + 1 - len(raw))
        capture.require(part, 'startup-worker-ended')
        raw += part
        capture.require(len(raw) <= MESSAGE_LIMIT, 'startup-message')
    capture.require(raw.endswith(b'\n') and raw.count(b'\n') == 1, 'startup-message')
    return capture.decode(raw)


def notify(fd, value):
    raw = (json.dumps(value, separators=(',', ':')) + '\n').encode()
    capture.require(len(raw) <= MESSAGE_LIMIT, 'startup-message')
    os.set_blocking(fd, False)
    capture.require(os.write(fd, raw) == len(raw), 'startup-message')


def recovery_worker(root, control, ready, deadline, commands, state, owned, context):
    """Own the deadline even while coordinator/observer/stages are blocked.

    Display teardown never gates disarming or reboot. Normal early fallback
    waits only for the disarm command; the original absolute watchdog deadline
    still requests reboot if that command refuses or never returns. A reboot
    request is not evidence that firmware fallback or OS recovery succeeded.
    """
    pending = None
    children = {}
    control_open = True
    state[0:1] = b'A'
    notify(ready, {'recovery': 'armed', 'pid': os.getpid()})
    while True:
        now = time.monotonic()
        expired = now >= deadline
        if state[0:1] == b'F':
            pending = pending or 'coordinator-refused'
        if pending is not None or expired:
            # Shared one-byte state has no lock or disk-write prerequisite.
            # It refuses known-pending work; it cannot atomically cancel an
            # operation already admitted by the coordinator.
            state[0:1] = b'F'
            for role in ('disarm', 'display'):
                if role not in children:
                    try:
                        children[role] = commands[role].start(subprocess.DEVNULL, subprocess.DEVNULL)
                        owned.append(children[role])
                    except OSError:
                        children[role] = None
            disarm = children['disarm']
            disarmed = disarm is not None and disarm.poll() == 0
            if disarmed or expired:
                try:
                    reboot = commands['reboot'].start(subprocess.DEVNULL, subprocess.DEVNULL)
                    owned.append(reboot)
                    reboot_pid = reboot.pid
                except OSError:
                    reboot_pid = None
                # Evidence publication follows dispatch, never precedes the
                # independent reboot request with a potentially blocking write.
                capture.publish_json(root / 'recovery.json', {
                    **context, 'recovery_pid': os.getpid(),
                    'format': 1, 'outcome': 'recovery-requested',
                    'reason': pending or 'watchdog-deadline',
                    'monotonic_ns': time.monotonic_ns(), 'disarm_completed': disarmed,
                    'watchdog_expired': expired, 'reboot_child_pid': reboot_pid,
                    'children': {role: None if child is None else
                                 {'pid': child.pid, 'returncode': child.poll()}
                                 for role, child in children.items()},
                    'display_completion_waited_for': False,
                    'observer_or_stage_waited_for': False,
                    'firmware_fallback_verified': False})
                return
        wait = max(0, deadline - time.monotonic())
        if pending is not None:
            wait = min(wait, 0.02)  # Only disarm process status; never poll the GPU/reader.
        readable, _, _ = select.select([control] if control_open else [], [], [], wait)
        if readable:
            message = os.read(control, 1)
            if (message == b'D' and pending is None and state[0:1] == b'A'
                    and time.monotonic() < deadline):
                state[0:1] = b'D'
                capture.publish_json(root / 'recovery.json', {
                    **context, 'recovery_pid': os.getpid(),
                    'format': 1, 'outcome': context.get('dismissal_outcome', 'dismissed-after-monitor'),
                    'monotonic_ns': time.monotonic_ns()})
                notify(ready, {'recovery': 'dismissed', 'pid': os.getpid()})
                return
            if message in (b'F', b''):
                pending = pending or ('coordinator-refused' if message else 'coordinator-ended')
                if not message:
                    control_open = False  # EOF stays readable: never spin on it.
            else:
                pending = pending or 'control-refused'


class Recovery:
    def __init__(self, root, commands, watchdog_seconds, identity, claim_path=None,
                 dismissal_outcome='dismissed-after-monitor', absolute_deadline=None):
        capture.require(set(commands) == set(RECOVERY_ROLES), 'startup-recovery')
        self.claim_sha256 = hashlib.sha256(capture.read_file(
            root.parent / 'startup.started' if claim_path is None else claim_path)).hexdigest()
        context = {'expected_identity': dict(identity), 'startup_claim_sha256': self.claim_sha256}
        capture.require(dismissal_outcome in ('dismissed-after-monitor', 'handed-to-coordinator-recovery'),
                        'startup-recovery')
        if dismissal_outcome != 'dismissed-after-monitor':
            context['dismissal_outcome'] = dismissal_outcome
        self.deadline = time.monotonic() + seconds(watchdog_seconds)
        if absolute_deadline is not None:
            capture.require(type(absolute_deadline) in (int, float) and math.isfinite(absolute_deadline)
                            and time.monotonic() < absolute_deadline, 'startup-duration')
            self.deadline = min(self.deadline, absolute_deadline)
        for role in RECOVERY_ROLES:
            commands[role].check()
        self.state = mmap.mmap(-1, 1)
        fds = []
        try:
            read_control, self.control = os.pipe(); fds.extend((read_control, self.control))
            self.ready, write_ready = os.pipe(); fds.extend((self.ready, write_ready))
            self.pid = os.fork()
        except BaseException:
            for fd in fds:
                os.close(fd)
            self.state.close()
            raise
        if self.pid == 0:
            os.close(self.control)
            os.close(self.ready)
            os.setsid()
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                signal.signal(signum, signal.SIG_DFL)
            owned = []  # Hold proxies until _exit without a blocking wait/destructor.
            try:
                recovery_worker(root, read_control, write_ready, self.deadline, commands, self.state, owned, context)
            except BaseException:
                self.state[0:1] = b'E'
                os._exit(74)
            os._exit(0)
        os.close(read_control)
        os.close(write_ready)
        os.set_blocking(self.control, False)
        self.reaped = False

    def check(self):
        if not self.reaped:
            self.reaped = os.waitpid(self.pid, os.WNOHANG)[0] == self.pid
        capture.require(not self.reaped and self.state[0:1] == b'A'
                        and time.monotonic() < self.deadline, 'startup-recovery-pending')

    def arm(self, deadline):
        receipt = receive(self.ready, min(deadline, self.deadline))
        capture.require(receipt == {'recovery': 'armed', 'pid': self.pid}, 'startup-recovery')

    def request(self):
        self.state[0:1] = b'F'
        try:
            os.write(self.control, b'F')
        except (BrokenPipeError, BlockingIOError):
            pass  # EOF/deadline is independently owned; never wait for another worker.

    def dismiss(self, deadline):
        self.check()
        os.write(self.control, b'D')
        receipt = receive(self.ready, min(deadline, self.deadline))
        capture.require(receipt == {'recovery': 'dismissed', 'pid': self.pid}, 'startup-recovery')

    def close(self, reap=True):
        os.close(self.control)
        os.close(self.ready)
        self.state.close()
        # Failure leaves the independent owner running to its original deadline.
        # A persistent caller must reap this exact PID later, never kill it to
        # make cleanup finish. No installable daemon/entrypoint is supplied here.
        if reap and not self.reaped:
            self.reaped = os.waitpid(self.pid, os.WNOHANG)[0] == self.pid
            if not self.reaped:
                _OWNED_PIDS.add(self.pid)


def validate_spec(spec):
    capture.keys(spec, 'reader reader_sha256 expected_build expected_image_uuid')
    capture.require(type(spec['reader']) is str, 'startup-spec')
    capture.checked_path(spec['reader'])
    capture.require(type(spec['reader_sha256']) is str
                    and re.fullmatch('[0-9a-f]{64}', spec['reader_sha256'])
                    and capture.integer(spec['expected_build'], (1 << 32) - 1) > 0
                    and capture.canonical_uuid(spec['expected_image_uuid'])
                    == spec['expected_image_uuid'], 'startup-spec')


def validate_identity(value, spec):
    capture.keys(value, 'boot_uuid os_build service_entry_id kext_build loaded_image_uuid')
    capture.require(capture.canonical_uuid(value['boot_uuid']) == value['boot_uuid']
                    and type(value['os_build']) is str
                    and re.fullmatch('[0-9]{2}[A-Z][0-9]+[a-z]?', value['os_build'])
                    and capture.integer(value['service_entry_id']) > 0
                    and capture.integer(value['kext_build']) == spec['expected_build']
                    and capture.canonical_uuid(value['loaded_image_uuid'])
                    == spec['expected_image_uuid'], 'startup-identity')


def identity_matches(current, expected, spec):
    value = current()
    validate_identity(value, spec)
    capture.require(value == expected, 'startup-identity')


def baseline_admission(root, ready, spec, expected_identity, current_identity):
    validate_spec(spec)
    validate_identity(expected_identity, spec)
    spec, expected_identity = dict(spec), dict(expected_identity)
    capture.keys(ready, 'format baseline_sha256 baseline_completed_ns ready_ns deadline_ns observer_pid')
    capture.require(capture.integer(ready['format']) == 1, 'startup-ready')
    for key in ('baseline_completed_ns', 'ready_ns', 'deadline_ns', 'observer_pid'):
        capture.integer(ready[key])
    capture.require(0 < ready['baseline_completed_ns'] <= ready['ready_ns']
                    <= time.monotonic_ns() < ready['deadline_ns']
                    and ready['observer_pid'] > 0
                    and ready['deadline_ns'] - ready['baseline_completed_ns'] <= 300_000_000_000,
                    'startup-late-baseline')
    raw = capture.read_file(root / 'baseline.json')
    digest = hashlib.sha256(raw).hexdigest()
    capture.require(digest == ready['baseline_sha256'], 'startup-baseline-changed')
    value = capture.decode(raw)
    capture.keys(value, 'format phase saved_at identity spec snapshot')
    validate_spec(value['spec'])
    validate_identity(value['identity'], spec)
    capture.require(capture.integer(value['format']) == 1 and value['phase'] == 'baseline'
                    and type(value['saved_at']) is str and 0 < len(value['saved_at']) <= 64
                    and value['spec'] == spec and value['identity'] == expected_identity,
                    'startup-identity')
    identity_matches(current_identity, expected_identity, spec)
    snapshot = capture.snapshot(json.dumps(value['snapshot']).encode(), spec['expected_build'])
    capture.require(all(reason['count'] < 4 for reason in snapshot['reasons']),
                    'startup-detail-capacity')
    capture.require(not any((root / name).exists() for name in
                            ('failure.started', 'observer.trigger.json', 'observer.json')),
                    'startup-observer-ended')
    capture.require(hashlib.sha256(capture.read_file(root / 'baseline.json')).hexdigest() == digest
                    and time.monotonic_ns() < ready['deadline_ns'], 'startup-baseline-changed')
    return digest


def bounded_stage(command, root, role, deadline, guard, children):
    """Drain bounded pipes in the coordinator, never in the recovery owner."""
    with output(root / (role + '.stdout')) as stdout, output(root / (role + '.stderr')) as stderr:
        guard()
        child = command.start(subprocess.PIPE, subprocess.PIPE)
        children.append(child)
        streams = {child.stdout: [stdout, 0], child.stderr: [stderr, 0]}
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
        try:
            while True:
                guard()
                capture.require(time.monotonic() < deadline, 'startup-stage-timeout')
                status = child.poll()
                if status is not None and not streams:
                    return status
                readable, _, _ = select.select(list(streams), [], [],
                                                min(POLL_SECONDS, max(0, deadline - time.monotonic())))
                for stream in readable:
                    raw = os.read(stream.fileno(), 8192)
                    if not raw:
                        streams.pop(stream)
                        stream.close()
                        continue
                    target, count = streams[stream]
                    remaining = capture.LIMIT - count
                    target.write(raw[:remaining])
                    streams[stream][1] += len(raw)
                    capture.require(len(raw) <= remaining, 'startup-output-limit')
        finally:
            for stream in streams:
                stream.close()


def stop_child(pid, group=False):
    """Signal only an owned PID/group; no recovery dependency on its return."""
    try:
        (os.killpg if group else os.kill)(pid, signal.SIGTERM)
        return 0
    except OSError as exc:
        # Darwin can return EPERM for an already-exited, unreaped group.
        # Preserve the signal error without skipping other owned cleanup or
        # replacing the original refusal. No termination claim follows.
        return exc.errno


def supervise(scope, spec, expected_identity, current_identity, boundary, observer_job,
              stages, recovery_commands, admission_seconds=10, stage_seconds=60,
              watchdog_seconds=240, stage_timeouts=None, on_recovery_armed=None, watchdog_deadline=None):
    """Run one reviewed attempt. Callbacks do not confer target acceptance.

    observer_job(out, on_ready) must call the actual observer; on_ready is a
    bounded pipe write. boundary() returns the selected framebuffer identity,
    held state and whether its user client is already open. A source/provenance
    reviewed adapter is required; a late state read alone proves no history.
    """
    capture.host_check()
    reap_owned()
    scope = capture.directory(scope)
    validate_spec(spec)
    validate_identity(expected_identity, spec)
    spec, expected_identity = dict(spec), dict(expected_identity)
    seconds(admission_seconds)
    seconds(stage_seconds)
    capture.require(tuple(stages) == ROLES, 'startup-stages')
    if stage_timeouts is None:
        stage_timeouts = {role: stage_seconds for role in ROLES}
    capture.require(type(stage_timeouts) is dict and set(stage_timeouts) == set(ROLES),
                    'startup-stage-timeouts')
    stage_timeouts = {role: seconds(stage_timeouts[role]) for role in ROLES}
    stages = dict(stages)
    for command in stages.values():
        command.check()
    # Fixed scope claim is durable on every exit. Output-directory changes
    # cannot make this approved scope's attempt runnable again.
    capture.write_json(scope / 'startup.started', {'format': 1, 'identity': expected_identity})
    capture.sync_directory(scope)
    root = scope / 'run'
    root.mkdir(mode=0o700)
    capture.write_file(root / '.gitignore', b'*\n')
    recovery = None
    observer_pid = None
    stage_children = []
    trail = None
    reader_fd = None
    writer_fd = None
    observer_reaped = False
    try:
        recovery = Recovery(root, recovery_commands, watchdog_seconds, expected_identity,
                            absolute_deadline=watchdog_deadline)
        admission_deadline = time.monotonic() + admission_seconds
        recovery.arm(admission_deadline)
        if on_recovery_armed is not None:
            on_recovery_armed()
        trail = Trail(root / 'startup.jsonl', expected_identity)
        trail.emit('recovery-armed', pid=recovery.pid, deadline_monotonic=recovery.deadline,
                   startup_claim_sha256=recovery.claim_sha256)
        reader_fd, writer_fd = os.pipe()
        observer_pid = os.fork()
        if observer_pid == 0:
            os.close(reader_fd)
            recovery.close(reap=False)  # A dead coordinator must cause control-pipe EOF.
            trail.close()
            os.setsid()
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                signal.signal(signum, capture.interrupted)
            try:
                observer_job(root / 'capture', lambda value: notify(writer_fd, value))
            except BaseException:
                os.close(writer_fd)
                os._exit(74)
            os.close(writer_fd)
            os._exit(0)
        os.close(writer_fd)
        writer_fd = None
        ready = receive(reader_fd, admission_deadline)
        capture.keys(ready, 'format baseline_sha256 baseline_completed_ns ready_ns deadline_ns observer_pid')
        capture.integer(ready['deadline_ns'])
        capture.require(ready.get('observer_pid') == observer_pid, 'startup-worker-identity')
        os.set_blocking(reader_fd, False)

        def running():
            nonlocal observer_reaped
            recovery.check()
            if not observer_reaped:
                observer_reaped = os.waitpid(observer_pid, os.WNOHANG)[0] == observer_pid
            capture.require(not observer_reaped, 'startup-observer-ended')
            readable, _, _ = select.select([reader_fd], [], [], 0)
            capture.require(not readable, 'startup-observer-ended')
            capture.require(time.monotonic_ns() < ready['deadline_ns'], 'startup-late-baseline')
            capture.require(not any((root / 'capture' / name).exists() for name in
                                    ('failure.started', 'observer.trigger.json', 'observer.json')),
                            'startup-observer-ended')

        running()
        baseline_hash = baseline_admission(root / 'capture', ready, spec,
                                           expected_identity, current_identity)
        first_boundary = boundary()
        capture.keys(first_boundary, 'framebuffer_id held panel_open')
        first_boundary = dict(first_boundary)
        capture.require(type(first_boundary['framebuffer_id']) is int
                        and first_boundary['framebuffer_id'] > 0
                        and first_boundary['held'] is True and first_boundary['panel_open'] is False,
                        'startup-panel-boundary')
        trail.emit('admitted', baseline_sha256=baseline_hash, ready=ready,
                   boundary=first_boundary)

        def prerequisite(released=False, monitored=False):
            # Once release is admitted, first-report collection/observer exit
            # must not replace the monitor's existing crash thresholds. Before
            # that boundary, an ended observer still refuses any new workload.
            (recovery.check if released else running)()
            identity_matches(current_identity, expected_identity, spec)
            current = boundary()
            capture.keys(current, 'framebuffer_id held panel_open')
            capture.require(type(current['framebuffer_id']) is int
                            and current['framebuffer_id'] == first_boundary['framebuffer_id']
                            and type(current['held']) is bool and type(current['panel_open']) is bool,
                            'startup-panel-boundary')
            if released:
                capture.require(current['held'] is False
                                and (not monitored or current['panel_open'] is True),
                                'startup-panel-boundary')
            else:
                capture.require(current == first_boundary, 'startup-panel-boundary')
            capture.require(hashlib.sha256(capture.read_file(root / 'capture/baseline.json')).hexdigest()
                            == baseline_hash, 'startup-baseline-changed')
            (recovery.check if released else running)()

        for role, command in stages.items():
            command.check()
            prerequisite(released=role == 'monitor')
            trail.emit('stage-request', role=role, baseline_sha256=baseline_hash)
            status = bounded_stage(command, root, role,
                                   min(time.monotonic() + stage_timeouts[role], recovery.deadline),
                                   recovery.check if role in ('release', 'monitor') else running,
                                   stage_children)
            trail.emit('stage-returned', role=role, returncode=status)
            capture.require(status == 0, 'startup-stage-failed')
            prerequisite(released=role in ('release', 'monitor'), monitored=role == 'monitor')
        recovery.dismiss(time.monotonic() + admission_seconds)
        result = {'format': 1, 'outcome': 'reviewed-stages-returned',
                  'baseline_sha256': baseline_hash, 'observer_pid': observer_pid,
                  'recovery_pid': recovery.pid, 'hardware_or_desktop_validated': False}
        trail.emit('monitor-completed', baseline_sha256=baseline_hash)
        capture.publish_json(root / 'startup.json', result)
        return result
    except BaseException as exc:
        if recovery is not None:
            recovery.request()
        try:
            capture.publish_json(root / 'startup-failure.json', {
                'format': 1, 'code': str(exc) if isinstance(exc, capture.CaptureError) else 'input-or-io',
                'recovery_pid': None if recovery is None else recovery.pid,
                'observer_pid': observer_pid, 'monotonic_ns': time.monotonic_ns()})
        except (OSError, capture.CaptureError):
            pass  # Never hold up the independent recovery owner for evidence.
        raise
    finally:
        # Recovery never waits for these signals, exits or kernel calls. A
        # terminated process is not proof an in-flight IOKit method was cancelled.
        signals = []
        for child in stage_children:
            if child.poll() is None:
                signals.append({'pid': child.pid, 'group': True,
                                'signal_errno': stop_child(child.pid, group=True)})
        if observer_pid is not None and not observer_reaped:
            signals.append({'pid': observer_pid, 'group': False,
                            'signal_errno': stop_child(observer_pid)})
        # Best-effort nonblocking reap only; retained PIDs belong to the caller
        # if still running. No claim of kernel-method cancellation is made.
        for child in stage_children:
            if child.poll() is None:
                _OWNED_PROCESSES[child.pid] = child
        if observer_pid is not None and not observer_reaped:
            if os.waitpid(observer_pid, os.WNOHANG)[0] == 0:
                _OWNED_PIDS.add(observer_pid)
        if reader_fd is not None:
            os.close(reader_fd)
        if writer_fd is not None:
            os.close(writer_fd)
        if recovery is not None:
            recovery.close()
        if trail is not None:
            trail.close()
        try:
            capture.publish_json(root / 'cleanup.json', {
                'format': 1, 'signal_attempts': signals, 'kernel_cancellation_verified': False})
        except (OSError, capture.CaptureError):
            pass
