"""Bind a pinned RADV clear recording to its exact Darwin submission."""

import hashlib

import build34_dcn_radv_clear_stage as clear


RAW = "src/amd/common/ac_linux_drm.c"
RAW_H = "src/amd/common/ac_linux_drm.h"
DRM = "src/amd/common/darwin/ac_darwin_drm.c"
DRM_H = "src/amd/common/darwin/ac_darwin_drm.h"
KEXT = "src/amd/common/darwin/ac_darwin_kext.c"
KEXT_H = "src/amd/common/darwin/ac_darwin_kext.h"
QUEUE = "src/amd/vulkan/radv_queue.c"
QUEUE_H = "src/amd/vulkan/radv_queue.h"
WINSYS_H = "src/amd/vulkan/radv_radeon_winsys.h"
CS = "src/amd/vulkan/winsys/amdgpu/radv_amdgpu_cs.c"
NATIVE_HEADER = "src/amd/common/build34_dcn_native_submit.h"
HEADER = "src/amd/vulkan/build34_dcn_radv_submit.h"
PINS = {
    RAW: "19874a4f9c25385099f42762b5f7f8990ce4b1e19f78185c176de0e323c19c2a",
    RAW_H: "371ef6ab512fd9587e8a07fb57ca8d78eda13da3b1ecee6a6378b7014a9e52fd",
    DRM: "4201d719ba5730a3755679c57fccc6b1b866c34371f28a066d0cd1337397f15a",
    DRM_H: "3cfddf00be2226609597da7efc5a4314d2c8abc5af8b33d55e4dd5570c276fa4",
    KEXT: "0f08b98e7739eb746ec77e1eb87bacfe10cc03085697f76dcd9fecd0ab90a78f",
    KEXT_H: "e0ecf65107395c4549116a2398fa220b2e4ffd1b0a44453f1975226a7966e199",
    QUEUE: "ad0662c04abf47cfd006c4b7598ecd9966e925cf96751998876216f6f0adfc34",
    QUEUE_H: "39105314629caaf7b643490b458f5c79bf8c22dfa463a341c65343a27371a24d",
    WINSYS_H: "d1c18bd8ae313f6fbc184bcd6c51e755c350962fd00c2309c672171f78e6b08d",
    CS: "5976a05ea932469a992b32ede5e0efa5f8c43d8371c41d7245cb2a67e6a12b31",
}
INPUTS = {**clear.INPUTS, **PINS}


def stage(inputs):
    sources = clear.stage(inputs)
    for name, digest in PINS.items():
        data = inputs.get(name, b"")
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Build34 RADV submit source drift: {name}")
        sources[name] = data.decode()

    def replace(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError(f"Build34 RADV submit anchor drift: {name}: {old[:75]}")
        sources[name] = sources[name].replace(old, new)

    replace(KEXT_H, "struct acd_cs_plan {\n", "struct acd_cs_plan {\n   struct acd_exact_receipt *receipt_out;\n")
    replace(KEXT, "         *seq = receipt.sequence;",
            "         if (plan->receipt_out)\n            *plan->receipt_out = receipt;\n         *seq = receipt.sequence;")

    replace(DRM_H, "int acd_ioctl(", """struct build34_dcn_ib;
struct build34_dcn_native_submit;
int acd_dcn_cs_submit(acd_device_handle dev, union drm_amdgpu_cs *cs, const struct build34_dcn_ib *writer,
                      struct build34_dcn_native_submit *out);

int acd_ioctl(""")
    replace(DRM, '#include "ac_darwin_kext.h"\n',
            '#include "ac_darwin_kext.h"\n#include "build34_dcn_native_submit.h"\n')
    replace(DRM, "static int\nacd_cmd_cs(struct acd_device *dev, union drm_amdgpu_cs *cs)\n{", """static bool
acd_dcn_matches_plan(const struct acd_cs_plan *plan, const struct build34_dcn_ib *writer)
{
   if (!writer || writer->index >= plan->n_ibs || !writer->va || !writer->bytes || plan->has_fence)
      return false;

   for (uint32_t index = 0; index < plan->n_ibs; index++) {
      const struct n48n_cs_ib *ib = &plan->ibs[index];
      if (ib->ip_type != AMDGPU_HW_IP_GFX || ib->ip_instance || ib->ring)
         return false;
      if (index == writer->index ? (ib->va_start != writer->va || ib->ib_bytes != writer->bytes) :
                                   ib->va_start == writer->va)
         return false;
   }
   return true;
}

static int
acd_cmd_cs(struct acd_device *dev, union drm_amdgpu_cs *cs, const struct build34_dcn_ib *writer,
           struct build34_dcn_native_submit *out)
{""")
    replace(DRM, "   uint64_t seq = 0;\n   if (!r)\n      r = acd_kext_submit(dev->core->kext, &plan, &seq);", """   struct acd_exact_receipt accepted = {0};
   if (exact && out && acd_dcn_matches_plan(&plan, writer))
      plan.receipt_out = &accepted;

   uint64_t seq = 0;
   if (!r)
      r = acd_kext_submit(dev->core->kext, &plan, &seq);""")
    replace(DRM, "   if (r)\n      return exact && seq && r == -ENOMEM ? -EIO : r;\n   memset(&cs->out, 0, sizeof(cs->out));", """   if (r)
      return exact && seq && r == -ENOMEM ? -EIO : r;
   if (out) {
      const struct build34_dcn_native_submit receipt = {
         accepted.sequence, accepted.owner, accepted.serial, accepted.generation,
         accepted.slot, accepted.queue, ctx_id,
      };
      if (build34_dcn_valid_native_submit(receipt, seq))
         *out = receipt;
   }
   memset(&cs->out, 0, sizeof(cs->out));""")
    replace(DRM, "static int\nacd_cmd_ctx(", """int
acd_dcn_cs_submit(acd_device_handle dev, union drm_amdgpu_cs *cs, const struct build34_dcn_ib *writer,
                  struct build34_dcn_native_submit *out)
{
   *out = (struct build34_dcn_native_submit){0};
   if (dev->host_bo)
      return acd_ioctl(dev, DRM_AMDGPU_CS, cs, sizeof(*cs));
   return acd_cmd_cs(dev, cs, writer, out);
}

static int
acd_cmd_ctx(""")
    replace(DRM, "      return acd_cmd_cs(dev, data);", "      return acd_cmd_cs(dev, data, NULL, NULL);")

    replace(RAW_H, "MESAPROC void ac_drm_cs_chunk_fence_info_to_data(", """#ifdef HAVE_AMDGPU_DARWIN
struct build34_dcn_ib;
struct build34_dcn_native_submit;
int ac_drm_dcn_cs_submit(ac_drm_device *dev, uint32_t ctx_id, uint32_t bo_list_handle, int num_chunks,
                         struct drm_amdgpu_cs_chunk *chunks, uint64_t *seq_no, const struct build34_dcn_ib *writer,
                         struct build34_dcn_native_submit *out);
#endif
MESAPROC void ac_drm_cs_chunk_fence_info_to_data(""")
    replace(RAW, '#include "darwin/ac_darwin_drm.h"\n',
            '#include "darwin/ac_darwin_drm.h"\n#include "build34_dcn_native_submit.h"\n')
    replace(RAW, "int ac_drm_cs_submit_raw2(ac_drm_device *dev, uint32_t ctx_id, uint32_t bo_list_handle,\n"
            "                          int num_chunks, struct drm_amdgpu_cs_chunk *chunks, uint64_t *seq_no)\n{", """static int
ac_drm_cs_submit_raw2_impl(ac_drm_device *dev, uint32_t ctx_id, uint32_t bo_list_handle,
                           int num_chunks, struct drm_amdgpu_cs_chunk *chunks, uint64_t *seq_no
#ifdef HAVE_AMDGPU_DARWIN
                           , const struct build34_dcn_ib *writer, struct build34_dcn_native_submit *out
#endif
                           )
{""")
    replace(RAW, "   r = ac_drm_ioctl_write_read(dev, DRM_AMDGPU_CS, &cs, sizeof(cs));", """#ifdef HAVE_AMDGPU_DARWIN
   if (out && dev->is_darwin)
      r = acd_dcn_cs_submit(dev->ddev, &cs, writer, out);
   else
#endif
      r = ac_drm_ioctl_write_read(dev, DRM_AMDGPU_CS, &cs, sizeof(cs));""")
    replace(RAW, "void ac_drm_cs_chunk_fence_info_to_data(", """int ac_drm_cs_submit_raw2(ac_drm_device *dev, uint32_t ctx_id, uint32_t bo_list_handle,
                          int num_chunks, struct drm_amdgpu_cs_chunk *chunks, uint64_t *seq_no)
{
#ifdef HAVE_AMDGPU_DARWIN
   return ac_drm_cs_submit_raw2_impl(dev, ctx_id, bo_list_handle, num_chunks, chunks, seq_no, NULL, NULL);
#else
   return ac_drm_cs_submit_raw2_impl(dev, ctx_id, bo_list_handle, num_chunks, chunks, seq_no);
#endif
}

#ifdef HAVE_AMDGPU_DARWIN
int
ac_drm_dcn_cs_submit(ac_drm_device *dev, uint32_t ctx_id, uint32_t bo_list_handle, int num_chunks,
                     struct drm_amdgpu_cs_chunk *chunks, uint64_t *seq_no, const struct build34_dcn_ib *writer,
                     struct build34_dcn_native_submit *out)
{
   *out = (struct build34_dcn_native_submit){0};
   return ac_drm_cs_submit_raw2_impl(dev, ctx_id, bo_list_handle, num_chunks, chunks, seq_no, writer, out);
}
#endif

void ac_drm_cs_chunk_fence_info_to_data(""")

    replace(WINSYS_H, "struct radeon_info;\n", "struct radv_dcn_submitted_clear;\nstruct radeon_info;\n")
    replace(WINSYS_H, "struct radv_winsys_submit_info {\n", """struct radv_winsys_submit_info {
#ifdef HAVE_AMDGPU_DARWIN
   struct radv_dcn_submitted_clear *dcn_clear;
#endif
""")
    replace(QUEUE_H, "struct radv_queue {\n   struct vk_queue vk;\n", """#ifdef HAVE_AMDGPU_DARWIN
#include "build34_dcn_radv_submit.h"
#endif

struct radv_queue {
   struct vk_queue vk;
#ifdef HAVE_AMDGPU_DARWIN
   struct radv_dcn_submitted_clear dcn_clear;
#endif
""")
    replace(QUEUE, "   for (uint32_t j = 0, advance; j < cmd_buffer_count; j += advance) {", """#ifdef HAVE_AMDGPU_DARWIN
   struct radv_dcn_submitted_clear dcn_clear = {0};
   if (cmd_buffer_count == 1 && !use_ace && !use_perf_counters && !submission->is_protected &&
       !vk_queue_submit_has_bind(submission)) {
      const struct radv_cmd_buffer *writer = (const struct radv_cmd_buffer *)submission->command_buffers[0];
      if (writer->dcn_clear.phase == RADV_DCN_CLEAR_CLOSED && writer->dcn_clear.serial &&
          writer->dcn_clear.stream == writer->cs->b) {
         dcn_clear.clear = writer->dcn_clear;
         submit.dcn_clear = &dcn_clear;
      }
   }
#endif

   for (uint32_t j = 0, advance; j < cmd_buffer_count; j += advance) {""")
    replace(QUEUE, "   radv_dump_printf_data(device, stderr, true);\n\nfail:\n   free(cs_array);", """   radv_dump_printf_data(device, stderr, true);
#ifdef HAVE_AMDGPU_DARWIN
   radv_dcn_finish_submit(&queue->dcn_clear, dcn_clear, result == VK_SUCCESS);
#endif

fail:
   free(cs_array);""")
    replace(QUEUE, "   VkResult result = radv_queue_submit_bind_sparse_memory(device, submission);\n", """#ifdef HAVE_AMDGPU_DARWIN
   queue->dcn_clear = (struct radv_dcn_submitted_clear){0};
#endif
   VkResult result = radv_queue_submit_bind_sparse_memory(device, submission);
""")

    replace(CS, '#include "build34_r3_radv_entry.h"\n',
            '#include "build34_r3_radv_entry.h"\n#include "build34_dcn_radv_submit.h"\n')
    replace(CS, "struct radv_amdgpu_cs_request {\n", """struct radv_amdgpu_cs_request {
#ifdef HAVE_AMDGPU_DARWIN
   struct radv_dcn_submitted_clear *dcn_clear;
#endif
""")
    replace(CS, "bool secure)\n{\n   VkResult result;\n\n   /* Last CS", """bool secure
#ifdef HAVE_AMDGPU_DARWIN
                                      , struct radv_dcn_submitted_clear *dcn_clear
#endif
                                      )
{
   VkResult result;

   /* Last CS""")
    replace(CS, "         /* When IBs are used, we only need to submit the main IB", """#ifdef HAVE_AMDGPU_DARWIN
         const bool writer_ib = dcn_clear && cs_count == 1 && !secure && !queue_idx &&
                                cs->hw_ip == AMD_IP_GFX && cs->num_ib_buffers == 1 && !cs->chained_to &&
                                dcn_clear->clear.stream == &cs->base;
#endif
         /* When IBs are used, we only need to submit the main IB""")
    replace(CS, "         assert(num_submitted_ibs < ib_array_size);\n         ibs[num_submitted_ibs++] = ib;", """#ifdef HAVE_AMDGPU_DARWIN
         if (writer_ib && ib.size && ib.size <= UINT32_MAX / 4) {
            request.dcn_clear = dcn_clear;
            dcn_clear->ib = (struct build34_dcn_ib){ib.ib_mc_address, ib.size * 4, num_submitted_ibs};
         }
#endif
         assert(num_submitted_ibs < ib_array_size);
         ibs[num_submitted_ibs++] = ib;""")
    replace(CS, "      /* Submit the CS. */\n      request.number_of_ibs = num_submitted_ibs;", """#ifdef HAVE_AMDGPU_DARWIN
      if (request.dcn_clear) {
         if (cs_idx != cs_count)
            request.dcn_clear = NULL;
         for (unsigned index = 0; index < preamble_count; ++index) {
            if (radv_amdgpu_cs(preambles[index])->chained_to)
               request.dcn_clear = NULL;
         }
         for (unsigned index = 0; index < postamble_count; ++index) {
            if (radv_amdgpu_cs(postamble_cs[index])->chained_to)
               request.dcn_clear = NULL;
         }
      }
#endif
      /* Submit the CS. */
      request.number_of_ibs = num_submitted_ibs;""")
    replace(CS, "submit->postamble_count, submit->uses_shadow_regs, submit->secure);", """submit->postamble_count, submit->uses_shadow_regs, submit->secure
#ifdef HAVE_AMDGPU_DARWIN
         , submit->dcn_clear
#endif
         );""")
    replace(CS, "      r = ac_drm_cs_submit_raw2(ctx->ws->dev, ctx->ctx_handle, 0, num_chunks, chunks, &request->seq_no);", """#ifdef HAVE_AMDGPU_DARWIN
      if (request->dcn_clear)
         r = ac_drm_dcn_cs_submit(ctx->ws->dev, ctx->ctx_handle, 0, num_chunks, chunks, &request->seq_no,
                                  &request->dcn_clear->ib, &request->dcn_clear->native);
      else
#endif
         r = ac_drm_cs_submit_raw2(ctx->ws->dev, ctx->ctx_handle, 0, num_chunks, chunks, &request->seq_no);""")
    return sources
