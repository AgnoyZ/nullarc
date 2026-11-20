// SPDX-License-Identifier: MIT
// Bounded build34 test. Only the external exact-image controller runs --run.
#include <atomic>
#include <chrono>
#include <thread>
#include <time.h>
#include "PhxNativeABI.h"
#define main ib_preamble_program
#include "ib_preamble_probe.cpp"
#undef main

namespace {
constexpr unsigned kBursts = 4, kComputePerBurst = 4, kGfxPerBurst = 10;
constexpr uint64_t kGfxFence = 0x2580000ull;
constexpr uint32_t kNop[] = {0xc0061000u, 0, 0, 0, 0, 0, 0, 0};
constexpr uint32_t kGfxIbOffset = 0x1000;
constexpr unsigned kComputeCount = 64;
// Fixed repetition of the already checked dispatch, without shader loops,
// waits, new opcodes or a larger arena. All four submissions reuse immutable
// commands/output until retirement; one burst has one distinct pattern.
constexpr unsigned kDispatchesPerIB = 24;
constexpr unsigned kComputeIbOffset = 0x1000;
constexpr unsigned kComputeIbBytes = kDispatchesPerIB * 320;
constexpr unsigned kComputeOutput = 0x3010;
static_assert(kComputeIbOffset + kComputeIbBytes <= 0x3000 &&
              kComputeOutput + 1024 < bytes, "commands/output remain inside the guarded arena");
constexpr unsigned kMaxExitWait = 4; // Each call is capped by WAITSEQ at 2 s.
using Clock = std::chrono::steady_clock;

struct Request { phxn_cs_in header{}; phxn_cs_ib ib[PHXN_MAX_IBS]{}; };
static Request request(const Session &s, bool gfx, unsigned count, unsigned offset, unsigned length) {
    Request r;
    r.header.abi = PHXN_ABI_VERSION;
    r.header.ctx_id = s.context;
    r.header.num_ibs = count;
    for (unsigned i = 0; i < count; ++i) {
        r.ib[i].va_start = s.gpuVA + offset;
        r.ib[i].ib_bytes = length;
        r.ib[i].ip_type = gfx ? PHX_AMDGPU_HW_IP_GFX : PHX_AMDGPU_HW_IP_COMPUTE;
    }
    return r;
}
static uint64_t wall() {
    struct timespec t{};
    if (clock_gettime(CLOCK_REALTIME, &t) != 0 || t.tv_sec <= 0 || t.tv_nsec < 0) return 0;
    return uint64_t(t.tv_sec) * 1000000000ull + uint64_t(t.tv_nsec);
}
static bool openSession(Session &s, io_service_t service) {
    if (IOServiceOpen(service, mach_task_self(), PHXN_UC_TYPE, &s.connection) != KERN_SUCCESS || !s.connection)
        return false;
    if (exercise(s, false, false, PreamblePolicy::Single, false, TargetPolicy::Off)) return false;
    phxn_info inf{};
    if (!call(s.connection, PHXN_SEL_QUERYINFO, nullptr, 0, nullptr, 0, nullptr, 0, &inf, sizeof(inf))) return false;
    if (inf.va_low_first != 0x10000 || inf.va_low_last < inf.va_low_first + bytes - 1) return false;
    s.gpuVA = inf.va_low_first;
    phxn_ctx in{PHX_AMDGPU_CTX_OP_ALLOC_CTX, 0, 0, 0}, out{};
    if (!call(s.connection, PHXN_SEL_CTX, nullptr, 0, &in, sizeof(in), nullptr, 0, &out, sizeof(out)) ||
        !out.op || out.op > PHXN_MAX_CTX || out.flags || out.ctx_id || out.priority) return false;
    s.context = out.op;
    const phxn_gem_create_in create{bytes, 4096, PHX_AMDGPU_GEM_DOMAIN_GTT, PHX_AMDGPU_GEM_CREATE_CPU_ACCESS_REQUIRED};
    uint64_t bo[4]{};
    if (!call(s.connection, PHXN_SEL_BOCREATE, nullptr, 0, &create, sizeof(create), bo, 4, nullptr, 0) ||
        !bo[0] || bo[0] >= PHXN_MAX_BOS || bo[1] != bytes || bo[2] != PHX_AMDGPU_GEM_DOMAIN_GTT ||
        !(bo[3] & PHXN_PLACED_ZEROED)) return false;
    s.handle = static_cast<uint32_t>(bo[0]);
    if (IOConnectMapMemory64(s.connection, s.handle, mach_task_self(), &s.cpu, &s.cpuBytes, kIOMapAnywhere) != KERN_SUCCESS)
        return false;
    s.cpuMapped = true;
    if (!s.cpu || (s.cpu & 4095) || s.cpuBytes != bytes || s.cpu > UINTPTR_MAX - bytes) return false;
    phxn_gem_va map{};
    map.handle = s.handle;
    map.operation = PHX_AMDGPU_VA_OP_MAP;
    map.flags = PHX_AMDGPU_VM_PAGE_EXECUTABLE;
    map.va_address = s.gpuVA;
    map.map_size = bytes;
    return call(s.connection, PHXN_SEL_GEMVA, nullptr, 0, &map, sizeof(map), nullptr, 0, nullptr, 0);
}
static bool dispatch(const Session &s, const Request &r, uint64_t &seq) {
    seq = 0;
    const size_t length = sizeof(r.header) + r.header.num_ibs * sizeof(r.ib[0]);
    return call(s.connection, PHXN_SEL_SUBMIT, nullptr, 0, &r, length, &seq, 1, nullptr, 0) && seq && seq < PHXN_SEQ_LAST;
}
static bool retired(const Session &s, uint64_t seq) {
    const uint64_t in[] = {seq, PHXN_WAIT_CAP_NS, 0};
    for (unsigned i = 0; i < kMaxExitWait; ++i) {
        uint64_t out[3]{};
        if (!call(s.connection, PHXN_SEL_WAITSEQ, in, 3, nullptr, 0, out, 3, nullptr, 0) ||
            out[0] > 1 || out[1] == PHXN_SEQ_LAST || out[2] != seq) return false;
        if (out[0] == 0) return out[1] >= seq;
    }
    return false;
}
static bool readGfxFence(const Session &s, uint64_t &seq) {
    // Read the high dword twice through one existing, read-only selector.
    const uint64_t in[] = {kGfxFence, 2};
    uint32_t first[2]{}, last[2]{};
    if (!call(s.connection, PHXN_SEL_DBG_VRAM_READ, in, 2, nullptr, 0, nullptr, 0, first, sizeof(first)) ||
        !call(s.connection, PHXN_SEL_DBG_VRAM_READ, in, 2, nullptr, 0, nullptr, 0, last, sizeof(last))) return false;
    if (first[1] != last[1] || first[0] > last[0]) return false;
    seq = uint64_t(last[1]) << 32 | last[0];
    return seq != PHXN_SEQ_LAST;
}
static bool sameBytes(const Session &s, const uint8_t (&expected)[bytes]) {
    __sync_synchronize();
    const auto *actual = reinterpret_cast<const volatile uint8_t *>(s.cpu);
    for (size_t i = 0; i < bytes; ++i) if (actual[i] != expected[i]) return false;
    return true;
}
static bool prepareCompute(const Session &s, uint8_t (&expected)[bytes], unsigned burst) {
    memset(expected, 0xa5, bytes);
    memset(expected, 0, 0x3000);
    memcpy(expected, phxGfx11ClearShader, sizeof(phxGfx11ClearShader));
    const uint32_t p[] = {0x7800c0deu ^ burst, 0x13579bdfu, 0x2468ace0u ^ (burst << 16), 0xc001d00du ^ burst};
    for (unsigned i = 0; i < kDispatchesPerIB; ++i) {
        uint32_t packet[80]{};
        if (phxGfx11DispatchCommands(packet, 80, s.gpuVA, s.gpuVA + kComputeOutput, p) != PHX_SHADER_DISPATCH_DWORDS) return false;
        packet[78] = packet[79] = 0xffff1000u;
        memcpy(expected + kComputeIbOffset + i * sizeof(packet), packet, sizeof(packet));
    }
    memcpy(reinterpret_cast<void *>(s.cpu), expected, bytes);
    for (unsigned j = 0; j < 256; ++j) memcpy(expected + kComputeOutput + 4 * j, &p[j & 3], 4);
    __sync_synchronize();
    return true;
}
static bool gfxOne(const Session &s, uint64_t &last, unsigned burst, unsigned i) {
    const auto r = request(s, true, 1, kGfxIbOffset, sizeof(kNop));
    uint64_t floor = 0, seq = 0;
    if (!readGfxFence(s, floor)) return false;
    const uint64_t begin = wall();
    if (!begin || !dispatch(s, r, seq) || seq <= floor || seq <= last) return false;
    last = seq;
    const auto limit = Clock::now() + std::chrono::milliseconds(40);
    for (unsigned poll = 0; poll < 128 && Clock::now() < limit; ++poll) {
        uint64_t fence = 0;
        if (!readGfxFence(s, fence)) return false;
        const uint64_t seen = wall();
        if (seen <= begin) return false;
        if (fence >= seq) {
            printf("GFX %u %u %llu %llu %llu %llu %llu\n", burst, i, begin, seen, seq, floor, fence);
            return true;
        }
        std::this_thread::sleep_for(std::chrono::microseconds(70));
    }
    return false;
}
static int run(io_service_t service) {
    // After the first call that could submit, any error retains both connections
    // and every BO for independent recovery. Never destruct an uncertain client.
    Session compute, gfx;
    auto fail = [](const char *where) -> int {
        fprintf(stderr, "HOLD pressure test at %s; retain GPU ownership for recovery\n", where);
        fflush(nullptr);
        for (;;) pause();
    };
    if (!openSession(compute, service) || !openSession(gfx, service)) return fail("client admission");
    uint8_t gfxExpected[bytes];
    memset(gfxExpected, 0xa5, bytes);
    memcpy(gfxExpected + kGfxIbOffset, kNop, sizeof(kNop));
    memcpy(reinterpret_cast<void *>(gfx.cpu), gfxExpected, bytes);
    uint8_t expected[bytes];
    uint64_t cmpLast = 0, gfxLast = 0;
    if (!gfxOne(gfx, gfxLast, 0, 0) || !retired(gfx, gfxLast)) return fail("GFX warmup");
    if (!prepareCompute(compute, expected, 0)) return fail("compute warmup arena");
    // Single IB warmup keeps the driver's first-submit debug logging out of the pressure burst.
    const auto warm = request(compute, false, 1, kComputeIbOffset, kComputeIbBytes);
    if (!dispatch(compute, warm, cmpLast) || !retired(compute, cmpLast)) return fail("compute warmup");
    for (unsigned burst = 1; burst <= kBursts; ++burst) {
        if (!prepareCompute(compute, expected, burst)) return fail("compute arena");
        std::atomic<bool> fourth{false}, done{false};
        bool gfxOk = true, cmpOk = true;
        unsigned gfxN = 0;
        std::thread work([&] {
            for (unsigned i = 0; i < 300 && !fourth.load() && !done.load(); ++i)
                std::this_thread::sleep_for(std::chrono::microseconds(70));
            while (fourth.load() && !done.load() && gfxN < kGfxPerBurst) {
                if (!gfxOne(gfx, gfxLast, burst, ++gfxN)) { gfxOk = false; break; }
                std::this_thread::sleep_for(std::chrono::microseconds(70));
            }
        });
        for (unsigned i = 0; i < kComputePerBurst; ++i) {
            const auto r = request(compute, false, kComputeCount, kComputeIbOffset, kComputeIbBytes);
            if (i == kComputePerBurst - 1) fourth.store(true);
            const uint64_t begin = wall();
            uint64_t seq = 0;
            if (!begin || !dispatch(compute, r, seq) || seq <= cmpLast) { cmpOk = false; break; }
            const uint64_t end = wall();
            if (end <= begin) { cmpOk = false; break; }
            cmpLast = seq;
            printf("CMP %u %u %llu %llu %llu\n", burst, i + 1, begin, end, seq);
        }
        done.store(true);
        work.join();
        if (!gfxOk || !cmpOk) return fail("bounded submissions");
        if (!retired(compute, cmpLast) || !retired(gfx, gfxLast)) return fail("retirement");
        if (!sameBytes(compute, expected) || !sameBytes(gfx, gfxExpected)) return fail("full arena");
        printf("ARENA %u %u %zu\n", burst, gfxN, bytes);
    }
    const int c = finish(compute, 0, true), g = finish(gfx, 0, true);
    if (c || g) return 74;
    puts("DONE pressure probe; both connections closed");
    return 0;
}
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--self-test")) {
        Session s;
        s.gpuVA = 0x10000; s.context = 1;
        const auto r = request(s, false, kComputeCount, kComputeIbOffset, kComputeIbBytes);
        static_assert(kComputeCount == PHXN_MAX_IBS && 3 * (kComputeCount * 4 + 16) <= 1008 &&
                      4 * (kComputeCount * 4 + 16) > 1008, "compute pressure requires a 1024-dword ring");
        for (const auto &ib : r.ib)
            if (ib.va_start != 0x11000 || ib.ib_bytes != kComputeIbBytes || ib.ip_type != PHX_AMDGPU_HW_IP_COMPUTE) return 1;
        alignas(4096) uint8_t mapping[bytes], expected[bytes];
        s.cpu = reinterpret_cast<uintptr_t>(mapping);
        if (!prepareCompute(s, expected, 1) || !memcmp(mapping, expected, bytes) || !wall()) return 1;
        // Every repeated packet is byte-identical, correctly bounded and ends
        // in the same two checked type-2 NOPs. Only output bytes may change.
        for (unsigned i = 0; i < kDispatchesPerIB; ++i)
            if (memcmp(mapping + kComputeIbOffset, mapping + kComputeIbOffset + i * 320, 320)) return 1;
        memcpy(mapping + kComputeOutput, expected + kComputeOutput, 1024);
        if (!sameBytes(s, expected)) return 1;
        mapping[bytes - 1] ^= 1;
        if (sameBytes(s, expected)) return 1;
        puts("PASS ring-pressure CPU packet/arena self-test; no IOKit device opened");
        return 0;
    }
    if (argc != 2 || strcmp(argv[1], "--run") || geteuid() != 0) return 64;
    if (getchar() != 'G') return 64; // The controller starts tracing before opening IOKit.
    setvbuf(stdout, nullptr, _IOLBF, 0);
    io_service_t service = IO_OBJECT_NULL;
    if (const int result = targetService(&service)) return result;
    const int result = run(service);
    IOObjectRelease(service);
    return result;
}
