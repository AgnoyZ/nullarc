# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Pure routing/observation helpers for a separately contained original34 trial.

Importing this module or calling its functions performs no device, process,
installation or reboot operation. A rendered router is not a trial controller.
"""
from pathlib import Path
import re
import shlex

REGISTERS = (0x305D, 0x305C, 0x2004, 0x2002, 0x2087, 0x219F, 0x21A0)
POLICIES = {"control": "mesboot-control", "mec-range": "mesboot-mec-range"}


def parse_registers(text):
    """Require the exact ordered output of original34 phxctl regs, fail closed."""
    if not isinstance(text, str):
        raise ValueError("Register output must be text")
    lines = text.splitlines()
    if len(lines) != len(REGISTERS):
        raise ValueError("Incomplete or unexpected register output")
    values = {}
    for expected, line in zip(REGISTERS, lines):
        match = re.fullmatch(r"0x([0-9a-fA-F]{5}): 0x([0-9a-fA-F]{8})", line)
        if not match or int(match[1], 16) != expected:
            raise ValueError("Wrong register, order or transport diagnostic")
        value = int(match[2], 16)
        if value == 0xFFFFFFFF:
            raise ValueError("All-ones register read is not an observation")
        values[expected] = value
    if values[0x2004] == 0:
        raise ValueError("Zero GRBM status is ambiguous, not idle evidence")
    return values


def observation_summary(samples):
    """Describe measurements without inferring global GPU idle or a repaired IB."""
    if not samples:
        raise ValueError("At least one complete register sample is required")
    for sample in samples:
        if set(sample) != set(REGISTERS) or any(type(value) is not int or not 0 <= value < 0xFFFFFFFF
                                               for value in sample.values()) or not sample[0x2004]:
            raise ValueError("Invalid register sample")
    return {
        "sample_count": len(samples),
        "range_stable": len({(sample[0x305D], sample[0x305C]) for sample in samples}) == 1,
        "proposed_range_present_all_samples": all(sample[0x305D] == 0x450 and sample[0x305C] == 0
                                                  for sample in samples),
        "GRBM_status_stable": len({sample[0x2004] for sample in samples}) == 1,
        "global_GPU_idle_established": False,
        "IB_integrity_established": False,
    }


def render_router(packet, python, controller, policy):
    """Route only gart/mes/kiqsched; preserve the original full.sh environment.

    The external controller must freeze every input and validate boot, image,
    ownership, live independent deadline and recovery before this is executable.
    The common sample precedes KIQ setup, after original GART/MES setup.
    """
    packet = Path(packet)
    python = Path(python)
    if (not packet.is_absolute() or not python.is_absolute() or ".." in packet.parts or
            ".." in python.parts or not isinstance(controller, str) or
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]*\.py", controller) or policy not in POLICIES):
        raise ValueError("Explicit packet, interpreter, controller and policy required")
    for value in (str(packet), str(python)):
        if any(c in value for c in ("\n", "\r", "\0")):
            raise ValueError("Unsafe path")
    original = shlex.quote(str(packet / "mesboot-original"))
    scheduler = shlex.quote(str(packet / POLICIES[policy]))
    sample = " ".join((shlex.quote(str(python)), "-B", "-I",
                       shlex.quote(str(packet / controller)), "sample-before"))
    return ("#!/bin/bash\nset -euo pipefail\n"
            "[ \"$#\" -eq 1 ] || exit 64\n"
            "case \"$1\" in\n"
            "  gart|mes) exec " + original + " \"$1\" ;;\n"
            "  kiqsched) " + sample + "\n"
            "    exec " + scheduler + " \"$1\" ;;\n"
            "  *) exit 64 ;;\nesac\n")
