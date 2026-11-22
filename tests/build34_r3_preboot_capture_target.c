#include "build34_r3_preboot_pci.h"

#ifndef PHX34_CAPTURE_FIXTURE_SEGMENT
#error Supply the emulated segment explicitly
#endif

static CONST struct {
    ACPI_HID_DEVICE_PATH Root;
    PCI_DEVICE_PATH Endpoint;
    EFI_DEVICE_PATH_PROTOCOL End;
} virtio_path = {
    .Root = {{ACPI_DEVICE_PATH, ACPI_DP, {sizeof(ACPI_HID_DEVICE_PATH), 0}}, EISA_PNP_ID(0x0A03), 0},
    .Endpoint = {{HARDWARE_DEVICE_PATH, HW_PCI_DP, {sizeof(PCI_DEVICE_PATH), 0}}, 0, 5},
    .End = {END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, {sizeof(EFI_DEVICE_PATH_PROTOCOL), 0}},
};

CONST PHX34_PREBOOT_PCI_PATH_IDENTITY Phx34CaptureTarget = {
    .DevicePath = (CONST UINT8 *)&virtio_path,
    .DevicePathBytes = sizeof(virtio_path),
    .Segment = PHX34_CAPTURE_FIXTURE_SEGMENT,
};
