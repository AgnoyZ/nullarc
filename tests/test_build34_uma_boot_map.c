#include "build34_uma_boot_map.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

enum { PAGE = 4096, STRIDE = 48, MAP_PHYS = 0x2000 };
static const uint64_t candidate = UINT64_C(1) << 32;

static void store_le(uint8_t *bytes, unsigned width, uint64_t value)
{
    for (unsigned index = 0; index < width; ++index)
        bytes[index] = (uint8_t)(value >> (index * 8));
}

static void setup_args(uint8_t args[4096], uint64_t address, size_t length, size_t stride)
{
    memset(args, 0xA5, 4096);
    args[0] = 1;
    args[1] = 0;
    args[2] = 2;
    args[3] = 0;
    args[4] = 64;
    store_le(args + 1032, 4, address);
    store_le(args + 1036, 4, length);
    store_le(args + 1040, 4, stride);
    store_le(args + 1044, 4, 1);
}

static void descriptor(uint8_t *entry, uint32_t kind, uint64_t start, uint64_t pages, uint64_t attrs)
{
    memset(entry, 0x5A, STRIDE);
    store_le(entry, 4, kind);
    store_le(entry + 8, 8, start);
    store_le(entry + 24, 8, pages);
    store_le(entry + 32, 8, attrs);
}

static enum phx34_boot_map_class run(const uint8_t args[4096], const uint8_t *entries, size_t length)
{
    return phx34_classify_boot_map(args, 4096, (struct phx34_boot_map_view){entries, length, MAP_PHYS},
                                   candidate, 2 * PAGE);
}

static void test_classification(void)
{
    uint8_t args[4096], entries[3 * STRIDE];
    setup_args(args, MAP_PHYS, sizeof(entries), STRIDE);
    descriptor(entries, 0, candidate + PAGE, 1, 0);
    descriptor(entries + STRIDE, 0, candidate, 1, 0);
    descriptor(entries + 2 * STRIDE, 7, candidate + 2 * PAGE, 1, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_RESERVED_TYPE_ONLY);
    args[0] = 0;
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_RESERVED_TYPE_ONLY);

    const uint32_t conflicts[] = {1, 2, 3, 4, 7};
    for (size_t index = 0; index < sizeof(conflicts) / sizeof(conflicts[0]); ++index) {
        descriptor(entries, conflicts[index], candidate + PAGE, 1, 0);
        assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_HOST_USABLE_OVERLAP);
        descriptor(entries, conflicts[index], candidate + PAGE, 1, UINT64_C(1) << 63);
        assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_OTHER_OVERLAP);
    }

    descriptor(entries, 10, candidate + PAGE, 1, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_OTHER_OVERLAP);
    descriptor(entries + STRIDE, 7, candidate, 1, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_HOST_USABLE_OVERLAP);
    descriptor(entries, 0, candidate + 3 * PAGE, 1, 0);
    descriptor(entries + STRIDE, 0, candidate, 1, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_INCOMPLETE);

    descriptor(entries + 2 * STRIDE, 0, candidate + 3 * PAGE, 1, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_REFUSED);
    descriptor(entries + 2 * STRIDE, 0, candidate + 4 * PAGE, 0, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_REFUSED);
    descriptor(entries + 2 * STRIDE, 0, candidate + 4 * PAGE + 1, 1, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_REFUSED);
    descriptor(entries + 2 * STRIDE, 0, UINT64_MAX - PAGE + 1, 2, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_REFUSED);
    descriptor(entries + 2 * STRIDE, 0, UINT64_MAX - PAGE + 1, 1, 0);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_INCOMPLETE);
}

static void test_input_binding(void)
{
    uint8_t args[4096], entry[STRIDE];
    descriptor(entry, 0, candidate, 2, 0);
    setup_args(args, MAP_PHYS, sizeof(entry), STRIDE);
    struct phx34_boot_map_view map = {entry, sizeof(entry), MAP_PHYS};
    assert(run(args, entry, sizeof(entry)) == PHX34_BOOT_MAP_RESERVED_TYPE_ONLY);
    assert(run(args, entry, sizeof(entry) - 1) == PHX34_BOOT_MAP_REFUSED);
    assert(run(args, NULL, sizeof(entry)) == PHX34_BOOT_MAP_REFUSED);
    assert(phx34_classify_boot_map(NULL, 4096, map, candidate, PAGE) == PHX34_BOOT_MAP_REFUSED);
    assert(phx34_classify_boot_map(args, 4095, map, candidate, PAGE) == PHX34_BOOT_MAP_REFUSED);
    assert(phx34_classify_boot_map(args, 4096, map, 0, PAGE) == PHX34_BOOT_MAP_REFUSED);
    assert(phx34_classify_boot_map(args, 4096, map, candidate + 1, PAGE) == PHX34_BOOT_MAP_REFUSED);
    assert(phx34_classify_boot_map(args, 4096, map, candidate, PAGE + 1) == PHX34_BOOT_MAP_REFUSED);
    assert(phx34_classify_boot_map(args, 4096, map, candidate, 0) == PHX34_BOOT_MAP_REFUSED);
    assert(phx34_classify_boot_map(args, 4096, map, candidate, UINT64_C(65) << 20) == PHX34_BOOT_MAP_REFUSED);
    const uint64_t high = (UINT64_C(1) << 48) - PAGE;
    assert(phx34_classify_boot_map(args, 4096, map, high, 2 * PAGE) == PHX34_BOOT_MAP_REFUSED);
    descriptor(entry, 0, high, 1, 0);
    assert(phx34_classify_boot_map(args, 4096, map, high, PAGE) == PHX34_BOOT_MAP_RESERVED_TYPE_ONLY);

    const size_t rejected_offsets[] = {0, 2, 4, 1032, 1036, 1040, 1044};
    for (size_t index = 0; index < sizeof(rejected_offsets) / sizeof(rejected_offsets[0]); ++index) {
        const size_t offset = rejected_offsets[index];
        args[offset] ^= 0x80;
        assert(run(args, entry, sizeof(entry)) == PHX34_BOOT_MAP_REFUSED);
        args[offset] ^= 0x80;
    }

    setup_args(args, 0, sizeof(entry), STRIDE);
    map.physical_base = 0;
    assert(phx34_classify_boot_map(args, 4096, map, candidate, PAGE) == PHX34_BOOT_MAP_REFUSED);
    setup_args(args, MAP_PHYS + 1, sizeof(entry), STRIDE);
    map.physical_base = MAP_PHYS + 1;
    assert(phx34_classify_boot_map(args, 4096, map, candidate, PAGE) == PHX34_BOOT_MAP_REFUSED);

    map.physical_base = (UINT64_C(1) << 32) - STRIDE;
    setup_args(args, map.physical_base, sizeof(entry), STRIDE);
    assert(phx34_classify_boot_map(args, 4096, map, high, PAGE) == PHX34_BOOT_MAP_RESERVED_TYPE_ONLY);
    map.physical_base += 8;
    setup_args(args, map.physical_base, sizeof(entry), STRIDE);
    assert(phx34_classify_boot_map(args, 4096, map, high, PAGE) == PHX34_BOOT_MAP_REFUSED);
}

static void test_shape_and_bound(void)
{
    uint8_t args[4096], entries[257 * STRIDE];
    for (size_t index = 0; index < sizeof(entries) / STRIDE; ++index)
        descriptor(entries + index * STRIDE, 0, candidate + index * PAGE, 1, 0);

    setup_args(args, MAP_PHYS, 40, 40);
    assert(phx34_classify_boot_map(args, 4096, (struct phx34_boot_map_view){entries, 40, MAP_PHYS},
                                   candidate, PAGE) == PHX34_BOOT_MAP_RESERVED_TYPE_ONLY);
    setup_args(args, MAP_PHYS, 2 * STRIDE - 1, STRIDE);
    assert(run(args, entries, 2 * STRIDE - 1) == PHX34_BOOT_MAP_REFUSED);
    setup_args(args, MAP_PHYS, STRIDE, 32);
    assert(run(args, entries, STRIDE) == PHX34_BOOT_MAP_REFUSED);
    setup_args(args, MAP_PHYS, STRIDE, 44);
    assert(run(args, entries, STRIDE) == PHX34_BOOT_MAP_REFUSED);
    setup_args(args, MAP_PHYS, STRIDE, 0);
    assert(run(args, entries, STRIDE) == PHX34_BOOT_MAP_REFUSED);
    setup_args(args, MAP_PHYS, 256 * STRIDE, STRIDE);
    assert(run(args, entries, 256 * STRIDE) == PHX34_BOOT_MAP_RESERVED_TYPE_ONLY);
    setup_args(args, MAP_PHYS, sizeof(entries), STRIDE);
    assert(run(args, entries, sizeof(entries)) == PHX34_BOOT_MAP_REFUSED);
}

int main(void)
{
    test_classification();
    test_input_binding();
    test_shape_and_bound();
    puts("PASS build34 UMA boot-args map classifier (synthetic inputs only)");
    return 0;
}
