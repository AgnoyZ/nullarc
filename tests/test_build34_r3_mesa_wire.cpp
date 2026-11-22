// SPDX-License-Identifier: MIT
#include "paired-native-receipt.h"

extern "C" {
#include "build34_r3_mesa_wire.h"

int acd_kext_open_iokit(struct acd_kext **) { std::abort(); }
}

struct Bridge {
    PhxBringup device;
    IOAccelPhxNativeClient client;
    const uint64_t owner;
    unsigned submits = 0, waits = 0, acks = 0, prefixes = 0;
    uint32_t corruptSelector = 0;
    unsigned corruption = 0;
    bool badPrefix = false;
    phx34_mesa_wire wire;
    acd_exact_backend backend;
    acd_kext *transport;

    static int call(void *context, uint32_t selector, const void *input, size_t inputSize,
                    void *output, size_t *outputSize) {
        auto &bridge = *static_cast<Bridge *>(context);
        CHECK(*outputSize == 64 && inputSize == (selector == 66 ? 2112 : 64));
        switch (selector) {
        case 66: ++bridge.submits; break;
        case 64: ++bridge.waits; break;
        case 65: ++bridge.acks; break;
        default: CHECK(false);
        }
        IOExternalMethodArguments args;
        args.selector = selector;
        args.scalarOutputCount = 0;
        args.structureInput = input;
        args.structureInputSize = inputSize;
        args.structureOutput = output;
        args.structureOutputSize = *outputSize;
        const int status = bridge.client.externalMethod(selector, &args, nullptr, nullptr, nullptr);
        switch (status) {
        case kIOReturnBusy: return static_cast<int>(ACD_KR_BUSY);
        case kIOReturnNoResources: return static_cast<int>(ACD_KR_NO_RESOURCES);
        case kIOReturnNotReady: return static_cast<int>(ACD_KR_NOT_READY);
        case kIOReturnNotFound: return static_cast<int>(ACD_KR_NOT_FOUND);
        case kIOReturnBadArgument: return static_cast<int>(ACD_KR_BAD_ARGUMENT);
        case kIOReturnUnsupported: return static_cast<int>(ACD_KR_UNSUPPORTED);
        default: CHECK(status == kIOReturnSuccess);
        }
        if (bridge.corruptSelector == selector) {
            auto &reply = *static_cast<phx34_r3_reply *>(output);
            switch (bridge.corruption) {
            case 0: return 0x10000003;
            case 1: --*outputSize; break;
            case 2: ++reply.version; break;
            case 3: --reply.size; break;
            case 4: ++reply.reserved0; break;
            case 5: ++reply.reserved; break;
            case 6: reply.status = 4; break;
            case 7: ++reply.owner; break;
            case 8: ++reply.serial; break;
            case 9: ++reply.sequence; break;
            case 10: ++reply.generation; break;
            case 11: reply.slot ^= 1; break;
            case 12: reply.queue ^= 1; break;
            case 13: return static_cast<int>(ACD_KR_EXCLUSIVE_ACCESS);
            default: CHECK(false);
            }
        }
        return 0;
    }

    static int prefix(void *context, uint64_t target, uint64_t timeout, acd_exact_snapshot *out) {
        auto &bridge = *static_cast<Bridge *>(context);
        CHECK(timeout <= N48N_WAIT_CAP_NS && (target || !timeout));
        ++bridge.prefixes;
        *out = {bridge.owner + bridge.badPrefix, bridge.device.gpuRetired()};
        return 0;
    }

    Bridge() : owner((setup(client, device), ownerID(client))), wire{owner, this, call, prefix} {
        const acd_kext_ops ops{.call = nullptr};
        transport = acd_kext_create(&ops, nullptr);
        CHECK(transport && phx34_mesa_wire_backend(&wire, &backend) == 0);
        CHECK(acd_kext_set_exact_backend(transport, &backend) == 0);
    }

    ~Bridge() { acd_kext_destroy(transport); }

    int submit(uint32_t engine, uint64_t *sequence, bool cpuFence = false) {
        n48n_cs_ib ib{.va_start = 0x20000, .ib_bytes = 4, .ip_type = engine};
        const acd_cs_plan plan{.ctx_id = 1, .ibs = &ib, .n_ibs = 1, .has_fence = cpuFence,
                               .fence_handle = cpuFence ? 7u : 0u};
        return acd_kext_submit(transport, &plan, sequence);
    }
};

static void paired_round_trip() {
    reset();
    Bridge bridge;
    uint64_t compute = 0, gfx = 0;
    CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &gfx, true) == -EOPNOTSUPP);
    CHECK(!bridge.submits && !gfx && !packetWrites);
    CHECK(bridge.submit(AMDGPU_HW_IP_COMPUTE, &compute) == 0 && compute == 100);
    CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &gfx) == 0 && gfx == 101);
    CHECK(bridge.client.exactRegistry.occupied() == 2);
    bool busy = false;
    acd_wait_status snapshot{};
    CHECK(acd_kext_wait_seq(bridge.transport, gfx, 1, &busy, &snapshot) == 0 && busy);
    CHECK(snapshot.retired == 99 && bridge.prefixes == 1);
    bridge.device.setFence(1, gfx);
    CHECK(acd_kext_wait_seq(bridge.transport, gfx, 0, &busy, &snapshot) == 0 && !busy);
    CHECK(snapshot.retired == 99 && bridge.acks == 1 && bridge.client.exactRegistry.occupied() == 1);
    CHECK(acd_kext_wait_seq(bridge.transport, gfx, 0, &busy, &snapshot) == 0 && !busy);
    CHECK(snapshot.retired == 99 && bridge.waits == 2);
    CHECK(acd_kext_wait_seq(bridge.transport, compute, 0, &busy, &snapshot) == 0 && busy);
    bridge.device.setFence(0, compute);
    CHECK(acd_kext_wait_seq(bridge.transport, 0, 0, &busy, &snapshot) == 0 && !busy);
    CHECK(snapshot.retired == gfx && bridge.acks == 2 && !bridge.client.exactRegistry.occupied());
}

static void full_receipts() {
    reset();
    Bridge bridge;
    uint64_t sequence = 0;
    for (unsigned index = 0; index < 64; ++index) {
        CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &sequence) == 0);
        bridge.device.setFence(1, sequence);
    }
    CHECK(bridge.client.exactRegistry.occupied() == 64);
    unsigned writes = packetWrites;
    CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &sequence) == -EAGAIN && packetWrites == writes);
    CHECK(bridge.client.exactRegistry.occupied() == 64 && sequence == 163);
    bool busy = true;
    CHECK(acd_kext_wait_seq(bridge.transport, 100, 0, &busy, nullptr) == 0 && !busy);
    CHECK(!bridge.client.exactRegistry.occupied() && bridge.acks == 64);
    CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &sequence) == 0 && sequence == 164);
}

static void uncertain_replies() {
    for (uint32_t selector : {64u, 65u, 66u}) {
        for (unsigned fault = 0; fault != 14; ++fault) {
            if (selector == 66 && fault >= 8 && fault <= 12)
                continue;
            reset();
            Bridge bridge;
            uint64_t sequence = 0;
            bridge.corruptSelector = selector;
            bridge.corruption = fault;
            if (selector == 66) {
                CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &sequence) < 0 && !sequence);
            } else {
                CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &sequence) == 0);
                bridge.device.setFence(1, sequence);
                bool busy = true;
                CHECK(acd_kext_wait_seq(bridge.transport, sequence, 0, &busy, nullptr) < 0 && busy);
                CHECK(bridge.acks == (selector == 65));
            }
            CHECK(bridge.client.exactRegistry.occupied() == (selector != 65));
            CHECK(bridge.submit(AMDGPU_HW_IP_COMPUTE, &sequence) == -ECANCELED && bridge.submits == 1);
        }
    }
    reset();
    Bridge bridge;
    uint64_t sequence = 0;
    CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &sequence) == 0);
    bridge.device.setFence(1, sequence);
    bridge.badPrefix = true;
    bool busy = true;
    CHECK(acd_kext_wait_seq(bridge.transport, sequence, 0, &busy, nullptr) == -EPROTO && busy);
    CHECK(bridge.prefixes == 1 && !bridge.acks && bridge.client.exactRegistry.occupied() == 1);
}

int main() {
    paired_round_trip();
    full_receipts();
    uncertain_replies();
    std::printf("PASS staged Mesa/native wire: %llu checks; GPU_executed=false\n",
                static_cast<unsigned long long>(checks.load()));
}
