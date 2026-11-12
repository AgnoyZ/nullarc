"""The reference workflow is not this repository's entry point, and that is asserted, not remembered.

`tools/phxctl/{bringup3.sh, bringup5.sh, full.sh, phxboot.sh}` are upstream's reference scripts: they arm reboot
watchdogs, write NVRAM and sysctls, and embed reference-machine constants and firmware byte offsets. This branch
replaces them (`tools/phx_boot_gate.sh` for staged bring-up, `phxctl`/`mesboot` subcommands, `tools/phx_baseline.sh`
for the read-only capture, `tools/phx_install_plan.py` for a plan a human executes).

The audit's oldest finding — literal firmware payload offsets that load garbage for a different firmware set — lives
only in those scripts. This test keeps the substitution honest: each script says it is not run here, no workflow runs
one, and the audited entry points only mention them in comments.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SCRIPTS = (
    "tools/phxctl/bringup3.sh",
    "tools/phxctl/bringup5.sh",
    "tools/phxctl/full.sh",
    "tools/phxctl/phxboot.sh",
)
AUDITED_ENTRY_POINTS = (
    "tools/phx_boot_gate.sh",
    "tools/phx_baseline.sh",
    "tools/phx_install_plan.py",
)
BANNER = "NOT RUN BY THIS REPOSITORY"


class ReferenceScriptTests(unittest.TestCase):
    def test_each_reference_script_says_it_is_not_run_here(self):
        for name in REFERENCE_SCRIPTS:
            head = (ROOT / name).read_text(encoding="utf-8", errors="replace").splitlines()[:6]
            self.assertTrue(any(BANNER in line for line in head),
                            f"{name} does not carry the '{BANNER}' banner in its first lines")

    def test_no_workflow_runs_a_reference_script(self):
        workflows = sorted((ROOT / ".github/workflows").glob("*.yml"))
        self.assertTrue(workflows, "no workflows found")
        for workflow in workflows:
            text = workflow.read_text(encoding="utf-8")
            for name in REFERENCE_SCRIPTS:
                self.assertNotIn(Path(name).name, text,
                                 f"{workflow.relative_to(ROOT)} runs {Path(name).name}; the reference workflow is not "
                                 "an entry point in this repository")

    def test_the_audited_entry_points_only_mention_them_in_comments(self):
        for name in AUDITED_ENTRY_POINTS:
            for number, line in enumerate((ROOT / name).read_text(encoding="utf-8").splitlines(), start=1):
                if not any(Path(script).name in line for script in REFERENCE_SCRIPTS):
                    continue
                stripped = line.lstrip()
                self.assertTrue(stripped.startswith("#") or stripped.startswith("*") or stripped.startswith('"'),
                                f"{name}:{number} mentions a reference script outside a comment: {stripped}")

    def test_the_audited_firmware_path_loads_the_generated_steps(self):
        # The extents come from the parsed headers (tools/firmware_manifest.py) through the generated profile, not
        # from literals in the loader; see docs/BRINGUP-AUDIT.md's RadeArc section for why this matters.
        loader = (ROOT / "tools/phxctl/phxctl.c").read_text(encoding="utf-8")
        self.assertIn("phxFirmwareSteps", loader)
        self.assertIn("phxFirmwareFiles", loader)
        manifest = (ROOT / "tools/firmware_manifest.py").read_text(encoding="utf-8")
        self.assertIn("payload_offset", manifest)

    def test_the_layout_gate_stays_in_the_audited_tool(self):
        # mesboot programs the reference machine's physical addresses; the gate that checks them against what the
        # driver publishes is what keeps that from happening on a different machine (docs/BRINGUP-AUDIT.md).
        tool = (ROOT / "tools/phxctl/mesboot.c").read_text(encoding="utf-8")
        self.assertIn("layout_from_driver", tool)
        self.assertIn("PHX_LAYOUT_REFERENCE", tool)
        # The layout must be variables the gate can replace, never macros a reader might trust as facts.
        for line in tool.splitlines():
            self.assertNotIn("#define VRAM_MC", line)
            self.assertNotIn("#define FB_PA", line)
        # The audited subcommand refuses to combine the reference override with its explicit layouts.
        self.assertIn('"PHX_LAYOUT_REFERENCE"', tool)
        overrides = [line for line in tool.splitlines() if "const char *overrides[]" in line]
        self.assertTrue(overrides, "the sched-query override list disappeared")
        self.assertIn("PHX_LAYOUT_REFERENCE", overrides[0])

    def test_the_layout_gate_is_refused_where_the_layout_is_checked(self):
        # Both modes keep the gate in the common open path; only explicit commands may derive target addresses.
        tool = (ROOT / "tools/phxctl/mesboot.c").read_text(encoding="utf-8")
        open_kext = tool.split("static int open_kext(int explicit_layout)", 1)[1].split("static uint32_t rd(", 1)[0]
        self.assertIn("layout_from_driver(svc, explicit_layout)", open_kext)
        self.assertIn("IOServiceClose(conn); return -1;", open_kext)
        self.assertEqual(tool.count("if (open_kext(1)) return 1;"), 3)
        self.assertEqual(tool.count("if (open_kext(0)) return 1;"), 1)


if __name__ == "__main__":
    unittest.main()
