"""Check private, normalized build34 legacy EOP trial observations offline."""

import re


_CASES = (("gfx", False), ("gfx", True), ("compute", False), ("compute", True))
_CLIENT = 0x14
_SOURCE = 0xB5
_RINGS = {"gfx": 0x00, "compute": 0x04}
_U32_MAX = (1 << 32) - 1
_U64_MAX = (1 << 64) - 1


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
        _fields(record, "queue interrupt recipe_sha256 target before first_read final_read start_ns submit_ns "
                        "close_ns cleanup_end_ns lost overflow fault vectors", "route case")
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
