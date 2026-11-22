#include "build34_r3_preboot_pci.h"

#include <Protocol/DriverBinding.h>
#include <Protocol/LoadedImage.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

static const EFI_GUID pci_guid = EFI_PCI_IO_PROTOCOL_GUID;
static const EFI_GUID path_guid = EFI_DEVICE_PATH_PROTOCOL_GUID;
static const EFI_GUID binding_guid = EFI_DRIVER_BINDING_PROTOCOL_GUID;
static const EFI_GUID image_guid = EFI_LOADED_IMAGE_PROTOCOL_GUID;

static UINT8 controller, manager, image, child, console, image_memory;
static EFI_DEVICE_PATH_PROTOCOL device_path, other_path;
static EFI_PCI_IO_PROTOCOL pci, other_pci;
static EFI_DRIVER_BINDING_PROTOCOL binding;
static EFI_LOADED_IMAGE_PROTOCOL loaded_image;

typedef struct {
    EFI_OPEN_PROTOCOL_INFORMATION_ENTRY rows[4];
    UINTN count;
    EFI_STATUS status;
} SCRIPTED_SAMPLE;

static SCRIPTED_SAMPLE samples[2];
static VOID *allocations[2];
static UINTN open_reads, path_reads, pci_reads, binding_reads, image_reads, releases;
static BOOLEAN change_path, change_pci, alias_buffer, change_image, empty_base, missing_binding, fail_release;

static EFI_STATUS EFIAPI
lookup(EFI_HANDLE handle, EFI_GUID *guid, VOID **interface)
{
    *interface = NULL;
    if (memcmp(guid, &path_guid, sizeof(*guid)) == 0) {
        CHECK(handle == &controller);
        ++path_reads;
        *interface = change_path && path_reads == 2 ? &other_path : &device_path;
    } else if (memcmp(guid, &pci_guid, sizeof(*guid)) == 0) {
        CHECK(handle == &controller);
        ++pci_reads;
        *interface = change_pci && pci_reads == 2 ? &other_pci : &pci;
    } else if (memcmp(guid, &binding_guid, sizeof(*guid)) == 0) {
        CHECK(handle == &manager);
        ++binding_reads;
        if (missing_binding)
            return EFI_UNSUPPORTED;
        *interface = &binding;
    } else if (memcmp(guid, &image_guid, sizeof(*guid)) == 0) {
        CHECK(handle == binding.ImageHandle);
        ++image_reads;
        loaded_image.ImageSize = change_image && image_reads == 2 ? 8192 : 4096;
        loaded_image.ImageBase = empty_base ? NULL : &image_memory;
        *interface = &loaded_image;
    } else {
        CHECK(FALSE);
    }
    return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
open_information(EFI_HANDLE handle, EFI_GUID *guid, EFI_OPEN_PROTOCOL_INFORMATION_ENTRY **entries, UINTN *count)
{
    CHECK(handle == &controller && memcmp(guid, &pci_guid, sizeof(*guid)) == 0);
    CHECK(path_reads == 1 && pci_reads == 1 && open_reads < 2);
    UINTN index = open_reads++;
    CONST SCRIPTED_SAMPLE *sample = &samples[index];
    *entries = NULL;
    *count = sample->count;
    if (sample->status != EFI_SUCCESS)
        return sample->status;
    if (sample->count == 2 && sample->rows[0].AgentHandle == NULL)
        return EFI_SUCCESS;
    if (alias_buffer && index == 1) {
        *entries = allocations[0];
        return EFI_SUCCESS;
    }
    allocations[index] = malloc(sizeof(sample->rows));
    CHECK(allocations[index] != NULL);
    memcpy(allocations[index], sample->rows, sizeof(sample->rows));
    *entries = allocations[index];
    return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
release_buffer(VOID *buffer)
{
    CHECK(buffer != NULL && (buffer == allocations[0] || buffer == allocations[1]));
    allocations[buffer == allocations[0] ? 0 : 1] = NULL;
    free(buffer);
    ++releases;
    return fail_release && releases == 1 ? EFI_INVALID_PARAMETER : EFI_SUCCESS;
}

static void
reset(void)
{
    samples[0] = (SCRIPTED_SAMPLE){
        .rows = {{&manager, &controller, EFI_OPEN_PROTOCOL_BY_DRIVER, 1},
                 {&manager, &child, EFI_OPEN_PROTOCOL_BY_CHILD_CONTROLLER, 1},
                 {&console, NULL, EFI_OPEN_PROTOCOL_BY_HANDLE_PROTOCOL, 2}},
        .count = 3
    };
    samples[1] = samples[0];
    samples[1].rows[0] = samples[0].rows[2];
    samples[1].rows[2] = samples[0].rows[0];
    binding = (EFI_DRIVER_BINDING_PROTOCOL){.ImageHandle = &image, .DriverBindingHandle = &manager};
    allocations[0] = allocations[1] = NULL;
    open_reads = path_reads = pci_reads = binding_reads = image_reads = releases = 0;
    change_path = change_pci = alias_buffer = change_image = empty_base = missing_binding = fail_release = FALSE;
}

typedef enum {
    REORDERED, EXCLUSIVE_MANAGER, SAME_IMAGE_HANDLE, NO_MANAGER, CHILD_ONLY, EMPTY, WRONG_FUNCTION,
    WRONG_INTERFACE, EXCLUSIVE_CLIENT, WRONG_CONTROLLER, TWO_MANAGERS, DUPLICATE, FOREIGN_CHILD,
    UNKNOWN_ATTRIBUTES, ZERO_OPEN_COUNT, OVERSIZED, NULL_LIST, OPEN_FAILED, LATE_OPEN_FAILED, WARNING_STATUS,
    CHANGED_COUNT, DISAPPEARED_ENTRY, CHANGED_MANAGER, CHANGED_PATH, CHANGED_PCI, MISSING_BINDING, WRONG_BINDING, NULL_IMAGE,
    EMPTY_IMAGE, CHANGED_IMAGE, ALIASED_BUFFER, FREE_FAILED, MISSING_SERVICES
} SCENARIO;

static void
exercise(SCENARIO scenario, EFI_STATUS expected, UINTN expected_releases)
{
    reset();
    EFI_BOOT_SERVICES boot = {.HandleProtocol = lookup, .OpenProtocolInformation = open_information, .FreePool = release_buffer};
    PHX34_PREBOOT_PCI_TARGET target = {&controller, &device_path, &pci};
    PHX34_PREBOOT_PCI_ATTRIBUTION attribution = {&console, &console, 123};

    switch (scenario) {
    case REORDERED: break;
    case EXCLUSIVE_MANAGER:
        samples[0].rows[0].Attributes |= EFI_OPEN_PROTOCOL_EXCLUSIVE;
        samples[1].rows[2].Attributes |= EFI_OPEN_PROTOCOL_EXCLUSIVE;
        break;
    case SAME_IMAGE_HANDLE: binding.ImageHandle = &manager; break;
    case NO_MANAGER: samples[0].rows[0].Attributes = EFI_OPEN_PROTOCOL_GET_PROTOCOL; break;
    case CHILD_ONLY: samples[0].rows[0] = samples[0].rows[1]; samples[0].count = 1; break;
    case EMPTY: samples[0].count = 0; break;
    case WRONG_FUNCTION: target.DevicePath = &other_path; break;
    case WRONG_INTERFACE: target.PciIo = &other_pci; break;
    case EXCLUSIVE_CLIENT: samples[0].rows[2].Attributes = EFI_OPEN_PROTOCOL_EXCLUSIVE; break;
    case WRONG_CONTROLLER: samples[0].rows[0].ControllerHandle = &child; break;
    case TWO_MANAGERS:
        samples[0].rows[3] = (EFI_OPEN_PROTOCOL_INFORMATION_ENTRY){&console, &controller, EFI_OPEN_PROTOCOL_BY_DRIVER, 1};
        samples[0].count = 4;
        break;
    case DUPLICATE: samples[0].rows[2] = samples[0].rows[0]; break;
    case FOREIGN_CHILD: samples[0].rows[1].AgentHandle = &console; break;
    case UNKNOWN_ATTRIBUTES: samples[0].rows[2].Attributes = 0; break;
    case ZERO_OPEN_COUNT: samples[0].rows[2].OpenCount = 0; break;
    case OVERSIZED: samples[0].count = 65; break;
    case NULL_LIST: samples[0].count = 2; samples[0].rows[0].AgentHandle = NULL; break;
    case OPEN_FAILED: samples[0].status = EFI_NOT_FOUND; break;
    case LATE_OPEN_FAILED: samples[1].status = EFI_OUT_OF_RESOURCES; break;
    case WARNING_STATUS: samples[1].status = EFI_WARN_UNKNOWN_GLYPH; break;
    case CHANGED_COUNT: ++samples[1].rows[0].OpenCount; break;
    case DISAPPEARED_ENTRY: samples[1].rows[0] = samples[1].rows[2]; samples[1].count = 2; break;
    case CHANGED_MANAGER: samples[1].rows[1].AgentHandle = samples[1].rows[2].AgentHandle = &console; break;
    case CHANGED_PATH: change_path = TRUE; break;
    case CHANGED_PCI: change_pci = TRUE; break;
    case MISSING_BINDING: missing_binding = TRUE; break;
    case WRONG_BINDING: binding.DriverBindingHandle = &console; break;
    case NULL_IMAGE: binding.ImageHandle = NULL; break;
    case EMPTY_IMAGE: empty_base = TRUE; break;
    case CHANGED_IMAGE: change_image = TRUE; break;
    case ALIASED_BUFFER: alias_buffer = TRUE; break;
    case FREE_FAILED: fail_release = TRUE; break;
    case MISSING_SERVICES: boot.OpenProtocolInformation = NULL; break;
    }

    EFI_STATUS actual = Phx34AttributePciManager(&boot, &target, &attribution);
    if (actual != expected)
        fprintf(stderr, "scenario %u returned %#llx, expected %#llx\n",
                (unsigned)scenario, (unsigned long long)actual, (unsigned long long)expected);
    CHECK(actual == expected);
    CHECK(releases == expected_releases && allocations[0] == NULL && allocations[1] == NULL);
    if (expected == EFI_SUCCESS) {
        CHECK(attribution.BindingHandle == &manager && attribution.ImageHandle == binding.ImageHandle &&
              attribution.OpenEntryCount == 3);
        CHECK(open_reads == 2 && path_reads == 2 && pci_reads == 2 && binding_reads == 2 && image_reads == 2);
    } else {
        CHECK(attribution.BindingHandle == NULL && attribution.ImageHandle == NULL && attribution.OpenEntryCount == 0);
    }
}

int main(void)
{
    CONST struct { SCENARIO scenario; EFI_STATUS expected; UINTN releases; } cases[] = {
        {REORDERED, EFI_SUCCESS, 2}, {EXCLUSIVE_MANAGER, EFI_SUCCESS, 2}, {SAME_IMAGE_HANDLE, EFI_SUCCESS, 2},
        {NO_MANAGER, EFI_NOT_FOUND, 1}, {CHILD_ONLY, EFI_NOT_FOUND, 1}, {EMPTY, EFI_NOT_FOUND, 1},
        {WRONG_FUNCTION, EFI_NO_MAPPING, 0}, {WRONG_INTERFACE, EFI_NO_MAPPING, 0},
        {EXCLUSIVE_CLIENT, EFI_ACCESS_DENIED, 1}, {WRONG_CONTROLLER, EFI_COMPROMISED_DATA, 1},
        {TWO_MANAGERS, EFI_COMPROMISED_DATA, 1}, {DUPLICATE, EFI_COMPROMISED_DATA, 1},
        {FOREIGN_CHILD, EFI_COMPROMISED_DATA, 1}, {UNKNOWN_ATTRIBUTES, EFI_COMPROMISED_DATA, 1},
        {ZERO_OPEN_COUNT, EFI_COMPROMISED_DATA, 1}, {OVERSIZED, EFI_COMPROMISED_DATA, 1},
        {NULL_LIST, EFI_COMPROMISED_DATA, 0}, {OPEN_FAILED, EFI_NOT_FOUND, 0},
        {LATE_OPEN_FAILED, EFI_OUT_OF_RESOURCES, 1}, {WARNING_STATUS, EFI_PROTOCOL_ERROR, 1},
        {CHANGED_COUNT, EFI_COMPROMISED_DATA, 2}, {DISAPPEARED_ENTRY, EFI_COMPROMISED_DATA, 2},
        {CHANGED_MANAGER, EFI_COMPROMISED_DATA, 2},
        {CHANGED_PATH, EFI_NO_MAPPING, 2}, {CHANGED_PCI, EFI_NO_MAPPING, 2},
        {MISSING_BINDING, EFI_UNSUPPORTED, 1}, {WRONG_BINDING, EFI_COMPROMISED_DATA, 1},
        {NULL_IMAGE, EFI_COMPROMISED_DATA, 1}, {EMPTY_IMAGE, EFI_COMPROMISED_DATA, 1},
        {CHANGED_IMAGE, EFI_COMPROMISED_DATA, 2}, {ALIASED_BUFFER, EFI_COMPROMISED_DATA, 1},
        {FREE_FAILED, EFI_DEVICE_ERROR, 2}, {MISSING_SERVICES, EFI_INVALID_PARAMETER, 0}
    };
    for (UINTN index = 0; index < sizeof(cases) / sizeof(*cases); ++index)
        exercise(cases[index].scenario, cases[index].expected, cases[index].releases);
    printf("PASS %zu preboot attribution scenarios (CPU Boot Services fixture only)\n", sizeof(cases) / sizeof(*cases));
    return EXIT_SUCCESS;
}
