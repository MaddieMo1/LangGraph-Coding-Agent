import os
import re


class DependencyGraphBuilder:
    """Build a deterministic graph of project-local Unity type dependencies."""

    SCHEMA_VERSION = 1

    def build(self, project_context):
        if project_context.get("schema_version") != 1:
            raise ValueError("dependency graph requires project context schema_version 1")

        project = project_context.get("project", {})
        project_root = project.get("root", "")
        scripts = project_context.get("scripts", [])
        declarations_by_full_name = {}
        short_name_index = {}
        guid_targets = {}

        for script in scripts:
            declarations = script.get("declarations", [])
            for declaration in declarations:
                full_name = declaration.get("full_name") or declaration.get("name", "")
                if not full_name:
                    continue
                record = declarations_by_full_name.setdefault(
                    full_name,
                    {
                        "id": "type:" + full_name,
                        "kind": "type",
                        "name": declaration.get("name", full_name.rsplit(".", 1)[-1]),
                        "full_name": full_name,
                        "type_kind": declaration.get("kind", ""),
                        "namespace": script.get("namespace", ""),
                        "module": script.get("module", ""),
                        "paths": [],
                        "guids": [],
                    },
                )
                if script.get("path") not in record["paths"]:
                    record["paths"].append(script.get("path"))
                if script.get("guid") and script.get("guid") not in record["guids"]:
                    record["guids"].append(script.get("guid"))

        for full_name, record in declarations_by_full_name.items():
            record["paths"].sort()
            record["guids"].sort()
            short_name_index.setdefault(record["name"], []).append(full_name)

        for candidates in short_name_index.values():
            candidates.sort()

        for script in scripts:
            declarations = script.get("declarations", [])
            mono_behaviours = [
                declaration
                for declaration in declarations
                if "MonoBehaviour" in declaration.get("base_types", [])
            ]
            guid_declarations = mono_behaviours or declarations
            if script.get("guid"):
                guid_targets[script["guid"]] = sorted(
                    {
                        "type:" + (declaration.get("full_name") or declaration.get("name", ""))
                        for declaration in guid_declarations
                        if declaration.get("full_name") or declaration.get("name")
                    }
                )

        edges = {}
        ambiguous_references = []
        source_errors = []

        for script in sorted(scripts, key=lambda item: item.get("path", "")):
            source = self._read_source(project_root, script.get("path", ""), source_errors)
            sanitized_source = self._sanitize(source)
            namespace = script.get("namespace", "")
            using_namespaces = script.get("dependency_hints", {}).get(
                "using_namespaces", []
            )

            for declaration in script.get("declarations", []):
                full_name = declaration.get("full_name") or declaration.get("name", "")
                if full_name not in declarations_by_full_name:
                    continue
                source_id = "type:" + full_name

                for base_type in declaration.get("base_types", []):
                    target = self._resolve_type(
                        base_type,
                        namespace,
                        using_namespaces,
                        declarations_by_full_name,
                        short_name_index,
                        source_id,
                        script.get("path", ""),
                        ambiguous_references,
                    )
                    if target and target != source_id:
                        self._add_edge(edges, source_id, target, "inherits", script.get("path", ""))

                body = self._declaration_segment(
                    sanitized_source,
                    declaration.get("kind", ""),
                    declaration.get("name", ""),
                )
                for reference in sorted(set(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", body))):
                    if reference not in short_name_index:
                        continue
                    target = self._resolve_type(
                        reference,
                        namespace,
                        using_namespaces,
                        declarations_by_full_name,
                        short_name_index,
                        source_id,
                        script.get("path", ""),
                        ambiguous_references,
                    )
                    if target and target != source_id:
                        self._add_edge(
                            edges,
                            source_id,
                            target,
                            "type_reference",
                            script.get("path", ""),
                        )

        asset_nodes = []
        for asset in sorted(
            project_context.get("scenes", []) + project_context.get("prefabs", []),
            key=lambda item: item.get("path", ""),
        ):
            path = asset.get("path", "")
            source_id = "asset:" + path
            asset_nodes.append(
                {
                    "id": source_id,
                    "kind": "asset",
                    "asset_kind": "scene" if path.endswith(".unity") else "prefab",
                    "name": os.path.basename(path),
                    "path": path,
                    "module": asset.get("module", ""),
                    "guid": asset.get("guid", ""),
                }
            )
            for script_guid in asset.get("script_guids", []):
                for target in guid_targets.get(script_guid, []):
                    self._add_edge(edges, source_id, target, "script_reference", path)

        type_nodes = [
            declarations_by_full_name[name]
            for name in sorted(declarations_by_full_name)
        ]
        nodes = sorted(type_nodes + asset_nodes, key=lambda item: item["id"])
        edge_list = sorted(
            edges.values(),
            key=lambda item: (item["source"], item["target"], item["kind"]),
        )
        duplicate_types = [
            {"full_name": node["full_name"], "paths": node["paths"]}
            for node in type_nodes
            if len(node["paths"]) > 1
        ]
        ambiguous_references.sort(
            key=lambda item: (item["source"], item["reference"], item["path"])
        )

        return {
            "schema_version": self.SCHEMA_VERSION,
            "project": {
                "name": project.get("name", ""),
                "root": project_root,
                "project_context_schema_version": project_context.get("schema_version"),
            },
            "summary": {
                "nodes": len(nodes),
                "edges": len(edge_list),
                "types": len(type_nodes),
                "assets": len(asset_nodes),
                "duplicate_types": len(duplicate_types),
                "ambiguous_references": len(ambiguous_references),
                "source_errors": len(source_errors),
            },
            "nodes": nodes,
            "edges": edge_list,
            "diagnostics": {
                "duplicate_types": duplicate_types,
                "ambiguous_references": ambiguous_references,
                "source_errors": source_errors,
            },
        }

    @staticmethod
    def _read_source(project_root, relative_path, errors):
        path = os.path.join(project_root, *relative_path.split("/"))
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as file:
                return file.read()
        except OSError as error:
            errors.append({"path": relative_path, "error": str(error)})
            return ""

    @staticmethod
    def _sanitize(source):
        patterns = [
            r"/\*.*?\*/",
            r"//[^\n]*",
            r'@"(?:""|[^"])*"',
            r'\$?"(?:\\.|[^"\\])*"',
            r"'(?:\\.|[^'\\])'",
        ]
        sanitized = source
        for pattern in patterns:
            sanitized = re.sub(
                pattern,
                lambda match: " " * len(match.group(0)),
                sanitized,
                flags=re.S if pattern == patterns[0] else 0,
            )
        return sanitized

    @staticmethod
    def _declaration_segment(source, kind, name):
        if not name:
            return ""
        match = re.search(
            rf"\b{re.escape(kind)}\s+{re.escape(name)}\b",
            source,
        )
        if not match:
            return ""
        opening = source.find("{", match.end())
        if opening < 0:
            return source[match.start():]
        depth = 0
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[match.start():index + 1]
        return source[match.start():]

    @staticmethod
    def _resolve_type(
        reference,
        namespace,
        using_namespaces,
        declarations,
        short_index,
        source_id,
        path,
        ambiguous,
    ):
        reference = reference.replace("global::", "").strip()
        reference = re.sub(r"[?\[\]]", "", reference)
        reference = reference.split("<", 1)[0].strip()
        if not reference:
            return None
        if reference in declarations:
            return "type:" + reference

        short_name = reference.rsplit(".", 1)[-1]
        candidates = []
        if namespace and namespace + "." + short_name in declarations:
            candidates.append(namespace + "." + short_name)
        for using_namespace in using_namespaces:
            candidate = using_namespace + "." + short_name
            if candidate in declarations and candidate not in candidates:
                candidates.append(candidate)
        if not candidates:
            candidates = list(short_index.get(short_name, []))
        if len(candidates) == 1:
            return "type:" + candidates[0]
        if len(candidates) > 1:
            item = {
                "source": source_id,
                "path": path,
                "reference": short_name,
                "candidates": sorted(candidates),
            }
            if item not in ambiguous:
                ambiguous.append(item)
        return None

    @staticmethod
    def _add_edge(edges, source, target, kind, evidence_path):
        key = (source, target, kind)
        edges[key] = {
            "source": source,
            "target": target,
            "kind": kind,
            "evidence": {"path": evidence_path},
        }


class DependencyGraphQuery:
    """Query direct, reverse, and transitive relationships in a graph."""

    def __init__(self, graph):
        self.forward = {}
        self.reverse = {}
        for edge in graph.get("edges", []):
            self.forward.setdefault(edge["source"], set()).add(edge["target"])
            self.reverse.setdefault(edge["target"], set()).add(edge["source"])

    def dependencies(self, node_id, transitive=False):
        return self._query(self.forward, node_id, transitive)

    def dependents(self, node_id, transitive=False):
        return self._query(self.reverse, node_id, transitive)

    @staticmethod
    def _query(index, node_id, transitive):
        direct = set(index.get(node_id, set()))
        if not transitive:
            return sorted(direct)

        visited = set()
        pending = list(direct)
        while pending:
            current = pending.pop()
            if current in visited or current == node_id:
                continue
            visited.add(current)
            pending.extend(index.get(current, set()) - visited)
        return sorted(visited)
