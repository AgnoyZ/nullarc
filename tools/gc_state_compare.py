#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Compare private fixed GC observations using files only; never access hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_BYTES = 65536
STAGES = ("baseline", "psp", "firmware", "power")
# Independent numeric contract for gc_state_observe.c, in its exact read order.
REGISTERS = (
    ("PSP_INITIALIZATION_STATUS", 0x16061), ("RCC_CONFIG_MEMSIZE", 0x0DE3),
    ("GRBM_STATUS", 0x2004), ("GRBM_STATUS2", 0x2002), ("GB_ADDR_CONFIG", 0x263E),
    ("CP_STAT", 0x21A0), ("GRBM_GFX_CNTL", 0xA900), ("CP_MES_CNTL", 0xC807),
    ("RLC_CNTL", 0xEC00), ("RLC_STAT", 0xEC04), ("RLC_PG_CNTL", 0xEC43),
    ("RLC_CGCG_CGLS_CTRL", 0xEC49), ("RLC_GPM_STAT", 0xEE6B),
    ("RLC_RLCS_BOOTLOAD_STATUS_GC_11_0_1", 0xEE7E), ("GFX_IMU_SCRATCH_0", 0xE068),
    ("GRBM_SOFT_RESET", 0x2008), ("CP_ME_CNTL", 0xA803),
    ("CP_SOFT_RESET_CNTL", 0x31B9), ("GRBM_CNTL", 0x2000),
)
# Field names/masks reviewed against the pinned GC 11.0.0 header, not recipes.
# Unknown bits are retained separately; no value is classified as a cause/fix.
FIELDS = {
    "GRBM_CNTL": {"READ_TIMEOUT": (0, 0xFF)},
    "CP_ME_CNTL": {"CE_HALT": (24, 0x01000000), "PFP_HALT": (26, 0x04000000),
                   "ME_HALT": (28, 0x10000000)},
    "CP_MES_CNTL": {"MES_PIPE0_RESET": (16, 0x00010000), "MES_PIPE1_RESET": (17, 0x00020000),
                    "MES_PIPE0_ACTIVE": (26, 0x04000000), "MES_PIPE1_ACTIVE": (27, 0x08000000),
                    "MES_HALT": (30, 0x40000000)},
    "GRBM_SOFT_RESET": {
        "SOFT_RESET_CP": (0, 0x1), "SOFT_RESET_RLC": (2, 0x4),
        "SOFT_RESET_UTCL2": (15, 0x8000), "SOFT_RESET_GFX": (16, 0x10000),
        "SOFT_RESET_CPF": (17, 0x20000), "SOFT_RESET_CPC": (18, 0x40000),
        "SOFT_RESET_CPG": (19, 0x80000), "SOFT_RESET_CAC": (20, 0x100000),
        "SOFT_RESET_EA": (22, 0x400000), "SOFT_RESET_SDMA0": (23, 0x800000),
        "SOFT_RESET_SDMA1": (24, 0x1000000),
    },
    "CP_SOFT_RESET_CNTL": {
        "CMP_ONLY_SOFT_RESET": (0, 0x1), "GFX_ONLY_SOFT_RESET": (1, 0x2),
        "CMP_HQD_REG_RESET": (2, 0x4), "CMP_INTR_REG_RESET": (3, 0x8),
        "CMP_HQD_QUEUE_DOORBELL_RESET": (4, 0x10), "GFX_RB_DOORBELL_RESET": (5, 0x20),
        "GFX_INTR_REG_RESET": (6, 0x40), "GFX_HQD_REG_RESET": (7, 0x80),
    },
}


class ObservationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ObservationError(message)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, "duplicate JSON key")
        result[name] = value
    return result


def read_json(path):
    """Bounded regular-file read; reject links/FIFOs before consuming contents."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES, "invalid input file")
        chunks, remaining = [], MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        require(len(raw) <= MAX_BYTES, "input exceeds byte limit")
    finally:
        os.close(fd)
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=lambda _: require(False, "nonfinite JSON number"))
    return value, hashlib.sha256(raw).hexdigest()


def exact_keys(value, keys, message):
    require(type(value) is dict and set(value) == set(keys), message)


def validate_observation(data, stage):
    require(stage in STAGES, "unknown phase")
    exact_keys(data, ("schema", "observation_only", "phase", "GPU_register_writes", "registers"),
               "unexpected observation schema")
    require(type(data["schema"]) is int and data["schema"] == 1 and data["observation_only"] is True
            and type(data["GPU_register_writes"]) is int and data["GPU_register_writes"] == 0,
            "not a fixed read-only observation")
    require(data["phase"] == ("configured" if stage == "baseline" else "tmr-ready"),
            "observation phase mismatch")
    rows = data["registers"]
    require(type(rows) is list and len(rows) == len(REGISTERS), "wrong fixed register count")
    values = {}
    for row, (name, index) in zip(rows, REGISTERS):
        exact_keys(row, ("name", "index", "value"), "unexpected register schema")
        require(row["name"] == name and type(row["index"]) is int and row["index"] == index,
                "fixed register identity/order mismatch")
        require(type(row["value"]) is int and 0 <= row["value"] < 0xFFFFFFFF,
                "invalid register observation")
        values[name] = row["value"]
    require(values["PSP_INITIALIZATION_STATUS"] & 0x80000000, "PSP control not ready")
    require(128 <= values["RCC_CONFIG_MEMSIZE"] <= 1 << 20, "invalid memory-size control")
    return values


def decode_fields(values):
    result = {}
    for name, fields in FIELDS.items():
        mask = 0
        decoded = {}
        for field, (shift, bits) in fields.items():
            mask |= bits
            decoded[field] = (values[name] & bits) >> shift
        result[name] = {"fields": decoded, "undecoded_bits": values[name] & (~mask & 0xFFFFFFFF)}
    return result


def compare(manifest_path):
    manifest_path = Path(manifest_path)
    manifest, manifest_sha = read_json(manifest_path)
    exact_keys(manifest, ("schema", "observations"), "unexpected manifest schema")
    require(type(manifest["schema"]) is int and manifest["schema"] == 1, "unsupported manifest")
    observations = manifest["observations"]
    require(type(observations) is list and 1 <= len(observations) <= len(STAGES), "invalid phase count")
    phases, prior, size, names = [], None, None, set()
    for ordinal, receipt in enumerate(observations):
        exact_keys(receipt, ("stage", "file", "sha256", "exit_status"), "unexpected receipt schema")
        stage = STAGES[ordinal]
        require(receipt["stage"] == stage, "phases must be an unrepeated baseline/psp/firmware/power prefix")
        require(type(receipt["exit_status"]) is int and receipt["exit_status"] == 0,
                "caller did not report a successful collector exit")
        name, expected = receipt["file"], receipt["sha256"]
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.partial", name)
                and name not in names, "invalid or repeated observation filename")
        require(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected), "invalid digest")
        names.add(name)
        data, actual = read_json(manifest_path.parent / name)
        require(actual == expected, "observation bytes differ from receipt")
        values = validate_observation(data, stage)
        if size is None:
            size = values["RCC_CONFIG_MEMSIZE"]
        require(values["RCC_CONFIG_MEMSIZE"] == size, "memory-size control changed between phases")
        changes = [] if prior is None else [
            {"name": name, "before": prior[name], "after": values[name], "xor": prior[name] ^ values[name]}
            for name, _ in REGISTERS if prior[name] != values[name]
        ]
        phases.append({"stage": stage, "observation_sha256": actual, "values": values,
                       "decoded": decode_fields(values), "changes_from_previous": changes,
                       "CP_RLC_completion_bits_observed": values["CP_STAT"] == 0 and
                       bool(values["RLC_RLCS_BOOTLOAD_STATUS_GC_11_0_1"] & 0x80000000)})
        prior = values
    return {"schema": 1, "file_comparison_only": True, "GPU_access_performed": False,
            "manifest_sha256": manifest_sha, "phase_order_and_exit_status_are_caller_asserted": True,
            "boot_and_capture_provenance_verified": False, "hardware_readiness_proven": False,
            "physical_cause_established": False, "complete_four_phase_input": len(phases) == len(STAGES),
            "phases": phases}


def write_private_report(path, report):
    path = Path(path)
    require(path.is_absolute() and path.name.endswith(".partial"), "output must be absolute and end in .partial")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare(args.manifest)
        write_private_report(args.output, report)
    except (OSError, ValueError, RecursionError):
        print("GC comparison refused: invalid/unreadable input or unavailable private output; no hardware access",
              file=sys.stderr)
        return 1
    print("GC file comparison complete: %d phases; hardware readiness and cause unproven" % len(report["phases"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
