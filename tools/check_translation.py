"""Compare a target units file with its source units file.

The checks are mechanical: unit structure, protected numbers, unit symbols and
markers, and decided terms or entities. They do not judge meaning. A clean
result means only that these checks found nothing; every finding is a
candidate for a person to judge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    from .sync_registry import write_new_outputs
    from .validate_assets import missing_dependency_hint, unique_object, validate
except ImportError:
    from sync_registry import write_new_outputs
    from validate_assets import missing_dependency_hint, unique_object, validate

VERSION = "0.7.0"
CHECKS = ("structure", "numbers", "symbols", "markers", "terms")
FAMILY = {
    "structure": "STRUCTURE", "numbers": "PROTECTED", "symbols": "PROTECTED", "markers": "PROTECTED",
    "terms": "TERMS",
}
MAX_LISTED = 50
MIN_CHARS = 20
MIN_LENGTH_UNITS = 5
MASK = "\ue000"

# Markers are blanked out before numbers and symbols are read, so "[12]" or a
# number inside a URL is compared once, as a marker.
MARKER_RE = re.compile(
    r"(?P<url>https?://[A-Za-z0-9\-._~:/?#@!$&'()*+,;=%]+)"
    r"|(?P<email>[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"
    r"|(?P<tag></?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>)"
    r"|(?P<placeholder>\{\{\s*[^{}\s]+\s*\}\}|\{[^{}\s]+\})"
    r"|(?P<printf>%(?:[0-9]+\$)?[-+#0]*[0-9]*(?:\.[0-9]+)?[sdifuxXeEgGcop])"
    r"|(?P<ref>\[[0-9]+(?:\s*[-\u2013,]\s*[0-9]+)*\])"
)
TAG_NAME_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)")
URL_TRAILING = ".,;:!?)]}'\""

# Case-sensitive unit symbols written after a digit. A lone "s" needs exactly one
# space, so "1990s" is not read as seconds. "A" is left out because it is also
# an English article.
SYMBOLS_MULTI = (
    "kHz", "MHz", "KB", "MB", "GB", "TB", "km", "cm", "mm", "kg", "mg", "mL", "min", "Hz", "kW", "mA",
    "\u00b0C", "\u00b0F", "%", "\u2030",
)
SYMBOLS_SINGLE = ("m", "g", "t", "L", "h", "W", "V", "\u00b0")
SYMBOL_RE = re.compile(
    "(?<=[0-9])(?: ?(" + "|".join(map(re.escape, SYMBOLS_MULTI)) + ")| (s)| ?("
    + "|".join(map(re.escape, SYMBOLS_SINGLE)) + "))(?![A-Za-z])"
)

# Chinese count words written after a digit, in simplified and traditional script,
# with their power of ten: "3.5\u4e07" is read as 35000.
SCALES = {"\u4e07\u4ebf": 12, "\u842c\u5104": 12, "\u4e07": 4, "\u842c": 4, "\u4ebf": 8, "\u5104": 8}


def _number_re(decimal_mark: str) -> re.Pattern[str]:
    group = re.escape("," if decimal_mark == "." else ".")
    mark = re.escape(decimal_mark)
    scale = "|".join(sorted(SCALES, key=len, reverse=True))
    return re.compile(
        rf"(?<![0-9])(?P<number>(?:[0-9]{{1,3}}(?:{group}[0-9]{{3}})+(?![0-9])|[0-9]+)(?:{mark}[0-9]+)?)"
        rf"(?: ?(?P<scale>{scale}))?"
    )


NUMBER_RE = {mark: _number_re(mark) for mark in ".,"}


def normalize(text: str) -> str:
    """Apply NFKC and write every decimal digit as an ASCII digit."""
    if text.isascii():
        return text
    text = unicodedata.normalize("NFKC", text)
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch for ch in text)


def squash(text: str) -> str:
    return " ".join(normalize(text).split())


def fold(text: str) -> str:
    return squash(text).casefold()


def _nonspace(squashed: str) -> int:
    return len(squashed) - squashed.count(" ")


def same_language(first: str, second: str) -> bool:
    """Treat "en", "EN_us" and "en-GB" as one language; "en" and "fr" differ."""
    first, second = (tag.strip().lower().replace("_", "-") for tag in (first, second))
    return first == second or first.startswith(second + "-") or second.startswith(first + "-")


def _word_like(char: str) -> bool:
    return char.isdecimal() or (
        char.isalpha() and unicodedata.name(char, "").startswith(("LATIN", "GREEK", "CYRILLIC"))
    )


def _find(needle: str, text: str) -> list[int]:
    """Return start offsets of non-overlapping matches of a folded needle in folded text.

    A needle that starts with a Latin, Greek or Cyrillic letter or a digit must
    start a word, so "gate rule" does not match inside "tailgate rule". There is
    no end boundary, so a short abbreviation can match the start of a longer word.
    """
    found: list[int] = []
    if not needle:
        return found
    bounded = _word_like(needle[0])
    start = text.find(needle)
    while start != -1:
        if not bounded or start == 0 or not _word_like(text[start - 1]):
            found.append(start)
            start = text.find(needle, start + len(needle))
        else:
            start = text.find(needle, start + 1)
    return found


def _mask(text: str, needle: str) -> str:
    for start in _find(needle, text):
        text = text[:start] + MASK * len(needle) + text[start + len(needle):]
    return text


def _canonical_marker(kind: str, raw: str) -> str:
    if kind == "url":
        # Drop sentence punctuation after a URL, but keep a balanced ")".
        while raw[-1] in URL_TRAILING and not (raw[-1] == ")" and raw.count("(") >= raw.count(")")):
            raw = raw[:-1]
        return raw
    if kind == "tag":
        return ("</" if raw.startswith("</") else "<") + TAG_NAME_RE.match(raw).group(1).lower() + ">"
    value = "".join(raw.split())
    return value.replace("\u2013", "-") if kind == "ref" else value


def _scan_markers(text: str) -> tuple[Counter, str]:
    """Count markers in normalized text and return the text with them blanked out."""
    found: Counter = Counter()
    chars = list(text)
    for match in MARKER_RE.finditer(text):
        kind = match.lastgroup
        value = _canonical_marker(kind, match.group())
        found[(kind, value)] += 1
        end = match.start() + len(value) if kind == "url" else match.end()
        chars[match.start():end] = " " * (end - match.start())
    return found, "".join(chars)


def _canonical_number(raw: str, decimal_mark: str, scale: str | None = None) -> str:
    group = "," if decimal_mark == "." else "."
    whole, _, fraction = raw.replace(group, "").partition(decimal_mark)
    if scale:
        # Move the decimal point by the count word's power of ten, on the digit string, so it stays exact.
        places = SCALES[scale]
        fraction = fraction.ljust(places, "0")
        whole, fraction = whole + fraction[:places], fraction[places:]
    whole, fraction = whole.lstrip("0") or "0", fraction.rstrip("0")
    return whole + "." + fraction if fraction else whole


def _count_numbers(masked: str, decimal_mark: str) -> Counter:
    return Counter(
        _canonical_number(m["number"], decimal_mark, m["scale"]) for m in NUMBER_RE[decimal_mark].finditer(masked)
    )


def _count_symbols(masked: str) -> Counter:
    return Counter(next(group for group in m.groups() if group) for m in SYMBOL_RE.finditer(masked))


def extract_markers(text: str) -> Counter:
    return _scan_markers(normalize(text))[0]


def extract_numbers(text: str, decimal_mark: str = ".") -> Counter:
    return _count_numbers(_scan_markers(normalize(text))[1], decimal_mark)


def extract_symbols(text: str) -> Counter:
    return _count_symbols(_scan_markers(normalize(text))[1])


def _differences(expected: Counter, actual: Counter) -> Iterable[tuple[str, Any, int]]:
    """Yield ("missing" or "extra", key, count difference) in first-seen order."""
    for key, count in expected.items():
        if count > actual[key]:
            yield "missing", key, count - actual[key]
    for key, count in actual.items():
        if count > expected[key]:
            yield "extra", key, count - expected[key]


def _read_json(path: Path) -> tuple[Any, str]:
    raw = Path(path).read_bytes()
    # The hash covers the exact bytes; a UTF-8 BOM is tolerated when parsing.
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object), hashlib.sha256(raw).hexdigest()


def load_units(path: Path) -> tuple[dict[str, Any], str]:
    value, digest = _read_json(path)
    validate("units", value)
    return value, digest


def load_glossary(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load term and entity records from JSON files, or from folders of JSON files."""
    files: list[Path] = []
    seen: set[Path] = set()
    for path in map(Path, paths):
        group = sorted(path.rglob("*.json"), key=lambda p: p.relative_to(path).as_posix()) if path.is_dir() else [path]
        for item in group:
            if item.resolve() not in seen:
                seen.add(item.resolve())
                files.append(item)
    records: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in files:
        value, digest = _read_json(path)
        items = value if isinstance(value, list) else [value]
        for record in items:
            if not isinstance(record, dict):
                raise ValueError("Glossary entries must be JSON objects")
            if "template_status" in record or record.get("status") == "draft-template":
                raise ValueError("Templates are not glossary records")
            kind = "term" if "term_id" in record else "entity" if "entity_id" in record else ""
            if not kind:
                raise ValueError("Glossary record needs term_id or entity_id")
            validate(kind, record)
            if record[kind + "_id"] in ids:
                raise ValueError("Duplicate glossary record ID")
            ids.add(record[kind + "_id"])
            records.append(record)
        inputs.append({"role": "glossary", "sha256": digest, "records": len(items)})
    return records, inputs


def _rules(records: list[dict[str, Any]], source_language: str, target_language: str) -> tuple[list[dict], int]:
    """Turn glossary records into match rules for one language pair; also count language skips."""
    rules, language_skipped = [], 0
    for record in records:
        if "term_id" in record:
            if record["status"] in ("rejected", "deprecated"):
                continue
            # A term without a target language applies to every target language.
            if not same_language(record["source_language"], source_language) or not same_language(
                record.get("target_language", target_language), target_language,
            ):
                language_skipped += 1
                continue
            locked = record["status"] == "locked"
            rule = {
                "kind": "term", "id": record["term_id"], "enforced": locked,
                "forms": [record["source_form"], record.get("native_script", "")],
                "candidate": record.get("candidate_target", ""),
                "alternatives": record.get("alternatives", []) if locked else [],
                "pending": {"status": record["status"]},
            }
        else:
            if "candidate_target" not in record:
                continue
            if not same_language(record["target_language"], target_language):
                language_skipped += 1
                continue
            rule = {
                "kind": "entity", "id": record["entity_id"], "enforced": "decision_id" in record,
                "forms": [record["source_label"], *(v["form"] for v in record["variants"]), record.get("native_name", "")],
                "candidate": record["candidate_target"], "alternatives": [],
                "pending": {"official_status": record["official_status"]},
            }
        rule["forms"] = [form for form in dict.fromkeys(map(fold, rule["forms"])) if form]
        rule["folded"] = fold(rule["candidate"])
        alternatives: dict[str, str] = {}
        for text in rule["alternatives"]:
            if fold(text) and fold(text) != rule["folded"]:
                alternatives.setdefault(fold(text), text)
        rule["alternatives"] = [(text, folded) for folded, text in alternatives.items()]
        rules.append(rule)
    return rules, language_skipped


def run_checks(
    source: dict[str, Any], target: dict[str, Any], records: list[dict[str, Any]] | None = None,
    checks: Iterable[str] = CHECKS, length_factor: float = 2.0,
) -> dict[str, Any]:
    """Compare two validated units files. records=None means that no glossary was given."""
    wanted = set(checks)
    if not wanted or not wanted <= set(CHECKS):
        raise ValueError("Unknown or empty check list")
    if not length_factor > 1:
        raise ValueError("Length factor must be greater than 1")
    requested = [check for check in CHECKS if check in wanted]

    # Alignment uses the first unit with each ID; repeated IDs are reported, not compared.
    src_first: dict[str, dict[str, Any]] = {}
    tgt_first: dict[str, dict[str, Any]] = {}
    for unit in source["units"]:
        src_first.setdefault(unit["unit_id"], unit)
    for unit in target["units"]:
        tgt_first.setdefault(unit["unit_id"], unit)
    order = {uid: i for i, uid in enumerate([*src_first, *(uid for uid in tgt_first if uid not in src_first)])}
    entries: list[tuple[int, int, int, dict[str, Any]]] = []

    def add(check: str, unit_id: str, code: str, refs: list[str] | None = None, detail: dict | None = None) -> None:
        item: dict[str, Any] = {"unit_id": unit_id}
        locator = src_first.get(unit_id, {}).get("locator") or tgt_first.get(unit_id, {}).get("locator")
        if locator:
            item["locator"] = locator
        item.update(family=FAMILY[check], code=code, origin="program", severity_suggestion="unrated",
                    status="candidate")
        if refs:
            item["refs"] = refs
        if detail:
            item["detail"] = detail
        entries.append((order[unit_id], CHECKS.index(check), len(entries), item))

    aligned = [uid for uid in src_first if uid in tgt_first]
    text: dict[str, tuple[str, str, str, str]] = {}
    for uid in aligned:
        src, tgt = normalize(src_first[uid]["text"]), normalize(tgt_first[uid]["text"])
        text[uid] = (src, tgt, " ".join(src.split()), " ".join(tgt.split()))
    structure = "structure" in requested
    # With the structure check on, an empty target is reported once and not checked further.
    empty = {uid for uid in aligned if structure and text[uid][2] and not text[uid][3]}
    active = [uid for uid in aligned if uid not in empty]
    different_language = not same_language(source["language"], target["language"])
    untranslated = {
        uid for uid in active
        if different_language and text[uid][2] == text[uid][3] and any(ch.isalpha() for ch in text[uid][2])
    }
    skipped: list[dict[str, str]] = []

    if structure:
        for name, units, first in (("source", source["units"], src_first), ("target", target["units"], tgt_first)):
            counts = Counter(unit["unit_id"] for unit in units)
            for uid in first:
                if counts[uid] > 1:
                    add("structure", uid, "duplicate-unit-id", detail={"file": name, "count": counts[uid]})
        for uid in src_first:
            if uid not in tgt_first:
                add("structure", uid, "unit-missing")
        for uid in tgt_first:
            if uid not in src_first:
                add("structure", uid, "unit-extra")
        for expected, actual in zip(aligned, [uid for uid in tgt_first if uid in src_first]):
            if expected != actual:
                add("structure", actual, "unit-order", refs=[expected])
                break
        first_target: dict[str, str] = {}
        first_source: dict[str, str] = {}
        for uid in aligned:
            src, tgt = text[uid][2], text[uid][3]
            if uid in empty:
                add("structure", uid, "target-empty")
                continue
            if uid in untranslated:
                add("structure", uid, "target-untranslated")
            if _nonspace(tgt) >= MIN_CHARS:
                earlier = first_target.setdefault(tgt, uid)
                if earlier != uid and text[earlier][2] != src:
                    add("structure", uid, "target-duplicate", refs=[earlier])
            if src:
                earlier = first_source.setdefault(src, uid)
                if earlier != uid and text[earlier][3] != tgt:
                    add("structure", uid, "repeat-inconsistent", refs=[earlier])
        eligible = [uid for uid in active if uid not in untranslated and _nonspace(text[uid][2]) >= MIN_CHARS]
        if len(eligible) < MIN_LENGTH_UNITS:
            skipped.append({"code": "length-outlier", "reason": "too-few-units"})
        else:
            ratios = {uid: _nonspace(text[uid][3]) / _nonspace(text[uid][2]) for uid in eligible}
            median = statistics.median(ratios.values())
            for uid, ratio in ratios.items():
                if ratio < median / length_factor or ratio > median * length_factor:
                    add("structure", uid, "length-outlier", detail={"ratio": round(ratio, 3), "median": round(median, 3)})

    src_mark, tgt_mark = source.get("decimal_mark", "."), target.get("decimal_mark", ".")
    for uid in active:
        src_markers, src_masked = _scan_markers(text[uid][0])
        tgt_markers, tgt_masked = _scan_markers(text[uid][1])
        if "numbers" in requested:
            for side, value, count in _differences(
                _count_numbers(src_masked, src_mark), _count_numbers(tgt_masked, tgt_mark),
            ):
                add("numbers", uid, "number-" + side, detail={"value": value, "count": count})
        if "symbols" in requested:
            for side, value, count in _differences(_count_symbols(src_masked), _count_symbols(tgt_masked)):
                add("symbols", uid, "symbol-" + side, detail={"value": value, "count": count})
        if "markers" in requested:
            for side, (marker, value), count in _differences(src_markers, tgt_markers):
                add("markers", uid, "marker-" + side, detail={"marker": marker, "value": value, "count": count})

    ran = [check for check in requested if check != "terms"]
    rules, language_skipped = ([], 0) if records is None else _rules(records, source["language"], target["language"])
    if "terms" in requested:
        if records is None:
            skipped.append({"code": "terms", "reason": "no-glossary"})
        elif not rules:
            skipped.append({"code": "terms", "reason": "no-applicable-records"})
        else:
            ran.append("terms")
            for uid in active:
                src_fold, tgt_fold = text[uid][2].casefold(), text[uid][3].casefold()
                for rule in rules:
                    if not any(_find(form, src_fold) for form in rule["forms"]):
                        continue
                    refs = [rule["id"]]
                    if not rule["enforced"]:
                        add("terms", uid, rule["kind"] + "-pending", refs=refs, detail=dict(rule["pending"]))
                        continue
                    if not _find(rule["folded"], tgt_fold):
                        add("terms", uid, rule["kind"] + "-missing", refs=refs, detail={"candidate": rule["candidate"]})
                    if rule["alternatives"]:
                        # Hide the decided rendering first, so a shorter alternative inside it is not reported.
                        masked = _mask(tgt_fold, rule["folded"])
                        for alternative, folded in rule["alternatives"]:
                            if _find(folded, masked):
                                add("terms", uid, "term-alternate", refs=refs, detail={"alternative": alternative})

    entries.sort(key=lambda entry: entry[:3])
    return {
        "findings": [entry[3] for entry in entries], "checks_run": ran, "skipped_checks": skipped,
        "language_skipped": language_skipped,
    }


def check_files(
    source_path: Path, target_path: Path, glossary_paths: Iterable[Path] | None = None,
    checks: Iterable[str] = CHECKS, length_factor: float = 2.0,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Load and compare files; return a validated findings report and summary counts."""
    source, source_hash = load_units(source_path)
    target, target_hash = load_units(target_path)
    if source["role"] == "target" or target["role"] == "source":
        raise ValueError("Source and target roles are reversed")
    glossary_paths = list(glossary_paths or [])
    records, glossary_inputs = load_glossary(glossary_paths) if glossary_paths else (None, [])
    result = run_checks(source, target, records, checks, length_factor)
    loaded = records or []
    report = {
        "report_type": "program-check",
        "producer": {"name": "check_translation", "version": VERSION},
        "target_version": target["version"],
        "inputs": [
            {"role": source["role"], "sha256": source_hash, "units": len(source["units"])},
            {"role": target["role"], "sha256": target_hash, "units": len(target["units"])},
            *glossary_inputs,
        ],
        "checks_run": result["checks_run"],
        "skipped_checks": result["skipped_checks"],
        "synthetic": all(item.get("synthetic") is True for item in [source, target, *loaded]),
        "findings": result["findings"],
    }
    validate("findings", report)
    stats = {
        "units_source": len(source["units"]), "units_target": len(target["units"]),
        "glossary_terms": sum("term_id" in item for item in loaded),
        "glossary_entities": sum("entity_id" in item for item in loaded),
        "glossary_language_skipped": result["language_skipped"],
    }
    return report, stats


def _checks_arg(text: str) -> list[str]:
    names = {name.strip() for name in text.split(",")}
    if not names <= set(CHECKS):
        raise argparse.ArgumentTypeError("use names from: " + ",".join(CHECKS))
    return [name for name in CHECKS if name in names]


def _factor_arg(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and value > 1):
        raise argparse.ArgumentTypeError("use a finite number greater than 1")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare a target units file with its source. Mechanical checks only; meaning is not judged.",
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, action="append", help="term or entity file or folder; repeatable")
    parser.add_argument("--checks", type=_checks_arg, default=list(CHECKS), help="comma list from: " + ",".join(CHECKS))
    parser.add_argument("--report", type=Path, help="new JSON file for the full findings report")
    parser.add_argument("--length-factor", type=_factor_arg, default=2.0)
    args = parser.parse_args(argv)
    hint = missing_dependency_hint()
    if hint:
        # No check can run without schema validation; exit 2 like any other run without checks.
        print(hint)
        return 2
    try:
        report, stats = check_files(args.source, args.target, args.glossary, args.checks, args.length_factor)
        if args.report:
            write_new_outputs(args.source, {args.report: json.dumps(report, ensure_ascii=False, indent=2) + "\n"})
    except Exception as exc:
        # Inputs can be private; print only the exception class.
        print("check_failed=" + type(exc).__name__)
        return 2
    findings = report["findings"]
    lines = [
        f"units_source={stats['units_source']}", f"units_target={stats['units_target']}",
        "checks=" + ",".join(report["checks_run"]),
        f"glossary_terms={stats['glossary_terms']}", f"glossary_entities={stats['glossary_entities']}",
        f"glossary_language_skipped={stats['glossary_language_skipped']}",
    ]
    if report["skipped_checks"]:
        lines.append("skipped=" + ",".join(f"{item['code']}:{item['reason']}" for item in report["skipped_checks"]))
    lines.append(f"findings={len(findings)}")
    lines.extend(
        f"findings_by_code {code}={count}" for code, count in sorted(Counter(f["code"] for f in findings).items())
    )
    for item in findings[:MAX_LISTED]:
        refs = " ref=" + ",".join(item["refs"]) if item.get("refs") else ""
        lines.append(f"finding unit={item['unit_id']} code={item['code']}{refs}")
    if len(findings) > MAX_LISTED:
        lines.append(f"more_findings={len(findings) - MAX_LISTED}")
    if args.report:
        lines.append("report=written")
    print("\n".join(lines))
    # Exit 2 when no check could run, so an empty run is never read as a pass.
    if not report["checks_run"]:
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
