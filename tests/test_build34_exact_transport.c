// SPDX-License-Identifier: MIT
// Actual Mesa ioctl/provider/transport; bounded fake CPU session, NOT a GPU.
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ac_darwin_drm.c"

static atomic_uint checks;
#define CHECK(x) do { atomic_fetch_add(&checks, 1); if (!(x)) { \
   fprintf(stderr, "check failed %d: %s\n", __LINE__, #x); abort(); } } while (0)
int acd_kext_open_iokit(struct acd_kext **out) { (void)out; CHECK(false); return -ENOSYS; }

#ifndef HAVE_EXACT_RECEIPT_LIFETIME
struct lost { bool known; unsigned waits; };
static int naive(void *ctx, uint32_t sel, const uint64_t *sin, uint32_t nin,
                 const void *in, size_t size, uint64_t *out, uint32_t *nout,
                 void *blob, size_t *blobsize)
{
   (void)in; (void)size; (void)blob; (void)blobsize;
   struct lost *f = ctx;
   CHECK(sel == ACD_SEL_WAIT_SEQ && nin == 3 && sin[0] == 20 && *nout == 3);
   f->waits++;
   if (!f->known) return ACD_KR_NOT_FOUND;
   out[0] = 0; out[1] = 9; out[2] = 20;
   f->known = false; // prospective naive auto-ACK loses the only native record
   return 0;
}
int main(void)
{
   unsetenv("RADV_DARWIN_TRACE");
   struct lost f = {.known = true};
   const struct acd_kext_ops ops = {.call = naive};
   struct acd_kext *k = acd_kext_create(&ops, &f); CHECK(k);
   const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = k, .exact_completion = true};
   struct util_sync_provider *s = acd_sync_provider_create(&be); CHECK(s);
   bool busy = true; CHECK(acd_kext_wait_seq(k, 20, 0, &busy, NULL) == 0 && !busy);
   uint32_t h; CHECK(s->create(s, 0, &h) == 0);
   CHECK(acd_sync_cs_attach(s, h, 0, 20) == 0);
   CHECK(s->wait(s, &h, 1, 0, 0, NULL) == -1 && errno == ENOENT && f.waits == 2);
   CHECK(acd_kext_wait_seq(k, 20, 0, &busy, NULL) == -ENOENT);
   s->finalize(s); acd_kext_destroy(k);
   puts("PASS 0006-only prospective auto-ACK counterexample: late provider attach and raw WaitCS lose completion; GPU_executed=false");
}
#else

struct native_record { struct acd_exact_receipt receipt; bool used, done; unsigned pins; };
struct fixture {
   struct acd_core core;
   struct acd_device dev;
   struct acd_exact_backend backend;
   pthread_mutex_t lock;
   pthread_cond_t cond;
   struct native_record native[64];
   uint64_t next, serial, prefix, owner, block_seq, reenter_seq;
   atomic_uint_fast64_t now;
   unsigned submits, waits, acks, snapshots, closes, entered, released, native_count;
   unsigned ack_busy, malformed, submit_error, wait_error, prefix_error, ack_error;
   bool no_dispatch, stale_wait, hold_ack, ack_entered, release_ack, reenter, inject_submit;
   uint64_t last_prefix_target, first_prefix_target, user_fence_value;
};
static void lock(struct fixture *f) { CHECK(pthread_mutex_lock(&f->lock) == 0); }
static void unlock(struct fixture *f) { CHECK(pthread_mutex_unlock(&f->lock) == 0); }
static void broadcast(struct fixture *f) { CHECK(pthread_cond_broadcast(&f->cond) == 0); }
static struct native_record *find(struct fixture *f, uint64_t seq)
{
   for (unsigned i = 0; i < 64; i++)
      if (f->native[i].used && f->native[i].receipt.sequence == seq) return &f->native[i];
   return NULL;
}
static uint64_t submit(struct fixture *f, unsigned engine);
static void reenter(struct fixture *f)
{
   if (!f->reenter) return;
   CHECK(acd_kext_set_exact_backend(f->core.kext, &f->backend) == -EBUSY);
   if (f->reenter_seq) {
      bool busy = true;
      CHECK(acd_kext_wait_seq(f->core.kext, f->reenter_seq, 0, &busy, NULL) == 0 && !busy);
   }
}
static int exact_submit(void *ctx, const void *packet, size_t size,
                        struct acd_exact_receipt *out, bool *no_dispatch)
{
   struct fixture *f = ctx;
   reenter(f);
   const struct n48n_cs_in *h = packet;
   const struct n48n_cs_ib *ibs = (const void *)((const char *)packet + sizeof(*h));
   CHECK(size == sizeof(*h) + h->num_ibs * sizeof(*ibs) && h->num_ibs && h->num_ibs <= N48N_MAX_IBS);
   CHECK(h->abi == N48N_ABI_VERSION && h->ctx_id == 1 && !h->reserved);
   for (unsigned i = 0; i < h->num_ibs; i++) {
      CHECK(ibs[i].ip_type == ibs[0].ip_type && !ibs[i].ip_instance && !ibs[i].ring);
      CHECK(ibs[i].ib_bytes == 4 && ibs[i].va_start >= 0x20000);
   }
   lock(f); f->submits++;
   if (f->submit_error) {
      *no_dispatch = f->no_dispatch;
      int result = -(int)f->submit_error; unlock(f); return result;
   }
   if (f->native_count == 64) {
      *no_dispatch = true; unlock(f); return -EAGAIN;
   }
   struct native_record *r = NULL;
   for (unsigned i = 0; i < 64; i++) if (!f->native[i].used) { r = &f->native[i]; break; }
   CHECK(r);
   r->used = true; f->native_count++;
   r->receipt = (struct acd_exact_receipt){.sequence = f->next, .owner = f->owner,
      .serial = ++f->serial, .generation = 7, .slot = (uint32_t)(r - f->native), .queue = ibs[0].ip_type};
   f->next += 10;
   if (h->flags & N48N_CS_HAS_FENCE) {
      CHECK(h->fence_handle == 7 && h->fence_offset == 16);
      f->user_fence_value = r->receipt.sequence; // CPU fake contract only
   }
   *out = r->receipt;
   switch (f->malformed) {
   case 1: out->owner++; break;
   case 2: out->serial = 0; break;
   case 3: out->generation = 0; break;
   case 4: out->slot = 64; break;
   case 5: out->queue = 2; break;
   case 6: out->sequence = 0; break;
   case 7: out->sequence = UINT64_MAX; break;
   case 8: out->sequence -= 10; break;
   case 9: *no_dispatch = true; break;
   case 10: out->serial = UINT64_MAX; break;
   case 11: out->generation = UINT64_MAX; break;
   case 12: out->serial--; break;
   default: break;
   }
   unlock(f); return 0;
}
static int exact_wait(void *ctx, const struct acd_exact_receipt *receipt, uint64_t ns,
                      bool *busy, struct acd_exact_snapshot *out)
{
   struct fixture *f = ctx; CHECK(ns <= N48N_WAIT_CAP_NS); reenter(f);
   lock(f); f->waits++;
   struct native_record *r = find(f, receipt->sequence); CHECK(r);
   CHECK(memcmp(&r->receipt, receipt, sizeof(*receipt)) == 0);
   r->pins++;
   bool pending = !r->done;
   struct acd_exact_snapshot snapshot = {.owner = f->owner, .retired = f->prefix};
   if (f->block_seq == receipt->sequence) {
      unsigned ordinal = ++f->entered; broadcast(f);
      while (f->released < ordinal) CHECK(pthread_cond_wait(&f->cond, &f->lock) == 0);
   }
   *busy = f->stale_wait ? pending : !r->done;
   *out = f->stale_wait ? snapshot : (struct acd_exact_snapshot){.owner = f->owner, .retired = f->prefix};
   if (f->malformed == 20) out->owner++;
   if (f->malformed == 21) out->retired = UINT64_MAX;
   r->pins--;
   int error = -(int)f->wait_error;
   unlock(f); return error;
}
static int exact_ack(void *ctx, const struct acd_exact_receipt *receipt)
{
   struct fixture *f = ctx; reenter(f);
   lock(f); f->acks++;
   struct native_record *r = find(f, receipt->sequence); CHECK(r);
   CHECK(memcmp(&r->receipt, receipt, sizeof(*receipt)) == 0);
   CHECK(r->done || receipt->sequence <= f->prefix);
   CHECK(!r->pins); // transport pins must prevent ACK before callbacks leave
   if (f->hold_ack) {
      f->ack_entered = true; broadcast(f);
      while (!f->release_ack) CHECK(pthread_cond_wait(&f->cond, &f->lock) == 0);
   }
   if (f->ack_busy) { f->ack_busy--; unlock(f); return -EBUSY; }
   if (f->ack_error) { int error = -(int)f->ack_error; unlock(f); return error; }
   memset(r, 0, sizeof(*r)); f->native_count--;
   unlock(f); return 0;
}
static int exact_prefix(void *ctx, uint64_t target, uint64_t ns, struct acd_exact_snapshot *out)
{
   struct fixture *f = ctx; CHECK(target != UINT64_MAX && ns <= N48N_WAIT_CAP_NS);
   CHECK(target || !ns); reenter(f);
   lock(f); f->snapshots++;
   f->last_prefix_target = target;
   if (!f->first_prefix_target) f->first_prefix_target = target;
   *out = (struct acd_exact_snapshot){.owner = f->owner, .retired = f->prefix};
   if (f->malformed == 20) out->owner++;
   if (f->malformed == 21) out->retired = UINT64_MAX;
   int error = -(int)f->prefix_error;
   bool inject = f->inject_submit; f->inject_submit = false;
   unlock(f);
   if (inject) (void)submit(f, AMDGPU_HW_IP_GFX);
   if (ns) atomic_fetch_add(&f->now, ns);
   return error;
}
static int forbidden(void *ctx, uint32_t sel, const uint64_t *sin, uint32_t nin,
                     const void *in, size_t n, uint64_t *out, uint32_t *nout, void *blob, size_t *nb)
{
   (void)ctx; (void)sel; (void)sin; (void)nin; (void)in; (void)n;
   (void)out; (void)nout; (void)blob; (void)nb;
   CHECK(false); return ACD_KR_UNSUPPORTED; // especially no legacy WAITSEQ(0)
}
static uint64_t now_ns(void *ctx) { return atomic_load(&((struct fixture *)ctx)->now); }
static void close_fake(void *ctx) { ((struct fixture *)ctx)->closes++; }
static void initialize(struct fixture *f)
{
   memset(f, 0, sizeof(*f)); f->next = 10; f->prefix = 9; f->owner = 77;
   atomic_init(&f->now, 100);
   CHECK(pthread_mutex_init(&f->lock, NULL) == 0 && pthread_cond_init(&f->cond, NULL) == 0);
   CHECK(pthread_mutex_init(&f->core.bo_lock, NULL) == 0);
   const struct acd_kext_ops ops = {.call = forbidden, .close = close_fake, .now_ns = now_ns};
   f->core.kext = acd_kext_create(&ops, f); CHECK(f->core.kext);
   f->backend = (struct acd_exact_backend){.owner = f->owner, .ctx = f, .submit = exact_submit,
      .wait = exact_wait, .ack = exact_ack, .wait_prefix = exact_prefix};
   CHECK(acd_kext_set_exact_backend(f->core.kext, &f->backend) == 0);
   const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq,
      .ctx = f->core.kext, .exact_completion = true};
   f->core.sync = acd_sync_provider_create(&be); CHECK(f->core.sync);
   f->dev = (struct acd_device){.core = &f->core, .sync = f->core.sync};
}
static void finalize(struct fixture *f)
{
   f->core.sync->finalize(f->core.sync); acd_kext_destroy(f->core.kext);
   CHECK(f->closes == 1 && pthread_mutex_destroy(&f->core.bo_lock) == 0);
   CHECK(pthread_cond_destroy(&f->cond) == 0 && pthread_mutex_destroy(&f->lock) == 0);
}
static int submit_result(struct fixture *f, unsigned engine, uint64_t *out, bool fence)
{
   struct drm_amdgpu_cs_chunk_ib ib = {.va_start = 0x20000, .ib_bytes = 4, .ip_type = engine};
   struct drm_amdgpu_cs_chunk_fence user = {.handle = 7, .offset = 16};
   struct drm_amdgpu_cs_chunk chunks[2] = {
      {.chunk_id = AMDGPU_CHUNK_ID_IB, .length_dw = sizeof(ib)/4, .chunk_data = (uintptr_t)&ib},
      {.chunk_id = AMDGPU_CHUNK_ID_FENCE, .length_dw = sizeof(user)/4, .chunk_data = (uintptr_t)&user},
   };
   uint64_t pointers[2] = {(uintptr_t)&chunks[0], (uintptr_t)&chunks[1]};
   union drm_amdgpu_cs cs = {.in = {.ctx_id = 1, .num_chunks = fence ? 2 : 1, .chunks = (uintptr_t)pointers}};
   unsigned char before[sizeof(cs)]; memcpy(before, &cs, sizeof(cs));
   int r = acd_ioctl(&f->dev, DRM_AMDGPU_CS, &cs, sizeof(cs));
   if (r) CHECK(memcmp(before, &cs, sizeof(cs)) == 0);
   else *out = cs.out.handle;
   return r;
}
static uint64_t submit(struct fixture *f, unsigned engine)
{
   uint64_t seq = 777; CHECK(submit_result(f, engine, &seq, false) == 0 && seq != 777); return seq;
}
static void done(struct fixture *f, uint64_t seq)
{
   lock(f); struct native_record *r = find(f, seq); CHECK(r); r->done = true; unlock(f);
}
static bool query(struct fixture *f, uint64_t seq)
{
   bool busy = true; struct acd_wait_status status = {UINT64_MAX, UINT64_MAX};
   CHECK(acd_kext_wait_seq(f->core.kext, seq, 0, &busy, &status) == 0);
   lock(f); CHECK(status.retired <= f->prefix && status.emitted < f->next); unlock(f);
   return !busy;
}
static uint32_t attach(struct fixture *f, uint64_t seq)
{
   uint32_t handle; CHECK(f->core.sync->create(f->core.sync, 0, &handle) == 0);
   CHECK(acd_sync_cs_attach(f->core.sync, handle, 0, seq) == 0); return handle;
}
static bool ready(struct fixture *f, uint32_t h)
{
   int r = f->core.sync->wait(f->core.sync, &h, 1, 0, 0, NULL);
   CHECK(!r || (r == -1 && errno == ETIME)); return !r;
}
static void late_and_idle(void)
{
   struct fixture f; initialize(&f);
   uint64_t c = submit(&f, AMDGPU_HW_IP_COMPUTE), g = submit(&f, AMDGPU_HW_IP_GFX);
   CHECK(c == 10 && g == 20); uint32_t pending = attach(&f, c);
   done(&f, g); CHECK(query(&f, g) && f.acks == 1 && f.native_count == 1);
   uint32_t late = attach(&f, g); unsigned calls = f.waits;
   CHECK(ready(&f, late) && !ready(&f, pending) && f.waits == calls + 1);
   CHECK(query(&f, g) && f.waits == calls + 1);
   union drm_amdgpu_wait_cs raw = {.in = {.handle = g, .timeout = 100}};
   CHECK(acd_ioctl(&f.dev, DRM_AMDGPU_WAIT_CS, &raw, sizeof(raw)) == 0 && !raw.out.status);
   CHECK(!query(&f, N48N_SEQ_LAST) && f.last_prefix_target == g);
   union drm_amdgpu_gem_wait_idle idle = {.in = {.handle = 1, .timeout = 100}};
   CHECK(acd_ioctl(&f.dev, DRM_AMDGPU_GEM_WAIT_IDLE, &idle, sizeof(idle)) == 0 && idle.out.status);
   CHECK(f.last_prefix_target == g && !ready(&f, pending) && f.prefix == 9);
   CHECK(query(&f, 0)); done(&f, c); f.prefix = g;
   CHECK(query(&f, N48N_SEQ_LAST) && f.native_count == 0);
   CHECK(query(&f, c) && query(&f, g));
   bool busy = true; unsigned waits = f.waits;
   CHECK(acd_kext_wait_seq(f.core.kext, 15, 0, &busy, NULL) == 0 && !busy && f.waits == waits);
   CHECK(acd_kext_wait_seq(f.core.kext, 21, 0, &busy, NULL) == -ENOENT);
   finalize(&f);
}
static void capacity_and_prefix(void)
{
   struct fixture f; initialize(&f); uint64_t first = submit(&f, 1), last = 0;
   for (unsigned i = 1; i < ACD_EXACT_RECORDS; i++) {
      last = submit(&f, 0);
      done(&f, last); CHECK(query(&f, last) && f.native_count == 1);
   }
   CHECK(!query(&f, first) && query(&f, 20) && f.acks == ACD_EXACT_RECORDS - 1);
   unsigned submissions = f.submits, snapshots = f.snapshots; uint64_t out = 777;
   CHECK(submit_result(&f, 0, &out, false) == -EAGAIN && out == 777 && f.submits == submissions);
   CHECK(f.snapshots == snapshots + 1 && !query(&f, first) && query(&f, 20));
   done(&f, first); f.prefix = last; CHECK(submit_result(&f, 0, &out, false) == 0 && out > last);
   CHECK(query(&f, first) && !query(&f, out));
   CHECK(f.acks == ACD_EXACT_RECORDS && f.native_count == 1);
   finalize(&f);
}
static void native_full_and_ack_busy(void)
{
   struct fixture f; initialize(&f); uint64_t seq[64];
   for (unsigned i = 0; i < 64; i++) seq[i] = submit(&f, i % 2);
   uint64_t out = 777; CHECK(submit_result(&f, 0, &out, false) == -EAGAIN && out == 777 && f.native_count == 64);
   done(&f, seq[1]); f.ack_busy = 2;
   CHECK(query(&f, seq[1]) && f.native_count == 64 && f.acks == 1);
   CHECK(query(&f, seq[1]) && f.native_count == 64 && f.acks == 2);
   CHECK(query(&f, seq[1]) && f.native_count == 63 && f.acks == 3);
   CHECK(submit_result(&f, 0, &out, false) == 0 && f.native_count == 64 && out > seq[63]);
   CHECK(query(&f, seq[1]) && !query(&f, seq[0]));
   finalize(&f);
}
static void failures(void)
{
   for (unsigned malformed = 1; malformed <= 12; malformed++) {
      struct fixture f; initialize(&f); (void)submit(&f, 0); f.malformed = malformed;
      uint64_t out = 777;
      CHECK(submit_result(&f, 0, &out, false) == -EPROTO && out == 777);
      unsigned calls = f.submits;
      CHECK(submit_result(&f, 0, &out, false) == -ECANCELED && f.submits == calls && out == 777);
      CHECK(f.native_count == 2 && !f.acks); finalize(&f);
   }
   for (unsigned definite = 0; definite < 2; definite++) {
      struct fixture f; initialize(&f); f.submit_error = EIO; f.no_dispatch = definite;
      uint64_t out = 777; CHECK(submit_result(&f, 0, &out, false) == -EIO && out == 777);
      f.submit_error = 0;
      int r = submit_result(&f, 0, &out, false);
      CHECK(definite ? r == 0 && out == 10 : r == -ECANCELED && out == 777);
      finalize(&f);
   }
   for (unsigned which = 0; which < 6; which++) {
      struct fixture f; initialize(&f); uint64_t seq = submit(&f, 0); done(&f, seq);
      if (which < 2) f.malformed = 20 + which;
      if (which == 2) f.wait_error = EINTR;
      if (which == 3) f.ack_error = EIO;
      if (which == 4) f.prefix_error = EINTR;
      if (which == 5) f.malformed = 20;
      bool busy = true; struct acd_wait_status status = {555, 666};
      uint64_t target = which >= 4 ? N48N_SEQ_LAST : seq;
      int r = acd_kext_wait_seq(f.core.kext, target, 0, &busy, &status);
      CHECK(r < 0 && busy && status.retired == 555 && status.emitted == 666);
      CHECK(f.native_count == 1);
      if (which == 2 || which == 4) {
         f.wait_error = f.prefix_error = 0; CHECK(query(&f, seq));
      } else {
         f.malformed = 0;
         CHECK(acd_kext_wait_seq(f.core.kext, seq, 0, &busy, &status) == -ECANCELED);
      }
      finalize(&f);
   }
   const unsigned errors[] = {EIO, ENODEV, ECANCELED, ETIME, ENOENT};
   for (unsigned path = 0; path < 2; path++) for (unsigned i = 0; i < 5; i++) {
      struct fixture f; initialize(&f);
      uint64_t old = submit(&f, 0), target = submit(&f, 1);
      done(&f, old); CHECK(query(&f, old));
      if (path) f.prefix_error = errors[i]; else f.wait_error = errors[i];
      bool busy = true; struct acd_wait_status status = {555, 666};
      CHECK(acd_kext_wait_seq(f.core.kext, path ? N48N_SEQ_LAST : target, 0, &busy, &status) == -(int)errors[i]);
      CHECK(busy && status.retired == 555 && status.emitted == 666);
      f.prefix_error = f.wait_error = 0;
      CHECK(acd_kext_wait_seq(f.core.kext, old, 0, &busy, NULL) == -ECANCELED);
      CHECK(f.native_count == 1); finalize(&f);
   }
   for (unsigned path = 0; path < 2; path++) {
      struct fixture f; initialize(&f); uint64_t seq = submit(&f, 0);
      if (path) f.prefix_error = EAGAIN; else f.wait_error = EAGAIN;
      bool busy = true;
      CHECK(acd_kext_wait_seq(f.core.kext, path ? N48N_SEQ_LAST : seq, 0, &busy, NULL) == -EAGAIN && busy);
      f.prefix_error = f.wait_error = 0; done(&f, seq);
      CHECK(query(&f, seq) && f.native_count == 0); finalize(&f);
   }
}
struct waiter { struct fixture *f; uint64_t seq; int result; bool busy; struct acd_wait_status status; };
static void *waiting(void *ctx)
{
   struct waiter *w = ctx; w->busy = true;
   w->result = acd_kext_wait_seq(w->f->core.kext, w->seq, 0, &w->busy, &w->status); return NULL;
}
static void wait_entered(struct fixture *f, unsigned n)
{
   lock(f); while (f->entered < n) CHECK(pthread_cond_wait(&f->cond, &f->lock) == 0); unlock(f);
}
static void threaded(void)
{
   // Two admitted native readers: neither the first completion nor a prefix
   // fold may ACK/reuse the pinned record until both have returned.
   struct fixture f; initialize(&f); uint64_t c = submit(&f, 1), g = submit(&f, 0);
   f.block_seq = g; struct waiter w[2] = {{.f = &f, .seq = g}, {.f = &f, .seq = g}};
   pthread_t t[2];
   CHECK(pthread_create(&t[0], NULL, waiting, &w[0]) == 0); wait_entered(&f, 1);
   CHECK(pthread_create(&t[1], NULL, waiting, &w[1]) == 0); wait_entered(&f, 2);
   lock(&f); find(&f, g)->done = true; f.released = 1; broadcast(&f); unlock(&f);
   CHECK(pthread_join(t[0], NULL) == 0 && !w[0].result && !w[0].busy);
   CHECK(!f.acks && query(&f, g) && !query(&f, c));
   lock(&f); f.released = 2; broadcast(&f); unlock(&f);
   CHECK(pthread_join(t[1], NULL) == 0 && !w[1].result && !w[1].busy);
   CHECK(f.acks == 1 && query(&f, g) && f.native_count == 1); finalize(&f);

   // An old pending reply cannot undo another reader's completed fact.
   initialize(&f); g = submit(&f, 0); f.block_seq = g; f.stale_wait = true;
   w[0] = (struct waiter){.f = &f, .seq = g};
   CHECK(pthread_create(&t[0], NULL, waiting, &w[0]) == 0); wait_entered(&f, 1);
   lock(&f); f.block_seq = 0; find(&f, g)->done = true; unlock(&f);
   CHECK(query(&f, g) && !f.acks);
   lock(&f); f.released = 1; broadcast(&f); unlock(&f);
   CHECK(pthread_join(t[0], NULL) == 0 && !w[0].result && !w[0].busy && f.acks == 1);
   finalize(&f);

   // Block an ACK while a different thread advances the prefix, queries the
   // cached record, and submits; the in-flight slot must remain stable.
   initialize(&f); g = submit(&f, 0); done(&f, g); f.hold_ack = true;
   w[0] = (struct waiter){.f = &f, .seq = g};
   CHECK(pthread_create(&t[0], NULL, waiting, &w[0]) == 0);
   lock(&f); while (!f.ack_entered) CHECK(pthread_cond_wait(&f.cond, &f.lock) == 0);
   f.prefix = g; unlock(&f);
   CHECK(query(&f, 0) && query(&f, g)); c = submit(&f, 1); CHECK(c > g);
   lock(&f); f.release_ack = true; broadcast(&f); unlock(&f);
   CHECK(pthread_join(t[0], NULL) == 0 && !w[0].result && !w[0].busy && f.native_count == 1);
   CHECK(query(&f, g) && !query(&f, c)); finalize(&f);

   // An older pending/safe-prefix reply arrives after a new global snapshot
   // covers its still-pinned ticket. Neither completion nor the prefix regresses.
   initialize(&f); g = submit(&f, 0); f.block_seq = g; f.stale_wait = true;
   w[0] = (struct waiter){.f = &f, .seq = g};
   CHECK(pthread_create(&t[0], NULL, waiting, &w[0]) == 0); wait_entered(&f, 1);
   lock(&f); f.prefix = g; unlock(&f);
   CHECK(query(&f, 0) && query(&f, g) && !f.acks);
   lock(&f); f.released = 1; broadcast(&f); unlock(&f);
   CHECK(pthread_join(t[0], NULL) == 0 && !w[0].result && !w[0].busy);
   CHECK(w[0].status.retired == g && f.acks == 1 && f.native_count == 0);
   finalize(&f);
}
static void configuration_deadline_and_reentrance(void)
{
   struct fixture f; initialize(&f);
   CHECK(acd_kext_set_exact_backend(f.core.kext, &f.backend) == -EBUSY);
   struct acd_exact_backend bad = f.backend; bad.owner = 0;
   CHECK(acd_kext_set_exact_backend(f.core.kext, &bad) == -EINVAL);
   bad = f.backend; bad.wait_prefix = NULL;
   CHECK(acd_kext_set_exact_backend(f.core.kext, &bad) == -EINVAL);
   uint64_t first = submit(&f, 0); done(&f, first); CHECK(query(&f, first));
   f.reenter = true; f.reenter_seq = first;
   uint64_t second = 777; CHECK(submit_result(&f, 1, &second, true) == 0);
   CHECK(second == 20 && f.user_fence_value == second);
   done(&f, second); CHECK(query(&f, second));
   f.inject_submit = true; bool busy = false;
   CHECK(acd_kext_wait_deadline(f.core.kext, N48N_SEQ_LAST, 2*N48N_WAIT_CAP_NS + 100, &busy) == 0 && busy);
   CHECK(f.first_prefix_target == second && f.last_prefix_target == second && f.next == 40);
   CHECK(atomic_load(&f.now) == 2*N48N_WAIT_CAP_NS + 100);
   CHECK(f.snapshots == 2); // the stable LAST target does not chase the injected CS
   finalize(&f);
}
static int legacy_zero(void *ctx, uint32_t sel, const uint64_t *sin, uint32_t nin,
                       const void *in, size_t size, uint64_t *out, uint32_t *nout,
                       void *blob, size_t *blobsize)
{
   (void)ctx; (void)in; (void)size; (void)blob; (void)blobsize;
   CHECK(sel == ACD_SEL_WAIT_SEQ && nin == 3 && sin[0] == 0 && *nout == 3);
   out[0] = out[1] = out[2] = 0; return 0;
}
static void admission_and_direct_shapes(void)
{
   struct fixture f; initialize(&f);
   struct n48n_cs_ib ibs[65];
   for (unsigned i = 0; i < 65; i++) ibs[i] = (struct n48n_cs_ib){.va_start = 0x20000, .ib_bytes = 4};
   struct acd_cs_plan p = {.ctx_id = 1, .ibs = ibs, .n_ibs = 65};
   uint64_t out = 777;
   CHECK(acd_kext_submit(f.core.kext, &p, &out) == -EOPNOTSUPP && out == 777);
   p.n_ibs = 2; ibs[1].ip_type = 1;
   CHECK(acd_kext_submit(f.core.kext, &p, &out) == -EOPNOTSUPP && out == 777);
   ibs[1].ip_type = 0; ibs[1].ip_instance = 1;
   CHECK(acd_kext_submit(f.core.kext, &p, &out) == -EOPNOTSUPP && out == 777);
   ibs[1].ip_instance = 0; ibs[1].ring = 1;
   CHECK(acd_kext_submit(f.core.kext, &p, &out) == -EOPNOTSUPP && out == 777);
   ibs[1].ring = 0; ibs[1].ip_type = ibs[0].ip_type = 99;
   CHECK(acd_kext_submit(f.core.kext, &p, &out) == -EOPNOTSUPP && out == 777);
   p.n_ibs = 0; CHECK(acd_kext_submit(f.core.kext, &p, &out) == -EINVAL && out == 777);
   CHECK(!f.submits && !f.waits && !f.snapshots && !f.acks);
   finalize(&f);

   // Any sequence traffic, including a zero-budget legacy poll, freezes setup.
   const struct acd_kext_ops ops = {.call = legacy_zero};
   struct acd_kext *k = acd_kext_create(&ops, NULL); CHECK(k);
   bool busy = true; CHECK(acd_kext_wait_seq(k, 0, 0, &busy, NULL) == 0 && !busy);
   CHECK(acd_kext_set_exact_backend(k, &f.backend) == -EBUSY);
   acd_kext_destroy(k);
}
int main(void)
{
   unsetenv("RADV_DARWIN_TRACE");
   late_and_idle(); capacity_and_prefix(); native_full_and_ack_busy(); failures(); threaded();
   configuration_deadline_and_reentrance(); admission_and_direct_shapes();
   printf("PASS actual Mesa exact receipt lifetime: %u checks; bounded cache, ACK, prefix, raw WaitCS, late attach, errors and four threaded scenarios; GPU_executed=false\n", atomic_load(&checks));
}
#endif
