"""Stage a deferred IH hint consumer without reading, claiming or programming IH."""

from build34_exact_event_wait import AVAILABLE, INVALIDATE, NOTIFY, WAKE_INVALIDATED
from build34_exact_open import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

ADMIT = 'bool PhxBringup::exactIHIngressAdmitted('
OPEN = 'bool PhxBringup::openExactIHRoute('
CLOSE = 'void PhxBringup::closeExactIHRouteLocked('
LOSE = 'bool PhxBringup::loseExactIHRoute('
MATCH = 'bool PhxBringup::exactIHRouteMatchesLocked('
DELIVER = 'bool PhxBringup::notifyExactIH('

TOKEN = '''    struct ExactIHRoute {
        uint64_t service, epoch, generation[2];
    };
'''
DECLARATIONS = TOKEN + '''    ExactIHRoute exactIHRoute{};
    uint64_t exactIHLastEpoch{0};
    bool exactIHUncertain{false};
    bool exactIHIngressAdmitted() const;
    bool openExactIHRoute(ExactIHRoute &);
    bool exactIHRouteMatchesLocked(const ExactIHRoute &) const;
    void closeExactIHRouteLocked();
    bool loseExactIHRoute(const ExactIHRoute &);
    bool notifyExactIH(const ExactIHRoute &, const uint8_t (&)[32]);
'''
METHODS = '''bool PhxBringup::exactIHIngressAdmitted() const {
    return false;
}

bool PhxBringup::openExactIHRoute(ExactIHRoute &out) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    const uint64_t service = getRegistryEntryID();
    if (!service || service == UINT64_MAX) return false;
    IOLockLock(gpuLock);
    const bool ready = exactIHIngressAdmitted() && !exactCallbacks.closed() && !exactStopped && !isSleeping && !exactIHUncertain &&
        !exactIHRoute.epoch && exactIHLastEpoch < UINT64_MAX - 1 &&
        exactEventOps && exactEventOps->sleep && exactEventOps->wake && exactEventOps->queues == 3 &&
        exactQueueLive[0] && exactQueueLive[1] && exactQueueGeneration[0] && exactQueueGeneration[1] &&
        exactQueueGeneration[0] < UINT64_MAX - 1 && exactQueueGeneration[1] < UINT64_MAX - 1 &&
        exactEventSerial[0] < UINT64_MAX && exactEventSerial[1] < UINT64_MAX;
    if (ready) {
        exactIHRoute = {service, ++exactIHLastEpoch, {exactQueueGeneration[0], exactQueueGeneration[1]}};
        out = exactIHRoute;
    }
    IOLockUnlock(gpuLock);
    return ready;
}

bool PhxBringup::exactIHRouteMatchesLocked(const ExactIHRoute &route) const {
    return exactIHRoute.epoch && route.epoch == exactIHRoute.epoch && route.service == exactIHRoute.service &&
        route.generation[0] == exactIHRoute.generation[0] && route.generation[1] == exactIHRoute.generation[1];
}

void PhxBringup::closeExactIHRouteLocked() {
    if (!exactIHRoute.epoch) return;
    exactIHRoute = {};
    for (uint32_t queue = 0; queue < 2; ++queue) {
        if (exactEventSerial[queue] < UINT64_MAX) ++exactEventSerial[queue];
        exactEventOps->wake(gpuLock, &exactEventSerial[queue]);
    }
}

bool PhxBringup::loseExactIHRoute(const ExactIHRoute &route) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    IOLockLock(gpuLock);
    const bool current = exactIHRouteMatchesLocked(route);
    if (current) {
        exactIHUncertain = true;
        closeExactIHRouteLocked();
    }
    IOLockUnlock(gpuLock);
    return current;
}

bool PhxBringup::notifyExactIH(const ExactIHRoute &route, const uint8_t (&vector)[32]) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    if (vector[0] != 0x14 || vector[1] != 0xB5 || (vector[19] & 1)) return false;
    const uint32_t ring = vector[2] & 0x7F;
    if (ring != 0x00 && ring != 0x04) return false;
    const uint32_t queue = ring == 0x04 ? 0 : 1;
    IOLockLock(gpuLock);
    const bool live = exactIHRouteMatchesLocked(route) && exactEventAvailable(queue, route.generation[queue]);
    if (live) {
        ++exactEventSerial[queue];
        exactEventOps->wake(gpuLock, &exactEventSerial[queue]);
    }
    IOLockUnlock(gpuLock);
    return live;
}

'''


def stage(source):
    source = previous_stage(source)
    declaration = '    bool notifyExactEvent(uint32_t queue, uint64_t generation); // deferred context only\n'
    source = once(source, declaration, DECLARATIONS)
    source = once(source, method(source, NOTIFY) + '\n', METHODS)
    available = method(source, AVAILABLE)
    source = once(source, available, once(available, 'return queue < 2 && exactEventOps',
                  '''return queue < 2 && exactIHRoute.epoch &&
           exactQueueLive[0] && exactQueueLive[1] &&
           exactIHRoute.generation[0] == exactQueueGeneration[0] &&
           exactIHRoute.generation[1] == exactQueueGeneration[1] && exactEventOps'''))
    invalidate = method(source, INVALIDATE)
    updated = once(invalidate, INVALIDATE + ' {\n', INVALIDATE + ' {\n    closeExactIHRouteLocked();\n')
    return once(source, invalidate, once(updated, WAKE_INVALIDATED, ''))
