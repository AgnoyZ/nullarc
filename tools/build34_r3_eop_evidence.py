"""Check private, normalized build34 legacy EOP trial observations offline."""

import re
from struct import Struct


_CASES = (("gfx", False), ("gfx", True), ("compute", False), ("compute", True))
_CLIENT = 0x14
_SOURCE = 0xB5
_RINGS = {"gfx": 0x00, "compute": 0x04}
_U32_MAX = (1 << 32) - 1
_U64_MAX = (1 << 64) - 1
_ENTRY = Struct("<8I")
_RELEASE_MEM = Struct("<8I")
_RELEASE_HEADER = 0xC0064900
_RELEASE_EVENT = 0x06603514
_RELEASE_DATA64 = 2 << 29
_RELEASE_INT_AFTER_CONFIRM = 2 << 24
_FENCE_BYTES = 8
_IH_OFFSET = 0x3FFFC
_IH_OVERFLOW = 1
_IH_FULL_OR_AT_RISK = 0xC0000
_MES_QUEUE_FLAG = 0x1000000
_MAX_BATCHES = 64
_CASE_FIELDS = ("queue interrupt recipe_sha256 target before first_read final_read start_ns submit_ns "
                "close_ns cleanup_end_ns lost overflow fault")
_SAMPLE_FIELDS = "identity begin_ns end_ns fence other_fence payload_ok"


def _fields(record, names, label):
    if type(record) is not dict or record.keys() != set(names.split()):
        raise ValueError(f"unexpected {label} fields")


def _integer(value, label, low=1, high=_U64_MAX - 1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid {label}")
    return value


def _identity(record):
    _fields(record, "service_epoch route_epoch gfx_generation compute_generation", "identity")
    for name, value in record.items():
        _integer(value, name)
    return record


def _sample(record):
    _fields(record, _SAMPLE_FIELDS, "fence sample")
    _identity(record["identity"])
    begin = _integer(record["begin_ns"], "sample start")
    _integer(record["end_ns"], "sample end", low=begin)
    for name in ("fence", "other_fence"):
        _integer(record[name], name, low=0, high=_U32_MAX)
    if type(record["payload_ok"]) is not bool:
        raise ValueError("invalid payload observation")


def _check_vector(vector, identity, queue, submit, read):
    _fields(vector, "identity seen_ns client_id source_id ring_id mes_tagged", "IH vector")
    if _identity(vector["identity"]) != identity:
        raise ValueError("stale IH vector identity")
    seen = _integer(vector["seen_ns"], "IH observation time")
    if not submit < seen < read:
        raise ValueError("IH observation outside submit-to-read window")
    client = _integer(vector["client_id"], "IH client", low=0, high=255)
    source = _integer(vector["source_id"], "IH source", low=0, high=255)
    ring = _integer(vector["ring_id"], "IH ring ID", low=0, high=255)
    if (client != _CLIENT or source != _SOURCE or vector["mes_tagged"] is not False or
            (ring & 0x7F) != _RINGS[queue]):
        raise ValueError("not the expected legacy CP EOP")


def _decode_entry(data, identity, seen_ns):
    if type(data) is not bytes or len(data) != _ENTRY.size:
        raise ValueError("IH entry must contain exactly 32 captured bytes")
    words = _ENTRY.unpack(data)
    header = words[0]
    return dict(identity=identity, seen_ns=seen_ns, client_id=header & 0xFF,
                source_id=(header >> 8) & 0xFF, ring_id=(header >> 16) & 0xFF,
                mes_tagged=bool(words[4] & _MES_QUEUE_FLAG))


def _cursor(value, ring_size, *, writeback=False):
    value = _integer(value, "IH cursor", low=0, high=_U32_MAX)
    if writeback and value & (_IH_OVERFLOW | _IH_FULL_OR_AT_RISK):
        raise ValueError("IH writeback signals overflow or insufficient ring space")
    if value & ~_IH_OFFSET or value >= ring_size or value % _ENTRY.size:
        raise ValueError("IH cursor outside the aligned ring")
    return value


def _capture_vectors(record, batches, ring_size, *, start_cursor=None, dispatch_ns=None):
    if type(batches) is not list or not 2 <= len(batches) <= _MAX_BATCHES:
        raise ValueError("require a bounded, bracketed IH capture")
    _sample(record["before"])
    identity = record["before"]["identity"]
    previous_end = _integer(record["start_ns"], "window start")
    submit = _integer(record["submit_ns"], "submission time")
    close = _integer(record["close_ns"], "window close")
    cleanup_end = _integer(record["cleanup_end_ns"], "cleanup end")
    next_cursor = start_cursor
    vectors = []
    for index, batch in enumerate(batches):
        _fields(batch, "identity begin_ns end_ns read_cursor writeback_before writeback_after entries", "IH batch")
        if _identity(batch["identity"]) != identity:
            raise ValueError("IH batch crossed a service, route or queue epoch")
        begin = _integer(batch["begin_ns"], "IH batch start", low=previous_end)
        end = _integer(batch["end_ns"], "IH batch end", low=begin, high=cleanup_end)
        previous_end = end
        read = _cursor(batch["read_cursor"], ring_size)
        write = _cursor(batch["writeback_before"], ring_size, writeback=True)
        if write != _cursor(batch["writeback_after"], ring_size, writeback=True):
            raise ValueError("IH writeback changed during capture")
        if next_cursor is not None and read != next_cursor:
            raise ValueError("IH consumer cursor skipped or replayed entries")
        next_cursor = write
        expected = ((write - read) % ring_size) // _ENTRY.size
        entries = batch["entries"]
        if type(entries) is not list or len(entries) != expected:
            raise ValueError("IH entry count disagrees with cursor movement")
        if index == 0 and (expected or end >= submit):
            raise ValueError("IH capture must begin empty before submission")
        if index == len(batches) - 1 and (expected or begin < close):
            raise ValueError("IH capture must end empty during cleanup")
        if expected:
            if expected != 1 or vectors or begin <= submit:
                raise ValueError("unexpected IH traffic outside the single-entry trial")
            if dispatch_ns is not None and dispatch_ns > begin:
                raise ValueError("IH copy began before the captured ISR dispatch")
            vectors.append(_decode_entry(entries[0], identity, end))
    return vectors, next_cursor


def _release_samples(record, bar0_mc_base, bar0_size):
    samples = {}
    offsets = None
    offset_fields = ("fence_offset", "other_fence_offset")
    for name in ("before", "first_read", "final_read"):
        sample = record[name]
        _fields(sample, _SAMPLE_FIELDS + " " + " ".join(offset_fields), "raw fence sample")
        pair = tuple(_integer(sample[field], field, low=0, high=bar0_size - _FENCE_BYTES)
                     for field in offset_fields)
        if pair[0] == pair[1] or any(offset % _FENCE_BYTES for offset in pair):
            raise ValueError("unaligned or aliased BAR0 fence slots")
        if offsets is not None and pair != offsets:
            raise ValueError("BAR0 fence slots changed during route case")
        offsets = pair
        samples[name] = {field: value for field, value in sample.items() if field not in offset_fields}

    packet = record["release_mem"]
    if type(packet) is not bytes or len(packet) != _RELEASE_MEM.size:
        raise ValueError("require 32 captured RELEASE_MEM bytes")
    header, event, control, address_lo, address_hi, data_lo, data_hi, context = _RELEASE_MEM.unpack(packet)
    expected_control = _RELEASE_DATA64 | (_RELEASE_INT_AFTER_CONFIRM if record["interrupt"] is True else 0)
    if (header, event, control, context) != (_RELEASE_HEADER, _RELEASE_EVENT, expected_control, 0):
        raise ValueError("unexpected RELEASE_MEM header, event, control or context")
    if (address_lo | (address_hi << 32)) != bar0_mc_base + offsets[0]:
        raise ValueError("RELEASE_MEM target does not match BAR0 fence slot")
    if data_hi or data_lo != record["target"]:
        raise ValueError("RELEASE_MEM data does not match trial target")
    return samples, offsets


def _geometry(ring_size_bytes, bar0_mc_base, bar0_size_bytes):
    ring_size = _integer(ring_size_bytes, "IH ring size", low=2 * _ENTRY.size, high=_IH_OFFSET + 4)
    if ring_size & (ring_size - 1):
        raise ValueError("IH ring size must be a power of two")
    mc_base = _integer(bar0_mc_base, "BAR0 MC base")
    bar0_size = _integer(bar0_size_bytes, "BAR0 size", low=2 * _FENCE_BYTES,
                         high=_U64_MAX - mc_base + 1)
    if mc_base % _FENCE_BYTES or bar0_size % _FENCE_BYTES:
        raise ValueError("unaligned BAR0 aperture")
    return ring_size, mc_base, bar0_size


def _normalize_capture(record, ring_size, mc_base, bar0_size, *, start_cursor=None, dispatch_ns=None):
    item = {name: record[name] for name in _CASE_FIELDS.split()}
    samples, offsets = _release_samples(record, mc_base, bar0_size)
    item.update(samples)
    item["vectors"], next_cursor = _capture_vectors(item, record["ih_capture"], ring_size,
                                                     start_cursor=start_cursor, dispatch_ns=dispatch_ns)
    return item, offsets, next_cursor


def check_ih_capture(records, *, ring_size_bytes, bar0_mc_base, bar0_size_bytes,
                     observe_budget_ns, cleanup_budget_ns):
    """Validate legacy multi-route snapshots; an IH vector is not an ISR observation."""
    ring_size, mc_base, bar0_size = _geometry(ring_size_bytes, bar0_mc_base, bar0_size_bytes)
    if type(records) is not list or len(records) != len(_CASES):
        raise ValueError("expected exactly four ordered route cases")
    normalized = []
    for record in records:
        _fields(record, _CASE_FIELDS + " ih_capture release_mem", "raw route case")
        item, _, _ = _normalize_capture(record, ring_size, mc_base, bar0_size)
        normalized.append(item)
    result = check(normalized, observe_budget_ns=observe_budget_ns, cleanup_budget_ns=cleanup_budget_ns)
    return dict(result, raw_ih_capture_checked=True, release_mem_checked=True)


def check_one_shot_irq_delivery(records, *, scope, terminal):
    """Correlate private ISR, IH and fence traces on one admitted, non-rearmed route.

    The caller supplies the independently bound scope and complete trace. This
    checks consistency, not loaded images, actual dispatch, DMA drain or admission.
    """
    _fields(scope, "identity irq_source_token initial_read_cursor ring_size_bytes bar0_mc_base "
            "bar0_size_bytes gfx_fence_offset compute_fence_offset observe_budget_ns cleanup_budget_ns "
            "terminal_deadline_ns",
            "single-route scope")
    identity = _identity(scope["identity"])
    irq_token = _integer(scope["irq_source_token"], "admitted IRQ source token")
    ring_size, mc_base, bar0_size = _geometry(scope["ring_size_bytes"], scope["bar0_mc_base"], scope["bar0_size_bytes"])
    cursor = _cursor(scope["initial_read_cursor"], ring_size)
    offsets = {queue: _integer(scope[queue + "_fence_offset"], "admitted BAR0 fence offset",
                               low=0, high=bar0_size - _FENCE_BYTES) for queue in _RINGS}
    if len(set(offsets.values())) != 2 or any(offset % _FENCE_BYTES for offset in offsets.values()):
        raise ValueError("invalid admitted BAR0 fence pair")
    if type(records) is not list or len(records) != len(_CASES):
        raise ValueError("expected exactly four ordered route cases")

    normalized = []
    next_dispatch = 1
    prior_fences = {}
    for record, (queue, interrupt) in zip(records, _CASES):
        _fields(record, _CASE_FIELDS + " ih_capture release_mem isr_dispatches", "single-route case")
        if record["queue"] != queue or record["interrupt"] is not interrupt:
            raise ValueError("expected control then EOP for GFX, then Compute")
        dispatches = record["isr_dispatches"]
        if type(dispatches) is not list or len(dispatches) != int(interrupt):
            raise ValueError("missing, duplicate or unexpected ISR dispatch")
        dispatch_ns = None
        if interrupt:
            dispatch = dispatches[0]
            _fields(dispatch, "identity source_token ordinal seen_ns", "ISR dispatch")
            if (_identity(dispatch["identity"]) != identity or
                    _integer(dispatch["source_token"], "IRQ source token") != irq_token):
                raise ValueError("ISR dispatch crossed the admitted route or source")
            if _integer(dispatch["ordinal"], "ISR dispatch ordinal") != next_dispatch:
                raise ValueError("ISR dispatch ordinal skipped or replayed")
            next_dispatch += 1
            dispatch_ns = _integer(dispatch["seen_ns"], "ISR dispatch time",
                                    low=_integer(record["submit_ns"], "submission time") + 1)

        item, pair, cursor = _normalize_capture(record, ring_size, mc_base, bar0_size,
                                                start_cursor=cursor, dispatch_ns=dispatch_ns)
        peer = "compute" if queue == "gfx" else "gfx"
        if pair != (offsets[queue], offsets[peer]):
            raise ValueError("BAR0 fence slots do not match the admitted queue pair")
        peer_value = item["before"]["other_fence"]
        if prior_fences.setdefault(peer, peer_value) != peer_value:
            raise ValueError("peer fence changed between route cases")
        prior_fences[queue] = item["target"]
        normalized.append(item)

    result = _check_records(normalized, observe_budget_ns=scope["observe_budget_ns"],
                            cleanup_budget_ns=scope["cleanup_budget_ns"], fixed_identity=identity)
    _fields(terminal, "identity source_token seen_ns dispatch_count", "terminal dispatch sample")
    if (_identity(terminal["identity"]) != identity or
            _integer(terminal["source_token"], "terminal IRQ source token") != irq_token):
        raise ValueError("terminal sample crossed the admitted route or source")
    if _integer(terminal["dispatch_count"], "terminal IRQ dispatch count", low=0) != next_dispatch - 1:
        raise ValueError("terminal IRQ dispatch count disagrees with the four windows")
    _integer(terminal["seen_ns"], "terminal sample time", low=normalized[-1]["cleanup_end_ns"],
             high=_integer(scope["terminal_deadline_ns"], "terminal deadline"))
    return dict(result, raw_ih_capture_checked=True, release_mem_checked=True, isr_dispatch_checked=True,
                single_route_checked=True, old_writer_drain_proved=False)


def check(records, *, observe_budget_ns, cleanup_budget_ns):
    """Refuse ambiguous evidence; never grant ownership, visibility or admission.

    Budgets and identities come from an independently admitted scope. The
    caller must supply the complete IH stream through verified cleanup and the
    actual first independent post-vector read, including failed reads.
    """
    return _check_records(records, observe_budget_ns=observe_budget_ns, cleanup_budget_ns=cleanup_budget_ns)


def _check_records(records, *, observe_budget_ns, cleanup_budget_ns, fixed_identity=None):
    observe = _integer(observe_budget_ns, "observation budget")
    cleanup = _integer(cleanup_budget_ns, "cleanup budget")
    if type(records) is not list or len(records) != len(_CASES):
        raise ValueError("expected exactly four ordered route cases")

    service = None
    prev_cleanup = 0
    route_epochs, queue_epochs, fence_values = set(), set(), set()
    recipes = {}
    for record, (queue, interrupt) in zip(records, _CASES):
        _fields(record, _CASE_FIELDS + " vectors", "route case")
        if record["queue"] != queue or record["interrupt"] is not interrupt:
            raise ValueError("expected control then EOP for GFX, then Compute")
        digest = record["recipe_sha256"]
        if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid control recipe fingerprint")
        if recipes.setdefault(queue, digest) != digest:
            raise ValueError("control and EOP recipes differ")

        before, first, final = record["before"], record["first_read"], record["final_read"]
        for sample in (before, first, final):
            _sample(sample)
        identity = before["identity"]
        if (first["identity"] != identity or final["identity"] != identity or
                service not in (None, identity["service_epoch"])):
            raise ValueError("fence sample crossed a service, route or queue epoch")
        service = identity["service_epoch"]
        route = identity["route_epoch"]
        queue_epoch = (queue, identity[queue + "_generation"])
        if fixed_identity is None:
            if route in route_epochs or queue_epoch in queue_epochs:
                raise ValueError("reused trial route or queue epoch")
            route_epochs.add(route)
            queue_epochs.add(queue_epoch)
        elif identity != fixed_identity:
            raise ValueError("fence sample crossed the admitted route or queue generation")

        target = _integer(record["target"], "target fence", high=_U32_MAX - 1)
        seed = before["fence"]
        if seed == target or seed in fence_values or target in fence_values:
            raise ValueError("reused fence seed or target")
        fence_values.update((seed, target))
        if before["payload_ok"] or first["fence"] != target or not first["payload_ok"]:
            raise ValueError("no fresh fence and verified payload at first read")
        if final["fence"] != target or not final["payload_ok"]:
            raise ValueError("fence or payload changed by the final read")
        if before["other_fence"] != first["other_fence"] or before["other_fence"] != final["other_fence"]:
            raise ValueError("other queue fence changed")

        start = _integer(record["start_ns"], "window start")
        submit = _integer(record["submit_ns"], "submission time")
        close = _integer(record["close_ns"], "window close")
        end = _integer(record["cleanup_end_ns"], "cleanup end")
        deadline = start + observe
        limit = _integer(deadline + cleanup, "cleanup deadline")
        if not (prev_cleanup < start <= before["begin_ns"] <= before["end_ns"] < submit <
                first["begin_ns"] <= first["end_ns"] < final["begin_ns"] <= final["end_ns"] <=
                deadline <= close <= end <= limit):
            raise ValueError("invalid observation window or cleanup deadline")
        prev_cleanup = end

        if record["lost"] is not False or record["overflow"] is not False:
            raise ValueError("IH capture lost or overflowed")
        if record["fault"] is not False:
            raise ValueError("fault during route trial")
        vectors = record["vectors"]
        if type(vectors) is not list or len(vectors) != int(interrupt):
            raise ValueError("missing, duplicate or unexpected IH observations")
        if interrupt:
            _check_vector(vectors[0], identity, queue, submit, first["begin_ns"])

    return {"status": "consistent-r3-eop-route-records", "hardware_attested": False}
