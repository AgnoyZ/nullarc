#!/bin/bash
# NOT RUN BY THIS REPOSITORY. The former address-bearing reference recipe is retired.
# Explicit wrapper for the existing checked firmware/power command; see docs/VRAM-LAYOUT-SAFETY.md.
# Requires a reviewed firmware profile, a matching downstream kext, and an external bounded stage runner.
# Run as root. No default regions, sudo prompt, reboot timer or timer cancellation is supplied here.
set -eu
if [ "$#" -ne 6 ]; then
    printf '%s\n' 'usage: bringup5.sh <firmware-dir> <ring-offset> <tmr-offset> <tmr-capacity> <staging-offset> <staging-capacity>' >&2
    printf '%s\n' 'Explicit target-relative regions are required; the reference-machine raw PSP recipe is retired.' >&2
    exit 64
fi
helper="$HOME/gpu/phxctl/phxctl"
if [ ! -f "$helper" ] || [ ! -x "$helper" ]; then
    printf '%s\n' 'The matching checked phxctl helper is missing or not executable; refusing.' >&2
    exit 127
fi
exec "$helper" gfx-power-sequence "$@"
