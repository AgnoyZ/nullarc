#!/usr/bin/env python3
"""Restore the exact tested AML buffer treatment alongside VBL on R1a.

Private sealed inputs hold the local configuration, firmware preview and full
manifests. Original host contracts retain their original-ACPI restrictions.
There is no installer, GPU probe or ordinary power action in this module.
"""

from collections import Counter
import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


vbl = load("ACPI_VBL_host", Path(__file__).with_name("build34_vbl_resume_host.py"))
base = vbl.base
CONFIG = "OC/config.plist"
AML = "OC/ACPI/SSDT-BFCOPY.aml"
AML_SHA256 = "89029f3d80843e3feafc0d69a11336f564d3621a2003b72af513bad14e5125b3"


def efi_states(value):
    """Admit only one config replacement and one exact added AML file."""
    before, after = value["EFI_accepted_private"], value["EFI_after_private"]
    assert AML not in before and set(after) == set(before) | {AML}
    assert {p for p in before if before[p] != after[p]} == {CONFIG}
    assert after[AML] == {"sha256": AML_SHA256, "bytes": 172}
    for key, manifest, path in (("ACPI-config-before.plist", before, CONFIG),
                                ("ACPI-config-after.plist", after, CONFIG),
                                ("SSDT-BFCOPY.aml", after, AML)):
        assert value["sealed"][key] == manifest[path]["sha256"]
    staged = copy.deepcopy(before)
    staged[AML] = copy.deepcopy(after[AML])
    return {"original": before, "staged": staged, "candidate": after}


def derive_acpi(original, config, kind):
    assert kind in ("contract", "stage")
    result = copy.deepcopy(original)
    assert result["EFI_baseline"] == config["ACPI_input_manifests_private"][kind]
    assert AML not in result["EFI_baseline"]
    assert result["EFI_baseline"][CONFIG] == config["EFI_accepted_private"][CONFIG]
    for path in (CONFIG, AML):
        result["EFI_baseline"][path] = copy.deepcopy(config["EFI_after_private"][path])
    return result


def validate_config(before, after):
    """Preserve every existing setting; append one enabled Patch and Add."""
    original, candidate = plistlib.loads(before), plistlib.loads(after)
    restored = copy.deepcopy(candidate)
    for key in ("Patch", "Add"):
        assert len(candidate["ACPI"][key]) == len(original["ACPI"][key]) + 1
        assert candidate["ACPI"][key][:-1] == original["ACPI"][key]
        assert restored["ACPI"][key].pop()["Enabled"] is True
    assert restored == original
    assert candidate["ACPI"]["Add"][-1]["Path"] == Path(AML).name
    patch = candidate["ACPI"]["Patch"][-1]
    assert patch["TableSignature"] == b"DSDT" and patch["Count"] == 1
    assert patch["Skip"] == 0 and patch["Find"] != patch["Replace"]
    return patch


class ACPIHost(vbl.VBLHost):
    SCOPE_KIND = "R1a-retained-VBL-AML-startup-recovery"

    def validate_efi_contract(self, value):
        efi_states(value)

    def validate_acpi_contract(self, value):
        assert value["ACPI_candidate_enabled"] is True
        assert value["owner_authorized_ACPI_restoration"] is True
        assert value["ACPI_separate_VBL_boot_prerequisite"] is False
        patch = validate_config((self.scope / "ACPI-config-before.plist").read_bytes(),
                                (self.scope / "ACPI-config-after.plist").read_bytes())
        assert base.sha(self.scope / "SSDT-BFCOPY.aml") == AML_SHA256
        preview = load("ACPI_exact_preview", self.scope / "offline-table-preview-private.py")
        tables = plistlib.loads((self.scope / "tables-before-private.plist").read_bytes())
        expected = preview.preview(tables["DSDT"], value["ACPI_original_DSDT_sha256"],
                                   patch["Find"], patch["Replace"])
        assert expected == (self.scope / "DSDT-preview-private.aml").read_bytes()
        assert patch["TableLength"] == len(tables["DSDT"])
        assert patch["OemTableId"] == tables["DSDT"][16:24]

    def __init__(self, directory):
        super().__init__(directory)
        original = self.readonly.derive
        self.readonly.derive = lambda record, config, kind: derive_acpi(
            original(record, config, kind), config, kind)
        self.readonly.acpi_check = self.acpi_check

    def acpi_check(self, *, allow_recovery=False):
        reader = load("ACPI_current_tables", self.scope / "acpi-readback-private.py")
        check = load("ACPI_exact_tables", self.scope / "table-validation-private.py")
        before = plistlib.loads((self.scope / "tables-before-private.plist").read_bytes())
        tables = reader.acpi_tables()
        candidate = (self.scope / "SSDT-BFCOPY.aml").read_bytes()
        if self.boot() == self.config["prepared_boot"] or (
                allow_recovery and tables.get("DSDT") == before["DSDT"]):
            assert set(tables) == set(before) and candidate not in tables.values()
            assert tables["DSDT"] == before["DSDT"]
            assert check.facp_semantics(tables["FACP"]) == check.facp_semantics(before["FACP"])
            assert check.header(tables["RSDT"]) == check.header(before["RSDT"])
            assert len(tables["RSDT"]) == len(before["RSDT"])
            ignored = {"FACP", "RSDT"}
            assert Counter(check.digest(v) for k, v in tables.items() if k not in ignored) == Counter(
                check.digest(v) for k, v in before.items() if k not in ignored)
            return {"loaded_candidate_ACPI": False}
        contract = json.loads((self.scope / "acpi-contract-private.json").read_text())
        return check.validate(tables, before,
                              (self.scope / "DSDT-preview-private.aml").read_bytes(),
                              candidate, contract["withdrawn_SSDT_sha256"])

    def transaction(self):
        return load("ACPI_exact_EFI_transaction", self.scope / "efi-transaction-private.py")

    def check_restore_inputs(self):
        c = self.contract()
        route = load("ACPI_recovery_route", self.readonly.OLD / "internal-route-private.py")
        with route.efi(route.static()) as root:
            self.transaction().state(root, efi_states(c))
        for path, change in c["VBL_changes"].items():
            base.secure(path)
            assert base.sha(path) in (change["before"], change["after"])
            assert base.sha(self.scope / change["backup"]) == change["before"]
        for path, accepted in c["recovery_jobs"].items():
            base.secure(path)
            assert base.sha(path) in (c["jobs"][path], accepted["sha256"])
            assert base.sha(self.scope / accepted["backup"]) == accepted["sha256"]
        watcher = Path(c["watcher_job"])
        if watcher.exists():
            base.secure(watcher)
            assert base.sha(watcher) == c["watcher_job_sha256"]
        pending = Path("/var/db/phxboot.pending")
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b""
        return c

    def restore(self):
        c = self.check_restore_inputs()
        route = load("ACPI_restore_route", self.readonly.OLD / "internal-route-private.py")
        with route.efi(route.static(), writable=True) as root:
            self.transaction().restore_efi(root, efi_states(c),
                (self.scope / "ACPI-config-before.plist").read_bytes(),
                (self.scope / "ACPI-config-after.plist").read_bytes())
        for path, change in c["VBL_changes"].items():
            vbl.atomic_image(path, self.scope / change["backup"],
                             (change["before"], change["after"]))
        self.restore_jobs()
        self.retire_watcher()
        pending = Path("/var/db/phxboot.pending")
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b""
            pending.unlink()
        subprocess.run(["/usr/sbin/sysctl", "-w", "debug.phxfb_hold=0"],
                       capture_output=True, timeout=5)
        subprocess.run(["/bin/sync"], check=True, timeout=15)

    def verify_restore(self):
        accepted = load("ACPI_independent_R1a", Path(self.config["accepted_scope"]) / "owner-startup-private.py")
        d, k, c = accepted.build()
        d.r.verify_disk("candidate")
        with d.r.efi(d.r.static()) as root:
            assert d.r.files(root) == c["EFI_after_private"] == self.config["EFI_accepted_private"]
            subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(root / d.r.ACTIVE)],
                           capture_output=True, check=True, timeout=20)
        assert d.plugin.files(d.plugin.LIVE) == k["plugin_after"]
        accepted.cache_check()
        # Disk restoration cannot remove already loaded AML. Validate either
        # exact known table set here; ordinary candidate admission stays strict.
        self.acpi_check(allow_recovery=True)
        assert d.r.support.security() == k["security"]
        for path, digest in c["jobs"].items():
            base.secure(path)
            assert base.sha(path) == digest
        assert not Path(self.config["watcher_job"]).exists()
        return True

    verify = verify_restore


def main():
    os.umask(0o077)
    host = ACPIHost(Path(__file__).resolve().parent)
    action = sys.argv[1]
    if action == "watch":
        host.watch()
    elif action == "recover":
        host.note_failure("protected-startup-failure")
    elif action == "worker":
        host.worker(sys.argv[2])
    else:
        host.supervise(action)


if __name__ == "__main__":
    main()
