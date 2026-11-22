// SPDX-License-Identifier: MIT
#include "paired-native-receipt.h"

extern "C" {
#include "build34_r3_mesa_wire.h"

#ifdef PHX34_TEST_IOKIT
#include "build34_r3_mesa_iokit.h"
#ifdef PHX34_TEST_DRM
#include "build34_r3_mesa_drm.h"
#include "util/u_sync_provider.h"
#endif
#else
int acd_kext_open_iokit(struct acd_kext **) { std::abort(); }
#endif
}

struct Bridge {
    PhxBringup device;
    IOAccelPhxNativeClient client;
    const uint64_t owner;
    unsigned submits = 0, waits = 0, acks = 0, prefixes = 0, sessions = 0;
    uint32_t corruptSelector = 0;
    unsigned corruption = 0;
    phx34_mesa_wire wire;
    acd_exact_backend backend;
    acd_kext *transport;

    static bool readDword(const volatile uint32_t *value, uint32_t *out) {
        CHECK(clientHeld && gpuHeld);
        std::memcpy(out, const_cast<const uint32_t *>(value), sizeof(*out));
        event("prefix-dword");
        return true;
    }

    static int call(void *context, uint32_t selector, const void *input, size_t inputSize,
                    void *output, size_t *outputSize) {
        auto &bridge = *static_cast<Bridge *>(context);
        const bool progress = selector == PHX34_R3_SEL_SESSION || selector == PHX34_R3_SEL_PREFIX;
        CHECK(*outputSize == (progress ? 48 : 64) && inputSize == (progress ? 32 : selector == 66 ? 2112 : 64));
        switch (selector) {
        case 66: ++bridge.submits; break;
        case 64: ++bridge.waits; break;
        case 65: ++bridge.acks; break;
        case PHX34_R3_SEL_PREFIX: ++bridge.prefixes; break;
        case PHX34_R3_SEL_SESSION: ++bridge.sessions; break;
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
            if (progress) {
                auto &reply = *static_cast<phx34_r3_progress_reply *>(output);
                switch (bridge.corruption) {
                case 0: return 0x10000003;
                case 1: --*outputSize; break;
                case 2: ++reply.version; break;
                case 3: --reply.size; break;
                case 4: ++reply.build; break;
                case 5: ++reply.flags; break;
                case 6: ++reply.target; break;
                case 7: reply.owner = selector == PHX34_R3_SEL_PREFIX ? reply.owner + 1 : 0; break;
                case 8: reply.retired = UINT64_MAX; break;
                case 9: ++reply.reserved; break;
                default: CHECK(false);
                }
                return 0;
            }
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

    explicit Bridge(bool negotiate = true) : owner((setup(client, device), ownerID(client))), wire{0, this, call} {
        testTicks = 10000000;
        device.exactDwordReader = readDword;
        for (unsigned queue = 0; queue < 2; ++queue)
            CHECK(device.exactFenceWindow[queue].seed(device.exactQueueGeneration[queue], device.gSeq));
        const acd_kext_ops ops{.call = nullptr};
        transport = acd_kext_create(&ops, nullptr);
        CHECK(transport);
        if (negotiate) {
            CHECK(phx34_mesa_wire_backend(&wire, &backend) == 0 && backend.owner == owner);
            CHECK(acd_kext_set_exact_backend(transport, &backend) == 0);
        }
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
    bridge.corruptSelector = PHX34_R3_SEL_PREFIX;
    bridge.corruption = 7;
    bool busy = true;
    CHECK(acd_kext_wait_seq(bridge.transport, sequence, 0, &busy, nullptr) == -EPROTO && busy);
    CHECK(bridge.prefixes == 1 && !bridge.acks && bridge.client.exactRegistry.occupied() == 1);
}

static void sequence_modes() {
    reset();
    Bridge bridge;
    Request exactRequest;
    CHECK(bridge.client.externalMethod(PHXN_SEL_WAITSEQ, &exactRequest.a, nullptr, nullptr, nullptr) ==
          kIOReturnUnsupported);
    CHECK(bridge.client.externalMethod(PHXN_SEL_SUBMIT, &exactRequest.a, nullptr, nullptr, nullptr) ==
          kIOReturnUnsupported);
    CHECK(exactRequest.a.scalarOutput[0] == sentinel && !packetWrites && !bridge.client.exactRegistry.occupied());
    uint64_t sequence = 0;
    CHECK(bridge.submit(AMDGPU_HW_IP_COMPUTE, &sequence) == 0 && sequence == 100);

    PhxBringup legacyDevice;
    IOAccelPhxNativeClient legacy;
    CHECK(legacy.start(&legacyDevice));
    legacy.hello = true;
    Request legacyRequest;
    for (uint32_t selector : {PHX34_R3_SEL_SUBMIT_RECEIPT, PHX34_R3_SEL_WAIT_RECEIPT, PHX34_R3_SEL_ACK_RECEIPT,
                              PHX34_R3_SEL_SESSION, PHX34_R3_SEL_PREFIX})
        CHECK(legacy.externalMethod(selector, &legacyRequest.a, nullptr, nullptr, nullptr) == kIOReturnUnsupported);
    CHECK(legacyRequest.a.scalarOutput[0] == sentinel && legacyDevice.gSeq == 99);
    CHECK(legacy.externalMethod(PHXN_SEL_WAITSEQ, &legacyRequest.a, nullptr, nullptr, nullptr) == 123);
    CHECK(legacy.externalMethod(PHXN_SEL_SUBMIT, &legacyRequest.a, nullptr, nullptr, nullptr) == kIOReturnSuccess);
    CHECK(legacyRequest.a.scalarOutput[0] == 100 && legacyDevice.gSeq == 100);
}

static void checked_progress() {
    reset();
    Bridge bridge;
    CHECK(bridge.sessions == 1 && !bridge.prefixes && !packetWrites);
    CHECK(phx34_mesa_wire_backend(&bridge.wire, &bridge.backend) == -EBUSY && bridge.sessions == 1);
    uint64_t compute = 0, gfx = 0;
    CHECK(bridge.submit(AMDGPU_HW_IP_COMPUTE, &compute) == 0);
    CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &gfx) == 0);
    bridge.device.setFence(1, gfx);
    acd_wait_status snapshot{};
    bool busy = false;
    unsigned sleeps = 0;
    eventHook = [&](const char *name) {
        if (!std::strcmp(name, "poll-sleep")) {
            CHECK(!clientHeld && !gpuHeld);
            ++sleeps;
        }
    };
    CHECK(acd_kext_wait_seq(bridge.transport, N48N_SEQ_LAST, 2000000, &busy, &snapshot) == 0 && busy);
    CHECK(snapshot.retired == 99 && sleeps == 2 && !bridge.acks && !bridge.waits);
    eventHook = {};
    bridge.device.setFence(0, compute);
    CHECK(acd_kext_wait_seq(bridge.transport, N48N_SEQ_LAST, 1, &busy, &snapshot) == 0 && !busy);
    CHECK(snapshot.retired == gfx && bridge.acks == 2 && !bridge.waits);
    CHECK(bridge.prefixes == 2 && !bridge.client.exactRegistry.occupied());
}

static void invalid_progress() {
    for (uint32_t selector : {PHX34_R3_SEL_SESSION, PHX34_R3_SEL_PREFIX}) {
        for (unsigned fault = 0; fault != 10; ++fault) {
            reset();
            Bridge bridge(selector != PHX34_R3_SEL_SESSION);
            bridge.corruptSelector = selector;
            bridge.corruption = fault;
            if (selector == PHX34_R3_SEL_SESSION) {
                acd_exact_backend untouched{};
                untouched.owner = UINT64_MAX;
                CHECK(phx34_mesa_wire_backend(&bridge.wire, &untouched) < 0);
                CHECK(!bridge.wire.owner && untouched.owner == UINT64_MAX && !bridge.submits);
            } else {
                acd_exact_snapshot untouched{UINT64_MAX, UINT64_MAX};
                CHECK(bridge.backend.wait_prefix(bridge.backend.ctx, 0, 0, &untouched) < 0);
                CHECK(untouched.owner == UINT64_MAX && untouched.retired == UINT64_MAX);
            }
        }
    }
    for (unsigned fault = 0; fault != 7; ++fault) {
        reset();
        Bridge bridge(false);
        switch (fault) {
        case 0: bridge.client.hello = false; break;
        case 1: bridge.device.exactDwordReader = nullptr; break;
        case 2: bridge.device.exactQueueAdopted[1] = false; break;
        case 3: ++bridge.device.exactQueueGeneration[1]; break;
        case 4: bridge.device.isSleeping = true; break;
        case 5: bridge.device.exactVMFault = true; break;
        case 6: bridge.device.exactCallbacks.close(); break;
        }
        acd_exact_backend untouched{};
        untouched.owner = UINT64_MAX;
        CHECK(phx34_mesa_wire_backend(&bridge.wire, &untouched) == -ENODEV);
        CHECK(!bridge.wire.owner && untouched.owner == UINT64_MAX);
    }
    reset();
    Bridge bridge;
    phx34_r3_progress_request request{PHX34_R3_WIRE_VERSION, sizeof(request), bridge.owner + 1, 0, 0};
    phx34_r3_progress_reply reply{};
    reply.owner = UINT64_MAX;
    size_t size = sizeof(reply);
    CHECK(static_cast<uint32_t>(Bridge::call(&bridge, PHX34_R3_SEL_PREFIX, &request, sizeof(request), &reply, &size)) ==
          ACD_KR_NOT_FOUND && reply.owner == UINT64_MAX);
    request.owner = bridge.owner;
    request.target = 1;
    CHECK(static_cast<uint32_t>(Bridge::call(&bridge, PHX34_R3_SEL_PREFIX, &request, sizeof(request), &reply, &size)) ==
          ACD_KR_BAD_ARGUMENT && reply.owner == UINT64_MAX);
    request.target = 0;
    eventHook = [&](const char *name) {
        if (!std::strcmp(name, "prefix-dword")) bridge.client.exactClientCallbacks.close();
    };
    CHECK(static_cast<uint32_t>(Bridge::call(&bridge, PHX34_R3_SEL_PREFIX, &request, sizeof(request), &reply, &size)) ==
          ACD_KR_NOT_READY && reply.owner == UINT64_MAX);
    eventHook = {};
}

static void zero_and_queue_loss() {
    reset();
    Bridge zero(false);
    zero.device.gSeq = 0;
    for (unsigned queue = 0; queue < 2; ++queue) {
        zero.device.exactQueueSubmitted[queue] = 0;
        zero.device.setFence(queue, 0);
        zero.device.exactFenceWindow[queue].invalidate();
        CHECK(zero.device.exactFenceWindow[queue].seed(++zero.device.exactQueueGeneration[queue], 0));
    }
    CHECK(phx34_mesa_wire_backend(&zero.wire, &zero.backend) == 0 && zero.backend.owner == zero.owner);
    acd_exact_snapshot observation{UINT64_MAX, UINT64_MAX};
    CHECK(zero.backend.wait_prefix(zero.backend.ctx, 0, 0, &observation) == 0);
    CHECK(observation.owner == zero.owner && !observation.retired);

    reset();
    Bridge loss;
    uint64_t sequence = 0;
    CHECK(loss.submit(AMDGPU_HW_IP_GFX, &sequence) == 0);
    unsigned sleeps = 0;
    eventHook = [&](const char *name) {
        if (!std::strcmp(name, "poll-sleep")) {
            CHECK(!clientHeld && !gpuHeld);
            loss.device.exactQueueLive[0] = false;
            ++sleeps;
        }
    };
    bool busy = false;
    acd_wait_status status{UINT64_MAX, UINT64_MAX};
    CHECK(acd_kext_wait_seq(loss.transport, N48N_SEQ_LAST, 2000000, &busy, &status) == -ENODEV);
    eventHook = {};
    CHECK(sleeps == 1 && status.retired == UINT64_MAX && !loss.acks);
    CHECK(loss.client.exactRegistry.occupied() == 1);
    CHECK(loss.submit(AMDGPU_HW_IP_GFX, &sequence) == -ECANCELED && loss.submits == 1);
}

#ifdef PHX34_TEST_IOKIT
struct FakeIOKit {
    Bridge bridge{false};
    mach_port_t port = 0x105;
    unsigned helloCalls = 0, closes = 0, helloFault = 0, failAllocation = 0;
#ifdef PHX34_TEST_DRM
    bool drm = false;
    Pause *waitPause = nullptr;
#endif
    static thread_local FakeIOKit *current;

    FakeIOKit() {
        CHECK(!current);
        current = this;
    }

    ~FakeIOKit() { current = nullptr; }
};

thread_local FakeIOKit *FakeIOKit::current = nullptr;

extern "C" void *phx34_fixture_calloc(size_t count, size_t size) {
    auto *fake = FakeIOKit::current;
    if (fake && fake->failAllocation && --fake->failAllocation == 0)
        return nullptr;
    return std::calloc(count, size);
}

extern "C" kern_return_t phx34_fixture_method(mach_port_t conn, uint32_t selector, const uint64_t *scalars,
                                              uint32_t scalarCount, const void *input, size_t inputSize,
                                              uint64_t *scalarOut, uint32_t *scalarOutCount, void *output,
                                              size_t *outputSize) {
    auto *fake = FakeIOKit::current;
    CHECK(fake && conn == 0x105 && fake->port == MACH_PORT_NULL && !fake->closes);
    if (selector == ACD_SEL_HELLO) {
        ++fake->helloCalls;
#ifdef PHX34_TEST_DRM
        CHECK(fake->helloCalls == 1 || (fake->drm && fake->helloCalls == 2 && fake->bridge.sessions == 1));
#else
        CHECK(fake->helloCalls == 1);
#endif
        CHECK(scalars && scalarCount == 2 && scalars[0] == N48N_ABI_VERSION && scalars[1] == N48N_HELLO_F_MINOR);
        CHECK(!input && !inputSize && !output && !outputSize);
        CHECK(scalarOut && scalarOutCount && *scalarOutCount == 4);
        if (fake->helloFault == 1)
            return static_cast<kern_return_t>(ACD_KR_NOT_READY);
        if (fake->helloFault == 2)
            *scalarOutCount = 3;
        scalarOut[0] = (uint64_t{9} << 16) | (N48N_ABI_VERSION + (fake->helloFault == 3));
        scalarOut[1] = PHX34_R3_PROGRESS_BUILD + (fake->helloFault == 4);
        scalarOut[2] = N48N_MAX_IBS - (fake->helloFault == 5);
        scalarOut[3] = PHXN_VMID + (fake->helloFault == 6);
        return KERN_SUCCESS;
    }
#ifdef PHX34_TEST_DRM
    if (fake->drm && (selector == ACD_SEL_QUERY_INFO || selector == PHX_SEL_TOPOLOGY)) {
        CHECK(fake->helloCalls == 2 && !scalars && !scalarCount && !input && !inputSize && !scalarOut && !scalarOutCount);
        CHECK(output && outputSize);
        if (selector == PHX_SEL_TOPOLOGY)
            return static_cast<kern_return_t>(ACD_KR_UNSUPPORTED);
        CHECK(*outputSize == sizeof(n48n_info));
        auto &info = *static_cast<n48n_info *>(output);
        info = {};
        info.gb_addr_config = acd_canned_gb_addr_config(acd_canned_device());
        info.va_low_last = info.va_high_last = UINT64_MAX;
        return KERN_SUCCESS;
    }
    CHECK(fake->helloCalls == (fake->drm && selector != PHX34_R3_SEL_SESSION ? 2u : 1u));
    if (selector == PHX34_R3_SEL_WAIT_RECEIPT && fake->waitPause)
        fake->waitPause->arrive();
    CHECK(!scalars && !scalarCount && !scalarOut && !scalarOutCount);
#else
    CHECK(fake->helloCalls == 1 && !scalars && !scalarCount && !scalarOut && !scalarOutCount);
#endif
    return Bridge::call(&fake->bridge, selector, input, inputSize, output, outputSize);
}

extern "C" kern_return_t phx34_fixture_close(mach_port_t conn) {
    auto *fake = FakeIOKit::current;
    CHECK(fake && conn == 0x105 && fake->port == MACH_PORT_NULL && ++fake->closes == 1);
    return KERN_SUCCESS;
}

static void iokit_adoption() {
    reset();
    FakeIOKit fake;
    auto &bridge = fake.bridge;
    acd_kext *adopted = bridge.transport;
    CHECK(acd_kext_adopt_exact_iokit(&fake.port, &adopted) == -EINVAL && fake.port == 0x105);
    adopted = nullptr;
    mach_port_t dead = MACH_PORT_DEAD;
    CHECK(acd_kext_adopt_exact_iokit(&dead, &adopted) == -EINVAL && dead == MACH_PORT_DEAD);
    CHECK(acd_kext_adopt_exact_iokit(nullptr, &adopted) == -EINVAL && !adopted);
    CHECK(acd_kext_adopt_exact_iokit(&fake.port, nullptr) == -EINVAL && fake.port == 0x105);
    CHECK(!fake.helloCalls && !fake.closes);
    CHECK(acd_kext_adopt_exact_iokit(&fake.port, &adopted) == 0 && adopted);
    CHECK(fake.port == MACH_PORT_NULL && fake.helloCalls == 1 && bridge.sessions == 1 && !bridge.submits);
    acd_kext_destroy(bridge.transport);
    bridge.transport = adopted;

    uint64_t compute = 0, gfx = 0;
    CHECK(bridge.submit(AMDGPU_HW_IP_COMPUTE, &compute) == 0 && compute == 100);
    CHECK(bridge.submit(AMDGPU_HW_IP_GFX, &gfx) == 0 && gfx == 101);
    bool busy = false;
    acd_wait_status snapshot{};
    CHECK(acd_kext_wait_seq(adopted, gfx, 1, &busy, &snapshot) == 0 && busy);
    bridge.device.setFence(1, gfx);
    CHECK(acd_kext_wait_seq(adopted, gfx, 0, &busy, &snapshot) == 0 && !busy && snapshot.retired < compute);
    CHECK(bridge.acks == 1 && bridge.client.exactRegistry.occupied() == 1);
    bridge.device.setFence(0, compute);
    CHECK(acd_kext_wait_seq(adopted, 0, 0, &busy, &snapshot) == 0 && !busy && snapshot.retired == gfx);
    CHECK(bridge.acks == 2 && !bridge.client.exactRegistry.occupied());
    acd_kext_destroy(adopted);
    bridge.transport = nullptr;
    CHECK(fake.closes == 1);
}

static void iokit_adoption_errors() {
    for (unsigned fault = 1; fault <= 11; ++fault) {
        reset();
        FakeIOKit fake;
        int expected = -EPROTO;
        if (fault <= 6) {
            fake.helloFault = fault;
            expected = fault == 1 ? -ENODEV : fault == 2 ? -EIO : -EPROTO;
        } else if (fault == 7) {
            fake.bridge.client.hello = false;
            expected = -ENODEV;
        } else if (fault == 8) {
            fake.bridge.corruptSelector = PHX34_R3_SEL_SESSION;
            fake.bridge.corruption = 5;
        } else {
            fake.failAllocation = fault - 8;
            expected = -ENOMEM;
        }
        acd_kext *adopted = nullptr;
        CHECK(acd_kext_adopt_exact_iokit(&fake.port, &adopted) == expected);
        CHECK(!adopted && fake.port == MACH_PORT_NULL && fake.closes == 1);
        CHECK(fake.helloCalls == (fault != 9 && fault != 10));
        CHECK(fake.bridge.sessions == (fault == 7 || fault == 8 || fault == 11));
        CHECK(!fake.bridge.submits && !fake.bridge.waits && !fake.bridge.acks && !packetWrites);
    }
}
#endif

#ifdef PHX34_TEST_DRM
static void drm_drop(acd_device_handle device) {
    auto *provider = acd_device_get_sync_provider(device);
    provider->finalize(provider);
    acd_device_deinitialize(device);
}

static uint32_t drm_signal_handle(util_sync_provider *provider) {
    uint32_t handle = 0;
    CHECK(provider->create(provider, 0, &handle) == 0 && handle);
    return handle;
}

static uint64_t drm_submit(acd_device_handle device, uint32_t engine, uint32_t signal) {
    drm_amdgpu_cs_chunk_ib ib{.va_start = 0x20000, .ib_bytes = 4, .ip_type = engine};
    drm_amdgpu_cs_chunk_sem sem{.handle = signal};
    drm_amdgpu_cs_chunk chunks[] = {
        {AMDGPU_CHUNK_ID_IB, sizeof(ib) / 4, reinterpret_cast<uintptr_t>(&ib)},
        {AMDGPU_CHUNK_ID_SYNCOBJ_OUT, sizeof(sem) / 4, reinterpret_cast<uintptr_t>(&sem)},
    };
    uint64_t pointers[] = {reinterpret_cast<uintptr_t>(&chunks[0]), reinterpret_cast<uintptr_t>(&chunks[1])};
    drm_amdgpu_cs args{.in = {.ctx_id = 1, .num_chunks = 2, .chunks = reinterpret_cast<uintptr_t>(pointers)}};
    CHECK(acd_ioctl(device, DRM_AMDGPU_CS, &args, sizeof(args)) == 0);
    return args.out.handle;
}

static void drm_publish_and_drain() {
    reset();
    FakeIOKit fake;
    fake.drm = true;
    acd_device_handle primary = nullptr, secondary = nullptr;
    uint32_t major = 0, minor = 0;
    CHECK(acd_device_initialize_exact_iokit(nullptr, &major, &minor, &primary) == -ENODEV && !primary);
    CHECK(acd_device_initialize_exact_iokit(&fake.port, &major, &minor, &primary) == 0 && primary);
    CHECK(fake.port == MACH_PORT_NULL && fake.helloCalls == 2 && fake.bridge.sessions == 1);
    mach_port_t extra = 0x106;
    CHECK(acd_device_initialize_exact_iokit(&extra, &major, &minor, &secondary) == -EBUSY && extra == 0x106 && !secondary);
    CHECK(acd_device_initialize(&major, &minor, &secondary) == -EBUSY && !secondary);
    CHECK(acd_device_initialize_exact_iokit(nullptr, &major, &minor, &secondary) == 0 && secondary);
    CHECK(acd_device_kext(primary, nullptr) == acd_device_kext(secondary, nullptr));
    auto *provider = acd_device_get_sync_provider(primary);
    CHECK(acd_sync_has_exact_completion(provider) && acd_sync_has_exact_completion(acd_device_get_sync_provider(secondary)));
    auto *waiter = provider->clone(provider);
    auto *observer = provider->clone(provider);
    CHECK(waiter && observer);
    uint32_t computeHandle = drm_signal_handle(provider), gfxHandle = drm_signal_handle(provider);
    uint32_t unsubmitted = drm_signal_handle(observer);
    const uint64_t compute = drm_submit(primary, AMDGPU_HW_IP_COMPUTE, computeHandle);
    const uint64_t gfx = drm_submit(secondary, AMDGPU_HW_IP_GFX, gfxHandle);
    CHECK(compute == 100 && gfx == 101);
    fake.bridge.device.setFence(1, gfx);
    CHECK(waiter->wait(waiter, &gfxHandle, 1, 0, 0, nullptr) == 0);
    CHECK(waiter->wait(waiter, &computeHandle, 1, 0, 0, nullptr) == -1 && errno == ETIME);
    CHECK(fake.bridge.acks == 1 && fake.bridge.client.exactRegistry.occupied() == 1);
    drm_drop(primary);
    CHECK(!fake.closes);

    Pause pause;
    fake.waitPause = &pause;
    bool canceled = false;
    std::thread waitThread([&] {
        FakeIOKit::current = &fake;
        canceled = waiter->wait(waiter, &computeHandle, 1, INT64_MAX, 0, nullptr) == -1 && errno == ECANCELED;
    });
    pause.wait();
    std::thread closeThread([&] {
        FakeIOKit::current = &fake;
        drm_drop(secondary);
    });
    timespec now{};
    CHECK(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    const int64_t deadline = (now.tv_sec + 2) * 1000000000ll + now.tv_nsec;
    CHECK(observer->wait(observer, &unsubmitted, 1, deadline, 0, nullptr) == -1 && errno == ECANCELED);
    CHECK(!fake.closes);
    acd_device_handle replacement = nullptr;
    CHECK(acd_device_initialize_exact_iokit(&extra, &major, &minor, &replacement) == -EBUSY && extra == 0x106 && !replacement);
    fake.bridge.device.setFence(0, compute);
    pause.release();
    waitThread.join();
    closeThread.join();
    CHECK(canceled && fake.closes == 1);
    CHECK(waiter->wait(waiter, &gfxHandle, 1, 0, 0, nullptr) == -1 && errno == ECANCELED);
    CHECK(acd_device_initialize_exact_iokit(nullptr, &major, &minor, &replacement) == -ENODEV && !replacement);
    waiter->finalize(waiter);
    observer->finalize(observer);
}

static void drm_initial_clone_failure() {
    reset();
    FakeIOKit fake;
    fake.drm = true;
    fake.failAllocation = 8;
    acd_device_handle device = nullptr;
    uint32_t major = UINT32_MAX, minor = UINT32_MAX;
    CHECK(acd_device_initialize_exact_iokit(&fake.port, &major, &minor, &device) == -ENOMEM);
    CHECK(!device && fake.port == MACH_PORT_NULL && fake.closes == 1 && major == UINT32_MAX && minor == UINT32_MAX);
    CHECK(fake.helloCalls == 2 && fake.bridge.sessions == 1 && !fake.bridge.submits);
    CHECK(acd_device_initialize_exact_iokit(nullptr, &major, &minor, &device) == -ENODEV && !device);
}
#endif

int main() {
    paired_round_trip();
    full_receipts();
    uncertain_replies();
    sequence_modes();
    checked_progress();
    invalid_progress();
    zero_and_queue_loss();
#ifdef PHX34_TEST_IOKIT
    iokit_adoption();
    iokit_adoption_errors();
#endif
#ifdef PHX34_TEST_DRM
    unsetenv("RADV_DARWIN_MOCK");
    unsetenv("RADV_DARWIN_HOST_BO");
    drm_publish_and_drain();
    drm_initial_clone_failure();
#endif
    std::printf("PASS staged Mesa/native wire: %llu checks; GPU_executed=false\n",
                static_cast<unsigned long long>(checks.load()));
}
