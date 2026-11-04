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


if __name__ == "__main__":
    unittest.main()
