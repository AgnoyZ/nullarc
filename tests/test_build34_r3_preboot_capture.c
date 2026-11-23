#include "build34_r3_preboot_pci.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

EFI_STATUS EFIAPI EfiMain(EFI_HANDLE Image, EFI_SYSTEM_TABLE *System);

static UINT8 image, manager, volume;
static EFI_BOOT_SERVICES boot;
static EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL console;
static EFI_STATUS observation_status, output_status;
static PHX34_PREBOOT_FAILURE_STAGE failure_stage;
static BOOLEAN has_fv, self_manager;
static const CHAR16 *expected_line;
static size_t expected_bytes;
static UINTN observes, outputs;

CONST PHX34_PREBOOT_PCI_PATH_IDENTITY Phx34CaptureTarget = {0};

EFI_STATUS EFIAPI
Phx34ObservePciManagerAtPath(EFI_BOOT_SERVICES *services, CONST PHX34_PREBOOT_PCI_PATH_IDENTITY *identity,
                            PHX34_PREBOOT_PCI_PATH_OBSERVATION *observation)
{
    CHECK(services == &boot && identity == &Phx34CaptureTarget && ++observes == 1);
    *observation = (PHX34_PREBOOT_PCI_PATH_OBSERVATION){
        .Candidate = {.ImageHandle = self_manager ? &image : &manager},
        .FirmwareFile = {.VolumeHandle = has_fv ? &volume : NULL,
                         .FileGuid = {0x12345678, 0x4321, 0xabcd, {1, 2, 3, 4, 5, 6, 7, 8}}},
        .FailureStage = failure_stage,
    };
    return observation_status;
}

static EFI_STATUS EFIAPI
output_line(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *interface, CHAR16 *line)
{
    CHECK(interface == &console && observes == 1 && ++outputs == 1);
    size_t count = 0;
    while (line[count] != 0)
        ++count;
    CHECK((count + 1) * sizeof(*line) == expected_bytes);
    CHECK(memcmp(line, expected_line, expected_bytes) == 0);
    return output_status;
}

int main(void)
{
    EFI_SYSTEM_TABLE system = {.BootServices = &boot, .ConOut = &console};
    CHECK(EfiMain(&image, &system) == EFI_INVALID_PARAMETER && observes == 0 && outputs == 0);
    console.OutputString = output_line;
    CHECK(EfiMain(NULL, &system) == EFI_INVALID_PARAMETER && observes == 0 && outputs == 0);

#define LINE(result) L"PHX34_PREBOOT_CAPTURE_V2 " result L"\r\n"
#define CASE(status, output, stage, volume, self, result) \
    {status, output, Phx34PrebootStage##stage, volume, self, LINE(result), sizeof(LINE(result))}
    const struct {
        EFI_STATUS observation, output;
        PHX34_PREBOOT_FAILURE_STAGE stage;
        BOOLEAN volume, self;
        const CHAR16 *line;
        size_t bytes;
    } cases[] = {
        CASE(EFI_SUCCESS, EFI_SUCCESS, None, TRUE, FALSE, L"FV 12345678-4321-abcd-0102-030405060708"),
        CASE(EFI_SUCCESS, EFI_SUCCESS, None, FALSE, FALSE, L"NO_FV"),
        CASE(EFI_NOT_FOUND, EFI_SUCCESS, Root, FALSE, FALSE, L"NOT_FOUND ROOT"),
        CASE(EFI_NOT_FOUND, EFI_SUCCESS, Endpoint, FALSE, FALSE, L"NOT_FOUND ENDPOINT"),
        CASE(EFI_NOT_FOUND, EFI_SUCCESS, OpenRecords, FALSE, FALSE, L"NOT_FOUND OPEN_RECORDS"),
        CASE(EFI_NOT_FOUND, EFI_SUCCESS, Image, TRUE, FALSE, L"NOT_FOUND IMAGE"),
        CASE(EFI_NOT_FOUND, EFI_SUCCESS, Recheck, TRUE, FALSE, L"NOT_FOUND RECHECK"),
        CASE(EFI_NO_MAPPING, EFI_SUCCESS, Root, FALSE, FALSE, L"NO_MAPPING ROOT"),
        CASE(EFI_INVALID_PARAMETER, EFI_SUCCESS, Input, FALSE, FALSE, L"REFUSED INPUT"),
        CASE(EFI_DEVICE_ERROR, EFI_SUCCESS, Cleanup, TRUE, FALSE, L"REFUSED CLEANUP"),
        CASE(EFI_COMPROMISED_DATA, EFI_SUCCESS, None, TRUE, FALSE, L"REFUSED UNKNOWN"),
        CASE(EFI_SUCCESS, EFI_SUCCESS, None, TRUE, TRUE, L"REFUSED IMAGE"),
        CASE(EFI_NOT_FOUND, EFI_DEVICE_ERROR, Endpoint, FALSE, FALSE, L"NOT_FOUND ENDPOINT"),
        CASE(EFI_SUCCESS, EFI_WARN_UNKNOWN_GLYPH, None, TRUE, FALSE, L"FV 12345678-4321-abcd-0102-030405060708"),
    };
#undef CASE
#undef LINE
    for (size_t index = 0; index < sizeof(cases) / sizeof(*cases); ++index) {
        observation_status = cases[index].observation;
        output_status = cases[index].output;
        failure_stage = cases[index].stage;
        has_fv = cases[index].volume;
        self_manager = cases[index].self;
        expected_line = cases[index].line;
        expected_bytes = cases[index].bytes;
        observes = outputs = 0;
        CHECK(EfiMain(&image, &system) == output_status && observes == 1 && outputs == 1);
    }
    printf("PASS %zu preboot capture reporting and EFI exit scenarios (CPU fixture only)\n",
           sizeof(cases) / sizeof(*cases) + 2);
    return EXIT_SUCCESS;
}
