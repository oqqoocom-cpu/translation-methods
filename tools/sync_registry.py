from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

try:
    from .validate_assets import load_json, validate, validate_application
except ImportError:
    from validate_assets import load_json, validate, validate_application


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def registry_hash(registry: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(registry)).hexdigest()


def cell(value: Any) -> str:
    # Escape every cell, not only the requirement text.
    return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def render_markdown(registry: dict[str, Any]) -> str:
    validate("registry", registry)
    lines = [
        "# Translation Method Registry", "",
        f"Version: {cell(registry['registry_version'])}",
        f"SHA-256 (canonical-json-v1): `{registry_hash(registry)}`", "",
        "| ID | Category | Title | Scope | Strength | Condition | Requirement | Verification |",
        "|---|---|---|---|---|---|---|---|",
    ]
    fields = ["id", "category", "title", "scope", "strength", "condition", "requirement", "verification"]
    for rule in registry["requirements"]:
        lines.append("| " + " | ".join(cell(rule.get(field, "")) for field in fields) + " |")
    return "\n".join(lines) + "\n"


def make_snapshot(registry: dict[str, Any], project_id: str, phase: str) -> dict[str, Any]:
    value = {
        "project_id": project_id, "phase": phase,
        "registry_version": registry["registry_version"],
        "registry_sha256": registry_hash(registry), "hash_algorithm": "canonical-json-v1",
        "rules": [
            {"id": rule["id"], "applicability": "pending", "acceptance": "pending"}
            for rule in registry["requirements"]
        ],
    }
    validate_application(value, registry)
    return value


def write_new_outputs(source: Path, outputs: dict[Path, str]) -> None:
    source = source.resolve(strict=True)
    resolved = []
    for path, text in outputs.items():
        target = path.resolve()
        if path.is_symlink() or target == source or target.exists():
            raise ValueError("Output must be a new file, separate from input")
        if any(parent.is_symlink() for parent in path.absolute().parents):
            raise ValueError("Output parent cannot be a symlink")
        if target in {p for p, _ in resolved}:
            raise ValueError("Output paths must be distinct")
        resolved.append((target, text))
    # Validate all targets before writing; exclusive open also protects against races.
    for target, text in resolved:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render rules and create a pending application snapshot.")
    parser.add_argument("registry", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--phase", choices=["intake", "pilot-release", "full-translation", "layout", "delivery"])
    args = parser.parse_args()
    try:
        registry = load_json(args.registry)
        validate("registry", registry)
        outputs = {}
        if args.markdown:
            outputs[args.markdown] = render_markdown(registry)
        if args.snapshot:
            if not args.project_id or not args.phase:
                raise ValueError("Snapshot requires project ID and phase")
            if args.snapshot in outputs:
                raise ValueError("Output paths must be distinct")
            outputs[args.snapshot] = json.dumps(
                make_snapshot(registry, args.project_id, args.phase), ensure_ascii=False, indent=2,
            ) + "\n"
        write_new_outputs(args.registry, outputs)
        print(f"registry_version={registry['registry_version']}")
        print(f"registry_sha256={registry_hash(registry)}")
        print(f"outputs={len(outputs)}")
    except Exception as exc:
        print(f"sync_failed={type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
