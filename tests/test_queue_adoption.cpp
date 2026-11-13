// Execute staged kernel methods. OS locks, mappings, flushing and PCI property/matching are faked.
#include "PhxGartLayout.h"
#include "PhxHardwarePolicy.hpp"
#include <cassert>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

using IOReturn = int;
enum { kIOReturnSuccess, kIOReturnBadArgument, kIOReturnNotReady, kIOReturnExclusiveAccess };
static unsigned depth = 0, acquisitions = 0;
struct FakeLock { unsigned rank; bool held{false}; };
static void IOLockLock(FakeLock *p) { assert(p && !p->held && p->rank == depth + 1); p->held = true; ++depth; ++acquisitions; }
static void IOLockUnlock(FakeLock *p) { assert(p && p->held && p->rank == depth); p->held = false; --depth; }
static void IOLog(const char *, ...) {}
struct FakeMap {
    std::vector<uint32_t> words;
    uint64_t length;
    unsigned accesses{0};
    explicit FakeMap(size_t bytes) : words(bytes / 4, 0xA5A5A5A5), length(bytes) {}
    uintptr_t getVirtualAddress() { ++accesses; return reinterpret_cast<uintptr_t>(words.data()); }
    uint64_t getLength() const { return length; }
};
static const bool fakeTrue = true;
static const void *kOSBooleanTrue = &fakeTrue;
struct FakePci {
    unsigned properties{0}, registrations{0};
    void setProperty(const char *name, const void *value) {
        assert(!std::strcmp(name, "nmxgpu-claimed") && value == kOSBooleanTrue);
        ++properties;
    }
    void registerService() { assert(properties); ++registrations; }
};
class PhxBringup {
public:
#include "queue-structure.inc"
    GpuQueue gq[2]{};
    FakeMap memory{0x100000}, bells{0x1000};
    FakeMap *fbAper{&memory}, *doorbellMap{&bells};
    void *mmio{reinterpret_cast<void *>(1)};
    FakeLock gpuMutex{1}, smuMutex{2};
    FakeLock *gpuLock{&gpuMutex}, *smuLock{&smuMutex};
    uint64_t fbAperLen{0x100000}, fbSize{0x100000}, fbMcBase{0x100000000ull}, fbPhys{0x200000000ull};
    uint64_t gSeq{0x1122334455667788ull};
    bool pspLayoutConfigured{true}, pspSubmissionFaulted{false}, stopping{false};
    PhxPspLayout pspLayout{PHX_PSP_LAYOUT_VERSION, 0, 0x10000, 0x2000, 0x20000, 0x2000, {0, 0}};
    uint64_t ringMc{0x100000000ull}, tmrSize{0x1000};
    bool tmrSetUp{true};
    FakePci device;
    FakePci *pci{&device};
    unsigned flushes{0}, target{0};
    void hdpFlush() { assert(depth == 2 && !gq[target].ready); ++flushes; }
    IOReturn adoptQueue(const uint64_t in[6]);
    IOReturn claimAccel();
    IOReturn bootMemory(PhxBootMemory *);
#include "queue-readiness-declaration.inc"
};
#include "queue-adoption.inc"
#include "queue-readiness-methods.inc"

static void adopt(PhxBringup &p, bool graphics) {
    uint64_t input[6] = {graphics ? 0x50000ull : 0x40000ull, 1024,
        graphics ? 0x52000ull : 0x42000ull, graphics ? 0x20ull : 0x18ull, 13,
        graphics ? 0x53001ull : 0x43000ull};
    p.target = graphics ? 1 : 0;
    assert(p.adoptQueue(input) == kIOReturnSuccess);
}

static PhxBootMemory snapshotAndClaim(PhxBringup &p, bool ready, IOReturn claim) {
    assert(p.gpuReady() == ready);
    const auto memory = p.memory.words, bells = p.bells.words;
    unsigned char queues[sizeof(p.gq)]; std::memcpy(queues, p.gq, sizeof(p.gq));
    const unsigned accesses = p.memory.accesses, flushes = p.flushes;
    const unsigned properties = p.device.properties, registrations = p.device.registrations;
    PhxBootMemory observation{};
    assert(p.bootMemory(&observation) == kIOReturnSuccess);
    assert(depth == 0 && !p.gpuMutex.held && !p.smuMutex.held);
    assert(observation.flags == (PHX_BOOT_LAYOUT_CONFIGURED | PHX_BOOT_RING_ACTIVE | PHX_BOOT_TMR_ACTIVE |
                                (ready ? PHX_BOOT_GPU_ACTIVE : 0)));
    assert(p.claimAccel() == claim);
    assert(p.device.properties == properties + (claim == kIOReturnSuccess));
    assert(p.device.registrations == registrations + (claim == kIOReturnSuccess));
    assert(p.memory.accesses == accesses && p.flushes == flushes);
    assert(p.memory.words == memory && p.bells.words == bells);
    assert(std::memcmp(queues, p.gq, sizeof(p.gq)) == 0);
    return observation;
}

static void prepareReadinessFixture(PhxBringup &p) {
    // The bootstrap validator additionally requires a 1 MiB-aligned TMR base.
    // Keep the original adoption-only fixtures and their boundary cases unchanged.
    p.memory.words.resize(0x400000 / 4, 0xA5A5A5A5);
    p.memory.length = p.fbAperLen = p.fbSize = 0x400000;
    p.pspLayout.tmrOffset = 0x100000;
}

static void readinessCase(const std::string &test) {
    const PhxGartLayout layout{PHX_GART_LAYOUT_VERSION, 0x4000000000ull, 0x5000, 0x70000, 0x71000};
    PhxBringup p;
    prepareReadinessFixture(p);
    if (test == "readiness-identity-collision") {
        PhxBringup graphics, both;
        prepareReadinessFixture(graphics); prepareReadinessFixture(both);
        adopt(p, false); adopt(graphics, true); adopt(both, false); adopt(both, true);
        const auto computeState = snapshotAndClaim(p, true, kIOReturnSuccess);
        const auto graphicsState = snapshotAndClaim(graphics, true, kIOReturnSuccess);
        const auto bothState = snapshotAndClaim(both, true, kIOReturnSuccess);
        assert(!p.gq[1].ready && !graphics.gq[0].ready && both.gq[0].ready && both.gq[1].ready);
        assert(std::memcmp(&computeState, &graphicsState, sizeof(computeState)) == 0);
        assert(std::memcmp(&computeState, &bothState, sizeof(computeState)) == 0);
        assert(phx780m::queueIndex(true, p.gq[0].ready, p.gq[1].ready) == -1);
        assert(phx780m::queueIndex(false, graphics.gq[0].ready, graphics.gq[1].ready) == -1);
        assert(!phxGartLayoutValid(&layout, &computeState));
        return;
    }
    if (test == "readiness-none") {
        const auto state = snapshotAndClaim(p, false, kIOReturnNotReady);
        assert(phxGartLayoutValid(&layout, &state));
        return;
    }
    if (test == "readiness-zero-submission") p.gSeq = 0;
    if (test == "readiness-graphics-only") adopt(p, true);
    else adopt(p, false);
    if (test == "readiness-both") adopt(p, true);
    if (test == "readiness-stopping-retained") {
        // Inject the stopping predicate, not a model or execution of stop()/teardown/concurrency.
        p.stopping = true;
        const auto stopped = snapshotAndClaim(p, false, kIOReturnNotReady);
        PhxBringup cold;
        prepareReadinessFixture(cold);
        const auto beforeAdoption = snapshotAndClaim(cold, false, kIOReturnNotReady);
        assert(p.gq[0].ready && !cold.gq[0].ready);
        assert(std::memcmp(&stopped, &beforeAdoption, sizeof(stopped)) == 0);
        assert(phxGartLayoutValid(&layout, &stopped)); // Arithmetic metadata is not lifecycle/ownership proof.
        return;
    }
    if (test == "readiness-missing-pci") p.pci = nullptr;
    const auto state = snapshotAndClaim(p, true, p.pci ? kIOReturnSuccess : kIOReturnNotReady);
    assert(!phxGartLayoutValid(&layout, &state)); // Preserve the pre-initialization validator's active-queue refusal.
    if (test == "readiness-zero-submission") {
        assert(p.gSeq == 0 && p.gq[0].head == p.gq[0].tail && p.gq[0].retiredSeq == 0);
        assert(p.memory.words[p.gq[0].fenceOff / 4] == 0 && p.memory.words[p.gq[0].fenceOff / 4 + 1] == 0);
        assert(p.flushes == 1); // Only the fake CPU-side adoption flush; no device completion was supplied.
    } else {
        assert(test == "readiness-compute-only" || test == "readiness-graphics-only" ||
               test == "readiness-both" || test == "readiness-missing-pci");
    }
}

int main(int argc, char **argv) {
    assert(argc == 2);
    const std::string test = argv[1];
    if (test.rfind("readiness-", 0) == 0) {
        readinessCase(test);
        std::cout << "{\"case\":\"" << test << "\",\"passed\":true,\"hardware_executed\":false}\n";
        return 0;
    }
    PhxBringup p;
    uint64_t input[6] = {0x40000, 1024, 0x42000, 0x18, 13, 0x43000};
    IOReturn expected = kIOReturnSuccess;
    bool repeated = false;
    auto peer = [&]() {
        p.gq[1].ready = true; p.gq[1].gfx = true;
        p.gq[1].ringOff = 0x50000; p.gq[1].ringDw = 1024;
        p.gq[1].wbOff = 0x52000; p.gq[1].fenceOff = 0x53000; p.gq[1].dbByte = 0x20;
        p.gq[1].wptr = 100; p.gq[1].doneEnd = 90;
        p.gq[1].tail = 1; p.gq[1].fseq[0] = p.gSeq; p.gq[1].fend[0] = 100;
    };
    if (test == "compute") {}
    else if (test == "graphics") input[5] |= 1;
    else if (test == "second-queue") peer();
    else if (test == "unready-peer") { peer(); p.gq[1].ready = false; input[3] = p.gq[1].dbByte; }
    else if (test == "adjacent-regions") { input[2] = 0x41000; input[5] = 0x41020; }
    else if (test == "aperture-end") input[5] = p.fbAperLen - 8;
    else if (test == "doorbell-end") input[3] = p.bells.length - 8;
    else if (test == "minimum-ring") input[1] = 256;
    else if (test == "maximum-ring") { input[1] = 65536; input[2] = 0x80000; input[5] = 0x80020; }
    else if (test == "repeated-compute" || test == "repeated-graphics" || test == "live-history") {
        if (test == "repeated-graphics") { input[5] |= 1; p.target = 1; }
        assert(p.adoptQueue(input) == kIOReturnSuccess);
        if (test == "live-history") {
            p.gq[0].tail = 2; p.gq[0].fseq[0] = 77; p.gq[0].fseq[1] = 78;
            p.gq[0].fend[0] = 20; p.gq[0].fend[1] = 30;
            input[0] += 0x10000; input[2] += 0x10000; input[5] += 0x10000;
        }
        expected = kIOReturnExclusiveAccess; repeated = true;
    }
    else if (test == "null-input") expected = kIOReturnBadArgument;
    else if (test.rfind("no-", 0) == 0 || test == "psp-fault" || test == "stopping") {
        expected = kIOReturnNotReady;
        if (test == "no-aperture") p.fbAper = nullptr;
        else if (test == "no-doorbell") p.doorbellMap = nullptr;
        else if (test == "no-mmio") p.mmio = nullptr;
        else if (test == "no-mc-base") p.fbMcBase = 0;
        else if (test == "no-gpu-lock") p.gpuLock = nullptr;
        else if (test == "no-smu-lock") p.smuLock = nullptr;
        else if (test == "no-layout") p.pspLayoutConfigured = false;
        else if (test == "psp-fault") p.pspSubmissionFaulted = true;
        else if (test == "stopping") p.stopping = true;
        else assert(false);
    }
    else if (test == "invalid-layout") { p.pspLayout.reserved[0] = 1; expected = kIOReturnBadArgument; }
    else if (test == "mc-overflow" || test == "physical-overflow") {
        (test == "mc-overflow" ? p.fbMcBase : p.fbPhys) = UINT64_MAX - 4095;
        expected = kIOReturnBadArgument;
    }
    else if (test == "shared-doorbell") { peer(); input[3] = p.gq[1].dbByte; expected = kIOReturnExclusiveAccess; }
    else if (test.rfind("psp-", 0) == 0 || test.rfind("peer-", 0) == 0) {
        const bool firmware = test.rfind("psp-", 0) == 0;
        const size_t pos = firmware ? 4 : 5;
        const unsigned candidate = test[pos] - '0', occupied = test[pos + 2] - '0';
        assert(candidate < 3 && occupied < 3);
        peer();
        const uint64_t reserved[] = {p.pspLayout.ringOffset, p.pspLayout.tmrOffset, p.pspLayout.stagingOffset};
        const uint64_t existing[] = {p.gq[1].ringOff, p.gq[1].wbOff, p.gq[1].fenceOff};
        const unsigned fields[] = {0, 2, 5};
        input[fields[candidate]] = firmware ? reserved[occupied] : existing[occupied];
        expected = kIOReturnExclusiveAccess;
    }
    else {
        expected = kIOReturnBadArgument;
        if (test == "ring-zero") input[1] = 0;
        else if (test == "ring-small") input[1] = 128;
        else if (test == "ring-large") input[1] = 131072;
        else if (test == "ring-not-power-two") input[1] = 257;
        else if (test == "ring-misaligned") input[0] += 8;
        else if (test == "wb-misaligned") input[2] += 4;
        else if (test == "fence-bit1") input[5] |= 2;
        else if (test == "fence-bit2") input[5] |= 4;
        else if (test == "doorbell-misaligned") input[3] += 4;
        else if (test == "doorbell-overflow") { input[3] = UINT64_MAX - 7; p.bells.length = UINT64_MAX; }
        else if (test == "doorbell-overrun") input[3] = p.bells.length;
        else if (test == "ring-wb-overlap") input[2] = input[0] + 8;
        else if (test == "ring-fence-overlap") input[5] = input[0] + 8;
        else if (test == "wb-fence-overlap") input[5] = input[2] + 24;
        else {
            const unsigned field = test.rfind("ring-", 0) == 0 ? 0 : test.rfind("wb-", 0) == 0 ? 2 : 5;
            const auto failure = test.substr(test.find('-') + 1);
            const uint64_t alignment = field == 0 ? 256 : 8;
            if (failure == "overflow") { input[field] = UINT64_MAX - alignment + 1; p.fbAperLen = p.fbSize = UINT64_MAX; }
            else if (failure == "narrow") { input[field] = 0x100000000ull; p.fbAperLen = p.fbSize = 0x200000000ull; }
            else if (failure == "cross-32bit") {
                input[field] = field == 5 ? 0x100000000ull : 0x100000000ull - alignment;
                p.fbAperLen = p.fbSize = 0x200000000ull;
            }
            else if (failure == "aperture-overrun") { p.fbSize *= 2; input[field] = p.fbAperLen; }
            else if (failure == "vram-overrun") { p.fbAperLen *= 2; input[field] = p.fbSize; }
            else assert(false);
        }
    }
    p.target = static_cast<unsigned>(input[5] & 1);
    const auto memory = p.memory.words, bells = p.bells.words;
    unsigned char queues[sizeof(p.gq)]; std::memcpy(queues, p.gq, sizeof(p.gq));
    const auto seq = p.gSeq;
    const unsigned flushes = p.flushes, locks = acquisitions;
    const auto result = p.adoptQueue(test == "null-input" ? nullptr : input);
    assert(result == expected && depth == 0 && !p.gpuMutex.held && !p.smuMutex.held);
    assert(p.bells.words == bells && p.gSeq == seq);
    if (result != kIOReturnSuccess) {
        assert(p.memory.words == memory && p.flushes == flushes);
        assert(std::memcmp(queues, p.gq, sizeof(p.gq)) == 0);
        if (repeated) assert(acquisitions - locks == 2);
    } else {
        assert(acquisitions - locks == 2 && p.flushes == flushes + 1);
        const auto &q = p.gq[p.target];
        assert(q.ready && q.gfx == (p.target == 1) && q.ringOff == input[0] && q.ringDw == input[1]);
        assert(q.wbOff == input[2] && q.dbByte == input[3] && q.wptr == input[4] && q.doneEnd == input[4]);
        assert(q.retiredSeq == seq);
        assert(q.fenceOff == (input[5] & ~1ull) && q.head == 0 && q.tail == 0);
        for (unsigned i = 0; i < 64; ++i) assert(q.fseq[i] == 0 && q.fend[i] == 0);
        const unsigned other = p.target ^ 1;
        assert(std::memcmp(queues + other * sizeof(q), &p.gq[other], sizeof(q)) == 0);
        auto changed = memory;
        changed[q.fenceOff / 4] = static_cast<uint32_t>(seq);
        changed[q.fenceOff / 4 + 1] = static_cast<uint32_t>(seq >> 32);
        assert(p.memory.words == changed);
    }
    std::cout << "{\"case\":\"" << test << "\",\"passed\":true,\"hardware_executed\":false}\n";
}
