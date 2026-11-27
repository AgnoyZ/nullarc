#include "build34_uma_boot_map.h"

enum {
    BOOT_ARGS_LENGTH = 4096,
    BOOT_REVISION_OFFSET = 0,
    BOOT_VERSION_OFFSET = 2,
    BOOT_EFI_MODE_OFFSET = 4,
    BOOT_MAP_ADDRESS_OFFSET = 1032,
    BOOT_MAP_SIZE_OFFSET = 1036,
    BOOT_MAP_STRIDE_OFFSET = 1040,
    BOOT_MAP_VERSION_OFFSET = 1044,
    EFI_DESCRIPTOR_LENGTH = 40,
    EFI_TYPE_OFFSET = 0,
    EFI_PHYSICAL_OFFSET = 8,
    EFI_PAGES_OFFSET = 24,
    EFI_ATTRIBUTES_OFFSET = 32,
    EFI_MAX_DESCRIPTORS = 256,
    EFI_MAX_MAP_LENGTH = 1 << 20,
    PAGE_SHIFT = 12,
    PAGE_BYTES = 1 << PAGE_SHIFT,
};

static uint64_t read_le(const uint8_t *bytes, unsigned width)
{
    uint64_t word = 0;
    for (unsigned index = 0; index < width; ++index)
        word |= (uint64_t)bytes[index] << (index * 8);
    return word;
}

enum phx34_boot_map_class phx34_classify_boot_map(const void *boot_args, size_t boot_args_length,
                                                 struct phx34_boot_map_view map,
                                                 uint64_t candidate_base, uint64_t candidate_length)
{
    const uint64_t address_limit = UINT64_C(1) << 48;
    const uint64_t map_address_limit = UINT64_C(1) << 32;
    const uint64_t runtime = UINT64_C(1) << 63;
    if (!boot_args || boot_args_length != BOOT_ARGS_LENGTH || !map.bytes ||
        !candidate_base || candidate_base >= address_limit || !candidate_length ||
        candidate_length > (UINT64_C(64) << 20) || candidate_length > address_limit - candidate_base ||
        ((candidate_base | candidate_length) & (PAGE_BYTES - 1)))
        return PHX34_BOOT_MAP_REFUSED;

    const uint8_t *args = boot_args;
    if (read_le(args + BOOT_REVISION_OFFSET, 2) > 1 || read_le(args + BOOT_VERSION_OFFSET, 2) != 2 ||
        args[BOOT_EFI_MODE_OFFSET] != 64 || read_le(args + BOOT_MAP_VERSION_OFFSET, 4) != 1)
        return PHX34_BOOT_MAP_REFUSED;

    const uint64_t map_address = read_le(args + BOOT_MAP_ADDRESS_OFFSET, 4);
    const uint64_t length = read_le(args + BOOT_MAP_SIZE_OFFSET, 4);
    const uint64_t stride = read_le(args + BOOT_MAP_STRIDE_OFFSET, 4);
    if (!map_address || (map_address & 7) || map_address != map.physical_base || length != map.length ||
        length > EFI_MAX_MAP_LENGTH || length > map_address_limit - map_address ||
        stride < EFI_DESCRIPTOR_LENGTH || stride > length || (stride & 7) || length % stride ||
        length / stride > EFI_MAX_DESCRIPTORS)
        return PHX34_BOOT_MAP_REFUSED;

    const uint64_t base = candidate_base >> PAGE_SHIFT;
    const uint64_t end = (candidate_base + candidate_length) >> PAGE_SHIFT;
    const uint8_t *data = map.bytes;
    uint64_t covered = 0;
    enum phx34_boot_map_class overlap = PHX34_BOOT_MAP_INCOMPLETE;
    for (size_t offset = 0; offset < length; offset += stride) {
        const uint8_t *entry = data + offset;
        const uint64_t physical = read_le(entry + EFI_PHYSICAL_OFFSET, 8);
        const uint64_t pages = read_le(entry + EFI_PAGES_OFFSET, 8);
        const uint64_t start = physical >> PAGE_SHIFT;
        if ((physical & (PAGE_BYTES - 1)) || !pages || pages > (UINT64_C(1) << (64 - PAGE_SHIFT)) - start)
            return PHX34_BOOT_MAP_REFUSED;
        const uint64_t stop = start + pages;

        for (size_t prior = 0; prior < offset; prior += stride) {
            const uint8_t *previous = data + prior;
            const uint64_t previous_start = read_le(previous + EFI_PHYSICAL_OFFSET, 8) >> PAGE_SHIFT;
            const uint64_t previous_stop = previous_start + read_le(previous + EFI_PAGES_OFFSET, 8);
            if (start < previous_stop && previous_start < stop)
                return PHX34_BOOT_MAP_REFUSED;
        }

        if (start >= end || base >= stop)
            continue;
        covered += (stop < end ? stop : end) - (start > base ? start : base);
        const uint64_t kind = read_le(entry + EFI_TYPE_OFFSET, 4);
        const uint64_t attrs = read_le(entry + EFI_ATTRIBUTES_OFFSET, 8);
        if (((kind >= 1 && kind <= 4) || kind == 7) && !(attrs & runtime))
            overlap = PHX34_BOOT_MAP_HOST_USABLE_OVERLAP;
        else if ((kind || (attrs & runtime)) && overlap != PHX34_BOOT_MAP_HOST_USABLE_OVERLAP)
            overlap = PHX34_BOOT_MAP_OTHER_OVERLAP;
    }

    if (overlap != PHX34_BOOT_MAP_INCOMPLETE)
        return overlap;
    return covered == (end - base) ? PHX34_BOOT_MAP_RESERVED_TYPE_ONLY : PHX34_BOOT_MAP_INCOMPLETE;
}
