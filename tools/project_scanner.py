import json
import os
import re
from datetime import datetime, timezone


class UnityProjectScanner:
    """确定性扫描 Unity 项目的 Assets 和轻量代码结构。"""

    SCHEMA_VERSION = 1
    IGNORE_DIRECTORIES = {
        ".git",
        ".ipynb_checkpoints",
        "Build",
        "Builds",
        "Library",
        "Logs",
        "Temp",
        "obj"
    }

    def __init__(self, project_path):
        self.project_path = os.path.realpath(
            os.path.abspath(project_path)
        )
        self.assets_path = os.path.join(
            self.project_path,
            "Assets"
        )
        self.scan_errors = []


    def scan(self):
        self._validate_project()
        self.scan_errors = []
        assets = []
        scripts = []
        scenes = []
        prefabs = []

        for root, directories, file_names in os.walk(
            self.assets_path
        ):
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in self.IGNORE_DIRECTORIES
            )

            for file_name in sorted(file_names):
                if file_name.endswith(".meta"):
                    continue

                absolute_path = os.path.join(root, file_name)
                relative_path = self._relative_path(absolute_path)
                extension = os.path.splitext(file_name)[1].lower()
                asset_type = self._asset_type(extension)
                asset = {
                    "path": relative_path,
                    "name": file_name,
                    "extension": extension,
                    "type": asset_type,
                    "module": self._module_name(relative_path),
                    "size": os.path.getsize(absolute_path),
                    "guid": self._read_guid(absolute_path + ".meta")
                }
                assets.append(asset)

                if extension == ".cs":
                    scripts.append(
                        self._scan_script(
                            absolute_path,
                            asset
                        )
                    )
                elif extension == ".unity":
                    scenes.append(
                        self._scan_yaml_asset(
                            absolute_path,
                            asset
                        )
                    )
                elif extension == ".prefab":
                    prefabs.append(
                        self._scan_yaml_asset(
                            absolute_path,
                            asset
                        )
                    )

        assets.sort(key=lambda item: item["path"])
        scripts.sort(key=lambda item: item["path"])
        scenes.sort(key=lambda item: item["path"])
        prefabs.sort(key=lambda item: item["path"])
        modules = self._build_modules(assets)
        declaration_count = sum(
            len(script["declarations"])
            for script in scripts
        )

        return {
            "schema_version": self.SCHEMA_VERSION,
            "project": {
                "name": os.path.basename(self.project_path),
                "root": self.project_path.replace("\\", "/"),
                "unity_version": self._unity_version(),
                "scanned_at": datetime.now(timezone.utc).isoformat()
            },
            "summary": {
                "assets": len(assets),
                "scripts": len(scripts),
                "scenes": len(scenes),
                "prefabs": len(prefabs),
                "modules": len(modules),
                "declarations": declaration_count,
                "scan_errors": len(self.scan_errors)
            },
            "modules": modules,
            "assets": assets,
            "scripts": scripts,
            "scenes": scenes,
            "prefabs": prefabs,
            "packages": self._packages(),
            "scan_errors": list(self.scan_errors)
        }


    def _validate_project(self):
        required_paths = [
            self.assets_path,
            os.path.join(self.project_path, "Packages"),
            os.path.join(self.project_path, "ProjectSettings")
        ]
        missing = [
            path
            for path in required_paths
            if not os.path.isdir(path)
        ]

        if missing:
            raise ValueError(
                "不是有效的 Unity 项目，缺少:"
                + ", ".join(missing)
            )


    def _scan_script(self, absolute_path, asset):
        content = self._read_text(absolute_path)
        code = self._remove_comments(content)
        namespace_match = re.search(
            r"\bnamespace\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*[;{]",
            code
        )
        namespace = (
            namespace_match.group(1)
            if namespace_match
            else ""
        )
        using_namespaces = sorted(
            set(
                re.findall(
                    r"^\s*using\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;",
                    code,
                    re.M
                )
            )
        )
        declarations = []

        for match in re.finditer(
            r"\b(class|interface|struct|enum|record)\s+"
            r"([A-Za-z_]\w*)"
            r"(?:\s*:\s*([^\n{]+))?",
            code
        ):
            base_types = self._base_types(
                match.group(3) or ""
            )
            declarations.append(
                {
                    "kind": match.group(1),
                    "name": match.group(2),
                    "full_name": (
                        namespace + "." + match.group(2)
                        if namespace
                        else match.group(2)
                    ),
                    "base_types": base_types
                }
            )

        dependency_base_types = sorted(
            {
                base_type
                for declaration in declarations
                for base_type in declaration["base_types"]
            }
        )

        return {
            "path": asset["path"],
            "module": asset["module"],
            "guid": asset["guid"],
            "namespace": namespace,
            "declarations": declarations,
            "dependency_hints": {
                "using_namespaces": using_namespaces,
                "base_types": dependency_base_types
            }
        }


    def _scan_yaml_asset(self, absolute_path, asset):
        content = self._read_text(absolute_path)
        script_guids = sorted(
            set(
                re.findall(
                    r"m_Script:.*?guid:\s*([^,\s}]+)",
                    content
                )
            )
        )

        return {
            "path": asset["path"],
            "module": asset["module"],
            "guid": asset["guid"],
            "game_objects": len(
                re.findall(r"^--- !u!1\s", content, re.M)
            ),
            "mono_behaviours": len(
                re.findall(r"^--- !u!114\s", content, re.M)
            ),
            "script_guids": script_guids
        }


    def _build_modules(self, assets):
        modules = {}

        for asset in assets:
            name = asset["module"]
            module = modules.setdefault(
                name,
                {
                    "name": name,
                    "path": (
                        "Assets"
                        if name == "Assets"
                        else "Assets/" + name
                    ),
                    "assets": 0,
                    "scripts": 0,
                    "scenes": 0,
                    "prefabs": 0
                }
            )
            module["assets"] += 1

            if asset["type"] == "script":
                module["scripts"] += 1
            elif asset["type"] == "scene":
                module["scenes"] += 1
            elif asset["type"] == "prefab":
                module["prefabs"] += 1

        return [modules[name] for name in sorted(modules)]


    def _unity_version(self):
        version_path = os.path.join(
            self.project_path,
            "ProjectSettings",
            "ProjectVersion.txt"
        )
        content = self._read_text(version_path)
        match = re.search(
            r"^m_EditorVersion:\s*(.+)$",
            content,
            re.M
        )
        return match.group(1).strip() if match else ""


    def _packages(self):
        manifest_path = os.path.join(
            self.project_path,
            "Packages",
            "manifest.json"
        )

        if not os.path.isfile(manifest_path):
            return []

        try:
            data = json.loads(self._read_text(manifest_path))
            dependencies = data.get("dependencies", {})
            return [
                {
                    "name": name,
                    "version": dependencies[name]
                }
                for name in sorted(dependencies)
            ]
        except (json.JSONDecodeError, AttributeError) as error:
            self.scan_errors.append(
                {
                    "path": self._relative_path(manifest_path),
                    "error": str(error)
                }
            )
            return []


    def _read_text(self, path):
        try:
            with open(
                path,
                "r",
                encoding="utf-8",
                errors="replace"
            ) as source_file:
                return source_file.read()
        except OSError as error:
            self.scan_errors.append(
                {
                    "path": self._relative_path(path),
                    "error": str(error)
                }
            )
            return ""


    def _read_guid(self, meta_path):
        if not os.path.isfile(meta_path):
            return ""

        content = self._read_text(meta_path)
        match = re.search(r"^guid:\s*(\S+)", content, re.M)
        return match.group(1) if match else ""


    def _relative_path(self, absolute_path):
        return os.path.relpath(
            absolute_path,
            self.project_path
        ).replace("\\", "/")


    @staticmethod
    def _module_name(relative_path):
        parts = relative_path.split("/")
        return parts[1] if len(parts) > 2 else "Assets"


    @staticmethod
    def _asset_type(extension):
        return {
            ".cs": "script",
            ".unity": "scene",
            ".prefab": "prefab"
        }.get(extension, "asset")


    @staticmethod
    def _remove_comments(content):
        without_blocks = re.sub(
            r"/\*.*?\*/",
            "",
            content,
            flags=re.S
        )
        return re.sub(r"//.*", "", without_blocks)


    @staticmethod
    def _base_types(base_text):
        return [
            item.strip().split("<", 1)[0].strip()
            for item in base_text.split(",")
            if item.strip()
        ]
