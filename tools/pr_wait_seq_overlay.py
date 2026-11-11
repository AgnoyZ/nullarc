"""Reviewed test-only overlay for the pinned upstream wait-sequence model."""
from contextlib import contextmanager
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '4839215157e2c904b0b27b75ef2f57c07b38db0cd680c4da580fca7fec45654d'


def transform(data):
    source = data.decode('utf-8').replace('\r\n', '\n')
    if hashlib.sha256(source.encode()).hexdigest() != EXPECTED:
        raise RuntimeError('Unreviewed upstream wait-sequence source; refusing overlay')
    changes = [
        ('static void mock_delay(uint32_t us) {', '''// Downstream test-only virtual clock. The upstream engine below stays unchanged.
static uint64_t g_virtual_ns, g_retire_at, g_retire_value;
static std::atomic<uint64_t> *g_retire_target;
static void advance(uint64_t ns) {
    g_virtual_ns += ns;
    if (g_retire_target && g_virtual_ns >= g_retire_at) {
        g_retire_target->store(g_retire_value, std::memory_order_release);
        g_retire_target = nullptr;
    }
}
static void schedule(std::atomic<uint64_t> &target, uint64_t at, uint64_t value) {
    g_virtual_ns = 0; g_retire_target = &target; g_retire_at = at; g_retire_value = value;
}
static void mock_delay(uint32_t us) {''', 1),
        ('std::this_thread::sleep_for(std::chrono::microseconds(us));', 'advance(uint64_t(us) * 1000);', 1),
        ('std::this_thread::sleep_for(std::chrono::milliseconds(ms));', 'advance(uint64_t(ms) * 1000000);', 1),
        ('''    // Simulate async retirement after 200 microseconds
    std::thread t([&eng]() {
        std::this_thread::sleep_for(std::chrono::microseconds(200));
        eng.retired.store(10, std::memory_order_release);
    });''', '    schedule(eng.retired, 200000, 10); // four virtual 50us polls', 1),
        ('''    // Simulate async retirement after 3 milliseconds
    std::thread t([&eng]() {
        std::this_thread::sleep_for(std::chrono::milliseconds(3));
        eng.retired.store(20, std::memory_order_release);
    });''', '    schedule(eng.retired, 3000000, 20); // 1ms polling + two 1ms sleeps', 1),
        ('    t.join();\n', '', 2),
        ('    assert(g_delay_calls > 0);\n', '    assert(g_delay_calls > 0);\n    assert(g_delay_calls == 4 && g_virtual_ns == 200000);\n', 1),
        ('    assert(g_sleep_calls > 0); // adaptive sleep phase entered to prevent CPU lockup',
         '    assert(g_sleep_calls > 0); // adaptive sleep phase entered to prevent CPU lockup\n    assert(g_delay_calls == 20 && g_sleep_calls == 2 && g_virtual_ns == 3000000);', 1),
        ('''    // Request huge timeout: 100 seconds (must be clamped to PHXN_WAIT_CAP_NS = 5s)
    // For test speed, run with 2ms timeout''',
         '    // Exercise the actual ABI cap with 100s requested, without wall-clock sleeps.\n    g_virtual_ns = 0; g_retire_target = nullptr;', 1),
        ('    int r = eng.wait_seq(10, 2000000, timed_out, out_retired); // 2 ms',
         '    int r = eng.wait_seq(10, 100000000000ull, timed_out, out_retired);\n    assert(g_virtual_ns == PHXN_WAIT_CAP_NS);\n    assert(g_delay_calls == 20);\n    assert(g_sleep_calls == (PHXN_WAIT_CAP_NS - 1000000ull) / 1000000ull);', 1),
    ]
    for old, new, count in changes:
        if source.count(old) != count:
            raise RuntimeError('Upstream wait overlay no longer matches reviewed test shape')
        source = source.replace(old, new)
    return source.encode()


@contextmanager
def deterministic_wait(root):
    root = Path(root).resolve()
    if root == ROOT:
        raise RuntimeError('Wait overlay is restricted to a disposable upstream candidate')
    path = root / 'tests/test_wait_seq.cpp'
    if path.resolve().parent != root / 'tests':
        raise RuntimeError('Wait overlay path escapes candidate tests')
    original = path.read_bytes()
    changed = transform(original)
    path.write_bytes(changed)
    try:
        yield {'path': 'tests/test_wait_seq.cpp', 'kind': 'test-only-virtual-clock',
               'original_bytes_sha256': hashlib.sha256(original).hexdigest(),
               'reviewed_lf_sha256': EXPECTED, 'effective_sha256': hashlib.sha256(changed).hexdigest(),
               'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'production_sources_modified': False, 'kernel_method_executed': False}
    finally:
        if path.read_bytes() != changed:
            raise RuntimeError('Overlay changed externally; refusing to overwrite it during restoration')
        path.write_bytes(original)
