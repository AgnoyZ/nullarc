#ifndef BUILD34_R3_PREBOOT_PCI_H
#define BUILD34_R3_PREBOOT_PCI_H

#include <Uefi.h>
#include <Protocol/PciIo.h>

typedef struct {
    EFI_HANDLE Controller;
    CONST EFI_DEVICE_PATH_PROTOCOL *DevicePath;
    CONST EFI_PCI_IO_PROTOCOL *PciIo;
} PHX34_PREBOOT_PCI_TARGET;

typedef struct {
    EFI_HANDLE BindingHandle;
    EFI_HANDLE ImageHandle;
    UINTN OpenEntryCount;
} PHX34_PREBOOT_PCI_ATTRIBUTION;

EFI_STATUS EFIAPI
Phx34AttributePciManager(EFI_BOOT_SERVICES *Boot, CONST PHX34_PREBOOT_PCI_TARGET *Target,
                         PHX34_PREBOOT_PCI_ATTRIBUTION *Attribution);

#endif
