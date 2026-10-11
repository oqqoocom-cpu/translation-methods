import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.check_release import MANIFEST, check_release, relative_name, unique_object


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.text = b"# Synthetic method fixture\n"
        (self.root / "README.md").write_bytes(self.text)
        self.manifest = {
            "scope": "generic-methods-only", "self_excluded": True,
            "files": [{"path": "README.md", "sha256": hashlib.sha256(self.text).hexdigest(),
                       "size_bytes": len(self.text)}],
        }
        self.save()

    def save(self):
        (self.root / MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_valid_release(self):
        result = check_release(self.root)
        self.assertEqual(result["files"], 2)
        self.assertFalse(result["publication_authorized"])
        self.assertFalse(result["complete_history_audited"])

    def test_changed_file(self):
        (self.root / "README.md").write_bytes(b"# Changed fixture\n")
        with self.assertRaises(ValueError):
            check_release(self.root)

    def test_unlisted_hidden_file(self):
        (self.root / ".hidden").write_bytes(b"no")
        with self.assertRaises(ValueError):
            check_release(self.root)

    def test_ignored_private_file_still_refused(self):
        (self.root / "private").mkdir()
        (self.root / "private/notes.md").write_text("not exported", encoding="utf-8")
        with self.assertRaises(ValueError):
            check_release(self.root)

    def test_missing_allowlisted_file(self):
        self.manifest["files"].append({**self.manifest["files"][0], "path": "missing.md"})
        self.save()
        with self.assertRaises(ValueError):
            check_release(self.root)

    def test_traversal_names_refused(self):
        for name in ["../other.md", "/other.md", "a/../b", "a//b", ".git/config", "a\\b",
                     "a:b", "a./b", "a/b ", "a/*"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                relative_name(name)

    def test_duplicate_casefold_names_refused(self):
        self.manifest["files"].append({**self.manifest["files"][0], "path": "readme.md"})
        self.save()
        with self.assertRaises(ValueError):
            check_release(self.root)

    def test_manifest_self_refused(self):
        self.manifest["files"].append({**self.manifest["files"][0], "path": MANIFEST})
        self.save()
        with self.assertRaises(ValueError):
            check_release(self.root)

    def test_duplicate_json_key_refused(self):
        with self.assertRaises(ValueError):
            json.loads('{"key":1,"key":2}', object_pairs_hook=unique_object)

    def test_bom_refused(self):
        (self.root / "README.md").write_bytes(b"\xef\xbb\xbf" + self.text)
        with self.assertRaises(ValueError):
            check_release(self.root)

    def test_secret_pattern_refused(self):
        (self.root / "README.md").write_text("ghp_" + "a" * 40, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "secret-pattern"):
            check_release(self.root)

    def test_local_path_refused(self):
        (self.root / "README.md").write_text(chr(67) + ":/private-file", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "local-path"):
            check_release(self.root)

    def test_unc_path_refused(self):
        value = chr(92) * 2 + "server" + chr(92) + "private"
        (self.root / "README.md").write_text(value, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "local-path"):
            check_release(self.root)

    def test_regex_escape_not_a_network_path(self):
        from tools.check_release import RISK_PATTERNS
        value = json.dumps({"pattern": r"\S"})
        self.assertIsNone(RISK_PATTERNS["local-path"].search(value))

    def test_external_local_link_refused(self):
        (self.root / "README.md").write_text("[outside](../outside.md)", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "broken-or-outside-link"):
            check_release(self.root)

    def test_git_metadata_not_treated_as_publishable_files(self):
        (self.root / ".git").mkdir()
        (self.root / ".git/config").write_text("local metadata", encoding="utf-8")
        self.assertEqual(check_release(self.root)["files"], 2)


if __name__ == "__main__":
    unittest.main()
