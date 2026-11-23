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

    const CHAR16 fv[] = L"PHX34_PREBOOT_CAPTURE_V1 FV 12345678-4321-abcd-0102-030405060708\r\n";
    const CHAR16 no_fv[] = L"PHX34_PREBOOT_CAPTURE_V1 NO_FV\r\n";
    const CHAR16 not_found[] = L"PHX34_PREBOOT_CAPTURE_V1 NOT_FOUND\r\n";
    const CHAR16 no_mapping[] = L"PHX34_PREBOOT_CAPTURE_V1 NO_MAPPING\r\n";
    const CHAR16 refused[] = L"PHX34_PREBOOT_CAPTURE_V1 REFUSED\r\n";
    const struct {
        EFI_STATUS observation, output;
        BOOLEAN volume, self;
        const CHAR16 *line;
        size_t bytes;
    } cases[] = {
        {EFI_SUCCESS, EFI_SUCCESS, TRUE, FALSE, fv, sizeof(fv)},
        {EFI_SUCCESS, EFI_SUCCESS, FALSE, FALSE, no_fv, sizeof(no_fv)},
        {EFI_NOT_FOUND, EFI_SUCCESS, FALSE, FALSE, not_found, sizeof(not_found)},
        {EFI_NO_MAPPING, EFI_SUCCESS, FALSE, FALSE, no_mapping, sizeof(no_mapping)},
        {EFI_COMPROMISED_DATA, EFI_SUCCESS, FALSE, FALSE, refused, sizeof(refused)},
        {EFI_SUCCESS, EFI_SUCCESS, TRUE, TRUE, refused, sizeof(refused)},
        {EFI_NOT_FOUND, EFI_DEVICE_ERROR, FALSE, FALSE, not_found, sizeof(not_found)},
        {EFI_SUCCESS, EFI_WARN_UNKNOWN_GLYPH, TRUE, FALSE, fv, sizeof(fv)},
    };
    for (size_t index = 0; index < sizeof(cases) / sizeof(*cases); ++index) {
        observation_status = cases[index].observation;
        output_status = cases[index].output;
        has_fv = cases[index].volume;
        self_manager = cases[index].self;
        expected_line = cases[index].line;
        expected_bytes = cases[index].bytes;
        observes = outputs = 0;
        CHECK(EfiMain(&image, &system) == output_status && observes == 1 && outputs == 1);
    }
    puts("PASS 10 preboot capture reporting and EFI exit scenarios (CPU fixture only)");
    return EXIT_SUCCESS;
}
