"""Stage a checked R3 table-chunk allocation; no production or native binding."""

from build34_exact_submit import once
from build34_exact_vm_detach import stage as previous_stage
from test_build34_exact_ownership import method


ALLOC = 'uint64_t PhxBringup::ptTablePhys('


def stage(source):
    source = previous_stage(source)
    old = method(source, ALLOC)
    new = once(old, '''        uint8_t *p = static_cast<uint8_t *>(b->getBytesNoCopy());
        bzero(p, kPtChunkBytes);
''', '''        uint8_t *p = static_cast<uint8_t *>(b->getBytesNoCopy());
        IOByteCount contiguous = 0;
        const uint64_t base = p && b->getLength() >= kPtChunkBytes
                            ? b->getPhysicalSegment(0, &contiguous) : 0;
        if (!base || contiguous < kPtChunkBytes || (base & ~kPtAddrMask) ||
            kPtChunkBytes - 4096 > kPtAddrMask - base) {
            b->release();
            return 0;
        }
        bzero(p, kPtChunkBytes);
''')
    new = once(new, '        c.chunkPhys[k] = b->getPhysicalAddress();', '        c.chunkPhys[k] = base;')
    return once(source, old, new)
