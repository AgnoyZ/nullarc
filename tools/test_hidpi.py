"""Execute the real PhxAMDFB mode-information method with fake IOKit, not a GPU."""
import argparse
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def color_methods(source):
    methods = re.findall(r'^    IOReturn (?:setGammaTable|setCLUTWithEntries)\([^\n]*\) override \{[^{}]*\}', source, re.M)
    if len(methods) != 3 or sum('setGammaTable(' in m for m in methods) != 2:
        raise RuntimeError('Expected two gamma overloads and one CLUT callback')
    return '\n'.join(m.replace(' override', '') for m in methods)


def harness():
    source = (ROOT / "src/phxaccel/accel/phxfb.cpp").read_text(encoding="utf-8")
    method = source.split("    IOReturn getInformationForDisplayMode(", 1)[1]
    method = "    IOReturn getInformationForDisplayMode(" + method.split("    UInt64 getPixelFormatsForDisplayMode(", 1)[0]
    method = method.replace(" override", "")
    template = (ROOT / "tests/test_hidpi.cpp").read_text(encoding="utf-8")
    return template.replace("    // ACTUAL_FRAMEBUFFER_METHOD", method).replace(
        "    // ACTUAL_FRAMEBUFFER_COLOR_METHODS", color_methods(source))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="phx-hidpi-") as temporary:
        root = Path(temporary)
        source, binary = root / "hidpi.cpp", root / "hidpi"
        source.write_text(harness(), encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        "-I" + str(ROOT / "src/phxaccel"), str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
