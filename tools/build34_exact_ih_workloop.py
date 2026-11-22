"""Stage a retained providerless workloop source; native IH admission stays closed."""

from build34_exact_ih_ingress import CLOSE, stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

ANCHOR = 'OSDefineMetaClassAndStructors(PhxBringup, IOService)\n'
STOP = 'void PhxBringup::stop('
STOP_ADMISSION = '    if (!exactCallbacks.close()) return;\n'
ROUTE_ADMISSION = '    __atomic_fetch_or(&exactIHSignals, kIHClosed, __ATOMIC_ACQ_REL);\n'
CLOSE_WORK = '    closeExactIHWorkAdmission();\n'
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


def stage(source):
    source = previous_stage(source)
    source = once(source, '#include <IOKit/IOWorkLoop.h>\n',
                  '#include <IOKit/IOWorkLoop.h>\n#include <IOKit/IOEventSource.h>\n')
    source = once(source, '    struct ExactIHRoute {\n',
                  ADMISSION_FIELDS + '    struct ExactIHRoute {\n')
    for signature, anchor in ((STOP, STOP_ADMISSION), (CLOSE, ROUTE_ADMISSION)):
        old = method(source, signature)
        source = once(source, old, once(old, anchor, anchor + CLOSE_WORK))
    return once(source, ANCHOR, ANCHOR + SOURCE)
