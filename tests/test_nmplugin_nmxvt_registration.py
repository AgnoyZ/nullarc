#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/nmplugin/NVMTLDevice.m").read_text()


def check(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    return condition


def main():
    registration_start = SOURCE.find("static void nvmtl_nmxvt_register(void)")
    registration_end = SOURCE.find("\n}", registration_start)
    registration = SOURCE[registration_start:registration_end] if registration_start >= 0 else ""
    trust_start = SOURCE.find("static bool nvmtl_loadable_root_only(const char *path)")
    trust_end = SOURCE.find("\n}", trust_start)
    trust_check = SOURCE[trust_start:trust_end] if trust_start >= 0 else ""
    device_start = SOURCE.find("- (instancetype)initWithAcceleratorPort:(mach_port_t)port {")
    device_end = SOURCE.find("\n}", device_start)
    device_init = SOURCE[device_start:device_end] if device_start >= 0 else ""

    checks = [
        ("provider registration is implemented", bool(registration)),
        ("registration requires the exact NMXVT=1 opt-in gate", "nvmtl_nmxvt_registration_allowed" in registration),
        ("provider library path is derived from the plugin image", "dladdr" in registration and "libnmxvt.dylib" in registration),
        ("provider library must pass the root-owned path check", "nvmtl_loadable_root_only(path)" in registration),
        ("library trust check rejects symlinks and non-regular files", "lstat(path, &st)" in trust_check and "S_ISREG(st.st_mode)" in trust_check),
        ("library and parent directory must be root-owned and not writable by others", "st.st_uid != 0" in trust_check and "ds.st_uid == 0" in trust_check and "S_IWGRP | S_IWOTH" in trust_check),
        ("provider entry point is resolved dynamically", 'dlsym(h, "NMXVT_Register")' in registration),
        ("registration does not assert hardware acceleration", "VTIsHardwareAccelerated" not in registration),
        ("registration runs only after the Vulkan device initializes", "if (nvmtl_vk_init())" in device_init and "nvmtl_nmxvt_register()" in device_init),
        ("NVIDIA registrations retain their vendor-specific branch", "if (nvmtl_vk_vendor() == 0x10de)" in device_init),
    ]
    return 0 if all(check(name, condition) for name, condition in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
