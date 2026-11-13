/* CPU-only constructor fault injection. Cleanup checks are API fakes, not Mesa's
 * complete destructor, allocator, winsys or a real GPU execution test. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define MAX_BIND_POINTS 3
#define VK_SUCCESS 0
#define VK_ERROR_OUT_OF_HOST_MEMORY (-1)
#define VK_ERROR_OUT_OF_DEVICE_MEMORY (-2)
#define VK_ERROR_INITIALIZATION_FAILED (-3)
#define VK_SYSTEM_ALLOCATION_SCOPE_OBJECT 1
#define VK_COMMAND_BUFFER_LEVEL_SECONDARY 1
#define VK_OBJECT_TYPE_DESCRIPTOR_SET 23
#define RADV_QUEUE_SPARSE 3
#define UTIL_DYNARRAY_INIT ((struct dynarray){0})
typedef int VkResult;
typedef int VkCommandBufferLevel;
enum amd_ip_type { AMD_IP_GFX };
struct vk_device { int marker; };
struct radv_physical_device { int unused; };
struct radv_device { struct vk_device vk; struct { void *context; } utrace; };
struct vk_command_pool { struct { struct vk_device *device; } base; int alloc; unsigned queue_family_index; };
struct vk_command_buffer { struct vk_command_pool *pool; int level; };
struct object_base { struct vk_device *device; int type; };
struct list_head { struct list_head *next, *prev; };
struct dynarray { void *data; size_t size; };
struct u_trace { int initialized; };
struct radv_cmd_buffer {
   struct vk_command_buffer vk;
   int qf;
   struct { struct list_head list; } upload;
   struct { struct { struct { struct object_base base; } set; } push_set; } descriptors[MAX_BIND_POINTS];
   void *accel_struct_buffers;
   struct dynarray ray_history;
   struct list_head msrtss_transients;
   void *cs;
   struct { struct u_trace *trace; uint32_t last_cdw; } utrace;
};
static const int radv_cmd_buffer_ops;
static struct radv_physical_device physical;
static bool fail_host, fail_init, fail_stream, cleanup_ready;
static unsigned allocations, destroys, stream_calls, descriptor_finishes, shader_init;

static struct radv_physical_device *radv_device_physical(struct radv_device *d) { (void)d; return &physical; }
static int vk_error(struct radv_device *d, int result) { (void)d; return result; }
static void *vk_zalloc(int *a, size_t size, int align, int scope) {
   (void)a; (void)align; (void)scope;
   if (fail_host) return NULL;
   void *p = calloc(1, size); assert(p); allocations++; return p;
}
static void vk_free(int *a, void *p) { (void)a; assert(allocations); allocations--; free(p); }
static int vk_command_buffer_init(struct vk_command_pool *pool, struct vk_command_buffer *b,
                                  const int *ops, int level) {
   assert(ops == &radv_cmd_buffer_ops); b->pool = pool; b->level = level;
   return fail_init ? VK_ERROR_INITIALIZATION_FAILED : VK_SUCCESS;
}
static int vk_queue_to_radv(const struct radv_physical_device *p, unsigned q) { (void)p; return (int)q; }
static enum amd_ip_type radv_queue_family_to_ring(const struct radv_physical_device *p, int q) {
   (void)p; (void)q; return AMD_IP_GFX;
}
static void list_inithead(struct list_head *h) { h->next = h->prev = h; }
static bool empty_initialized(const struct list_head *h) { return h->next == h && h->prev == h; }
static void radv_cmd_buffer_init_shader_part_cache(struct radv_device *d, struct radv_cmd_buffer *b) {
   (void)d; (void)b; shader_init++;
}
static int radv_create_cmd_stream(struct radv_device *d, enum amd_ip_type ip, bool secondary, void **out) {
   (void)d; (void)ip; (void)secondary; stream_calls++;
   if (fail_stream) return VK_ERROR_OUT_OF_DEVICE_MEMORY;
   *out = &physical; return VK_SUCCESS;
}
static void vk_object_base_init(struct vk_device *d, struct object_base *b, int type) { b->device = d; b->type = type; }
static void *_mesa_pointer_set_create(void *ctx) { (void)ctx; void *p = malloc(1); assert(p); return p; }
static void u_trace_init(struct u_trace *t, void *ctx) { assert(ctx); t->initialized = 1; }
static void radv_destroy_cmd_buffer(struct vk_command_buffer *vk) {
   struct radv_cmd_buffer *b = container_of(vk, struct radv_cmd_buffer, vk);
   destroys++;
   if (b->qf != RADV_QUEUE_SPARSE) {
      /* Observe the real destructor's preconditions without walking an invalid
       * list on the deliberately unpatched negative control. */
      cleanup_ready = empty_initialized(&b->upload.list) && empty_initialized(&b->msrtss_transients);
      for (unsigned i = 0; i < MAX_BIND_POINTS; i++) {
         const struct object_base *base = &b->descriptors[i].push_set.set.base;
         bool ready = base->device == vk->pool->base.device && base->type == VK_OBJECT_TYPE_DESCRIPTOR_SET;
         cleanup_ready = cleanup_ready && ready;
         descriptor_finishes += ready;
      }
      free(b->accel_struct_buffers);
      assert(!b->ray_history.data && !b->ray_history.size);
   }
   free(b->utrace.trace);
   vk_free(&vk->pool->alloc, b);
}

#include "radv_constructor.inc"

static void reset(void) {
   assert(!allocations);
   fail_host = fail_init = fail_stream = cleanup_ready = false;
   destroys = stream_calls = descriptor_finishes = shader_init = 0;
}
int main(void) {
   struct radv_device d = {0};
   struct vk_command_pool pool = {.base.device = &d.vk};
   struct vk_command_buffer sentinel = {0}, *out;
   unsigned cases = 0;
   reset(); fail_stream = true; out = &sentinel;
   assert(radv_create_cmd_buffer(&pool, 0, &out) == VK_ERROR_OUT_OF_DEVICE_MEMORY);
   assert(out == &sentinel && destroys == 1 && stream_calls == 1 && shader_init == 1 && !allocations);
#ifdef NEGATIVE_CONTROL
   assert(!cleanup_ready && descriptor_finishes == 0);
#else
   assert(cleanup_ready && descriptor_finishes == MAX_BIND_POINTS);
#endif
   cases++;
   reset(); fail_host = true; out = &sentinel;
   assert(radv_create_cmd_buffer(&pool, 0, &out) == VK_ERROR_OUT_OF_HOST_MEMORY);
   assert(out == &sentinel && !destroys && !stream_calls && !allocations); cases++;
   reset(); fail_init = true; out = &sentinel;
   assert(radv_create_cmd_buffer(&pool, 0, &out) == VK_ERROR_INITIALIZATION_FAILED);
   assert(out == &sentinel && !destroys && !stream_calls && !allocations); cases++;
   for (unsigned traced = 0; traced < 2; traced++) {
      reset(); d.utrace.context = traced ? &d : NULL;
      out = &sentinel;
      assert(radv_create_cmd_buffer(&pool, VK_COMMAND_BUFFER_LEVEL_SECONDARY, &out) == VK_SUCCESS);
      assert(out != &sentinel && stream_calls == 1);
      struct radv_cmd_buffer *b = container_of(out, struct radv_cmd_buffer, vk);
      assert((b->utrace.trace != NULL) == (traced != 0));
      if (traced) assert(b->utrace.trace->initialized && b->utrace.last_cdw == UINT32_MAX);
      radv_destroy_cmd_buffer(out);
      assert(cleanup_ready && descriptor_finishes == MAX_BIND_POINTS && !allocations); cases++;
   }
   reset(); d.utrace.context = NULL; pool.queue_family_index = RADV_QUEUE_SPARSE;
   out = &sentinel;
   assert(radv_create_cmd_buffer(&pool, 0, &out) == VK_SUCCESS);
   assert(!stream_calls && !shader_init);
   radv_destroy_cmd_buffer(out); assert(!allocations); cases++;
   printf("{\"cases\":%u,\"hardware_executed\":false}\n", cases);
   return 0;
}
