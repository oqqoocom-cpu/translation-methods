from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_translation import check_files
from tools.make_units import EmptyInputError, make_units, read_source, render_units, split_text

# The tools refuse paths through linked directories. On macOS the default temp dir sits
# under the symlink /var, so the tests work in its resolved path.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())

UNITS = ROOT / "examples/units"
GLOSSARY = [ROOT / "examples/term.synthetic.json", ROOT / "examples/entity.synthetic.json"]
TOOL = ROOT / "tools/make_units.py"
MARKER = "Zebra-Quartz"


def texts(blocks: list[tuple[int, str]]) -> list[str]:
    return [text for _, text in blocks]


class SplitTests(unittest.TestCase):
    def test_paragraphs_keep_inner_line_breaks(self):
        blocks = split_text("First line  \nsecond line\n\n\n  Next paragraph\t\n")
        self.assertEqual(blocks, [(1, "First line\nsecond line"), (5, "Next paragraph")])

    def test_line_endings_normalized(self):
        for text in ["a\nb\n\nc\n", "a\r\nb\r\n\r\nc\r\n", "a\rb\r\rc\r", "a\r\nb\n\rc"]:
            with self.subTest(text=ascii(text)):
                self.assertEqual(split_text(text), [(1, "a\nb"), (4, "c")])

    def test_unicode_blank_lines_and_indent(self):
        text = "\u3000\u3000First\n\u3000\nSecond\n\f\nThird"
        self.assertEqual(split_text(text), [(1, "First"), (3, "Second"), (5, "Third")])

    def test_line_mode(self):
        self.assertEqual(split_text("\u3000One\nTwo  \n\nThree", by_line=True), [(1, "One"), (2, "Two"), (4, "Three")])

    def test_no_text(self):
        for text in ["", " \n\t\n\u3000\n"]:
            with self.subTest(text=ascii(text)):
                self.assertEqual(split_text(text), [])


class MarkdownTests(unittest.TestCase):
    def test_headings_are_units(self):
        text = "# Title\nIntro line\n## Part 1\nBody\n#hashtag stays text\n####### seven marks"
        self.assertEqual(split_text(text, markdown=True), [
            (1, "# Title"), (2, "Intro line"), (3, "## Part 1"), (4, "Body\n#hashtag stays text\n####### seven marks"),
        ])

    def test_heading_forms(self):
        for line, heading in [("#", True), ("   ### Three spaces", True), ("#\tTab", True), ("    # Four spaces", False)]:
            with self.subTest(line=line):
                self.assertEqual(len(split_text("Text\n" + line, markdown=True)), 2 if heading else 1)

    def test_fence_keeps_blank_lines(self):
        for mark in ["```", "~~~"]:
            text = f"Before\n{mark}python\nx = 1\n\n# not a heading\n{mark}\nAfter"
            with self.subTest(mark=mark):
                self.assertEqual(split_text(text, markdown=True), [
                    (1, "Before"), (2, f"{mark}python\nx = 1\n\n# not a heading\n{mark}"), (7, "After"),
                ])

    def test_fence_closing_rules(self):
        for text, count in [
            ("````\na\n```\nb\n````", 1),  # a shorter run does not close the fence
            ("```\na\n~~~\nb\n```", 1),  # nor does the other fence character
            ("```\na\n``` x\nb\n```", 1),  # a closing line carries no info string
            ("```\na\n\nb", 1),  # an unclosed fence runs to the end of the file
            ("``` a`b\nc\n\nd", 2),  # a backtick in the info string means no fence
        ]:
            with self.subTest(text=text):
                self.assertEqual(len(split_text(text, markdown=True)), count)

    def test_text_mode_reads_marks_as_text(self):
        text = "# Title\nBody\n\n```\ncode\n\nmore\n```"
        self.assertEqual(texts(split_text(text)), ["# Title\nBody", "```\ncode", "more\n```"])

    def test_line_mode_keeps_fences_whole(self):
        text = "# Title\nOne\nTwo\n```\na\n\nb\n```"
        self.assertEqual(
            texts(split_text(text, markdown=True, by_line=True)), ["# Title", "One", "Two", "```\na\n\nb\n```"],
        )


class BuildTests(unittest.TestCase):
    def test_id_width_grows_past_999(self):
        for count, first, last in [(1, "UNIT-001", "UNIT-001"), (999, "UNIT-001", "UNIT-999"),
                                   (1000, "UNIT-0001", "UNIT-1000")]:
            with self.subTest(count=count):
                items = make_units("\n\n".join(f"Line {n}" for n in range(count)), "en", "v1")["units"]
                self.assertEqual((len(items), items[0]["unit_id"], items[-1]["unit_id"]), (count, first, last))

    def test_fields_and_key_order(self):
        value = make_units("One\n\nTwo", "zh", "draft-3", prefix="CH01", role="target", decimal_mark=",", synthetic=True)
        self.assertEqual(list(value), ["role", "language", "version", "decimal_mark", "units", "synthetic"])
        self.assertEqual(value["units"], [
            {"unit_id": "CH01-001", "locator": "line 1", "text": "One"},
            {"unit_id": "CH01-002", "locator": "line 3", "text": "Two"},
        ])
        self.assertEqual(list(make_units("One", "en", "v1")), ["role", "language", "version", "units"])

    def test_invalid_input_rejected(self):
        for text in ["", " \n\u3000\n\t"]:
            with self.subTest(text=ascii(text)), self.assertRaises(EmptyInputError):
                make_units(text, "en", "v1")
        for prefix in ["unit", "CH01-", "CH 01", "1CH", "U-", ""]:
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                make_units("Text", "en", "v1", prefix=prefix)
        for changes in [{"prefix": "A" * 70}, {"language": " "}, {"version": ""}, {"role": "draft"}]:
            with self.subTest(changes=changes), self.assertRaises((ValidationError, ValueError)):
                make_units("Text", **{"language": "en", "version": "v1", **changes})

    def test_read_source_accepts_only_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.txt"
            text = "\u4e2d\u6587 text"
            path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
            self.assertEqual(read_source(path), text)
            for index, data in enumerate([text.encode("gbk"), text.encode("utf-16"), "Text".encode("utf-16-le")]):
                path.write_bytes(data)
                with self.subTest(index=index), self.assertRaises(UnicodeError):
                    read_source(path)


class DemoTests(unittest.TestCase):
    def test_demo_text_rebuilds_the_source_units(self):
        value = make_units(read_source(UNITS / "source.txt"), "en", "demo-source-v1", prefix="UNIT-DEMO", synthetic=True)
        expected = json.loads((UNITS / "source.json").read_text(encoding="utf-8"))
        self.assertEqual([unit["locator"] for unit in value["units"]], [f"line {n}" for n in range(1, 24, 2)])
        for unit in value["units"] + expected["units"]:
            del unit["locator"]
        self.assertEqual(value, expected)

    def test_render_matches_example_layout(self):
        for name in ["source.json", "draft-1.json", "draft-2.json"]:
            with self.subTest(name=name):
                text = (UNITS / name).read_bytes().decode("utf-8")
                self.assertEqual(render_units(json.loads(text)), text)
        with self.assertRaises(ValueError):
            render_units({"role": "source", "language": "en", "version": "v1", "units": [], "note": "x"})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(TOOL), *args], capture_output=True, text=True)

    def args(self, source: Path, output: Path, *extra: str) -> list[str]:
        return ["--input", str(source), "--output", str(output), "--language", "en", "--version", "v1", *extra]

    def test_demo_written_once_and_checks_clean(self):
        output = self.root / "source.units.json"
        args = [
            "--input", str(UNITS / "source.txt"), "--output", str(output), "--language", "en",
            "--version", "demo-source-v1", "--prefix", "UNIT-DEMO", "--synthetic",
        ]
        first = self.run_tool(*args)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(first.stdout.split(), ["units=12", "format=text", "split=paragraph", "max_unit_lines=1", "output=written"])
        report, _ = check_files(output, UNITS / "draft-2.json", GLOSSARY)
        self.assertEqual(report["findings"], [])
        before = output.read_bytes()
        second = self.run_tool(*args)
        self.assertEqual((second.returncode, second.stdout.strip()), (1, "make_units_failed=ValueError"))
        self.assertEqual(output.read_bytes(), before)

    def test_format_and_split_options(self):
        page = self.root / "page.md"
        page.write_text("# Title\nBody line one\nBody line two\n", encoding="utf-8")
        for index, (extra, expected) in enumerate([
            ([], ["units=2", "format=markdown", "split=paragraph", "max_unit_lines=2"]),
            (["--format", "text"], ["units=1", "format=text", "split=paragraph", "max_unit_lines=3"]),
            (["--split", "line"], ["units=3", "format=markdown", "split=line", "max_unit_lines=1"]),
        ]):
            with self.subTest(extra=extra):
                result = self.run_tool(*self.args(page, self.root / f"out-{index}.json", *extra))
                self.assertEqual(result.stdout.split(), [*expected, "output=written"])

    def test_failures_print_only_the_class(self):
        source = self.root / "source.txt"
        for index, (data, name) in enumerate([
            ((MARKER + " text").encode("utf-16"), "UnicodeDecodeError"),
            ((MARKER + " text").encode("utf-16-le"), "UnicodeError"),
            (MARKER.encode("ascii") + "\u4e2d\u6587".encode("gbk"), "UnicodeDecodeError"),
            (b" \n\t\n", "EmptyInputError"),
        ]):
            with self.subTest(name=name, index=index):
                source.write_bytes(data)
                output = self.root / f"out-{index}.json"
                result = self.run_tool(*self.args(source, output))
                self.assertEqual((result.returncode, result.stdout.strip()), (1, "make_units_failed=" + name))
                self.assertNotIn("Zebra", result.stdout + result.stderr)
                self.assertFalse(output.exists())
        missing = self.run_tool(*self.args(self.root / (MARKER + ".txt"), self.root / "out.json"))
        self.assertEqual((missing.returncode, missing.stdout.strip()), (1, "make_units_failed=FileNotFoundError"))
        self.assertNotIn("Zebra", missing.stdout + missing.stderr)

    def test_bad_arguments_exit_2(self):
        source = self.root / "source.txt"
        source.write_text("Text", encoding="utf-8")
        output = self.root / "out.json"
        for extra in [["--prefix", "unit"], ["--prefix", "CH01-"], ["--split", "word"], ["--format", "docx"],
                      ["--role", "draft"]]:
            with self.subTest(extra=extra):
                result = self.run_tool(*self.args(source, output, *extra))
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertFalse(output.exists())
        self.assertEqual(self.run_tool("--input", str(source), "--output", str(output)).returncode, 2)


if __name__ == "__main__":
    unittest.main()
