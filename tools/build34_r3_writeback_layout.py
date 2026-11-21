# SPDX-License-Identifier: MIT
"""Check proposed build34 VMID0 system-memory writeback ranges offline only.

The private caller supplies an admitted GART window and known reservations in
three separate address spaces. Geometry cannot attest mappings, reservation
completeness, old-writer drain, coherency, or permission to execute.
"""

PAGE_BYTES = 4096
DWORD_BYTES = 4
LIMITS = {"gpu_va": 1 << 47, "dma": 1 << 48, "host_pa": 1 << 64}


def _fields(record, fields):
    if type(record) is not dict or record.keys() != fields:
        raise ValueError("unexpected writeback record fields")


def _span(base, length, limit):
    if (type(base) is not int or type(length) is not int or base < 0 or
            length <= 0 or base >= limit or length > limit - base):
        raise ValueError("invalid address extent")
    return base, base + length


def _range(record, limit):
    _fields(record, {"base", "bytes"})
    return _span(record["base"], record["bytes"], limit)


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def check(gart_window, compute, gfx, reserved):
    """Require two dedicated 4 KiB pages with a dword guard on either side.

    GPU addresses are lower-half VMID0 VAs; DMA addresses must fit the
    build34 PTE address field. Compare reservations within each space only.
    Success returns no addresses and is never a runtime admission token.
    """
    window = _range(gart_window, LIMITS["gpu_va"])
    if any(edge % PAGE_BYTES for edge in window):
        raise ValueError("unaligned GART window")
    _fields(reserved, LIMITS.keys())
    prior = {}
    for space, limit in LIMITS.items():
        if type(reserved[space]) is not list:
            raise ValueError("invalid reserved range list")
        prior[space] = [_range(item, limit) for item in reserved[space]]

    for queue in (compute, gfx):
        _fields(queue, {*LIMITS, "fence_offset"})
        offset = queue["fence_offset"]
        if (type(offset) is not int or not DWORD_BYTES <= offset <= PAGE_BYTES - 2 * DWORD_BYTES or
                offset % DWORD_BYTES):
            raise ValueError("fence and both guards must fit the page")
        for space, limit in LIMITS.items():
            base = queue[space]
            span = _span(base, PAGE_BYTES, limit)
            if not base or base % PAGE_BYTES:
                raise ValueError(f"invalid writeback page alignment in {space}")
            if space == "gpu_va" and not (window[0] <= span[0] and span[1] <= window[1]):
                raise ValueError("writeback page outside GART window")
            if any(_overlap(span, other) for other in prior[space]):
                raise ValueError(f"writeback page overlaps in {space}")
            prior[space].append(span)

    return {"status": "consistent-writeback-layout-geometry", "hardware_attested": False}
