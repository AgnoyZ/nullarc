#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define RADV_DCN_PAGE_BYTES 4096ull
#define RADV_DCN_HOST_LIMIT (64ull * 1024 * 1024)
#define RADV_DCN_VA_END (1ull << 48)

struct radv_dcn_host_map {
   const void *winsys;
   const void *host;
   uint64_t generation, va, bytes;
   uint32_t handle;
};

struct radv_dcn_render_binding {
   struct radv_dcn_host_map map;
   uint64_t phx_va, bind_bytes, pitch, scanout_bytes;
   uint32_t width, height;
   const void *memory;
};

static inline uint64_t
radv_dcn_phx_va(uint64_t va)
{
   if (va < RADV_DCN_VA_END)
      return va;
   if (va >= ~(RADV_DCN_VA_END / 2 - 1))
      return va & (RADV_DCN_VA_END - 1);
   return 0;
}

static inline bool
radv_dcn_valid_host_map(const struct radv_dcn_host_map *map)
{
   const uint64_t phx_va = radv_dcn_phx_va(map->va);
   return map->winsys && map->host && map->generation && map->handle && map->bytes &&
          !((map->va | map->bytes | (uintptr_t)map->host) & (RADV_DCN_PAGE_BYTES - 1)) &&
          phx_va >= 0x10000 && map->bytes <= RADV_DCN_VA_END - phx_va && map->bytes <= RADV_DCN_HOST_LIMIT;
}

static inline struct radv_dcn_render_binding
radv_dcn_check_binding(struct radv_dcn_host_map map, const void *host, uint64_t alloc_bytes,
                       uint64_t bind_va, uint64_t bind_offset, uint64_t bind_bytes,
                       uint32_t width, uint32_t height, uint64_t pitch,
                       uint64_t layout_offset, uint64_t layout_bytes)
{
   if (!radv_dcn_valid_host_map(&map) || map.host != host || alloc_bytes != map.bytes ||
       bind_offset || bind_va != map.va || bind_bytes > map.bytes ||
       layout_offset || !width || !height || pitch < (uint64_t)width * 4 || (pitch & 3) ||
       height > bind_bytes / pitch)
      return (struct radv_dcn_render_binding){0};
   const uint64_t footprint = height * pitch;
   const uint64_t rounded = (footprint + RADV_DCN_PAGE_BYTES - 1) & ~(RADV_DCN_PAGE_BYTES - 1);
   const uint64_t texel_end = footprint - pitch + (uint64_t)width * 4;
   if (rounded > bind_bytes || layout_bytes < texel_end || layout_bytes > bind_bytes)
      return (struct radv_dcn_render_binding){0};
   return (struct radv_dcn_render_binding){map, radv_dcn_phx_va(map.va), bind_bytes, pitch, rounded, width, height, NULL};
}
