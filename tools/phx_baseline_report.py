"""Turn a phase-1 capture (tools/phx_baseline.sh) into the H1-H4 verdict docs/analysis.md asks for.

docs/analysis.md fixes which optimisation is worth implementing, but "which hypothesis holds" was a hand
computation: read three windows of a JSON file, decide, and hope nobody mis-read a column. This tool does
that computation instead, with the thresholds written down (docs/analysis.md §9), so the verdict can be
reviewed, re-run and tested on the host that runs CI -- without the target laptop.

What it does NOT do: measure. It only reads a capture the laptop produced. A capture that is missing, a
snapshot without a window, or a counter the capture stopped recording, is refused rather than guessed:
every undecidable hypothesis is reported as undecidable with the reason, never as "not supported".

  python3 tools/phx_baseline_report.py baseline=/Users/Shared/phx-baseline-20261103-1010 --out build/verdict
  python3 tools/phx_baseline_report.py baseline=DIR b1-sse-off=DIR --out build/verdict
  python3 tools/phx_baseline_report.py --demo --out build/verdict   # synthetic: proves the pipeline, no data

Exit codes: 0 verdict written, 2 usage, 4 the capture cannot support a verdict (reason printed),
5 the output directory already exists.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics

# Thresholds: the same table as docs/analysis.md §9. Changing one changes what "supported" means, so it is
# a documented number rather than a literal buried in a comparison.
THRESHOLDS = {
    "h1_copy_share_pct": 40.0,
    "h1_present_ratio": 0.85,
    "h2_late_avg_us": 300.0,
    "h2_late_max_us": 2000.0,
    "h3_present_over_tick_ratio": 1.05,
    "h3_dropped_refresh_pct": 5.0,
    "h4_stall_share_pct": 3.0,
    "ab_meaningful_pct": 10.0,
}

# Fields every measured window has to carry, or the capture cannot decide anything.
REQUIRED_WINDOW_FIELDS = (
    "vbl_hz", "presents_per_s", "frames_on_panel", "avg_copy_us", "copy_share_of_refresh_pct",
    "copy_skip", "blank_frames", "iop_fail", "vbl_late_avg_us", "vbl_late_max_us",
)
# Fields added when the capture started recording the present cadence (the H3 evidence).
CADENCE_WINDOW_FIELDS = (
    "iop_gap1", "iop_gap2", "iop_gap3", "iop_gap4", "iop_vsync_waits", "iop_vsync_late",
)
# Metrics compared between a baseline capture and an A/B capture.
COMPARED_METRICS = (
    "presents_per_s", "avg_copy_us", "copy_share_of_refresh_pct", "vbl_late_avg_us", "gap1_share_pct",
)


class ReportError(ValueError):
    pass


def load_capture(label, path):
    """Read one baseline.json (or the directory holding it) and refuse anything that cannot be a verdict."""
    path = Path(path).expanduser()
    if path.is_dir():
        path = path / "baseline.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise ReportError(f"{label}: cannot read {path}") from None
    try:
        record = json.loads(raw)
    except json.JSONDecodeError:
        raise ReportError(f"{label}: {path} is not JSON") from None
    if not isinstance(record, dict) or record.get("tool") != "phx_baseline":
        raise ReportError(f"{label}: not a phx_baseline record (tool field)")
    claims = record.get("claims")
    if not isinstance(claims, dict):
        raise ReportError(f"{label}: the record carries no claims block")
    if claims.get("hardware_execution_established"):
        raise ReportError(f"{label}: the record claims hardware execution, so it is not a display-path capture")
    window_seconds = record.get("window_seconds")
    if not isinstance(window_seconds, int) or window_seconds <= 0:
        raise ReportError(f"{label}: captured with --window 0, which reads the counters once: "
                          "there is no rate and no delta, so no hypothesis can be decided. Rerun with --window 60")
    windows = record.get("windows")
    if not isinstance(windows, list) or not windows:
        raise ReportError(f"{label}: the record has no windows")
    if any(window.get("snapshot_only") for window in windows):
        raise ReportError(f"{label}: a window of the record is a snapshot, not a measurement")
    missing = sorted({field for window in windows for field in REQUIRED_WINDOW_FIELDS
                      if not isinstance(window.get(field), (int, float))})
    if missing:
        raise ReportError(f"{label}: the capture is missing {', '.join(missing)}: "
                          "the record is incomplete, not a result")
    return {
        "label": label,
        "path": str(path),
        "window_seconds": window_seconds,
        "samples": record.get("samples", len(windows)),
        "knobs": record.get("knobs") or {},
        "windows": windows,
        "fixture": bool(record.get("fixture")),
        "has_cadence": all(isinstance(window.get(field), (int, float))
                           for window in windows for field in CADENCE_WINDOW_FIELDS),
    }


def median_of(capture, field):
    return float(statistics.median(float(window[field]) for window in capture["windows"]))


def cadence_medians(capture):
    if not capture["has_cadence"]:
        return None
    gaps = [median_of(capture, f"iop_gap{i}") for i in (1, 2, 3, 4)]
    total = sum(gaps)
    presented = median_of(capture, "presents_per_s")
    ticks = median_of(capture, "vbl_hz")
    return {
        "gap1_share_pct": 100.0 * gaps[0] / total if total else 0.0,
        "dropped_refresh_pct": 100.0 * (gaps[1] + gaps[2]) / total if total else 0.0,
        "gap_frames": gaps,
        "present_over_tick_ratio": presented / ticks if ticks else 0.0,
        "vsync_waits": median_of(capture, "iop_vsync_waits"),
        "vsync_late": median_of(capture, "iop_vsync_late"),
    }


def decide(capture):
    """Apply the documented thresholds to one capture and say what is supported, undecidable, or refuted."""
    metrics = {
        "vbl_hz": median_of(capture, "vbl_hz"),
        "presents_per_s": median_of(capture, "presents_per_s"),
        "frames_on_panel": median_of(capture, "frames_on_panel"),
        "avg_copy_us": median_of(capture, "avg_copy_us"),
        "copy_share_of_refresh_pct": median_of(capture, "copy_share_of_refresh_pct"),
        "copy_skip": median_of(capture, "copy_skip"),
        "blank_frames": median_of(capture, "blank_frames"),
        "iop_fail": median_of(capture, "iop_fail"),
        "vbl_late_avg_us": median_of(capture, "vbl_late_avg_us"),
        "vbl_late_max_us": median_of(capture, "vbl_late_max_us"),
    }
    copies = metrics["frames_on_panel"]
    metrics["stall_share_pct"] = (100.0 * metrics["copy_skip"] / (copies + metrics["copy_skip"])
                                 if copies + metrics["copy_skip"] else 0.0)
    metrics["blank_share_pct"] = (100.0 * metrics["blank_frames"] / (copies + metrics["blank_frames"])
                                  if copies + metrics["blank_frames"] else 0.0)
    cadence = cadence_medians(capture)

    decisions = []

    copy_limited = (metrics["copy_share_of_refresh_pct"] >= THRESHOLDS["h1_copy_share_pct"]
                    and metrics["vbl_hz"] > 0
                    and metrics["presents_per_s"] <= THRESHOLDS["h1_present_ratio"] * metrics["vbl_hz"])
    decisions.append({
        "id": "H1",
        "state": "supported" if copy_limited else "refuted",
        "evidence": {"copy_share_of_refresh_pct": round(metrics["copy_share_of_refresh_pct"], 1),
                     "presents_per_s": round(metrics["presents_per_s"], 1),
                     "vbl_hz": round(metrics["vbl_hz"], 1)},
        "threshold": {"copy_share_pct_at_least": THRESHOLDS["h1_copy_share_pct"],
                      "presents_at_most_of_ticks": THRESHOLDS["h1_present_ratio"]},
        "why": ("one copied frame costs at least the threshold share of a refresh and the panel takes frames "
                "slower than it ticks: the copy is the limiter"
                if copy_limited else
                "the copy does not both dominate a refresh and hold the present rate below the tick rate"),
        "if_supported": "optimise the copy loop (nvrm-accel.cpp:1225-1254) and the destination decision "
                        "(phxfb.cpp:434-451), one boot argument per commit",
    })

    jitter = (metrics["vbl_late_avg_us"] >= THRESHOLDS["h2_late_avg_us"]
              or metrics["vbl_late_max_us"] >= THRESHOLDS["h2_late_max_us"])
    decisions.append({
        "id": "H2",
        "state": "candidate" if jitter else "refuted",
        "evidence": {"vbl_late_avg_us": round(metrics["vbl_late_avg_us"], 1),
                     "vbl_late_max_us": round(metrics["vbl_late_max_us"], 1)},
        "threshold": {"late_avg_us_at_least": THRESHOLDS["h2_late_avg_us"],
                      "late_max_us_at_least": THRESHOLDS["h2_late_max_us"]},
        "why": ("the software VBL tick fires late enough to move a present across a refresh boundary; "
                "candidate only -- confirm with the B2 A/B (debug.phxfb_vbl_staged=0)"
                if jitter else "tick lateness is below the threshold that would move a present"),
        "if_supported": "work on the tick (phxfb.cpp:218-242) only after the B2 A/B shows it costs frames",
    })

    if cadence is None:
        decisions.append({
            "id": "H3",
            "state": "undecidable",
            "evidence": None,
            "threshold": {"present_over_tick_ratio_above": THRESHOLDS["h3_present_over_tick_ratio"],
                          "dropped_refresh_pct_at_least": THRESHOLDS["h3_dropped_refresh_pct"]},
            "why": ("this capture does not record the present cadence (debug.nvaccel_iop_gap1..4, "
                    "_vsync_waits, _vsync_late): rerun the capture with the current tools/phx_baseline.sh"),
            "if_supported": "work on present pacing (nvrm-accel.cpp:1096-1117), A/B on debug.nvaccel_iop_vsync",
        })
    else:
        uneven = (cadence["present_over_tick_ratio"] > THRESHOLDS["h3_present_over_tick_ratio"]
                  or cadence["dropped_refresh_pct"] >= THRESHOLDS["h3_dropped_refresh_pct"])
        decisions.append({
            "id": "H3",
            "state": "supported" if uneven else "refuted",
            "evidence": {"gap1_share_pct": round(cadence["gap1_share_pct"], 1),
                         "dropped_refresh_pct": round(cadence["dropped_refresh_pct"], 1),
                         "present_over_tick_ratio": round(cadence["present_over_tick_ratio"], 2),
                         "vsync_waits": cadence["vsync_waits"],
                         "vsync_late": cadence["vsync_late"]},
            "threshold": {"present_over_tick_ratio_above": THRESHOLDS["h3_present_over_tick_ratio"],
                          "dropped_refresh_pct_at_least": THRESHOLDS["h3_dropped_refresh_pct"]},
            "why": ("frames present more often than the panel ticks, or land two or more refreshes apart: "
                    "the cadence is uneven, not merely slow"
                    if uneven else "frames land about one refresh apart, so the cadence is even"),
            "if_supported": "work on present pacing (nvrm-accel.cpp:1096-1117), A/B on debug.nvaccel_iop_vsync",
        })

    stalled = (metrics["stall_share_pct"] >= THRESHOLDS["h4_stall_share_pct"]
               or metrics["blank_share_pct"] >= THRESHOLDS["h4_stall_share_pct"])
    decisions.append({
        "id": "H4",
        "state": "supported" if stalled else "refuted",
        "evidence": {"stall_share_pct": round(metrics["stall_share_pct"], 1),
                     "blank_share_pct": round(metrics["blank_share_pct"], 1),
                     "copy_skip": metrics["copy_skip"], "blank_frames": metrics["blank_frames"]},
        "threshold": {"stall_or_blank_share_pct_at_least": THRESHOLDS["h4_stall_share_pct"]},
        "why": ("frames are held back (surface not ready) or copied as one colour often enough to be a cause"
                if stalled else "held-back and blank frames are rare: readiness is not where frames go"),
        "if_supported": ("work on surface readiness (nvrm-accel.cpp:2240-2270, limit in "
                         "phx780m::nextCopyHold) and sticky VRAM (1326-1329)"),
    })

    supported = [decision["id"] for decision in decisions if decision["state"] == "supported"]
    candidates = [decision["id"] for decision in decisions if decision["state"] == "candidate"]
    undecidable = [decision["id"] for decision in decisions if decision["state"] == "undecidable"]
    return {
        "label": capture["label"],
        "path": capture["path"],
        "windows": len(capture["windows"]),
        "window_seconds": capture["window_seconds"],
        "stable": len(capture["windows"]) >= 2,
        "knobs": capture["knobs"],
        "metrics": {name: round(value, 1) for name, value in metrics.items()},
        "cadence": None if cadence is None else {name: (round(value, 1) if isinstance(value, float) else value)
                                                 for name, value in cadence.items()},
        "decisions": decisions,
        "supported": supported,
        "candidates": candidates,
        "undecidable": undecidable,
        "next_step": next_step(supported, candidates, undecidable),
    }


def next_step(supported, candidates, undecidable):
    if undecidable:
        return (f"decide {', '.join(undecidable)} first: the capture lacks the counters that would settle it, "
                "so a second capture with the current tools/phx_baseline.sh is cheaper than a guess")
    if "H1" in supported:
        return ("optimise the copy: the B1 A/B (debug.nvaccel_iop_sse=0 vs 1) sizes the row copy, then the "
                "destination: one boot argument and one commit per change (docs/analysis.md §8)")
    if "H2" in candidates:
        return ("the tick is late enough to matter but not proven to cost frames: run the B2 A/B "
                "(debug.phxfb_vbl_staged=0 vs 1) before touching the copy (docs/analysis.md §8)")
    if "H3" in supported or "H4" in supported:
        return ("work on pacing/readiness: A/B debug.nvaccel_iop_vsync and watch copy_skip, one change per "
                "commit (docs/analysis.md §8)")
    return ("no display-path hypothesis is supported by this capture: measure the application-side cost first "
            "(A/B debug.phxbos_flush=0 vs 1, plugin dispatch, RADV), as docs/analysis.md §5 requires")


def compare(baseline, other):
    """Difference between a baseline capture and an A/B capture, with the noise caveat spelled out."""
    rows = []
    for metric in COMPARED_METRICS:
        if metric == "gap1_share_pct":
            left, right = cadence_medians(baseline), cadence_medians(other)
            if left is None or right is None:
                continue
            first = left["gap1_share_pct"]
            second = right["gap1_share_pct"]
        else:
            first = median_of(baseline, metric)
            second = median_of(other, metric)
        change = (100.0 * (second - first) / first) if first else None
        rows.append({
            "metric": metric,
            "baseline": round(first, 1),
            "ab": round(second, 1),
            "change_pct": None if change is None else round(change, 1),
            "meaningful": change is not None and abs(change) >= THRESHOLDS["ab_meaningful_pct"],
        })
    return {"baseline": baseline["label"], "ab": other["label"], "rows": rows,
            "note": ("one window per side is a single sample: a change below the threshold is not proof of "
                     "no effect, and a change above it still needs a repeat before it is a result")}


def demo_capture():
    """A synthetic capture shaped exactly like the real one, so CI can run the whole pipeline without hardware."""
    return {
        "tool": "phx_baseline",
        "fixture": True,
        "host": "Darwin-x86_64",
        "window_seconds": 60,
        "samples": 2,
        "knobs": {"debug.phxfb_alias": 1, "debug.phxfb_vbl_staged": 1, "debug.nvaccel_iop": 1,
                  "debug.nvaccel_iop_sse": 1, "debug.nvaccel_iop_vsync": 1, "debug.nvaccel_vm_sticky": 1,
                  "debug.phxbos_flush": 0},
        "windows": [
            {"index": 1, "vbl_ticks": 7200, "vbl_hz": 120.0, "frames_on_panel": 3000, "presents_per_s": 50.0,
             "avg_copy_us": 8000.0, "copy_share_of_refresh_pct": 96.0, "copy_skip": 12, "blank_frames": 0,
             "iop_fail": 0, "vbl_late_avg_us": 120.0, "vbl_late_max_us": 640.0,
             "iop_gap1": 2400, "iop_gap2": 400, "iop_gap3": 120, "iop_gap4": 80,
             "iop_vsync_waits": 900, "iop_vsync_late": 3},
            {"index": 2, "vbl_ticks": 7200, "vbl_hz": 120.0, "frames_on_panel": 3060, "presents_per_s": 51.0,
             "avg_copy_us": 7900.0, "copy_share_of_refresh_pct": 94.8, "copy_skip": 14, "blank_frames": 1,
             "iop_fail": 0, "vbl_late_avg_us": 130.0, "vbl_late_max_us": 700.0,
             "iop_gap1": 2450, "iop_gap2": 380, "iop_gap3": 110, "iop_gap4": 120,
             "iop_vsync_waits": 950, "iop_vsync_late": 4},
        ],
        "claims": {"display_path_counters_read": True, "gpu_work_submitted": False,
                   "hardware_execution_established": False},
        "limitation": "SYNTHETIC fixture written by tools/phx_baseline_report.py --demo: the numbers are made "
                      "up to exercise the pipeline. They are not a measurement and decide nothing.",
    }


def parse_capture_argument(argument):
    if "=" in argument:
        label, _, path = argument.partition("=")
        return label.strip() or "capture", path.strip()
    return Path(argument).name or "capture", argument


def render_markdown(report, comparisons):
    lines = ["# Phase-1 display-path verdict", ""]
    if not report["evidence"]:
        lines += ["> **Synthetic input.** At least one capture in this report is a fixture written by the tool "
                  "itself. It demonstrates the pipeline; it is not measurement and decides nothing.", ""]
    lines += [f"Captures: {len(report['captures'])}; thresholds: docs/analysis.md §9.", "",
              "| capture | windows x seconds | copy share of refresh | presents/s | vbl Hz | avg copy us | late avg/max us |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for capture in report["captures"]:
        means = capture["metrics"]
        lines.append("| {label} | {windows} x {window_seconds} | {copy:.1f}% | {present:.1f} | {ticks:.1f} | "
                     "{copy_us:.0f} | {late_avg:.0f}/{late_max:.0f} |".format(
                         label=capture["label"], windows=capture["windows"],
                         window_seconds=capture["window_seconds"],
                         copy=means["copy_share_of_refresh_pct"], present=means["presents_per_s"],
                         ticks=means["vbl_hz"], copy_us=means["avg_copy_us"],
                         late_avg=means["vbl_late_avg_us"], late_max=means["vbl_late_max_us"]))
    lines.append("")
    for capture in report["captures"]:
        lines += [f"## {capture['label']}", "",
                  "| hypothesis | state | why |", "| --- | --- | --- |"]
        for decision in capture["decisions"]:
            lines.append(f"| {decision['id']} | {decision['state']} | {decision['why']} |")
        if not capture["stable"]:
            lines += ["", "Single window: provisional until a repeat window agrees."]
        lines += ["", f"Next step: {capture['next_step']}", ""]
    for comparison in comparisons:
        lines += [f"## A/B: {comparison['ab']} against {comparison['baseline']}", "",
                  "| metric | baseline | A/B | change |", "| --- | --- | --- | --- |"]
        for row in comparison["rows"]:
            change = "n/a" if row["change_pct"] is None else f"{row['change_pct']:+.1f}%"
            marker = "" if row["meaningful"] else " (below threshold)"
            lines.append(f"| {row['metric']} | {row['baseline']} | {row['ab']} | {change}{marker} |")
        lines += ["", comparison["note"], ""]
    lines += ["## What this report is not", "",
              "- It is not hardware evidence: `hardware_execution_established` stays false in every capture and "
              "in this report.",
              "- A supported hypothesis says where to look, not that the change will help: every optimisation "
              "still needs its own before/after capture."]
    return "\n".join(lines) + "\n"


def build(labels_paths):
    records = [load_capture(label, path) for label, path in labels_paths]
    capture_reports = [decide(record) for record in records]
    comparisons = [compare(records[0], record) for record in records[1:]]
    report = {
        "tool": "phx_baseline_report",
        "evidence": not any(record["fixture"] for record in records),
        "thresholds": THRESHOLDS,
        "captures": capture_reports,
        "comparisons": comparisons,
        "claims": {"derived_from_a_capture": True, "hardware_execution_established": False,
                   "measured_anything_itself": False},
        "limitation": ("A verdict over a capture the target laptop produced. It decides which hypothesis the "
                       "capture supports; it is not GPU-execution, acceleration or smoothness evidence, and a "
                       "capture with one window per configuration is a single sample."),
    }
    return report, render_markdown(report, comparisons)


def write_file(out, name, text):
    descriptor = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)


def make_directory(out):
    """Create --out 0700 on POSIX. Windows has no POSIX mode: asking for one there yields an unusable ACL."""
    if os.name == "nt":
        out.mkdir(parents=True)
    else:
        out.mkdir(parents=True, mode=0o700)


def write_outputs(out, report, markdown, fixture=None, allow_existing=False):
    out = Path(out).absolute()
    if out.exists() and not allow_existing:
        raise ReportError("output directory exists; choose a fresh one")
    try:
        if not out.exists():
            make_directory(out)
        if fixture is not None:
            write_file(out, "capture-fixture.json", json.dumps(fixture, indent=2) + "\n")
        write_file(out, "verdict.json", json.dumps(report, indent=2) + "\n")
        write_file(out, "verdict.md", markdown)
    except OSError:
        raise ReportError("could not write the verdict") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("captures", nargs="*", metavar="LABEL=PATH",
                        help="baseline.json or the phx_baseline output directory; the first one is the baseline")
    parser.add_argument("--out", type=Path, help="new directory for verdict.json and verdict.md")
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of markdown")
    parser.add_argument("--demo", action="store_true",
                        help="write and analyse a synthetic capture: proves the pipeline where no hardware exists")
    arguments = parser.parse_args()
    if not arguments.demo and not arguments.captures:
        parser.error("name at least one capture (LABEL=PATH), or pass --demo")
    try:
        if arguments.demo:
            out = Path(arguments.out or "build/baseline-report-demo").absolute()
            if out.exists():
                raise ReportError("output directory exists; choose a fresh one")
            make_directory(out)
            fixture = demo_capture()
            write_file(out, "capture-fixture.json", json.dumps(fixture, indent=2) + "\n")
            pairs = [("demo", str(out / "capture-fixture.json"))]
            report, markdown = build(pairs)
            write_outputs(out, report, markdown, allow_existing=True)
        else:
            pairs = [parse_capture_argument(argument) for argument in arguments.captures]
            report, markdown = build(pairs)
            if arguments.out:
                write_outputs(arguments.out, report, markdown)
    except ReportError as error:
        parser.exit(4, f"phx_baseline_report: {error}\n")
    if arguments.json:
        print(json.dumps(report, indent=2))
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
