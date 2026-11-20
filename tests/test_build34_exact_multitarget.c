// SPDX-License-Identifier: MIT
// Actual pinned Mesa provider; CPU callbacks only, no device or GPU simulation.
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ac_darwin_drm.h"
#include "drm-uapi/drm.h"
#include "util/u_sync_provider.h"

static atomic_uint checks;
#define CHECK(x) do { atomic_fetch_add(&checks, 1); if (!(x)) { \
   fprintf(stderr, "check failed at %d: %s\n", __LINE__, #x); abort(); \
} } while (0)

// Only the provider object is compiled with -Drealloc=fixture_realloc.
static atomic_int fail_alloc = -1;
static atomic_bool fake_clock;
static atomic_uint_fast64_t fake_now;
static atomic_bool attach_after_unlock;
static atomic_uint cond_waits;
static struct util_sync_provider *gap_provider;
static uint32_t gap_handle;

// Only the provider object redirects these functions. Inject an attach in the
// exact gap after an empty snapshot unlock, then count any unnecessary sleep.
int fixture_mutex_unlock(pthread_mutex_t *mutex)
{
   int r = pthread_mutex_unlock(mutex);
   if (atomic_exchange(&attach_after_unlock, false))
      CHECK(acd_sync_cs_attach(gap_provider, gap_handle, 0, 20) == 0);
   return r;
}

int fixture_cond_timedwait(pthread_cond_t *cond, pthread_mutex_t *mutex,
                           const struct timespec *deadline)
{
   atomic_fetch_add(&cond_waits, 1);
   return pthread_cond_timedwait(cond, mutex, deadline);
}

// Only the provider object redirects clock_gettime; deterministically model
// deadline passage during a callback without wall-clock sleeps or GPU work.
int fixture_clock_gettime(clockid_t clock, struct timespec *ts)
{
   if (clock == CLOCK_MONOTONIC && atomic_load(&fake_clock)) {
      uint64_t ns = atomic_load(&fake_now);
      ts->tv_sec = ns / 1000000000ull;
      ts->tv_nsec = ns % 1000000000ull;
      return 0;
   }
   return clock_gettime(clock, ts);
}

void *fixture_realloc(void *ptr, size_t size)
{
   int n = atomic_load(&fail_alloc);
   if (n >= 0 && atomic_fetch_sub(&fail_alloc, 1) == 0)
      return NULL;
   return realloc(ptr, size);
}

struct call { uint64_t seq, ns; };
struct gate {
   pthread_mutex_t lock;
   pthread_cond_t cond;
   bool entered, released;
};
struct backend {
   struct util_sync_provider *p;
   uint64_t retired, completed[256];
   unsigned completed_count, call_count, block_count;
   struct call calls[4096];
   int error;
   uint64_t error_seq;
   void (*hook)(struct backend *, uint64_t, uint64_t);
   uint32_t handles[128];
   unsigned mode, mutations;
   struct gate *gate;
};

static bool is_complete(struct backend *b, uint64_t seq)
{
   if (seq <= b->retired)
      return true;
   for (unsigned i = 0; i < b->completed_count; i++)
      if (b->completed[i] == seq)
         return true;
   return false;
}

static int wait_seq(void *ctx, uint64_t seq, uint64_t ns, bool *busy, uint64_t *retired)
{
   struct backend *b = ctx;
   CHECK(ns <= 20000000ull && b->call_count < 4096);
   b->calls[b->call_count++] = (struct call){seq, ns};
   if (ns) b->block_count++;
   if (b->hook) b->hook(b, seq, ns);
   if (b->error && (!b->error_seq || b->error_seq == seq))
      return b->error;
   *retired = b->retired;
   *busy = !is_complete(b, seq);
   return 0;
}

static struct util_sync_provider *provider(struct backend *b, bool exact)
{
   memset(b, 0, sizeof(*b));
   b->retired = 9;
   struct acd_sync_backend be = {.wait_seq = wait_seq, .ctx = b};
#ifdef HAVE_EXACT_MULTITARGET
   be.exact_completion = exact;
#else
   (void)exact;
#endif
   b->p = acd_sync_provider_create(&be);
   CHECK(b->p);
   return b->p;
}

static uint32_t attached(struct util_sync_provider *p, uint64_t seq, uint64_t point)
{
   uint32_t h = 0;
   CHECK(p->create(p, 0, &h) == 0 && h);
   CHECK(acd_sync_cs_attach(p, h, point, seq) == 0);
   return h;
}

static bool done(struct util_sync_provider *p, uint32_t h, uint64_t point)
{
   errno = 0;
   int r = point ? p->timeline_wait(p, &h, &point, 1, 0, 0, NULL)
                 : p->wait(p, &h, 1, 0, 0, NULL);
   CHECK(r == 0 || (r == -1 && errno == ETIME));
   return r == 0;
}

static uint64_t mono(void)
{
   struct timespec ts;
   CHECK(clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
   return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}

// Reproduce three distinct gaps with 0003 already applied, then fix them with
// the exact-only path. These are proposed-backend tests, not live-driver bugs.
static void transition_cases(bool expect_fixed)
{
   struct backend b;
   struct util_sync_provider *p = provider(&b, true);
   b.completed[b.completed_count++] = 20;
   uint32_t hs[] = {attached(p, 10, 0), attached(p, 20, 0)};
   uint32_t first = UINT32_MAX;
   int r = p->wait(p, hs, 2, 0, 0, &first);
   CHECK(expect_fixed ? r == 0 && first == 1 : r == -1 && errno == ETIME);
   CHECK(!done(p, hs[0], 0));
   p->finalize(p);

   p = provider(&b, true);
   b.completed[b.completed_count++] = 20;
   hs[0] = attached(p, 20, 11);
   hs[1] = attached(p, 30, 17);
   uint64_t values[] = {999, 999};
   CHECK(p->query(p, hs, values, 2, 0) == 0);
   CHECK(values[0] == (expect_fixed ? 11 : 0) && values[1] == 0);
   p->finalize(p);

   p = provider(&b, true);
   b.completed[b.completed_count++] = 20;
   uint32_t h = attached(p, 10, 3);
   CHECK(acd_sync_cs_attach(p, h, 8, 20) == 0);
   CHECK(done(p, h, 3) == expect_fixed);
   p->finalize(p);
}

#ifdef HAVE_EXACT_MULTITARGET
static void gaps_permutations_and_aliases(void)
{
   for (unsigned i = 0; i < 128; i++) {
      struct backend b;
      struct util_sync_provider *p = provider(&b, true);
      uint64_t lo = i < 64 ? 10 + 2 * i : UINT64_MAX - 512 + 2 * i;
      uint64_t hi = lo + 1;
      b.completed[b.completed_count++] = hi;
      uint32_t a = attached(p, lo, 0), z = attached(p, hi, 0);
      uint32_t hs[] = {i & 1 ? z : a, i & 1 ? a : z};
      uint32_t first = UINT32_MAX;
      CHECK(p->wait(p, hs, 2, i & 2 ? -1 : 0, 0, &first) == 0);
      CHECK(first == (i & 1 ? 0 : 1));
      CHECK(b.call_count == 2 && b.block_count == 0);
      CHECK(!done(p, a, 0) && done(p, z, 0));
      CHECK(p->wait(p, hs, 2, 0, DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL, NULL) == -1 && errno == ETIME);
      b.retired = hi;
      CHECK(p->wait(p, hs, 2, 0, DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL, NULL) == 0);
      p->finalize(p);
   }
   struct backend b;
   struct util_sync_provider *p = provider(&b, true);
   b.completed[b.completed_count++] = 20;
   uint32_t hs[24];
   uint64_t points[24];
   for (unsigned i = 0; i < 24; i++) {
      points[i] = i & 1 ? i : 0;
      hs[i] = attached(p, 20, points[i]);
   }
   struct util_sync_provider *clone = p->clone(p);
   CHECK(clone);
   CHECK(clone->timeline_wait(clone, hs, points, 24, 0, DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL, NULL) == 0);
   CHECK(b.call_count == 1 && b.block_count == 0); // unique-sequence dedup
   for (unsigned i = 0; i < 24; i++) CHECK(done(p, hs[i], points[i]));
   clone->finalize(clone);
   p->finalize(p);
}

static void query_and_timeline_cases(void)
{
   struct backend b;
   struct util_sync_provider *p = provider(&b, true);
   b.completed[b.completed_count++] = 20;
   b.completed[b.completed_count++] = 40;
   uint32_t h = attached(p, 10, 100);
   CHECK(acd_sync_cs_attach(p, h, 11, 20) == 0);
   CHECK(acd_sync_cs_attach(p, h, 21, 40) == 0);
   uint32_t pending = attached(p, 30, 13);
   uint32_t unrelated = attached(p, 10, 0);
   uint32_t hs[] = {pending, h, h};
   uint64_t values[3];
   CHECK(p->query(p, hs, values, 3, 0) == 0);
   CHECK(values[0] == 0 && values[1] == 21 && values[2] == 21);
   CHECK(b.call_count == 4 && !b.block_count);
   CHECK(!done(p, h, 100) && !done(p, unrelated, 0));
   CHECK(done(p, h, 11) && done(p, h, 21));
   uint32_t transfer = 0;
   CHECK(p->create(p, 0, &transfer) == 0);
   CHECK(p->transfer(p, transfer, 50, h, 21, 0) == 0);
   CHECK(done(p, transfer, 50));
   p->finalize(p);

   // A completed higher point needs no extra backend work on the lower point.
   p = provider(&b, true);
   h = attached(p, 10, 3);
   CHECK(acd_sync_cs_attach(p, h, 8, 20) == 0);
   b.completed[b.completed_count++] = 20;
   CHECK(done(p, h, 3));
   unsigned calls = b.call_count;
   CHECK(done(p, h, 8) && b.call_count == calls);
   p->finalize(p);
}

static void blocking_hook(struct backend *b, uint64_t seq, uint64_t ns)
{
   (void)seq;
   if (!ns) return;
   if (b->mode == 1 || b->mode == 2) {
      // Advance the provider clock beyond its deadline during the first wait.
      atomic_fetch_add(&fake_now, 2000000ull);
      if (b->mode == 1) b->completed[b->completed_count++] = 20;
   } else if (b->block_count == 4) {
      b->completed[b->completed_count++] = 10;
      b->completed[b->completed_count++] = 20;
      b->completed[b->completed_count++] = 30;
   }
}

static void deadlines_rotation_and_final_poll(void)
{
   for (unsigned mode = 0; mode < 3; mode++) {
      struct backend b;
      struct util_sync_provider *p = provider(&b, true);
      b.mode = mode;
      b.hook = blocking_hook;
      atomic_store(&fake_now, 1000000ull);
      atomic_store(&fake_clock, true);
      uint32_t hs[] = {attached(p, 10, 0), attached(p, 20, 0), attached(p, 30, 0)};
      int r = p->wait(p, hs, 3, mode ? 2000000 : INT64_MAX,
                      mode ? 0 : DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL, NULL);
      atomic_store(&fake_clock, false);
      CHECK(mode == 2 ? r == -1 && errno == ETIME : r == 0);
      CHECK(b.block_count == (mode ? 1 : 4));
      unsigned blocks = 0;
      for (unsigned i = 0; i < b.call_count; i++) {
         if (!b.calls[i].ns) continue;
         CHECK(b.calls[i].seq == (blocks % 3 + 1) * 10);
         CHECK(b.calls[i].ns <= (mode ? 1000000ull : 20000000ull));
         blocks++;
      }
      CHECK(blocks == b.block_count);
      CHECK(b.calls[b.call_count - 1].ns == 0); // recheck/sweep after a wait
      p->finalize(p);
   }
}

static void mutation_hook(struct backend *b, uint64_t seq, uint64_t ns)
{
   (void)seq;
   CHECK(ns == 0);
   if (b->mode == 3) {
      // Appends cannot enlarge the current finite snapshot or starve timeout0.
      CHECK(acd_sync_cs_attach(b->p, b->handles[0], 100 + b->mutations,
                               40 + b->mutations) == 0);
      b->mutations++;
      return;
   }
   if (b->mutations++) return;
   if (b->mode == 0) {
      CHECK(b->p->reset(b->p, &b->handles[1], 1) == 0);
      CHECK(acd_sync_cs_attach(b->p, b->handles[1], 0, 21) == 0);
   } else {
      CHECK(b->p->destroy(b->p, b->handles[1]) == 0);
      uint32_t replacement = attached(b->p, 21, b->mode == 2 ? 99 : 0);
      CHECK(replacement == b->handles[1]);
   }
   // Force objs reallocation while the caller owns only sequence snapshots.
   for (unsigned i = 2; i < 64; i++) {
      uint32_t h = 0;
      CHECK(b->p->create(b->p, 0, &h) == 0);
   }
}

static void callback_mutation_and_finite_snapshot(void)
{
   for (unsigned mode = 0; mode < 3; mode++) {
      struct backend b;
      struct util_sync_provider *p = provider(&b, true);
      b.mode = mode;
      b.handles[0] = attached(p, 10, mode == 2 ? 7 : 0);
      b.handles[1] = attached(p, 20, mode == 2 ? 11 : 0);
      uint32_t alias = attached(p, 20, 0);
      b.completed[b.completed_count++] = 20;
      b.hook = mutation_hook;
      if (mode == 2) {
         uint64_t points[2] = {999, 999};
         CHECK(p->query(p, b.handles, points, 2, 0) == 0);
         CHECK(points[0] == 0 && points[1] == 0);
      } else {
         CHECK(p->wait(p, b.handles, 2, 0, 0, NULL) == -1 && errno == ETIME);
      }
      b.hook = NULL;
      CHECK(done(p, alias, 0));
      CHECK(!done(p, b.handles[1], mode == 2 ? 99 : 0));
      p->finalize(p);
   }
   for (unsigned query = 0; query < 2; query++) {
      struct backend b;
      struct util_sync_provider *p = provider(&b, true);
      b.mode = 3;
      b.handles[0] = attached(p, 10, 1);
      CHECK(acd_sync_cs_attach(p, b.handles[0], 2, 20) == 0);
      CHECK(acd_sync_cs_attach(p, b.handles[0], 3, 30) == 0);
      b.hook = mutation_hook;
      uint64_t point = query ? 999 : 1;
      int r = query ? p->query(p, b.handles, &point, 1, 0)
                    : p->timeline_wait(p, b.handles, &point, 1, 0, 0, NULL);
      CHECK(query ? r == 0 && point == 0 : r == -1 && errno == ETIME);
      CHECK(b.call_count == 3 && b.mutations == 3 && !b.block_count);
      p->finalize(p);
   }
}

static void gated_hook(struct backend *b, uint64_t seq, uint64_t ns)
{
   CHECK(ns == 0);
   if (seq != 10) return;
   struct gate *g = b->gate;
   CHECK(pthread_mutex_lock(&g->lock) == 0);
   g->entered = true;
   CHECK(pthread_cond_broadcast(&g->cond) == 0);
   while (!g->released) CHECK(pthread_cond_wait(&g->cond, &g->lock) == 0);
   CHECK(pthread_mutex_unlock(&g->lock) == 0);
}

struct set_waiter {
   struct util_sync_provider *p;
   uint32_t handles[2];
   uint64_t values[2];
   bool query;
   int result, error;
};
static void *set_wait(void *ctx)
{
   struct set_waiter *w = ctx;
   errno = 0;
   w->result = w->query ? w->p->query(w->p, w->handles, w->values, 2, 0)
                         : w->p->wait(w->p, w->handles, 2, 0, 0, NULL);
   w->error = errno;
   return NULL;
}

static void concurrent_callback_races(void)
{
   for (unsigned query = 0; query < 2; query++) {
      for (unsigned mode = 0; mode < 3; mode++) {
         struct backend b;
         struct util_sync_provider *p = provider(&b, true);
         struct gate g = {0};
         CHECK(pthread_mutex_init(&g.lock, NULL) == 0);
         CHECK(pthread_cond_init(&g.cond, NULL) == 0);
         struct set_waiter w = {.p = p, .query = query};
         w.handles[0] = attached(p, 10, query ? 7 : 0);
         w.handles[1] = attached(p, 20, query ? 11 : 0);
         uint32_t alias = attached(p, 20, 0);
         b.completed[b.completed_count++] = 20;
         b.gate = &g;
         b.hook = gated_hook;
         pthread_t thread;
         CHECK(pthread_create(&thread, NULL, set_wait, &w) == 0);
         CHECK(pthread_mutex_lock(&g.lock) == 0);
         struct timespec deadline;
         CHECK(clock_gettime(CLOCK_REALTIME, &deadline) == 0);
         deadline.tv_sec += 5;
         while (!g.entered)
            CHECK(pthread_cond_timedwait(&g.cond, &g.lock, &deadline) == 0);
         CHECK(pthread_mutex_unlock(&g.lock) == 0);
         // The real waiting thread is paused outside mtx in a backend callback.
         if (!mode && !query) {
            CHECK(p->reset(p, &w.handles[1], 1) == 0);
            CHECK(acd_sync_cs_attach(p, w.handles[1], 0, 21) == 0);
         } else {
            CHECK(p->destroy(p, w.handles[1]) == 0);
            if (mode != 2) CHECK(attached(p, 21, query ? 99 : 0) == w.handles[1]);
         }
         if (mode != 2) {
            for (unsigned i = 0; i < 48; i++) {
               uint32_t h;
               CHECK(p->create(p, 0, &h) == 0);
            }
         }
         CHECK(pthread_mutex_lock(&g.lock) == 0);
         g.released = true;
         CHECK(pthread_cond_broadcast(&g.cond) == 0);
         CHECK(pthread_mutex_unlock(&g.lock) == 0);
         CHECK(pthread_join(thread, NULL) == 0);
         b.hook = NULL;
         if (mode == 2) {
            CHECK(w.result == -1 && w.error == EINVAL);
         } else if (query) {
            CHECK(w.result == 0 && w.values[0] == 0 && w.values[1] == 0);
         } else {
            CHECK(w.result == -1 && w.error == ETIME);
            CHECK(!done(p, w.handles[1], 0));
         }
         CHECK(done(p, alias, 0));
         CHECK(pthread_cond_destroy(&g.cond) == 0);
         CHECK(pthread_mutex_destroy(&g.lock) == 0);
         p->finalize(p);
      }
   }
}

struct waiter { struct util_sync_provider *p; uint32_t h; atomic_bool started; int result; };
static void *cpu_waiter(void *ctx)
{
   struct waiter *w = ctx;
   atomic_store(&w->started, true);
   w->result = w->p->wait(w->p, &w->h, 1, mono() + 1000000000ull, 0, NULL);
   return NULL;
}

static void cpu_signal_attach_and_no_backend(void)
{
   // A submit between the empty snapshot and the sleep decision must trigger
   // a new poll immediately, rather than miss its already-delivered wakeup.
   struct backend gap;
   struct util_sync_provider *gp = provider(&gap, true);
   CHECK(gp->create(gp, 0, &gap_handle) == 0);
   gap.completed[gap.completed_count++] = 20;
   gap_provider = gp;
   atomic_store(&cond_waits, 0);
   atomic_store(&attach_after_unlock, true);
   CHECK(gp->wait(gp, &gap_handle, 1, INT64_MAX, 0, NULL) == 0);
   CHECK(gap.call_count == 1 && !gap.block_count && atomic_load(&cond_waits) == 0);
   gap_provider = NULL;
   gp->finalize(gp);

   for (unsigned i = 0; i < 32; i++) {
      struct backend b;
      struct util_sync_provider *p = provider(&b, true);
      uint32_t h = 0;
      CHECK(p->create(p, 0, &h) == 0);
      CHECK(!done(p, h, 0) && b.call_count == 0);
      struct waiter w = {.p = p, .h = h};
      pthread_t thread;
      CHECK(pthread_create(&thread, NULL, cpu_waiter, &w) == 0);
      while (!atomic_load(&w.started)) sched_yield();
      if (i & 1) {
         b.completed[b.completed_count++] = 20;
         CHECK(acd_sync_cs_attach(p, h, 0, 20) == 0);
      } else {
         CHECK(p->signal(p, &h, 1) == 0);
      }
      CHECK(pthread_join(thread, NULL) == 0 && w.result == 0);
      p->finalize(p);
   }
   const struct acd_sync_backend be = {.exact_completion = true};
   struct util_sync_provider *p = acd_sync_provider_create(&be);
   CHECK(p);
   uint32_t h = attached(p, 10, 0);
   CHECK(!done(p, h, 0));
   CHECK(p->signal(p, &h, 1) == 0 && done(p, h, 0));
   p->finalize(p);
}

static void errors_validation_and_allocation(void)
{
   struct backend b;
   struct util_sync_provider *p = provider(&b, true);
   uint32_t hs[] = {attached(p, 10, 0), attached(p, 20, 0)};
   b.error = -ETIME;
   CHECK(p->wait(p, hs, 2, 0, 0, NULL) == -1 && errno == ECANCELED);
   b.error = -EIO;
   CHECK(p->wait(p, hs, 2, 0, 0, NULL) == -1 && errno == EIO);
   b.error = 0;
   uint32_t first = 999;
   uint32_t invalid[] = {hs[0], 0};
   CHECK(p->wait(p, invalid, 2, 0, 0, &first) == -1 && errno == EINVAL && first == 999);
   CHECK(p->wait(p, NULL, 0, 0, DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL, &first) == 0 && first == 0);
   CHECK(p->wait(p, NULL, 0, 0, 0, NULL) == -1 && errno == ETIME);
   // Wait-any returns as soon as one target is done; an unrelated error is not polled.
   b.completed[b.completed_count++] = 10;
   b.error = -EIO;
   b.error_seq = 20;
   CHECK(p->wait(p, hs, 2, 0, 0, &first) == 0 && first == 0);
   p->finalize(p);

   p = provider(&b, true);
   hs[0] = attached(p, 10, 7);
   uint64_t value = 123;
   b.error = -ETIME;
   CHECK(p->query(p, hs, &value, 1, 0) == -1 && errno == ECANCELED && value == 123);
   b.error = -EIO;
   CHECK(p->query(p, hs, &value, 1, 0) == -1 && errno == EIO);
   b.error = 0;
   unsigned calls = b.call_count;
   CHECK(p->query(p, invalid + 1, &value, 1, 0) == -1 && errno == EINVAL && b.call_count == calls);
   p->finalize(p);

   for (unsigned query = 0; query < 2; query++) {
      for (int fail = 0; fail < 2; fail++) {
         p = provider(&b, true);
         uint32_t h = attached(p, 10, 1);
         for (unsigned i = 1; i < 24; i++) CHECK(acd_sync_cs_attach(p, h, i + 1, i + 10) == 0);
         atomic_store(&fail_alloc, fail);
         value = 1;
         int r = query ? p->query(p, &h, &value, 1, 0)
                       : p->timeline_wait(p, &h, &value, 1, 0, 0, NULL);
         CHECK(r == -1 && errno == ENOMEM && b.call_count == 0);
         atomic_store(&fail_alloc, -1);
         CHECK(!done(p, h, 1)); // allocator failure leaves pending payloads intact
         CHECK(b.call_count == 24);
         p->finalize(p);
      }
   }
}

static void legacy_default_compatibility(void)
{
   struct backend b;
   struct util_sync_provider *p = provider(&b, false);
   uint32_t hs[] = {attached(p, 20, 0), attached(p, 10, 0)};
   CHECK(p->wait(p, hs, 2, 0, 0, NULL) == -1 && errno == ETIME);
   CHECK(b.call_count == 1 && b.calls[0].seq == 10 && b.calls[0].ns == 0);
   b.retired = 20;
   CHECK(p->wait(p, hs, 2, 0, DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL, NULL) == 0);
   CHECK(b.call_count == 2 && b.calls[1].seq == 10);
   p->finalize(p);
   p = provider(&b, false);
   hs[0] = attached(p, 20, 11);
   hs[1] = attached(p, 30, 17);
   uint64_t points[2];
   b.retired = 20;
   CHECK(p->query(p, hs, points, 2, 0) == 0 && points[0] == 11 && points[1] == 0);
   CHECK(b.call_count == 1 && b.calls[0].seq == 30);
   p->finalize(p);
}
#endif

int main(void)
{
#ifdef HAVE_EXACT_MULTITARGET
   transition_cases(true);
   gaps_permutations_and_aliases();
   query_and_timeline_cases();
   deadlines_rotation_and_final_poll();
   callback_mutation_and_finite_snapshot();
   concurrent_callback_races();
   cpu_signal_attach_and_no_backend();
   errors_validation_and_allocation();
   legacy_default_compatibility();
   printf("PASS actual Mesa exact multitarget: %u checks; 128 gaps, wait-any/all, query, deadlines, rotation, mutation, allocation, legacy; GPU_executed=false\n",
          atomic_load(&checks));
#else
   (void)mono;
   transition_cases(false);
   printf("PASS 0003-only counterexamples: wait-any, multi-query, higher-timeline; GPU_executed=false\n");
#endif
   return 0;
}
