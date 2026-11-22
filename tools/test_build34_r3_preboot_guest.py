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


def regular_file(value):
    path = Path(value).resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError("expected a regular file")
    return path


def boot_guest(command):
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
                lines = result.split(b"\n")[:-1]
                for line in lines:
                    match = FAIL.fullmatch(line.strip())
                    if match is not None:
                        raise SystemExit(f"UEFI guest check {match[1].decode('ascii')} failed")
                if any(line.strip() == PASS for line in lines):
                    return
            raise SystemExit("UEFI guest did not report a complete result within the output and time limits")
        finally:
            if guest.poll() is None:
                guest.kill()
            guest.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description="Run the build34 UEFI metadata fixture inside QEMU TCG only")
    for option in ("qemu", "linker", "uefi-code", "uefi-vars"):
        parser.add_argument(f"--{option}", required=True, type=regular_file)
    parser.add_argument("--edk2-include", required=True, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    if not (args.edk2_include / "Uefi.h").is_file():
        parser.error("--edk2-include must be the pinned EDK II MdePkg/Include directory")

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
        for source in ("tools/build34_r3_preboot_pci.c", "tests/test_build34_r3_preboot_guest.c"):
            obj = private / (Path(source).stem + ".obj")
            subprocess.run(["clang", "-target", "x86_64-pc-windows-msvc", "-std=c11", "-O2", "-Wall",
                            "-Wextra", "-Werror", "-fshort-wchar", "-ffreestanding", "-fno-builtin",
                            "-fno-stack-protector", "-isystem", args.edk2_include, "-isystem",
                            args.edk2_include / "X64", "-Itools", "-c", source, "-o", obj],
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
                    f"if=virtio,format=raw,readonly=on,file=fat:ro:{esp}"])
        print("PASS isolated UEFI guest attribution, refusal and cleanup (synthetic PCI protocols)")
        print(f"guest_application_sha256={digest}")


if __name__ == "__main__":
    main()
