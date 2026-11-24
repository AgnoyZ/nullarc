#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <string.h>
#include "build34_dcn_radv_submit.h"

#ifdef TEST_DARWIN_SUBMIT
#define N48N_MAX_IBS 64
#define AMDGPU_HW_IP_GFX 0
#define AMDGPU_HW_IP_COMPUTE 1
#define AMDGPU_CHUNK_ID_DEPENDENCIES 3
#define AMDGPU_CHUNK_ID_SCHEDULED_DEPENDENCIES 8
#define DRM_AMDGPU_CS 4
#define ACD_CS_DEP_TIMEOUT_NS 60000000000ull

union drm_amdgpu_cs {
   struct { uint32_t ctx_id, bo_list_handle, num_chunks; uint64_t chunks; } in;
   struct { uint64_t handle; } out;
};
struct drm_amdgpu_cs_chunk { uint32_t length_dw, chunk_id; };
struct n48n_cs_ib { uint64_t va_start; uint32_t ib_bytes, ip_type, ip_instance, ring; };
struct acd_exact_receipt { uint64_t sequence, owner, serial, generation; uint32_t slot, queue; };
struct acd_cs_sync { uint32_t handle; uint64_t point; };
struct acd_cs_plan {
   struct acd_exact_receipt *receipt_out;
   struct n48n_cs_ib *ibs;
   uint32_t n_ibs, n_waits, n_signals;
   struct acd_cs_sync *waits, *signals;
   bool has_fence;
};
static struct n48n_cs_ib ibs[65];
static struct acd_cs_plan fixture;
static struct acd_exact_receipt receipt;
static struct acd_cs_sync sync;
static bool exact_enabled, supplied;
static int parse_result, wait_result, submit_result, attach_result;
static unsigned called_submit, called_attach, called_wait;

struct acd_core { void *kext; };
typedef struct acd_device { struct acd_core *core; void *sync; bool host_bo; } *acd_device_handle;

static int
acd_cs_plan_init(struct acd_cs_plan *plan, uint32_t ctx, uint32_t handle, uint32_t count, const uint64_t *chunks)
{
   assert(ctx == 23 && !handle && count == 1 && chunks);
   *plan = fixture;
   return parse_result;
}

static void acd_cs_plan_fini(struct acd_cs_plan *plan)
{
   memset(plan, 0, sizeof(*plan));
}

static bool acd_sync_has_exact_completion(void *provider)
{
   assert(provider);
   return exact_enabled;
}

static int acd_kext_submit(void *kext, const struct acd_cs_plan *plan, uint64_t *seq)
{
   assert(kext);
   ++called_submit;
   supplied = plan->receipt_out != NULL;
   if (submit_result)
      return submit_result;
   *seq = 19;
   if (plan->receipt_out)
      *plan->receipt_out = receipt;
   return 0;
}

static int acd_sync_cs_wait_ready(void *provider, uint32_t handle, uint64_t point, uint64_t timeout)
{
   assert(provider && handle == sync.handle && point == sync.point && timeout == ACD_CS_DEP_TIMEOUT_NS);
   ++called_wait;
   return wait_result;
}

static int acd_sync_cs_attach(void *provider, uint32_t handle, uint64_t point, uint64_t seq)
{
   assert(provider && handle == sync.handle && point == sync.point && seq == 19);
   ++called_attach;
   return attach_result;
}

static int acd_ioctl(acd_device_handle dev, unsigned command, void *data, unsigned size)
{
   assert(dev->host_bo && command == DRM_AMDGPU_CS && data && size == sizeof(union drm_amdgpu_cs));
   return -ENODEV;
}

#include "staged_darwin_submit.inc"

static void test_darwin_submit(void)
{
   struct acd_core core = {.kext = &core};
   struct acd_device dev = {.core = &core, .sync = &dev};
   struct drm_amdgpu_cs_chunk chunk = {0};
   const uint64_t chunks[] = {(uint64_t)(uintptr_t)&chunk};
   const struct build34_dcn_ib recorded = {0x20000, 64, 1};
   sync = (struct acd_cs_sync){17, 12};

   for (unsigned test = 0; test < 17; ++test) {
      ibs[0] = (struct n48n_cs_ib){0x10000, 32, AMDGPU_HW_IP_GFX, 0, 0};
      ibs[1] = (struct n48n_cs_ib){0x20000, 64, AMDGPU_HW_IP_GFX, 0, 0};
      fixture = (struct acd_cs_plan){.ibs = ibs, .n_ibs = 2, .n_waits = 1, .n_signals = 1,
                                    .waits = &sync, .signals = &sync};
      exact_enabled = true;
      supplied = false;
      dev.host_bo = false;
      struct build34_dcn_ib writer = recorded;
      receipt = (struct acd_exact_receipt){19, 28, 37, 46, 55, 1};
      union drm_amdgpu_cs cs = {.in = {23, 0, 1, (uint64_t)(uintptr_t)chunks}};
      chunk = (struct drm_amdgpu_cs_chunk){0};
      struct build34_dcn_native_submit out = {2, 3, 4, 5, 6, 1, 8};
      parse_result = wait_result = submit_result = attach_result = 0;
      called_submit = called_attach = called_wait = 0;
      int expected_result = 0;

      switch (test) {
      case 1: exact_enabled = false; break;
      case 2: writer.index = 0; break;
      case 3: writer.bytes++; break;
      case 4: ibs[0].va_start = writer.va; break;
      case 5: fixture.has_fence = true; break;
      case 6: ibs[0].ip_type = AMDGPU_HW_IP_COMPUTE; expected_result = -EOPNOTSUPP; break;
      case 7: fixture.n_ibs = 65; expected_result = -EOPNOTSUPP; break;
      case 8: wait_result = expected_result = -ETIME; break;
      case 9: submit_result = expected_result = -ECANCELED; break;
      case 10: attach_result = -ENOMEM; expected_result = -EIO; break;
      case 11: attach_result = expected_result = -EINVAL; break;
      case 12: receipt.queue = 0; break;
      case 13: receipt.sequence++; break;
      case 14: parse_result = expected_result = -EINVAL; break;
      case 15: dev.host_bo = true; expected_result = -ENODEV; break;
      case 16: chunk = (struct drm_amdgpu_cs_chunk){1, AMDGPU_CHUNK_ID_DEPENDENCIES};
               expected_result = -EOPNOTSUPP; break;
      }

      assert(acd_dcn_cs_submit(&dev, &cs, &writer, &out) == expected_result);
      if (!test) {
         assert(cs.out.handle == 19 && out.sequence == 19 && out.context == 23 && out.queue == 1);
         assert(out.owner == 28 && out.serial == 37 && out.generation == 46 && out.slot == 55);
      } else {
         assert(!out.sequence && !out.owner && !out.serial && !out.generation && !out.context);
      }
      assert(called_submit == (test != 6 && test != 7 && test != 8 && test < 14));
      assert(called_attach == (called_submit && test != 9));
      assert(called_wait == (test <= 5 || (test >= 8 && test < 14)));
      assert(supplied == (!test || (test >= 9 && test <= 13)));
   }
}
#endif

int main(void)
{
   struct radv_dcn_submitted_clear result = {0};
   struct radv_dcn_submitted_clear writer = {
      .clear = {.serial = 7, .phase = RADV_DCN_CLEAR_CLOSED},
      .ib = {0x10000, 64, 1},
      .native = {19, 23, 31, 37, 0, 1, 47},
   };
   radv_dcn_finish_submit(&result, writer, true);
   assert(result.clear.serial == 7 && result.native.serial == 31 && result.ib.index == 1);
   radv_dcn_finish_submit(&result, writer, false);
   assert(!result.clear.serial && !result.native.serial);
   radv_dcn_finish_submit(&result, writer, true);
   writer.native.queue = 0;
   radv_dcn_finish_submit(&result, writer, true);
   assert(!result.clear.serial && !result.native.serial);
#ifdef TEST_DARWIN_SUBMIT
   test_darwin_submit();
#endif
   return 0;
}
