#pragma once

#include <stddef.h>
#include <stdint.h>

enum phx34_boot_map_class {
    PHX34_BOOT_MAP_REFUSED,
    PHX34_BOOT_MAP_HOST_USABLE_OVERLAP,
    PHX34_BOOT_MAP_OTHER_OVERLAP,
    PHX34_BOOT_MAP_INCOMPLETE,
    PHX34_BOOT_MAP_RESERVED_TYPE_ONLY,
};

struct phx34_boot_map_view {
    const void *bytes;
    size_t length;
    uint64_t physical_base;
};

enum phx34_boot_map_class phx34_classify_boot_map(const void *boot_args, size_t boot_args_length,
                                                 struct phx34_boot_map_view map,
                                                 uint64_t candidate_base, uint64_t candidate_length);
