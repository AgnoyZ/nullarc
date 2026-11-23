import argparse
import hashlib
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PASS = b"PHX34_PREBOOT_GUEST_PASS"
FAIL = re.compile(rb"PHX34_PREBOOT_GUEST_FAIL ([0-9]{2})")
CAPTURE_PREFIX = b"PHX34_PREBOOT_CAPTURE_V2 "
VIRTIO_CAPTURE = CAPTURE_PREFIX + b"FV 83dd3b39-7caf-4fac-a542-e050b767e3a7"


def regular_file(value):
    path = Path(value).resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError("expected a regular file")
    return path


def boot_guest(command, expected):
    result = bytearray()
    deadline = time.monotonic() + 30
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL) as guest, selectors.DefaultSelector() as ready:
        ready.register(guest.stdout, selectors.EVENT_READ)
        try:
            while len(result) < 262144:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not ready.select(remaining):
                    break
                chunk = os.read(guest.stdout.fileno(), 4096)
                if not chunk:
                    break
                result.extend(chunk)
                for line in result.split(b"\n")[:-1]:
                    line = line.strip()
                    match = FAIL.fullmatch(line)
                    if match is not None:
                        raise SystemExit(f"UEFI guest check {match[1].decode('ascii')} failed")
                    if line == expected:
                        return
                    if line.startswith(b"PHX34_PREBOOT_CAPTURE_"):
                        raise SystemExit("UEFI guest capture did not match the sealed expected result")
            raise SystemExit("UEFI guest did not report a complete result within the output and time limits")
        finally:
            if guest.poll() is None:
                guest.kill()
            guest.wait(timeout=5)


def run_fixture(args, sources, flags, expected):
    output = ROOT / "build"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build34-preboot-guest-", dir=output) as directory:
        private = Path(directory)
        esp = private / "esp"
        application = esp / "EFI" / "BOOT" / "BOOTX64.EFI"
        application.parent.mkdir(parents=True)
        code = private / "code.fd"
        variables = private / "vars.fd"
        shutil.copyfile(args.uefi_code, code)
        shutil.copyfile(args.uefi_vars, variables)
        objects = []
        for source in ("tools/build34_r3_preboot_pci.c", *sources):
            obj = private / (Path(source).stem + ".obj")
            subprocess.run(["clang", "-target", "x86_64-pc-windows-msvc", "-std=c11", "-O2", "-Wall",
                            "-Wextra", "-Werror", "-fshort-wchar", "-ffreestanding", "-fno-builtin",
                            "-fno-stack-protector", "-isystem", args.edk2_include, "-isystem",
                            args.edk2_include / "X64", "-Itools", *flags, "-c", source, "-o", obj],
                           cwd=ROOT, check=True, timeout=30)
            objects.append(obj)
        subprocess.run([args.linker, "-mi386pep", "--subsystem=10", "--entry=EfiMain", "--image-base=0",
                        "--enable-reloc-section", "--no-insert-timestamp", *objects, "-o", application],
                       check=True, timeout=30)
        digest = hashlib.sha256(application.read_bytes()).hexdigest()
        boot_guest([args.qemu, "-L", args.uefi_code.parent, "-nodefaults", "-machine", "q35,accel=tcg",
                    "-m", "256", "-smp", "1", "-display", "none", "-monitor", "none", "-serial", "stdio",
                    "-nic", "none", "-no-reboot", "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
                    "-drive", f"if=pflash,format=raw,file={variables}", "-drive",
                    f"if=none,id=bootdisk,format=raw,readonly=on,file=fat:ro:{esp}", "-device",
                    "virtio-blk-pci,drive=bootdisk,addr=0x5,disable-modern=on"], expected)
        return digest


def main():
    parser = argparse.ArgumentParser(description="Run the build34 UEFI metadata fixtures inside QEMU TCG only")
    for option in ("qemu", "linker", "uefi-code", "uefi-vars"):
        parser.add_argument(f"--{option}", required=True, type=regular_file)
    parser.add_argument("--edk2-include", required=True, type=lambda value: Path(value).resolve())
    parser.add_argument("--capture", action="store_true", help="exercise the sealed, emulated-target capture entry")
    args = parser.parse_args()
    if not (args.edk2_include / "Uefi.h").is_file():
        parser.error("--edk2-include must be the pinned EDK II MdePkg/Include directory")

    if args.capture:
        sources = ("tools/build34_r3_preboot_capture.c", "tests/build34_r3_preboot_capture_target.c")
        cases = (("capture", 0, 5, VIRTIO_CAPTURE),
                 ("wrong_segment", 1, 5, CAPTURE_PREFIX + b"NO_MAPPING ROOT"),
                 ("missing_endpoint", 0, 6, CAPTURE_PREFIX + b"NOT_FOUND ENDPOINT"))
        for name, segment, device, expected in cases:
            flags = (f"-DPHX34_CAPTURE_FIXTURE_SEGMENT={segment}", f"-DPHX34_CAPTURE_FIXTURE_DEVICE={device}")
            print(f"guest_{name}_sha256={run_fixture(args, sources, flags, expected)}")
        print("PASS isolated UEFI capture, exact Virtio firmware-file locator, wrong segment and missing endpoint")
    else:
        digest = run_fixture(args, ("tests/test_build34_r3_preboot_guest.c",), (), PASS)
        print("PASS isolated UEFI guest attribution, refusal and cleanup (synthetic and emulated PCI)")
        print(f"guest_application_sha256={digest}")


if __name__ == "__main__":
    main()
