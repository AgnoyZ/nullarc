"""Check real panel EDID or prepare an offline OpenCore property fragment; never install."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 4096
HEADER = bytes.fromhex("00ffffffffffff00")


def native_size(text):
    match = re.fullmatch(r"([0-9]+)x([0-9]+)", text)
    if not match:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT from the current physical boot raster")
    width, height = map(int, match.groups())
    if not 1 <= width <= 16384 or not 1 <= height <= 16384:
        raise argparse.ArgumentTypeError("physical dimensions must be within 1..16384")
    return width, height


def device_path(text):
    if not re.fullmatch(r"PciRoot\(0x[0-9a-fA-F]{1,8}\)(?:/Pci\(0x[0-9a-fA-F]{1,2},0x[0-7]\)){1,12}", text):
        raise argparse.ArgumentTypeError("supply the verified GPU OpenCore PCI path, not a guessed address")
    if any(int(value, 16) > 31 for value in re.findall(r"/Pci\(0x([0-9a-fA-F]+),", text)):
        raise argparse.ArgumentTypeError("PCI device numbers must be within 0..31")
    return text


def validate(data, native=None):
    if not 128 <= len(data) <= MAX_BYTES or len(data) % 128:
        raise ValueError("EDID must contain 1..32 whole 128-byte blocks")
    if data[:8] != HEADER or data[18] != 1 or data[19] > 4:
        raise ValueError("unsupported EDID header/version (require EDID 1.0..1.4)")
    if len(data) // 128 != data[126] + 1:
        raise ValueError("extension count does not match input length")
    if any(sum(data[i:i + 128]) % 256 for i in range(0, len(data), 128)):
        raise ValueError("EDID checksum failure; do not silently repair a damaged dump")
    if native is not None:
        rasters = []
        for off in (54, 72, 90, 108):
            d = data[off:off + 18]
            if (d[0] or d[1]) and not d[17] & 0x80:
                rasters.append((d[2] | ((d[4] & 0xF0) << 4), d[5] | ((d[7] & 0xF0) << 4)))
        if tuple(native) not in rasters:
            raise ValueError("no progressive base-block DTD matches the current physical raster")
    return data


def read_edid(path, native=None, trim_zero_padding=False):
    # Bound the read before trusting any byte from an arbitrary file.
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("input exceeds the 4096-byte EDID limit")
    if trim_zero_padding and len(data) >= 128:
        size = (data[126] + 1) * 128
        if len(data) > size:
            if len(data) % 128 or any(data[size:]):
                raise ValueError("only whole all-zero undeclared trailing blocks may be trimmed")
            data = data[:size]
    return validate(data, native)


def prepare(source, out, native, gpu_path, trim_zero_padding=False):
    data = read_edid(source, native, trim_zero_padding)
    gpu_path = device_path(gpu_path)
    build = ROOT / "build"
    resolved_build = build.resolve()
    out = Path(out).resolve()
    # Fail before creating anything if build itself points outside this repository.
    if resolved_build != ROOT.resolve() / "build" or out == resolved_build or not out.is_relative_to(resolved_build):
        raise ValueError("output must be a fresh subdirectory of this repository's build/")
    if out.exists():
        raise FileExistsError("output already exists; refusing to overwrite it")
    fragment = {"DeviceProperties": {"Add": {gpu_path: {"phx-edid": data}}}}
    plan = {
        "property": "phx-edid", "device_path": gpu_path, "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(), "physical_raster": list(native),
        "hardware_read": False, "hardware_tested": False, "installed": False, "mode_changed": False,
        "note": "Operator-supplied real EDID. Merge only this property after review; this is not a complete config.plist.",
    }
    out.mkdir(parents=True)
    (out / "DeviceProperties.plist").write_bytes(plistlib.dumps(fragment, sort_keys=False))
    (out / "edid.bin").write_bytes(data)
    (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("--native", type=native_size, required=name == "prepare")
        command.add_argument("--trim-zero-padding", action="store_true")
        if name == "prepare":
            command.add_argument("--device-path", type=device_path, required=True)
            command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.input, args.out, args.native, args.device_path, args.trim_zero_padding)
        else:
            data = read_edid(args.input, args.native, args.trim_zero_padding)
            result = {"valid": True, "bytes": len(data), "read_only": True, "hardware_read": False}
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
