"""Stage a deferred IH hint consumer without reading, claiming or programming IH."""

from build34_exact_event_wait import AVAILABLE, INVALIDATE, NOTIFY, WAKE_INVALIDATED
from build34_exact_open import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

ADMIT = 'bool PhxBringup::exactIHIngressAdmitted('
OPEN = 'bool PhxBringup::openExactIHRoute('
CLOSE = 'void PhxBringup::closeExactIHRouteLocked('
LOSE = 'bool PhxBringup::loseExactIHRoute('
MATCH = 'bool PhxBringup::exactIHRouteMatches('
DELIVER = 'int PhxBringup::notifyExactIHLocked('
CURSOR = 'bool PhxBringup::validExactIHCursor('
LIVE = 'bool PhxBringup::exactIHRouteLiveLocked('
COLLECT = 'int PhxBringup::collectExactIH('
WORKER_DRAIN = 'bool PhxBringup::exactIHWorkerDrainedLocked('
ACTIVATE = 'bool PhxBringup::activateExactIHRoute('
SIGNAL = 'bool PhxBringup::signalExactIH('

TOKEN = '''    struct ExactIHRoute {
        uint64_t service, epoch, generation[2];
    };
'''
DECLARATIONS = TOKEN + '''    ExactIHRoute exactIHRoute{};
    static constexpr uint32_t kExactIHEntryBytes = 32;
    static constexpr uint32_t kExactIHBatchEntries = 32;
    struct ExactIHBatch {
        uint64_t ordinal;
        uint32_t read, before, after, count;
        uint8_t entries[kExactIHBatchEntries][kExactIHEntryBytes];
    };
    enum ExactIHRejection : int { kExactIHStale = -1, kExactIHInvalid = -2, kExactIHBusy = -3, kExactIHIdle = -4 };
    enum class ExactIHState : uint8_t { Empty, Arming, Active, Retiring, Lost };
    ExactIHState exactIHState{ExactIHState::Empty};
    enum ExactIHSignal : uint32_t {
        kIHPublished = 1, kIHEnabled = 2, kIHPending = 4, kIHClosed = 8, kIHCollecting = 16
    };
    static_assert(__atomic_always_lock_free(sizeof(uint32_t), nullptr), "IH signal path requires lock-free atomics");
    alignas(uint32_t) uint32_t exactIHSignals{0};
    phx34_exact::CallbackGate<1> exactIHWorker;
    uint32_t exactIHRingSize{0}, exactIHNext{0};
    uint64_t exactIHBatchOrdinal{0};
    uint64_t exactIHLastEpoch{0};
    bool exactIHIngressAdmitted() const;
    static bool validExactIHCursor(uint32_t, uint32_t);
    bool openExactIHRoute(ExactIHRoute &, uint32_t ringSize, uint32_t cursor);
    bool activateExactIHRoute(const ExactIHRoute &, bool &kick);
    bool signalExactIH(const ExactIHRoute &);
    bool exactIHRouteMatches(const ExactIHRoute &) const;
    bool exactIHRouteLiveLocked(const ExactIHRoute &) const;
    void closeExactIHRouteLocked();
    bool loseExactIHRoute(const ExactIHRoute &);
    bool exactIHWorkerDrainedLocked(const ExactIHRoute &) const;
    int collectExactIH(const ExactIHRoute &, bool (*capture)(void *, ExactIHBatch &), void *, bool &kick);
    int notifyExactIHLocked(const ExactIHRoute &, const ExactIHBatch &);
'''
METHODS = '''bool PhxBringup::exactIHIngressAdmitted() const {
    return false;
}

bool PhxBringup::validExactIHCursor(uint32_t cursor, uint32_t size) {
    return cursor < size && cursor % kExactIHEntryBytes == 0;
}

bool PhxBringup::openExactIHRoute(ExactIHRoute &out, uint32_t ringSize, uint32_t cursor) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    if (ringSize < 2 * kExactIHEntryBytes || ringSize > (1u << 18) ||
        (ringSize & (ringSize - 1)) || !validExactIHCursor(cursor, ringSize)) return false;
    const uint64_t service = getRegistryEntryID();
    if (!service || service == UINT64_MAX) return false;
    IOLockLock(gpuLock);
    const bool ready = exactIHIngressAdmitted() && !exactCallbacks.closed() && !exactStopped && !isSleeping &&
        exactIHState == ExactIHState::Empty && exactIHLastEpoch < UINT64_MAX - 1 &&
        exactEventOps && exactEventOps->sleep && exactEventOps->wake && exactEventOps->queues == 3 &&
        exactQueueLive[0] && exactQueueLive[1] && exactQueueGeneration[0] && exactQueueGeneration[1] &&
        exactQueueGeneration[0] < UINT64_MAX - 1 && exactQueueGeneration[1] < UINT64_MAX - 1 &&
        exactEventSerial[0] < UINT64_MAX && exactEventSerial[1] < UINT64_MAX;
    if (ready) {
        exactIHRoute = {service, ++exactIHLastEpoch, {exactQueueGeneration[0], exactQueueGeneration[1]}};
        exactIHRingSize = ringSize;
        exactIHNext = cursor;
        exactIHState = ExactIHState::Arming;
        out = exactIHRoute;
        __atomic_store_n(&exactIHSignals, kIHPublished, __ATOMIC_RELEASE);
    }
    IOLockUnlock(gpuLock);
    return ready;
}

bool PhxBringup::exactIHRouteMatches(const ExactIHRoute &route) const {
    return exactIHRoute.epoch && route.epoch == exactIHRoute.epoch && route.service == exactIHRoute.service &&
        route.generation[0] == exactIHRoute.generation[0] && route.generation[1] == exactIHRoute.generation[1];
}

bool PhxBringup::activateExactIHRoute(const ExactIHRoute &route, bool &kick) {
    kick = false;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    IOLockLock(gpuLock);
    const bool ready = exactIHState == ExactIHState::Arming && exactIHRouteMatches(route) &&
        !exactCallbacks.closed() && !exactStopped && !isSleeping && exactQueueLive[0] && exactQueueLive[1] &&
        route.generation[0] == exactQueueGeneration[0] && route.generation[1] == exactQueueGeneration[1];
    if (ready) {
        exactIHState = ExactIHState::Active;
        kick = (__atomic_fetch_or(&exactIHSignals, kIHEnabled, __ATOMIC_ACQ_REL) & kIHPending) != 0;
    }
    IOLockUnlock(gpuLock);
    return ready;
}

bool PhxBringup::signalExactIH(const ExactIHRoute &route) {
    const uint32_t observed = __atomic_load_n(&exactIHSignals, __ATOMIC_ACQUIRE);
    if ((observed & (kIHPublished | kIHClosed)) != kIHPublished || exactCallbacks.closed() ||
        !exactIHRouteMatches(route)) return false;
    const uint32_t previous = __atomic_fetch_or(&exactIHSignals, kIHPending, __ATOMIC_ACQ_REL);
    return (previous & (kIHEnabled | kIHPending | kIHClosed | kIHCollecting)) == kIHEnabled;
}

bool PhxBringup::exactIHRouteLiveLocked(const ExactIHRoute &route) const {
    return exactIHRouteMatches(route) && exactIHState == ExactIHState::Active &&
        !exactCallbacks.closed() && !exactStopped && !isSleeping && exactQueueLive[0] && exactQueueLive[1] &&
        route.generation[0] == exactQueueGeneration[0] && route.generation[1] == exactQueueGeneration[1];
}

void PhxBringup::closeExactIHRouteLocked() {
    if (exactIHState != ExactIHState::Arming && exactIHState != ExactIHState::Active) return;
    __atomic_fetch_or(&exactIHSignals, kIHClosed, __ATOMIC_ACQ_REL);
    exactIHWorker.close();
    exactIHState = ExactIHState::Retiring;
    for (uint32_t queue = 0; queue < 2; ++queue) {
        if (exactEventSerial[queue] < UINT64_MAX) ++exactEventSerial[queue];
        exactEventOps->wake(gpuLock, &exactEventSerial[queue]);
    }
}

bool PhxBringup::loseExactIHRoute(const ExactIHRoute &route) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    IOLockLock(gpuLock);
    const bool current = (exactIHState == ExactIHState::Arming || exactIHState == ExactIHState::Active ||
        exactIHState == ExactIHState::Retiring) && exactIHRouteMatches(route);
    if (current) {
        closeExactIHRouteLocked();
        exactIHState = ExactIHState::Lost;
    }
    IOLockUnlock(gpuLock);
    return current;
}

bool PhxBringup::exactIHWorkerDrainedLocked(const ExactIHRoute &route) const {
    return exactIHRouteMatches(route) && exactIHWorker.drained();
}

int PhxBringup::collectExactIH(const ExactIHRoute &route, bool (*capture)(void *, ExactIHBatch &), void *context,
                              bool &kick) {
    kick = false;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock || !capture) return kExactIHStale;
    IOLockLock(gpuLock);
    if (!exactIHRouteLiveLocked(route)) {
        IOLockUnlock(gpuLock);
        return kExactIHStale;
    }
    int result = kExactIHIdle;
    {
        decltype(exactIHWorker)::Lease worker(exactIHWorker);
        if (!worker) {
            IOLockUnlock(gpuLock);
            return kExactIHBusy;
        }
        __atomic_fetch_or(&exactIHSignals, kIHCollecting, __ATOMIC_ACQ_REL);
        if (__atomic_fetch_and(&exactIHSignals, ~kIHPending, __ATOMIC_ACQ_REL) & kIHPending) {
            IOLockUnlock(gpuLock);
            ExactIHBatch batch{};
            const bool copied = capture(context, batch);
            IOLockLock(gpuLock);
            result = kExactIHStale;
            if (exactIHRouteLiveLocked(route)) {
                if (copied) {
                    result = notifyExactIHLocked(route, batch);
                    if (result >= 0 && exactIHNext != batch.before)
                        __atomic_fetch_or(&exactIHSignals, kIHPending, __ATOMIC_ACQ_REL);
                } else {
                    closeExactIHRouteLocked();
                    exactIHState = ExactIHState::Lost;
                    result = kExactIHInvalid;
                }
            }
        }
    }
    const uint32_t previous = __atomic_fetch_and(&exactIHSignals, ~kIHCollecting, __ATOMIC_ACQ_REL);
    kick = (previous & (kIHPending | kIHClosed)) == kIHPending && exactIHRouteLiveLocked(route);
    IOLockUnlock(gpuLock);
    return result;
}

int PhxBringup::notifyExactIHLocked(const ExactIHRoute &route, const ExactIHBatch &batch) {
    const uint32_t distance = (batch.before - batch.read) & (exactIHRingSize - 1);
    const uint32_t available = distance / kExactIHEntryBytes;
    const uint32_t expected = available < kExactIHBatchEntries ? available : kExactIHBatchEntries;
    if (batch.ordinal != exactIHBatchOrdinal + 1 || batch.ordinal == UINT64_MAX ||
        batch.read != exactIHNext || batch.before != batch.after || !validExactIHCursor(batch.before, exactIHRingSize) ||
        batch.count != expected) {
        closeExactIHRouteLocked();
        exactIHState = ExactIHState::Lost;
        return kExactIHInvalid;
    }
    exactIHNext = (batch.read + batch.count * kExactIHEntryBytes) & (exactIHRingSize - 1);
    exactIHBatchOrdinal = batch.ordinal;
    int queueMask = 0;
    for (uint32_t index = 0; index < batch.count; ++index) {
        const auto &vector = batch.entries[index];
        if (vector[0] != 0x14 || vector[1] != 0xB5 || (vector[19] & 1)) continue;
        const uint32_t ring = vector[2] & 0x7F;
        if (ring != 0x00 && ring != 0x04) continue;
        const uint32_t queue = ring == 0x04 ? 0 : 1;
        const int bit = 1 << queue;
        if (!(queueMask & bit) && exactEventAvailable(queue, route.generation[queue])) {
            ++exactEventSerial[queue];
            exactEventOps->wake(gpuLock, &exactEventSerial[queue]);
            queueMask |= bit;
        }
    }
    return queueMask;
}

'''


def stage(source):
    source = previous_stage(source)
    declaration = '    bool notifyExactEvent(uint32_t queue, uint64_t generation); // deferred context only\n'
    source = once(source, declaration, DECLARATIONS)
    source = once(source, method(source, NOTIFY) + '\n', METHODS)
    available = method(source, AVAILABLE)
    source = once(source, available, once(available, 'return queue < 2 && exactEventOps',
                  '''return queue < 2 && exactIHState == ExactIHState::Active &&
           exactQueueLive[0] && exactQueueLive[1] &&
           exactIHRoute.generation[0] == exactQueueGeneration[0] &&
           exactIHRoute.generation[1] == exactQueueGeneration[1] && exactEventOps'''))
    invalidate = method(source, INVALIDATE)
    updated = once(invalidate, INVALIDATE + ' {\n', INVALIDATE + ' {\n    closeExactIHRouteLocked();\n')
    return once(source, invalidate, once(updated, WAKE_INVALIDATED, ''))
