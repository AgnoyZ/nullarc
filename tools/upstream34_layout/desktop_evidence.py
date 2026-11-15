"""Pure evidence checks for original build 34; no hardware or process APIs."""


def validate_frames(before, after, reports_before, reports_after):
    """Require progress, a stable compositor and the original readback contract.

    nvaccelfb accepts command 3 to enable scanout, but its getter returns
    gNvAccelArmed (0 or 1). A successful write of 3 does not make its readback 3.
    This checker observes already-collected values and performs no operations.
    """
    count = "debug.nvaccel_iop_ok"
    if not (type(before[count]) is int and type(after[count]) is int
            and after[count] > before[count] >= 0):
        raise AssertionError("no measured frame progress")
    if (before["WindowServer_pids"] != after["WindowServer_pids"]
            or len(after["WindowServer_pids"]) != 1):
        raise AssertionError("WindowServer changed or is not a single process")
    expected = {"debug.phxagdc": 1, "debug.nvaccelfb": 1,
                "debug.nvaccel_iop": 1, "debug.phxfb_hold": 0}
    for sample_name, sample in [("before", before), ("after", after)]:
        for name, value in expected.items():
            if type(sample[name]) is not int or sample[name] != value:
                raise AssertionError(f"{sample_name} {name}: expected {value}, got {sample[name]!r}")
    if reports_after != reports_before:
        raise AssertionError("new WindowServer diagnostic report")
