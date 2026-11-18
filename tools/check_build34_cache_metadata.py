#!/usr/bin/env python3
"""Read-only comparison of complete kmutil --show-prelink-info captures.

Image-UUID enumeration alone misses changes to automatic matching and bundle
location. This gate also preserves every Info.plist-derived policy field and
the links to the unchanged boot/system collections. It never builds, installs
or loads a collection and never prints private identifiers or raw metadata.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re


class ValidationError(ValueError):
    pass


RELOCATIONS = frozenset({
    "_PrelinkExecutableLoadAddr", "_PrelinkExecutableSourceAddr", "_PrelinkKmodInfo",
})
IMAGE_FIELDS = frozenset({"OSBundleUUID", "_PrelinkExecutableSize"})


def parse_capture(raw):
    fragments = re.findall(rb"<\?xml.*?</plist>", raw, re.S)
    if len(fragments) != 3:
        raise ValidationError("require complete boot/system/auxiliary metadata")
    collections = []
    entries = {}
    for fragment in fragments:
        try:
            collection = plistlib.loads(fragment)
        except Exception as error:
            raise ValidationError("invalid collection plist") from error
        if not isinstance(collection, dict):
            raise ValidationError("collection is not a dictionary")
        rows = collection.get("_PrelinkInfoDictionary")
        if not isinstance(rows, list):
            raise ValidationError("missing collection entry list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError("invalid collection entry")
            key = row.get("CFBundleIdentifier")
            if not isinstance(key, str) or not key or key in entries:
                raise ValidationError("missing or duplicate bundle identifier")
            entries[key] = row
        collections.append(collection)
    return collections, entries


def compare_captures(baseline, candidate, image_changes=(), expected_records=416,
                     expected_codeless=29):
    old_collections, old = parse_capture(baseline)
    new_collections, new = parse_capture(candidate)
    expected_changes = set(image_changes)
    if len(old) != expected_records or len(new) != expected_records:
        raise ValidationError("complete collection record count differs")
    if old.keys() != new.keys():
        raise ValidationError("collection bundle set differs")
    for values in (old, new):
        if sum("OSBundleUUID" not in row for row in values.values()) != expected_codeless:
            raise ValidationError("codeless record count differs")
    for index, (before, after) in enumerate(zip(old_collections, new_collections)):
        if {x["CFBundleIdentifier"] for x in before["_PrelinkInfoDictionary"]} != {
                x["CFBundleIdentifier"] for x in after["_PrelinkInfoDictionary"]}:
            raise ValidationError("bundle moved between collections")
        allowed = {"_PrelinkInfoDictionary"}
        if index == 2:
            allowed.add("_PrelinkKCID")
        for key in sorted(before.keys() | after.keys()):
            if key not in allowed and (key not in before or key not in after or
                                       before[key] != after[key]):
                raise ValidationError("collection metadata changed: " + key)
    actual_changes = set()
    missing = object()
    for bundle, before in old.items():
        after = new[bundle]
        if before.get("OSBundleUUID", missing) != after.get("OSBundleUUID", missing):
            actual_changes.add(bundle)
        allowed = RELOCATIONS | (IMAGE_FIELDS if bundle in expected_changes else frozenset())
        for key in sorted(before.keys() | after.keys()):
            if key not in allowed and before.get(key, missing) != after.get(key, missing):
                raise ValidationError("bundle metadata changed: " + bundle + ": " + key)
    if actual_changes != expected_changes:
        raise ValidationError("changed image set differs from the exact allowance")
    return {
        "status": "passed", "combined_records": len(new),
        "codeless_records": expected_codeless,
        "changed_images": sorted(actual_changes),
        "automatic_matching_and_explicit_load_policy_preserved": True,
        "bundle_paths_personalities_and_dependencies_preserved": True,
        "boot_and_system_collection_links_preserved": True,
        "installed": False, "loaded": False, "GPU_submissions": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--allow-image-change", action="append", default=[])
    args = parser.parse_args()
    old, new = args.baseline.read_bytes(), args.candidate.read_bytes()
    try:
        result = compare_captures(old, new, args.allow_image_change)
    except ValidationError as error:
        print(json.dumps({"status": "refused", "reason": str(error)}))
        return 1
    result.update(baseline_capture_sha256=hashlib.sha256(old).hexdigest(),
                  candidate_capture_sha256=hashlib.sha256(new).hexdigest())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
