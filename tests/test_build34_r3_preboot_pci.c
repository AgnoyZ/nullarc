#include "build34_r3_preboot_pci.h"

#include <Pi/PiFirmwareFile.h>
#include <Pi/PiFirmwareVolume.h>
#include <Protocol/DriverBinding.h>
#include <Protocol/FirmwareVolume2.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/PciRootBridgeIo.h>

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
static const EFI_GUID root_guid = EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL_GUID;
static const EFI_GUID path_guid = EFI_DEVICE_PATH_PROTOCOL_GUID;
static const EFI_GUID binding_guid = EFI_DRIVER_BINDING_PROTOCOL_GUID;
static const EFI_GUID image_guid = EFI_LOADED_IMAGE_PROTOCOL_GUID;
static const EFI_GUID fv_guid = EFI_FIRMWARE_VOLUME2_PROTOCOL_GUID;
static const EFI_GUID zero_guid = {0};

static UINT8 controller, manager, image, child, console, image_memory, root_handle, other_root_handle, other_controller;
static EFI_DEVICE_PATH_PROTOCOL device_path, other_path;
static EFI_PCI_IO_PROTOCOL pci, other_pci;
static EFI_DRIVER_BINDING_PROTOCOL binding;
static EFI_LOADED_IMAGE_PROTOCOL loaded_image;
static UINT8 volume, other_volume;
static EFI_FIRMWARE_VOLUME2_PROTOCOL fv, other_fv;
static UINTN volume_reads;
static EFI_DEVICE_PATH_PROTOCOL *published_path;
static UINTN target_reads_at_sample;

typedef enum {
    LOCATION_OK, SHORT_SEAL, LONG_SEAL, BAD_ROOT, BAD_BRIDGE, BAD_TERMINATOR, WRONG_SEALED_FUNCTION,
    BAD_SEGMENT, BAD_BUS, BAD_DEVICE, BAD_FUNCTION, NO_ADMITTED_READER, NO_LOCATE_SERVICE,
    LOCATE_FAILED, PREFIX_MATCH, FOREIGN_REMAINDER, NULL_CONTROLLER, TAMPERED_LOOKUP,
    SHORT_PUBLISHED_PATH, CHANGED_PUBLISHED_PATH, UNKNOWN_READER, LOCATION_FAILED, LOCATION_WARNING,
    PARTIAL_LOCATION, WRONG_LOCATION_BUS, WRONG_LOCATION_SEGMENT, WRONG_LOCATION_DEVICE, WRONG_LOCATION_FUNCTION,
    LATE_LOCATE_FAILED, LATE_LOCATION_CHANGED, LATE_PCI_REPLACED, LATE_READER_REPLACED,
    ROOT_MISSING, ROOT_PREFIX, ROOT_PATH_CHANGED, ROOT_IO_MISSING, ROOT_WRONG_SEGMENT,
    ROOT_LATE_SEGMENT, ROOT_LATE_HANDLE, ROOT_LATE_PATH, ROOT_LATE_IO
} LOCATION_SCENARIO;

static LOCATION_SCENARIO location_scenario;
static UINTN location_reads, locate_calls, root_locates, root_io_reads;

typedef enum {
    PATH_OK, PATH_NULL_ACCESSOR, PATH_NO_SERVICE, PATH_BAD_SEAL, PATH_UNKNOWN_SEGMENT, PATH_NO_PCI_HANDLES,
    PATH_OVERSIZED_HANDLES, PATH_PARTIAL_HANDLE, PATH_NULL_HANDLE, PATH_PREFIX_ONLY, PATH_DUP_ROOT,
    PATH_DUP_ENDPOINT, PATH_LATE_DUP_ENDPOINT, PATH_LATE_ENDPOINT_REPLACED, PATH_LATE_ROOT_REPLACED,
    PATH_FV_OK, PATH_OTHER_ORIGIN, PATH_FV_BAD_REVISION, PATH_FV_BAD_NODE, PATH_FV_NO_END, PATH_FV_ZERO_GUID,
    PATH_FV_NO_HANDLE, PATH_FV_IMAGE_HANDLE, PATH_FV_MISSING, PATH_FV_NULL, PATH_FV_WARNING, PATH_FV_LATE_GUID,
    PATH_FV_LATE_PATH, PATH_FV_LATE_VOLUME, PATH_FV_LATE_INTERFACE, PATH_FV_LATE_NON_FV,
    PATH_FV_CHANGED_DURING_LOOKUP, PATH_FV_CHANGED_GUID_DURING_LOOKUP, PATH_FV_CHANGED_END_DURING_LOOKUP
} PATH_SCENARIO;

static PATH_SCENARIO path_scenario;

typedef struct {
    MEDIA_FW_VOL_FILEPATH_DEVICE_PATH File;
    EFI_DEVICE_PATH_PROTOCOL End;
} FIXTURE_FV_PATH;

static const FIXTURE_FV_PATH valid_fv_path = {
    .File = {
        .Header = {MEDIA_DEVICE_PATH, MEDIA_PIWG_FW_FILE_DP, {sizeof(MEDIA_FW_VOL_FILEPATH_DEVICE_PATH), 0}},
        .FvFileName = {0x12345678, 0x4321, 0xabcd, {1, 2, 3, 4, 5, 6, 7, 8}},
    },
    .End = {END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, {sizeof(EFI_DEVICE_PATH_PROTOCOL), 0}},
};
static FIXTURE_FV_PATH fv_path, other_fv_path;

typedef struct {
    ACPI_HID_DEVICE_PATH Root;
    PCI_DEVICE_PATH Bridge, Endpoint;
    EFI_DEVICE_PATH_PROTOCOL End;
} FIXTURE_PATH;

static const FIXTURE_PATH valid_path = {
    .Root = {{ACPI_DEVICE_PATH, ACPI_DP, {sizeof(ACPI_HID_DEVICE_PATH), 0}}, EISA_PNP_ID(0x0A08), 0},
    .Bridge = {{HARDWARE_DEVICE_PATH, HW_PCI_DP, {sizeof(PCI_DEVICE_PATH), 0}}, 0, 4},
    .Endpoint = {{HARDWARE_DEVICE_PATH, HW_PCI_DP, {sizeof(PCI_DEVICE_PATH), 0}}, 3, 16},
    .End = {END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, {sizeof(EFI_DEVICE_PATH_PROTOCOL), 0}}
};

static FIXTURE_PATH sealed_path, installed_path;
static struct { ACPI_HID_DEVICE_PATH Root; PCI_DEVICE_PATH Bridge; EFI_DEVICE_PATH_PROTOCOL End; } prefix;
static struct ROOT_PATH { ACPI_HID_DEVICE_PATH Root; EFI_DEVICE_PATH_PROTOCOL End; } root_path, other_root_path;
static EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL root_io, other_root_io;

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
        if (handle == &root_handle || handle == &other_root_handle) {
            *interface = root_locates == 2 && location_scenario == ROOT_LATE_PATH ? &other_root_path : &root_path;
            return EFI_SUCCESS;
        }
        if (handle == &child || handle == &other_controller) {
            *interface = handle == &child ? &prefix.Root.Header : published_path;
            return EFI_SUCCESS;
        }
        if (handle == &console)
            return EFI_UNSUPPORTED;
        CHECK(handle == &controller);
        ++path_reads;
        *interface = change_path && path_reads == 2 ? &other_path : published_path;
    } else if (memcmp(guid, &root_guid, sizeof(*guid)) == 0) {
        CHECK(handle == &root_handle || handle == &other_root_handle);
        CHECK(++root_io_reads == root_locates);
        if (location_scenario == ROOT_IO_MISSING)
            return EFI_UNSUPPORTED;
        if (root_locates == 2 && location_scenario == ROOT_LATE_SEGMENT)
            ++root_io.SegmentNumber;
        *interface = root_locates == 2 && location_scenario == ROOT_LATE_IO ? &other_root_io : &root_io;
    } else if (memcmp(guid, &pci_guid, sizeof(*guid)) == 0) {
        CHECK(handle == &controller);
        ++pci_reads;
        *interface = (change_pci && pci_reads == 2) ||
                     (location_scenario == LATE_PCI_REPLACED && pci_reads == 4) ? &other_pci : &pci;
        if (location_scenario == LATE_READER_REPLACED && pci_reads == 4)
            pci.GetLocation = NULL;
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
        if (image_reads == 2) {
            if (path_scenario == PATH_FV_LATE_GUID)
                ++fv_path.File.FvFileName.Data1;
            if (path_scenario == PATH_FV_LATE_PATH)
                loaded_image.FilePath = &other_fv_path.File.Header;
            if (path_scenario == PATH_FV_LATE_VOLUME)
                loaded_image.DeviceHandle = &other_volume;
            if (path_scenario == PATH_FV_LATE_NON_FV)
                loaded_image.FilePath = &installed_path.Root.Header;
        }
        *interface = &loaded_image;
    } else if (memcmp(guid, &fv_guid, sizeof(*guid)) == 0) {
        CHECK(handle == loaded_image.DeviceHandle && (handle == &volume || handle == &other_volume));
        CHECK(++volume_reads == image_reads);
        if (path_scenario == PATH_FV_MISSING)
            return EFI_UNSUPPORTED;
        if (path_scenario == PATH_FV_WARNING)
            return EFI_WARN_UNKNOWN_GLYPH;
        if (path_scenario != PATH_FV_NULL)
            *interface = path_scenario == PATH_FV_LATE_INTERFACE && volume_reads == 2 ? &other_fv : &fv;
        if (volume_reads == 2 && path_scenario == PATH_FV_CHANGED_DURING_LOOKUP)
            loaded_image.DeviceHandle = &other_volume;
        if (volume_reads == 2 && path_scenario == PATH_FV_CHANGED_GUID_DURING_LOOKUP)
            ++fv_path.File.FvFileName.Data1;
        if (volume_reads == 2 && path_scenario == PATH_FV_CHANGED_END_DURING_LOOKUP)
            fv_path.End.SubType = END_INSTANCE_DEVICE_PATH_SUBTYPE;
    } else {
        CHECK(FALSE);
    }
    return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
open_information(EFI_HANDLE handle, EFI_GUID *guid, EFI_OPEN_PROTOCOL_INFORMATION_ENTRY **entries, UINTN *count)
{
    CHECK(handle == &controller && memcmp(guid, &pci_guid, sizeof(*guid)) == 0);
    CHECK(path_reads == target_reads_at_sample && pci_reads == target_reads_at_sample && open_reads < 2);
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
    loaded_image = (EFI_LOADED_IMAGE_PROTOCOL){.Revision = EFI_LOADED_IMAGE_PROTOCOL_REVISION};
    fv_path = other_fv_path = valid_fv_path;
    allocations[0] = allocations[1] = NULL;
    open_reads = path_reads = pci_reads = binding_reads = image_reads = releases = 0;
    location_reads = locate_calls = root_locates = root_io_reads = 0;
    volume_reads = 0;
    target_reads_at_sample = 1;
    location_scenario = LOCATION_OK;
    path_scenario = PATH_OK;
    published_path = &device_path;
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

static EFI_STATUS EFIAPI
locate(EFI_GUID *guid, EFI_DEVICE_PATH_PROTOCOL **path, EFI_HANDLE *handle)
{
    if (memcmp(guid, &root_guid, sizeof(*guid)) == 0) {
        CHECK(memcmp(*path, &valid_path.Root, sizeof(valid_path.Root)) == 0 && root_locates < 2);
        ++root_locates;
        if (location_scenario == ROOT_MISSING)
            return EFI_NOT_FOUND;
        if (location_scenario != ROOT_PREFIX)
            *path = (EFI_DEVICE_PATH_PROTOCOL *)((UINT8 *)*path + sizeof(ACPI_HID_DEVICE_PATH));
        CHECK(memcmp(*path, location_scenario == ROOT_PREFIX ? (const VOID *)&valid_path.Root : &valid_path.End,
                     sizeof(EFI_DEVICE_PATH_PROTOCOL)) == 0);
        *handle = root_locates == 2 && location_scenario == ROOT_LATE_HANDLE ? &other_root_handle : &root_handle;
        return EFI_SUCCESS;
    }
    CHECK(memcmp(guid, &pci_guid, sizeof(*guid)) == 0 && *path != &sealed_path.Root.Header);
    CHECK(root_locates == 1 && root_io_reads == 1);
    CHECK(memcmp(*path, &valid_path, sizeof(valid_path)) == 0 && locate_calls < 2);
    ++locate_calls;
    if (location_scenario == LOCATE_FAILED || (location_scenario == LATE_LOCATE_FAILED && locate_calls == 2))
        return EFI_NOT_FOUND;
    UINT8 *bytes = (UINT8 *)*path;
    if (location_scenario == TAMPERED_LOOKUP)
        bytes[OFFSET_OF(ACPI_HID_DEVICE_PATH, UID)] ^= 1;
    *path = (EFI_DEVICE_PATH_PROTOCOL *)(bytes + OFFSET_OF(FIXTURE_PATH, End));
    if (location_scenario == PREFIX_MATCH)
        *path = (EFI_DEVICE_PATH_PROTOCOL *)(bytes + OFFSET_OF(FIXTURE_PATH, Endpoint));
    if (location_scenario == FOREIGN_REMAINDER)
        *path = &installed_path.End;
    *handle = location_scenario == NULL_CONTROLLER ? NULL : &controller;
    return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
get_location(EFI_PCI_IO_PROTOCOL *interface, UINTN *segment, UINTN *bus, UINTN *device, UINTN *function)
{
    CHECK(interface == &pci || interface == &other_pci);
    CHECK(++location_reads <= 2);
    if (location_scenario == LOCATION_FAILED)
        return EFI_DEVICE_ERROR;
    if (location_scenario == LOCATION_WARNING)
        return EFI_WARN_UNKNOWN_GLYPH;
    *segment = location_scenario == WRONG_LOCATION_SEGMENT ? 3 : 2;
    *bus = location_scenario == WRONG_LOCATION_BUS ||
           (location_scenario == LATE_LOCATION_CHANGED && location_reads == 2) ? 36 : 37;
    *device = location_scenario == WRONG_LOCATION_DEVICE ? 17 : 16;
    if (location_scenario != PARTIAL_LOCATION)
        *function = location_scenario == WRONG_LOCATION_FUNCTION ? 4 : 3;
    return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
enumerate_handles(EFI_LOCATE_SEARCH_TYPE search, EFI_GUID *guid, VOID *key, UINTN *size, EFI_HANDLE *handles)
{
    CHECK(search == ByProtocol && key == NULL && *size == 256 * sizeof(*handles));
    if (memcmp(guid, &root_guid, sizeof(*guid)) == 0) {
        CHECK(++root_locates <= 2);
        handles[0] = &root_handle;
        if (path_scenario == PATH_DUP_ROOT) {
            handles[1] = &other_root_handle;
            *size = 2 * sizeof(*handles);
        } else {
            *size = sizeof(*handles);
        }
        return EFI_SUCCESS;
    }
    CHECK(memcmp(guid, &pci_guid, sizeof(*guid)) == 0 && ++locate_calls <= 2);
    CHECK(root_locates == 1 && root_io_reads == 1);
    if (path_scenario == PATH_NO_PCI_HANDLES)
        return EFI_NOT_FOUND;
    if (path_scenario == PATH_OVERSIZED_HANDLES) {
        *size += sizeof(*handles);
        return EFI_BUFFER_TOO_SMALL;
    }
    handles[0] = &child;
    handles[1] = &console;
    handles[2] = path_scenario == PATH_NULL_HANDLE ? NULL : &controller;
    *size = (path_scenario == PATH_PREFIX_ONLY ? 2 : 3) * sizeof(*handles);
    if (path_scenario == PATH_PARTIAL_HANDLE)
        --*size;
    if (path_scenario == PATH_DUP_ENDPOINT || (path_scenario == PATH_LATE_DUP_ENDPOINT && locate_calls == 2)) {
        handles[3] = &other_controller;
        *size += sizeof(*handles);
    }
    return EFI_SUCCESS;
}

static void
exercise_path(PATH_SCENARIO scenario, EFI_STATUS expected, UINTN snapshots, UINTN expected_volume_reads)
{
    reset();
    path_scenario = scenario;
    target_reads_at_sample = 2;
    sealed_path = installed_path = valid_path;
    published_path = &installed_path.Root.Header;
    prefix.Root = valid_path.Root;
    prefix.Bridge = valid_path.Bridge;
    prefix.End = valid_path.End;
    root_path = other_root_path = (struct ROOT_PATH){valid_path.Root, valid_path.End};
    root_io = other_root_io = (EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL){.SegmentNumber = 2};
    pci.GetLocation = other_pci.GetLocation = get_location;
    EFI_BOOT_SERVICES boot = {.HandleProtocol = lookup, .OpenProtocolInformation = open_information,
                              .FreePool = release_buffer, .LocateHandle = enumerate_handles};
    PHX34_PREBOOT_PCI_PATH_IDENTITY identity = {(const UINT8 *)&sealed_path, sizeof(sealed_path), 2};
    PHX34_PREBOOT_PCI_PATH_OBSERVATION observation = {
        .Candidate = {.BindingHandle = &console, .ImageHandle = &console, .OpenEntryCount = 123},
        .FirmwareFile = {.VolumeHandle = &console, .FileGuid = valid_fv_path.File.FvFileName},
    };
    if (scenario >= PATH_FV_OK || scenario == PATH_LATE_ROOT_REPLACED) {
        loaded_image.FilePath = &fv_path.File.Header;
        loaded_image.DeviceHandle = &volume;
    }

    switch (scenario) {
    case PATH_NULL_ACCESSOR: pci.GetLocation = NULL; break;
    case PATH_NO_SERVICE: boot.LocateHandle = NULL; break;
    case PATH_BAD_SEAL: sealed_path.End.SubType = END_INSTANCE_DEVICE_PATH_SUBTYPE; break;
    case PATH_UNKNOWN_SEGMENT: ++identity.Segment; break;
    case PATH_LATE_ENDPOINT_REPLACED: location_scenario = LATE_PCI_REPLACED; break;
    case PATH_LATE_ROOT_REPLACED: location_scenario = ROOT_LATE_IO; break;
    case PATH_OTHER_ORIGIN: loaded_image.FilePath = &installed_path.Root.Header; break;
    case PATH_FV_BAD_REVISION: --loaded_image.Revision; break;
    case PATH_FV_BAD_NODE: --fv_path.File.Header.Length[0]; break;
    case PATH_FV_NO_END: fv_path.End.SubType = END_INSTANCE_DEVICE_PATH_SUBTYPE; break;
    case PATH_FV_ZERO_GUID: fv_path.File.FvFileName = zero_guid; break;
    case PATH_FV_NO_HANDLE: loaded_image.DeviceHandle = NULL; break;
    case PATH_FV_IMAGE_HANDLE: loaded_image.DeviceHandle = &image; break;
    default: break;
    }

    EFI_STATUS actual = Phx34ObservePciManagerAtPath(&boot, &identity, &observation);
    if (actual != expected)
        fprintf(stderr, "path scenario %u returned %#llx, expected %#llx\n",
                (unsigned)scenario, (unsigned long long)actual, (unsigned long long)expected);
    CHECK(actual == expected && location_reads == 0 && open_reads == snapshots && releases == snapshots);
    CHECK(volume_reads == expected_volume_reads);
    CHECK(allocations[0] == NULL && allocations[1] == NULL);
    CONST PHX34_PREBOOT_PCI_ATTRIBUTION *candidate = &observation.Candidate;
    if (expected == EFI_SUCCESS) {
        CHECK(candidate->BindingHandle == &manager && candidate->ImageHandle == &image && candidate->OpenEntryCount == 3);
        CHECK(locate_calls == 2 && root_locates == 2 && root_io_reads == 2 && pci_reads == 4);
    } else {
        CHECK(candidate->BindingHandle == NULL && candidate->ImageHandle == NULL && candidate->OpenEntryCount == 0);
    }
    BOOLEAN has_fv = scenario == PATH_FV_OK;
    CONST EFI_GUID *expected_guid = has_fv ? &valid_fv_path.File.FvFileName : &zero_guid;
    CHECK(observation.FirmwareFile.VolumeHandle == (has_fv ? &volume : NULL));
    CHECK(memcmp(&observation.FirmwareFile.FileGuid, expected_guid, sizeof(*expected_guid)) == 0);
}

static void
exercise_location(LOCATION_SCENARIO scenario, EFI_STATUS expected, UINTN locates, UINTN reads, UINTN snapshots)
{
    reset();
    location_scenario = scenario;
    target_reads_at_sample = 2;
    sealed_path = installed_path = valid_path;
    published_path = &installed_path.Root.Header;
    root_path = other_root_path = (struct ROOT_PATH){valid_path.Root, valid_path.End};
    root_io = other_root_io = (EFI_PCI_ROOT_BRIDGE_IO_PROTOCOL){.SegmentNumber = 2};
    pci.GetLocation = other_pci.GetLocation = get_location;
    EFI_BOOT_SERVICES boot = {.HandleProtocol = lookup, .OpenProtocolInformation = open_information,
                              .FreePool = release_buffer, .LocateDevicePath = locate};
    PHX34_PREBOOT_PCI_IDENTITY identity = {(const UINT8 *)&sealed_path, sizeof(sealed_path), 2, 37, 16, 3, get_location};
    PHX34_PREBOOT_PCI_ATTRIBUTION attribution = {&console, &console, 123};

    switch (scenario) {
    case SHORT_SEAL: --identity.DevicePathBytes; break;
    case LONG_SEAL: identity.DevicePathBytes = 257; break;
    case BAD_ROOT: sealed_path.Root.Header.Length[0] = 0; break;
    case BAD_BRIDGE: sealed_path.Bridge.Function = 8; break;
    case BAD_TERMINATOR: sealed_path.End.SubType = END_INSTANCE_DEVICE_PATH_SUBTYPE; break;
    case WRONG_SEALED_FUNCTION: ++sealed_path.Endpoint.Function; break;
    case BAD_SEGMENT: identity.Segment = 65536; break;
    case BAD_BUS: identity.Bus = 256; break;
    case BAD_DEVICE: identity.Device = 32; break;
    case BAD_FUNCTION: identity.Function = 8; break;
    case NO_ADMITTED_READER: identity.ReadLocation = NULL; break;
    case NO_LOCATE_SERVICE: boot.LocateDevicePath = NULL; break;
    case SHORT_PUBLISHED_PATH:
        prefix.Root = valid_path.Root;
        prefix.Bridge = valid_path.Bridge;
        prefix.End = valid_path.End;
        published_path = &prefix.Root.Header;
        break;
    case CHANGED_PUBLISHED_PATH: installed_path.Root.UID ^= 1; break;
    case UNKNOWN_READER: pci.GetLocation = NULL; break;
    case ROOT_PATH_CHANGED: root_path.Root.UID ^= 1; break;
    case ROOT_WRONG_SEGMENT: ++root_io.SegmentNumber; break;
    default: break;
    }

    EFI_STATUS actual = Phx34AttributePciManagerAtLocation(&boot, &identity, &attribution);
    if (actual != expected)
        fprintf(stderr, "location scenario %u returned %#llx, expected %#llx\n",
                (unsigned)scenario, (unsigned long long)actual, (unsigned long long)expected);
    CHECK(actual == expected);
    CHECK(locate_calls == locates && location_reads == reads && open_reads == snapshots);
    CHECK(releases == snapshots && allocations[0] == NULL && allocations[1] == NULL);
    if (expected == EFI_SUCCESS) {
        CHECK(attribution.BindingHandle == &manager && attribution.ImageHandle == &image && attribution.OpenEntryCount == 3);
        CHECK(path_reads == 4 && pci_reads == 4 && binding_reads == 2 && image_reads == 2 &&
              root_locates == 2 && root_io_reads == 2);
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
    CONST struct { LOCATION_SCENARIO scenario; EFI_STATUS expected; UINTN locates, reads, snapshots; } locations[] = {
        {LOCATION_OK, EFI_SUCCESS, 2, 2, 2}, {SHORT_SEAL, EFI_INVALID_PARAMETER, 0, 0, 0},
        {LONG_SEAL, EFI_INVALID_PARAMETER, 0, 0, 0}, {BAD_ROOT, EFI_INVALID_PARAMETER, 0, 0, 0},
        {BAD_BRIDGE, EFI_INVALID_PARAMETER, 0, 0, 0}, {BAD_TERMINATOR, EFI_INVALID_PARAMETER, 0, 0, 0},
        {WRONG_SEALED_FUNCTION, EFI_INVALID_PARAMETER, 0, 0, 0},
        {BAD_SEGMENT, EFI_INVALID_PARAMETER, 0, 0, 0}, {BAD_BUS, EFI_INVALID_PARAMETER, 0, 0, 0},
        {BAD_DEVICE, EFI_INVALID_PARAMETER, 0, 0, 0}, {BAD_FUNCTION, EFI_INVALID_PARAMETER, 0, 0, 0},
        {NO_ADMITTED_READER, EFI_INVALID_PARAMETER, 0, 0, 0}, {NO_LOCATE_SERVICE, EFI_INVALID_PARAMETER, 0, 0, 0},
        {LOCATE_FAILED, EFI_NOT_FOUND, 1, 0, 0}, {PREFIX_MATCH, EFI_NO_MAPPING, 1, 0, 0},
        {FOREIGN_REMAINDER, EFI_NO_MAPPING, 1, 0, 0}, {NULL_CONTROLLER, EFI_NO_MAPPING, 1, 0, 0},
        {TAMPERED_LOOKUP, EFI_NO_MAPPING, 1, 0, 0}, {SHORT_PUBLISHED_PATH, EFI_NO_MAPPING, 1, 0, 0},
        {CHANGED_PUBLISHED_PATH, EFI_NO_MAPPING, 1, 0, 0}, {UNKNOWN_READER, EFI_UNSUPPORTED, 1, 0, 0},
        {LOCATION_FAILED, EFI_DEVICE_ERROR, 1, 1, 0}, {LOCATION_WARNING, EFI_PROTOCOL_ERROR, 1, 1, 0},
        {PARTIAL_LOCATION, EFI_NO_MAPPING, 1, 1, 0}, {WRONG_LOCATION_BUS, EFI_NO_MAPPING, 1, 1, 0},
        {WRONG_LOCATION_SEGMENT, EFI_NO_MAPPING, 1, 1, 0}, {WRONG_LOCATION_DEVICE, EFI_NO_MAPPING, 1, 1, 0},
        {WRONG_LOCATION_FUNCTION, EFI_NO_MAPPING, 1, 1, 0}, {LATE_LOCATE_FAILED, EFI_NOT_FOUND, 2, 1, 2},
        {LATE_LOCATION_CHANGED, EFI_NO_MAPPING, 2, 2, 2}, {LATE_PCI_REPLACED, EFI_NO_MAPPING, 2, 2, 2},
        {LATE_READER_REPLACED, EFI_UNSUPPORTED, 2, 1, 2},
        {ROOT_MISSING, EFI_NOT_FOUND, 0, 0, 0}, {ROOT_PREFIX, EFI_NO_MAPPING, 0, 0, 0},
        {ROOT_PATH_CHANGED, EFI_NO_MAPPING, 0, 0, 0}, {ROOT_IO_MISSING, EFI_UNSUPPORTED, 0, 0, 0},
        {ROOT_WRONG_SEGMENT, EFI_NO_MAPPING, 0, 0, 0}, {ROOT_LATE_SEGMENT, EFI_NO_MAPPING, 2, 2, 2},
        {ROOT_LATE_HANDLE, EFI_NO_MAPPING, 2, 2, 2}, {ROOT_LATE_PATH, EFI_NO_MAPPING, 2, 2, 2},
        {ROOT_LATE_IO, EFI_NO_MAPPING, 2, 2, 2}
    };
    for (UINTN index = 0; index < sizeof(locations) / sizeof(*locations); ++index)
        exercise_location(locations[index].scenario, locations[index].expected, locations[index].locates,
                          locations[index].reads, locations[index].snapshots);
    printf("PASS %zu exact preboot PCI selection scenarios (CPU fixture only)\n", sizeof(locations) / sizeof(*locations));
    CONST struct { PATH_SCENARIO scenario; EFI_STATUS expected; UINTN snapshots, volume_reads; } paths[] = {
        {PATH_OK, EFI_SUCCESS, 2, 0}, {PATH_NULL_ACCESSOR, EFI_SUCCESS, 2, 0},
        {PATH_NO_SERVICE, EFI_INVALID_PARAMETER, 0, 0}, {PATH_BAD_SEAL, EFI_INVALID_PARAMETER, 0, 0},
        {PATH_UNKNOWN_SEGMENT, EFI_NO_MAPPING, 0, 0}, {PATH_NO_PCI_HANDLES, EFI_NOT_FOUND, 0, 0},
        {PATH_OVERSIZED_HANDLES, EFI_BUFFER_TOO_SMALL, 0, 0}, {PATH_PARTIAL_HANDLE, EFI_COMPROMISED_DATA, 0, 0},
        {PATH_NULL_HANDLE, EFI_COMPROMISED_DATA, 0, 0}, {PATH_PREFIX_ONLY, EFI_NOT_FOUND, 0, 0},
        {PATH_DUP_ROOT, EFI_NO_MAPPING, 0, 0}, {PATH_DUP_ENDPOINT, EFI_NO_MAPPING, 0, 0},
        {PATH_LATE_DUP_ENDPOINT, EFI_NO_MAPPING, 2, 0}, {PATH_LATE_ENDPOINT_REPLACED, EFI_NO_MAPPING, 2, 0},
        {PATH_LATE_ROOT_REPLACED, EFI_NO_MAPPING, 2, 2},
        {PATH_FV_OK, EFI_SUCCESS, 2, 2}, {PATH_OTHER_ORIGIN, EFI_SUCCESS, 2, 0},
        {PATH_FV_BAD_REVISION, EFI_COMPROMISED_DATA, 1, 0}, {PATH_FV_BAD_NODE, EFI_COMPROMISED_DATA, 1, 0},
        {PATH_FV_NO_END, EFI_COMPROMISED_DATA, 1, 0}, {PATH_FV_ZERO_GUID, EFI_COMPROMISED_DATA, 1, 0},
        {PATH_FV_NO_HANDLE, EFI_COMPROMISED_DATA, 1, 0}, {PATH_FV_IMAGE_HANDLE, EFI_COMPROMISED_DATA, 1, 0},
        {PATH_FV_MISSING, EFI_UNSUPPORTED, 1, 1}, {PATH_FV_NULL, EFI_COMPROMISED_DATA, 1, 1},
        {PATH_FV_WARNING, EFI_PROTOCOL_ERROR, 1, 1}, {PATH_FV_LATE_GUID, EFI_COMPROMISED_DATA, 2, 2},
        {PATH_FV_LATE_PATH, EFI_COMPROMISED_DATA, 2, 2}, {PATH_FV_LATE_VOLUME, EFI_COMPROMISED_DATA, 2, 2},
        {PATH_FV_LATE_INTERFACE, EFI_COMPROMISED_DATA, 2, 2}, {PATH_FV_LATE_NON_FV, EFI_COMPROMISED_DATA, 2, 1},
        {PATH_FV_CHANGED_DURING_LOOKUP, EFI_COMPROMISED_DATA, 2, 2},
        {PATH_FV_CHANGED_GUID_DURING_LOOKUP, EFI_COMPROMISED_DATA, 2, 2},
        {PATH_FV_CHANGED_END_DURING_LOOKUP, EFI_COMPROMISED_DATA, 2, 2},
    };
    for (UINTN index = 0; index < sizeof(paths) / sizeof(*paths); ++index)
        exercise_path(paths[index].scenario, paths[index].expected, paths[index].snapshots, paths[index].volume_reads);
    printf("PASS %zu preboot path-only observation scenarios (CPU fixture only)\n", sizeof(paths) / sizeof(*paths));
    return EXIT_SUCCESS;
}
