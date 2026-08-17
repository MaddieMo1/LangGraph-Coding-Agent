import json
import os


class DependencyGraphStore:
    """Persist the latest versioned project dependency graph."""

    SCHEMA_VERSION = 1

    def __init__(self, path):
        self.path = os.path.abspath(path)

    def save(self, graph):
        self._validate(graph)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary_path = self.path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(graph, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, self.path)
        return self.path

    def load(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                graph = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to load dependency graph: {error}") from error
        self._validate(graph)
        return graph

    def _validate(self, graph):
        if not isinstance(graph, dict):
            raise ValueError("dependency graph must be a JSON object")
        if graph.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported dependency graph schema_version: {graph.get('schema_version')}"
            )


def build_prompt_graph(graph, max_nodes=100, max_edges=200):
    """Return a bounded dependency view suitable for downstream prompts."""

    if not graph:
        return {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    return {
        "project": graph.get("project", {}),
        "summary": graph.get("summary", {}),
        "nodes": nodes[:max_nodes],
        "edges": edges[:max_edges],
        "diagnostics": graph.get("diagnostics", {}),
        "truncated": len(nodes) > max_nodes or len(edges) > max_edges,
    }
