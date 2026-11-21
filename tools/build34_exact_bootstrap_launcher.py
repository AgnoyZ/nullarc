# SPDX-License-Identifier: MIT
"""Derive the launcher paired with checked build34 MES bootstrap (source only)."""

from build34_exact_submit import once


LEGACY = '''MC=1 CS=1 ADOPT=1 GFX=1 AG=1 bash $G/full.sh kiqsched | grep -E "^compute:|^gfx:|adopt"
$G/phxctl/mesboot claim
'''

CHECKED = '''# Preserve the initializer's status independently of the diagnostic filter.
if (
    MC=1 CS=1 ADOPT=1 GFX=1 AG=1 /bin/bash "$G/full.sh" kiqsched | grep -E "^compute:|^gfx:|adopt"
    exit "${PIPESTATUS[0]}"
); then :; else
    rc=$?
    printf 'build34: queue bootstrap failed (status %s); accelerator claim skipped\\n' "$rc" >&2
    exit "$rc"
fi
if "$G/phxctl/mesboot" claim; then :; else
    rc=$?
    printf 'build34: accelerator claim failed (status %s)\\n' "$rc" >&2
    exit "$rc"
fi
'''


def stage_launcher(source):
    if not source.startswith('#!/bin/bash\n'):
        raise ValueError('Expected build34 Bash launcher')
    return once(source, '\n' + LEGACY, '\n' + CHECKED)
