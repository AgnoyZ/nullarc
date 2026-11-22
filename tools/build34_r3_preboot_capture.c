#include "build34_r3_preboot_pci.h"

extern CONST PHX34_PREBOOT_PCI_PATH_IDENTITY Phx34CaptureTarget;

static CHAR16 *
append_hex(CHAR16 *output, UINT32 value, UINTN digits)
{
    static CONST CHAR16 hex[] = L"0123456789abcdef";
    while (digits != 0) {
        --digits;
        *output++ = hex[(value >> (4 * digits)) & 15];
    }
    return output;
}

static EFI_STATUS
report_firmware_file(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *console, CONST EFI_GUID *file)
{
    static CHAR16 line[] = L"PHX34_PREBOOT_CAPTURE_V1 FV 00000000-0000-0000-0000-000000000000\r\n";
    CHAR16 *output = line + sizeof(L"PHX34_PREBOOT_CAPTURE_V1 FV ") / sizeof(CHAR16) - 1;
    output = append_hex(output, file->Data1, 8) + 1;
    output = append_hex(output, file->Data2, 4) + 1;
    output = append_hex(output, file->Data3, 4) + 1;
    output = append_hex(output, file->Data4[0], 2);
    output = append_hex(output, file->Data4[1], 2) + 1;
    for (UINTN index = 2; index < sizeof(file->Data4); ++index)
        output = append_hex(output, file->Data4[index], 2);
    return console->OutputString(console, line);
}

EFI_STATUS EFIAPI
EfiMain(EFI_HANDLE image, EFI_SYSTEM_TABLE *system)
{
    if (image == NULL || system == NULL || system->BootServices == NULL || system->ConOut == NULL ||
        system->ConOut->OutputString == NULL)
        return EFI_INVALID_PARAMETER;

    EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *console = system->ConOut;
    PHX34_PREBOOT_PCI_PATH_OBSERVATION observation;
    EFI_STATUS status = Phx34ObservePciManagerAtPath(system->BootServices, &Phx34CaptureTarget, &observation);
    if (status == EFI_SUCCESS && observation.Candidate.ImageHandle == image)
        status = EFI_COMPROMISED_DATA;
    if (status == EFI_SUCCESS && observation.FirmwareFile.VolumeHandle != NULL)
        return report_firmware_file(console, &observation.FirmwareFile.FileGuid);

    CHAR16 *line = L"PHX34_PREBOOT_CAPTURE_V1 REFUSED\r\n";
    if (status == EFI_SUCCESS)
        line = L"PHX34_PREBOOT_CAPTURE_V1 NO_FV\r\n";
    else if (status == EFI_NO_MAPPING)
        line = L"PHX34_PREBOOT_CAPTURE_V1 NO_MAPPING\r\n";
    else if (status == EFI_NOT_FOUND)
        line = L"PHX34_PREBOOT_CAPTURE_V1 NOT_FOUND\r\n";

    EFI_STATUS reported = console->OutputString(console, line);
    return reported == EFI_SUCCESS ? status : reported;
}
