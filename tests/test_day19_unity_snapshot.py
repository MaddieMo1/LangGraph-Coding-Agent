import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.unity_snapshot import (
    UnitySnapshotBuilder,
    UnitySnapshotError,
    safe_extract_snapshot,
)


class UnitySnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.project = self.root / "UnityProject"
        self.production = self.root / "generated"
        self.editmode = self.root / "generated-tests" / "editmode"
        self.playmode = self.root / "generated-tests" / "playmode"

        for folder in (
            self.project / "Assets" / "Scripts",
            self.project / "Assets" / "Generated",
            self.project / "Assets" / "Tests" / "EditMode",
            self.project / "Assets" / "Tests" / "PlayMode",
            self.project / "Packages",
            self.project / "ProjectSettings",
            self.project / "Library",
            self.production,
            self.editmode,
            self.playmode,
        ):
            folder.mkdir(parents=True, exist_ok=True)

        self._write(self.project / "Assets" / "Scripts" / "Existing.cs", "existing")
        self._write(self.project / "Assets" / "Generated" / "Old.cs", "old")
        self._write(
            self.project / "Assets" / "Tests" / "EditMode" / "OldTests.cs", "old"
        )
        self._write(
            self.project / "Assets" / "Tests" / "PlayMode" / "OldPlayTests.cs", "old"
        )
        self._write(self.project / "Library" / "cache.bin", "ignored")
        self._write(
            self.project / "Packages" / "manifest.json",
            '{"dependencies":{"com.unity.test-framework":"1.1.33"}}',
        )
        self._write(
            self.project / "ProjectSettings" / "ProjectVersion.txt",
            "m_EditorVersion: 2022.3.62f2c1\n",
        )
        self._write(self.production / "Probe.cs", "public class Probe {}")
        self._write(self.editmode / "ProbeTests.cs", "public class ProbeTests {}")
        self._write(
            self.playmode / "ProbePlayModeTests.cs",
            "public class ProbePlayModeTests {}",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def _write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _builder(self, **overrides):
        values = {
            "project_path": self.project,
            "production_source_path": self.production,
            "editmode_test_source_path": self.editmode,
            "playmode_test_source_path": self.playmode,
        }
        values.update(overrides)
        return UnitySnapshotBuilder(**values)

    def test_builds_deterministic_allowlisted_snapshot_with_generated_overlays(self):
        first_path = self.root / "first.unityjob"
        second_path = self.root / "second.unityjob"

        first = self._builder().build(first_path)
        second = self._builder().build(second_path)

        self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
        self.assertEqual("2022.3.62f2c1", first["unity_version"])
        self.assertTrue(first["source_unchanged"])
        self.assertEqual(
            first["source_fingerprint_before"], first["source_fingerprint_after"]
        )

        paths = [item["path"] for item in first["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertIn("Assets/Scripts/Existing.cs", paths)
        self.assertIn("Assets/Generated/Probe.cs", paths)
        self.assertIn("Assets/Tests/EditMode/ProbeTests.cs", paths)
        self.assertIn("Assets/Tests/PlayMode/ProbePlayModeTests.cs", paths)
        self.assertNotIn("Assets/Generated/Old.cs", paths)
        self.assertNotIn("Assets/Tests/EditMode/OldTests.cs", paths)
        self.assertNotIn("Assets/Tests/PlayMode/OldPlayTests.cs", paths)
        self.assertNotIn("Library/cache.bin", paths)
        self.assertTrue(
            all(path.split("/", 1)[0] in {"Assets", "Packages", "ProjectSettings"} for path in paths)
        )

    def test_extracts_and_verifies_every_manifest_file(self):
        archive = self.root / "snapshot.unityjob"
        built = self._builder().build(archive)
        destination = self.root / "sandbox"

        manifest = safe_extract_snapshot(archive, destination)

        self.assertEqual(built["snapshot_sha256"], manifest["snapshot_sha256"])
        self.assertEqual(
            "public class Probe {}",
            (destination / "Assets" / "Generated" / "Probe.cs").read_text(
                encoding="utf-8"
            ),
        )

    def test_rejects_traversal_archive_without_writing_outside_destination(self):
        archive = self.root / "malicious.unityjob"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../outside.txt", "secret")
            bundle.writestr("unity-snapshot.json", "{}")

        with self.assertRaises(UnitySnapshotError):
            safe_extract_snapshot(archive, self.root / "sandbox")

        self.assertFalse((self.root / "outside.txt").exists())

    def test_rejects_tampered_archive_content(self):
        archive = self.root / "snapshot.unityjob"
        self._builder().build(archive)
        entries = {}
        with zipfile.ZipFile(archive, "r") as source:
            for name in source.namelist():
                entries[name] = source.read(name)
        original = entries["Assets/Generated/Probe.cs"]
        entries["Assets/Generated/Probe.cs"] = b"x" * len(original)
        with zipfile.ZipFile(archive, "w") as target:
            for name in sorted(entries):
                target.writestr(name, entries[name])

        with self.assertRaisesRegex(UnitySnapshotError, "hash mismatch"):
            safe_extract_snapshot(archive, self.root / "sandbox")

    def test_rejects_oversized_files_before_creating_archive(self):
        archive = self.root / "snapshot.unityjob"
        builder = self._builder(max_file_size=4)

        with self.assertRaisesRegex(UnitySnapshotError, "file exceeds"):
            builder.build(archive)

        self.assertFalse(archive.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are not supported")
    def test_rejects_source_symlinks(self):
        link = self.project / "Assets" / "linked.cs"
        try:
            os.symlink(self.production / "Probe.cs", link)
        except OSError as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        with self.assertRaisesRegex(UnitySnapshotError, "symbolic link"):
            self._builder().build(self.root / "snapshot.unityjob")

    def test_detects_source_change_during_build_and_keeps_existing_target(self):
        archive = self.root / "snapshot.unityjob"
        archive.write_bytes(b"existing")
        project_file = self.project / "Assets" / "Scripts" / "Existing.cs"

        class MutatingBuilder(UnitySnapshotBuilder):
            def _write_archive(inner_self, path, manifest, sources):
                super()._write_archive(path, manifest, sources)
                project_file.write_text("changed during build", encoding="utf-8")

        builder = MutatingBuilder(
            self.project,
            self.production,
            self.editmode,
            self.playmode,
        )

        with self.assertRaisesRegex(UnitySnapshotError, "changed during snapshot"):
            builder.build(archive)

        self.assertEqual(b"existing", archive.read_bytes())

    def test_manifest_inside_archive_matches_returned_manifest(self):
        archive = self.root / "snapshot.unityjob"
        result = self._builder().build(archive)

        with zipfile.ZipFile(archive, "r") as bundle:
            stored = json.loads(bundle.read("unity-snapshot.json"))

        self.assertEqual(result["snapshot_sha256"], stored["snapshot_sha256"])
        self.assertEqual(result["files"], stored["files"])


if __name__ == "__main__":
    unittest.main()
