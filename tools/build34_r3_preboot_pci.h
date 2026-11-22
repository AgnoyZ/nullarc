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
    CONST UINT8 *DevicePath;
    UINTN DevicePathBytes;
    UINTN Segment;
    UINTN Bus;
    UINTN Device;
    UINTN Function;
    EFI_PCI_IO_PROTOCOL_GET_LOCATION ReadLocation;
} PHX34_PREBOOT_PCI_IDENTITY;

typedef struct {
    EFI_HANDLE BindingHandle;
    EFI_HANDLE ImageHandle;
    UINTN OpenEntryCount;
} PHX34_PREBOOT_PCI_ATTRIBUTION;

typedef struct {
    CONST UINT8 *DevicePath;
    UINTN DevicePathBytes;
    UINTN Segment;
} PHX34_PREBOOT_PCI_PATH_IDENTITY;

typedef struct {
    PHX34_PREBOOT_PCI_ATTRIBUTION Candidate;
} PHX34_PREBOOT_PCI_PATH_OBSERVATION;

EFI_STATUS EFIAPI
Phx34AttributePciManager(EFI_BOOT_SERVICES *Boot, CONST PHX34_PREBOOT_PCI_TARGET *Target,
                         PHX34_PREBOOT_PCI_ATTRIBUTION *Attribution);

EFI_STATUS EFIAPI
Phx34AttributePciManagerAtLocation(EFI_BOOT_SERVICES *Boot, CONST PHX34_PREBOOT_PCI_IDENTITY *Identity,
                                   PHX34_PREBOOT_PCI_ATTRIBUTION *Attribution);

EFI_STATUS EFIAPI
Phx34ObservePciManagerAtPath(EFI_BOOT_SERVICES *Boot, CONST PHX34_PREBOOT_PCI_PATH_IDENTITY *Identity,
                            PHX34_PREBOOT_PCI_PATH_OBSERVATION *Observation);

#endif
