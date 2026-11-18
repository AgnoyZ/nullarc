#!/usr/bin/env python3
"""CPU/filesystem-only checks for a supervised build34 installation's kill switch.

This module neither changes files nor admits GPU execution. The caller must
separately verify the frozen contract, executable identities, successful GPU
evidence, boot configuration, and independent recovery process.
"""

import hashlib
import os
from pathlib import Path
import stat


def kill_switch_required(*, owner_requested_install, installation_started,
                         installation_accepted, recovery_started):
    """Require the baseline OFF marker except after an accepted installation.

    Recovery always returns to the OFF state. A result file alone cannot enable
    an installation that the owner did not request or that never began.
    """
    for value in (owner_requested_install, installation_started,
                  installation_accepted, recovery_started):
        if type(value) is not bool:
            raise ValueError("installation state must contain booleans")
    if installation_accepted and not (owner_requested_install and installation_started):
        raise ValueError("accepted installation lacks authorization or intent")
    return recovery_started or not installation_accepted


def verify_kill_switch(path, expected_sha256, *, required, expected_uid=0):
    """Verify exact baseline marker content or its explicitly expected absence.

    Missing markers remain errors before acceptance and during recovery.
    An unexpected marker, including a dangling symlink, stops enabled operation.
    """
    if type(required) is not bool:
        raise ValueError("required must be a boolean")
    path = Path(path)
    if not required:
        if os.path.lexists(path):
            raise ValueError("kill switch present during enabled operation")
        return
    metadata = path.lstat()  # Preserve FileNotFoundError when OFF is required.
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_uid != expected_uid or metadata.st_mode & 0o022):
        raise ValueError("unsafe kill switch metadata")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("kill switch content changed")
