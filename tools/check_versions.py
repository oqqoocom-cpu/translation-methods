"""Check that the manifest, README, changelog and checker declare one version."""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = r"[0-9]+\.[0-9]+\.[0-9]+"


def check_versions(root=ROOT):
    root = Path(root)
    manifest = json.loads((root / "release_manifest.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(VERSION_RE, version):
        raise ValueError("invalid-manifest-version")
    readme = (root / "README.md").read_text(encoding="utf-8")
    declarations = re.findall(r"(?m)^\u7248\u672c\uff1a(" + VERSION_RE + r")(?=[\s\uff0c,]|$)", readme)
    if declarations != [version]:
        raise ValueError("readme-version-mismatch")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"(?m)^## (" + VERSION_RE + r")\s*$", changelog)
    if not headings or headings[0] != version or len(headings) != len(set(headings)):
        raise ValueError("changelog-version-mismatch")
    tree = ast.parse((root / "tools/check_translation.py").read_text(encoding="utf-8"))
    checker = []
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == "VERSION" for target in targets):
            if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                raise ValueError("checker-version-not-literal")
            checker.append(node.value.value)
    if checker != [version]:
        raise ValueError("checker-version-mismatch")
    return {"version": version, "declarations": 4}


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        result = check_versions()
    except (OSError, ValueError, SyntaxError) as exc:
        # Never echo text or paths from an input file.
        print("version_check_failed=" + type(exc).__name__)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
