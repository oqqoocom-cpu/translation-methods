"""Split a UTF-8 text or Markdown file into a units file.

A unit is a paragraph: lines between blank lines. With --split line, every
non-blank line is a unit. In Markdown, a heading line is a unit of its own and
a fenced code block stays one unit, blank lines included. Unit IDs are numbered
in order, so the first result is the baseline: a corrected source becomes a new
source version, not a fresh split.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from .sync_registry import write_new_outputs
    from .validate_assets import missing_dependency_hint, validate
except ImportError:
    from sync_registry import write_new_outputs
    from validate_assets import missing_dependency_hint, validate

HEADING_RE = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})")
PREFIX_RE = re.compile(r"[A-Z](?:[A-Z0-9_-]*[A-Z0-9])?")
MARKDOWN_SUFFIXES = {".md", ".markdown"}
FIELDS = ("role", "language", "version", "decimal_mark", "units", "synthetic")


class EmptyInputError(ValueError):
    """The input has no text to split."""


def _closing_fence(line: str) -> re.Pattern[str] | None:
    """Return a pattern for the line that closes the fence opened by this line, or None."""
    match = FENCE_RE.match(line)
    if match is None:
        return None
    run = match.group(1)
    # A backtick fence cannot carry a backtick in its info string (CommonMark).
    if run[0] == "`" and "`" in line[match.end():]:
        return None
    return re.compile(r" {0,3}" + re.escape(run[0]) + "{" + str(len(run)) + r",}[ \t]*")


def split_text(text: str, markdown: bool = False, by_line: bool = False) -> list[tuple[int, str]]:
    """Return (start line, unit text) pairs; lines count from 1 and blank lines separate units."""
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    closing: re.Pattern[str] | None = None
    for number, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        if closing is not None:
            current.append(line)
            if closing.fullmatch(line):
                closing = current = None
            continue
        if not line.strip():
            current = None
            continue
        if markdown:
            closing = _closing_fence(line)
            if closing is not None:
                current = [line]
                blocks.append((number, current))
                continue
            if HEADING_RE.match(line):
                blocks.append((number, [line]))
                current = None
                continue
        if current is None or by_line:
            current = [line]
            blocks.append((number, current))
        else:
            current.append(line)
    return [(start, "\n".join(line.rstrip() for line in block).strip()) for start, block in blocks]


def make_units(
    text: str, language: str, version: str, prefix: str = "UNIT", role: str = "source", markdown: bool = False,
    by_line: bool = False, decimal_mark: str | None = None, synthetic: bool = False,
) -> dict[str, Any]:
    """Build and validate a units document; IDs run PREFIX-001, PREFIX-002, ... in text order."""
    if PREFIX_RE.fullmatch(prefix) is None:
        raise ValueError("Unit ID prefix must use capital letters, digits, '-' or '_'")
    blocks = split_text(text, markdown, by_line)
    if not blocks:
        raise EmptyInputError("Input has no text to split")
    width = max(3, len(str(len(blocks))))
    value: dict[str, Any] = {"role": role, "language": language, "version": version}
    if decimal_mark is not None:
        value["decimal_mark"] = decimal_mark
    value["units"] = [
        {"unit_id": f"{prefix}-{index:0{width}d}", "locator": f"line {start}", "text": unit}
        for index, (start, unit) in enumerate(blocks, 1)
    ]
    if synthetic:
        value["synthetic"] = True
    validate("units", value)
    return value


def render_units(value: dict[str, Any]) -> str:
    """Write a units document with one unit per line, in the layout of the examples."""
    if not set(value) <= set(FIELDS):
        raise ValueError("Unknown units field")
    lines = []
    for key in FIELDS:
        if key == "units":
            items = ",\n".join("    " + json.dumps(unit, ensure_ascii=False) for unit in value["units"])
            lines.append('  "units": [\n' + items + "\n  ]")
        elif key in value:
            lines.append(f"  {json.dumps(key)}: {json.dumps(value[key], ensure_ascii=False)}")
    return "{\n" + ",\n".join(lines) + "\n}\n"


def read_source(path: Path) -> str:
    """Read UTF-8 text and drop a BOM; other encodings fail instead of being guessed."""
    text = Path(path).read_bytes().decode("utf-8-sig")
    # UTF-16 without a BOM can still decode as UTF-8 when the text is ASCII; it leaves NUL characters.
    if "\x00" in text:
        raise UnicodeError("Input contains NUL characters; save it as UTF-8 text")
    return text


def _prefix_arg(text: str) -> str:
    if PREFIX_RE.fullmatch(text) is None:
        raise argparse.ArgumentTypeError("use capital letters, digits, '-' or '_', starting with a letter")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split a UTF-8 text or Markdown file into a new units file.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new JSON file")
    parser.add_argument("--language", required=True, help="language tag of the text, such as en or zh")
    parser.add_argument("--version", required=True, help="version label of this text layer")
    parser.add_argument("--prefix", type=_prefix_arg, default="UNIT", help="unit ID prefix; default UNIT")
    parser.add_argument("--role", choices=["source", "pivot", "target"], default="source")
    parser.add_argument("--format", choices=["auto", "text", "markdown"], default="auto",
                        help="auto reads .md and .markdown files as Markdown")
    parser.add_argument("--split", choices=["paragraph", "line"], default="paragraph")
    parser.add_argument("--decimal-mark", choices=[".", ","])
    parser.add_argument("--synthetic", action="store_true", help="mark the file as synthetic demo data")
    args = parser.parse_args(argv)
    hint = missing_dependency_hint()
    if hint:
        print(hint)
        return 1
    markdown = args.format == "markdown" or (
        args.format == "auto" and args.input.suffix.lower() in MARKDOWN_SUFFIXES
    )
    try:
        value = make_units(
            read_source(args.input), args.language, args.version, args.prefix, args.role, markdown,
            args.split == "line", args.decimal_mark, args.synthetic,
        )
        write_new_outputs(args.input, {args.output: render_units(value)})
    except Exception as exc:
        # The input can be private; print only the exception class.
        print("make_units_failed=" + type(exc).__name__)
        return 1
    # A very long unit usually means the text has no blank lines between paragraphs.
    longest = max(unit["text"].count("\n") + 1 for unit in value["units"])
    print("\n".join([
        f"units={len(value['units'])}", "format=" + ("markdown" if markdown else "text"), "split=" + args.split,
        f"max_unit_lines={longest}", "output=written",
    ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
