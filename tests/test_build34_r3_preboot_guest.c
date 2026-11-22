#include "build34_r3_preboot_pci.h"

#include <Protocol/DriverBinding.h>
#include <Protocol/PciRootBridgeIo.h>

typedef struct {
    ACPI_HID_DEVICE_PATH Root;
    PCI_DEVICE_PATH Endpoint;
    EFI_DEVICE_PATH_PROTOCOL End;
} GUEST_PATH;

typedef struct {
    ACPI_HID_DEVICE_PATH Root;
    PCI_DEVICE_PATH Bridge, Endpoint;
    EFI_DEVICE_PATH_PROTOCOL End;
} GUEST_LONG_PATH;

typedef struct {
    ACPI_HID_DEVICE_PATH Root;
    EFI_DEVICE_PATH_PROTOCOL End;
} GUEST_ROOT_PATH;

static GUEST_PATH fixture_path = {
    {{ACPI_DEVICE_PATH, ACPI_DP, {sizeof(ACPI_HID_DEVICE_PATH), 0}}, EISA_PNP_ID(0x0A08), 0x52334755},
    {{HARDWARE_DEVICE_PATH, HW_PCI_DP, {sizeof(PCI_DEVICE_PATH), 0}}, 7, 31},
    {END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, {sizeof(EFI_DEVICE_PATH_PROTOCOL), 0}}
};

static EFI_GUID path_guid = EFI_DEVICE_PATH_PROTOCOL_GUID;
static EFI_GUID pci_guid = EFI_PCI_IO_PROTOCOL_GUID;
static EFI_GUID root_guid = EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL_GUID;
static EFI_GUID binding_guid = EFI_DRIVER_BINDING_PROTOCOL_GUID;
static GUEST_ROOT_PATH fixture_root_path;
static EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL fixture_root_io = {.SegmentNumber = 0x5233};
static EFI_PCI_IO_PROTOCOL fixture_pci;
static EFI_DRIVER_BINDING_PROTOCOL fixture_binding;
static UINTN location_reads;
static VOID *volatile relocation_anchor = &fixture_path;

static EFI_STATUS EFIAPI
fixture_location(EFI_PCI_IO_PROTOCOL *protocol, UINTN *segment, UINTN *bus, UINTN *device, UINTN *function)
{
    if (protocol != &fixture_pci)
        return EFI_INVALID_PARAMETER;
    ++location_reads;
    *segment = 0x5233;
    *bus = 23;
    *device = 31;
    *function = 7;
    return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
reject_location(EFI_PCI_IO_PROTOCOL *protocol, UINTN *segment, UINTN *bus, UINTN *device, UINTN *function)
{
    (void)protocol;
    (void)segment;
    (void)bus;
    (void)device;
    (void)function;
    return EFI_ABORTED;
}

static BOOLEAN
empty_attribution(CONST PHX34_PREBOOT_PCI_ATTRIBUTION *attribution)
{
    return attribution->BindingHandle == NULL && attribution->ImageHandle == NULL && attribution->OpenEntryCount == 0;
}

static UINTN
check_attribution(EFI_BOOT_SERVICES *boot, EFI_HANDLE image, EFI_HANDLE controller, EFI_HANDLE manager,
                  BOOLEAN *opened)
{
    PHX34_PREBOOT_PCI_IDENTITY identity = {(CONST UINT8 *)&fixture_path, sizeof(fixture_path),
                                          0x5233, 23, 31, 7, fixture_location};
    PHX34_PREBOOT_PCI_ATTRIBUTION attribution = {manager, image, 1};
    if (Phx34AttributePciManagerAtLocation(boot, &identity, &attribution) != EFI_NOT_FOUND ||
        !empty_attribution(&attribution) || location_reads != 1)
        return 3;

    VOID *interface = NULL;
    if (boot->OpenProtocol(controller, &pci_guid, &interface, manager, controller, EFI_OPEN_PROTOCOL_BY_DRIVER) != EFI_SUCCESS)
        return 4;
    *opened = TRUE;
    if (interface != &fixture_pci || Phx34AttributePciManagerAtLocation(boot, &identity, &attribution) != EFI_SUCCESS ||
        attribution.BindingHandle != manager || attribution.ImageHandle != image || attribution.OpenEntryCount < 1 ||
        location_reads != 3)
        return 5;

    PHX34_PREBOOT_PCI_IDENTITY wrong = identity;
    wrong.Bus++;
    if (Phx34AttributePciManagerAtLocation(boot, &wrong, &attribution) != EFI_NO_MAPPING ||
        !empty_attribution(&attribution) || location_reads != 4)
        return 6;
    wrong = identity;
    wrong.ReadLocation = reject_location;
    if (Phx34AttributePciManagerAtLocation(boot, &wrong, &attribution) != EFI_UNSUPPORTED ||
        !empty_attribution(&attribution) || location_reads != 4)
        return 7;
    wrong = identity;
    ++wrong.Segment;
    if (Phx34AttributePciManagerAtLocation(boot, &wrong, &attribution) != EFI_NO_MAPPING ||
        !empty_attribution(&attribution) || location_reads != 4)
        return 14;

    GUEST_LONG_PATH longer = {fixture_path.Root, fixture_path.Endpoint, fixture_path.Endpoint, fixture_path.End};
    wrong = identity;
    wrong.DevicePath = (CONST UINT8 *)&longer;
    wrong.DevicePathBytes = sizeof(longer);
    if (Phx34AttributePciManagerAtLocation(boot, &wrong, &attribution) != EFI_NO_MAPPING ||
        !empty_attribution(&attribution) || location_reads != 4)
        return 8;
    if (boot->CloseProtocol(controller, &pci_guid, manager, controller) != EFI_SUCCESS)
        return 9;
    *opened = FALSE;
    if (Phx34AttributePciManagerAtLocation(boot, &identity, &attribution) != EFI_NOT_FOUND ||
        !empty_attribution(&attribution) || location_reads != 5)
        return 10;
    return 0;
}

EFI_STATUS EFIAPI
EfiMain(EFI_HANDLE image, EFI_SYSTEM_TABLE *system)
{
    if (image == NULL || system == NULL || system->BootServices == NULL || system->ConOut == NULL ||
        relocation_anchor != &fixture_path)
        return EFI_INVALID_PARAMETER;

    EFI_BOOT_SERVICES *boot = system->BootServices;
    EFI_HANDLE root = NULL, controller = NULL, manager = NULL;
    BOOLEAN opened = FALSE;
    UINTN failure;

    fixture_pci.GetLocation = fixture_location;
    fixture_binding.ImageHandle = image;
    fixture_root_path = (GUEST_ROOT_PATH){fixture_path.Root, fixture_path.End};
    if (boot->InstallMultipleProtocolInterfaces(&root, &path_guid, &fixture_root_path,
                                               &root_guid, &fixture_root_io, NULL) != EFI_SUCCESS) {
        failure = 15;
    } else if (boot->InstallMultipleProtocolInterfaces(&controller, &path_guid, &fixture_path,
                                                      &pci_guid, &fixture_pci, NULL) != EFI_SUCCESS) {
        failure = 1;
    } else if (boot->InstallProtocolInterface(&manager, &binding_guid, EFI_NATIVE_INTERFACE,
                                              &fixture_binding) != EFI_SUCCESS) {
        failure = 2;
    } else {
        fixture_binding.DriverBindingHandle = manager;
        failure = check_attribution(boot, image, controller, manager, &opened);
    }

    if (opened && boot->CloseProtocol(controller, &pci_guid, manager, controller) != EFI_SUCCESS)
        failure = 11;
    if (manager != NULL && boot->UninstallProtocolInterface(manager, &binding_guid, &fixture_binding) != EFI_SUCCESS)
        failure = 12;
    if (controller != NULL && boot->UninstallMultipleProtocolInterfaces(controller, &pci_guid, &fixture_pci,
                                                                       &path_guid, &fixture_path, NULL) != EFI_SUCCESS)
        failure = 13;
    if (root != NULL && boot->UninstallMultipleProtocolInterfaces(root, &root_guid, &fixture_root_io,
                                                                 &path_guid, &fixture_root_path, NULL) != EFI_SUCCESS)
        failure = 16;
    if (failure != 0) {
        CHAR16 message[] = L"PHX34_PREBOOT_GUEST_FAIL 00\r\n";
        message[25] = (CHAR16)(L'0' + failure / 10);
        message[26] = (CHAR16)(L'0' + failure % 10);
        system->ConOut->OutputString(system->ConOut, message);
        return EFI_ABORTED;
    }
    return system->ConOut->OutputString(system->ConOut, L"PHX34_PREBOOT_GUEST_PASS\r\n");
}
