import os
import tempfile
import unittest

from tools.dependency_graph import DependencyGraphBuilder, DependencyGraphQuery


class DependencyGraphBuilderTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name
        os.makedirs(os.path.join(self.root, "Assets", "Scripts"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "Assets", "Scenes"), exist_ok=True)

        self._write(
            "Assets/Scripts/ProjectBase.cs",
            "namespace Game.Core { public class ProjectBase {} }",
        )
        self._write(
            "Assets/Scripts/BaseItem.cs",
            "namespace Game.Data { public class BaseItem {} }",
        )
        self._write(
            "Assets/Scripts/InventoryManager.cs",
            """
using Game.Core;
using Game.Data;
namespace Game.Inventory
{
    public class InventoryManager : ProjectBase
    {
        private BaseItem currentItem;
    }
}
""",
        )
        self._write(
            "Assets/Scripts/InventoryView.cs",
            """
namespace Game.Inventory
{
    public class InventoryView
    {
        private InventoryManager manager;
    }
}
""",
        )
        self._write(
            "Assets/Scripts/AConfig.cs",
            "namespace A { public class Config {} }",
        )
        self._write(
            "Assets/Scripts/BConfig.cs",
            "namespace B { public class Config {} }",
        )
        self._write(
            "Assets/Scripts/Consumer.cs",
            "public class Consumer { private Config config; }",
        )
        self._write(
            "Assets/Scenes/Main.unity",
            "--- !u!114 &1\nMonoBehaviour:\n  m_Script: {fileID: 11500000, guid: manager-guid, type: 3}\n",
        )

        self.context = {
            "schema_version": 1,
            "project": {"name": "GraphDemo", "root": self.root.replace("\\", "/")},
            "scripts": [
                self._script("ProjectBase.cs", "base-guid", "Game.Core", "ProjectBase"),
                self._script("BaseItem.cs", "item-guid", "Game.Data", "BaseItem"),
                self._script(
                    "InventoryManager.cs",
                    "manager-guid",
                    "Game.Inventory",
                    "InventoryManager",
                    ["ProjectBase"],
                    ["Game.Core", "Game.Data"],
                ),
                self._script("InventoryView.cs", "view-guid", "Game.Inventory", "InventoryView"),
                self._script("AConfig.cs", "a-guid", "A", "Config"),
                self._script("BConfig.cs", "b-guid", "B", "Config"),
                self._script("Consumer.cs", "consumer-guid", "", "Consumer"),
            ],
            "scenes": [
                {
                    "path": "Assets/Scenes/Main.unity",
                    "module": "Scenes",
                    "guid": "scene-guid",
                    "script_guids": ["manager-guid"],
                }
            ],
            "prefabs": [],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, relative_path, content):
        path = os.path.join(self.root, *relative_path.split("/"))
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)

    @staticmethod
    def _script(file_name, guid, namespace, type_name, bases=None, usings=None):
        full_name = f"{namespace}.{type_name}" if namespace else type_name
        return {
            "path": f"Assets/Scripts/{file_name}",
            "module": "Scripts",
            "guid": guid,
            "namespace": namespace,
            "declarations": [
                {
                    "kind": "class",
                    "name": type_name,
                    "full_name": full_name,
                    "base_types": bases or [],
                }
            ],
            "dependency_hints": {"using_namespaces": usings or [], "base_types": bases or []},
        }

    def test_builds_type_and_asset_nodes(self):
        graph = DependencyGraphBuilder().build(self.context)

        self.assertEqual(1, graph["schema_version"])
        self.assertIn("type:Game.Inventory.InventoryManager", self._node_ids(graph))
        self.assertIn("asset:Assets/Scenes/Main.unity", self._node_ids(graph))
        self.assertEqual(8, graph["summary"]["nodes"])

    def test_resolves_inheritance_and_type_references(self):
        graph = DependencyGraphBuilder().build(self.context)
        edges = self._edges(graph)

        self.assertIn(
            ("type:Game.Inventory.InventoryManager", "type:Game.Core.ProjectBase", "inherits"),
            edges,
        )
        self.assertIn(
            ("type:Game.Inventory.InventoryManager", "type:Game.Data.BaseItem", "type_reference"),
            edges,
        )
        self.assertIn(
            ("type:Game.Inventory.InventoryView", "type:Game.Inventory.InventoryManager", "type_reference"),
            edges,
        )

    def test_records_scene_script_guid_reference(self):
        graph = DependencyGraphBuilder().build(self.context)

        self.assertIn(
            (
                "asset:Assets/Scenes/Main.unity",
                "type:Game.Inventory.InventoryManager",
                "script_reference",
            ),
            self._edges(graph),
        )

    def test_reports_ambiguous_short_type_names(self):
        graph = DependencyGraphBuilder().build(self.context)

        ambiguous = graph["diagnostics"]["ambiguous_references"]
        self.assertTrue(any(item["reference"] == "Config" for item in ambiguous))
        self.assertFalse(any(edge[0] == "type:Consumer" for edge in self._edges(graph)))

    def test_queries_direct_reverse_and_transitive_dependencies(self):
        graph = DependencyGraphBuilder().build(self.context)
        query = DependencyGraphQuery(graph)

        self.assertEqual(
            ["type:Game.Inventory.InventoryManager"],
            query.dependencies("type:Game.Inventory.InventoryView"),
        )
        self.assertIn(
            "type:Game.Data.BaseItem",
            query.dependencies("type:Game.Inventory.InventoryView", transitive=True),
        )
        self.assertIn(
            "type:Game.Inventory.InventoryView",
            query.dependents("type:Game.Inventory.InventoryManager"),
        )

    def test_output_is_deterministic(self):
        builder = DependencyGraphBuilder()
        self.assertEqual(builder.build(self.context), builder.build(self.context))

    @staticmethod
    def _node_ids(graph):
        return {node["id"] for node in graph["nodes"]}

    @staticmethod
    def _edges(graph):
        return {
            (edge["source"], edge["target"], edge["kind"])
            for edge in graph["edges"]
        }


if __name__ == "__main__":
    unittest.main()
