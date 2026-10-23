"""Sprawdzenie zawartości archiwum dla użytkownika i zgodności wersji."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_integration", ROOT / "scripts/package_integration.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleaseTests(unittest.TestCase):
    def test_only_tracked_integration_files_are_distributed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            integration = root / builder.INTEGRATION
            for name in ("__init__.py", "LICENSE", "brand/icon.png", "translations/pl.json"):
                target = integration / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture")
            (integration / "manifest.json").write_text('{"version":"0.2.1"}')
            subprocess.run(["git", "-C", str(root), "add", "custom_components"], check=True)
            (integration / "private.env").write_text("not for distribution")
            (root / "configuration.json").write_text("private configuration")
            (root / "dlms_reader").mkdir()
            (root / "dlms_reader/config.yaml").write_text("add-on configuration")
            output = root / "package.zip"
            self.assertEqual(builder.package(output, "v0.2.1", root), "0.2.1")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {
                    "dlms_reader/__init__.py", "dlms_reader/LICENSE", "dlms_reader/brand/icon.png",
                    "dlms_reader/translations/pl.json", "dlms_reader/manifest.json"})
                self.assertIsNone(archive.testzip())

    def test_wrong_release_version_does_not_create_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "package.zip"
            with self.assertRaisesRegex(ValueError, "manifest.json"):
                builder.package(output, "999.0.0")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
