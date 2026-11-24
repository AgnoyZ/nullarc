"""Derive a private RADV host-render binding observation from pinned Mesa files."""

import hashlib


IMAGE = "src/amd/vulkan/radv_image.c"
IMAGE_H = "src/amd/vulkan/radv_image.h"
BO = "src/amd/vulkan/winsys/amdgpu/radv_amdgpu_bo.c"
BO_H = "src/amd/vulkan/winsys/amdgpu/radv_amdgpu_bo.h"
HEADER = "src/amd/vulkan/build34_dcn_radv_binding.h"
INPUTS = {
    IMAGE: "70c2f5cc2b699e9e9afe363f80f70497c2e3ac91d3e438c8a351d637e029751a",
    IMAGE_H: "571e3640738620fa16204f31aa71fb11e1ffcd65d8d7c2c0503b7d480c548e18",
    BO: "94b3b804927b06466497942fe6ed85bdb01d2ab1a4394a3d490c4b76fa410b17",
    BO_H: "629e91b75e7b76bc9a6aa876705e118e92e6857efbb99ccdfcfc493510d6c889",
}


def stage(inputs):
    sources = {}
    for name, digest in INPUTS.items():
        data = inputs.get(name, b"")
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Build34 RADV binding source drift: {name}")
        sources[name] = data.decode()

    def replace(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError(f"Build34 RADV binding anchor drift: {name}: {old[:75]}")
        sources[name] = sources[name].replace(old, new)

    for name, anchor in ((BO_H, '#include "radv_amdgpu_winsys.h"\n'),
                         (IMAGE_H, '#include "vk_image.h"\n')):
        replace(name, anchor, anchor + '\n#ifdef HAVE_AMDGPU_DARWIN\n'
                '#include "build34_dcn_radv_binding.h"\n#endif\n')
    replace(BO_H, "   bool emulate_sparse_residency;\n",
            "   bool emulate_sparse_residency;\n#ifdef HAVE_AMDGPU_DARWIN\n"
            "   struct radv_dcn_host_map dcn_host_map;\n#endif\n")
    replace(BO_H, "void radv_amdgpu_bo_init_functions(",
            "#ifdef HAVE_AMDGPU_DARWIN\n"
            "struct radv_dcn_host_map radv_amdgpu_dcn_host_map(const struct radeon_winsys *ws,\n"
            "                                                const struct radeon_winsys_bo *bo);\n"
            "#endif\n\nvoid radv_amdgpu_bo_init_functions(")
    replace(IMAGE_H, "   struct radv_image_binding bindings[3];\n",
            "   struct radv_image_binding bindings[3];\n#ifdef HAVE_AMDGPU_DARWIN\n"
            "   struct radv_dcn_render_binding dcn_render_binding;\n#endif\n")

    replace(BO, '#include <stdio.h>\n', '#include <stdio.h>\n#ifdef HAVE_AMDGPU_DARWIN\n'
            '#include <stdatomic.h>\n#endif\n')
    replace(BO, "static VkResult\nradv_amdgpu_winsys_bo_from_ptr(", """#ifdef HAVE_AMDGPU_DARWIN
static _Atomic uint64_t radv_dcn_host_serial;

static uint64_t
radv_dcn_next_host_serial(void)
{
   uint64_t previous = atomic_load_explicit(&radv_dcn_host_serial, memory_order_relaxed);
   while (previous != UINT64_MAX) {
      if (atomic_compare_exchange_weak_explicit(&radv_dcn_host_serial, &previous, previous + 1,
                                                memory_order_relaxed, memory_order_relaxed))
         return previous + 1;
   }
   return 0;
}
#endif

static VkResult
radv_amdgpu_winsys_bo_from_ptr(""")
    host_publish = "   bo->base.obj_id = (uintptr_t)(buf_handle.abo);\n\n   p_atomic_add(&ws->alloc_tracker->allocated_gtt,"
    replace(BO, host_publish, """   bo->base.obj_id = (uintptr_t)(buf_handle.abo);
#ifdef HAVE_AMDGPU_DARWIN
   if (!r && ws->info.pci_id == 0x1900 && ws->info.gfx_level == GFX11) {
      struct radv_dcn_host_map host_map = {_ws, pointer, 1, va, size, kms_handle};
      struct amdgpu_bo_info imported = {0};
      if (radv_dcn_valid_host_map(&host_map) && !ac_drm_bo_query_info(ws->dev, kms_handle, &imported) &&
          imported.alloc_size == size) {
         host_map.generation = radv_dcn_next_host_serial();
         if (host_map.generation)
            bo->dcn_host_map = host_map;
      }
   }
#endif

   p_atomic_add(&ws->alloc_tracker->allocated_gtt,""")
    replace(BO, "static VkResult\nradv_amdgpu_winsys_bo_from_fd(", """#ifdef HAVE_AMDGPU_DARWIN
struct radv_dcn_host_map
radv_amdgpu_dcn_host_map(const struct radeon_winsys *ws, const struct radeon_winsys_bo *base)
{
   const struct radv_dcn_host_map absent = {0};
   if (!ws || ws->buffer_from_ptr != radv_amdgpu_winsys_bo_from_ptr || !base || base->is_virtual)
      return absent;
   const struct radv_amdgpu_winsys_bo *bo = (const struct radv_amdgpu_winsys_bo *)base;
   const struct radv_dcn_host_map map = bo->dcn_host_map;
   return map.winsys == ws && map.handle == bo->bo_handle && map.va == base->va && map.bytes == base->size &&
          radv_dcn_valid_host_map(&map) ? map : absent;
}
#endif

static VkResult
radv_amdgpu_winsys_bo_from_fd(""")

    replace(IMAGE, '#include "radv_wsi.h"\n', '#include "radv_wsi.h"\n#ifdef HAVE_AMDGPU_DARWIN\n'
            '#include "winsys/amdgpu/radv_amdgpu_bo.h"\n#endif\n')
    replace(IMAGE, "VKAPI_ATTR VkResult VKAPI_CALL\nradv_BindImageMemory2(", """#ifdef HAVE_AMDGPU_DARWIN
static struct radv_dcn_render_binding
radv_dcn_bound_image(VkDevice device, struct radv_image *image,
                     const struct radv_device_memory *mem, struct radeon_winsys *ws,
                     uint32_t bind_idx, uint64_t offset)
{
   const VkExternalMemoryHandleTypeFlagBits host = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT;
   if (bind_idx || image->disjoint || image->plane_count != 1 || image->vk.external_handle_types != host ||
       mem->import_handle_type != host || !mem->user_ptr || mem->bo != image->bindings[0].bo ||
       image->vk.format != VK_FORMAT_B8G8R8A8_UNORM || image->vk.image_type != VK_IMAGE_TYPE_2D ||
       image->vk.extent.depth != 1 || image->vk.mip_levels != 1 || image->vk.array_layers != 1 ||
       image->vk.samples != VK_SAMPLE_COUNT_1_BIT || !(image->vk.usage & VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) ||
       !image->planes[0].surface.is_linear || radv_image_has_dcc(image) ||
       radv_image_has_cmask(image) || radv_image_has_fmask(image) || radv_image_has_htile(image))
      return (struct radv_dcn_render_binding){0};

   const bool modifier = image->vk.tiling == VK_IMAGE_TILING_DRM_FORMAT_MODIFIER_EXT;
   if (modifier ? image->planes[0].surface.modifier != 0 : image->vk.tiling != VK_IMAGE_TILING_LINEAR)
      return (struct radv_dcn_render_binding){0};
   const struct radv_dcn_host_map map = radv_amdgpu_dcn_host_map(ws, mem->bo);
   if (!map.generation)
      return (struct radv_dcn_render_binding){0};

   const VkImageSubresource2 subresource = {VK_STRUCTURE_TYPE_IMAGE_SUBRESOURCE_2, NULL,
      {modifier ? VK_IMAGE_ASPECT_MEMORY_PLANE_0_BIT_EXT : VK_IMAGE_ASPECT_COLOR_BIT, 0, 0}};
   VkSubresourceLayout2 layout = {.sType = VK_STRUCTURE_TYPE_SUBRESOURCE_LAYOUT_2};
   radv_GetImageSubresourceLayout2(device, radv_image_to_handle(image), &subresource, &layout);
   return radv_dcn_check_binding(map, mem->user_ptr, mem->bo->size, image->bindings[0].addr, offset,
      image->bindings[0].range, image->vk.extent.width, image->vk.extent.height,
      layout.subresourceLayout.rowPitch, layout.subresourceLayout.offset, layout.subresourceLayout.size);
}
#endif

VKAPI_ATTR VkResult VKAPI_CALL
radv_BindImageMemory2(""")
    replace(IMAGE, "      radv_bind_image_memory(device, image, bind_idx, mem->bo, addr, offset, reqs.memoryRequirements.size);\n",
            "      radv_bind_image_memory(device, image, bind_idx, mem->bo, addr, offset, reqs.memoryRequirements.size);\n"
            "#ifdef HAVE_AMDGPU_DARWIN\n"
            "      image->dcn_render_binding = radv_dcn_bound_image(_device, image, mem, device->ws, bind_idx, offset);\n"
            "#endif\n")
    return sources
