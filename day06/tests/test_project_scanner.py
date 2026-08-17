import json
import tempfile
import unittest
from pathlib import Path

from tools.project_scanner import UnityProjectScanner


class UnityProjectScannerTest(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_directory.name) / "UnityProject"
        (self.project_path / "Assets" / "Scripts" / "Core").mkdir(
            parents=True
        )
        (self.project_path / "Assets" / "Scenes").mkdir()
        (self.project_path / "Assets" / "Prefabs").mkdir()
        (self.project_path / "Assets" / "Resources").mkdir()
        (self.project_path / "Packages").mkdir()
        (self.project_path / "ProjectSettings").mkdir()
        (self.project_path / "Library").mkdir()

        (self.project_path / "Packages" / "manifest.json").write_text(
            json.dumps({"dependencies": {"com.unity.test-framework": "1.1.0"}}),
            encoding="utf-8"
        )
        (
            self.project_path
            / "ProjectSettings"
            / "ProjectVersion.txt"
        ).write_text(
            "m_EditorVersion: 2022.3.62f2c1\n",
            encoding="utf-8"
        )

        script_path = (
            self.project_path
            / "Assets"
            / "Scripts"
            / "Core"
            / "InventoryManager.cs"
        )
        script_path.write_text(
            """using System;
using UnityEngine;

namespace Game.Inventory;

public sealed class InventoryManager : MonoBehaviour, IInventory
{
}

public interface IInventory
{
}
""",
            encoding="utf-8"
        )
        script_path.with_suffix(".cs.meta").write_text(
            "fileFormatVersion: 2\nguid: script-guid-001\n",
            encoding="utf-8"
        )
        (self.project_path / "Assets" / "Scenes" / "Main.unity").write_text(
            """--- !u!1 &1
GameObject:
  m_Name: Main
--- !u!114 &2
MonoBehaviour:
  m_Script: {fileID: 11500000, guid: script-guid-001, type: 3}
""",
            encoding="utf-8"
        )
        (
            self.project_path
            / "Assets"
            / "Prefabs"
            / "Inventory.prefab"
        ).write_text(
            """--- !u!1 &1
GameObject:
  m_Name: Inventory
--- !u!114 &2
MonoBehaviour:
  m_Script: {fileID: 11500000, guid: script-guid-001, type: 3}
""",
            encoding="utf-8"
        )
        (
            self.project_path
            / "Assets"
            / "Resources"
            / "settings.json"
        ).write_text("{}", encoding="utf-8")
        (self.project_path / "Library" / "Ignored.cs").write_text(
            "public class Ignored {}",
            encoding="utf-8"
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_scans_unity_project_into_versioned_context(self):
        context = UnityProjectScanner(
            str(self.project_path)
        ).scan()

        self.assertEqual(context["schema_version"], 1)
        self.assertEqual(context["project"]["unity_version"], "2022.3.62f2c1")
        self.assertEqual(context["summary"]["scripts"], 1)
        self.assertEqual(context["summary"]["scenes"], 1)
        self.assertEqual(context["summary"]["prefabs"], 1)
        self.assertEqual(context["summary"]["assets"], 4)
        self.assertEqual(context["packages"][0]["name"], "com.unity.test-framework")

    def test_extracts_csharp_types_and_dependency_hints(self):
        context = UnityProjectScanner(
            str(self.project_path)
        ).scan()
        script = context["scripts"][0]

        self.assertEqual(script["namespace"], "Game.Inventory")
        self.assertEqual(script["guid"], "script-guid-001")
        self.assertEqual(
            [declaration["name"] for declaration in script["declarations"]],
            ["InventoryManager", "IInventory"]
        )
        self.assertEqual(
            script["declarations"][0]["base_types"],
            ["MonoBehaviour", "IInventory"]
        )
        self.assertEqual(
            script["dependency_hints"]["using_namespaces"],
            ["System", "UnityEngine"]
        )
        self.assertEqual(
            script["dependency_hints"]["base_types"],
            ["IInventory", "MonoBehaviour"]
        )

    def test_extracts_scene_and_prefab_script_references(self):
        context = UnityProjectScanner(
            str(self.project_path)
        ).scan()
        scene = context["scenes"][0]
        prefab = context["prefabs"][0]

        self.assertEqual(scene["game_objects"], 1)
        self.assertEqual(scene["mono_behaviours"], 1)
        self.assertEqual(scene["script_guids"], ["script-guid-001"])
        self.assertEqual(prefab["script_guids"], ["script-guid-001"])

    def test_builds_modules_and_ignores_non_asset_folders(self):
        context = UnityProjectScanner(
            str(self.project_path)
        ).scan()

        self.assertEqual(
            [module["name"] for module in context["modules"]],
            ["Prefabs", "Resources", "Scenes", "Scripts"]
        )
        all_paths = [asset["path"] for asset in context["assets"]]
        self.assertFalse(any("Library" in path for path in all_paths))
        self.assertFalse(any(path.endswith(".meta") for path in all_paths))

    def test_output_order_is_deterministic(self):
        scanner = UnityProjectScanner(str(self.project_path))

        first = scanner.scan()
        second = scanner.scan()

        first["project"].pop("scanned_at")
        second["project"].pop("scanned_at")
        self.assertEqual(first, second)

    def test_rejects_non_unity_project(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                UnityProjectScanner(directory).scan()


if __name__ == "__main__":
    unittest.main()
