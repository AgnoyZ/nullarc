#!/usr/bin/env python3
"""Durable, one-use decisions for a future isolated build34 startup trial.

The host adapter owns the sealed contract, boot identity, existing admission
deadlines and exact restore/power operations. This module performs journal I/O
only; importing it or running it directly cannot change live boot settings.
"""

from contextlib import contextmanager
import fcntl
import json
import os
import re
import stat
import time


STARTUP_LIMIT_SECONDS = 300
POLL_SECONDS = 1


class StartupRecovery:
    def __init__(self, journal):
        self.journal = os.fspath(journal)

    @staticmethod
    def _token(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            raise ValueError("invalid startup journal identity")
        return value

    @staticmethod
    def _private(fd, check_type):
        info = os.fstat(fd)
        if (info.st_uid != os.geteuid() or info.st_mode & 0o077
                or not check_type(info.st_mode)
                or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
            raise ValueError("unsafe startup recovery journal")

    @contextmanager
    def _locked(self):
        directory = os.open(self.journal, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self._private(directory, stat.S_ISDIR)
            lock = os.open("lock", os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                           0o600, dir_fd=directory)
            try:
                self._private(lock, stat.S_ISREG)
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield directory
            finally:
                os.close(lock)
        finally:
            os.close(directory)

    @classmethod
    def _read(cls, directory, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as handle:
            cls._private(handle.fileno(), stat.S_ISREG)
            state = handle.read(4097)
        if len(state) > 4096:
            raise ValueError("oversize startup recovery record")
        state = json.loads(state)
        if not isinstance(state, dict):
            raise ValueError("invalid startup recovery record")
        return state

    @staticmethod
    def _put(directory, name, value):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)

    def prepare(self, current_boot, *, permit_recovery_restart=False):
        """Record the exact preparation boot before the single trial request."""
        boot = self._token(current_boot)
        if type(permit_recovery_restart) is not bool:
            raise ValueError("recovery restart permission must be boolean")
        with self._locked() as directory:
            self._put(directory, "prepared.json", {"boot": boot,
                       "permit_recovery_restart": permit_recovery_restart})

    def begin_trial(self, current_boot):
        """Bind this scope to the first eligible new boot; reject later boots.

        Call only after verifying the staged scope's trial request and the new
        boot's relation to that request. Multiple startup workers in that boot
        may use this method; they share the same terminal decision.
        """
        boot = self._token(current_boot)
        with self._locked() as directory:
            prepared = self._read(directory, "prepared.json")
            if (not prepared or prepared["boot"] == boot
                    or self._read(directory, "outcome.json") is not None):
                return False
            trial = self._read(directory, "trial.json")
            if trial is None:
                self._put(directory, "trial.json", {"boot": boot})
                return True
            return trial == {"boot": boot}

    def _decide(self, current_boot, decision):
        boot = self._token(current_boot)
        with self._locked() as directory:
            if self._read(directory, "trial.json") != {"boot": boot}:
                return None
            if self._read(directory, "outcome.json") is not None:
                return None
            prepared = self._read(directory, "prepared.json")
            if (prepared is None or prepared["boot"] == boot
                    or type(prepared["permit_recovery_restart"]) is not bool):
                raise ValueError("invalid startup recovery scope")
            self._put(directory, "outcome.json", {"boot": boot, **decision})
            return prepared

    def accept_startup(self, current_boot):
        """Close recovery before any pressure probe or post-startup work."""
        return self._decide(current_boot, {"decision": "accepted"}) is not None

    def startup_accepted(self, current_boot):
        """Check the same-boot decision from a separate pressure observer."""
        boot = self._token(current_boot)
        with self._locked() as directory:
            return (self._read(directory, "trial.json") == {"boot": boot}
                    and self._read(directory, "outcome.json") == {"boot": boot, "decision": "accepted"})

    def recover(self, current_boot, *, reason, quiesce, restore, verify,
                prepare_restart, request_restart):
        """Return false if this failure cannot claim recovery for this boot.

        Call from the existing startup admission failure or deadline path.
        Quiesce must confirm the exact trial workers stopped (no pending probe).
        Restore must return the accepted files/jobs and retire the trial jobs.
        Verify must perform an independent full readback. Prepare_restart must
        commit and verify the known-good panel flag and rule out other pending
        power requests. Any failed check, exception or uncertain request
        consumes the attempt. There is no second power call or old recovery.
        """
        reason = self._token(reason)
        prepared = self._decide(current_boot, {"decision": "rollback", "reason": reason})
        if prepared is None:
            return False
        if quiesce() is not True:
            raise RuntimeError("could not verify that the trial stopped")
        restore()
        if verify() is not True:
            raise RuntimeError("accepted startup route failed independent readback")
        if not prepared["permit_recovery_restart"]:
            return True
        if prepare_restart() is not True:
            raise RuntimeError("accepted startup route not ready for restart")
        with self._locked() as directory:
            self._put(directory, "recovery-restart.intent", {"boot": current_boot, "requests": 1})
        request_restart()
        return True

    def watch(self, current_boot, *, read_admission, recovery_actions,
              monotonic=time.monotonic, sleep=time.sleep):
        """Run one startup-only watcher from the fresh boot's launchd job.

        The existing 45/150/300-second gates remain authoritative. The adapter
        must use bounded I/O and return None for pending, True only after full
        current-boot admission, or a short reason for a confirmed failure. The
        watcher does not sample or dispatch any GPU work. Its result separates
        an accepted startup, an independently verified rollback on disk and a
        scope already closed or ineligible for the current boot.
        """
        deadline = monotonic() + STARTUP_LIMIT_SECONDS
        if not self.begin_trial(current_boot):
            return "closed"
        while True:
            if monotonic() >= deadline:
                reason = "startup-deadline"
                break
            status = read_admission()
            remaining = deadline - monotonic()
            if remaining <= 0:
                reason = "startup-deadline"
                break
            if status is True:
                return "accepted" if self.accept_startup(current_boot) else "closed"
            if status is not None:
                reason = self._token(status)
                break
            sleep(min(remaining, POLL_SECONDS))
        restored = self.recover(current_boot, reason=reason, **recovery_actions)
        return "rolled-back-on-disk" if restored else "closed"
