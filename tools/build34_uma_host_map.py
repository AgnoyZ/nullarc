"""Classify host-side coverage only; no result grants UMA ownership."""

from struct import Struct

PAGE_BYTES = 4096
PHYSICAL_LIMIT = 1 << 48
MAX_MAP_BYTES = 1 << 20
MAX_WINDOW_BYTES = 64 << 20
MEMORY_RUNTIME = 1 << 63
HOST_USABLE_TYPES = frozenset((1, 2, 3, 4, 7))
DESCRIPTOR = Struct('<I4xQ8xQQ')


def classify_host_map(blob, stride, version, base, length):
    """Check a supplied x86 EFI map; the caller must verify its same-boot provenance."""
    if (type(version) is not int or version != 1 or type(stride) is not int or
            stride < DESCRIPTOR.size or stride % 8 or type(blob) is not bytes or
            not stride <= len(blob) <= MAX_MAP_BYTES or len(blob) % stride):
        raise ValueError('Invalid EFI memory map shape')
    if (type(base) is not int or type(length) is not int or not 0 < base < PHYSICAL_LIMIT or
            not 0 < length <= min(MAX_WINDOW_BYTES, PHYSICAL_LIMIT - base) or
            (base | length) % PAGE_BYTES):
        raise ValueError('Invalid UMA pilot window geometry')

    spans = []
    for offset in range(0, len(blob), stride):
        kind, start, pages, attrs = DESCRIPTOR.unpack_from(blob, offset)
        if not pages or start % PAGE_BYTES or pages > ((1 << 64) - start) // PAGE_BYTES:
            raise ValueError('Invalid EFI descriptor range')
        spans.append((start, start + pages * PAGE_BYTES, kind, attrs))
    spans.sort()

    end = base + length
    covered = 0
    cursor = 0
    other_type = host_usable_type = False
    for start, stop, kind, attrs in spans:
        if start < cursor:
            raise ValueError('Overlapping EFI descriptors')
        cursor = stop
        intersection = min(end, stop) - max(base, start)
        if intersection <= 0:
            continue
        covered += intersection
        if kind in HOST_USABLE_TYPES and not attrs & MEMORY_RUNTIME:
            host_usable_type = True
        elif kind != 0 or attrs & MEMORY_RUNTIME:
            other_type = True

    if host_usable_type:
        return 'host-usable-type-overlap'
    if other_type:
        return 'other-descriptor-overlap'
    if covered != length:
        return 'coverage-incomplete'
    return 'reserved-type-only'
