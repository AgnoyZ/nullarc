"""Prepare an explicit legacy-tool DeviceProperty offline; never install or initialize hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import struct

from phx_edid import device_path

ROOT = Path(__file__).resolve().parents[1]
PROPERTY = "phx-legacy-boot"
FIELDS = ("mc_base", "physical_base", "vram_bytes", "aperture_bytes", "console_offset", "console_bytes",
          "ring_offset", "tmr_offset", "tmr_capacity", "staging_offset", "staging_capacity")
U64_MAX = (1 << 64) - 1


def uint64(value):
    if isinstance(value, str) and re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", value):
        value = int(value, 16 if value.lower().startswith("0x") else 10)
    if type(value) is not int or not 0 <= value <= U64_MAX:
        raise ValueError("all fields must be unsigned 64-bit integers or decimal/hex strings")
    return value


def span(offset, size, limit):
    return 0 < size <= limit and offset <= limit - size


def disjoint(a, a_size, b, b_size):
    return a_size <= b - a if a <= b else b_size <= a - b


def encode(profile):
    if not isinstance(profile, dict) or set(profile) != set(FIELDS):
        raise ValueError("supply exactly these fields: " + ", ".join(FIELDS))
    p = {key: uint64(profile[key]) for key in FIELDS}
    mc, physical, vram, aperture = (p[k] for k in FIELDS[:4])
    if any(p[k] & 4095 for k in FIELDS) or not all((mc, physical, vram, aperture)):
        raise ValueError("all values must be page-aligned, with nonzero bases and extents")
    if vram - 1 > U64_MAX - mc or vram - 1 > U64_MAX - physical:
        raise ValueError("VRAM address overflow")
    if p["tmr_capacity"] > (1 << 32) - 1 or p["staging_capacity"] > 16 * 1024 * 1024:
        raise ValueError("TMR or staging capacity exceeds the driver contract")
    if (mc + p["tmr_offset"]) & 0xfffff or (physical + p["tmr_offset"]) & 0xfffff:
        raise ValueError("both TMR addresses require 1 MiB alignment")
    regions = ((p["ring_offset"], 0x9000), (p["tmr_offset"], p["tmr_capacity"]),
               (p["staging_offset"], p["staging_capacity"]), (p["console_offset"], p["console_bytes"]))
    for i, (offset, size) in enumerate(regions):
        if not span(offset, size, min(vram, aperture)):
            raise ValueError("all regions must fit VRAM and BAR0")
        for other, other_size in regions[:i]:
            if not disjoint(offset, size, other, other_size):
                raise ValueError("PSP and declared console regions must be disjoint")
    return struct.pack("<16Q", 1, 1, mc, physical, vram, aperture, p["console_offset"], p["console_bytes"],
                       1, p["ring_offset"], p["tmr_offset"], p["tmr_capacity"],
                       p["staging_offset"], p["staging_capacity"], 0, 0)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def read_profile(path):
    with Path(path).open("rb") as stream:
        data = stream.read(8193)
    if len(data) > 8192:
        raise ValueError("profile input exceeds 8192 bytes")
    return json.loads(data, object_pairs_hook=unique_object)


def prepare(source, out, gpu_path):
    data = encode(read_profile(source))
    try:
        gpu_path = device_path(gpu_path)
    except argparse.ArgumentTypeError as exc:
        raise ValueError(str(exc)) from exc
    build = ROOT / "build"
    resolved_build = build.resolve()
    out = Path(out).resolve()
    if resolved_build != ROOT.resolve() / "build" or out == resolved_build or not out.is_relative_to(resolved_build):
        raise ValueError("output must be a fresh subdirectory of this repository's build/")
    if out.exists():
        raise FileExistsError("output already exists; refusing to overwrite it")
    fragment = {"DeviceProperties": {"Add": {gpu_path: {PROPERTY: data}}}}
    plan = {"property": PROPERTY, "device_path": gpu_path, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "hardware_tested": False,
            "installed": False, "memory_reserved": False,
            "note": "Operator-supplied numeric layout; no hardware discovery or ownership proof. Not a complete config.plist."}
    out.mkdir(parents=True)
    (out / "DeviceProperties.plist").write_bytes(plistlib.dumps(fragment, sort_keys=False))
    (out / "legacy-boot.bin").write_bytes(data)
    (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="reviewed per-machine JSON; no default addresses")
    parser.add_argument("--gpu-path", type=device_path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.input, args.out, args.gpu_path)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
