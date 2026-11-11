"""Generate a native-2x display override in build/; never install or change a mode.

Use the display vendor/product IDs and physical GOP size read on the target.
Only a render size equal to the firmware raster is allowed: PhxAMDFB has no scaler.
"""
import argparse
import json
from pathlib import Path
import plistlib
import struct

ROOT = Path(__file__).resolve().parents[1]


def identifier(text):
    try:
        value = int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError("use a decimal or 0x-prefixed display ID") from None
    # IODisplayVendorID/ProductID are UInt32, not just the 16-bit EDID fields.
    # With no EDID, IOGraphics uses the four-character vendor 'unkn'.
    if not 0 <= value <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("display ID must fit uint32; read it on the target")
    return value


def native_size(text):
    try:
        width, height = map(int, text.lower().split("x"))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError("use the actual pixel raster, e.g. 2560x1600") from None
    if not (640 <= width <= 16384 and 400 <= height <= 16384) or width % 2 or height % 2:
        raise argparse.ArgumentTypeError("native 2x requires even dimensions in 640..16384 x 400..16384")
    return width, height


def display_override(vendor, product, width, height):
    # A 12-byte scale-resolutions record: big-endian *backing* pixels and
    # resolution flag 1 (HiDPI). Logical dimensions must NOT go in this record.
    native_size(f"{width}x{height}")
    identifier(str(vendor))
    identifier(str(product))
    return {
        "DisplayVendorID": vendor,
        "DisplayProductID": product,
        "scale-resolutions": [struct.pack(">III", width, height, 1)],
    }


def generate(out, vendor, product, size):
    out = Path(out).resolve()
    build = ROOT.resolve() / "build"
    if build.resolve() != build or not out.is_relative_to(build) or out == build:
        raise ValueError("output must be a fresh subdirectory of this repository's build/; no install mode")
    override = display_override(vendor, product, *size)
    # Atomic mkdir refuses existing outputs, including symlinks to other trees.
    out.mkdir(parents=True, exist_ok=False)
    relative = f"DisplayVendorID-{vendor:x}/DisplayProductID-{product:x}"
    target = out / relative
    target.parent.mkdir()
    target.write_bytes(plistlib.dumps(override, sort_keys=True))
    report = {
        "schema": 1, "native_pixels": list(size),
        "logical_points": [size[0] // 2, size[1] // 2],
        "override": relative, "boot_argument": "phxfbhires=1",
        "resampling_supported": False, "hardware_tested": False,
        "installed": False, "mode_changed": False,
    }
    (out / "plan.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=identifier, required=True)
    parser.add_argument("--product", type=identifier, required=True)
    parser.add_argument("--native", type=native_size, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = generate(args.out, args.vendor, args.product, args.native)
    except (ValueError, OSError) as error:
        parser.exit(1, f"refused: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
