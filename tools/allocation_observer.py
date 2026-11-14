#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Observe new crash-report files in an independent process; never invoke recovery."""
import argparse
import hashlib
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import time

import allocation_capture as capture

MAX_ENTRIES = 4096
MAX_EVENTS = 64
MAX_SECONDS = 300


class ReportWatch:
    """macOS vnode notifications and bounded scans; no report contents are read."""

    def __init__(self, path):
        self.fd = None
        self.queue = None
        self.path = capture.checked_path(path)
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(self.fd)
            capture.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                            and not info.st_mode & 0o002, 'report-directory')
            self.identity = (info.st_dev, info.st_ino)
            self.queue = select.kqueue()
            self.invalid = select.KQ_NOTE_RENAME | select.KQ_NOTE_DELETE | select.KQ_NOTE_REVOKE
            change = select.kevent(self.fd, filter=select.KQ_FILTER_VNODE,
                                   flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                                   fflags=select.KQ_NOTE_WRITE | self.invalid)
            self.queue.control([change], 0, 0)
        except BaseException:
            self.close()
            raise

    def check(self):
        info = self.path.lstat()
        capture.require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == self.identity
                        and info.st_uid == os.geteuid() and not info.st_mode & 0o002,
                        'report-directory-changed')

    def scan(self):
        self.check()
        result = {}
        with os.scandir(self.fd) as entries:
            for count, entry in enumerate(entries, 1):
                capture.require(count <= MAX_ENTRIES, 'report-entry-limit')
                if not (entry.name.startswith(('WindowServer-', 'WindowServer_'))
                        and entry.name.endswith(('.ips', '.spin'))):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue  # A report removed during this scan supplies no event evidence.
                if stat.S_ISREG(info.st_mode):
                    result[entry.name] = (info.st_dev, info.st_ino)
        self.check()
        return result

    def wait(self, seconds):
        capture.require(0 < seconds <= MAX_SECONDS, 'watch-deadline')
        events = self.queue.control(None, 1, seconds)
        self.check()
        for event in events:
            capture.require(event.ident == self.fd and not event.flags & select.KQ_EV_ERROR
                            and not event.fflags & self.invalid, 'report-watch-event')
        return bool(events)

    def close(self):
        if self.queue is not None:
            self.queue.close()
            self.queue = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def observe(reports, out, reader, digest, build, image, window_seconds,
            watch_factory=ReportWatch, baseline=capture.begin, failure=capture.finish,
            clock=time.monotonic, on_ready=None):
    capture.host_check()
    capture.require(type(window_seconds) is int and 1 <= window_seconds <= MAX_SECONDS, 'watch-window')
    deadline = clock() + window_seconds
    watcher = watch_factory(reports)
    try:
        initial = watcher.scan()  # Already armed; post-baseline scan covers persistent arrivals during baseline.
        baseline(out, reader, digest, build, image)
        root = capture.directory(out)
        baseline_completed = clock()
        started = {'format': 1, 'reports_directory': str(reports), 'initial_report_count': len(initial),
                   'window_seconds': window_seconds, 'deadline_monotonic': deadline,
                   'baseline_sha256': hashlib.sha256(capture.read_file(root / 'baseline.json')).hexdigest()}
        capture.write_json(root / 'observer.started', started)
        capture.sync_directory(root)

        def complete(outcome, events, failure_hash=None):
            result = {'format': 1, 'outcome': outcome, 'notifications': events,
                      'baseline_sha256': started['baseline_sha256']}
            if failure_hash is not None:
                result['failure_sha256'] = failure_hash
            capture.publish_json(root / 'observer.json', result)
            capture.sync_directory(root)
            return result

        # One immediate scan and at most 64 notification-driven rescans. No polling or snapshot retry.
        for notifications in range(MAX_EVENTS + 1):
            remaining = deadline - clock()
            if remaining <= 0:
                return complete('window-expired', notifications)
            current = watcher.scan()
            if clock() >= deadline:
                return complete('window-expired', notifications)
            added = sorted(name for name, identity in current.items() if initial.get(name) != identity)
            if added:
                # Multiple coalesced reports are one trigger, with a deterministic representative.
                name = added[0]
                trigger = {'format': 1, 'name': name, 'file_identity': list(current[name]),
                           'new_candidate_count': len(added), 'notifications': notifications}
                capture.publish_json(root / 'observer.trigger.json', trigger)
                capture.sync_directory(root)
                if clock() >= deadline:
                    return complete('window-expired', notifications)
                failure(root)  # Ordinary one-attempt collector; no recovery callback exists.
                raw = capture.read_file(root / 'failure.json')
                return complete('captured', notifications, hashlib.sha256(raw).hexdigest())
            if notifications == 0 and on_ready is not None:
                # A startup coordinator may validate this receipt, not observer.started.
                # The first post-baseline scan above excludes reports already discovered
                # during baseline. The callback must not wait for startup or recovery.
                ready_at = clock()
                if ready_at >= deadline:
                    return complete('window-expired', notifications)
                on_ready({'format': 1, 'baseline_sha256': started['baseline_sha256'],
                          'baseline_completed_ns': int(baseline_completed * 1_000_000_000),
                          'ready_ns': int(ready_at * 1_000_000_000),
                          'deadline_ns': int(deadline * 1_000_000_000),
                          'observer_pid': os.getpid()})
            if notifications == MAX_EVENTS:
                return complete('event-limit', notifications)
            remaining = deadline - clock()
            if remaining <= 0 or not watcher.wait(remaining):
                return complete('window-expired', notifications)
        raise capture.CaptureError('observer-state')
    finally:
        watcher.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--reader', required=True, type=Path)
    parser.add_argument('--reader-sha256', required=True)
    parser.add_argument('--expected-build', required=True, type=int)
    parser.add_argument('--expected-image-uuid', required=True)
    parser.add_argument('--window-seconds', required=True, type=int)
    args = parser.parse_args()
    for name in ('SIGINT', 'SIGTERM', 'SIGHUP'):
        signum = getattr(signal, name, None)
        if signum is not None:
            signal.signal(signum, capture.interrupted)
    try:
        result = observe(args.reports, args.out, args.reader, args.reader_sha256,
                         args.expected_build, args.expected_image_uuid, args.window_seconds)
    except (capture.CaptureError, OSError, subprocess.SubprocessError, ValueError, TypeError,
            KeyError, OverflowError, capture.plistlib.InvalidFileException,
            capture.ExpatError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, capture.CaptureError) else 'input-or-io'
        print('allocation-observer refused: ' + code + '; keep partial output private', file=sys.stderr)
        return 74
    print('Private allocation observer ended: ' + result['outcome'])
    return 0 if result['outcome'] == 'captured' else 75


if __name__ == '__main__':
    raise SystemExit(main())
