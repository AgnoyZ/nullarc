"""Execute actual PhxAMDFB EDID methods with IOKit doubles and ASan/UBSan; no GPU."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("loadEdid", "hasDDCConnect", "getDDCBlock", "getAttributeForConnection")


def extract_methods(source):
    result = []
    for name in METHODS:
        matches = list(re.finditer(r"^    (?:void|bool|IOReturn) " + name + r"\(", source, re.M))
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one actual PhxAMDFB method: " + name)
        start = matches[0].start()
        opening = source.index("{", matches[0].end())
        depth = 1
        end = opening + 1
        while depth and end < len(source):
            depth += (source[end] == "{") - (source[end] == "}")
            end += 1
        if depth:
            raise RuntimeError("Unbalanced method body: " + name)
        result.append(source[start:end].replace(" override", ""))
    return "\n".join(result)


def harness():
    source = (ROOT / "src/phxaccel/accel/phxfb.cpp").read_text(encoding="utf-8")
    methods = extract_methods(source)
    template = (ROOT / "tests/test_edid.cpp").read_text(encoding="utf-8")
    marker = "    // ACTUAL_EDID_METHODS"
    if template.count(marker) != 1:
        raise RuntimeError("Expected exactly one fixture insertion marker")
    return template.replace(marker, methods), hashlib.sha256(methods.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    text, digest = harness()
    with tempfile.TemporaryDirectory(prefix="phx-edid-") as temporary:
        root = Path(temporary)
        source, binary = root / "edid.cpp", root / "edid"
        source.write_text(text, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        "-fno-omit-frame-pointer", "-I" + str(ROOT / "src/phxaccel"),
                        str(source), "-o", str(binary)], check=True, timeout=120)
        subprocess.run([str(binary)], check=True, timeout=30)
    print("ACTUAL_EDID_METHODS_SHA256=" + digest)


if __name__ == "__main__":
    main()
