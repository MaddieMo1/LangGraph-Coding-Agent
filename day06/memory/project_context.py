import json
import os


class ProjectContextStore:
    """Persist the latest deterministic Unity project context."""

    SCHEMA_VERSION = 1

    def __init__(self, path):
        self.path = os.path.abspath(path)

    def save(self, context):
        self._validate(context)
        parent = os.path.dirname(self.path)
        os.makedirs(parent, exist_ok=True)
        temporary_path = self.path + ".tmp"

        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(context, file, ensure_ascii=False, indent=2)
            file.write("\n")

        os.replace(temporary_path, self.path)
        return self.path

    def load(self):
        if not os.path.exists(self.path):
            return {}

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                context = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to load project context: {error}") from error

        self._validate(context)
        return context

    def _validate(self, context):
        if not isinstance(context, dict):
            raise ValueError("project context must be a JSON object")
        if context.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported project context schema_version: "
                f"{context.get('schema_version')}"
            )


def build_prompt_context(context):
    """Return the useful, size-bounded part of project context for LLM prompts."""

    if not context:
        return {}

    keys = (
        "project",
        "summary",
        "modules",
        "scripts",
        "scenes",
        "prefabs",
        "packages",
        "scan_errors",
    )
    return {key: context.get(key, []) for key in keys if key in context}
