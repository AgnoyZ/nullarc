"""Stage a retained providerless workloop source; native IH admission stays closed."""

from build34_exact_event_wait import ENTRY, WAIT
from build34_exact_ih_ingress import CLOSE, stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

ANCHOR = 'OSDefineMetaClassAndStructors(PhxBringup, IOService)\n'
STOP = 'void PhxBringup::stop('
STOP_ADMISSION = '    if (!exactCallbacks.close()) return;\n'
ROUTE_ADMISSION = '    __atomic_fetch_or(&exactIHSignals, kIHClosed, __ATOMIC_ACQ_REL);\n'
CLOSE_WORK = '    closeExactIHWorkAdmission();\n'
POLL = 'void PhxBringup::pauseExactPoll('
POLL_DECL = '''    void pauseExactPoll(const phx34_exact::Receipt &, const phx34_exact::CallbackGate<> &,
                        uint64_t start, uint64_t timeout);
'''
POLL_AT = 'void PhxBringup::sleepExactIOKit('
POLL_METHOD = '''void PhxBringup::pauseExactPoll(const phx34_exact::Receipt &receipt,
                               const phx34_exact::CallbackGate<> &client, uint64_t start, uint64_t timeout) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return;
    IOLockLock(gpuLock);
    if (!client.closed() && !exactCallbacks.closed() && !exactStopped && !isSleeping &&
        receipt.queue < 2 && exactQueueLive[receipt.queue] &&
        exactQueueGeneration[receipt.queue] == receipt.generation) {
        const uint64_t now = mach_absolute_time();
        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(now - start, &elapsed);
        if (elapsed < timeout) {
            const uint64_t remaining = timeout - elapsed;
            const uint64_t slice = remaining < 1000000 ? remaining : 1000000;
            uint64_t ticks = 0;
            nanoseconds_to_absolutetime(slice, &ticks);
            if (ticks && ticks <= UINT64_MAX - now) {
                uint64_t deadline = now + ticks;
                if (mach_absolute_time() < deadline)
                    (void)IOLockSleepDeadline(gpuLock, &deadline, deadline, THREAD_UNINT);
            }
        }
    }
    IOLockUnlock(gpuLock);
}

'''
PRIOR_POLL = '            IOSleep(1);\n'
BOUNDED_POLL = '            owner->pauseExactPoll(receipt, exactClientCallbacks, start, timeout);\n'
PREPARE_ENTRY = '    if (!gpu || !capture || !captureOwner || !gpu->exactIHIngressAdmitted()) return nullptr;\n'
PREPARE_LEASE = '''    if (!gpu || !capture || !captureOwner) return nullptr;
    phx34_exact::CallbackGate<>::Lease preparing(gpu->exactCallbacks);
    if (!preparing || !gpu->exactIHIngressAdmitted()) return nullptr;
'''
PREPARE_PUBLISH = '    source->setAttachment(Attachment::Attached);\n    return source;\n'
PREPARE_CHECKED_PUBLISH = '''    source->setAttachment(Attachment::Attached);
    if (gpu->exactCallbacks.closed() || !source->accepting()) {
        source->closeAdmission();
        if (source->detach() == kIOReturnBusy) source->setAttachment(Attachment::Held);
        source->release();
        return nullptr;
    }
    return source;
'''
ADMISSION_FIELDS = '''    friend class PhxExactIHWorkSource;
    static constexpr uint64_t kExactIHKickClosed = 1ull << 63;
    static_assert(__atomic_always_lock_free(sizeof(uint64_t), nullptr), "IH kick admission requires lock-free atomics");
    alignas(uint64_t) uint64_t exactIHKicks{0};
    phx34_exact::CallbackGate<1> exactIHTurns;
    void closeExactIHWorkAdmission() {
        __atomic_fetch_or(&exactIHKicks, kExactIHKickClosed, __ATOMIC_ACQ_REL);
        exactIHTurns.close();
    }
'''
SOURCE = '''
class PhxExactIHWorkSource final : public IOEventSource {
    OSDeclareDefaultStructors(PhxExactIHWorkSource)
public:
    using Capture = bool (*)(void *, PhxBringup::ExactIHBatch &);
    static PhxExactIHWorkSource *prepare(PhxBringup *, uint32_t, uint32_t, Capture, OSObject *);
    bool activate();
    void hint();
    void closeAdmission();
    IOReturn detach();

protected:
    bool checkForWork() override;
    void free() override;

private:
    enum class Attachment : uint32_t { Preparing, Attached, Removing, Detached, Held };
    Attachment attachment{Attachment::Preparing};
    static constexpr uint64_t kKickClosed = PhxBringup::kExactIHKickClosed;
    PhxBringup *gpu{nullptr};
    IOWorkLoop *loop{nullptr};
    OSObject *captureOwner{nullptr};
    Capture capture{nullptr};
    PhxBringup::ExactIHRoute route{};
    bool accepting() const;
    void kick();
    void setAttachment(Attachment state) { __atomic_store(&attachment, &state, __ATOMIC_RELEASE); }
    Attachment getAttachment() const {
        Attachment state;
        __atomic_load(&attachment, &state, __ATOMIC_ACQUIRE);
        return state;
    }
};

OSDefineMetaClassAndStructors(PhxExactIHWorkSource, IOEventSource)

PhxExactIHWorkSource *PhxExactIHWorkSource::prepare(PhxBringup *gpu, uint32_t ringSize, uint32_t cursor,
                                                  Capture capture, OSObject *captureOwner) {
    if (!gpu || !capture || !captureOwner || !gpu->exactIHIngressAdmitted()) return nullptr;
    auto *source = new PhxExactIHWorkSource;
    if (!source) return nullptr;
    if (!source->init(gpu)) {
        source->release();
        return nullptr;
    }
    gpu->retain();
    captureOwner->retain();
    source->gpu = gpu;
    source->captureOwner = captureOwner;
    source->capture = capture;
    source->loop = IOWorkLoop::workLoop();
    if (!source->loop || !gpu->openExactIHRoute(source->route, ringSize, cursor)) {
        source->release();
        return nullptr;
    }
    source->retain();
    const IOReturn attached = source->loop->addEventSource(source);
    if (attached != kIOReturnSuccess || source->getWorkLoop() != source->loop) {
        source->closeAdmission();
        gpu->loseExactIHRoute(source->route);
        if (attached != kIOReturnSuccess && !source->getWorkLoop()) source->release();
        else source->setAttachment(Attachment::Held);
        source->release();
        return nullptr;
    }
    source->setAttachment(Attachment::Attached);
    return source;
}

bool PhxExactIHWorkSource::accepting() const {
    return getAttachment() == Attachment::Attached &&
        !(__atomic_load_n(&gpu->exactIHKicks, __ATOMIC_ACQUIRE) & kKickClosed);
}

void PhxExactIHWorkSource::kick() {
    const uint64_t earlier = __atomic_fetch_add(&gpu->exactIHKicks, 1, __ATOMIC_ACQ_REL);
    if (!(earlier & kKickClosed)) signalWorkAvailable();
    __atomic_fetch_sub(&gpu->exactIHKicks, 1, __ATOMIC_ACQ_REL);
}

bool PhxExactIHWorkSource::activate() {
    bool wake = false;
    if (!accepting() || !gpu->activateExactIHRoute(route, wake)) return false;
    if (wake) kick();
    return accepting();
}

void PhxExactIHWorkSource::hint() {
    if (accepting() && gpu->signalExactIH(route)) kick();
}

void PhxExactIHWorkSource::closeAdmission() {
    gpu->closeExactIHWorkAdmission();
}

bool PhxExactIHWorkSource::checkForWork() {
    decltype(gpu->exactIHTurns)::Lease turn(gpu->exactIHTurns);
    if (turn && accepting()) {
        bool wake = false;
        gpu->collectExactIH(route, capture, captureOwner, wake);
        if (wake) kick();
    }
    return false;
}

IOReturn PhxExactIHWorkSource::detach() {
    if (loop->onThread() || loop->inGate()) return kIOReturnNotPermitted;
    if (__atomic_load_n(&gpu->exactIHKicks, __ATOMIC_ACQUIRE) != kKickClosed) return kIOReturnBusy;
    Attachment attached = Attachment::Attached, removing = Attachment::Removing;
    if (!__atomic_compare_exchange(&attachment, &attached, &removing, false,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return kIOReturnNotReady;
    gpu->loseExactIHRoute(route);
    if (!gpu->exactIHTurns.drained()) {
        setAttachment(Attachment::Attached);
        return kIOReturnBusy;
    }
    const IOReturn removed = getWorkLoop() == loop ? loop->removeEventSource(this) : kIOReturnNotAttached;
    const bool detached = removed == kIOReturnSuccess && !getWorkLoop();
    setAttachment(detached ? Attachment::Detached : Attachment::Held);
    if (detached) release();
    return detached ? kIOReturnSuccess : removed == kIOReturnSuccess ? kIOReturnNotReady : removed;
}

void PhxExactIHWorkSource::free() {
    if (loop) loop->release();
    if (captureOwner) captureOwner->release();
    if (gpu) gpu->release();
    IOEventSource::free();
}
'''

PROVIDER_ADMISSION_FIELDS = once(
    ADMISSION_FIELDS, '    void closeExactIHWorkAdmission() {\n',
    '    phx34_exact::CallbackGate<1> exactIHProviderCalls;\n'
    '    void closeExactIHWorkAdmission() {\n'
    '        exactIHProviderCalls.close();\n',
)
PROVIDER_INTERFACE = '''    struct ProviderRetirement { IOReturn status; bool callbacksDrained; };
    struct ProviderOps {
        IOReturn (*registerTarget)(OSObject *, PhxExactIHWorkSource *);
        IOReturn (*enableTarget)(OSObject *, PhxExactIHWorkSource *);
        ProviderRetirement (*unregisterAndDrain)(OSObject *, PhxExactIHWorkSource *);
    };
    bool armProvider(ProviderOps, OSObject *);
    IOReturn retireProvider();
'''
PROVIDER_STATE = '''    enum class Provider : uint32_t { Unbound, Arming, Attempted, Retiring, Retired, Held };
    Provider providerState{Provider::Unbound};
    OSObject *providerOwner{nullptr};
    decltype(ProviderOps::unregisterAndDrain) unregisterAndDrain{nullptr};
    bool claimProvider(Provider expected, Provider desired) {
        return __atomic_compare_exchange(&providerState, &expected, &desired, false,
                                         __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
    }
    void setProvider(Provider state) { __atomic_store(&providerState, &state, __ATOMIC_RELEASE); }
    Provider getProvider() const {
        Provider state;
        __atomic_load(&providerState, &state, __ATOMIC_ACQUIRE);
        return state;
    }
'''
PROVIDER_METHODS = '''bool PhxExactIHWorkSource::armProvider(ProviderOps ops, OSObject *context) {
    if (!context || !ops.registerTarget || !ops.enableTarget || !ops.unregisterAndDrain ||
        loop->onThread() || loop->inGate()) return false;
    phx34_exact::CallbackGate<>::Lease callback(gpu->exactCallbacks);
    if (!callback || !accepting() || !claimProvider(Provider::Unbound, Provider::Arming)) return false;
    IOReturn registered;
    using ProviderLease = decltype(gpu->exactIHProviderCalls)::Lease;
    {
        ProviderLease registering(gpu->exactIHProviderCalls);
        if (!registering || gpu->exactCallbacks.closed() || !accepting()) {
            setProvider(Provider::Retired);
            return false;
        }
        retain();
        context->retain();
        providerOwner = context;
        unregisterAndDrain = ops.unregisterAndDrain;
        registered = ops.registerTarget(context, this);
    }
    bool enabled = false;
    if (registered == kIOReturnSuccess) {
        ProviderLease enabling(gpu->exactIHProviderCalls);
        if (enabling && !gpu->exactCallbacks.closed() && accepting())
            enabled = ops.enableTarget(context, this) == kIOReturnSuccess;
    }
    const bool active = enabled && activate();
    if (!active) {
        closeAdmission();
        gpu->loseExactIHRoute(route);
    }
    setProvider(Provider::Attempted);
    return active && accepting();
}

IOReturn PhxExactIHWorkSource::retireProvider() {
    if (loop->onThread() || loop->inGate()) return kIOReturnNotPermitted;
    if (!gpu->exactIHProviderCalls.drained() || !gpu->exactIHTurns.closed()) return kIOReturnBusy;
    if (!claimProvider(Provider::Attempted, Provider::Retiring)) {
        const auto state = getProvider();
        return state == Provider::Arming || state == Provider::Retiring ? kIOReturnBusy : kIOReturnNotReady;
    }
    const ProviderRetirement retired = unregisterAndDrain(providerOwner, this);
    if (retired.status != kIOReturnSuccess || !retired.callbacksDrained) {
        setProvider(Provider::Held);
        return retired.status == kIOReturnSuccess ? kIOReturnNotReady : retired.status;
    }
    providerOwner->release();
    providerOwner = nullptr;
    unregisterAndDrain = nullptr;
    setProvider(Provider::Retired);
    release();
    return kIOReturnSuccess;
}

'''
PROVIDER_DETACH_CHECK = '''    const auto provider = getProvider();
    if (provider != Provider::Unbound && provider != Provider::Retired) return kIOReturnBusy;
'''


def stage_lifecycle(source):
    source = previous_stage(source)
    source = once(source, '#include <IOKit/IOWorkLoop.h>\n',
                  '#include <IOKit/IOWorkLoop.h>\n#include <IOKit/IOEventSource.h>\n')
    source = once(source, '    struct ExactIHRoute {\n',
                  ADMISSION_FIELDS + '    struct ExactIHRoute {\n')
    for signature, anchor in ((STOP, STOP_ADMISSION), (CLOSE, ROUTE_ADMISSION)):
        old = method(source, signature)
        source = once(source, old, once(old, anchor, anchor + CLOSE_WORK))
    return once(source, ANCHOR, ANCHOR + SOURCE)


def stage_bounded_poll(source):
    source = stage_lifecycle(source)
    source = once(source, ENTRY, ENTRY + POLL_DECL)
    source = once(source, POLL_AT, POLL_METHOD + POLL_AT)
    wait = method(source, WAIT)
    return once(source, wait, once(wait, PRIOR_POLL, BOUNDED_POLL))


def checked_adapter(adapter):
    return once(once(adapter, PREPARE_ENTRY, PREPARE_LEASE), PREPARE_PUBLISH, PREPARE_CHECKED_PUBLISH)


def stage(source):
    return once(stage_bounded_poll(source), SOURCE, checked_adapter(SOURCE))


def provider_adapter(adapter):
    adapter = once(adapter, '    bool activate();\n', '')
    adapter = once(adapter, '    IOReturn detach();\n', PROVIDER_INTERFACE + '    IOReturn detach();\n')
    adapter = once(adapter, '    Attachment attachment{Attachment::Preparing};\n',
                   '    Attachment attachment{Attachment::Preparing};\n    bool activate();\n' + PROVIDER_STATE)
    adapter = once(adapter, 'IOReturn PhxExactIHWorkSource::detach() {\n',
                   PROVIDER_METHODS + 'IOReturn PhxExactIHWorkSource::detach() {\n')
    return once(adapter, '    Attachment attached = Attachment::Attached, removing = Attachment::Removing;\n',
                PROVIDER_DETACH_CHECK +
                '    Attachment attached = Attachment::Attached, removing = Attachment::Removing;\n')


def stage_provider(source):
    adapter = checked_adapter(SOURCE)
    return once(once(stage(source), ADMISSION_FIELDS, PROVIDER_ADMISSION_FIELDS),
                adapter, provider_adapter(adapter))
