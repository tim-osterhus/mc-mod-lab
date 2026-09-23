import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.package_plugin import ROOT, audit_text, build_package, package_files


class ReleaseTests(unittest.TestCase):
    def test_package_is_deterministic_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as temp:
            one, two = Path(temp) / "one.zip", Path(temp) / "two.zip"
            build_package(one)
            build_package(two)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            with zipfile.ZipFile(one) as archive:
                self.assertEqual(set(archive.namelist()), {"mc-mod-lab/" + name for name in package_files()})
                self.assertNotIn("mc-mod-lab/identity.json", archive.namelist())

    def test_package_cannot_include_traversal_or_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package-files.json").write_text(json.dumps(["../outside"]), encoding="utf-8")
            with self.assertRaises(ValueError):
                package_files(root)
        for value in ("ghp_" + "a" * 40, "Bearer " + "a" * 40, "C:/Users/example/private"):
            with self.assertRaises(ValueError):
                audit_text(value)

    def test_package_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "existing.zip"
            path.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                build_package(path)
            self.assertEqual(path.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
