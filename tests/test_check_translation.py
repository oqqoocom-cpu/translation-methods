from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_translation import (
    check_files, extract_markers, extract_numbers, extract_symbols, load_glossary, run_checks, same_language,
)
from tools.validate_assets import validate, validator

# The tools refuse paths through linked directories. On macOS the default temp dir sits
# under the symlink /var, so the tests work in its resolved path.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())

UNITS = ROOT / "examples/units"
GLOSSARY = [ROOT / "examples/term.synthetic.json", ROOT / "examples/entity.synthetic.json"]
TOOL = ROOT / "tools/check_translation.py"
BASE = {
    "term": {
        "term_id": "TERM-TEST-001", "source_form": "gate rule", "target_language": "fr",
        "candidate_target": "regle du portail", "alternatives": ["regle de porte"],
    },
    "entity": {
        "entity_id": "ENT-TEST-001", "source_label": "Harbour Board", "official_name": "Harbour Coordination Board",
        "target_language": "fr", "candidate_target": "Conseil du port",
        "variants": [{"form": "HB", "relation": "abbreviation"}],
    },
}


def units(role: str, language: str, pairs, **extra) -> dict:
    return {
        "role": role, "language": language, "version": "test-1",
        "units": [{"unit_id": unit_id, "text": text} for unit_id, text in pairs], **extra,
    }


def doc(role: str, language: str, *texts: str, **extra) -> dict:
    """Units document whose texts get the IDs UNIT-001, UNIT-002, ..."""
    return units(role, language, [(f"UNIT-{i:03d}", text) for i, text in enumerate(texts, 1)], **extra)


def record(kind: str, **changes) -> dict:
    """Schema-valid en->fr copy of a synthetic glossary fixture; a None value removes the field."""
    value = json.loads((ROOT / "examples" / f"{kind}.synthetic.json").read_text(encoding="utf-8"))
    for key, item in {**BASE[kind], **changes}.items():
        if item is None:
            value.pop(key, None)
        else:
            value[key] = item
    validate(kind, value)
    return value


def codes(result: dict) -> list[tuple[str, str]]:
    return [(item["unit_id"], item["code"]) for item in result["findings"]]


class DemoTests(unittest.TestCase):
    def test_draft_1_reports_the_unlocked_rendering(self):
        report, stats = check_files(UNITS / "source.json", UNITS / "draft-1.json", GLOSSARY)
        term = json.loads(GLOSSARY[0].read_text(encoding="utf-8"))
        self.assertEqual(
            [(item["unit_id"], item["code"], item["refs"]) for item in report["findings"]],
            [("UNIT-DEMO-001", "term-missing", ["TERM-DEMO-001"]), ("UNIT-DEMO-001", "term-alternate", ["TERM-DEMO-001"])],
        )
        self.assertEqual(report["findings"][0]["detail"], {"candidate": term["candidate_target"]})
        self.assertEqual(report["findings"][1]["detail"], {"alternative": term["alternatives"][0]})
        self.assertEqual(report["findings"][0]["locator"], "Clause 1")
        self.assertEqual(report["checks_run"], ["structure", "numbers", "symbols", "markers", "terms"])
        self.assertEqual(report["skipped_checks"], [])
        self.assertTrue(report["synthetic"])
        self.assertEqual((stats["glossary_terms"], stats["glossary_entities"]), (1, 1))

    def test_draft_2_is_clean(self):
        report, _ = check_files(UNITS / "source.json", UNITS / "draft-2.json", GLOSSARY)
        self.assertEqual(report["findings"], [])
        self.assertEqual(len(report["checks_run"]), 5)

    def test_report_records_input_hashes(self):
        report, _ = check_files(UNITS / "source.json", UNITS / "draft-2.json", GLOSSARY)
        paths = [UNITS / "source.json", UNITS / "draft-2.json", *GLOSSARY]
        self.assertEqual([item["role"] for item in report["inputs"]], ["source", "target", "glossary", "glossary"])
        self.assertEqual(
            [item["sha256"] for item in report["inputs"]], [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths],
        )
        self.assertEqual(report["target_version"], "demo-draft-2")
        validate("findings", report)

    def test_drafts_match_the_issue_record(self):
        source, first, second = (
            json.loads((UNITS / name).read_text(encoding="utf-8")) for name in ["source.json", "draft-1.json", "draft-2.json"]
        )
        issue = json.loads((ROOT / "examples/issue.synthetic.json").read_text(encoding="utf-8"))
        self.assertEqual(issue["affected_versions"], [first["version"]])
        self.assertEqual(issue["fix_version"], second["version"])
        changed = [a["unit_id"] for a, b in zip(first["units"], second["units"]) if a != b]
        self.assertEqual(changed, issue["affected_units"])
        ids = [unit["unit_id"] for unit in source["units"]]
        for value in (first, second):
            self.assertEqual([unit["unit_id"] for unit in value["units"]], ids)
        self.assertTrue(all(value["synthetic"] for value in (source, first, second)))

    def test_candidate_term_is_only_pending_on_draft_1(self):
        # Before DEC-DEMO-001 the term was a candidate: the check prompts, it does not enforce.
        term = json.loads(GLOSSARY[0].read_text(encoding="utf-8"))
        term["status"] = "candidate"
        for key in ["decision_id", "decision_reason", "verified_at"]:
            del term[key]
        validate("term", term)
        source, draft = (json.loads((UNITS / name).read_text(encoding="utf-8")) for name in ["source.json", "draft-1.json"])
        result = run_checks(source, draft, [term])
        self.assertEqual(
            [(item["unit_id"], item["code"], item["refs"], item["detail"]) for item in result["findings"]],
            [("UNIT-DEMO-001", "term-pending", ["TERM-DEMO-001"], {"status": "candidate"})],
        )

    def test_merged_findings_example_matches_program_output(self):
        example = json.loads((ROOT / "examples/findings.synthetic.json").read_text(encoding="utf-8"))
        validate("findings", example)
        report, _ = check_files(UNITS / "source.json", UNITS / "draft-1.json", GLOSSARY)
        self.assertEqual(example["report_type"], "merged")
        for key in ["target_version", "inputs", "checks_run", "skipped_checks", "synthetic"]:
            with self.subTest(key=key):
                self.assertEqual(example[key], report[key])
        program = [item for item in example["findings"] if item["origin"] == "program"]
        self.assertEqual(program, report["findings"])
        self.assertEqual({item["origin"] for item in example["findings"]}, {"program", "model"})
        issue = json.loads((ROOT / "examples/issue.synthetic.json").read_text(encoding="utf-8"))
        self.assertEqual(example["target_version"], issue["affected_versions"][0])


class StructureTests(unittest.TestCase):
    def test_missing_extra_and_order(self):
        source = units("source", "en", [("UNIT-A", "one"), ("UNIT-B", "two"), ("UNIT-C", "three")])
        target = units("target", "fr", [("UNIT-C", "trois"), ("UNIT-A", "un"), ("UNIT-D", "quatre")])
        result = run_checks(source, target, checks=["structure"])
        self.assertEqual(codes(result), [("UNIT-B", "unit-missing"), ("UNIT-C", "unit-order"), ("UNIT-D", "unit-extra")])
        self.assertEqual(result["findings"][1]["refs"], ["UNIT-A"])
        self.assertEqual(result["skipped_checks"], [{"code": "length-outlier", "reason": "too-few-units"}])

    def test_duplicate_ids_reported_and_first_unit_compared(self):
        source = units("source", "en", [("UNIT-A", "one"), ("UNIT-A", "again"), ("UNIT-B", "two")])
        target = units("target", "fr", [("UNIT-A", "un"), ("UNIT-B", "deux"), ("UNIT-B", "encore")])
        result = run_checks(source, target, checks=["structure"])
        self.assertEqual(codes(result), [("UNIT-A", "duplicate-unit-id"), ("UNIT-B", "duplicate-unit-id")])
        self.assertEqual(
            [item["detail"] for item in result["findings"]], [{"file": "source", "count": 2}, {"file": "target", "count": 2}],
        )

    def test_empty_and_untranslated_targets(self):
        source = doc("source", "en", "Close the gate.", "NOC", "   ", "Open 3 gates.")
        target = doc("target", "fr", "", "NOC", "", "   ")
        result = run_checks(source, target)
        self.assertEqual(
            codes(result), [("UNIT-001", "target-empty"), ("UNIT-002", "target-untranslated"), ("UNIT-004", "target-empty")],
        )
        # Without the structure check, an empty target is compared like any other unit.
        self.assertEqual(codes(run_checks(source, target, checks=["numbers"])), [("UNIT-004", "number-missing")])

    def test_same_language_edit_is_not_untranslated(self):
        source = doc("source", "en", "Colour the gate.")
        target = doc("target", "en-GB", "Colour the gate.")
        self.assertEqual(run_checks(source, target, checks=["structure"])["findings"], [])

    def test_language_tags(self):
        self.assertTrue(same_language("en", "EN_us"))
        self.assertTrue(same_language("en-GB", "en"))
        self.assertFalse(same_language("en", "fr"))
        self.assertFalse(same_language("zh-Hans", "zh-Hant"))

    def test_duplicate_target_and_inconsistent_repeat(self):
        source = doc(
            "source", "en", "The gate stays closed at night.", "The shed stays locked at night.",
            "Members vote once a year.", "Members vote once a year.",
        )
        target = doc(
            "target", "fr", "La porte reste fermee la nuit.", "La porte reste fermee la nuit.",
            "Les membres votent une fois par an.", "Les membres votent chaque annee.",
        )
        result = run_checks(source, target, checks=["structure"])
        self.assertEqual(codes(result), [("UNIT-002", "target-duplicate"), ("UNIT-004", "repeat-inconsistent")])
        self.assertEqual([item["refs"] for item in result["findings"]], [["UNIT-001"], ["UNIT-003"]])

    def test_length_outlier(self):
        letters = "ABCDEF"
        source = doc("source", "en", *(f"Rule {x} applies to every member household." for x in letters))
        target_texts = [f"La regle {x} vaut pour chaque foyer membre." for x in letters]
        target_texts[-1] *= 5
        target = doc("target", "fr", *target_texts)
        result = run_checks(source, target, checks=["structure"])
        self.assertEqual(codes(result), [("UNIT-006", "length-outlier")])
        self.assertEqual(result["findings"][0]["detail"], {"ratio": round(170 / 35, 3), "median": round(34 / 35, 3)})
        self.assertEqual(run_checks(source, target, checks=["structure"], length_factor=6.0)["findings"], [])

    def test_invalid_arguments(self):
        source, target = doc("source", "en", "a"), doc("target", "fr", "b")
        for kwargs in [{"checks": []}, {"checks": ["spelling"]}, {"length_factor": 1.0}, {"length_factor": float("nan")}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_checks(source, target, **kwargs)


class ProtectedTests(unittest.TestCase):
    def test_number_normalization(self):
        self.assertEqual(extract_numbers("1,250 credits, 3.50 m, 007"), Counter({"1250": 1, "3.5": 1, "7": 1}))
        self.assertEqual(extract_numbers("1.250,5 und 2,5", ","), Counter({"1250.5": 1, "2.5": 1}))
        self.assertEqual(extract_numbers("\uff11\uff14 \u0661\u0664"), Counter({"14": 2}))
        self.assertEqual(extract_numbers("see [12] and https://example.org/2026/10 and 3"), Counter({"3": 1}))

    def test_chinese_count_words(self):
        wan, wan_t, yi, yi_t = "\u4e07", "\u842c", "\u4ebf", "\u5104"
        for text, expected in [
            ("3.5" + wan, "35000"), ("1.2" + yi, "120000000"), ("2" + wan + yi, "2000000000000"),
            ("1.2" + wan + yi, "1200000000000"), ("3" + wan_t, "30000"), ("1.5" + yi_t, "150000000"),
            ("3.5 " + wan, "35000"), ("1,250" + wan, "12500000"), ("0.05" + wan, "500"),
        ]:
            with self.subTest(text=ascii(text)):
                self.assertEqual(extract_numbers(text), Counter({expected: 1}))
        self.assertEqual(extract_numbers("1,5" + wan, ","), Counter({"15000": 1}))
        # Only a count word right after a digit is read, so in "3 wan 5 qian" the 5 stays 5. The word for
        # 1,000 is left out because it also starts the words for km and kg; Chinese numerals are not read.
        self.assertEqual(extract_numbers("3" + wan + "5\u5343"), Counter({"30000": 1, "5": 1}))
        self.assertEqual(extract_numbers("5\u5343\u7c73"), Counter({"5": 1}))
        self.assertEqual(extract_numbers("\u5341" + wan), Counter())

    def test_count_word_compared_by_value(self):
        source = doc("source", "en", "Raise 35,000 credits.")
        same = doc("target", "zh", "\u7b79\u96c63.5\u4e07\u79ef\u5206\u3002")
        self.assertEqual(run_checks(source, same, checks=["numbers"])["findings"], [])
        changed = doc("target", "zh", "\u7b79\u96c63.6\u4e07\u79ef\u5206\u3002")
        result = run_checks(source, changed, checks=["numbers"])
        self.assertEqual(codes(result), [("UNIT-001", "number-missing"), ("UNIT-001", "number-extra")])
        self.assertEqual(
            [item["detail"] for item in result["findings"]], [{"value": "35000", "count": 1}, {"value": "36000", "count": 1}],
        )

    def test_english_count_words(self):
        for text, expected in [
            ("3.5 million", {"3500000": 1}), ("1.2 billion", {"1200000000": 1}),
            ("2 trillion", {"2000000000000": 1}), ("5 thousand", {"5000": 1}),
            ("3.5million", {"3500000": 1}), ("1.5-billion", {"1500000000": 1}),
            ("3.5 Million", {"3500000": 1}), ("3.5 MILLION", {"3500000": 1}),
            ("1,000 million", {"1000000000": 1}), ("5\u00a0million", {"5000000": 1}),
            # Only the number right before the count word is scaled.
            ("5-10 million", {"5": 1, "10000000": 1}),
            # Plurals, ordinals, longer words, abbreviations and a dotless i are not read as count words.
            ("3 millionth", {"3": 1}), ("3 millions", {"3": 1}), ("3 thousandfold", {"3": 1}),
            ("3m", {"3": 1}), ("3 bn", {"3": 1}), ("3 m\u0131ll\u0131on", {"3": 1}),
        ]:
            with self.subTest(text=ascii(text)):
                self.assertEqual(extract_numbers(text, english_scales=True), Counter(expected))
        self.assertEqual(extract_numbers("3,5 million", ",", english_scales=True), Counter({"3500000": 1}))
        # English count words are read only on request.
        self.assertEqual(extract_numbers("3.5 million"), Counter({"3.5": 1}))

    def test_english_count_words_compared_by_value(self):
        def findings(source: dict, target: dict) -> list:
            return run_checks(source, target, checks=["numbers"])["findings"]

        source = doc("source", "en", "Raise 5 million credits.")
        for language, text in [
            ("zh", "\u7b79\u96c6500\u4e07\u79ef\u5206\u3002"),
            ("ja", "500\u4e07\u30af\u30ec\u30b8\u30c3\u30c8\u3002"),
            ("en-GB", "Raise 5,000,000 credits."),
            # French count words are not read, so neither side is scaled.
            ("fr", "Collectez 5 millions de credits."),
            # English left in a Chinese target is read the same way as in the source.
            ("zh", "\u7b79\u96c6 5 million \u79ef\u5206\u3002"),
            ("zh", "Raise 5 million credits."),
        ]:
            with self.subTest(language=language, text=ascii(text)):
                self.assertEqual(findings(source, doc("target", language, text)), [])
        chinese = doc("source", "zh", "\u7b79\u96c6500\u4e07\u79ef\u5206\u3002")
        self.assertEqual(findings(chinese, doc("target", "en", "Raise 5 million credits.")), [])
        german = doc("target", "de", "Ausgaben von 2 Billionen.")
        self.assertEqual(findings(doc("source", "en", "Spend 2 trillion."), german), [])
        result = run_checks(source, doc("target", "zh", "\u7b79\u96c65\u4e07\u79ef\u5206\u3002"), checks=["numbers"])
        self.assertEqual(codes(result), [("UNIT-001", "number-missing"), ("UNIT-001", "number-extra")])
        self.assertEqual(
            [item["detail"] for item in result["findings"]],
            [{"value": "5000000", "count": 1}, {"value": "50000", "count": 1}],
        )

    def test_numbers_compared_by_value_and_count(self):
        source = doc("source", "en", "Pay 1,250 credits within 14 days.", "Use 2.5 kg.")
        target = doc("target", "de", "Zahle 1250 Punkte binnen 15 Tagen.", "Nimm 2,5 kg.", decimal_mark=",")
        result = run_checks(source, target, checks=["numbers"])
        self.assertEqual(codes(result), [("UNIT-001", "number-missing"), ("UNIT-001", "number-extra")])
        self.assertEqual([item["detail"] for item in result["findings"]], [{"value": "14", "count": 1}, {"value": "15", "count": 1}])

    def test_unit_symbols(self):
        self.assertEqual(extract_symbols("5 km, 10%, 3 s, 2 kg"), Counter({"km": 1, "%": 1, "s": 1, "kg": 1}))
        self.assertEqual(extract_symbols("25 \u00b0C"), Counter({"\u00b0C": 1}))
        self.assertEqual(extract_symbols("the 1990s, 3 times, 5 minutes, 2 hours"), Counter())

    def test_symbol_written_as_word_is_reported(self):
        result = run_checks(doc("source", "en", "Walk 5 km."), doc("target", "fr", "Marchez 5 kilometres."), checks=["symbols"])
        self.assertEqual(codes(result), [("UNIT-001", "symbol-missing")])
        self.assertEqual(result["findings"][0]["detail"], {"value": "km", "count": 1})

    def test_url_and_reference_markers(self):
        self.assertEqual(extract_markers("See https://example.org/a."), Counter({("url", "https://example.org/a"): 1}))
        self.assertEqual(
            extract_markers("(see https://example.org/a_(b))."), Counter({("url", "https://example.org/a_(b)"): 1}),
        )
        self.assertEqual(
            extract_markers("see [12] and [3\u20135]"), Counter({("ref", "[12]"): 1, ("ref", "[3-5]"): 1}),
        )
        self.assertEqual(extract_markers("50% of 3 %d"), Counter({("printf", "%d"): 1}))

    def test_marker_differences(self):
        source = doc("source", "en", "<b>Save</b> {name}", "{{ count }} files", "%d of %s")
        target = doc("target", "fr", "Enregistrer {nom}", "{{count}} fichiers", "%s sur %d")
        result = run_checks(source, target, checks=["markers"])
        self.assertEqual(
            [(item["unit_id"], item["code"], item["detail"]["marker"], item["detail"]["value"]) for item in result["findings"]],
            [
                ("UNIT-001", "marker-missing", "tag", "<b>"), ("UNIT-001", "marker-missing", "tag", "</b>"),
                ("UNIT-001", "marker-missing", "placeholder", "{name}"),
                ("UNIT-001", "marker-extra", "placeholder", "{nom}"),
            ],
        )


class TermTests(unittest.TestCase):
    source = doc("source", "en", "The gate rule applies.")

    def test_locked_term_missing_and_alternate(self):
        target = doc("target", "fr", "La regle de porte s'applique.")
        result = run_checks(self.source, target, [record("term")], checks=["terms"])
        self.assertEqual(codes(result), [("UNIT-001", "term-missing"), ("UNIT-001", "term-alternate")])
        self.assertEqual(result["checks_run"], ["terms"])

    def test_alternate_inside_decided_rendering_not_reported(self):
        value = record("term", candidate_target="regle du portail nord", alternatives=["regle du portail"])
        target = doc("target", "fr", "La regle du portail nord s'applique.")
        self.assertEqual(run_checks(self.source, target, [value], checks=["terms"])["findings"], [])

    def test_source_match_needs_word_start(self):
        source = doc("source", "en", "The tailgate rule applies.")
        result = run_checks(source, doc("target", "fr", "Rien."), [record("term")], checks=["terms"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["checks_run"], ["terms"])

    def test_cjk_term_matches_inside_text(self):
        value = record(
            "term", source_form="\u679c\u56ed", source_language="zh", target_language="en",
            candidate_target="orchard", alternatives=[],
        )
        source = doc("source", "zh", "\u5317\u679c\u56ed\u89c4\u5219")
        result = run_checks(source, doc("target", "en", "North garden rule"), [value], checks=["terms"])
        self.assertEqual(codes(result), [("UNIT-001", "term-missing")])

    def test_unlocked_term_is_pending(self):
        target = doc("target", "fr", "La regle du portail s'applique.")
        for status in ["candidate", "under-review", "verified"]:
            with self.subTest(status=status):
                result = run_checks(self.source, target, [record("term", status=status)], checks=["terms"])
                self.assertEqual(codes(result), [("UNIT-001", "term-pending")])
                self.assertEqual(result["findings"][0]["detail"], {"status": status})

    def test_rejected_and_deprecated_terms_ignored(self):
        for status in ["rejected", "deprecated"]:
            with self.subTest(status=status):
                value = record("term", status=status, rejection_reason="Synthetic noise")
                result = run_checks(self.source, doc("target", "fr", "Rien."), [value], checks=["terms"])
                self.assertEqual((result["findings"], result["checks_run"]), ([], []))
                self.assertEqual(result["skipped_checks"], [{"code": "terms", "reason": "no-applicable-records"}])

    def test_term_language_scope(self):
        regional = run_checks(self.source, doc("target", "fr-CA", "Rien."), [record("term")], checks=["terms"])
        self.assertEqual(codes(regional), [("UNIT-001", "term-missing")])
        other = doc("target", "de", "Nichts.")
        result = run_checks(self.source, other, [record("term")], checks=["terms"])
        self.assertEqual(result["language_skipped"], 1)
        self.assertEqual(result["skipped_checks"], [{"code": "terms", "reason": "no-applicable-records"}])
        # A term without a target language applies to every target language.
        open_term = record("term", status="candidate", target_language=None, candidate_target=None)
        self.assertEqual(codes(run_checks(self.source, other, [open_term], checks=["terms"])), [("UNIT-001", "term-pending")])

    def test_entity_variants_and_decision(self):
        source = doc("source", "en", "The HB meets monthly.", "The Harbour Board keeps minutes.", "The board votes.")
        target = doc("target", "fr", "Le Conseil du port se reunit.", "Le HB tient les proces-verbaux.", "Le conseil vote.")
        result = run_checks(source, target, [record("entity")], checks=["terms"])
        self.assertEqual(codes(result), [("UNIT-002", "entity-missing")])
        self.assertEqual(result["findings"][0]["refs"], ["ENT-TEST-001"])

    def test_entity_without_decision_or_candidate(self):
        source = doc("source", "en", "The Harbour Board keeps minutes.")
        target = doc("target", "fr", "Le conseil tient les proces-verbaux.")
        pending = record("entity", decision_id=None, official_status="not-checked")
        result = run_checks(source, target, [pending], checks=["terms"])
        self.assertEqual(codes(result), [("UNIT-001", "entity-pending")])
        self.assertEqual(result["findings"][0]["detail"], {"official_status": "not-checked"})
        result = run_checks(source, target, [record("entity", candidate_target=None)], checks=["terms"])
        self.assertEqual(result["skipped_checks"], [{"code": "terms", "reason": "no-applicable-records"}])

    def test_no_glossary_skips_terms(self):
        result = run_checks(self.source, doc("target", "fr", "La regle s'applique."))
        self.assertNotIn("terms", result["checks_run"])
        self.assertIn({"code": "terms", "reason": "no-glossary"}, result["skipped_checks"])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name: str, value, prefix: bytes = b"") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(prefix + json.dumps(value, ensure_ascii=False).encode("utf-8"))
        return path

    def test_reversed_roles_rejected(self):
        with self.assertRaises(ValueError):
            check_files(UNITS / "draft-1.json", UNITS / "source.json")

    def test_units_schema_enforced(self):
        source = json.loads((UNITS / "source.json").read_text(encoding="utf-8"))
        broken = [
            dict(source, units=[]), dict(source, extra="field"), dict(source, decimal_mark=";"),
            {key: item for key, item in source.items() if key != "version"},
            dict(source, units=[{"unit_id": "unit-1", "text": "x"}]),
            dict(source, units=[{"unit_id": "UNIT-A", "text": "x", "note": "y"}]),
        ]
        for index, value in enumerate(broken):
            with self.subTest(index=index), self.assertRaises((ValidationError, ValueError)):
                validate("units", value)

    def test_bom_tolerated_and_hashed_as_bytes(self):
        value = json.loads((UNITS / "source.json").read_text(encoding="utf-8"))
        path = self.write("source.json", value, prefix=b"\xef\xbb\xbf")
        report, _ = check_files(path, UNITS / "draft-2.json", GLOSSARY)
        self.assertEqual(report["inputs"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(report["findings"], [])

    def test_report_synthetic_only_when_all_inputs_are(self):
        value = json.loads((UNITS / "draft-2.json").read_text(encoding="utf-8"))
        del value["synthetic"]
        report, _ = check_files(UNITS / "source.json", self.write("draft.json", value), GLOSSARY)
        self.assertFalse(report["synthetic"])

    def test_glossary_folder_and_duplicate_ids(self):
        term = record("term")
        self.write("glossary/b/entity.json", record("entity"))
        self.write("glossary/a/terms.json", [term])
        records, inputs = load_glossary([self.root / "glossary", self.root / "glossary/a/terms.json"])
        self.assertEqual([item.get("term_id", item.get("entity_id")) for item in records], ["TERM-TEST-001", "ENT-TEST-001"])
        self.assertEqual([item["records"] for item in inputs], [1, 1])
        self.write("glossary/c/again.json", term)
        with self.assertRaises(ValueError):
            load_glossary([self.root / "glossary"])

    def test_templates_refused(self):
        with self.assertRaises(ValueError):
            load_glossary([ROOT / "templates/term.blank.json"])


class CliTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(TOOL), *args], capture_output=True, text=True)

    def demo_args(self, draft: str) -> list[str]:
        args = ["--source", str(UNITS / "source.json"), "--target", str(UNITS / draft)]
        for path in GLOSSARY:
            args += ["--glossary", str(path)]
        return args

    def test_exit_codes(self):
        first = self.run_tool(*self.demo_args("draft-1.json"))
        self.assertEqual(first.returncode, 1, first.stdout)
        self.assertIn("finding unit=UNIT-DEMO-001 code=term-missing ref=TERM-DEMO-001", first.stdout)
        second = self.run_tool(*self.demo_args("draft-2.json"))
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertIn("findings=0", second.stdout)

    def test_terms_only_without_glossary_is_not_a_pass(self):
        result = self.run_tool(
            "--source", str(UNITS / "source.json"), "--target", str(UNITS / "draft-2.json"), "--checks", "terms",
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("skipped=terms:no-glossary", result.stdout)

    def test_bad_arguments(self):
        base = ["--source", str(UNITS / "source.json"), "--target", str(UNITS / "draft-2.json")]
        for extra in [["--checks", "spelling"], ["--length-factor", "1"], ["--length-factor", "nan"]]:
            with self.subTest(extra=extra):
                self.assertEqual(self.run_tool(*base, *extra).returncode, 2)

    def test_output_does_not_echo_text(self):
        text = "Zebra-Quartz private clause 77"
        with tempfile.TemporaryDirectory() as directory:
            source, target, broken = (Path(directory) / name for name in ["source.json", "target.json", "broken.json"])
            for path, role, unit in [
                (source, "source", {"unit_id": "UNIT-A", "text": text}),
                (target, "target", {"unit_id": "UNIT-A", "text": text}),
                (broken, "source", {"unit_id": "UNIT-A", "text": text, "note": text}),
            ]:
                value = {"role": role, "language": "en" if role == "source" else "fr", "version": "v1", "units": [unit]}
                path.write_text(json.dumps(value), encoding="utf-8")
            result = self.run_tool("--source", str(source), "--target", str(target))
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("code=target-untranslated", result.stdout)
            self.assertNotIn("Zebra", result.stdout + result.stderr)
            result = self.run_tool("--source", str(broken), "--target", str(target))
            self.assertEqual((result.returncode, result.stdout.strip()), (2, "check_failed=ValidationError"))
            self.assertNotIn("Zebra", result.stdout + result.stderr)

    def test_report_written_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "findings.json"
            first = self.run_tool(*self.demo_args("draft-1.json"), "--report", str(path))
            self.assertEqual(first.returncode, 1, first.stdout)
            self.assertIn("report=written", first.stdout)
            report = json.loads(path.read_text(encoding="utf-8"))
            validate("findings", report)
            self.assertEqual(len(report["findings"]), 2)
            before = path.read_bytes()
            repeated = self.run_tool(*self.demo_args("draft-2.json"), "--report", str(path))
            self.assertEqual(repeated.returncode, 2, repeated.stdout)
            self.assertEqual(path.read_bytes(), before)


class CacheTests(unittest.TestCase):
    def test_validator_built_once_per_kind(self):
        self.assertIs(validator("units"), validator("units"))
        self.assertIsNot(validator("units"), validator("findings"))


if __name__ == "__main__":
    unittest.main()
