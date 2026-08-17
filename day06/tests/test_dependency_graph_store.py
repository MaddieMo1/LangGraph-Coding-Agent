import json
import os
import tempfile
import unittest

from memory.dependency_graph import DependencyGraphStore, build_prompt_graph


class DependencyGraphStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "memory", "dependency_graph.json")
        self.store = DependencyGraphStore(self.path)
        self.graph = {
            "schema_version": 1,
            "project": {"name": "Demo"},
            "summary": {"nodes": 2, "edges": 1},
            "nodes": [
                {"id": "type:A", "kind": "type", "full_name": "A", "paths": ["A.cs"]},
                {"id": "type:B", "kind": "type", "full_name": "B", "paths": ["B.cs"]},
            ],
            "edges": [
                {"source": "type:A", "target": "type:B", "kind": "type_reference"}
            ],
            "diagnostics": {"duplicate_types": [], "ambiguous_references": [], "source_errors": []},
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_file_returns_empty_graph(self):
        self.assertEqual({}, self.store.load())

    def test_saves_and_loads_graph_atomically(self):
        self.assertEqual(os.path.abspath(self.path), self.store.save(self.graph))
        self.assertEqual(self.graph, self.store.load())
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_rejects_unsupported_schema(self):
        with self.assertRaisesRegex(ValueError, "schema_version"):
            self.store.save(dict(self.graph, schema_version=2))

    def test_rejects_invalid_json(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("invalid")
        with self.assertRaisesRegex(ValueError, "dependency graph"):
            self.store.load()

    def test_prompt_view_is_bounded(self):
        graph = dict(
            self.graph,
            nodes=self.graph["nodes"] * 3,
            edges=self.graph["edges"] * 3,
        )
        view = build_prompt_graph(graph, max_nodes=2, max_edges=1)

        self.assertEqual(2, len(view["nodes"]))
        self.assertEqual(1, len(view["edges"]))
        self.assertTrue(view["truncated"])


if __name__ == "__main__":
    unittest.main()
