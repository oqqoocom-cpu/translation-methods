"""Export a source units file and a target units file as one bilingual table.

Rows follow the source order; target units with no source unit come last. The
table is a reading copy for review: corrections go back into the units files,
which stay the record. Markdown cells are escaped so text cannot break the
table. CSV cells are all quoted, and a cell that a spreadsheet could read as a
formula gets a leading apostrophe.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
from pathlib import Path
from typing import Any

try:
    from .check_translation import load_units
    from .sync_registry import write_new_outputs
    from .validate_assets import missing_dependency_hint
except ImportError:
    from check_translation import load_units
    from sync_registry import write_new_outputs
    from validate_assets import missing_dependency_hint

COLUMNS = ("unit_id", "locator", "source", "target")
SUFFIXES = {".md": "markdown", ".markdown": "markdown", ".csv": "csv"}
# Leading characters that make a spreadsheet read a cell as a formula, with the
# full-width forms some spreadsheets also accept (OWASP, CSV Injection).
FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")


class DuplicateUnitIdError(ValueError):
    """A units file uses one unit ID twice, so its rows cannot be paired."""


def _index(units: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for unit in units:
        if unit["unit_id"] in index:
            raise DuplicateUnitIdError("Duplicate unit ID")
        index[unit["unit_id"]] = unit
    return index


def pair_units(source: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    """Pair units by ID: source order first, then target-only units; a missing side is None."""
    source_units, target_units = _index(source["units"]), _index(target["units"])
    order = list(source_units) + [unit_id for unit_id in target_units if unit_id not in source_units]
    rows = []
    for unit_id in order:
        left, right = source_units.get(unit_id), target_units.get(unit_id)
        rows.append({
            "unit_id": unit_id,
            "locator": (left or {}).get("locator") or (right or {}).get("locator"),
            "source": None if left is None else left["text"],
            "target": None if right is None else right["text"],
        })
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "rows": len(rows),
        "aligned": sum(row["source"] is not None and row["target"] is not None for row in rows),
        "missing_in_target": sum(row["target"] is None for row in rows),
        "extra_in_target": sum(row["source"] is None for row in rows),
    }


def markdown_cell(value: Any) -> str:
    """Escape a value for one Markdown table cell; line breaks become <br>."""
    if value is None:
        return ""
    text = html.escape(str(value), quote=False).replace("\\", "&#92;").replace("|", "&#124;")
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render_markdown(source: dict[str, Any], target: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = ["# Bilingual Table", ""]
    for name, value in (("Source", source), ("Target", target)):
        lines += [f"{name}: {markdown_cell(value['language'])}, version {markdown_cell(value['version'])}", ""]
    lines += [
        "Reading copy: make corrections in the units files.", "",
        "| Unit | Locator | Source | Target |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(markdown_cell(row[column]) for column in COLUMNS) + " |")
    return "\n".join(lines) + "\n"


def csv_cell(value: Any) -> str:
    """Return a CSV cell; a leading apostrophe stops a spreadsheet reading the text as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def render_csv(rows: list[dict[str, Any]]) -> str:
    """Return CSV text with CRLF rows and a UTF-8 BOM, so spreadsheets detect the encoding."""
    stream = io.StringIO(newline="")
    # Quoting every cell stops a separator in the text (',' or, in some locales,
    # ';') from starting a new cell that begins with a formula character.
    writer = csv.writer(stream, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([csv_cell(row[column]) for column in COLUMNS])
    return "\ufeff" + stream.getvalue()


def export_files(source_path: Path, target_path: Path, fmt: str) -> tuple[str, dict[str, int]]:
    """Load both units files; return the table text and the row counts."""
    if fmt not in ("markdown", "csv"):
        raise ValueError("Unknown table format")
    source, _ = load_units(source_path)
    target, _ = load_units(target_path)
    if source["role"] == "target" or target["role"] == "source":
        raise ValueError("Source and target roles are reversed")
    rows = pair_units(source, target)
    text = render_markdown(source, target, rows) if fmt == "markdown" else render_csv(rows)
    return text, summarize(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a source and a target units file as one bilingual table.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new .md or .csv file")
    parser.add_argument("--format", choices=["auto", "markdown", "csv"], default="auto",
                        help="auto follows the output suffix: .md, .markdown or .csv")
    args = parser.parse_args(argv)
    fmt = SUFFIXES.get(args.output.suffix.lower()) if args.format == "auto" else args.format
    if fmt is None:
        parser.error("the output suffix does not name a format; use --format markdown or --format csv")
    hint = missing_dependency_hint()
    if hint:
        print(hint)
        return 1
    try:
        text, stats = export_files(args.source, args.target, fmt)
        write_new_outputs(args.source, {args.output: text})
    except Exception as exc:
        # The inputs can be private; print only the exception class.
        print("export_failed=" + type(exc).__name__)
        return 1
    print("\n".join([*(f"{key}={value}" for key, value in stats.items()), "format=" + fmt, "output=written"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
