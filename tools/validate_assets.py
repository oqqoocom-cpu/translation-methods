from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CHECKS = {"STRUCTURE", "PROTECTED", "HIGH-RISK", "TERMS", "FIDELITY", "LAYOUT"}
TIERS = ("light", "standard", "full")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON object key")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


@lru_cache(maxsize=None)
def validator(kind: str) -> Draft202012Validator:
    # Built once per kind and process; large glossaries validate many records.
    schemas = ROOT / "schemas"
    path = schemas / f"{kind}.schema.json"
    if path.parent != schemas or not path.is_file():
        raise ValueError("Unknown schema kind")
    resources = []
    for source in schemas.glob("*.schema.json"):
        schema = load_json(source)
        Draft202012Validator.check_schema(schema)
        resources.append((source.as_uri(), Resource.from_contents(schema)))
    schema = {"$ref": path.as_uri()}
    return Draft202012Validator(
        schema, registry=Registry().with_resources(resources), format_checker=FormatChecker(),
    )


def unique_ids(items: list[dict[str, Any]], field: str) -> None:
    ids = [item[field] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate {field}")


def check_evidence(value: Any, synthetic: bool) -> None:
    if isinstance(value, dict):
        if value.get("kind") == "synthetic" and not synthetic:
            raise ValueError("Synthetic evidence cannot verify a real record")
        for item in value.values():
            check_evidence(item, synthetic)
    elif isinstance(value, list):
        for item in value:
            check_evidence(item, synthetic)


def validate(kind: str, value: dict[str, Any]) -> None:
    validator(kind).validate(value)
    check_evidence(value, bool(value.get("synthetic", False)))
    if kind == "registry":
        unique_ids(value["requirements"], "id")
    elif kind == "application":
        unique_ids(value["rules"], "id")
    elif kind == "entity":
        unique_ids(value["variants"], "form")
        if any(item["entity_id"] == value["entity_id"] for item in value["relations"]):
            raise ValueError("Entity cannot refer to itself as a distinct related entity")
    elif kind == "quality-report":
        unique_ids(value["checks"], "check_id")
        for total, checked in [
            ("high_risk_total", "high_risk_reviewed"), ("protected_total", "protected_checked"),
        ]:
            if value[checked] > value[total]:
                raise ValueError("Coverage count exceeds target total")
            if value["status"] == "passed" and value[checked] != value[total]:
                raise ValueError("Passed report requires full declared coverage")
        if value["status"] == "passed" and not REQUIRED_CHECKS <= {
            item["check_id"] for item in value["checks"]
        }:
            raise ValueError("Passed report is missing a required check family")


def rules_for_tier(registry: dict[str, Any], tier: str) -> list[str]:
    """Return active rule IDs for a process tier; tiers are cumulative."""
    if tier not in TIERS:
        raise ValueError("Unknown process tier")
    limit = TIERS.index(tier)
    return [
        rule["id"] for rule in registry["requirements"]
        if rule["status"] == "active" and TIERS.index(rule["tier"]) <= limit
    ]


def validate_application(value: dict[str, Any], registry: dict[str, Any]) -> None:
    import hashlib
    validate("application", value)
    validate("registry", registry)
    encoded = json.dumps(registry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if value["registry_sha256"] != hashlib.sha256(encoded).hexdigest():
        raise ValueError("Application registry hash mismatch")
    if value["registry_version"] != registry["registry_version"]:
        raise ValueError("Application registry version mismatch")
    if {item["id"] for item in value["rules"]} != set(rules_for_tier(registry, value["process_tier"])):
        raise ValueError("Application must retain exactly the rules of its process tier")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local method records, not translation accuracy.")
    parser.add_argument("--kind")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    try:
        if bool(args.kind) != bool(args.file):
            raise ValueError("--kind and --file must be supplied together")
        if args.file:
            value = load_json(args.file)
            if args.kind == "application":
                source = args.registry or ROOT / "registry/public.registry.json"
                validate_application(value, load_json(source))
            else:
                if args.registry:
                    raise ValueError("--registry is only valid for application records")
                validate(args.kind, value)
            print("records=1 valid")
        else:
            registry = load_json(ROOT / "registry/public.registry.json")
            validate("registry", registry)
            count = 1
            for path in sorted((ROOT / "examples").glob("*.synthetic.json")):
                kind = path.name.removesuffix(".synthetic.json")
                value = load_json(path)
                if value.get("synthetic") is not True:
                    raise ValueError("Examples must be marked synthetic")
                if kind == "application":
                    validate_application(value, registry)
                else:
                    validate(kind, value)
                count += 1
            print(f"records={count} valid")
    except Exception as exc:
        # Validation exceptions can contain private input. Never print their full text.
        print(f"validation_failed={type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
