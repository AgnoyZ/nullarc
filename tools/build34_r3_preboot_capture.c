#include "build34_r3_preboot_pci.h"

extern CONST PHX34_PREBOOT_PCI_PATH_IDENTITY Phx34CaptureTarget;

#define CAPTURE_PREFIX L"PHX34_PREBOOT_CAPTURE_V2 "

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
    static CHAR16 line[] = CAPTURE_PREFIX L"FV 00000000-0000-0000-0000-000000000000\r\n";
    CHAR16 *output = line + sizeof(CAPTURE_PREFIX L"FV ") / sizeof(CHAR16) - 1;
    output = append_hex(output, file->Data1, 8) + 1;
    output = append_hex(output, file->Data2, 4) + 1;
    output = append_hex(output, file->Data3, 4) + 1;
    output = append_hex(output, file->Data4[0], 2);
    output = append_hex(output, file->Data4[1], 2) + 1;
    for (UINTN index = 2; index < sizeof(file->Data4); ++index)
        output = append_hex(output, file->Data4[index], 2);
    return console->OutputString(console, line);
}

static EFI_STATUS
report_failure(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *console, EFI_STATUS status, PHX34_PREBOOT_FAILURE_STAGE stage)
{
    CONST CHAR16 *classification = L"REFUSED";
    if (status == EFI_NOT_FOUND)
        classification = L"NOT_FOUND";
    else if (status == EFI_NO_MAPPING)
        classification = L"NO_MAPPING";

    static CONST CHAR16 *CONST names[] = {
        [Phx34PrebootStageNone] = L"UNKNOWN",
        [Phx34PrebootStageInput] = L"INPUT",
        [Phx34PrebootStageRoot] = L"ROOT",
        [Phx34PrebootStageEndpoint] = L"ENDPOINT",
        [Phx34PrebootStageOpenRecords] = L"OPEN_RECORDS",
        [Phx34PrebootStageImage] = L"IMAGE",
        [Phx34PrebootStageRecheck] = L"RECHECK",
        [Phx34PrebootStageCleanup] = L"CLEANUP",
    };
    CONST CHAR16 *name = (UINTN)stage < sizeof(names) / sizeof(names[0]) ? names[stage] : L"UNKNOWN";
    CHAR16 line[64];
    CHAR16 *output = line;
    CONST CHAR16 *parts[] = {CAPTURE_PREFIX, classification, L" ", name, L"\r\n"};
    for (UINTN index = 0; index < sizeof(parts) / sizeof(parts[0]); ++index) {
        for (CONST CHAR16 *part = parts[index]; *part != 0; ++part) {
            if (output == line + sizeof(line) / sizeof(line[0]) - 1)
                return EFI_BAD_BUFFER_SIZE;
            *output++ = *part;
        }
    }
    *output = 0;
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
    if (status != EFI_SUCCESS)
        return report_failure(console, status, observation.FailureStage);
    if (observation.Candidate.ImageHandle == image)
        return report_failure(console, EFI_COMPROMISED_DATA, Phx34PrebootStageImage);
    if (observation.FirmwareFile.VolumeHandle != NULL)
        return report_firmware_file(console, &observation.FirmwareFile.FileGuid);
    return console->OutputString(console, CAPTURE_PREFIX L"NO_FV\r\n");
}
