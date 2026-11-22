#include "build34_r3_preboot_pci.h"

#include <Protocol/DriverBinding.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/PciRootBridgeIo.h>

#define PHX34_MAX_OPEN_ENTRIES 64
#define PHX34_MAX_PATH_BYTES 256
#define PHX34_MAX_PROTOCOL_HANDLES 256

typedef struct {
    EFI_OPEN_PROTOCOL_INFORMATION_ENTRY *Entries;
    UINTN Count;
    EFI_HANDLE Manager;
} OPEN_SAMPLE;

typedef struct {
    CONST EFI_DRIVER_BINDING_PROTOCOL *Binding;
    EFI_HANDLE Handle;
    CONST EFI_LOADED_IMAGE_PROTOCOL *Image;
    CONST VOID *Base;
    UINT64 Size;
} IMAGE_SAMPLE;

typedef struct {
    EFI_HANDLE Handle;
    CONST VOID *Path;
    CONST EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL *Io;
} ROOT_SAMPLE;

static EFI_GUID pci_io = EFI_PCI_IO_PROTOCOL_GUID;
static EFI_GUID root_bridge_io = EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL_GUID;
static EFI_GUID device_path = EFI_DEVICE_PATH_PROTOCOL_GUID;
static EFI_GUID driver_binding = EFI_DRIVER_BINDING_PROTOCOL_GUID;
static EFI_GUID loaded_image = EFI_LOADED_IMAGE_PROTOCOL_GUID;

static EFI_STATUS
strict_status(EFI_STATUS status)
{
    return status == EFI_SUCCESS || EFI_ERROR(status) ? status : EFI_PROTOCOL_ERROR;
}

static EFI_STATUS
check_target(EFI_BOOT_SERVICES *boot, CONST PHX34_PREBOOT_PCI_TARGET *target)
{
    VOID *interface = NULL;
    EFI_STATUS status = boot->HandleProtocol(target->Controller, &device_path, &interface);
    if (status != EFI_SUCCESS)
        return status;
    if (interface != target->DevicePath)
        return EFI_NO_MAPPING;
    interface = NULL;
    status = boot->HandleProtocol(target->Controller, &pci_io, &interface);
    if (status != EFI_SUCCESS)
        return status;
    return interface == target->PciIo ? EFI_SUCCESS : EFI_NO_MAPPING;
}

static BOOLEAN
same_open_key(CONST EFI_OPEN_PROTOCOL_INFORMATION_ENTRY *first,
              CONST EFI_OPEN_PROTOCOL_INFORMATION_ENTRY *second)
{
    return first->AgentHandle == second->AgentHandle &&
           first->ControllerHandle == second->ControllerHandle &&
           first->Attributes == second->Attributes;
}

static EFI_STATUS
read_sample(EFI_BOOT_SERVICES *boot, EFI_HANDLE controller,
            CONST EFI_OPEN_PROTOCOL_INFORMATION_ENTRY *previous_buffer, OPEN_SAMPLE *sample)
{
    EFI_OPEN_PROTOCOL_INFORMATION_ENTRY *entries = NULL;
    UINTN count = 0;
    EFI_STATUS status = boot->OpenProtocolInformation(controller, &pci_io, &entries, &count);
    if (status != EFI_SUCCESS)
        return status;
    sample->Entries = entries;
    sample->Count = count;
    if ((entries != NULL && entries == previous_buffer) ||
        (count != 0 && entries == NULL) || count > PHX34_MAX_OPEN_ENTRIES)
        return EFI_COMPROMISED_DATA;

    for (UINTN index = 0; index < count; ++index) {
        CONST EFI_OPEN_PROTOCOL_INFORMATION_ENTRY *entry = &entries[index];
        if (entry->AgentHandle == NULL || entry->OpenCount == 0)
            return EFI_COMPROMISED_DATA;
        for (UINTN prior = 0; prior < index; ++prior) {
            if (same_open_key(&entries[prior], entry))
                return EFI_COMPROMISED_DATA;
        }
        switch (entry->Attributes) {
        case EFI_OPEN_PROTOCOL_BY_DRIVER:
        case EFI_OPEN_PROTOCOL_BY_DRIVER | EFI_OPEN_PROTOCOL_EXCLUSIVE:
            if (entry->ControllerHandle != controller || entry->AgentHandle == controller ||
                sample->Manager != NULL)
                return EFI_COMPROMISED_DATA;
            sample->Manager = entry->AgentHandle;
            break;
        case EFI_OPEN_PROTOCOL_BY_CHILD_CONTROLLER:
            if (entry->ControllerHandle == NULL || entry->ControllerHandle == controller)
                return EFI_COMPROMISED_DATA;
            break;
        case EFI_OPEN_PROTOCOL_BY_HANDLE_PROTOCOL:
        case EFI_OPEN_PROTOCOL_GET_PROTOCOL:
        case EFI_OPEN_PROTOCOL_TEST_PROTOCOL:
            break;
        case EFI_OPEN_PROTOCOL_EXCLUSIVE:
            return EFI_ACCESS_DENIED;
        default:
            return EFI_COMPROMISED_DATA;
        }
    }
    if (sample->Manager == NULL)
        return EFI_NOT_FOUND;
    for (UINTN index = 0; index < count; ++index) {
        if (entries[index].Attributes == EFI_OPEN_PROTOCOL_BY_CHILD_CONTROLLER &&
            entries[index].AgentHandle != sample->Manager)
            return EFI_COMPROMISED_DATA;
    }
    return EFI_SUCCESS;
}

static BOOLEAN
same_sample(CONST OPEN_SAMPLE *first, CONST OPEN_SAMPLE *second)
{
    if (first->Manager != second->Manager || first->Count != second->Count)
        return FALSE;
    for (UINTN index = 0; index < first->Count; ++index) {
        CONST EFI_OPEN_PROTOCOL_INFORMATION_ENTRY *entry = &first->Entries[index];
        BOOLEAN matched = FALSE;
        for (UINTN peer = 0; peer < second->Count; ++peer) {
            if (same_open_key(entry, &second->Entries[peer]) &&
                entry->OpenCount == second->Entries[peer].OpenCount) {
                matched = TRUE;
                break;
            }
        }
        if (!matched)
            return FALSE;
    }
    return TRUE;
}

static EFI_STATUS
resolve_image(EFI_BOOT_SERVICES *boot, EFI_HANDLE controller, EFI_HANDLE manager,
              IMAGE_SAMPLE *sample)
{
    VOID *interface = NULL;
    EFI_STATUS status = boot->HandleProtocol(manager, &driver_binding, &interface);
    if (status != EFI_SUCCESS)
        return status;
    CONST EFI_DRIVER_BINDING_PROTOCOL *binding = interface;
    if (binding == NULL || binding->DriverBindingHandle != manager ||
        binding->ImageHandle == NULL || binding->ImageHandle == controller)
        return EFI_COMPROMISED_DATA;
    sample->Binding = binding;
    sample->Handle = binding->ImageHandle;
    interface = NULL;
    status = boot->HandleProtocol(sample->Handle, &loaded_image, &interface);
    if (status != EFI_SUCCESS)
        return status;
    CONST EFI_LOADED_IMAGE_PROTOCOL *image = interface;
    if (image == NULL || image->ImageBase == NULL || image->ImageSize == 0)
        return EFI_COMPROMISED_DATA;
    sample->Image = image;
    sample->Base = image->ImageBase;
    sample->Size = image->ImageSize;
    return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
Phx34AttributePciManager(EFI_BOOT_SERVICES *boot, CONST PHX34_PREBOOT_PCI_TARGET *target,
                         PHX34_PREBOOT_PCI_ATTRIBUTION *attribution)
{
    if (attribution == NULL)
        return EFI_INVALID_PARAMETER;
    *attribution = (PHX34_PREBOOT_PCI_ATTRIBUTION){0};
    if (boot == NULL || boot->HandleProtocol == NULL || boot->OpenProtocolInformation == NULL ||
        boot->FreePool == NULL || target == NULL || target->Controller == NULL ||
        target->DevicePath == NULL || target->PciIo == NULL)
        return EFI_INVALID_PARAMETER;

    CONST PHX34_PREBOOT_PCI_TARGET identity = *target;
    OPEN_SAMPLE first = {0}, second = {0};
    IMAGE_SAMPLE image = {0}, confirmation = {0};

    EFI_STATUS status = check_target(boot, &identity);
    if (status == EFI_SUCCESS)
        status = read_sample(boot, identity.Controller, NULL, &first);
    if (status == EFI_SUCCESS)
        status = resolve_image(boot, identity.Controller, first.Manager, &image);
    if (status == EFI_SUCCESS)
        status = read_sample(boot, identity.Controller, first.Entries, &second);
    if (status == EFI_SUCCESS && !same_sample(&first, &second))
        status = EFI_COMPROMISED_DATA;
    if (status == EFI_SUCCESS)
        status = resolve_image(boot, identity.Controller, second.Manager, &confirmation);
    if (status == EFI_SUCCESS &&
        (image.Binding != confirmation.Binding || image.Handle != confirmation.Handle ||
         image.Image != confirmation.Image || image.Base != confirmation.Base || image.Size != confirmation.Size))
        status = EFI_COMPROMISED_DATA;
    if (status == EFI_SUCCESS)
        status = check_target(boot, &identity);

    if (second.Entries != NULL && second.Entries != first.Entries && boot->FreePool(second.Entries) != EFI_SUCCESS)
        status = EFI_DEVICE_ERROR;
    if (first.Entries != NULL && boot->FreePool(first.Entries) != EFI_SUCCESS)
        status = EFI_DEVICE_ERROR;
    if (status == EFI_SUCCESS) {
        attribution->BindingHandle = first.Manager;
        attribution->ImageHandle = image.Handle;
        attribution->OpenEntryCount = first.Count;
    }
    return strict_status(status);
}

static BOOLEAN
node_is(CONST UINT8 *node, UINT8 type, UINT8 subtype, UINTN length)
{
    return node[0] == type && node[1] == subtype &&
           ((UINTN)node[2] | ((UINTN)node[3] << 8)) == length;
}

static CONST UINT8 *
pci_path_endpoint(CONST UINT8 *path, UINTN bytes)
{
    UINTN root_size = sizeof(ACPI_HID_DEVICE_PATH);
    UINTN pci_size = sizeof(PCI_DEVICE_PATH);
    UINTN end_size = sizeof(EFI_DEVICE_PATH_PROTOCOL);
    if (bytes < root_size + pci_size + end_size || (bytes - root_size - end_size) % pci_size != 0 ||
        !node_is(path, ACPI_DEVICE_PATH, ACPI_DP, root_size))
        return NULL;

    UINTN end = bytes - end_size;
    for (UINTN offset = root_size; offset < end; offset += pci_size) {
        CONST UINT8 *node = path + offset;
        if (!node_is(node, HARDWARE_DEVICE_PATH, HW_PCI_DP, pci_size) ||
            node[OFFSET_OF(PCI_DEVICE_PATH, Device)] > 31 || node[OFFSET_OF(PCI_DEVICE_PATH, Function)] > 7)
            return NULL;
    }
    return node_is(path + end, END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, end_size) ?
           path + end - pci_size : NULL;
}

static BOOLEAN
same_path(CONST UINT8 *expected, CONST UINT8 *actual, UINTN bytes)
{
    for (UINTN index = 0; index < bytes; ++index) {
        if (expected[index] != actual[index])
            return FALSE;
    }
    return TRUE;
}

static EFI_STATUS
locate_exact_path(EFI_BOOT_SERVICES *boot, EFI_GUID *protocol, CONST UINT8 *expected, UINTN bytes,
                  EFI_HANDLE *handle, VOID **published)
{
    UINT8 path[PHX34_MAX_PATH_BYTES];
    for (UINTN index = 0; index < bytes; ++index)
        path[index] = expected[index];

    EFI_DEVICE_PATH_PROTOCOL *remaining = (EFI_DEVICE_PATH_PROTOCOL *)path;
    *handle = NULL;
    EFI_STATUS status = boot->LocateDevicePath(protocol, &remaining, handle);
    if (status != EFI_SUCCESS)
        return status;
    if (*handle == NULL || (UINT8 *)remaining != path + bytes - sizeof(*remaining) ||
        !same_path(expected, path, bytes))
        return EFI_NO_MAPPING;

    *published = NULL;
    status = boot->HandleProtocol(*handle, &device_path, published);
    if (status != EFI_SUCCESS)
        return status;
    if (*published == NULL || !same_path(expected, *published, bytes))
        return EFI_NO_MAPPING;
    return EFI_SUCCESS;
}

static EFI_STATUS
locate_unique_path(EFI_BOOT_SERVICES *boot, EFI_GUID *protocol, CONST UINT8 *expected, UINTN bytes,
                   EFI_HANDLE *handle, VOID **published)
{
    EFI_HANDLE handles[PHX34_MAX_PROTOCOL_HANDLES];
    UINTN size = sizeof(handles);
    EFI_STATUS status = boot->LocateHandle(ByProtocol, protocol, NULL, &size, handles);
    if (status != EFI_SUCCESS)
        return status;
    if (size == 0 || size > sizeof(handles) || size % sizeof(handles[0]) != 0)
        return EFI_COMPROMISED_DATA;

    *handle = NULL;
    for (UINTN index = 0; index < size / sizeof(handles[0]); ++index) {
        if (handles[index] == NULL)
            return EFI_COMPROMISED_DATA;
        VOID *candidate = NULL;
        status = boot->HandleProtocol(handles[index], &device_path, &candidate);
        if (status == EFI_UNSUPPORTED)
            continue;
        if (status != EFI_SUCCESS)
            return status;
        if (candidate == NULL)
            return EFI_COMPROMISED_DATA;
        if (same_path(expected, candidate, bytes)) {
            if (*handle != NULL)
                return EFI_NO_MAPPING;
            *handle = handles[index];
            *published = candidate;
        }
    }
    return *handle == NULL ? EFI_NOT_FOUND : EFI_SUCCESS;
}

static EFI_STATUS
resolve_root(EFI_BOOT_SERVICES *boot, CONST PHX34_PREBOOT_PCI_PATH_IDENTITY *identity, BOOLEAN unique,
             ROOT_SAMPLE *root)
{
    UINT8 expected[sizeof(ACPI_HID_DEVICE_PATH) + sizeof(EFI_DEVICE_PATH_PROTOCOL)];
    for (UINTN index = 0; index < sizeof(ACPI_HID_DEVICE_PATH); ++index)
        expected[index] = identity->DevicePath[index];
    for (UINTN index = 0; index < sizeof(EFI_DEVICE_PATH_PROTOCOL); ++index)
        expected[sizeof(ACPI_HID_DEVICE_PATH) + index] =
            identity->DevicePath[identity->DevicePathBytes - sizeof(EFI_DEVICE_PATH_PROTOCOL) + index];

    EFI_HANDLE handle;
    VOID *path;
    EFI_STATUS status = (unique ? locate_unique_path : locate_exact_path)(boot, &root_bridge_io, expected,
                                                                        sizeof(expected), &handle, &path);
    if (status != EFI_SUCCESS)
        return status;
    VOID *interface = NULL;
    status = boot->HandleProtocol(handle, &root_bridge_io, &interface);
    if (status != EFI_SUCCESS)
        return status;
    CONST EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL *bridge = interface;
    if (bridge == NULL || bridge->SegmentNumber != identity->Segment)
        return EFI_NO_MAPPING;
    *root = (ROOT_SAMPLE){handle, path, bridge};
    return EFI_SUCCESS;
}

static EFI_STATUS
resolve_by_path(EFI_BOOT_SERVICES *boot, CONST PHX34_PREBOOT_PCI_PATH_IDENTITY *identity, BOOLEAN unique,
                PHX34_PREBOOT_PCI_TARGET *target)
{
    EFI_HANDLE controller;
    VOID *path_interface;
    EFI_STATUS status = (unique ? locate_unique_path : locate_exact_path)(boot, &pci_io, identity->DevicePath,
                                                                        identity->DevicePathBytes, &controller,
                                                                        &path_interface);
    if (status != EFI_SUCCESS)
        return status;

    VOID *pci_interface = NULL;
    status = boot->HandleProtocol(controller, &pci_io, &pci_interface);
    if (status != EFI_SUCCESS)
        return status;
    if (pci_interface == NULL)
        return EFI_UNSUPPORTED;
    *target = (PHX34_PREBOOT_PCI_TARGET){controller, path_interface, pci_interface};
    return EFI_SUCCESS;
}

static EFI_STATUS
resolve_target(EFI_BOOT_SERVICES *boot, CONST PHX34_PREBOOT_PCI_IDENTITY *identity,
               CONST PHX34_PREBOOT_PCI_PATH_IDENTITY *path, PHX34_PREBOOT_PCI_TARGET *target)
{
    EFI_STATUS status = resolve_by_path(boot, path, FALSE, target);
    if (status != EFI_SUCCESS)
        return status;
    if (target->PciIo->GetLocation != identity->ReadLocation)
        return EFI_UNSUPPORTED;

    UINTN segment = MAX_UINTN, bus = MAX_UINTN, device = MAX_UINTN, function = MAX_UINTN;
    status = identity->ReadLocation((EFI_PCI_IO_PROTOCOL *)target->PciIo, &segment, &bus, &device, &function);
    if (status != EFI_SUCCESS)
        return status;
    if (segment != identity->Segment || bus != identity->Bus ||
        device != identity->Device || function != identity->Function)
        return EFI_NO_MAPPING;
    return EFI_SUCCESS;
}

static BOOLEAN
same_target(CONST PHX34_PREBOOT_PCI_TARGET *first, CONST PHX34_PREBOOT_PCI_TARGET *last)
{
    return first->Controller == last->Controller && first->DevicePath == last->DevicePath && first->PciIo == last->PciIo;
}

static BOOLEAN
same_root(CONST ROOT_SAMPLE *first, CONST ROOT_SAMPLE *last)
{
    return first->Handle == last->Handle && first->Path == last->Path && first->Io == last->Io;
}

EFI_STATUS EFIAPI
Phx34AttributePciManagerAtLocation(EFI_BOOT_SERVICES *boot, CONST PHX34_PREBOOT_PCI_IDENTITY *identity,
                                   PHX34_PREBOOT_PCI_ATTRIBUTION *attribution)
{
    if (attribution == NULL)
        return EFI_INVALID_PARAMETER;
    *attribution = (PHX34_PREBOOT_PCI_ATTRIBUTION){0};
    if (boot == NULL || boot->LocateDevicePath == NULL || boot->HandleProtocol == NULL ||
        boot->OpenProtocolInformation == NULL || boot->FreePool == NULL || identity == NULL)
        return EFI_INVALID_PARAMETER;
    PHX34_PREBOOT_PCI_IDENTITY expected = *identity;
    if (expected.DevicePath == NULL || expected.DevicePathBytes > PHX34_MAX_PATH_BYTES ||
        expected.ReadLocation == NULL || expected.Segment > 65535 || expected.Bus > 255 ||
        expected.Device > 31 || expected.Function > 7)
        return EFI_INVALID_PARAMETER;

    UINT8 path[PHX34_MAX_PATH_BYTES];
    for (UINTN index = 0; index < expected.DevicePathBytes; ++index)
        path[index] = expected.DevicePath[index];
    CONST UINT8 *endpoint = pci_path_endpoint(path, expected.DevicePathBytes);
    if (endpoint == NULL || endpoint[OFFSET_OF(PCI_DEVICE_PATH, Device)] != expected.Device ||
        endpoint[OFFSET_OF(PCI_DEVICE_PATH, Function)] != expected.Function)
        return EFI_INVALID_PARAMETER;
    PHX34_PREBOOT_PCI_PATH_IDENTITY sealed = {path, expected.DevicePathBytes, expected.Segment};

    PHX34_PREBOOT_PCI_TARGET first = {0}, last = {0};
    ROOT_SAMPLE first_root = {0}, last_root = {0};
    PHX34_PREBOOT_PCI_ATTRIBUTION result = {0};
    EFI_STATUS status = resolve_root(boot, &sealed, FALSE, &first_root);
    if (status == EFI_SUCCESS)
        status = resolve_target(boot, &expected, &sealed, &first);
    if (status == EFI_SUCCESS)
        status = Phx34AttributePciManager(boot, &first, &result);
    if (status == EFI_SUCCESS)
        status = resolve_target(boot, &expected, &sealed, &last);
    if (status == EFI_SUCCESS && !same_target(&first, &last))
        status = EFI_NO_MAPPING;
    if (status == EFI_SUCCESS)
        status = resolve_root(boot, &sealed, FALSE, &last_root);
    if (status == EFI_SUCCESS && !same_root(&first_root, &last_root))
        status = EFI_NO_MAPPING;
    if (status == EFI_SUCCESS)
        *attribution = result;
    return strict_status(status);
}

EFI_STATUS EFIAPI
Phx34ObservePciManagerAtPath(EFI_BOOT_SERVICES *boot, CONST PHX34_PREBOOT_PCI_PATH_IDENTITY *identity,
                            PHX34_PREBOOT_PCI_PATH_OBSERVATION *observation)
{
    if (observation == NULL)
        return EFI_INVALID_PARAMETER;
    *observation = (PHX34_PREBOOT_PCI_PATH_OBSERVATION){0};
    if (boot == NULL || boot->LocateHandle == NULL || boot->HandleProtocol == NULL ||
        boot->OpenProtocolInformation == NULL || boot->FreePool == NULL || identity == NULL)
        return EFI_INVALID_PARAMETER;
    PHX34_PREBOOT_PCI_PATH_IDENTITY sealed = *identity;
    if (sealed.DevicePath == NULL || sealed.DevicePathBytes > PHX34_MAX_PATH_BYTES || sealed.Segment > 65535)
        return EFI_INVALID_PARAMETER;

    UINT8 path[PHX34_MAX_PATH_BYTES];
    for (UINTN index = 0; index < sealed.DevicePathBytes; ++index)
        path[index] = sealed.DevicePath[index];
    sealed.DevicePath = path;
    if (pci_path_endpoint(path, sealed.DevicePathBytes) == NULL)
        return EFI_INVALID_PARAMETER;

    PHX34_PREBOOT_PCI_TARGET first = {0}, last = {0};
    ROOT_SAMPLE first_root = {0}, last_root = {0};
    PHX34_PREBOOT_PCI_ATTRIBUTION candidate = {0};
    EFI_STATUS status = resolve_root(boot, &sealed, TRUE, &first_root);
    if (status == EFI_SUCCESS)
        status = resolve_by_path(boot, &sealed, TRUE, &first);
    if (status == EFI_SUCCESS)
        status = Phx34AttributePciManager(boot, &first, &candidate);
    if (status == EFI_SUCCESS)
        status = resolve_by_path(boot, &sealed, TRUE, &last);
    if (status == EFI_SUCCESS && !same_target(&first, &last))
        status = EFI_NO_MAPPING;
    if (status == EFI_SUCCESS)
        status = resolve_root(boot, &sealed, TRUE, &last_root);
    if (status == EFI_SUCCESS && !same_root(&first_root, &last_root))
        status = EFI_NO_MAPPING;
    if (status == EFI_SUCCESS)
        observation->Candidate = candidate;
    return strict_status(status);
}
