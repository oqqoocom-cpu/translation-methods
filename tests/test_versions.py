import json
import tempfile
import unittest
from pathlib import Path

from tools.check_versions import check_versions


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp)
        (self.root / "tools").mkdir()
        self.write("release_manifest.json", json.dumps({"version": "1.2.3"}))
        self.write("README.md", "# Methods\n\n\u7248\u672c\uff1a1.2.3\uff0csynthetic.\n")
        self.write("CHANGELOG.md", "# Changes\n\n## 1.2.3\n\n## 1.2.2\n")
        self.write("tools/check_translation.py", 'VERSION = "1.2.3"\n')

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def test_consistent_versions(self):
        self.assertEqual(check_versions(self.root), {"version": "1.2.3", "declarations": 4})

    def test_mismatched_readme(self):
        self.write("README.md", "\u7248\u672c\uff1a1.2.2\n")
        with self.assertRaisesRegex(ValueError, "readme-version"):
            check_versions(self.root)

    def test_first_changelog_heading_is_current(self):
        self.write("CHANGELOG.md", "## 1.2.2\n\n## 1.2.3\n")
        with self.assertRaisesRegex(ValueError, "changelog-version"):
            check_versions(self.root)

    def test_duplicate_changelog_version_rejected(self):
        self.write("CHANGELOG.md", "## 1.2.3\n\n## 1.2.3\n")
        with self.assertRaisesRegex(ValueError, "changelog-version"):
            check_versions(self.root)

    def test_checker_literal_matches(self):
        self.write("tools/check_translation.py", 'VERSION = "1.2.2"\n')
        with self.assertRaisesRegex(ValueError, "checker-version"):
            check_versions(self.root)

    def test_checker_is_parsed_without_execution(self):
        self.write("tools/check_translation.py", 'raise RuntimeError("must not execute")\nVERSION = "1.2.3"\n')
        self.assertEqual(check_versions(self.root)["version"], "1.2.3")

    def test_computed_or_duplicate_checker_declaration_rejected(self):
        for text in ['VERSION = ".".join(["1", "2", "3"])\n',
                     'VERSION = "1.2.3"\nVERSION = "1.2.3"\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.write("tools/check_translation.py", text)
                check_versions(self.root)

    def test_invalid_or_missing_manifest_version(self):
        for value in [None, 1, "1.2", "1.2.3-extra"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.write("release_manifest.json", json.dumps({"version": value}))
                check_versions(self.root)


if __name__ == "__main__":
    unittest.main()
