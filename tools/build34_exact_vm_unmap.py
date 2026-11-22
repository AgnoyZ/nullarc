"""Stage failure-preserving unmap on build34; not a runtime change."""

from build34_exact_submit import once
from build34_exact_vm_chunk import stage as previous_stage
from test_build34_exact_ownership import method


TABLE = 'uint64_t *PhxBringup::ptTable('
WALK = 'uint64_t *PhxBringup::vmPte('
UNMAP = 'IOReturn PhxBringup::vmUnmap('
DECLARATION = '    uint64_t *vmPte(VmCtx &c, uint64_t va, bool alloc);'
CHECKED_DECLARATION = '    uint64_t *vmPte(VmCtx &c, uint64_t va, bool alloc, bool *absent = nullptr);'


def stage(source):
    source = once(previous_stage(source), DECLARATION, CHECKED_DECLARATION)
    table = method(source, TABLE)
    source = once(source, table, once(table, '''        if (phys - c.chunkPhys[i] < kPtChunkBytes)
            return reinterpret_cast<uint64_t *>(static_cast<uint8_t *>(c.chunk[i]->getBytesNoCopy()) + (phys - c.chunkPhys[i]));''',
        '''        if (phys - c.chunkPhys[i] < kPtChunkBytes) {
            auto *bytes = static_cast<uint8_t *>(c.chunk[i]->getBytesNoCopy());
            return bytes ? reinterpret_cast<uint64_t *>(bytes + (phys - c.chunkPhys[i])) : nullptr;
        }'''))
    walk = method(source, WALK)
    checked = once(walk, 'bool alloc) {\n', 'bool alloc, bool *absent) {\n    if (absent) *absent = false;\n')
    checked = once(checked, '''            if (!alloc || c.used >= c.pages)
                return nullptr;''', '''            if (!alloc) {
                if (absent) *absent = *e == 0;
                return nullptr;
            }
            if (c.used >= c.pages)
                return nullptr;''')
    source = once(source, walk, checked)
    unmap = method(source, UNMAP)
    return once(source, unmap, once(unmap, '''        uint64_t *pte = vmPte(c, va + p, false);
        if (pte) {
            *pte = 0;
            flushLine(pte);
        }''', '''        bool absent;
        uint64_t *pte = vmPte(c, va + p, false, &absent);
        if (!pte) {
            if (absent) continue;
            exactVMFault = true;
            IOLockUnlock(gpuLock);
            return kIOReturnVMError;
        }
        *pte = 0;
        flushLine(pte);'''))
