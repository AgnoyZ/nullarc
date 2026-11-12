// Actual submit-begin body with explicit Vulkan/ownership observations, no GPU.
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef void *VkCommandBuffer; typedef void *VkFence; typedef void *VkQueryPool; typedef int VkResult;
enum { VK_SUCCESS = 0, VK_ERROR_DEVICE_LOST = -4, VK_STRUCTURE_TYPE_FENCE_CREATE_INFO = 1,
       VK_STRUCTURE_TYPE_MEMORY_BARRIER = 2, VK_STRUCTURE_TYPE_SUBMIT_INFO = 3,
       VK_ACCESS_TRANSFER_WRITE_BIT = 1, VK_ACCESS_MEMORY_READ_BIT = 2, VK_ACCESS_MEMORY_WRITE_BIT = 4, VK_ACCESS_HOST_READ_BIT = 8,
       VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT = 1, VK_PIPELINE_STAGE_TRANSFER_BIT = 2, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT = 4, VK_PIPELINE_STAGE_HOST_BIT = 8 };
#ifndef CLOCK_UPTIME_RAW
#define CLOCK_UPTIME_RAW 9
#endif
#define clock_gettime_nsec_np test_clock_now
#define VK_NULL_HANDLE NULL
typedef struct { int type; const void *next; unsigned flags; } VkFenceCreateInfo;
typedef struct { int type; const void *next; unsigned src, dst; } VkMemoryBarrier;
typedef struct { int type; const void *next; unsigned waitCount; const void *wait, *stages; unsigned commandBufferCount; const VkCommandBuffer *pCommandBuffers; unsigned signalCount; const void *signals; } VkSubmitInfo;
typedef struct { int valid; } test_clock;
typedef struct { void *cb; int counter_error, in_rp; void *timing_pool; struct { test_clock clock; uint64_t host_before_ns; } timing; uint32_t wseq; int retired; } nvk_cmdbuf;
typedef struct { nvk_cmdbuf cb; unsigned begun, n, fills, copies, nhold; unsigned long long bytes; void *hold[4]; } nvmtl_prologue;
typedef struct { nvk_cmdbuf *c; VkFence fence; nvmtl_prologue pre; uint64_t pt[8]; } nvmtl_inflight;
static pthread_mutex_t nvmtl_submit_mutex = PTHREAD_MUTEX_INITIALIZER;
static int g_state, g_perf_kind; static void *g_dev, *g_queue;
static unsigned g_cmd_submitted, g_pre_fail; static nvmtl_prologue *g_pre_cur;
static void (*nvmtl_pre_submit_hook)(void); static void (*nvmtl_pre_release_hook)(void *);
static int pro, pre_mode, reset_enabled, flush_error, reset_error, main_error, pre_error, fence_error, queue_error, lose_in_hook, rp_light;
static unsigned submits, fences, destroyed, main_retired, pre_retired, released, barriers, controls, tests;
static VkCommandBuffer submitted[3]; static unsigned submitted_count;
static uint64_t ticks;
static void nvlog(const char *format, ...) { (void)format; }
static void nvmtl_subwho_note(const char *who, int n) { (void)who; (void)n; }
static int nvmtl_counter_flush(nvk_cmdbuf *c) { (void)c; return flush_error; }
static int nvmtl_counter_reset_finish(nvk_cmdbuf *c, VkCommandBuffer *reset) { (void)c; *reset = reset_enabled ? (void *)3 : NULL; return reset_error; }
static void nvmtl_cmd_retire(nvk_cmdbuf *c) {
    assert(!submits); assert(!c->retired);
    if (c->cb == (void *)1) main_retired++; else { assert(c->cb == (void *)2); pre_retired++; }
    c->retired = 1; c->cb = NULL;
}
static test_clock nvmtl_clock_snapshot(void) { return (test_clock){1}; }
static uint64_t clock_gettime_nsec_np(int clock) { (void)clock; return ++ticks; }
static uint64_t nvmtl_perf_now(void) { return ++ticks; }
static int nvmtl_prologue_on(void) { return pro; }
static int nvmtl_rp_light(void) { return rp_light; }
static int nvmtl_keep_on(void) { return 1; }
static uint32_t nvmtl_wit_record(nvk_cmdbuf *c) { (void)c; return 17; }
static void nvmtl_wit_control(uint32_t wseq) { assert(wseq == 17); controls++; }
static VkResult pvkEndCommandBuffer(VkCommandBuffer cb) { return cb == (void *)1 ? main_error : pre_error; }
static VkResult pvkCreateFence(void *dev, const VkFenceCreateInfo *info, void *alloc, VkFence *fence) {
    (void)dev; (void)alloc; assert(info->type == VK_STRUCTURE_TYPE_FENCE_CREATE_INFO);
    if (fence_error) return fence_error; *fence = (void *)4; fences++; return VK_SUCCESS;
}
static void pvkDestroyFence(void *dev, VkFence fence, void *alloc) { (void)dev; (void)alloc; assert(fence == (void *)4 && !submits); destroyed++; }
static void pvkCmdWriteTimestamp(VkCommandBuffer cb, unsigned stage, VkQueryPool pool, unsigned index) { (void)cb; (void)stage; (void)pool; (void)index; }
static void pvkCmdPipelineBarrier(VkCommandBuffer cb, unsigned src, unsigned dst, unsigned flags, unsigned count, const VkMemoryBarrier *mb, unsigned nb, const void *buf, unsigned ni, const void *img) {
    assert(!flags && !nb && !buf && !ni && !img && count == 1);
    if (cb == (void *)1) {
        assert(src == VK_PIPELINE_STAGE_ALL_COMMANDS_BIT && dst == (VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | VK_PIPELINE_STAGE_HOST_BIT));
        assert(mb->src == VK_ACCESS_MEMORY_WRITE_BIT && mb->dst == (VK_ACCESS_HOST_READ_BIT | VK_ACCESS_MEMORY_READ_BIT));
    } else {
        assert(cb == (void *)2 && src == VK_PIPELINE_STAGE_TRANSFER_BIT && dst == VK_PIPELINE_STAGE_ALL_COMMANDS_BIT);
        assert(mb->src == VK_ACCESS_TRANSFER_WRITE_BIT && mb->dst == (VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT));
    }
    barriers++;
}
static VkResult pvkQueueSubmit(void *queue, unsigned n, const VkSubmitInfo *si, VkFence fence) {
    (void)queue; assert(n == 1 && fence == (void *)4); submits++; submitted_count = si->commandBufferCount;
    assert(submitted_count <= 3); memcpy(submitted, si->pCommandBuffers, submitted_count * sizeof *submitted); return queue_error;
}
static void release_hold(void *p) { assert(p == (void *)5); released++; }
static void hook(void) {
    if (lose_in_hook) g_state = -1;
    if (!g_pre_cur || !pre_mode) return;
    g_pre_cur->begun = 1; g_pre_cur->cb.cb = (void *)2; g_pre_cur->n = pre_mode == 2 ? 1 : 0;
    g_pre_cur->nhold = 1; g_pre_cur->hold[0] = (void *)5; g_pre_cur->bytes = 128;
}
#include "submit_begin.inc"
static nvk_cmdbuf c; static nvmtl_inflight f; static nvmtl_prologue outer;
static void setup(void) {
    memset(&c, 0, sizeof c); memset(&f, 0, sizeof f); memset(&outer, 0, sizeof outer);
    c.cb = (void *)1; c.timing_pool = (void *)6; g_state = 1; g_perf_kind = 8; g_pre_cur = &outer;
    pro = rp_light = 1; pre_mode = reset_enabled = flush_error = reset_error = main_error = pre_error = fence_error = queue_error = lose_in_hook = 0;
    submits = fences = destroyed = main_retired = pre_retired = released = barriers = controls = g_cmd_submitted = g_pre_fail = 0; submitted_count = 0;
    nvmtl_pre_submit_hook = hook; nvmtl_pre_release_hook = release_hold;
}
static int run(nvk_cmdbuf *cmd) {
    int r = nvmtl_vk_submit_begin_at(cmd, &f, "host-test"); tests++;
    assert(pthread_mutex_trylock(&nvmtl_submit_mutex) == 0); assert(pthread_mutex_unlock(&nvmtl_submit_mutex) == 0);
    assert(g_pre_cur == &outer && g_perf_kind == 8); return r;
}
int main(void) {
    setup(); g_state = 0; assert(run(&c) == -2 && !main_retired && !submits);
    setup(); g_state = -1; assert(run(&c) == -2 && !main_retired);
    setup(); assert(run(NULL) == -2 && !main_retired);
    setup(); c.cb = NULL; assert(run(&c) == -2 && !main_retired);
    setup(); c.counter_error = 1; assert(run(&c) == -1 && main_retired == 1 && !fences);
    setup(); flush_error = 1; assert(run(&c) == -1 && main_retired == 1 && !fences);
    setup(); reset_error = 1; assert(run(&c) == -1 && main_retired == 1 && !fences);
    setup(); main_error = -1; assert(run(&c) == -1 && main_retired == 1 && !fences);
    setup(); fence_error = -1; assert(run(&c) == -1 && main_retired == 1 && !fences);
    for (int reset = 0; reset < 2; ++reset) {
        for (int mode = 0; mode < 3; ++mode) {
            setup(); reset_enabled = reset; pre_mode = mode;
            assert(run(&c) == 0 && f.fence == (void *)4 && submits == 1 && !main_retired && !destroyed);
            assert(submitted_count == 1u + (unsigned)reset + (mode == 2));
            unsigned idx = 0; if (reset) assert(submitted[idx++] == (void *)3);
            if (mode == 2) assert(submitted[idx++] == (void *)2); assert(submitted[idx] == (void *)1);
            assert(pre_retired == (mode == 1) && released == (mode == 1) && controls == 1);
            assert(barriers == 1u + (mode == 2));
            setup(); reset_enabled = reset; pre_mode = mode; queue_error = VK_ERROR_DEVICE_LOST;
            assert(run(&c) == -2 && g_state == -1 && submits == 1 && !main_retired && !destroyed && !f.fence);
            assert(pre_retired == (mode == 1) && released == (mode == 1));
            setup(); reset_enabled = reset; pre_mode = mode; lose_in_hook = 1;
            assert(run(&c) == -2 && g_state == -1 && !submits && !main_retired && !destroyed);
            assert(pre_retired == (mode == 1) && released == (mode == 1));
        }
        for (int error = 0; error < 2; ++error) {
            setup(); reset_enabled = reset; pre_mode = 2; pre_error = error ? VK_ERROR_DEVICE_LOST : -1;
            assert(run(&c) == (error ? -2 : -1));
            assert(!submits && main_retired == 1 && pre_retired == 1 && released == 1 && fences == 1 && destroyed == 1);
            assert(!f.fence && !f.pre.begun && !f.pre.nhold && !controls && !g_cmd_submitted && g_pre_fail == 1);
            assert(g_state == (error ? -1 : 1));
        }
    }
    setup(); pro = 0; assert(run(&c) == 0 && submits == 1 && submitted_count == 1);
    setup(); nvmtl_pre_submit_hook = NULL; assert(run(&c) == 0 && submits == 1);
    setup(); rp_light = 0; assert(run(&c) == 0 && submits == 1 && !barriers);
    setup(); c.in_rp = 1; assert(run(&c) == 0 && submits == 1 && !barriers);
    assert(tests == 35);
    printf("{\"cases\": %u, \"hardware_executed\": false}\n", tests);
}
