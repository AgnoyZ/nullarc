#include "build34_r3_preboot_pci.h"

#include <Protocol/DriverBinding.h>
#include <Protocol/LoadedImage.h>

#define PHX34_MAX_OPEN_ENTRIES 64

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

static EFI_GUID pci_io = EFI_PCI_IO_PROTOCOL_GUID;
static EFI_GUID device_path = EFI_DEVICE_PATH_PROTOCOL_GUID;
static EFI_GUID driver_binding = EFI_DRIVER_BINDING_PROTOCOL_GUID;
static EFI_GUID loaded_image = EFI_LOADED_IMAGE_PROTOCOL_GUID;

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
    return status == EFI_SUCCESS || EFI_ERROR(status) ? status : EFI_PROTOCOL_ERROR;
}
