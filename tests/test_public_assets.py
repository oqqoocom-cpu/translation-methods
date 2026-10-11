from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sync_registry import make_snapshot, registry_hash, render_markdown, write_new_outputs
from tools.validate_assets import load_json, validate, validate_application, validator
from tools.check_release import check_release


def fixture(kind: str) -> dict:
    return json.loads((ROOT / "examples" / f"{kind}.synthetic.json").read_text(encoding="utf-8"))


def registry() -> dict:
    return json.loads((ROOT / "registry/public.registry.json").read_text(encoding="utf-8"))


class SchemaTests(unittest.TestCase):
    def reject(self, kind: str, value: dict) -> None:
        with self.assertRaises((ValidationError, ValueError)):
            validate(kind, value)

    def test_all_schemas_valid(self):
        for path in (ROOT / "schemas").glob("*.schema.json"):
            validator(path.name.removesuffix(".schema.json"))

    def test_positive_examples(self):
        for kind in ["term", "entity", "decision", "issue", "quality-report"]:
            with self.subTest(kind=kind):
                value = fixture(kind)
                self.assertTrue(value["synthetic"])
                validate(kind, value)

    def test_registry_valid(self):
        validate("registry", registry())
        self.assertEqual(len(registry()["requirements"]), 27)

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

    def test_application_valid(self):
        validate_application(fixture("application"), registry())

    def test_locked_term_requires_evidence_and_decision(self):
        for field in ["evidence", "scope", "decision_reason", "decision_id", "verified_at"]:
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
        for kind in ["term", "entity", "decision", "quality-report"]:
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
        value = fixture("application")
        value["rules"][0]["applicability"] = "exception"
        self.reject("application", value)

    def test_application_pending_cannot_pass(self):
        value = fixture("application")
        value["rules"][0]["acceptance"] = "passed"
        self.reject("application", value)

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


class ToolTests(unittest.TestCase):
    def test_public_registry_markdown_is_current(self):
        self.assertEqual(
            (ROOT / "registry/public.registry.md").read_text(encoding="utf-8"),
            render_markdown(registry()),
        )

    def test_snapshot_is_pending(self):
        value = make_snapshot(registry(), "DEMO-NEW", "intake")
        self.assertTrue(all(r["acceptance"] == r["applicability"] == "pending" for r in value["rules"]))

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

    def test_templates_are_deliberately_incomplete(self):
        for path in (ROOT / "templates").glob("*.blank.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value.get("template_status", value.get("status")), "draft-template")


if __name__ == "__main__":
    unittest.main()
