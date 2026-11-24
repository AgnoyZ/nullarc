#include <assert.h>
#include "build34_dcn_radv_binding.h"

static _Alignas(4096) unsigned char original[4096], replacement[4096];

int main(void)
{
   const struct radv_dcn_host_map map = {&original, original, 3, 0x10000, 16384, 7};
   struct radv_dcn_render_binding binding = radv_dcn_check_binding(map, original, 16384,
       0x10000, 0, 12288, 63, 33, 256, 0, 8444);
   assert(binding.map.generation == 3 && binding.map.handle == 7 && binding.map.host == original);
   assert(binding.phx_va == map.va);
   assert(binding.scanout_bytes == 12288 && binding.bind_bytes == 12288 && binding.pitch == 256);
   assert(binding.width == 63 && binding.height == 33 && binding.map.winsys == &original);

   for (unsigned test = 0; test < 11; ++test) {
      struct radv_dcn_host_map broken = map;
      switch (test) {
      case 0: broken.winsys = 0; break;
      case 1: broken.handle = 0; break;
      case 2: broken.generation = 0; break;
      case 3: broken.va++; break;
      case 4: broken.bytes--; break;
      case 5: broken.host = original + 1; break;
      case 6: broken.va = RADV_DCN_VA_END - 4096; break;
      case 7: broken.va = 0xf000; break;
      case 8: broken.bytes = RADV_DCN_HOST_LIMIT + 4096; break;
      case 9: broken.bytes = 0; break;
      case 10: broken.va = RADV_DCN_VA_END; break;
      }
      assert(!radv_dcn_valid_host_map(&broken));
   }
   for (unsigned test = 0; test < 13; ++test) {
      const void *host = original;
      uint64_t alloc = 16384, va = 0x10000, offset = 0, span = 12288, pitch = 256, layout = 8444, layout_offset = 0;
      uint32_t width = 63, height = 33;
      switch (test) {
      case 0: host = replacement; break;
      case 1: alloc -= 4096; break;
      case 2: va += 4096; break;
      case 3: offset += 4096; break;
      case 4: span = 20480; break;
      case 5: span = 8448; break;
      case 6: layout = 8443; break;
      case 7: layout = 12289; break;
      case 8: layout_offset = 256; break;
      case 9: pitch = 255; break;
      case 10: height = 0; break;
      case 11: pitch = 0; break;
      case 12: height = UINT32_MAX; break;
      }
      binding = radv_dcn_check_binding(map, host, alloc, va, offset, span, width, height, pitch, layout_offset, layout);
      assert(!binding.map.generation && !binding.scanout_bytes);
   }

   struct radv_dcn_host_map reused = map;
   reused.host = replacement;
   reused.generation++;
   assert(!radv_dcn_check_binding(reused, original, 16384, 0x10000, 0, 12288, 63, 33, 256, 0, 8444).map.generation);
   assert(radv_dcn_check_binding(reused, replacement, 16384, 0x10000, 0, 12288, 63, 33, 256, 0, 8444).map.generation == 4);

   struct radv_dcn_host_map high = map;
   high.va = 0xffff800000010000ull;
   binding = radv_dcn_check_binding(high, original, 16384, high.va, 0, 12288, 63, 33, 256, 0, 8444);
   assert(binding.map.va == high.va && binding.phx_va == 0x800000010000ull);
   assert(!radv_dcn_check_binding(high, original, 16384, binding.phx_va, 0, 12288, 63, 33, 256, 0, 8444).map.generation);
   high.va = 0xffff000000010000ull;
   assert(!radv_dcn_valid_host_map(&high));
   high.va = UINT64_MAX - 4095;
   assert(!radv_dcn_valid_host_map(&high));
   return 0;
}
