from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sync_registry import make_snapshot, registry_hash, render_markdown, write_new_outputs
from tools.validate_assets import TIERS, load_json, rules_for_tier, validate, validate_application, validator
from tools.check_release import RISK_PATTERNS, check_release

# The tools refuse paths through linked directories. On macOS the default temp dir sits
# under the symlink /var, so the tests work in its resolved path.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())


def fixture(kind: str) -> dict:
    return json.loads((ROOT / "examples" / f"{kind}.synthetic.json").read_text(encoding="utf-8"))


def registry() -> dict:
    return json.loads((ROOT / "registry/public.registry.json").read_text(encoding="utf-8"))


def rule_id_pattern(ids) -> re.Pattern:
    # Match whole rule IDs only, so QA-DEMO-001 or ERROR-001 never yield a shorter false ID.
    prefixes = "|".join(map(re.escape, sorted({rule_id.rsplit("-", 1)[0] for rule_id in ids})))
    return re.compile(rf"(?<![A-Za-z0-9-])(?:{prefixes})-\d{{3}}(?![A-Za-z0-9-])")


class SchemaTests(unittest.TestCase):
    def reject(self, kind: str, value: dict) -> None:
        with self.assertRaises((ValidationError, ValueError)):
            validate(kind, value)

    def test_all_schemas_valid(self):
        for path in (ROOT / "schemas").glob("*.schema.json"):
            validator(path.name.removesuffix(".schema.json"))

    def test_positive_examples(self):
        for kind in ["term", "entity", "decision", "issue", "quality-report", "findings"]:
            with self.subTest(kind=kind):
                value = fixture(kind)
                self.assertTrue(value["synthetic"])
                validate(kind, value)

    def test_registry_valid(self):
        validate("registry", registry())
        self.assertEqual(len(registry()["requirements"]), 32)

    def test_general_scope_and_conditional_research_layer(self):
        value = registry()
        self.assertNotIn("\u7814\u7a76\u578b\u957f\u7bc7", value["purpose"])
        rules = {rule["id"]: rule for rule in value["requirements"]}
        research = rules["RESEARCH-001"]
        self.assertEqual(research["strength"], "mandatory-when-applicable")
        self.assertIn("\u7814\u7a76\u8f85\u52a9\u5c42", research["condition"])
        self.assertEqual(rules["TRANS-001"]["strength"], "mandatory")
        self.assertEqual(rules["REVIEW-001"]["strength"], "mandatory")
        self.assertEqual(rules["PRIV-001"]["strength"], "mandatory")

    def test_tiers_are_cumulative(self):
        value = registry()
        sets = [set(rules_for_tier(value, tier)) for tier in TIERS]
        self.assertEqual([len(item) for item in sets], [10, 25, 32])
        self.assertTrue(sets[0] < sets[1] < sets[2])
        strengths = [rule["strength"] for rule in value["requirements"]]
        self.assertEqual(strengths.count("mandatory"), 22)
        self.assertEqual(strengths.count("mandatory-when-applicable"), 10)

    def test_core_and_benchmark_rule_tiers(self):
        rules = {rule["id"]: rule for rule in registry()["requirements"]}
        for rule_id in ["TRANS-001", "REVIEW-001", "QA-001", "PRIV-001", "SOURCE-001", "RIGHTS-001"]:
            with self.subTest(rule=rule_id):
                self.assertEqual((rules[rule_id]["tier"], rules[rule_id]["strength"]), ("light", "mandatory"))
        for rule_id in ["QA-002", "BENCH-001", "MODEL-001"]:
            with self.subTest(rule=rule_id):
                self.assertEqual(
                    (rules[rule_id]["tier"], rules[rule_id]["strength"]), ("full", "mandatory-when-applicable"),
                )

    def test_rule_tier_required_and_known(self):
        value = registry()
        del value["requirements"][0]["tier"]
        self.reject("registry", value)
        value = registry()
        value["requirements"][0]["tier"] = "medium"
        self.reject("registry", value)

    def test_application_valid(self):
        validate_application(fixture("application"), registry())

    def test_locked_term_requires_evidence_and_decision(self):
        for field in [
            "evidence", "scope", "decision_reason", "decision_id", "verified_at", "target_language", "candidate_target",
        ]:
            with self.subTest(field=field):
                value = fixture("term")
                del value[field]
                self.reject("term", value)

    def test_empty_evidence_rejected(self):
        value = fixture("term")
        value["evidence"] = []
        self.reject("term", value)

    def test_date_format_checked(self):
        value = fixture("term")
        value["verified_at"] = "2026-99-99"
        self.reject("term", value)

    def test_whitespace_reason_rejected(self):
        value = fixture("term")
        value["decision_reason"] = " \n "
        self.reject("term", value)

    def test_noise_rejection_needs_reason(self):
        value = fixture("term")
        value["status"] = "rejected"
        self.reject("term", value)
        value["rejection_reason"] = "Synthetic ordinary-word noise"
        validate("term", value)

    def test_entity_dual_track_required(self):
        value = fixture("entity")
        del value["official_name"]
        self.reject("entity", value)

    def test_entity_self_relation_rejected(self):
        value = fixture("entity")
        value["relations"] = [{"entity_id": value["entity_id"], "relation": "not-identical-to"}]
        self.reject("entity", value)

    def test_entity_duplicate_variant_rejected(self):
        value = fixture("entity")
        value["variants"] *= 2
        self.reject("entity", value)

    def test_accepted_decision_needs_regression(self):
        value = fixture("decision")
        del value["regression_refs"]
        self.reject("decision", value)

    def test_fixed_issue_needs_regression(self):
        value = fixture("issue")
        value["status"] = "fixed"
        value["regression_status"] = "pending"
        self.reject("issue", value)

    def test_closed_issue_needs_responsibility(self):
        value = fixture("issue")
        del value["closed_by"]
        self.reject("issue", value)

    def test_issue_fix_needs_affected_versions(self):
        value = fixture("issue")
        value["affected_versions"] = []
        self.reject("issue", value)

    def test_report_no_checks_rejected(self):
        value = fixture("quality-report")
        value["checks"] = []
        self.reject("quality-report", value)

    def test_report_critical_gate(self):
        value = fixture("quality-report")
        value["open_critical"] = 1
        self.reject("quality-report", value)

    def test_report_major_gate(self):
        value = fixture("quality-report")
        value["open_major"] = 1
        self.reject("quality-report", value)

    def test_report_high_risk_gate(self):
        value = fixture("quality-report")
        value["unresolved_high_risk"] = 1
        self.reject("quality-report", value)

    def test_report_independent_review_required(self):
        value = fixture("quality-report")
        value["independent_review"] = False
        self.reject("quality-report", value)

    def test_report_check_status_must_pass(self):
        value = fixture("quality-report")
        value["checks"][0]["status"] = "pending"
        self.reject("quality-report", value)

    def test_report_coverage_gate(self):
        for field in ["high_risk_reviewed", "protected_checked"]:
            with self.subTest(field=field):
                value = fixture("quality-report")
                value[field] = 0
                self.reject("quality-report", value)

    def test_report_excess_count_rejected(self):
        value = fixture("quality-report")
        value["protected_checked"] = value["protected_total"] + 1
        self.reject("quality-report", value)

    def test_report_required_families(self):
        value = fixture("quality-report")
        value["checks"].pop()
        self.reject("quality-report", value)

    def test_report_duplicate_checks(self):
        value = fixture("quality-report")
        value["checks"].append(copy.deepcopy(value["checks"][0]))
        self.reject("quality-report", value)

    def test_synthetic_cannot_verify_real_record(self):
        for kind in ["term", "entity", "decision", "quality-report", "application"]:
            with self.subTest(kind=kind):
                value = fixture(kind)
                value["synthetic"] = False
                self.reject(kind, value)

    def test_duplicate_registry_rule_rejected(self):
        value = registry()
        value["requirements"].append(copy.deepcopy(value["requirements"][0]))
        self.reject("registry", value)

    def test_empty_registry_rejected(self):
        value = registry()
        value["requirements"] = []
        self.reject("registry", value)

    def test_conditional_rule_needs_condition(self):
        value = registry()
        rule = next(r for r in value["requirements"] if r["strength"] == "mandatory-when-applicable")
        del rule["condition"]
        self.reject("registry", value)

    def test_application_exception_needs_reason(self):
        value = make_snapshot(registry(), "DEMO-NEW", "intake", "standard")
        value["rules"][0]["applicability"] = "exception"
        self.reject("application", value)
        value["rules"][0].update(reason="Synthetic exception reason", decision_id="DEC-DEMO-NEW")
        validate_application(value, registry())

    def test_application_pending_cannot_pass(self):
        value = make_snapshot(registry(), "DEMO-NEW", "intake", "standard")
        value["synthetic"] = True
        value["rules"][0].update(acceptance="passed", evidence=[{
            "evidence_id": "EVID-DEMO-NEW", "kind": "synthetic", "locator": "Synthetic check", "checked_at": "2026-10-11",
        }])
        self.reject("application", value)
        value["rules"][0]["applicability"] = "applicable"
        validate_application(value, registry())

    def test_application_missing_rule_rejected(self):
        value = fixture("application")
        value["rules"].pop()
        with self.assertRaises(ValueError):
            validate_application(value, registry())

    def test_application_hash_mismatch(self):
        value = fixture("application")
        value["registry_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_application(value, registry())

    def test_application_needs_process_tier(self):
        value = fixture("application")
        del value["process_tier"]
        self.reject("application", value)

    def test_application_tier_must_match_rules(self):
        for tier in ["light", "full"]:
            with self.subTest(tier=tier):
                value = fixture("application")
                value["process_tier"] = tier
                with self.assertRaises(ValueError):
                    validate_application(value, registry())

    def test_application_extra_rule_rejected(self):
        value = fixture("application")
        value["rules"].append({"id": "GOV-003", "applicability": "pending", "acceptance": "pending"})
        with self.assertRaises(ValueError):
            validate_application(value, registry())

    def test_candidate_target_needs_target_language(self):
        value = fixture("term")
        value["status"] = "candidate"
        validate("term", value)
        del value["target_language"]
        self.reject("term", value)
        value = fixture("entity")
        del value["target_language"]
        self.reject("entity", value)
        del value["candidate_target"]
        validate("entity", value)

    def test_no_language_specific_field_names(self):
        pattern = re.compile(r'"[a-z_]*_zh"')
        paths = [
            *(ROOT / "schemas").glob("*.json"), *(ROOT / "templates").glob("*.json"),
            *(ROOT / "examples").glob("*.json"), *(ROOT / "registry").glob("*.json"),
        ]
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))

    def test_examples_cross_reference(self):
        term, entity, decision = fixture("term"), fixture("entity"), fixture("decision")
        issue, report = fixture("issue"), fixture("quality-report")
        self.assertEqual({term["decision_id"], entity["decision_id"]}, {decision["decision_id"]})
        self.assertEqual(issue["fix_version"], report["target_version"])
        self.assertEqual(issue["regression_refs"], decision["regression_refs"])
        self.assertLessEqual(set(issue["affected_units"]), set(decision["affected_units"]))

    def test_delivery_snapshot_records_not_applicable_rules(self):
        value = fixture("application")
        self.assertEqual((value["process_tier"], value["phase"]), ("standard", "delivery"))
        excluded = {rule["id"] for rule in value["rules"] if rule["applicability"] == "not-applicable"}
        self.assertEqual(excluded, {"MULTI-002", "MULTI-003", "QA-003", "BENCH-002"})
        conditional = {
            rule["id"] for rule in registry()["requirements"] if rule["strength"] == "mandatory-when-applicable"
        }
        self.assertLessEqual(excluded, conditional)
        self.assertTrue(all(rule["decision_id"] == "DEC-DEMO-002" for rule in value["rules"] if rule["id"] in excluded))
        self.assertTrue(all(rule["acceptance"] == "passed" for rule in value["rules"]))
        self.assertEqual(sum(rule["applicability"] == "applicable" for rule in value["rules"]), 21)


class ToolTests(unittest.TestCase):
    def test_public_registry_markdown_is_current(self):
        self.assertEqual(
            (ROOT / "registry/public.registry.md").read_text(encoding="utf-8"),
            render_markdown(registry()),
        )

    def test_snapshot_is_pending(self):
        value = make_snapshot(registry(), "DEMO-NEW", "intake", "standard")
        self.assertTrue(all(r["acceptance"] == r["applicability"] == "pending" for r in value["rules"]))

    def test_snapshot_size_follows_tier(self):
        for tier, size in zip(TIERS, [10, 25, 32]):
            with self.subTest(tier=tier):
                value = make_snapshot(registry(), "DEMO-NEW", "intake", tier)
                self.assertEqual((value["process_tier"], len(value["rules"])), (tier, size))

    def test_unknown_tier_rejected(self):
        with self.assertRaises(ValueError):
            make_snapshot(registry(), "DEMO-NEW", "intake", "medium")

    def test_hash_ignores_key_order(self):
        value = registry()
        reordered = dict(reversed(list(value.items())))
        self.assertEqual(registry_hash(value), registry_hash(reordered))

    def test_markdown_escapes_all_cells(self):
        value = registry()
        for field in ["category", "title", "requirement", "verification"]:
            value["requirements"][0][field] = "a|b\n<script>"
        rendered = render_markdown(value)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("a|b", rendered)
        self.assertEqual(rendered.count("a&#124;b &lt;script&gt;"), 4)

    def test_input_overwrite_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "registry.json"
            source.write_text("original", encoding="utf-8")
            with self.assertRaises(ValueError):
                write_new_outputs(source, {source: "modified"})
            self.assertEqual(source.read_text(encoding="utf-8"), "original")

    def test_existing_output_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, first, existing = root / "in.json", root / "first.md", root / "existing.md"
            source.write_text("input", encoding="utf-8")
            existing.write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                write_new_outputs(source, {first: "new", existing: "bad"})
            self.assertFalse(first.exists())
            self.assertEqual(existing.read_text(encoding="utf-8"), "keep")

    def test_duplicate_resolved_targets_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "in.json"
            source.write_text("input", encoding="utf-8")
            first = root / "new.md"
            second = root / "unused" / ".." / "new.md"
            with self.assertRaises(ValueError):
                write_new_outputs(source, {first: "one", second: "two"})
            self.assertFalse(first.exists())

    def test_cli_new_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, snapshot = root / "rules.md", root / "application.json"
            command = [
                sys.executable, "-B", str(ROOT / "tools/sync_registry.py"),
                str(ROOT / "registry/public.registry.json"), "--markdown", str(output),
                "--snapshot", str(snapshot), "--project-id", "DEMO-NEW", "--phase", "intake",
                "--tier", "standard",
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            validate_application(json.loads(snapshot.read_text(encoding="utf-8")), registry())
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)

    def test_cli_invalid_input_creates_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "bad.json", Path(directory) / "new.md"
            source.write_text("{}", encoding="utf-8")
            result = subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/sync_registry.py"),
                str(source), "--markdown", str(output),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "duplicate.json"
            source.write_text('{"registry_version": "one", "registry_version": "two"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_json(source)

    def test_cli_application_checks_registry_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "application.json"
            value = fixture("application")
            value["rules"].pop()
            source.write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/validate_assets.py"),
                "--kind", "application", "--file", str(source),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_cli_snapshot_requires_tier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, snapshot = root / "rules.md", root / "application.json"
            result = subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/sync_registry.py"),
                str(ROOT / "registry/public.registry.json"), "--markdown", str(output),
                "--snapshot", str(snapshot), "--project-id", "DEMO-NEW", "--phase", "intake",
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertFalse(snapshot.exists())


class PackagingTests(unittest.TestCase):
    def test_license_map_declares_dual_scope(self):
        text = (ROOT / "LICENSE.md").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("CC BY 4.0", text)
        self.assertIn("tools/", text)
        self.assertIn("docs/", text)

    def test_manifest_covers_every_file(self):
        result = check_release(ROOT)
        self.assertTrue(result["byte_hashes"])
        self.assertFalse(result["publication_authorized"])

    def test_no_bom_and_all_utf8(self):
        for path in ROOT.rglob("*"):
            if path.is_file() and path.relative_to(ROOT).parts[0] != ".git":
                raw = path.read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path.name)
                raw.decode("utf-8")

    def test_risk_patterns_catch_tokens_next_to_cjk(self):
        cjk = chr(0x89C1)
        unit = "BOOK" + "-" + "1234"
        for kind, value in [
            ("local-path", cjk + chr(68) + ":" + chr(92) + "private"), ("local-path", cjk + chr(67) + ":/x"),
            ("private-unit-id", cjk + unit), ("private-unit-id", unit + cjk),
        ]:
            with self.subTest(kind=kind, value=ascii(value)):
                self.assertIsNotNone(RISK_PATTERNS[kind].search(value))
        for value in ["https://example.org", "mailto:a@b.c", "abc:/x"]:
            with self.subTest(value=value):
                self.assertIsNone(RISK_PATTERNS["local-path"].search(value))

    def test_templates_are_deliberately_incomplete(self):
        paths = sorted((ROOT / "templates").glob("*.blank.json"))
        self.assertEqual({path.name.removesuffix(".blank.json") for path in paths}, {
            "project-intake", "style-guide", "batch-list", "cost-sheet", "delivery-list", "recovery", "term",
        })
        for path in paths:
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value.get("template_status", value.get("status")), "draft-template")

    def test_markdown_rule_ids_exist(self):
        ids = {rule["id"] for rule in registry()["requirements"]}
        pattern = rule_id_pattern(ids)
        found = set()
        for path in ROOT.rglob("*.md"):
            if path.relative_to(ROOT).parts[0] == ".git":
                continue
            with self.subTest(path=path.name):
                names = set(pattern.findall(path.read_text(encoding="utf-8")))
                self.assertLessEqual(names, ids)
                found |= names
        self.assertTrue(found)

    def test_walkthrough_ids_match_examples(self):
        text = (ROOT / "examples/walkthrough.md").read_text(encoding="utf-8")
        examples = "".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "examples").glob("*.json")))
        ids = {
            item for item in re.findall(r"(?<![A-Za-z0-9-])[A-Z]+-DEMO-\d{3}(?![A-Za-z0-9-])", text)
            if not item.startswith("UNIT-")
        }
        self.assertTrue(ids)
        for item in sorted(ids):
            with self.subTest(id=item):
                self.assertIn(item, examples)

    def test_walkthrough_light_tier_list_matches_registry(self):
        value = registry()
        section = (ROOT / "examples/walkthrough.md").read_text(encoding="utf-8").rsplit("\n## ", 1)[1]
        listed = set(rule_id_pattern({rule["id"] for rule in value["requirements"]}).findall(section))
        self.assertEqual(listed, set(rules_for_tier(value, "light")))


# Runs a tool with jsonschema and referencing blocked, as on a machine without the requirements installed.
BLOCKED_IMPORT = (
    "import runpy, sys; sys.modules['jsonschema'] = None; sys.modules['referencing'] = None; "
    "sys.argv = sys.argv[1:]; sys.path.insert(0, str(__import__('pathlib').Path(sys.argv[0]).parent)); "
    "runpy.run_path(sys.argv[0], run_name='__main__')"
)


class DependencyTests(unittest.TestCase):
    def test_missing_jsonschema_prints_install_hint(self):
        units = ROOT / "examples/units"
        hint = "missing_dependency=jsonschema; run: python -m pip install -r requirements.txt"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.json"
            for tool, args, code in [
                ("check_translation.py", ["--source", str(units / "source.json"), "--target",
                                          str(units / "draft-2.json"), "--report", str(output)], 2),
                ("validate_assets.py", [], 1),
                ("sync_registry.py", [str(ROOT / "registry/public.registry.json"), "--snapshot", str(output),
                                      "--project-id", "DEMO-NEW", "--phase", "intake", "--tier", "light"], 1),
                ("make_units.py", ["--input", str(units / "source.txt"), "--output", str(output),
                                   "--language", "en", "--version", "v1"], 1),
                ("export_bilingual.py", ["--source", str(units / "source.json"), "--target",
                                         str(units / "draft-2.json"), "--output", str(output),
                                         "--format", "markdown"], 1),
            ]:
                with self.subTest(tool=tool):
                    result = subprocess.run(
                        [sys.executable, "-B", "-c", BLOCKED_IMPORT, str(ROOT / "tools" / tool), *args],
                        capture_output=True, text=True,
                    )
                    self.assertEqual((result.returncode, result.stdout.strip()), (code, hint), result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
