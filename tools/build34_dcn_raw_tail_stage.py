"""Pair the staged DCN adopter with a fenced Compute/GFX bootstrap tail."""

from build34_exact_bootstrap_progress import change
from build34_exact_mes_status import stage_bootstrap as previous_bootstrap
from build34_exact_submit import once


ADOPT = 'IOReturn PhxBringup::adoptQueue('
VERIFY = 'bool PhxBringup::dcnRawTailMatchesLocked('
DECLARATION = '    bool dcnRawTailMatchesLocked(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t) const;\n'
PACKET_PREFIX = '0xc0064900u, 0x06603514u, 0x40000000u'
METHOD = '''bool PhxBringup::dcnRawTailMatchesLocked(uint64_t ringOff, uint64_t ringDw, uint64_t wbOff,
    uint64_t wptr, uint64_t fenceOff) const {
    const auto live = [&] {
        return !exactCallbacks.closed() && exactRawWriters.drained() && !exactStopped && !isSleeping && !exactVMFault;
    };
    if (!live() || !fbAper || !exactDwordReader || wptr < 8 || wptr >= ringDw || ringDw > 65536 ||
        ringOff > UINT32_MAX || wbOff > UINT32_MAX || fenceOff > UINT32_MAX ||
        fbMcBase > UINT64_MAX - fenceOff) return false;
    const uint64_t bytes = fbAper->getLength();
    const uintptr_t base = fbAper->getVirtualAddress();
    if (!base || (base & 3)) return false;
    const auto read = [&](uint64_t offset, uint32_t &word) {
        return !(offset & 3) && offset <= UINTPTR_MAX - base && offset <= fbAperLen && fbAperLen - offset >= 4 &&
            offset <= bytes && bytes - offset >= 4 && live() &&
            exactDwordReader(reinterpret_cast<const volatile uint32_t *>(base + offset), &word);
    };
    const auto atTail = [&] {
        uint32_t low = 0, high = 0;
        return read(wbOff + 16, low) && read(wbOff + 20, high) && low == wptr && !high;
    };
    if (!atTail()) return false;
    const uint64_t tail = ringOff + (wptr - 8) * 4, address = fbMcBase + fenceOff;
    const uint32_t expected[] = {PACKET_PREFIX, static_cast<uint32_t>(address), static_cast<uint32_t>(address >> 32)};
    for (size_t index = 0; index < sizeof(expected) / sizeof(expected[0]); ++index) {
        uint32_t word = 0;
        if (!read(tail + index * 4, word) || word != expected[index]) return false;
    }
    uint32_t low = 0, high = 0, context = 0;
    if (!read(tail + 20, low) || !read(tail + 24, high) || !read(tail + 28, context) ||
        !(low & 1) || !(high & 0x80000000u) || context || (uint64_t(high) << 32 | low) == gSeq) return false;
    const auto fenceMatches = [&] {
        uint32_t first = 0, second = 0;
        return read(fenceOff, first) && read(fenceOff + 4, second) && first == low && second == high;
    };
    return fenceMatches() && atTail() && fenceMatches() && live();
}

'''.replace('PACKET_PREFIX', PACKET_PREFIX)

BOOTSTRAP = '''#define PHX34_CMP_TAIL_FENCE 0x2550000ull
#define PHX34_GFX_TAIL_FENCE 0x2580000ull

static bool phx34AppendQueueTail(uint64_t ring, uint32_t capacity, uint32_t *end, uint64_t fence, uint32_t cookie[2])
{
   if (!phx34CheckedBoot) return true;
   if (capacity <= 8 || *end >= capacity - 8 || vr(fence) || vr(fence + 4)) return false;
   arc4random_buf(cookie, 2 * sizeof(*cookie));
   cookie[0] |= 1u;
   cookie[1] |= 0x80000000u;
   const uint64_t address = MC(fence);
   const uint32_t words[] = {PACKET_PREFIX, (uint32_t)address, (uint32_t)(address >> 32), cookie[0], cookie[1], 0};
   for (unsigned index = 0; index < sizeof(words) / sizeof(words[0]); ++index) vw(ring + (*end)++ * 4, words[index]);
   return !vr(fence) && !vr(fence + 4);
}

static bool phx34QueueTailReached(uint64_t fence, const uint32_t cookie[2])
{
   return !phx34CheckedBoot || (vr(fence) == cookie[0] && vr(fence + 4) == cookie[1]);
}

'''.replace('PACKET_PREFIX', PACKET_PREFIX)


def stage_native(source):
    source = once(source, '    IOReturn adoptQueue(const uint64_t in[6]);\n',
                  '    IOReturn adoptQueue(const uint64_t in[6]);\n' + DECLARATION)
    source = once(source, ADOPT, METHOD + ADOPT)
    anchor = '    exactQueueAdopted[qi] = true;'
    return change(source, ADOPT, (anchor, '''    if (!dcnRawTailMatchesLocked(ringOff, ringDw, wbOff, wptr, fenceOff)) {
        IOLockUnlock(gpuLock);
        return kIOReturnNotReady;
    }
''' + anchor))


def stage_bootstrap(source):
    source = previous_bootstrap(source)
    compute = 'static void compute_via_mes(void)\n'
    source = once(source, compute, BOOTSTRAP + compute)
    source = change(source, compute,
                    ('   vw(CMP_WB + 16, 8); vw(CMP_WB + 20, 0);\n   db(6 * 4, 8);',
                     '''   uint32_t end = 8, cookie[2] = {0, 0};
   if (!phx34AppendQueueTail(CMP_RING, 1024, &end, PHX34_CMP_TAIL_FENCE, cookie)) return;
   vw(CMP_WB + 16, end); vw(CMP_WB + 20, 0);
   db(6 * 4, end);'''),
                    ('vr(TESTBUF) == 0xFEEDF00D) { reached',
                     'vr(TESTBUF) == 0xFEEDF00D &&\n         phx34QueueTailReached(PHX34_CMP_TAIL_FENCE, cookie)) { reached'),
                    ('6 * 4, 8, 0x2550000}', '6 * 4, end, PHX34_CMP_TAIL_FENCE}'))
    return change(source, 'static void gfx_via_mes(void)\n',
                  ('   vw(GFX_WB + 16, w);',
                   '''   uint32_t cookie[2] = {0, 0};
   if (!phx34AppendQueueTail(GFX_RING, GFX_RDW, &w, PHX34_GFX_TAIL_FENCE, cookie)) return;
   vw(GFX_WB + 16, w);'''),
                  ('vr(TESTBUF + 0x40) == 0x6F7A6F7A) { reached',
                   'vr(TESTBUF + 0x40) == 0x6F7A6F7A &&\n         phx34QueueTailReached(PHX34_GFX_TAIL_FENCE, cookie)) { reached'),
                  ('0x2580000 | 1}', 'PHX34_GFX_TAIL_FENCE | 1}'))
