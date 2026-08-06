import os

from tools.diff_tool import DiffTool


class ChangeProposalTool:
    """Create bounded production-code patches without applying them."""

    SOURCES = {"coder", "repair"}

    def __init__(self, file_manager, generated_root="generated", diff_tool=None):
        self.file_manager = file_manager
        self.generated_root = os.path.realpath(os.path.abspath(generated_root))
        self.diff_tool = diff_tool or DiffTool(file_manager, self.generated_root)

    def propose(self, changes, source):
        if source not in self.SOURCES:
            raise ValueError("change proposal source must be coder or repair")
        if not isinstance(changes, list) or not changes:
            raise ValueError("change proposal requires at least one change")

        validated_changes = []
        seen = set()
        for change in changes:
            if not isinstance(change, dict):
                raise ValueError("change proposal entries must be objects")
            path, normalized_name = self._resolve_file(change.get("file", ""))
            content = change.get("content")
            if not isinstance(content, str) or not content:
                raise ValueError(f"change content must not be empty: {normalized_name}")
            if normalized_name in seen:
                raise ValueError(f"change proposal contains duplicate file: {normalized_name}")
            seen.add(normalized_name)
            validated_changes.append((path, normalized_name, content))

        patches = []
        unchanged_files = []
        for path, normalized_name, after_content in validated_changes:
            before_content = (
                self.file_manager.read_file(path) if os.path.isfile(path) else ""
            )
            patch = self.diff_tool.create_patch(
                normalized_name,
                before_content,
                after_content,
            )
            if patch["changed"]:
                patches.append(patch)
            else:
                unchanged_files.append(normalized_name)

        return {
            "source": source,
            "patches": patches,
            "unchanged_files": unchanged_files,
        }

    def _resolve_file(self, file_name):
        if not isinstance(file_name, str) or not file_name.strip():
            raise ValueError("change proposal file path must not be empty")
        normalized_name = os.path.normpath(file_name.strip().replace("\\", "/"))
        if os.path.isabs(normalized_name):
            raise ValueError(f"absolute file path is not allowed: {file_name}")
        candidate = os.path.realpath(
            os.path.abspath(os.path.join(self.generated_root, normalized_name))
        )
        try:
            inside_generated_root = os.path.normcase(
                os.path.commonpath([self.generated_root, candidate])
            ) == os.path.normcase(self.generated_root)
        except ValueError:
            inside_generated_root = False
        if not inside_generated_root:
            raise ValueError(f"file path escapes generated directory: {file_name}")
        if not candidate.lower().endswith(".cs"):
            raise ValueError(f"only C# files may be proposed: {file_name}")
        relative_name = os.path.relpath(candidate, self.generated_root).replace("\\", "/")
        return candidate, relative_name
