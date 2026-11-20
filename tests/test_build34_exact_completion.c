// SPDX-License-Identifier: MIT
// Execute the pinned Mesa sync provider with CPU-only completion callbacks.
// No IOKit, Vulkan device, kernel submission or GPU ISA simulation is linked.
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ac_darwin_drm.h"
#include "util/u_sync_provider.h"

static atomic_uint checks;
#define CHECK(x) do { atomic_fetch_add(&checks, 1); if (!(x)) { \
   fprintf(stderr, "check failed at %d: %s\n", __LINE__, #x); abort(); \
} } while (0)

struct backend {
   pthread_mutex_t lock;
   pthread_cond_t cond;
   uint64_t retired, exact;
   int error;
   unsigned calls;
   bool hold, entered, released;
};

static int
wait_seq(void *ctx, uint64_t seq, uint64_t rel_ns, bool *busy, uint64_t *retired)
{
   struct backend *b = ctx;
   CHECK(rel_ns <= 20000000ull);
   pthread_mutex_lock(&b->lock);
   ++b->calls;
   if (b->hold && seq == b->exact) {
      b->entered = true;
      pthread_cond_broadcast(&b->cond);
      while (!b->released)
         pthread_cond_wait(&b->cond, &b->lock);
   }
   int error = b->error;
   if (!error) {
      *retired = b->retired;
      *busy = seq > b->retired && seq != b->exact;
   }
   pthread_mutex_unlock(&b->lock);
   return error;
}

static struct util_sync_provider *
provider(struct backend *b, uint64_t retired, uint64_t exact)
{
   memset(b, 0, sizeof(*b));
   CHECK(pthread_mutex_init(&b->lock, NULL) == 0);
   CHECK(pthread_cond_init(&b->cond, NULL) == 0);
   b->retired = retired;
   b->exact = exact;
   const struct acd_sync_backend be = {.wait_seq = wait_seq, .ctx = b};
   struct util_sync_provider *p = acd_sync_provider_create(&be);
   CHECK(p);
   return p;
}

static void
finish(struct util_sync_provider *p, struct backend *b)
{
   p->finalize(p);
   CHECK(pthread_cond_destroy(&b->cond) == 0);
   CHECK(pthread_mutex_destroy(&b->lock) == 0);
}

static uint32_t
attached(struct util_sync_provider *p, uint64_t seq, uint64_t point)
{
   uint32_t h = 0;
   CHECK(p->create(p, 0, &h) == 0 && h);
   CHECK(acd_sync_cs_attach(p, h, point, seq) == 0);
   return h;
}

static bool
done(struct util_sync_provider *p, uint32_t h, uint64_t point)
{
   errno = 0;
   uint32_t first = UINT32_MAX;
   int r = point ? p->timeline_wait(p, &h, &point, 1, 0, 0, &first)
                 : p->wait(p, &h, 1, 0, 0, &first);
   CHECK(r == 0 || (r == -1 && errno == ETIME));
   if (!r) CHECK(first == 0);
   return r == 0;
}

static bool
prefix_counterexample(void)
{
   struct backend b;
   struct util_sync_provider *p = provider(&b, 9, 20);
   uint32_t lower = attached(p, 10, 0), upper = attached(p, 20, 0);
   CHECK(!done(p, lower, 0));
   CHECK(done(p, upper, 0));
   bool false_prefix = done(p, lower, 0);
   finish(p, &b);
   return false_prefix;
}

#ifndef EXPECT_LEGACY_PREFIX
static void
binary_gaps_and_late_attach(void)
{
   for (unsigned i = 0; i < 128; ++i) {
      struct backend b;
      uint64_t lower_seq = 10 + 2 * i, upper_seq = lower_seq + 10;
      struct util_sync_provider *p = provider(&b, lower_seq - 1, upper_seq);
      uint32_t lower = attached(p, lower_seq, 0), upper = attached(p, upper_seq, 0);
      uint32_t later = attached(p, upper_seq + 1, 0);
      CHECK(done(p, upper, 0));
      CHECK(!done(p, lower, 0));
      CHECK(!done(p, later, 0));
      // A late reference can recheck the exact fence without a permanent set.
      uint32_t late = attached(p, upper_seq, 0);
      CHECK(done(p, late, 0));
      CHECK(!done(p, lower, 0));
      CHECK(p->reset(p, &upper, 1) == 0);
      CHECK(!done(p, upper, 0));
      CHECK(p->signal(p, &upper, 1) == 0 && done(p, upper, 0));
      finish(p, &b);
   }
}

static void
timelines_clones_and_transfers(void)
{
   struct backend b;
   struct util_sync_provider *p = provider(&b, 9, 20);
   uint32_t lower = attached(p, 10, 7), upper = attached(p, 20, 11);
   uint32_t mixed = attached(p, 10, 3);
   CHECK(acd_sync_cs_attach(p, mixed, 8, 20) == 0);
   uint32_t transfer = 0;
   CHECK(p->create(p, 0, &transfer) == 0);
   CHECK(p->transfer(p, transfer, 13, upper, 11, 0) == 0);
   uint32_t binary = attached(p, 20, 0);
   struct util_sync_provider *clone = p->clone(p);
   CHECK(clone && done(clone, upper, 11));
   CHECK(done(p, transfer, 13) && done(p, binary, 0));
   CHECK(done(p, mixed, 8) && done(p, mixed, 3)); // one timeline is monotonic
   CHECK(!done(p, lower, 7));                   // unrelated timeline stays pending
   uint64_t value = 0;
   CHECK(p->query(p, &lower, &value, 1, 0) == 0 && value == 0);
   CHECK(p->query(p, &upper, &value, 1, 0) == 0 && value == 11);
   CHECK(!done(p, upper, 12));
   clone->finalize(clone);
   finish(p, &b);
}

static void
global_prefix_and_error_compatibility(void)
{
   struct backend b;
   struct util_sync_provider *p = provider(&b, 20, 0);
   uint32_t lower = attached(p, 10, 0), upper = attached(p, 20, 4);
   uint32_t later = attached(p, 30, 0);
   CHECK(!done(p, later, 0)); // busy response can still advance the safe prefix
   CHECK(done(p, lower, 0) && done(p, upper, 4));
   unsigned calls = b.calls;
   CHECK(done(p, lower, 0) && b.calls == calls);
   CHECK(p->destroy(p, later) == 0);
   later = attached(p, 30, 0);
   b.error = -ETIME;
   errno = 0;
   CHECK(p->wait(p, &later, 1, 0, 0, NULL) == -1 && errno == ECANCELED);
   b.error = -EIO;
   errno = 0;
   CHECK(p->wait(p, &later, 1, 0, 0, NULL) == -1 && errno == EIO);
   b.error = 0;
   CHECK(!done(p, later, 0));
   finish(p, &b);
}

struct waiter { struct util_sync_provider *p; uint32_t handle; bool done; };
static void *
thread_wait(void *ctx)
{
   struct waiter *w = ctx;
   w->done = done(w->p, w->handle, 0);
   return NULL;
}

static void
destroy_reset_reuse_during_callback(void)
{
   for (unsigned reset = 0; reset < 2; ++reset) {
      struct backend b;
      struct util_sync_provider *p = provider(&b, 9, 20);
      uint32_t h = attached(p, 20, 0), alias = attached(p, 20, 0);
      b.hold = true;
      struct waiter w = {p, h, true};
      pthread_t thread;
      CHECK(pthread_create(&thread, NULL, thread_wait, &w) == 0);
      pthread_mutex_lock(&b.lock);
      while (!b.entered) pthread_cond_wait(&b.cond, &b.lock);
      pthread_mutex_unlock(&b.lock);
      if (reset) {
         CHECK(p->reset(p, &h, 1) == 0);
         CHECK(acd_sync_cs_attach(p, h, 0, 21) == 0);
      } else {
         CHECK(p->destroy(p, h) == 0);
         uint32_t replacement = attached(p, 21, 0);
         CHECK(replacement == h);
      }
      pthread_mutex_lock(&b.lock);
      b.released = true;
      pthread_cond_broadcast(&b.cond);
      pthread_mutex_unlock(&b.lock);
      CHECK(pthread_join(thread, NULL) == 0);
      CHECK(!w.done && !done(p, h, 0));
      CHECK(done(p, alias, 0));
      finish(p, &b);
   }
}
#endif

int main(void)
{
#ifdef EXPECT_LEGACY_PREFIX
   CHECK(prefix_counterexample());
   printf("PASS baseline counterexample: exact 20 falsely completes pending 10; GPU_executed=false\n");
#else
   CHECK(!prefix_counterexample());
   binary_gaps_and_late_attach();
   timelines_clones_and_transfers();
   global_prefix_and_error_compatibility();
   destroy_reset_reuse_during_callback();
   printf("PASS actual Mesa exact-completion prerequisite: %u checks; 128 gaps, clones, timelines, transfers, reset/destroy races; GPU_executed=false\n",
          atomic_load(&checks));
#endif
   return 0;
}
