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
_IH_OFFSET = 0x3FFFC
_IH_OVERFLOW = 1
_IH_FULL_OR_AT_RISK = 0xC0000
_MES_QUEUE_FLAG = 0x1000000
_MAX_BATCHES = 64
_CASE_FIELDS = ("queue interrupt recipe_sha256 target before first_read final_read start_ns submit_ns "
                "close_ns cleanup_end_ns lost overflow fault")


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
    _fields(record, "identity begin_ns end_ns fence other_fence payload_ok", "fence sample")
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


def _capture_vectors(record, ring_size):
    batches = record["ih_capture"]
    if type(batches) is not list or not 2 <= len(batches) <= _MAX_BATCHES:
        raise ValueError("require a bounded, bracketed IH capture")
    _sample(record["before"])
    identity = record["before"]["identity"]
    previous_end = _integer(record["start_ns"], "window start")
    submit = _integer(record["submit_ns"], "submission time")
    close = _integer(record["close_ns"], "window close")
    cleanup_end = _integer(record["cleanup_end_ns"], "cleanup end")
    next_cursor = None
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
            vectors.append(_decode_entry(entries[0], identity, end))
    return vectors


def check_ih_capture(records, *, ring_size_bytes, observe_budget_ns, cleanup_budget_ns):
    """Validate private primary-ring snapshots, without reading or acknowledging hardware.

    Each batch describes one stable writeback interval and all entries between
    its read cursor and writeback. The collector must attest visibility,
    ownership, actual reads, no flag clearing and complete capture separately.
    """
    ring_size = _integer(ring_size_bytes, "IH ring size", low=2 * _ENTRY.size, high=_IH_OFFSET + 4)
    if ring_size & (ring_size - 1):
        raise ValueError("IH ring size must be a power of two")
    if type(records) is not list or len(records) != len(_CASES):
        raise ValueError("expected exactly four ordered route cases")
    normalized = []
    for record in records:
        _fields(record, _CASE_FIELDS + " ih_capture", "raw route case")
        item = {name: value for name, value in record.items() if name != "ih_capture"}
        item["vectors"] = _capture_vectors(record, ring_size)
        normalized.append(item)
    result = check(normalized, observe_budget_ns=observe_budget_ns, cleanup_budget_ns=cleanup_budget_ns)
    return dict(result, raw_ih_capture_checked=True)


def check(records, *, observe_budget_ns, cleanup_budget_ns):
    """Refuse ambiguous evidence; never grant ownership, visibility or admission.

    Budgets and identities come from an independently admitted scope. The
    caller must supply the complete IH stream through verified cleanup and the
    actual first independent post-vector read, including failed reads.
    """
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
        if route in route_epochs or queue_epoch in queue_epochs:
            raise ValueError("reused trial route or queue epoch")
        route_epochs.add(route)
        queue_epochs.add(queue_epoch)

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
