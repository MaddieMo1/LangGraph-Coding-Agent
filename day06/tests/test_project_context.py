import json
import os
import tempfile
import unittest

from memory.project_context import ProjectContextStore, build_prompt_context


class ProjectContextStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "memory", "project_context.json")
        self.store = ProjectContextStore(self.path)
        self.context = {
            "schema_version": 1,
            "project": {"name": "Demo"},
            "summary": {"script_count": 1},
            "modules": [{"name": "Scripts"}],
            "scripts": [
                {
                    "path": "Assets/Scripts/Demo.cs",
                    "namespace": "Game.Demo",
                    "declarations": [{"kind": "class", "name": "Demo"}],
                    "dependency_hints": {"using_namespaces": ["UnityEngine"]},
                }
            ],
            "scenes": [],
            "prefabs": [],
            "packages": [],
            "scan_errors": [],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_file_returns_empty_context(self):
        self.assertEqual({}, self.store.load())

    def test_saves_and_loads_versioned_context(self):
        saved_path = self.store.save(self.context)

        self.assertEqual(os.path.abspath(self.path), saved_path)
        self.assertEqual(self.context, self.store.load())
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_rejects_unsupported_schema(self):
        invalid = dict(self.context, schema_version=2)

        with self.assertRaisesRegex(ValueError, "schema_version"):
            self.store.save(invalid)

    def test_rejects_invalid_json(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("not-json")

        with self.assertRaisesRegex(ValueError, "project context"):
            self.store.load()

    def test_builds_bounded_prompt_view(self):
        context = dict(self.context, assets=[{"path": "large-binary.png"}])

        prompt_context = build_prompt_context(context)

        self.assertEqual("Demo", prompt_context["project"]["name"])
        self.assertEqual("Demo", prompt_context["scripts"][0]["declarations"][0]["name"])
        self.assertNotIn("assets", prompt_context)


if __name__ == "__main__":
    unittest.main()
