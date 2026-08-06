import hashlib
import json
import os
import re
from datetime import datetime, timezone


class LongTermMemoryStore:
    """Persist verified, project-scoped engineering memory."""

    SCHEMA_VERSION = 1
    CATEGORIES = (
        "project_memory",
        "coding_style",
        "bug_history",
        "solution_history",
    )

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.data = self._load()

    def get_project(self, project_path):
        project_key = self._project_key(project_path)
        project = self.data["projects"].get(project_key)
        if project is None:
            project = self._empty_project(project_path)
            self.data["projects"][project_key] = project
            self._save()
        self._validate_project(project)
        return project

    def update_project_memory(self, project_path, context):
        if not isinstance(context, dict):
            raise ValueError("project memory must be a JSON object")
        project = self.get_project(project_path)
        project_memory = project["project_memory"]
        for key in ("project", "summary", "modules", "packages", "scan_errors"):
            if key in context:
                project_memory[key] = context[key]
        project_memory["project_path"] = os.path.abspath(project_path)
        project_memory["updated_at"] = self._now()
        self._save()
        return project_memory

    def remember_coding_style(self, project_path, rule, source="manual"):
        rule = str(rule).strip()
        if not rule:
            raise ValueError("coding style rule must not be empty")
        project = self.get_project(project_path)
        normalized = self._normalize(rule)
        for item in project["coding_style"]:
            if self._normalize(item.get("rule", "")) == normalized:
                item["last_seen_at"] = self._now()
                self._save()
                return item
        item = {
            "id": self._hash("style", normalized),
            "rule": rule,
            "source": source,
            "created_at": self._now(),
            "last_seen_at": self._now(),
        }
        project["coding_style"].append(item)
        self._save()
        return item

    def record_failure(self, project_path, source, error):
        if source not in ("compile", "test"):
            raise ValueError("failure source must be compile or test")
        if not isinstance(error, dict):
            raise ValueError("failure error must be a JSON object")

        project = self.get_project(project_path)
        fingerprint = self._bug_fingerprint(source, error)
        bug = next(
            (
                item
                for item in project["bug_history"]
                if item.get("fingerprint") == fingerprint
            ),
            None,
        )
        now = self._now()
        if bug is None:
            bug = {
                "id": self._hash("bug", fingerprint),
                "fingerprint": fingerprint,
                "source": source,
                "error_code": str(error.get("code", "") or "TEST_FAILURE"),
                "file": str(error.get("file", "")),
                "symbol": str(error.get("symbol", "")),
                "message": str(error.get("message", "")),
                "test": str(error.get("test", "")),
                "status": "open",
                "occurrences": 1,
                "first_seen_at": now,
                "last_seen_at": now,
            }
            project["bug_history"].append(bug)
        else:
            bug["status"] = "open"
            bug["occurrences"] = int(bug.get("occurrences", 0)) + 1
            bug["last_seen_at"] = now
            bug.pop("resolved_at", None)

        active_bugs = project["project_memory"].setdefault("active_bugs", {})
        active_ids = active_bugs.setdefault(source, [])
        if bug["id"] not in active_ids:
            active_ids.append(bug["id"])
        self._save()
        return bug

    def record_successful_repair(self, project_path, source, repair_record):
        project = self.get_project(project_path)
        active_bugs = project["project_memory"].setdefault("active_bugs", {})
        bug_ids = list(active_bugs.get(source, []))
        if not bug_ids:
            return {}

        actions = [
            action
            for action in repair_record.get("actions", [])
            if isinstance(action, dict) and action.get("success", False)
        ]
        if not actions:
            return {}

        roots = [action.get("root", {}) for action in actions]
        error_codes = sorted(
            {
                str(root.get("error_code", ""))
                for root in roots
                if root.get("error_code")
            }
            or {
                bug.get("error_code", "")
                for bug in project["bug_history"]
                if bug.get("id") in bug_ids
            }
        )
        operations = sorted(
            {
                str(root.get("fix_action", {}).get("operation", ""))
                for root in roots
                if root.get("fix_action", {}).get("operation")
            }
        )
        strategies = []
        for root in roots:
            strategy = str(
                root.get("fix_strategy", "")
                or root.get("description", "")
                or root.get("cause", "")
            ).strip()
            if strategy and strategy not in strategies:
                strategies.append(strategy)

        solution_id = self._hash(
            "solution",
            source,
            ",".join(sorted(bug_ids)),
            str(repair_record.get("round", "")),
            ",".join(operations),
        )
        existing = next(
            (
                item
                for item in project["solution_history"]
                if item.get("id") == solution_id
            ),
            None,
        )
        now = self._now()
        if existing is None:
            existing = {
                "id": solution_id,
                "source": source,
                "bug_ids": sorted(bug_ids),
                "error_codes": error_codes,
                "successful_operations": operations,
                "strategies": strategies,
                "repair_round": repair_record.get("round"),
                "success_count": 1,
                "created_at": now,
                "last_verified_at": now,
            }
            project["solution_history"].append(existing)
        else:
            existing["success_count"] = int(existing.get("success_count", 0)) + 1
            existing["last_verified_at"] = now

        for bug in project["bug_history"]:
            if bug.get("id") in bug_ids:
                bug["status"] = "resolved"
                bug["resolved_at"] = now
        active_bugs[source] = []
        self._save()
        return existing

    def recall(self, project_path, source, errors, limit=5):
        project = self.get_project(project_path)
        error_codes = sorted(
            {
                str(error.get("code", "") or "TEST_FAILURE")
                for error in errors
                if isinstance(error, dict)
            }
        )
        insights = []
        for solution in project["solution_history"]:
            matching_codes = sorted(
                set(error_codes).intersection(solution.get("error_codes", []))
            )
            if source != solution.get("source") or not matching_codes:
                continue
            strategies = solution.get("strategies", [])
            insights.append(
                {
                    "error_code": matching_codes[0],
                    "recommended_strategy": strategies[0] if strategies else "",
                    "successful_operations": solution.get(
                        "successful_operations", []
                    ),
                    "success_count": solution.get("success_count", 1),
                    "last_verified_at": solution.get("last_verified_at", ""),
                }
            )
        insights.sort(
            key=lambda item: (
                item.get("success_count", 0),
                item.get("last_verified_at", ""),
            ),
            reverse=True,
        )
        return {
            "matched_error_codes": error_codes,
            "insights": insights[:limit],
            "coding_style": project["coding_style"][:limit],
        }

    def get_bug(self, project_path, bug_id):
        return next(
            (
                bug
                for bug in self.get_project(project_path)["bug_history"]
                if bug.get("id") == bug_id
            ),
            None,
        )

    def _load(self):
        if not os.path.exists(self.path):
            return {"schema_version": self.SCHEMA_VERSION, "projects": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as memory_file:
                data = json.load(memory_file)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to load long-term memory: {error}") from error
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != self.SCHEMA_VERSION
            or not isinstance(data.get("projects"), dict)
        ):
            raise ValueError("Invalid long-term memory schema")
        for project in data["projects"].values():
            self._validate_project(project)
        return data

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary_path = self.path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as memory_file:
                json.dump(self.data, memory_file, ensure_ascii=False, indent=2)
                memory_file.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def _empty_project(self, project_path):
        return {
            "project_memory": {
                "project_path": os.path.abspath(project_path),
                "active_bugs": {"compile": [], "test": []},
            },
            "coding_style": [],
            "bug_history": [],
            "solution_history": [],
        }

    def _validate_project(self, project):
        if not isinstance(project, dict) or set(project) != set(self.CATEGORIES):
            raise ValueError("Invalid long-term memory project schema")
        if not isinstance(project["project_memory"], dict):
            raise ValueError("Invalid project_memory category")
        for category in ("coding_style", "bug_history", "solution_history"):
            if not isinstance(project[category], list):
                raise ValueError(f"Invalid {category} category")

    @staticmethod
    def _normalize(value):
        return re.sub(r"\s+", " ", str(value).strip().lower())

    def _bug_fingerprint(self, source, error):
        return "|".join(
            [
                source,
                self._normalize(error.get("code", "") or "TEST_FAILURE"),
                self._normalize(os.path.basename(str(error.get("file", "")))),
                self._normalize(error.get("symbol", "")),
                self._normalize(error.get("test", "")),
                self._normalize(error.get("message", "")),
            ]
        )

    @staticmethod
    def _project_key(project_path):
        normalized = os.path.normcase(os.path.abspath(project_path))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _hash(*parts):
        value = "|".join(str(part) for part in parts)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
