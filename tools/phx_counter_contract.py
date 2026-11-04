"""Check that the phase-1 display-path instrumentation still matches code, capture script and docs.

Why this exists: docs/analysis.md decides which optimisation is worth implementing, but only after
tools/phx_baseline.sh has read the counters on the target laptop. A renamed counter, a deleted knob or a
changed default makes that one capture useless -- the script exits 5, or worse, the numbers no longer mean
what the analysis says they mean. Neither failure can happen on the host that runs CI, and neither can be
noticed without the laptop, so it is caught here instead: this tool compares three sources and fails when
they disagree.

What it reads (and it writes nothing outside --out):
  * src/**                  SYSCTL_* declarations: name, read-only or writable, and the initial value of the
                            variable it points at (that variable, not the macro's `val` argument, is the
                            default a session actually starts with)
  * tools/phx_baseline.sh   the KNOBS/COUNTERS lists the capture reads
  * tools/phxctl/phxboot.sh debug.* names the reference arming script writes
  * docs/analysis.md        the names the analysis promises are readable

Exit codes: 0 the contract holds, 1 at least one violation, 2 usage.

This proves a name/plumbing contract. It proves nothing about the hardware, and it measures nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".m", ".mm"}
CAPTURE_SCRIPT = "tools/phx_baseline.sh"
ARMING_SCRIPT = "tools/phxctl/phxboot.sh"
ANALYSIS_DOC = "docs/analysis.md"

# The knobs docs/analysis.md §7 A/B plan assumes, and the value each has to still start with. The phase-1
# capture is only comparable against itself if these do not move; a changed default changes what "off" means.
EXPECTED_DEFAULTS = {
    "debug.phxfb_alias": 1,
    "debug.phxfb_vbl_staged": 1,
    "debug.nvaccel_iop_sse": 0,
    "debug.nvaccel_iop_damage": 0,   # a new copy path ships off (docs/analysis.md §8)
    "debug.nvaccel_iop_vsync": 0,
    "debug.nvaccel_vm_sticky": 1,
    "debug.phxbos_flush": 0,
    "debug.nvaccel_iop_flip": 0,
}

# Counters the H1-H4 verdict is computed from (docs/analysis.md §5, tools/phx_baseline_report.py). If the
# capture stops reading one of these, the hypotheses can no longer be decided from its output, so a missing
# one is a violation and not a warning.
REQUIRED_FROM_CAPTURE = frozenset({
    "debug.phxfb_vbl_n",
    "debug.phxfb_vbl_late_us_sum",
    "debug.phxfb_vbl_late_us_max",
    "debug.nvaccel_iop_ok",
    "debug.nvaccel_iop_copy_us_sum",
    "debug.nvaccel_iop_copy_skip",
    "debug.nvaccel_iop_blank",
    "debug.nvaccel_iop_fail",
    "debug.nvaccel_iop_gap1",
    "debug.nvaccel_iop_gap2",
    "debug.nvaccel_iop_gap3",
    "debug.nvaccel_iop_gap4",
    "debug.nvaccel_iop_vsync_waits",
    "debug.nvaccel_iop_vsync_late",
})

SYSCTL_MACRO = re.compile(r"\b(SYSCTL_[A-Z0-9_]+)\s*\(")
ALIAS_MACRO = re.compile(r"#[ \t]*define[ \t]+([A-Za-z_]\w*)[ \t]*\(([^)]*)\)[ \t]*(SYSCTL_[A-Z0-9_]+)[ \t]*\(")
LIST_ASSIGNMENT = re.compile(r"^[ \t]*([A-Z_]+)='([^']*)'", re.MULTILINE)
DEBUG_NAME = re.compile(r"debug\.([a-z0-9_]+)")
INTEGER_LITERAL = re.compile(r"[A-Za-z_]\w*")
INITIAL_VALUE = re.compile(
    r"\b(?:(?:static|extern|const|volatile|register|unsigned|signed)\s+)*"
    r"(?:bool|int|long|short|char|SInt8|SInt16|SInt32|SInt64|UInt8|UInt16|UInt32|UInt64|u_int|"
    r"u_int8_t|u_int16_t|u_int32_t|u_int64_t|uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t|size_t)"
    r"\s+(?:\*\s*)?([A-Za-z_]\w*)\s*(?:=\s*(-?\d+))?\s*;"
)


class ContractError(ValueError):
    pass


def balanced_arguments(text, open_index):
    """Split the argument list of the call whose '(' is at open_index, ignoring commas in strings."""
    depth = 0
    quote = None
    arguments = []
    current = []
    index = open_index
    while index < len(text):
        character = text[index]
        if quote:
            current.append(character)
            if character == "\\" and quote != "'":
                index += 1
                if index < len(text):
                    current.append(text[index])
            elif character == quote:
                quote = None
        elif character in "\"'":
            quote = character
            current.append(character)
        elif character == "(":
            depth += 1
            if depth > 1:
                current.append(character)
        elif character == ")":
            depth -= 1
            if depth == 0:
                arguments.append("".join(current))
                return [argument.strip() for argument in arguments]
            current.append(character)
        elif character == "," and depth == 1:
            arguments.append("".join(current))
            current = []
        else:
            current.append(character)
        index += 1
    return None


def inside_define(text, index):
    line_start = text.rfind("\n", 0, index) + 1
    return text[line_start:index].lstrip().startswith("#define")


def initial_values(text):
    """Map each scalar variable declared in this file to its starting value (statics start at zero)."""
    values = {}
    for match in INITIAL_VALUE.finditer(text):
        values.setdefault(match.group(1), int(match.group(2)) if match.group(2) else 0)
    return values


def pointed_variable(arguments):
    for argument in arguments[4:6]:
        found = re.search(r"&([A-Za-z_]\w*)", argument)
        if found:
            return found.group(1)
    return None


def scan_source(root):
    """Every debug.* OID the kernel sources declare, with its default and whether a session may write it."""
    files = [path for path in sorted((root / "src").rglob("*")) if path.suffix in SOURCE_SUFFIXES]
    if not files:
        raise ContractError("no kernel sources found under src/")
    texts = {path: path.read_text(encoding="utf-8", errors="replace") for path in files}
    aliases = {}
    for text in texts.values():
        for match in ALIAS_MACRO.finditer(text):
            aliases[match.group(1)] = match.group(3)
    declared = {}
    for path, text in texts.items():
        relative = path.relative_to(root).as_posix()
        initials = initial_values(text)
        for match in SYSCTL_MACRO.finditer(text):
            if inside_define(text, match.start()):
                continue
            arguments = balanced_arguments(text, match.end() - 1)
            if not arguments or len(arguments) < 5:
                continue
            name = arguments[2]
            if not INTEGER_LITERAL.fullmatch(name):
                continue
            variable = pointed_variable(arguments)
            declared["debug." + name] = {
                "file": relative,
                "macro": match.group(1),
                "writable": "CTLFLAG_RW" in " ".join(arguments[3:]),
                "variable": variable,
                "default": initials.get(variable) if variable else None,
            }
        for macro, underlying in aliases.items():
            for match in re.finditer(r"\b" + re.escape(macro) + r"\s*\(", text):
                if inside_define(text, match.start()):
                    continue
                arguments = balanced_arguments(text, match.end() - 1)
                if not arguments:
                    continue
                name = arguments[0]
                if not INTEGER_LITERAL.fullmatch(name):
                    continue
                declared["debug." + name] = {
                    "file": relative,
                    "macro": underlying,
                    "writable": False,
                    "variable": arguments[1] if len(arguments) > 1 else None,
                    "default": None,
                }
    if not declared:
        raise ContractError("no SYSCTL declarations found under src/")
    return declared


def read_text(root, relative, what):
    path = root / relative
    if not path.is_file():
        raise ContractError(f"{what} is missing: {relative}")
    return path.read_text(encoding="utf-8", errors="replace")


def capture_lists(root):
    """The names tools/phx_baseline.sh reads, split the way the script splits them."""
    text = read_text(root, CAPTURE_SCRIPT, "the phase-1 capture script")
    lists = {name: [item for item in value.split()] for name, value in LIST_ASSIGNMENT.findall(text)}
    for required in ("KNOBS", "COUNTERS"):
        if required not in lists:
            raise ContractError(f"{CAPTURE_SCRIPT} no longer defines {required}")
    knobs = [f"debug.{name}" if not name.startswith("debug.") else name for name in lists["KNOBS"]]
    counters = [f"debug.{name}" if not name.startswith("debug.") else name for name in lists["COUNTERS"]]
    return knobs, counters


def evaluate(root):
    declared = scan_source(root)
    knobs, counters = capture_lists(root)
    captured = knobs + counters
    armed = sorted({"debug." + name for name in DEBUG_NAME.findall(read_text(root, ARMING_SCRIPT, "the arming script"))})
    documented = sorted({"debug." + name for name in DEBUG_NAME.findall(read_text(root, ANALYSIS_DOC, "the analysis document"))})

    violations = []
    warnings = []

    def violation(check, name, detail):
        violations.append({"check": check, "name": name, "detail": detail})

    for name in sorted(set(captured)):
        if name not in declared:
            violation("capture_reads_undeclared_oid", name,
                      f"{CAPTURE_SCRIPT} reads it but no SYSCTL declaration under src/ provides it")
    for name in sorted(set(captured) - set(documented)):
        violation("capture_reads_undocumented_oid", name,
                  f"{CAPTURE_SCRIPT} reads it but {ANALYSIS_DOC} never names it: the analysis and the capture disagree")
    for name in sorted(set(documented) - set(declared)):
        violation("docs_name_undeclared_oid", name,
                  f"{ANALYSIS_DOC} names it but no SYSCTL declaration under src/ provides it")
    for name in armed:
        if name not in declared:
            violation("arming_writes_undeclared_oid", name,
                      f"{ARMING_SCRIPT} writes it but no SYSCTL declaration under src/ provides it")
    for name in sorted(REQUIRED_FROM_CAPTURE - set(captured)):
        violation("verdict_counter_not_captured", name,
                  "the phase-1 verdict needs it but the capture no longer reads it")
    for name in sorted(REQUIRED_FROM_CAPTURE - set(declared)):
        violation("verdict_counter_not_declared", name,
                  "the phase-1 verdict needs it but no source declares it")
    for name, expected in sorted(EXPECTED_DEFAULTS.items()):
        if name not in declared:
            violation("default_knob_not_declared", name, "the phase-1 A/B plan uses it but no source declares it")
            continue
        actual = declared[name]["default"]
        if actual != expected:
            violation("default_changed", name,
                      f"starts at {actual!r}, the phase-1 plan assumes {expected}: an earlier capture is no longer comparable")

    for name in sorted(declared):
        if declared[name]["writable"] and name not in set(documented):
            warnings.append({"check": "writable_oid_undocumented", "name": name,
                             "detail": f"{declared[name]['file']} lets a session write it; {ANALYSIS_DOC} does not mention it"})

    report = {
        "tool": "phx_counter_contract",
        "contract_holds": not violations,
        "sources": {
            "sources": len({entry["file"] for entry in declared.values()}),
            "declared": len(declared),
            "captured": len(set(captured)),
            "documented": len(documented),
            "armed": len(armed),
        },
        "capture": {"knobs": knobs, "counters": counters},
        "defaults": {name: declared[name]["default"] for name in sorted(EXPECTED_DEFAULTS) if name in declared},
        "violations": violations,
        "warnings": warnings,
        "claims": {
            "names_and_defaults_checked": True,
            "hardware_execution_established": False,
            "measured_nothing": True,
        },
        "limitation": ("A name and default contract between the kernel sources, the capture script and the analysis. "
                       "It establishes no counter value: only the target laptop can produce those."),
    }
    return report


def save_report(out, report):
    out = Path(out).absolute()
    if out.exists():
        raise ContractError("output directory exists; choose a fresh one")
    try:
        # Windows has no POSIX mode: asking for 0700 there yields a directory the account cannot write to.
        if os.name == "nt":
            out.mkdir(parents=True)
        else:
            out.mkdir(parents=True, mode=0o700)
        fd = os.open(out / "counter-contract.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2, sort_keys=False) + "\n")
    except OSError:
        raise ContractError("could not write the contract report") from None


def describe(report):
    lines = [
        "phase-1 instrumentation contract",
        "  sources: {sources} files, {declared} OIDs; capture reads {captured}; {documented} documented; {armed} armed".format(
            **report["sources"]),
        "  defaults: " + ", ".join(f"{name}={value}" for name, value in report["defaults"].items()),
    ]
    if report["violations"]:
        lines.append(f"  {len(report['violations'])} violation(s):")
        lines.extend(f"    {item['check']}: {item['name']} -- {item['detail']}" for item in report["violations"])
    else:
        lines.append("  contract holds: every name the capture reads is declared, documented and still defaulted as planned")
    if report["warnings"]:
        lines.append(f"  {len(report['warnings'])} undocumented writable OID(s) (not a failure):")
        lines.extend(f"    {item['name']} -- {item['detail']}" for item in report["warnings"])
    lines.append("  nothing was measured: this is a name/default contract, not hardware evidence")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository root (default: the checkout this tool lives in)")
    parser.add_argument("--out", type=Path, help="new directory for counter-contract.json")
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of prose")
    arguments = parser.parse_args()
    try:
        report = evaluate(arguments.root.absolute())
        if arguments.out:
            save_report(arguments.out, report)
    except ContractError as error:
        parser.exit(2, f"phx_counter_contract: {error}\n")
    if arguments.json:
        print(json.dumps(report, indent=2))
    else:
        print(describe(report))
    return 0 if report["contract_holds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
