"""Keep `docs/SUPPORT-STATUS.md` mechanically checkable instead of a page that quietly rots.

The table answers "does this work on my machine?" per area, and its value depends on two things that are easy to
lose in editing: the evidence-class vocabulary stays the five classes the document defines, and every citation in
the table is a path that exists. Both were prose promises until now; `test_phase1_baseline_shell.py` and
`test_baseline_report.py` cover the other half — that the capture and the verdict tool actually produce the fields
the table's "what would move it up" column names.

The last assertion is the one worth keeping: a row may only say `target-verified` when a record under
`docs/validation/` exists to back it. Today there is none, so no row may — the day one is added, the assertion
still holds, and the reverse mistake (claiming the laptop ran something it did not) fails here.
"""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/SUPPORT-STATUS.md"
CAPTURE = ROOT / "tools/phx_baseline.sh"
RECORD_DIR = ROOT / "docs/validation"

CLASSES = ("target-verified", "host-verified", "policy-asserted", "not implemented", "unknown")
# Branch names and CI job names appear in backticks but are not paths.
NOT_A_PATH = {"downstream/780m-tahoe"}
# The mapping table has one meta row (the knob values describe every row), which is not a row name.
META_ROW_NAMES = {"every row"}
FIELD_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def table_rows(text):
    """Yield the cell lists of the support table, skipping the header and the separator."""
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| area ") or set(line) <= set("|- "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) == 5:
            yield cells


def cited_paths(text):
    for token in re.findall(r"`([^`]+)`", text):
        candidate = token.split(" ")[0]
        if candidate in NOT_A_PATH or "://" in candidate:
            continue
        if candidate.startswith("debug.") or candidate.startswith("phx-"):
            continue
        if candidate.endswith((".md", ".py", ".json", ".sh", ".hpp", ".h", ".cpp")) or "/" in candidate:
            yield candidate


class SupportStatusTests(unittest.TestCase):
    def setUp(self):
        self.text = STATUS.read_text(encoding="utf-8")
        self.rows = list(table_rows(self.text))

    def test_the_table_has_rows(self):
        self.assertGreater(len(self.rows), 15, "the support table lost its rows")

    def test_every_row_uses_a_defined_evidence_class(self):
        for area, _, evidence, _, _ in self.rows:
            plain = evidence.replace("`", "")
            self.assertTrue(any(plain.startswith(certainty) for certainty in CLASSES),
                            f"{area}: evidence class '{evidence}' is not one of {CLASSES}")

    def test_every_cited_path_exists(self):
        missing = sorted({path for path in cited_paths(self.text)
                          if not (ROOT / path.rstrip("/")).exists()})
        self.assertEqual(missing, [], f"docs/SUPPORT-STATUS.md cites paths that do not exist: {missing}")

    def test_no_row_claims_target_verification_without_a_record(self):
        records = sorted(RECORD_DIR.glob("*.json")) if RECORD_DIR.is_dir() else []
        claims = [area for area, _, evidence, _, _ in self.rows
                  if evidence.replace("`", "").startswith("target-verified")]
        if claims and not records:
            self.fail(f"{claims} claim target verification, but docs/validation/ holds no record")

    def test_every_capture_field_the_table_promises_is_written_by_the_capture(self):
        # The mapping section names, per row, the field that would move it. A field the capture does not write is a
        # row that can never move, which reads as "waiting for hardware" instead of "cannot be answered".
        mapping = self.after_the_table()
        script = CAPTURE.read_text(encoding="utf-8")
        promised = [token for token in re.findall(r"`([^`]+)`", mapping) if FIELD_NAME.match(token)]
        self.assertGreater(len(promised), 5, "the mapping section no longer names capture fields")
        missing = sorted({field for field in promised if field not in script})
        self.assertEqual(missing, [], f"tools/phx_baseline.sh never writes {missing}, so those rows cannot move")

    def test_every_undecided_row_says_what_would_decide_it(self):
        # `unknown` means "this repository cannot decide it": the row must then point at the capture field that
        # would, or at the section explaining why no capture can. A row in neither list is a promise nobody audits.
        names = self.section_row_names()
        unaddressed = [area for area, _, evidence, _, _ in self.rows
                       if evidence.replace("`", "").startswith("unknown")
                       and not any(area.startswith(name) for name in names)]
        self.assertEqual(unaddressed, [], f"unknown rows with no field and no explanation: {unaddressed}")

    def test_the_accounting_sections_name_rows_that_exist(self):
        # The reverse direction: a renamed row leaves an orphan behind in the mapping tables, which is how a table
        # like this starts describing rows that no longer exist.
        areas = [area for area, *_ in self.rows]
        orphans = sorted({name for name in self.section_row_names() if name not in META_ROW_NAMES
                          and not any(area.startswith(name) for area in areas)})
        self.assertEqual(orphans, [], f"the mapping sections name rows the table does not have: {orphans}")

    def test_a_dash_in_the_move_up_cell_is_explained_in_the_no_capture_section(self):
        start = self.text.index("## Rows no capture can move")
        section = self.text[start:self.text.index("## How to keep this table honest", start)]
        unexplained = [area for area, _, _, _, would in self.rows
                       if would.strip() == "—" and area not in section]
        self.assertEqual(unexplained, [], f"rows with a bare em dash and no explanation: {unexplained}")

    def after_the_table(self):
        """Everything after the support table: the two sections that have to account for every undecided row."""
        return self.text[self.text.index("## What one capture would move"):]

    def section_row_names(self):
        """The row names as the two accounting sections write them (shorter than the table's area cells)."""
        names, column, in_table = [], None, False
        for line in self.after_the_table().splitlines():
            if line.startswith("| capture field "):
                column, in_table = 1, True
                continue
            if line.startswith("| row |"):
                column, in_table = 0, True
                continue
            if not line.startswith("| "):
                in_table = False
                continue
            if not in_table or set(line) <= set("|- "):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
            if len(cells) == 3 and cells[column]:
                names.append(cells[column])
        return names


if __name__ == "__main__":
    unittest.main()
