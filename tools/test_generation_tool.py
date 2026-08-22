import os
import shutil
import tempfile
import uuid


class TestGenerationTool:
    """Safely replace generated Unity test files inside one managed root."""

    def __init__(self, root_path):
        self.root_path = os.path.realpath(os.path.abspath(root_path))

    def apply(self, tests):
        errors = self._validate(tests)
        if errors:
            return {"success": False, "files": [], "errors": errors}

        parent = os.path.dirname(self.root_path)
        os.makedirs(parent, exist_ok=True)
        staging_path = tempfile.mkdtemp(prefix=".generated-tests-", dir=parent)
        backup_path = self.root_path + ".backup-" + uuid.uuid4().hex

        try:
            for test in tests:
                path = os.path.join(staging_path, test["name"])
                with open(path, "w", encoding="utf-8") as file:
                    file.write(test["content"])

            had_existing = os.path.isdir(self.root_path)
            if had_existing:
                os.replace(self.root_path, backup_path)
            os.replace(staging_path, self.root_path)
            if had_existing:
                shutil.rmtree(backup_path)
        except OSError as error:
            if os.path.isdir(staging_path):
                shutil.rmtree(staging_path, ignore_errors=True)
            if os.path.isdir(backup_path) and not os.path.exists(self.root_path):
                os.replace(backup_path, self.root_path)
            return {"success": False, "files": [], "errors": [str(error)]}

        return {
            "success": True,
            "files": sorted(test["name"] for test in tests),
            "errors": [],
        }

    def apply_platforms(self, editmode_tests, playmode_tests):
        errors = [
            f"EditMode: {error}" for error in self._validate(editmode_tests)
        ] + [f"PlayMode: {error}" for error in self._validate(playmode_tests)]
        if errors:
            return {
                "success": False,
                "files": [],
                "editmode_files": [],
                "playmode_files": [],
                "errors": errors,
            }

        parent = os.path.dirname(self.root_path)
        os.makedirs(parent, exist_ok=True)
        staging_path = tempfile.mkdtemp(prefix=".generated-tests-", dir=parent)
        backup_path = self.root_path + ".backup-" + uuid.uuid4().hex
        try:
            for platform, tests in (
                ("editmode", editmode_tests),
                ("playmode", playmode_tests),
            ):
                platform_path = os.path.join(staging_path, platform)
                os.makedirs(platform_path)
                for test in tests:
                    with open(
                        os.path.join(platform_path, test["name"]),
                        "w",
                        encoding="utf-8",
                    ) as file:
                        file.write(test["content"])

            had_existing = os.path.isdir(self.root_path)
            if had_existing:
                os.replace(self.root_path, backup_path)
            os.replace(staging_path, self.root_path)
            if had_existing:
                shutil.rmtree(backup_path)
        except OSError as error:
            if os.path.isdir(staging_path):
                shutil.rmtree(staging_path, ignore_errors=True)
            if os.path.isdir(backup_path) and not os.path.exists(self.root_path):
                os.replace(backup_path, self.root_path)
            return {
                "success": False,
                "files": [],
                "editmode_files": [],
                "playmode_files": [],
                "errors": [str(error)],
            }

        editmode_files = sorted(test["name"] for test in editmode_tests)
        playmode_files = sorted(test["name"] for test in playmode_tests)
        return {
            "success": True,
            "files": editmode_files + playmode_files,
            "editmode_files": editmode_files,
            "playmode_files": playmode_files,
            "errors": [],
        }

    @staticmethod
    def _validate(tests):
        if not isinstance(tests, list) or not tests:
            return ["tests must be a non-empty list"]

        errors = []
        names = set()
        for index, test in enumerate(tests):
            if not isinstance(test, dict):
                errors.append(f"tests[{index}] must be an object")
                continue
            name = test.get("name", "")
            content = test.get("content", "")
            if (
                not isinstance(name, str)
                or not name.endswith(".cs")
                or os.path.basename(name) != name
                or "/" in name
                or "\\" in name
            ):
                errors.append(f"invalid test file name: {name}")
            elif name in names:
                errors.append(f"duplicate test file name: {name}")
            names.add(name)
            if not isinstance(content, str) or not content.strip():
                errors.append(f"test content is empty: {name}")
        return errors
