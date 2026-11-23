#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage bounded retry for the matched typed receipt-capacity backend only."""

from build34_exact_submit import once
from test_build34_exact_ownership import method


SUBMIT = 'static int\nacd_exact_submit('
DRM_SUBMIT = 'static int\nacd_cmd_cs('
HELPER = '''static int
acd_exact_submit_once(struct acd_kext *, struct acd_exact_state *,
                      const struct acd_cs_plan *, uint64_t *, bool *, const uint64_t *);

static uint64_t
acd_exact_retry_remaining(struct acd_kext *k, uint64_t started)
{
   const uint64_t now = acd_kext_now_ns(k);
   const uint64_t budget = 20000000ull;
   return now >= started && now - started < budget ? budget - (now - started) : 0;
}

static int
acd_exact_make_submit_space(struct acd_kext *k, struct acd_exact_state *e,
                            uint64_t acked_before_submit, uint64_t started)
{
   uint64_t oldest[2] = {0};
   pthread_mutex_lock(&k->mtx);
   for (uint32_t index = 0; index < ACD_EXACT_RECORDS; ++index) {
      const struct acd_exact_record *record = &e->records[index];
      if (record->phase < ACD_EXACT_PENDING || record->acked || record->waiters || record->acknowledging)
         continue;
      const uint32_t queue = record->receipt.queue;
      if (!oldest[queue] || record->receipt.sequence < oldest[queue])
         oldest[queue] = record->receipt.sequence;
   }
   pthread_mutex_unlock(&k->mtx);

   const uint32_t first = oldest[1] && (!oldest[0] || oldest[1] < oldest[0]) ? 1 : 0;
   for (uint32_t turn = 0; turn <= 2; ++turn) {
      const uint64_t remaining = acd_exact_retry_remaining(k, started);
      pthread_mutex_lock(&k->mtx);
      const bool poisoned = e->poisoned;
      const bool released = e->acked_receipts != acked_before_submit;
      pthread_mutex_unlock(&k->mtx);
      if (poisoned)
         return -ECANCELED;
      if (!remaining)
         return -ETIMEDOUT;
      if (released)
         return 0;
      if (turn == 2)
         break;
      const uint64_t sequence = oldest[first ^ turn];
      if (!sequence)
         continue;
      const uint64_t slice = remaining < 5000000ull ? remaining : 5000000ull;
      bool pending;
      int result = acd_exact_wait(k, e, sequence, slice, &pending, NULL);
      if (acd_exact_terminal_error(result))
         return result == -ENOMEM ? -EIO : result;
   }
   return -EAGAIN;
}

'''


def stage_transport(source):
    source = once(source, '   uint64_t emitted, retired, native_serial;\n',
                  '   uint64_t emitted, retired, native_serial, acked_receipts;\n')
    source = once(source, '      if (!result)\n         r->acked = true;\n      else if (result != -EBUSY)\n',
                  '      if (!result) {\n         r->acked = true;\n         ++e->acked_receipts;\n'
                  '      } else if (result != -EBUSY)\n')
    submit = method(source, SUBMIT)
    seam = '   int result = acd_exact_service(k, e);\n'
    wrapper = submit[:submit.index(seam)] + '''   bool capacity = false;
   int result = acd_exact_submit_once(k, e, plan, seq, &capacity, NULL);
   if (capacity) {
      const uint64_t started = acd_kext_now_ns(k);
      pthread_mutex_lock(&k->mtx);
      const uint64_t acked_at_refusal = e->acked_receipts;
      pthread_mutex_unlock(&k->mtx);
      result = acd_exact_make_submit_space(k, e, acked_at_refusal, started);
      if (!result)
         result = acd_exact_submit_once(k, e, plan, seq, &capacity, &started);
   }
   pthread_mutex_unlock(&e->submit_mtx);
   return result == -ENOMEM ? -EIO : result;
}

'''
    body = '''static int
acd_exact_submit_once(struct acd_kext *k, struct acd_exact_state *e,
                      const struct acd_cs_plan *plan, uint64_t *seq, bool *capacity, const uint64_t *retry_started)
{
   *capacity = false;
''' + submit[submit.index(seam):]
    body = once(body, seam, '   int result = retry_started ? 0 : acd_exact_service(k, e);\n')
    body = once(body, '      if (!pass) {\n', '      if (retry_started)\n         break;\n      if (!pass) {\n')
    body = once(body, '      acd_sfence();\n', '''      if (retry_started && !acd_exact_retry_remaining(k, *retry_started)) {
         pthread_mutex_lock(&k->mtx);
         memset(r, 0, sizeof(*r));
         pthread_mutex_unlock(&k->mtx);
         return -ETIMEDOUT;
      }
      acd_sfence();
''')
    body = once(body, '         if (no_dispatch)\n            memset(r, 0, sizeof(*r));\n         else\n',
                '         if (no_dispatch) {\n            memset(r, 0, sizeof(*r));\n'
                '            *capacity = result == -EAGAIN && !e->poisoned;\n         } else\n')
    body = once(body, '   pthread_mutex_unlock(&e->submit_mtx);\n', '')
    return once(source, submit, HELPER + wrapper + body)


def stage_drm(source):
    submit = method(source, DRM_SUBMIT)
    updated = once(submit, '   if (acd_sync_has_exact_completion(dev->sync)) {\n',
                   '   const bool exact = acd_sync_has_exact_completion(dev->sync);\n   if (exact) {\n')
    updated = once(updated, '   if (r)\n      return r;\n   memset(&cs->out, 0, sizeof(cs->out));\n',
                   '   if (r)\n      return exact && seq && r == -ENOMEM ? -EIO : r;\n'
                   '   memset(&cs->out, 0, sizeof(cs->out));\n')
    return once(source, submit, updated)
