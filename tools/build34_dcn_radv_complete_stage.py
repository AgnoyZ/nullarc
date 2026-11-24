"""Derive a bounded exact-completion poll for the recorded build34 writer."""

import build34_dcn_radv_submit_stage as submit


INPUTS = submit.INPUTS


def stage(inputs):
    sources = submit.stage(inputs)

    def replace(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError(f"Build34 RADV completion anchor drift: {name}: {old[:75]}")
        sources[name] = sources[name].replace(old, new)

    kext, kext_h = submit.KEXT, submit.KEXT_H
    replace(kext_h, "struct acd_wait_status {", """struct build34_dcn_native_submit;
int acd_kext_dcn_poll(struct acd_kext *k, const struct build34_dcn_native_submit *writer, bool *busy);
void acd_kext_dcn_discard(struct acd_kext *k, const struct build34_dcn_native_submit *writer);

struct acd_wait_status {""")
    replace(kext, '#include "ac_darwin_kext.h"\n',
            '#include "ac_darwin_kext.h"\n#include "build34_dcn_native_submit.h"\n')
    replace(kext, "   struct acd_exact_record records[ACD_EXACT_RECORDS];\n", """   struct acd_exact_record records[ACD_EXACT_RECORDS];
   struct acd_exact_record *dcn_writer;
   uint32_t dcn_context;
""")
    replace(kext, "          !r->waiters && r->receipt.sequence <= e->retired)\n",
            "          !r->waiters && r != e->dcn_writer && r->receipt.sequence <= e->retired)\n")
    replace(kext, "static int\nacd_exact_wait(struct acd_kext *k, struct acd_exact_state *e, uint64_t seq,\n"
            "               uint64_t rel_ns, bool *busy, struct acd_wait_status *st)", """static bool
acd_exact_dcn_matches(const struct acd_exact_state *e, const struct build34_dcn_native_submit *writer)
{
   if (!e || !e->dcn_writer || e->dcn_writer->phase < ACD_EXACT_PENDING || e->dcn_context != writer->context)
      return false;
   const struct acd_exact_receipt *accepted = &e->dcn_writer->receipt;
   return accepted->owner == writer->owner && accepted->serial == writer->serial &&
          accepted->sequence == writer->sequence && accepted->generation == writer->generation &&
          accepted->slot == writer->slot && accepted->queue == writer->queue;
}

void
acd_kext_dcn_discard(struct acd_kext *k, const struct build34_dcn_native_submit *writer)
{
   if (!writer->sequence)
      return;
   pthread_mutex_lock(&k->mtx);
   struct acd_exact_state *e = k->exact;
   if (acd_exact_dcn_matches(e, writer))
      e->dcn_writer = NULL;
   pthread_mutex_unlock(&k->mtx);
}

static int
acd_exact_wait_impl(struct acd_kext *k, struct acd_exact_state *e, uint64_t seq,
                    uint64_t rel_ns, bool *busy, struct acd_wait_status *st,
                    const struct build34_dcn_native_submit *writer)""")
    replace(kext, """   struct acd_exact_record *r = NULL;
   for (uint32_t i = 0; i < ACD_EXACT_RECORDS; i++) {
      if (e->records[i].phase >= ACD_EXACT_PENDING && e->records[i].receipt.sequence == seq) {
         r = &e->records[i];
         break;
      }
   }
   if (!r && !(seq <= e->retired && seq <= e->emitted)) {
      pthread_mutex_unlock(&k->mtx);
      return -ENOENT;
   }
""", """   struct acd_exact_record *r = NULL;
   if (writer) {
      if (!acd_exact_dcn_matches(e, writer)) {
         pthread_mutex_unlock(&k->mtx);
         return -ENOENT;
      }
      r = e->dcn_writer;
   } else {
      for (uint32_t i = 0; i < ACD_EXACT_RECORDS; i++) {
         if (e->records[i].phase >= ACD_EXACT_PENDING && e->records[i].receipt.sequence == seq) {
            r = &e->records[i];
            break;
         }
      }
      if (!r && !(seq <= e->retired && seq <= e->emitted)) {
         pthread_mutex_unlock(&k->mtx);
         return -ENOENT;
      }
   }
""")
    replace(kext, "   bool pending = r && r->phase != ACD_EXACT_COMPLETE;\n   pthread_mutex_unlock(&k->mtx);", """   bool pending = r && r->phase != ACD_EXACT_COMPLETE;
   if (writer) {
      if (r != e->dcn_writer) {
         pthread_mutex_unlock(&k->mtx);
         return -ENOENT;
      }
      *busy = pending;
      pthread_mutex_unlock(&k->mtx);
      return 0;
   }
   pthread_mutex_unlock(&k->mtx);""")
    replace(kext, "static int\nacd_exact_submit_once(struct acd_kext *,", """static int
acd_exact_wait(struct acd_kext *k, struct acd_exact_state *e, uint64_t seq,
               uint64_t rel_ns, bool *busy, struct acd_wait_status *st)
{
   return acd_exact_wait_impl(k, e, seq, rel_ns, busy, st, NULL);
}

int
acd_kext_dcn_poll(struct acd_kext *k, const struct build34_dcn_native_submit *writer, bool *busy)
{
   if (!busy)
      return -EINVAL;
   *busy = true;
   if (!k || !writer || !build34_dcn_valid_native_submit(*writer, writer->sequence))
      return -EINVAL;
   pthread_mutex_lock(&k->mtx);
   struct acd_exact_state *e = k->exact;
   pthread_mutex_unlock(&k->mtx);
   if (!e)
      return -EOPNOTSUPP;

   int result = pthread_mutex_trylock(&e->submit_mtx);
   if (result)
      return result == EBUSY ? -EAGAIN : -result;
   result = acd_exact_wait_impl(k, e, writer->sequence, 0, busy, NULL, writer);
   pthread_mutex_unlock(&e->submit_mtx);
   return result;
}

static int
acd_exact_submit_once(struct acd_kext *,""")
    replace(kext, "   const uint64_t acked_before_submit = e->acked_receipts;", """   e->dcn_writer = NULL;
   const uint64_t acked_before_submit = e->acked_receipts;""")
    replace(kext, """         acd_exact_fold(e);
         if (plan->receipt_out)
            *plan->receipt_out = receipt;
         *seq = receipt.sequence;""", """         if (plan->receipt_out && receipt.queue == 1) {
            e->dcn_context = plan->ctx_id;
            e->dcn_writer = r;
            *plan->receipt_out = receipt;
         }
         acd_exact_fold(e);
         *seq = receipt.sequence;""")

    drm, drm_h = submit.DRM, submit.DRM_H
    replace(drm_h, "int acd_ioctl(", """int acd_dcn_poll(acd_device_handle dev, const struct build34_dcn_native_submit *writer, bool *busy);

int acd_ioctl(""")
    replace(drm, """   if (r)
      return exact && seq && r == -ENOMEM ? -EIO : r;
   if (out) {
      const struct build34_dcn_native_submit receipt = {
         accepted.sequence, accepted.owner, accepted.serial, accepted.generation,
         accepted.slot, accepted.queue, ctx_id,
      };
      if (build34_dcn_valid_native_submit(receipt, seq))
         *out = receipt;
   }
""", """   const struct build34_dcn_native_submit receipt = {
      accepted.sequence, accepted.owner, accepted.serial, accepted.generation,
      accepted.slot, accepted.queue, ctx_id,
   };
   if (r) {
      if (receipt.sequence)
         acd_kext_dcn_discard(dev->core->kext, &receipt);
      return exact && seq && r == -ENOMEM ? -EIO : r;
   }
   if (out && build34_dcn_valid_native_submit(receipt, seq))
      *out = receipt;
""")
    replace(drm, "int\nacd_device_exact_profile(", """int
acd_dcn_poll(acd_device_handle dev, const struct build34_dcn_native_submit *writer, bool *busy)
{
   return acd_kext_dcn_poll(dev ? dev->core->kext : NULL, writer, busy);
}

int
acd_device_exact_profile(""")

    raw, raw_h = submit.RAW, submit.RAW_H
    replace(raw_h, "int ac_drm_dcn_cs_submit(", """int ac_drm_dcn_poll(ac_drm_device *dev, const struct build34_dcn_native_submit *writer, bool *busy);
int ac_drm_dcn_cs_submit(""")
    replace(raw, "int\nac_drm_dcn_cs_submit(", """int
ac_drm_dcn_poll(ac_drm_device *dev, const struct build34_dcn_native_submit *writer, bool *busy)
{
   return acd_dcn_poll(dev && dev->is_darwin ? dev->ddev : NULL, writer, busy);
}

int
ac_drm_dcn_cs_submit(""")
    replace(submit.CS, "static void\nradv_amdgpu_winsys_get_cpu_addr(", """#ifdef HAVE_AMDGPU_DARWIN
int
radv_dcn_poll_native(const struct radeon_winsys *ws, const struct build34_dcn_native_submit *writer, bool *busy)
{
   if (!busy)
      return -EINVAL;
   *busy = true;
   if (!ws || ws->cs_submit != radv_amdgpu_winsys_cs_submit || !writer)
      return -EINVAL;
   const struct radv_amdgpu_winsys *amdgpu = (const struct radv_amdgpu_winsys *)ws;
   return ac_drm_dcn_poll(amdgpu->dev, writer, busy);
}
#endif

static void
radv_amdgpu_winsys_get_cpu_addr(""")
    return sources
