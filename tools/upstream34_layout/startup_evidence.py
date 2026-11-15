"""Startup-log selection with one fixed boot-time boundary; no hardware APIs."""
import datetime
import re


class StartupLog:
    """Capture boot time once, before polling the original startup log.

    Wall-clock synchronization can move kern.boottime while startup is running.
    Re-reading that boundary can incorrectly discard an already-admitted block.
    The caller must bind this reader to one boot identity, retain that identity
    throughout observation, and create a new reader for a different boot.
    """

    def __init__(self, boot_epoch):
        if type(boot_epoch) is not int:
            raise TypeError("boot epoch must be an integer snapshot")
        self._boot_epoch = boot_epoch

    @property
    def boot_epoch(self):
        return self._boot_epoch

    def select(self, text):
        """Keep the original latest-block and stale-log refusal semantics."""
        block = text.rsplit("== ", 1)[-1]
        match = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) phxboot\n", block)
        if not match:
            return ""
        started = datetime.datetime.fromisoformat(match.group(1)).astimezone().timestamp()
        return block if started >= self._boot_epoch else ""
