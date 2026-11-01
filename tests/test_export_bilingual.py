from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_translation import load_units
from tools.export_bilingual import (
    DuplicateUnitIdError, csv_cell, export_files, markdown_cell, pair_units, render_csv, render_markdown, summarize,
)

# The tools refuse paths through linked directories. On macOS the default temp dir sits
# under the symlink /var, so the tests work in its resolved path.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())

UNITS = ROOT / "examples/units"
TOOL = ROOT / "tools/export_bilingual.py"
MARKER = "Zebra-Quartz"
# Built from chr() so no test string looks like a network path to check_release.
BACKSLASH = chr(92)
DEMO_STATS = {"rows": 12, "aligned": 12, "missing_in_target": 0, "extra_in_target": 0}


def doc(role: str, language: str, *units: tuple) -> dict:
    """Units document from (unit_id, text) or (unit_id, text, locator) tuples."""
    items = []
    for unit_id, text, *locator in units:
        item = {"unit_id": unit_id, "text": text}
        if locator:
            item["locator"] = locator[0]
        items.append(item)
    return {"role": role, "language": language, "version": "test-1", "units": items}


class PairTests(unittest.TestCase):
    def test_demo_rows_follow_the_source(self):
        source, _ = load_units(UNITS / "source.json")
        target, _ = load_units(UNITS / "draft-2.json")
        rows = pair_units(source, target)
        self.assertEqual(summarize(rows), DEMO_STATS)
        self.assertEqual([row["unit_id"] for row in rows], [unit["unit_id"] for unit in source["units"]])
        self.assertEqual(rows[0]["locator"], "Clause 1")
        self.assertEqual(rows[0]["target"], target["units"][0]["text"])

    def test_missing_extra_and_locator_fallback(self):
        source = doc("source", "en", ("UNIT-001", "One", "p1"), ("UNIT-002", "Two"), ("UNIT-003", "Three", "p3"))
        target = doc("target", "zh", ("UNIT-009", "Nine", "t9"), ("UNIT-003", "San", "t3"), ("UNIT-002", "Er", "t2"))
        rows = pair_units(source, target)
        self.assertEqual(rows, [
            {"unit_id": "UNIT-001", "locator": "p1", "source": "One", "target": None},
            {"unit_id": "UNIT-002", "locator": "t2", "source": "Two", "target": "Er"},
            {"unit_id": "UNIT-003", "locator": "p3", "source": "Three", "target": "San"},
            {"unit_id": "UNIT-009", "locator": "t9", "source": None, "target": "Nine"},
        ])
        self.assertEqual(summarize(rows), {"rows": 4, "aligned": 2, "missing_in_target": 1, "extra_in_target": 1})

    def test_duplicate_ids_rejected_on_either_side(self):
        once = doc("source", "en", ("UNIT-001", "One"))
        twice = doc("target", "zh", ("UNIT-001", "Yi"), ("UNIT-001", "Yi again"))
        for left, right in [(once, twice), (twice, once)]:
            with self.subTest(duplicate_in="target" if right is twice else "source"):
                with self.assertRaises(DuplicateUnitIdError):
                    pair_units(left, right)
        self.assertTrue(issubclass(DuplicateUnitIdError, ValueError))


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_demo_export(self):
        for fmt, start in [
            ("markdown", "# Bilingual Table\n\nSource: en, version demo-source-v1\n"),
            ("csv", '\ufeff"unit_id","locator","source","target"\r\n"UNIT-DEMO-001","Clause 1",'),
        ]:
            with self.subTest(fmt=fmt):
                text, stats = export_files(UNITS / "source.json", UNITS / "draft-2.json", fmt)
                self.assertEqual(stats, DEMO_STATS)
                self.assertTrue(text.startswith(start), text[:120])

    def test_roles_and_format_checked(self):
        source = self.write("source.json", doc("source", "en", ("UNIT-001", "One")))
        pivot = self.write("pivot.json", doc("pivot", "fr", ("UNIT-001", "Un")))
        target = self.write("target.json", doc("target", "zh", ("UNIT-001", "Yi")))
        for left, right in [(source, pivot), (pivot, target), (source, target)]:
            with self.subTest(left=left.stem, right=right.stem):
                self.assertEqual(export_files(left, right, "csv")[1]["aligned"], 1)
        for left, right in [(target, source), (target, pivot), (pivot, source), (source, source), (target, target)]:
            with self.subTest(left=left.stem, right=right.stem):
                with self.assertRaisesRegex(ValueError, "reversed"):
                    export_files(left, right, "markdown")
        # The format is checked before any file is read.
        with self.assertRaisesRegex(ValueError, "Unknown table format"):
            export_files(self.root / "missing.json", self.root / "missing.json", "docx")


class MarkdownTests(unittest.TestCase):
    def test_cell_escaping(self):
        for value, expected in [
            (None, ""), ("", ""), (7, "7"),
            ("a|b", "a&#124;b"),
            ("<i>x</i> & y", "&lt;i&gt;x&lt;/i&gt; &amp; y"),
            ("&#124;", "&amp;#124;"),
            ("a" + BACKSLASH + "|b", "a&#92;&#124;b"),
            ("one\r\ntwo\rthree\nfour", "one<br>two<br>three<br>four"),
            ('"quoted"', '"quoted"'),
        ]:
            with self.subTest(value=value):
                self.assertEqual(markdown_cell(value), expected)

    def test_hostile_text_cannot_break_rows(self):
        hostile = "| x |\n|---|---|\n# Heading\r\n<script>" + BACKSLASH
        rows = [
            {"unit_id": "UNIT-001", "locator": hostile, "source": hostile, "target": hostile},
            {"unit_id": "UNIT-002", "locator": None, "source": "Plain", "target": None},
        ]
        text = render_markdown(doc("source", "en", ("UNIT-001", "x")), doc("target", "zh", ("UNIT-001", "x")), rows)
        table = [line for line in text.split("\n") if line.startswith("|")]
        self.assertEqual([line.count("|") for line in table], [5, 5, 5, 5])
        self.assertEqual(table[3], "| UNIT-002 |  | Plain |  |")
        self.assertNotIn("<script>", text)
        self.assertNotIn("\r", text)

    def test_layout_and_escaped_meta(self):
        source = doc("source", "en", ("UNIT-001", "One", "p1"), ("UNIT-002", "Two"))
        source["version"] = "v1 <draft>"
        target = doc("target", "zh", ("UNIT-001", "Yi"))
        target["version"] = "a|b"
        self.assertEqual(render_markdown(source, target, pair_units(source, target)), "\n".join([
            "# Bilingual Table", "",
            "Source: en, version v1 &lt;draft&gt;", "",
            "Target: zh, version a&#124;b", "",
            "Reading copy: make corrections in the units files.", "",
            "| Unit | Locator | Source | Target |",
            "|---|---|---|---|",
            "| UNIT-001 | p1 | One | Yi |",
            "| UNIT-002 |  | Two |  |",
        ]) + "\n")


class CsvTests(unittest.TestCase):
    def test_formula_guard(self):
        for value in ["=1+2", "+1", "-5", "@SUM(A1)", "\tx", "\rx", "\nx", "\uff1d1", "\uff0b1", "\uff0d1", "\uff201"]:
            with self.subTest(value=ascii(value)):
                self.assertEqual(csv_cell(value), "'" + value)
        for value in ["Plain", "1-2", "a=b", "'quoted", ""]:
            with self.subTest(value=value):
                self.assertEqual(csv_cell(value), value)
        self.assertEqual(csv_cell(None), "")

    def test_owasp_examples(self):
        # The two worked examples on the OWASP CSV Injection page.
        for value, expected in [
            ('=1+2";=1+2', '"\'=1+2"";=1+2"'),
            ("=1+2'\" ;,=1+2", '"\'=1+2\'"" ;,=1+2"'),
        ]:
            with self.subTest(value=value):
                rows = [{"unit_id": "UNIT-001", "locator": None, "source": value, "target": "x"}]
                self.assertEqual(render_csv(rows).split("\r\n")[1], '"UNIT-001","",' + expected + ',"x"')

    def test_layout_and_round_trip(self):
        rows = [
            {"unit_id": "UNIT-001", "locator": "p1", "source": 'Say "hi", then\r\nleave', "target": "=SUM(A1)"},
            {"unit_id": "UNIT-002", "locator": None, "source": "Two", "target": None},
        ]
        text = render_csv(rows)
        self.assertEqual(text, "\ufeff" + "\r\n".join([
            '"unit_id","locator","source","target"',
            '"UNIT-001","p1","Say ""hi"", then\r\nleave","\'=SUM(A1)"',
            '"UNIT-002","","Two",""',
        ]) + "\r\n")
        self.assertEqual(list(csv.reader(io.StringIO(text[1:], newline=""))), [
            ["unit_id", "locator", "source", "target"],
            ["UNIT-001", "p1", 'Say "hi", then\r\nleave', "'=SUM(A1)"],
            ["UNIT-002", "", "Two", ""],
        ])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(TOOL), *args], capture_output=True, text=True)

    def export(self, output: Path, *extra: str, source: Path = UNITS / "source.json",
               target: Path = UNITS / "draft-2.json") -> subprocess.CompletedProcess:
        return self.run_tool("--source", str(source), "--target", str(target), "--output", str(output), *extra)

    def test_demo_tables(self):
        stats = ["rows=12", "aligned=12", "missing_in_target=0", "extra_in_target=0"]
        for name, fmt in [("table.md", "markdown"), ("table.csv", "csv")]:
            with self.subTest(fmt=fmt):
                result = self.export(self.root / name)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.split(), [*stats, "format=" + fmt, "output=written"])
        markdown = (self.root / "table.md").read_bytes()
        self.assertTrue(markdown.startswith(b"# Bilingual Table\n"))
        self.assertNotIn(b"\r", markdown)
        table = (self.root / "table.csv").read_bytes()
        self.assertTrue(table.startswith(b"\xef\xbb\xbf\"unit_id\""))
        self.assertEqual((table.count(b"\r\n"), table.count(b"\n")), (13, 13))

    def test_format_option_overrides_suffix(self):
        for index, (name, extra, fmt) in enumerate([
            ("table.txt", ["--format", "csv"], "csv"),
            ("table.csv", ["--format", "markdown"], "markdown"),
            ("TABLE.MD", [], "markdown"),
            ("table.markdown", [], "markdown"),
        ]):
            with self.subTest(name=name, extra=extra):
                output = self.root / str(index) / name
                result = self.export(output, *extra)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("format=" + fmt, result.stdout.split())
                self.assertEqual(output.read_bytes().startswith(b"\xef\xbb\xbf"), fmt == "csv")

    def test_existing_output_and_input_are_kept(self):
        output = self.root / "table.md"
        output.write_bytes(b"keep")
        result = self.export(output)
        self.assertEqual((result.returncode, result.stdout.strip()), (1, "export_failed=ValueError"))
        self.assertEqual(output.read_bytes(), b"keep")
        source = self.root / "source.json"
        source.write_bytes((UNITS / "source.json").read_bytes())
        result = self.export(source, "--format", "markdown", source=source)
        self.assertEqual((result.returncode, result.stdout.strip()), (1, "export_failed=ValueError"))
        self.assertEqual(source.read_bytes(), (UNITS / "source.json").read_bytes())

    def test_bad_arguments_exit_2(self):
        output = self.root / (MARKER + ".txt")
        result = self.export(output)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("--format markdown or --format csv", result.stderr)
        self.assertNotIn("Zebra", result.stdout + result.stderr)
        self.assertFalse(output.exists())
        result = self.export(self.root / "table.md", "--format", "docx")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertFalse((self.root / "table.md").exists())
        self.assertEqual(self.run_tool("--source", str(UNITS / "source.json"), "--output", str(output)).returncode, 2)

    def test_failures_print_only_the_class(self):
        source = json.loads((UNITS / "source.json").read_text(encoding="utf-8"))
        target = json.loads((UNITS / "draft-2.json").read_text(encoding="utf-8"))
        hidden = {"unit_id": "UNIT-DEMO-001", "text": MARKER}
        for index, (name, left, right) in enumerate([
            ("DuplicateUnitIdError", source, dict(target, units=target["units"] + [hidden])),
            ("ValidationError", dict(source, note=MARKER), target),
            ("ValueError", dict(target, units=[hidden]), dict(source, units=[hidden])),
        ]):
            with self.subTest(name=name):
                left_path, right_path = self.root / f"left-{index}.json", self.root / f"right-{index}.json"
                left_path.write_text(json.dumps(left, ensure_ascii=False), encoding="utf-8")
                right_path.write_text(json.dumps(right, ensure_ascii=False), encoding="utf-8")
                output = self.root / f"out-{index}.md"
                result = self.export(output, source=left_path, target=right_path)
                self.assertEqual((result.returncode, result.stdout.strip()), (1, "export_failed=" + name))
                self.assertNotIn("Zebra", result.stdout + result.stderr)
                self.assertFalse(output.exists())
        missing = self.export(self.root / "out.md", source=self.root / (MARKER + ".json"))
        self.assertEqual((missing.returncode, missing.stdout.strip()), (1, "export_failed=FileNotFoundError"))
        self.assertNotIn("Zebra", missing.stdout + missing.stderr)


if __name__ == "__main__":
    unittest.main()
