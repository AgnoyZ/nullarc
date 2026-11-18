#!/usr/bin/env python3
"""Derive exact EFI expectations for one owner-authorized, local S5 trial.

No EFI contents, firmware, deployment, power action or hardware access lives
here. Historical records remain unchanged. The existing verifier continues
to compare real file manifests against the explicitly derived expectations.
"""

import copy
import hashlib
import json
import re
from pathlib import Path


CONFIG = "OC/config.plist"
AML = "OC/ACPI/SSDT-S5-PCIe.aml"
KIND = "build34-owner-s5-pcie-v1"
STATES = {"original", "staged", "candidate"}
KEYS = {
    "kind", "contract_before_sha256", "stage_before_sha256",
    "contract_manifest_before_sha256", "stage_manifest_before_sha256",
    "config_before", "config_after", "aml_after",
}


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def manifest_digest(manifest):
    return digest_bytes(json.dumps(manifest, sort_keys=True,
                                   separators=(",", ":")).encode())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_string(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_scope(scope):
    require(isinstance(scope, dict) and set(scope) == KEYS, "unexpected S5 scope fields")
    require(scope["kind"] == KIND, "wrong S5 scope kind")
    for key in KEYS - {"kind", "config_before", "config_after", "aml_after"}:
        require(sha256_string(scope[key]), "invalid scope digest: " + key)
    for key in ("config_before", "config_after", "aml_after"):
        record = scope[key]
        require(isinstance(record, dict) and set(record) == {"sha256", "bytes"},
                "unexpected file record: " + key)
        require(sha256_string(record["sha256"]), "invalid file digest: " + key)
        require(type(record["bytes"]) is int and 0 < record["bytes"] <= 4 * 1024 * 1024,
                "invalid file length: " + key)
    require(scope["config_before"]["sha256"] != scope["config_after"]["sha256"],
            "configuration must actually change")


def select_state(observed, scope):
    """Identify only the two scoped paths; the full verifier must still run."""
    validate_scope(scope)
    if observed.get(CONFIG) == scope["config_before"]:
        if AML not in observed:
            return "original"
        if observed[AML] == scope["aml_after"]:
            return "staged"
    elif (observed.get(CONFIG) == scope["config_after"] and
          observed.get(AML) == scope["aml_after"]):
        return "candidate"
    raise ValueError("unrecognized S5 configuration/table state")


def derive_manifest(before, scope, expected_digest, state="candidate"):
    validate_scope(scope)
    require(state in STATES, "wrong S5 state")
    require(isinstance(before, dict) and manifest_digest(before) == expected_digest,
            "historical EFI manifest differs")
    require(before.get(CONFIG) == scope["config_before"], "configuration baseline differs")
    require(AML not in before, "S5 table already present in baseline")
    after = copy.deepcopy(before)
    if state == "candidate":
        after[CONFIG] = copy.deepcopy(scope["config_after"])
    if state != "original":
        after[AML] = copy.deepcopy(scope["aml_after"])
    return after


def derive_record(before, scope, kind, state="candidate"):
    require(kind in ("contract", "stage"), "wrong historical record kind")
    require(isinstance(before, dict) and "EFI_baseline" in before, "missing EFI manifest")
    after = copy.deepcopy(before)
    after["EFI_baseline"] = derive_manifest(
        before["EFI_baseline"], scope, scope[kind + "_manifest_before_sha256"], state)
    return after


def bind_route(route, scope, state="candidate"):
    """Extend only expected manifests; keep file hashing and checks untouched."""
    validate_scope(scope)
    require(state in STATES, "wrong S5 state")
    require(not getattr(route, "_owner_s5_scope_bound", False), "S5 scope already bound")
    frozen_scope = copy.deepcopy(scope)
    for name, key in (("contract-private.json", "contract_before_sha256"),
                      ("stage-private.json", "stage_before_sha256")):
        require(digest_bytes((Path(route.D) / name).read_bytes()) == frozen_scope[key],
                "historical input changed: " + name)
    original_static, original_read = route.static, route.read

    def scoped_static(*args, **kwargs):
        return derive_record(original_static(*args, **kwargs), frozen_scope, "contract", state)

    def scoped_read(name, *args, **kwargs):
        result = original_read(name, *args, **kwargs)
        if name == "stage-private.json":
            return derive_record(result, frozen_scope, "stage", state)
        return result

    # Verify both derived records before changing any in-memory route function.
    derive_record(original_static(), frozen_scope, "contract", state)
    derive_record(original_read("stage-private.json"), frozen_scope, "stage", state)
    route.static, route.read = scoped_static, scoped_read
    route._owner_s5_scope_bound = True
    route._owner_s5_scope_state = state
