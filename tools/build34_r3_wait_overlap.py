# SPDX-License-Identifier: MIT
"""Check the ordering of one controlled R3 pair from normalized observations.

The caller supplies one admitted boot/service, one monotonic clock and
serialized, independently read queue fences and retirement snapshots. This
module cannot attest their origin, hardware visibility, scope or teardown.
"""

U64_MAX = (1 << 64) - 1


def _fields(value, label, names):
    if type(value) is not dict or value.keys() != set(names.split()):
        raise ValueError(f"unexpected {label} fields")


def _number(value, label, low=0, high=U64_MAX - 1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid {label}")
    return value


def _receipt(value, queue):
    _fields(value, "receipt", "owner serial slot sequence queue generation")
    for name in ("owner", "serial", "sequence", "generation"):
        _number(value[name], f"receipt {name}", 1)
    _number(value["slot"], "receipt slot", high=63)
    if _number(value["queue"], "receipt queue", high=1) != queue:
        raise ValueError("wrong actual receipt queue")


def check(compute, gfx, wait, before, witness, after, drained):
    """Refuse incomplete or inconsistent ordering; return no hardware verdict."""
    targets = {"compute": compute, "gfx": gfx}
    for queue, receipt in enumerate(targets.values()):
        _receipt(receipt, queue)
    c, g = compute["sequence"], gfx["sequence"]
    if c >= g or (compute["owner"], compute["serial"]) == (gfx["owner"], gfx["serial"]):
        raise ValueError("expected distinct receipts with earlier Compute")

    _fields(wait, "wait", "service_epoch begin_ns end_ns reply status")
    epoch = _number(wait["service_epoch"], "wait service epoch", 1)
    begin = _number(wait["begin_ns"], "wait start", 1)
    end = _number(wait["end_ns"], "wait end", 1)
    _receipt(wait["reply"], 1)
    # The staged wire reply uses status 0 for COMPLETE.
    if _number(wait["status"], "wait status") != 0 or wait["reply"] != gfx:
        raise ValueError("no exact completion for the GFX receipt")

    previous = None
    for sample in (before, witness, after, drained):
        _fields(sample, "snapshot", "service_epoch ns compute gfx retired")
        _number(sample["ns"], "snapshot time", 1)
        if _number(sample["service_epoch"], "snapshot service epoch", 1) != epoch:
            raise ValueError("service changed during observation")
        floor = _number(sample["retired"], "global retirement prefix")
        for name, receipt in targets.items():
            current = sample[name]
            _fields(current, "queue sample", "generation submitted completed")
            generation = _number(current["generation"], "queue generation", 1)
            submitted = _number(current["submitted"], "queue submitted sequence")
            completed = _number(current["completed"], "queue completed sequence")
            if generation != receipt["generation"] or submitted < max(completed, receipt["sequence"]):
                raise ValueError("stale queue or invalid fence bounds")
            if previous and (completed < previous[name]["completed"] or submitted < previous[name]["submitted"]):
                raise ValueError("queue observation regressed")
        if floor > max(sample[name]["submitted"] for name in targets) or (previous and floor < previous["retired"]):
            raise ValueError("invalid global retirement prefix")
        previous = sample

    if not before["ns"] < begin < witness["ns"] < end < after["ns"] < drained["ns"]:
        raise ValueError("snapshots do not bracket the exact wait and later drain")
    if before["gfx"]["completed"] >= g or witness["gfx"]["completed"] < g:
        raise ValueError("no independent GFX fence completion before wait return")
    if after["compute"]["completed"] >= c:
        raise ValueError("earlier Compute was not still pending after the wait")
    if after["retired"] >= c:
        raise ValueError("global retirement crossed pending Compute")
    if drained["compute"]["completed"] < c or drained["retired"] < g:
        raise ValueError("missing later drain of both targets and the global prefix")

    return {"status": "consistent-r3-wait-overlap-records", "hardware_attested": False}
