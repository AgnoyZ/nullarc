/*
 * Copyright © 2016 Red Hat.
 * Copyright © 2016 Bas Nieuwenhuizen
 *
 * based in part on anv driver which is:
 * Copyright © 2015 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 *
 * Exact constructor excerpt from Mesa commit
 * f5cb8ee032adabef599ae892ec4e42d796b84da9,
 * src/amd/vulkan/radv_cmd_buffer.c. Full license: LICENSES/MIT.txt.
 * Function SHA-256 (including its final newline):
 * bdfbc84e5888e499d2f8e8d9a324875f8730b9ce62a504c8317f74df8167f737
 */
static VkResult
radv_create_cmd_buffer(struct vk_command_pool *pool, VkCommandBufferLevel level,
                       struct vk_command_buffer **cmd_buffer_out)
{
   struct radv_device *device = container_of(pool->base.device, struct radv_device, vk);
   const struct radv_physical_device *pdev = radv_device_physical(device);
   struct radv_cmd_buffer *cmd_buffer;

   cmd_buffer = vk_zalloc(&pool->alloc, sizeof(*cmd_buffer), 8, VK_SYSTEM_ALLOCATION_SCOPE_OBJECT);
   if (cmd_buffer == NULL)
      return vk_error(device, VK_ERROR_OUT_OF_HOST_MEMORY);

   VkResult result = vk_command_buffer_init(pool, &cmd_buffer->vk, &radv_cmd_buffer_ops, level);
   if (result != VK_SUCCESS) {
      vk_free(&cmd_buffer->vk.pool->alloc, cmd_buffer);
      return result;
   }

   cmd_buffer->qf = vk_queue_to_radv(pdev, pool->queue_family_index);

   if (cmd_buffer->qf != RADV_QUEUE_SPARSE) {
      const enum amd_ip_type ip = radv_queue_family_to_ring(pdev, cmd_buffer->qf);
      list_inithead(&cmd_buffer->upload.list);

      radv_cmd_buffer_init_shader_part_cache(device, cmd_buffer);
      result =
         radv_create_cmd_stream(device, ip, cmd_buffer->vk.level == VK_COMMAND_BUFFER_LEVEL_SECONDARY, &cmd_buffer->cs);
      if (result != VK_SUCCESS) {
         radv_destroy_cmd_buffer(&cmd_buffer->vk);
         return vk_error(device, VK_ERROR_OUT_OF_DEVICE_MEMORY);
      }

      for (unsigned i = 0; i < MAX_BIND_POINTS; i++)
         vk_object_base_init(&device->vk, &cmd_buffer->descriptors[i].push_set.set.base, VK_OBJECT_TYPE_DESCRIPTOR_SET);

      cmd_buffer->accel_struct_buffers = _mesa_pointer_set_create(NULL);
      cmd_buffer->ray_history = UTIL_DYNARRAY_INIT;
      list_inithead(&cmd_buffer->msrtss_transients);
   }

   if (device->utrace.context) {
      cmd_buffer->utrace.trace = malloc(sizeof(struct u_trace));
      if (cmd_buffer->utrace.trace)
         u_trace_init(cmd_buffer->utrace.trace, device->utrace.context);
      cmd_buffer->utrace.last_cdw = UINT32_MAX;
   }

   *cmd_buffer_out = &cmd_buffer->vk;

   return VK_SUCCESS;
}
