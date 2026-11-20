// SPDX-License-Identifier: MIT
// Real Mesa ioctl -> CS planner -> sync provider -> marshaller, CPU ops only.
// The private fixture core injects a proposed exact backend. No IOKit open,
// device runtime, GPU ISA interpreter, driver deployment or GPU work is used.
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ac_darwin_drm.c"

static atomic_uint checks;
#define CHECK(x) do { atomic_fetch_add(&checks, 1); if (!(x)) { \
   fprintf(stderr, "check failed at %d: %s\n", __LINE__, #x); abort(); \
} } while (0)

// Redirect only the separately compiled provider's clock and condition wait.
static atomic_uint_fast64_t clock_ns;
static pthread_mutex_t observer_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t observer_cond = PTHREAD_COND_INITIALIZER;
static bool cond_entered;
int fixture_clock_gettime(clockid_t clock, struct timespec *ts)
{
   if (clock != CLOCK_MONOTONIC) return clock_gettime(clock, ts);
   uint64_t ns = atomic_load(&clock_ns);
   ts->tv_sec = ns / 1000000000ull;
   ts->tv_nsec = ns % 1000000000ull;
   return 0;
}
int fixture_cond_timedwait(pthread_cond_t *cond, pthread_mutex_t *mutex,
                           const struct timespec *deadline)
{
   CHECK(pthread_mutex_lock(&observer_lock) == 0);
   cond_entered = true;
   CHECK(pthread_cond_broadcast(&observer_cond) == 0);
   CHECK(pthread_mutex_unlock(&observer_lock) == 0);
   return pthread_cond_timedwait(cond, mutex, deadline);
}
int acd_kext_open_iokit(struct acd_kext **out)
{
   (void)out;
   CHECK(false); // every setup/submit uses only the explicitly supplied CPU ops
   return -ENOSYS;
}

enum behavior { COMPLETE_ON_BLOCK, KEEP_PENDING, EXPIRE_ON_BLOCK, BLOCKED_CALLBACK };
struct fixture {
   struct acd_core core;
   struct acd_device dev;
   pthread_mutex_t lock;
   pthread_cond_t cond;
   enum behavior behavior;
   uint64_t next_seq, completed[16], required[16];
   unsigned completed_n, required_n, submissions, premature, waits, blocks, closes;
   uint32_t engines[16];
   int wait_error, submit_error;
   uint64_t error_seq;
   bool entered, released;
};

static bool completed(struct fixture *f, uint64_t seq)
{
   if (seq <= 9) return true;
   for (unsigned i = 0; i < f->completed_n; i++)
      if (f->completed[i] == seq) return true;
   return false;
}

static int wait_seq(void *ctx, uint64_t seq, uint64_t ns, bool *busy, uint64_t *retired)
{
   struct fixture *f = ctx;
   CHECK(ns <= 20000000ull);
   CHECK(pthread_mutex_lock(&f->lock) == 0);
   f->waits++;
   if (ns) f->blocks++;
   if (f->behavior == BLOCKED_CALLBACK && !f->released) {
      f->entered = true;
      CHECK(pthread_cond_broadcast(&f->cond) == 0);
      while (!f->released) CHECK(pthread_cond_wait(&f->cond, &f->lock) == 0);
   }
   int error = !f->error_seq || f->error_seq == seq ? f->wait_error : 0;
   if (!error && ns && f->behavior == COMPLETE_ON_BLOCK && !completed(f, seq)) {
      CHECK(f->completed_n < 16);
      f->completed[f->completed_n++] = seq;
   }
   if (ns && f->behavior == EXPIRE_ON_BLOCK)
      atomic_fetch_add(&clock_ns, ACD_CS_DEP_TIMEOUT_NS + 1);
   *retired = 9; // separate earlier work keeps the safe global prefix behind
   *busy = !completed(f, seq);
   CHECK(pthread_mutex_unlock(&f->lock) == 0);
   return error;
}

static int call(void *ctx, uint32_t sel, const uint64_t *sin, uint32_t nsin,
                const void *stin, size_t stinsz, uint64_t *sout, uint32_t *nsout,
                void *stout, size_t *stoutsz)
{
   struct fixture *f = ctx;
   CHECK(sel == ACD_SEL_SUBMIT && !sin && nsin == 0 && !stout && !stoutsz);
   CHECK(stin && stinsz == sizeof(struct n48n_cs_in) + sizeof(struct n48n_cs_ib));
   const struct n48n_cs_in *h = stin;
   const struct n48n_cs_ib *ib = (const void *)((const char *)stin + sizeof(*h));
   CHECK(h->ctx_id == 1 && h->num_ibs == 1 && h->abi == N48N_ABI_VERSION);
   CHECK(sout && nsout && *nsout == 1 && ib->ib_bytes == 4 && !ib->_pad);
   CHECK(pthread_mutex_lock(&f->lock) == 0);
   CHECK(f->submissions < 16);
   f->engines[f->submissions++] = ib->ip_type;
   for (unsigned i = 0; i < f->required_n; i++)
      if (!completed(f, f->required[i])) f->premature++;
   int error = f->submit_error;
   if (!error) sout[0] = f->next_seq++;
   CHECK(pthread_mutex_unlock(&f->lock) == 0);
   return error;
}
static void close_fake(void *ctx) { ((struct fixture *)ctx)->closes++; }

static void initialize(struct fixture *f, bool exact, bool clone)
{
   memset(f, 0, sizeof(*f));
   atomic_store(&clock_ns, 1000000000ull);
   CHECK(pthread_mutex_init(&f->lock, NULL) == 0);
   CHECK(pthread_cond_init(&f->cond, NULL) == 0);
   CHECK(pthread_mutex_init(&f->core.bo_lock, NULL) == 0);
   const struct acd_kext_ops ops = {.call = call, .close = close_fake};
   f->core.kext = acd_kext_create(&ops, f);
   CHECK(f->core.kext);
   const struct acd_sync_backend be = {.wait_seq = wait_seq, .ctx = f, .exact_completion = exact};
   f->core.sync = acd_sync_provider_create(&be);
   CHECK(f->core.sync);
   f->dev.core = &f->core;
   f->dev.sync = clone ? f->core.sync->clone(f->core.sync) : f->core.sync;
   CHECK(f->dev.sync);
   f->next_seq = 20;
   f->behavior = COMPLETE_ON_BLOCK;
}
static void finalize(struct fixture *f)
{
   if (f->dev.sync != f->core.sync) f->dev.sync->finalize(f->dev.sync);
   f->core.sync->finalize(f->core.sync);
   acd_kext_destroy(f->core.kext);
   CHECK(f->closes == 1);
   CHECK(pthread_mutex_destroy(&f->core.bo_lock) == 0);
   CHECK(pthread_cond_destroy(&f->cond) == 0);
   CHECK(pthread_mutex_destroy(&f->lock) == 0);
}
static uint32_t create(struct fixture *f)
{
   uint32_t h = 0;
   CHECK(f->core.sync->create(f->core.sync, 0, &h) == 0 && h);
   return h;
}
static bool ready(struct fixture *f, uint32_t h, uint64_t point)
{
   struct util_sync_provider *p = f->core.sync;
   int r = point ? p->timeline_wait(p, &h, &point, 1, 0, 0, NULL)
                 : p->wait(p, &h, 1, 0, 0, NULL);
   CHECK(!r || (r == -1 && errno == ETIME));
   return r == 0;
}
static void check_attached(struct fixture *f, uint32_t h, uint64_t point, bool attached)
{
   struct util_sync_provider *p = f->core.sync;
   uint32_t copy = create(f);
   int r = p->transfer(p, copy, 0, h, point, 0);
   CHECK(attached ? r == 0 : r == -1 && errno == EINVAL);
   CHECK(p->destroy(p, copy) == 0);
}

// Build real DRM chunks; no alternate CS planner or dependency implementation.
static int submit_waits(struct fixture *f, uint32_t engine, const uint32_t *waits,
                        const uint64_t *points, unsigned wait_count, uint32_t signal,
                        uint64_t signal_point, unsigned legacy_chunk,
                        bool nonempty, uint64_t *sequence)
{
   CHECK(wait_count <= 4);
   struct drm_amdgpu_cs_chunk_ib ib = {.va_start = 0x20000, .ib_bytes = 4, .ip_type = engine};
   struct drm_amdgpu_cs_chunk_sem wbin[4], sbin = {.handle = signal};
   struct drm_amdgpu_cs_chunk_syncobj wtl[4];
   struct drm_amdgpu_cs_chunk_syncobj stl = {.handle = signal, .point = signal_point};
   struct drm_amdgpu_cs_chunk_dep dep = {.ip_type = AMDGPU_HW_IP_COMPUTE, .ctx_id = 1, .handle = 20};
   struct drm_amdgpu_cs_chunk chunks[7] = {{.chunk_id = AMDGPU_CHUNK_ID_IB,
      .length_dw = sizeof(ib) / 4, .chunk_data = (uintptr_t)&ib}};
   uint64_t pointers[7] = {(uintptr_t)&chunks[0]};
   unsigned count = 1;
   for (unsigned i = 0; i < wait_count; i++) {
      wbin[i] = (struct drm_amdgpu_cs_chunk_sem){.handle = waits[i]};
      wtl[i] = (struct drm_amdgpu_cs_chunk_syncobj){.handle = waits[i], .point = points[i]};
      chunks[count] = (struct drm_amdgpu_cs_chunk){
         .chunk_id = points[i] ? AMDGPU_CHUNK_ID_SYNCOBJ_TIMELINE_WAIT : AMDGPU_CHUNK_ID_SYNCOBJ_IN,
         .length_dw = (points[i] ? sizeof(wtl[i]) : sizeof(wbin[i])) / 4,
         .chunk_data = points[i] ? (uintptr_t)&wtl[i] : (uintptr_t)&wbin[i]};
      pointers[count] = (uintptr_t)&chunks[count]; count++;
   }
   if (signal) {
      chunks[count] = (struct drm_amdgpu_cs_chunk){
         .chunk_id = signal_point ? AMDGPU_CHUNK_ID_SYNCOBJ_TIMELINE_SIGNAL : AMDGPU_CHUNK_ID_SYNCOBJ_OUT,
         .length_dw = (signal_point ? sizeof(stl) : sizeof(sbin)) / 4,
         .chunk_data = signal_point ? (uintptr_t)&stl : (uintptr_t)&sbin};
      pointers[count] = (uintptr_t)&chunks[count]; count++;
   }
   if (legacy_chunk) {
      chunks[count] = (struct drm_amdgpu_cs_chunk){.chunk_id = legacy_chunk,
         .length_dw = nonempty ? sizeof(dep) / 4 : 0, .chunk_data = (uintptr_t)&dep};
      pointers[count] = (uintptr_t)&chunks[count]; count++;
   }
   union drm_amdgpu_cs cs = {.in = {.ctx_id = 1, .num_chunks = count, .chunks = (uintptr_t)pointers}};
   int r = acd_ioctl(&f->dev, DRM_AMDGPU_CS, &cs, sizeof(cs));
   if (!r && sequence) *sequence = cs.out.handle;
   return r;
}
static int submit(struct fixture *f, uint32_t engine, uint32_t wait, uint64_t point,
                  uint32_t signal, uint64_t signal_point, unsigned legacy_chunk,
                  bool nonempty, uint64_t *sequence)
{
   return submit_waits(f, engine, &wait, &point, wait ? 1 : 0, signal, signal_point,
                       legacy_chunk, nonempty, sequence);
}

static void ordering_case(unsigned index, bool fixed)
{
   struct fixture f;
   initialize(&f, true, index & 4);
   bool timeline = index & 2;
   uint64_t point = timeline ? index + 1 : 0;
   uint32_t producer = create(&f), consumer = create(&f), unrelated = create(&f);
   CHECK(acd_sync_cs_attach(f.core.sync, unrelated, 0, 10) == 0);
   uint32_t producer_engine = index & 1 ? AMDGPU_HW_IP_GFX : AMDGPU_HW_IP_COMPUTE;
   uint32_t consumer_engine = index & 8 ? producer_engine
      : producer_engine == AMDGPU_HW_IP_GFX ? AMDGPU_HW_IP_COMPUTE : AMDGPU_HW_IP_GFX;
   uint64_t seq = 0;
   CHECK(submit(&f, producer_engine, 0, 0, producer, point, 0, false, &seq) == 0 && seq == 20);
   f.required[f.required_n++] = seq;
   CHECK(submit(&f, consumer_engine, producer, point, consumer, point ? point + 100 : 0,
                0, false, &seq) == 0 && seq == 21);
   CHECK(f.submissions == 2 && f.engines[0] == producer_engine && f.engines[1] == consumer_engine);
   CHECK(fixed ? f.premature == 0 && f.blocks == 1 && f.waits >= 2
               : f.premature == 1 && f.blocks == 0 && f.waits == 0);
   f.behavior = KEEP_PENDING;
   CHECK(!ready(&f, unrelated, 0)); // exact completion did not move the safe prefix
   CHECK(!ready(&f, consumer, point ? point + 100 : 0)); // output attached, not falsely signalled
   check_attached(&f, consumer, point ? point + 100 : 0, true);
   CHECK(ready(&f, producer, point) == fixed);
   finalize(&f);
}

static void legacy_chunk_case(unsigned id, bool fixed)
{
   struct fixture f;
   initialize(&f, true, false);
   uint32_t signal = create(&f);
   int r = submit(&f, AMDGPU_HW_IP_GFX, 0, 0, signal, 0, id, true, NULL);
   CHECK(fixed ? r == -EOPNOTSUPP && f.submissions == 0 && f.waits == 0
               : r == 0 && f.submissions == 1);
   f.behavior = KEEP_PENDING;
   CHECK(!ready(&f, signal, 0));
   check_attached(&f, signal, 0, !fixed);
   finalize(&f);
}

#ifdef HAVE_EXACT_CS_GUARD
static void errors_timeout_and_signal_publication(void)
{
   const int errors[] = {-EIO, -ETIME, -ECANCELED, -ENOMEM};
   for (unsigned i = 0; i < 5; i++) {
      struct fixture f;
      initialize(&f, true, false);
      uint32_t dep = create(&f), out = create(&f);
      CHECK(submit(&f, AMDGPU_HW_IP_COMPUTE, 0, 0, dep, 0, 0, false, NULL) == 0);
      if (i < 4) f.wait_error = errors[i];
      else f.behavior = EXPIRE_ON_BLOCK;
      int r = submit(&f, AMDGPU_HW_IP_GFX, dep, 0, out, 0, 0, false, NULL);
      int expected = i == 4 ? -ETIME : errors[i] == -ETIME ? -ECANCELED : errors[i];
      CHECK(r == expected && f.submissions == 1 && !f.premature);
      f.wait_error = 0; f.behavior = KEEP_PENDING;
      CHECK(!ready(&f, out, 0)); // no consumer signal is published after refusal
      check_attached(&f, out, 0, false);
      finalize(&f);
   }
   struct fixture f;
   initialize(&f, true, false);
   uint32_t dep = create(&f), out = create(&f);
   CHECK(submit(&f, AMDGPU_HW_IP_COMPUTE, 0, 0, dep, 0, 0, false, NULL) == 0);
   f.submit_error = ACD_KR_BAD_ARGUMENT;
   CHECK(submit(&f, AMDGPU_HW_IP_GFX, dep, 0, out, 0, 0, false, NULL) == -EINVAL);
   f.behavior = KEEP_PENDING;
   CHECK(f.submissions == 2 && !ready(&f, out, 0));
   check_attached(&f, out, 0, false);
   finalize(&f);
}

static void multiple_dependencies_and_refusal(void)
{
   for (unsigned mode = 0; mode < 6; mode++) {
      struct fixture f;
      initialize(&f, true, mode & 1);
      uint32_t handles[4] = {create(&f), create(&f), create(&f), 0};
      uint64_t points[4] = {0, 3, 0, 0};
      handles[3] = handles[0]; // duplicate across real wait chunks
      for (unsigned i = 0; i < 3; i++) {
         CHECK(submit(&f, i & 1 ? AMDGPU_HW_IP_GFX : AMDGPU_HW_IP_COMPUTE,
                      0, 0, handles[i], points[i], 0, false, NULL) == 0);
      }
      for (unsigned i = 0; i < 3; i++) f.required[f.required_n++] = 20 + i;
      uint32_t out = create(&f);
      unsigned legacy = 0;
      if (mode == 1) {
         // The higher point's exact completion also satisfies requested point 3.
         CHECK(acd_sync_cs_attach(f.core.sync, handles[1], 8, 30) == 0);
         f.completed[f.completed_n++] = 30;
         f.required[1] = 30;
      } else if (mode == 2) {
         f.wait_error = -EIO; f.error_seq = 21;
      } else if (mode == 3) {
         f.completed[f.completed_n++] = 20; // first wait passes; second expires
         f.behavior = EXPIRE_ON_BLOCK;
      } else if (mode >= 4) {
         legacy = mode == 4 ? AMDGPU_CHUNK_ID_DEPENDENCIES : AMDGPU_CHUNK_ID_SCHEDULED_DEPENDENCIES;
      }
      int r = submit_waits(&f, AMDGPU_HW_IP_GFX, handles, points, 4, out, 10,
                           legacy, true, NULL);
      if (mode < 2) {
         CHECK(r == 0 && f.submissions == 4 && f.premature == 0);
         CHECK(f.blocks == (mode ? 2 : 3));
      } else {
         CHECK(r == (mode == 2 ? -EIO : mode == 3 ? -ETIME : -EOPNOTSUPP));
         CHECK(f.submissions == 3 && f.premature == 0);
         if (mode == 2 || mode == 3) CHECK(completed(&f, 20) && !completed(&f, 21));
         if (mode >= 4) CHECK(f.waits == 0 && f.blocks == 0);
      }
      f.wait_error = 0; f.behavior = KEEP_PENDING;
      check_attached(&f, out, 10, mode < 2);
      CHECK(!ready(&f, out, 10));
      finalize(&f);
   }
}

static void direct_budget_timeline_and_legacy(void)
{
   struct fixture f;
   initialize(&f, true, false);
   CHECK(acd_sync_has_exact_completion(f.core.sync));
   CHECK(acd_sync_has_exact_completion(f.dev.sync));
   uint32_t h = create(&f), unrelated = create(&f);
   CHECK(acd_sync_cs_attach(f.core.sync, h, 3, 20) == 0);
   CHECK(acd_sync_cs_attach(f.core.sync, h, 8, 30) == 0);
   CHECK(acd_sync_cs_attach(f.core.sync, unrelated, 0, 10) == 0);
   f.completed[f.completed_n++] = 30;
   CHECK(acd_sync_cs_wait_ready(f.core.sync, h, 3, 0) == 0);
   CHECK(!ready(&f, unrelated, 0));
   CHECK(acd_sync_cs_wait_ready(f.core.sync, 0, 0, 0) == -EINVAL);
   uint32_t pending = create(&f);
   CHECK(acd_sync_cs_attach(f.core.sync, pending, 0, 40) == 0);
   CHECK(acd_sync_cs_wait_ready(f.core.sync, pending, 0, 0) == -ETIME);
   unsigned blocks = f.blocks;
   CHECK(acd_sync_cs_wait_ready(f.core.sync, pending, 0, UINT64_MAX) == 0);
   CHECK(f.blocks == blocks + 1); // no wrap and no accidental expired budget
   uint32_t empty = create(&f);
   CHECK(acd_sync_cs_wait_ready(f.core.sync, empty, 0, 0) == -ETIME);
   CHECK(f.core.sync->signal(f.core.sync, &empty, 1) == 0);
   CHECK(acd_sync_cs_wait_ready(f.core.sync, empty, 0, 0) == 0);
   atomic_store(&clock_ns, (uint64_t)INT64_MAX - 1);
   CHECK(acd_sync_cs_wait_ready(f.core.sync, unrelated, 0, UINT64_MAX) == -ETIME);
   CHECK(f.blocks == blocks + 1); // saturation cannot turn into infinity
   finalize(&f);

   initialize(&f, false, true);
   CHECK(!acd_sync_has_exact_completion(f.core.sync) && !acd_sync_has_exact_completion(f.dev.sync));
   h = create(&f); CHECK(acd_sync_cs_attach(f.core.sync, h, 0, 20) == 0);
   f.behavior = KEEP_PENDING;
   CHECK(acd_sync_cs_wait_ready(f.core.sync, h, 0, 0) == 0 && f.waits == 0);
   CHECK(submit(&f, AMDGPU_HW_IP_GFX, h, 0, 0, 0, AMDGPU_CHUNK_ID_DEPENDENCIES, true, NULL) == 0);
   CHECK(f.submissions == 1 && f.waits == 0); // legacy call shape preserved
   finalize(&f);

   for (unsigned i = 0; i < 2; i++) {
      initialize(&f, true, false);
      CHECK(submit(&f, AMDGPU_HW_IP_GFX, 0, 0, 0, 0,
                   i ? AMDGPU_CHUNK_ID_SCHEDULED_DEPENDENCIES : AMDGPU_CHUNK_ID_DEPENDENCIES,
                   false, NULL) == 0 && f.submissions == 1);
      finalize(&f); // empty legacy chunks carry no dependencies
   }
}

struct cs_thread { struct fixture *f; uint32_t h, signal; int result; };
static void *consumer_thread(void *ctx)
{
   struct cs_thread *t = ctx;
   t->result = submit(t->f, AMDGPU_HW_IP_GFX, t->h, 0, t->signal, 0, 0, false, NULL);
   return NULL;
}
static struct timespec watchdog(void)
{
   struct timespec ts;
   CHECK(clock_gettime(CLOCK_REALTIME, &ts) == 0); ts.tv_sec += 5;
   return ts;
}
static void unsubmitted_cpu_signal_and_producer_attach(void)
{
   for (unsigned i = 0; i < 2; i++) {
      struct fixture f;
      initialize(&f, true, true);
      struct cs_thread t = {.f = &f, .h = create(&f), .signal = create(&f)};
      CHECK(pthread_mutex_lock(&observer_lock) == 0); cond_entered = false;
      CHECK(pthread_mutex_unlock(&observer_lock) == 0);
      pthread_t thread;
      CHECK(pthread_create(&thread, NULL, consumer_thread, &t) == 0);
      CHECK(pthread_mutex_lock(&observer_lock) == 0);
      struct timespec ts = watchdog();
      while (!cond_entered) CHECK(pthread_cond_timedwait(&observer_cond, &observer_lock, &ts) == 0);
      CHECK(pthread_mutex_unlock(&observer_lock) == 0);
      if (i) {
         CHECK(submit(&f, AMDGPU_HW_IP_COMPUTE, 0, 0, t.h, 0, 0, false, NULL) == 0);
      } else {
         CHECK(f.core.sync->signal(f.core.sync, &t.h, 1) == 0);
      }
      CHECK(pthread_join(thread, NULL) == 0 && t.result == 0);
      CHECK(f.submissions == (i ? 2 : 1));
      CHECK(f.blocks == (i ? 1 : 0));
      finalize(&f);
   }
}

static void reset_destroy_reuse_during_dependency(void)
{
   for (unsigned mode = 0; mode < 3; mode++) {
      struct fixture f;
      initialize(&f, true, true);
      struct cs_thread t = {.f = &f, .h = create(&f), .signal = create(&f)};
      CHECK(submit(&f, AMDGPU_HW_IP_COMPUTE, 0, 0, t.h, 0, 0, false, NULL) == 0);
      f.behavior = BLOCKED_CALLBACK;
      pthread_t thread;
      CHECK(pthread_create(&thread, NULL, consumer_thread, &t) == 0);
      CHECK(pthread_mutex_lock(&f.lock) == 0);
      struct timespec ts = watchdog();
      while (!f.entered) CHECK(pthread_cond_timedwait(&f.cond, &f.lock, &ts) == 0);
      CHECK(f.submissions == 1);
      CHECK(pthread_mutex_unlock(&f.lock) == 0);
      if (mode == 0) {
         CHECK(f.core.sync->reset(f.core.sync, &t.h, 1) == 0);
         CHECK(acd_sync_cs_attach(f.core.sync, t.h, 0, 21) == 0);
      } else {
         CHECK(f.core.sync->destroy(f.core.sync, t.h) == 0);
         if (mode == 1) {
            CHECK(create(&f) == t.h);
            CHECK(acd_sync_cs_attach(f.core.sync, t.h, 0, 21) == 0);
         }
      }
      CHECK(pthread_mutex_lock(&f.lock) == 0);
      f.completed[f.completed_n++] = 20;
      f.behavior = EXPIRE_ON_BLOCK;
      f.released = true;
      CHECK(pthread_cond_broadcast(&f.cond) == 0);
      CHECK(pthread_mutex_unlock(&f.lock) == 0);
      CHECK(pthread_join(thread, NULL) == 0);
      CHECK(t.result == (mode == 2 ? -EINVAL : -ETIME) && f.submissions == 1);
      f.behavior = KEEP_PENDING;
      CHECK(!ready(&f, t.signal, 0));
      check_attached(&f, t.signal, 0, false);
      finalize(&f);
   }
}
#endif

int main(void)
{
   unsetenv("RADV_DARWIN_TRACE");
#ifdef HAVE_EXACT_CS_GUARD
   for (unsigned i = 0; i < 64; i++) ordering_case(i, true);
   legacy_chunk_case(AMDGPU_CHUNK_ID_DEPENDENCIES, true);
   legacy_chunk_case(AMDGPU_CHUNK_ID_SCHEDULED_DEPENDENCIES, true);
   errors_timeout_and_signal_publication();
   multiple_dependencies_and_refusal();
   direct_budget_timeline_and_legacy();
   unsubmitted_cpu_signal_and_producer_attach();
   reset_destroy_reuse_during_dependency();
   printf("PASS actual Mesa CS dependency guard: %u checks; 64 ordering cases, six multi-dependency cases, errors, budgets, chunk refusal, CPU attach, reset/destroy/reuse; GPU_executed=false\n",
          atomic_load(&checks));
#else
   ordering_case(0, false);
   ordering_case(3, false);
   legacy_chunk_case(AMDGPU_CHUNK_ID_DEPENDENCIES, false);
   legacy_chunk_case(AMDGPU_CHUNK_ID_SCHEDULED_DEPENDENCIES, false);
   printf("PASS 0004-only CS counterexamples: compute/GFX consumers overtake pending dependencies; legacy chunks ignored; GPU_executed=false\n");
#endif
   return 0;
}
