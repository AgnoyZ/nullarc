#!/usr/bin/env python3
"""Analyze one completed process's phase records without double-counting children.

This is an offline reader, never an admission, startup or deployment entrypoint.
Inclusive phase totals overlap. Exclusive totals remove only recorded immediate
children: they can still contain uninstrumented work, waits and logging costs.
Process clock origins are deliberately omitted from the output.
"""

import argparse
import json
from pathlib import Path
import re


def summarize_records(records, *, limit=256):
    if type(limit) is not int or not 1 <= limit <= 1024:
        raise ValueError("invalid record budget")
    if not isinstance(records, list) or not 1 <= len(records) <= limit:
        raise ValueError("requires a nonempty bounded record list from one process")
    indexed = {}
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("record must be an object")
        for name in ("sequence", "start_monotonic_ns", "end_monotonic_ns",
                     "elapsed_ns", "process_cpu_ns"):
            if type(row.get(name)) is not int or row[name] < 0:
                raise ValueError("record has an invalid integer field")
        sequence = row["sequence"]
        if sequence < 1 or sequence in indexed:
            raise ValueError("duplicate or invalid sequence; do not combine processes")
        parent = row.get("parent_sequence")
        if "parent_sequence" not in row or (parent is not None and
                (type(parent) is not int or not 1 <= parent < sequence)):
            raise ValueError("invalid parent sequence")
        phase = row.get("phase")
        if not isinstance(phase, str) or re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", phase) is None:
            raise ValueError("invalid fixed phase label")
        if row.get("status") not in ("returned", "error"):
            raise ValueError("invalid completion status")
        if row["end_monotonic_ns"] - row["start_monotonic_ns"] != row["elapsed_ns"]:
            raise ValueError("duration disagrees with endpoints")
        indexed[sequence] = row
    if set(indexed) != set(range(1, len(records) + 1)):
        raise ValueError("missing record sequence")
    children = {sequence: [] for sequence in indexed}
    roots = []
    previous_start = None
    for sequence in sorted(indexed):
        row = indexed[sequence]
        if previous_start is not None and row["start_monotonic_ns"] < previous_start:
            raise ValueError("sequence order disagrees with the process clock")
        previous_start = row["start_monotonic_ns"]
        parent = row["parent_sequence"]
        if parent is None:
            roots.append(row)
        else:
            if parent not in indexed:
                raise ValueError("missing parent; the capture may be incomplete")
            outer = indexed[parent]
            if not (outer["start_monotonic_ns"] <= row["start_monotonic_ns"] <=
                    row["end_monotonic_ns"] <= outer["end_monotonic_ns"]):
                raise ValueError("child interval escapes its parent")
            children[parent].append(row)
    for group in [roots, *children.values()]:
        intervals = sorted(group, key=lambda row: row["sequence"])
        for earlier, later in zip(intervals, intervals[1:]):
            if earlier["end_monotonic_ns"] > later["start_monotonic_ns"]:
                raise ValueError("sibling intervals overlap; invalid synchronous parentage")
    by_phase = {}
    for sequence in sorted(indexed):
        row = indexed[sequence]
        exclusive = row["elapsed_ns"] - sum(child["elapsed_ns"] for child in children[sequence])
        item = by_phase.setdefault(row["phase"], dict(calls=0, errors=0,
            inclusive_elapsed_ns=0, exclusive_elapsed_ns=0, inclusive_process_cpu_ns=0))
        item["calls"] += 1
        item["errors"] += int(row["status"] == "error")
        item["inclusive_elapsed_ns"] += row["elapsed_ns"]
        item["exclusive_elapsed_ns"] += exclusive
        item["inclusive_process_cpu_ns"] += row["process_cpu_ns"]
    root_elapsed = sum(row["elapsed_ns"] for row in roots)
    if sum(row["exclusive_elapsed_ns"] for row in by_phase.values()) != root_elapsed:
        raise ValueError("exclusive interval accounting failed")
    return dict(records=len(records), potentially_incomplete=len(records) == limit,
        all_calls_returned=all(row["status"] == "returned" for row in records),
        root_elapsed_ns=root_elapsed,
        root_process_cpu_ns=sum(row["process_cpu_ns"] for row in roots),
        by_phase=by_phase,
        top_level=[dict(sequence=row["sequence"], phase=row["phase"],
                        elapsed_ns=row["elapsed_ns"]) for row in roots],
        inclusive_totals_overlap=True, exclusive_includes_uninstrumented_work_and_waits=True,
        cross_process_clock_origins_compared=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase_file", type=Path, help="one completed process's JSONL file")
    parser.add_argument("--limit", type=int, default=256)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.phase_file.read_text().splitlines() if line.strip()]
    print(json.dumps(summarize_records(records, limit=args.limit), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
