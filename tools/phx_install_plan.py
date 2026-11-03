"""Write the operator's install plan for these kexts into an OpenCore EFI — and write nothing else.

To measure anything (docs/analysis.md §7) the kexts have to be installed, and installation is exactly what this
repository is not allowed to do: it must not deploy drivers, touch the internal disk's EFI, reset NVRAM or
weaken OS security. So this tool is a planner with **no apply mode**. It reads an existing `config.plist`,
checks that the bundles really are the kexts they claim to be, and emits the exact steps for a human, each one
revertible, plus the rollback. It never writes the plist, the EFI partition, NVRAM, a sysctl or a kext.

Two consequences it states instead of hiding:
  * The steps it writes are the OpenCore part only. With those alone the driver will not load: upstream's
    install needs AMFI weakened (`amfi=0x80 amfi_get_out_of_my_way=0x1 -amfipassbeta`), `csr-active-config`
    changed and `SecureBootModel` disabled (docs/INSTALL.md §1). Those are listed as operator decisions —
    security state this repository does not change for you — not as steps.
  * `PhxAccel.kext` is not an OpenCore kext (upstream builds it into the auxiliary kernel collection from
    `/Library/Extensions`), so it is reported, never planned.

  python3 tools/phx_install_plan.py --efi-root /Volumes/OC/EFI --kext build/PhxBringup.kext --out build/plan

Exit codes: 0 plan written or printed, 2 usage, 3 refused (the layout, a bundle or a digest is not what it must
be). Nothing here has ever run on a Mac: this is a text plan and a set of refusals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_artifacts  # noqa: E402  (the binary check that already exists in this repository)

BOOT_ARG = "phx780m=1"
BOOT_ARGS_GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
MIN_KERNEL = "25.0.0"

# Identifier -> how the bundle is installed. Only the OpenCore ones can be planned here.
OPENCORE_KEXTS = {
    "org.drip.PhxBringup": "PhxBringup.kext",
    "org.drip.PhxProbe": "PhxProbe.kext",
}
OTHER_KEXTS = {
    "com.luuumi.PhxAccel": (
        "PhxAccel.kext is not an OpenCore kext: upstream builds it into the auxiliary kernel collection from "
        "/Library/Extensions (docs/INSTALL.md §2), which is a system location this repository does not write "
        "and which needs AMFI weakened first. Installing it is the owner's decision, not a step of this plan."
    ),
}

# Boot-argument and config tokens that weaken OS security. The plan reports them; it never adds them.
SECURITY_TOKENS = {
    "amfi=": "AMFI enforcement level",
    "amfi_get_out_of_my_way": "AMFI bypass",
    "amfipass": "AMFIPass.kext argument",
}

# This repository never writes these locations (docs/INSTALL.md, AGENTS.md).
REFUSED_PREFIXES = ("/System", "/Library", "/usr", "/Applications", "/private/var/db", "/private/var/vm")


class PlanError(ValueError):
    pass


def refused_location(path):
    """The macOS system location this path is under, if any.

    A Windows drive prefix is dropped first: the list is about where a Mac install may write, and giving the same
    answer on a developer's checkout is what keeps this refusal testable there.
    """
    text = Path(path).as_posix()
    if len(text) > 2 and text[1] == ":":
        text = text[2:]
    return next((prefix for prefix in REFUSED_PREFIXES if text == prefix or text.startswith(prefix + "/")), None)


def load_config(efi_root):
    prefix = refused_location(efi_root)
    if prefix:
        raise PlanError(f"{efi_root} is under {prefix}: this repository never writes a system location")
    if not efi_root.is_dir():
        raise PlanError(f"EFI root is not a directory: {efi_root}")
    config_path = efi_root / "EFI" / "OC" / "config.plist"
    if not config_path.is_file():
        raise PlanError(f"no OpenCore config at {config_path}")
    try:
        raw = config_path.read_bytes()
        config = plistlib.loads(raw)
    except (OSError, plistlib.InvalidFileException) as error:
        raise PlanError(f"{config_path} is not a readable property list ({error.__class__.__name__})") from None
    if not isinstance(config, dict):
        raise PlanError(f"{config_path} is not a configuration dictionary")
    kernel = config.get("Kernel")
    if not isinstance(kernel, dict) or not isinstance(kernel.get("Add"), list):
        raise PlanError(f"{config_path} has no Kernel > Add array: this is not an OpenCore configuration")
    if not isinstance(config.get("NVRAM"), dict):
        raise PlanError(f"{config_path} has no NVRAM dictionary")
    return config_path, config, raw


def boot_args(config):
    section = config.get("NVRAM", {}).get("Add", {})
    entry = section.get(BOOT_ARGS_GUID) if isinstance(section, dict) else None
    if not isinstance(entry, dict):
        return ""
    value = entry.get("boot-args")
    return value if isinstance(value, str) else ""


def blocked_kernels(config):
    entries = config.get("Kernel", {}).get("Block", [])
    return [entry.get("Identifier", "?") for entry in entries
            if isinstance(entry, dict) and entry.get("Enabled", False)]


def security_state(config):
    args = boot_args(config)
    present = {token: description for token, description in SECURITY_TOKENS.items() if token in args}
    nvram = config.get("NVRAM", {}).get("Add", {})
    entry = nvram.get(BOOT_ARGS_GUID, {}) if isinstance(nvram, dict) else {}
    csr = entry.get("csr-active-config") if isinstance(entry, dict) else None
    if isinstance(csr, (bytes, bytearray)):
        csr = csr.hex()
    secure_boot = config.get("Misc", {}).get("Security", {}).get("SecureBootModel")
    return {
        "boot_args": args,
        "weakening_tokens_present": present,
        "csr_active_config": csr,
        "secure_boot_model": secure_boot,
        "blocked_kernel_extensions": blocked_kernels(config),
    }


def tree_digest(bundle):
    digest = hashlib.sha256()
    for path in sorted(item for item in bundle.rglob("*") if item.is_file()):
        relative = path.relative_to(bundle).as_posix()
        data = path.read_bytes()
        digest.update(f"{relative}\0{len(data)}\0".encode())
        digest.update(data)
    return digest.hexdigest()


def inspect_bundle(path):
    bundle = Path(path).expanduser().absolute()
    if not bundle.is_dir() or bundle.suffix != ".kext":
        raise PlanError(f"{bundle} is not a .kext directory")
    info_path = bundle / "Contents/Info.plist"
    if not info_path.is_file():
        raise PlanError(f"{bundle} has no Contents/Info.plist")
    try:
        info = plistlib.loads(info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        raise PlanError(f"{bundle}/Contents/Info.plist is not a property list") from None
    identifier = info.get("CFBundleIdentifier") if isinstance(info, dict) else None
    if identifier not in OPENCORE_KEXTS and identifier not in OTHER_KEXTS:
        raise PlanError(f"{bundle} declares identifier {identifier!r}, which is not one of this project's kexts")
    try:
        binary = verify_artifacts.inspect_kext(bundle, identifier)
    except (OSError, ValueError) as error:
        raise PlanError(f"{bundle} is not a usable kext bundle: {error}") from None
    return {
        "path": str(bundle),
        "name": bundle.name,
        "identifier": identifier,
        "install": "opencore" if identifier in OPENCORE_KEXTS else "operator-decision",
        "executable": info.get("CFBundleExecutable"),
        "macho": binary,
        "tree_sha256": tree_digest(bundle),
    }


def existing_entries(config):
    entries = {}
    for entry in config.get("Kernel", {}).get("Add", []):
        if isinstance(entry, dict) and isinstance(entry.get("BundlePath"), str):
            entries[entry["BundlePath"]] = entry
    return entries


def plan(efi_root, bundles, expected_digests, config_path, config):
    entries = existing_entries(config)
    state = security_state(config)
    args = state["boot_args"]
    steps, operator_decisions, warnings, notes = [], [], [], []

    for token, description in state["weakening_tokens_present"].items():
        notes.append(f"boot-args already carry `{token}` ({description}); this plan leaves it exactly as it is.")
    if state["csr_active_config"] not in (None, b"", "00000000"):
        notes.append(f"`csr-active-config` is already set to {state['csr_active_config']}; this plan leaves it as is.")
    if state["secure_boot_model"] not in (None, "Default"):
        notes.append(f"`SecureBootModel` is already {state['secure_boot_model']}; this plan leaves it as is.")
    if state["blocked_kernel_extensions"]:
        warnings.append("Kernel > Block still refuses: " + ", ".join(str(item) for item in state["blocked_kernel_extensions"]))

    opencore = [bundle for bundle in bundles if bundle["install"] == "opencore"]
    if not opencore:
        raise PlanError("none of the given bundles is an OpenCore kext, so there is nothing to plan")

    for bundle in bundles:
        if bundle["install"] != "opencore":
            operator_decisions.append(OTHER_KEXTS[bundle["identifier"]])
            continue
        expected = expected_digests.get(bundle["name"])
        if expected and expected.lower() != bundle["tree_sha256"]:
            raise PlanError(f"{bundle['name']} digest is {bundle['tree_sha256']}, not the expected {expected}")
        existing = entries.get(bundle["name"])
        if existing:
            enabled = "enabled" if existing.get("Enabled") else "disabled"
            notes.append(f"Kernel > Add already lists {bundle['name']} ({enabled}); verify its fields, do not add a second entry.")
        if (efi_root / "EFI" / "OC" / "Kexts" / bundle["name"]).exists():
            warnings.append(f"{efi_root}/EFI/OC/Kexts/{bundle['name']} already exists and would be replaced; "
                            "keep a copy if it is not the same build.")

    if BOOT_ARG not in args.split():
        needs_boot_argument = True
    else:
        needs_boot_argument = False
        notes.append(f"boot-args already contain `{BOOT_ARG}`; verify it and leave the rest of the arguments alone.")

    missing_security = [token for token in SECURITY_TOKENS if token not in args]
    if missing_security:
        operator_decisions.append(
            "docs/INSTALL.md §1 requires AMFI weakened (`amfi=0x80 amfi_get_out_of_my_way=0x1 -amfipassbeta`, "
            "with AMFIPass.kext), `csr-active-config` set and `SecureBootModel` disabled before PhxBringup will "
            "load. Without them the steps below install the files and the driver still will not attach. This "
            "repository does not change those settings for you: turning library validation off system-wide has "
            "real costs (FairPlay video, apps that check signatures), and that trade is the owner's to make, "
            "deliberately, with the rollback below at hand."
        )

    steps.append({
        "title": "Make the return path first",
        "detail": f"Copy {config_path.name} to {config_path.name}.phx-backup-<UTC date-time> beside it, then confirm "
                  "you can open the copy. Confirm the EFI you are editing is the external disk's, never the "
                  "internal disk's.",
        "performed_by": "operator",
    })
    steps.append({
        "title": "Copy the kext bundle(s) into the EFI",
        "detail": "; ".join(f"{bundle['name']} (sha256 {bundle['tree_sha256']}) from {bundle['path']} to "
                            f"{efi_root}/EFI/OC/Kexts/" for bundle in opencore),
        "performed_by": "operator",
    })
    steps.append({
        "title": "Add the Kernel > Add entries",
        "detail": "; ".join(
            f"{bundle['name']}: BundlePath {bundle['name']}, ExecutablePath Contents/MacOS/{bundle['executable']}, "
            f"PlistPath Contents/Info.plist, MinKernel {MIN_KERNEL}, Enabled true"
            for bundle in opencore) + ". Place them after Lilu and VirtualSMC, and edit the plist with a property "
               "list editor so the file stays a valid plist.",
        "performed_by": "operator",
    })
    steps.append({
        "title": "Add the boot argument" if needs_boot_argument else "Verify the boot argument",
        "detail": f"Under NVRAM > Add > {BOOT_ARGS_GUID} append `{BOOT_ARG}` to `boot-args`, leaving every existing "
                  "argument in place; add the same key under NVRAM > Delete so the new value takes effect."
                  if needs_boot_argument else "Nothing to change.",
        "performed_by": "operator",
    })
    steps.append({
        "title": "Reboot and watch the driver attach",
        "detail": "In Terminal, `ioreg -l | grep phx-build` prints a line once PhxBringup is loaded. It cannot "
                  "print anything before the security settings above exist — that is the expected result, not a "
                  "failure of the copy.",
        "performed_by": "operator",
    })
    steps.append({
        "title": "Capture phase 1",
        "detail": "sh tools/phx_baseline.sh --out /Users/Shared/phx-baseline-$(date +%Y%m%d-%H%M) --window 60 "
                  "--samples 3, then python3 tools/phx_baseline_report.py baseline=<that directory> "
                  "--out build/verdict (docs/analysis.md §7). This is the step that produces evidence.",
        "performed_by": "operator",
    })

    for number, step in enumerate(steps, start=1):
        step["order"] = number

    return {
        "tool": "phx_install_plan",
        "mode": "plan-only",
        "efi_root": str(efi_root),
        "config": str(config_path),
        "config_sha256": hashlib.sha256((config_path).read_bytes()).hexdigest(),
        "kexts": bundles,
        "security_state": state,
        "notes": notes,
        "warnings": warnings,
        "operator_decisions": operator_decisions,
        "steps": steps,
        "rollback": [
            "Restore the backup over config.plist, and delete the Kernel > Add entries and the copied kext "
            "folders from EFI/OC/Kexts.",
            f"Remove `{BOOT_ARG}` from boot-args (and its NVRAM > Delete key); every other argument stays.",
            "If the panel never comes up, boot the external disk's recovery entry; the driver has a display-level "
            "kill switch (`$G/phxboot-off`, `nvram -d phxfb-boot`) for the case where it armed.",
            "Nothing here touches NVRAM, BIOS, the internal disk or an installed system: the only files that "
            "changed are the ones listed above, and they are in the external disk's EFI.",
        ],
        "claims": {
            "config_read": True,
            "config_written": False,
            "efi_written": False,
            "nvram_written": False,
            "kext_installed": False,
            "hardware_execution_established": False,
        },
        "limitations": [
            "A plan and a set of refusals. It has never run on a Mac; the plist layout is checked structurally, "
            "not against a real OpenCore build.",
            "It does not validate that the kexts run, and it deliberately does not plan the security changes "
            "upstream's install requires.",
            "Binary validity is whatever `tools/verify_artifacts.py` checks: a thin x86_64 Mach-O kext bundle, "
            "not a loadable, signed, working driver.",
        ],
    }


def render_markdown(result):
    lines = [
        "# Install plan (nothing was written)", "",
        f"EFI root: `{result['efi_root']}`  ",
        f"Config: `{result['config']}` (sha256 `{result['config_sha256'][:16]}…`)", "",
        "This is a plan for a human. The tool read the configuration and wrote no file, no NVRAM key and no kext.",
        "",
    ]
    if result["operator_decisions"]:
        lines += ["## Operator decisions (not steps)", ""]
        lines += [f"- {item}" for item in result["operator_decisions"]]
        lines.append("")
    if result["warnings"]:
        lines += ["## Warnings", ""] + [f"- {item}" for item in result["warnings"]] + [""]
    if result["notes"]:
        lines += ["## What the configuration already has", ""] + [f"- {item}" for item in result["notes"]] + [""]
    lines += ["## Steps", "", "| # | step | do |", "| --- | --- | --- |"]
    for step in result["steps"]:
        lines.append(f"| {step['order']} | {step['title']} | {step['detail']} |")
    lines += ["", "## Rollback", ""] + [f"{number}. {item}" for number, item in enumerate(result["rollback"], 1)]
    lines += ["", "## What this plan is not", ""] + [f"- {item}" for item in result["limitations"]]
    return "\n".join(lines) + "\n"


def write_outputs(out, result):
    out = Path(out).absolute()
    if out.exists():
        raise PlanError("output directory exists; choose a fresh one")
    try:
        if os.name == "nt":
            out.mkdir(parents=True)
        else:
            out.mkdir(parents=True, mode=0o700)
        (out / "plan.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        (out / "plan.md").write_text(render_markdown(result), encoding="utf-8")
    except OSError:
        raise PlanError("could not write the plan") from None


def parse_digest(argument):
    if "=" not in argument:
        raise PlanError(f"--expect-sha256 wants NAME=HEX, got {argument!r}")
    name, _, value = argument.partition("=")
    return name.strip(), value.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--efi-root", type=Path, required=True,
                        help="the external disk's EFI directory (the one holding EFI/OC/config.plist)")
    parser.add_argument("--kext", type=Path, action="append", default=[], required=True,
                        help="a built .kext bundle to install; repeatable")
    parser.add_argument("--expect-sha256", action="append", default=[], metavar="NAME=HEX",
                        help="expected tree digest of a bundle, e.g. PhxBringup.kext=abc…; repeatable")
    parser.add_argument("--out", type=Path, help="new directory for plan.json and plan.md")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON instead of markdown")
    arguments = parser.parse_args()
    try:
        efi_root = arguments.efi_root.expanduser().absolute()
        config_path, config, _ = load_config(efi_root)
        expected = dict(parse_digest(item) for item in arguments.expect_sha256)
        bundles = [inspect_bundle(path) for path in arguments.kext]
        result = plan(efi_root, bundles, expected, config_path, config)
        if arguments.out:
            write_outputs(arguments.out, result)
    except PlanError as error:
        parser.exit(3, f"phx_install_plan: {error}\n")
    if arguments.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
