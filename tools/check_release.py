from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

MANIFEST = "release_manifest.json"
ROOT = Path(__file__).resolve().parents[1]
TEXT_TYPES = {".py", ".json", ".md", ".txt", ".yml"}
SPECIAL = {".gitignore", ".gitattributes"}
RISK_PATTERNS = {
    # ASCII lookarounds, not \b: in Python, CJK characters count as word characters,
    # so \b would miss a token written directly after Chinese text.
    "local-path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|/(?:Users|home)/|\\\\[A-Za-z0-9_-]+\\"),
    "private-unit-id": re.compile(r"(?<![A-Za-z0-9])(?:BOOK-\d{4}|PDF\d{3}-S\d{3})(?![A-Za-z0-9])", re.I),
    "secret-pattern": re.compile(r"(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{16,})"),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
    )


def relative_name(name):
    require(isinstance(name, str) and bool(name), "invalid-relative-path")
    require("\\" not in name and ":" not in name and not name.startswith("/"), "invalid-relative-path")
    require(all(p not in ("", ".", "..") for p in name.split("/")), "invalid-relative-path")
    require(not PurePosixPath(name).is_absolute() and name.split("/")[0] != ".git", "invalid-relative-path")
    require(all(not p.endswith((".", " ")) and not any(ord(c) < 32 or c in '<>"|?*' for c in p)
                for p in name.split("/")), "invalid-relative-path")
    return name


def check_release(root=ROOT, staged=False):
    root = Path(root).absolute()
    require(root.is_dir(), "root-missing")
    require(not any(linked(p) for p in (root, *root.parents)), "linked-root")
    root = root.resolve(strict=True)
    require((root / MANIFEST).is_file() and not linked(root / MANIFEST), "manifest-missing-or-linked")
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    require(manifest.get("scope") == "generic-methods-only" and manifest.get("self_excluded") is True, "manifest-scope")
    rows = manifest["files"]
    require(bool(rows), "empty-allowlist")
    allowed, seen = {}, set()
    for row in rows:
        name = relative_name(row["path"])
        require(name != MANIFEST and name.casefold() not in seen, "duplicate-or-self-member")
        require(re.fullmatch("[0-9a-f]{64}", row["sha256"]) is not None, "invalid-sha256")
        require(type(row["size_bytes"]) is int and 0 <= row["size_bytes"] <= 1024 * 1024, "invalid-size")
        seen.add(name.casefold())
        allowed[name] = row
    actual = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        if Path(directory) == root and ".git" in dirs:
            require(not linked(root / ".git"), "linked-git")
            dirs.remove(".git")
        for name in [*dirs, *names]:
            require(not linked(Path(directory) / name), "linked-entry")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            require(path.suffix.lower() in TEXT_TYPES or path.name in SPECIAL, "unapproved-type")
            raw = path.read_bytes()
            require(len(raw) <= 1024 * 1024 and not raw.startswith(b"\xef\xbb\xbf"), "oversized-or-bom")
            text = raw.decode("utf-8")
            require("\x00" not in text, "binary-content")
            for kind, pattern in RISK_PATTERNS.items():
                require(pattern.search(text) is None, kind)
            actual[relative] = raw
            if path.suffix == ".md":
                for link in re.finditer(r"\[[^\]\n]*\]\((<?[^)\n]+>?)\)", text):
                    target = link.group(1).strip("<>")
                    parsed = urlsplit(target)
                    if parsed.scheme in {"http", "https", "mailto"} or not parsed.path:
                        continue
                    require(not parsed.scheme, "unapproved-link-scheme")
                    dest = (path.parent / unquote(parsed.path)).resolve()
                    require(dest.is_relative_to(root) and dest.is_file(), "broken-or-outside-link")
    require(set(actual) == set(allowed) | {MANIFEST}, "files-not-exact-allowlist")
    for name, row in allowed.items():
        require(len(actual[name]) == row["size_bytes"] and hashlib.sha256(actual[name]).hexdigest() == row["sha256"],
                "file-hash-mismatch")
    if staged:
        git_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root).decode("utf-8").strip()
        require(Path(git_root).resolve() == root, "git-root-not-independent")
        raw_index = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root).decode("utf-8")
        index = {}
        for entry in raw_index.rstrip("\x00").split("\x00") if raw_index else []:
            meta, name = entry.split("\t", 1)
            mode, _, stage = meta.split()
            require(mode == "100644" and stage == "0", "nonregular-or-conflicted-index")
            require(name not in index, "duplicate-index-member")
            index[name] = subprocess.check_output(["git", "show", ":" + name], cwd=root)
        require(index == actual, "staged-snapshot-not-exact-release")
    return {"files": len(actual), "byte_hashes": True, "links": True, "staged": staged,
            "complete_history_audited": False, "publication_authorized": False}


def main():
    parser = argparse.ArgumentParser(description="Check public file allowlist, not rights or translation quality.")
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    try:
        result = check_release(staged=args.staged)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        # Do not echo input, paths, secrets, or subprocess output.
        print("release_check_failed=" + type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
