import json
import os
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET


class UnityTestTool:
    """Run Unity EditMode tests in an isolated copy of the target project."""

    def __init__(
        self,
        unity_path,
        project_path,
        production_source_path,
        test_source_path,
        timeout=600,
        keep_sandbox=False,
        process_factory=None,
        result_grace=3.0,
    ):
        self.unity_path = os.path.realpath(os.path.abspath(unity_path))
        self.project_path = os.path.realpath(os.path.abspath(project_path))
        self.production_source_path = os.path.realpath(
            os.path.abspath(production_source_path)
        )
        self.test_source_path = os.path.realpath(os.path.abspath(test_source_path))
        self.timeout = timeout
        self.keep_sandbox = keep_sandbox
        self.process_factory = process_factory or subprocess.Popen
        self.result_grace = result_grace

    def run(self):
        environment_error = self._validate_environment()
        if environment_error:
            return self._system_error(environment_error)

        sandbox_root = tempfile.mkdtemp(prefix="coding-agent-unity-tests-")
        sandbox_project = os.path.join(sandbox_root, "Project")
        results_path = os.path.join(sandbox_root, "test-results.xml")
        log_path = os.path.join(sandbox_root, "unity-test.log")
        result = None
        production_files = []
        test_files = []

        try:
            self._copy_project(sandbox_project)
            production_files, test_files = self._prepare_sources(sandbox_project)
            command = [
                self.unity_path,
                "-batchmode",
                "-nographics",
                "-runTests",
                "-testPlatform",
                "EditMode",
                "-projectPath",
                sandbox_project,
                "-testResults",
                results_path,
                "-logFile",
                log_path,
            ]
            exit_code, stopped_after_results = self._execute(
                command,
                results_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            raw = self._read_log(log_path)

            if not os.path.isfile(results_path):
                result = self._system_error(
                    f"Unity Test Runner did not create result XML (exit code {exit_code})",
                    raw,
                )
            else:
                try:
                    with open(results_path, "r", encoding="utf-8-sig") as file:
                        parsed = self.parse_results(file.read())
                    parsed.update(
                        {
                            "system_error": False,
                            "platform": "EditMode",
                            "production_files": production_files,
                            "test_files": test_files,
                            "exit_code": exit_code,
                            "raw": raw[-100000:],
                            "sandbox_project": sandbox_project,
                            "runner_stopped_after_results": stopped_after_results,
                        }
                    )
                    result = parsed
                except (OSError, ET.ParseError, ValueError) as error:
                    result = self._system_error(
                        f"Unable to parse Unity test result XML: {error}",
                        raw,
                    )
        except subprocess.TimeoutExpired:
            raw = self._read_log(log_path)
            if os.path.isfile(results_path):
                try:
                    with open(results_path, "r", encoding="utf-8-sig") as file:
                        parsed = self.parse_results(file.read())
                    parsed.update(
                        {
                            "system_error": False,
                            "platform": "EditMode",
                            "production_files": production_files,
                            "test_files": test_files,
                            "exit_code": None,
                            "raw": raw[-100000:],
                            "runner_timeout_after_results": True,
                        }
                    )
                    result = parsed
                except (OSError, ET.ParseError, ValueError) as error:
                    result = self._system_error(
                        f"Unity tests timed out and result XML was invalid: {error}",
                        raw,
                    )
            else:
                result = self._system_error(
                    f"Unity tests timed out after {self.timeout} seconds",
                    raw,
                )
        except (OSError, ValueError) as error:
            result = self._system_error(str(error))
        finally:
            cleaned = False
            if not self.keep_sandbox:
                shutil.rmtree(sandbox_root, ignore_errors=True)
                cleaned = not os.path.exists(sandbox_root)
            if result is not None:
                result["sandbox_project"] = sandbox_project
                result["sandbox_cleaned"] = cleaned

        return result

    def parse_results(self, xml_content):
        root = ET.fromstring(xml_content)
        test_cases = []
        errors = []

        for element in root.iter():
            if self._tag(element) != "test-case":
                continue
            test_result = element.attrib.get("result", "Unknown")
            item = {
                "name": element.attrib.get("name", ""),
                "full_name": element.attrib.get("fullname", ""),
                "result": test_result,
                "duration": self._float(element.attrib.get("duration", 0)),
                "message": self._descendant_text(element, "message"),
                "stack_trace": self._descendant_text(element, "stack-trace"),
            }
            test_cases.append(item)
            if test_result.lower().startswith("fail"):
                errors.append(
                    {
                        "test": item["full_name"] or item["name"],
                        "message": item["message"],
                        "stack_trace": item["stack_trace"],
                    }
                )

        passed = self._int(root.attrib.get("passed"), self._count(test_cases, "pass"))
        failed = self._int(root.attrib.get("failed"), self._count(test_cases, "fail"))
        skipped = self._int(root.attrib.get("skipped"), self._count(test_cases, "skip"))
        inconclusive = self._int(
            root.attrib.get("inconclusive"), self._count(test_cases, "inconclusive")
        )
        total = self._int(root.attrib.get("total"), len(test_cases))
        success = failed == 0 and not root.attrib.get("result", "").lower().startswith(
            "fail"
        )

        return {
            "success": success,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "inconclusive": inconclusive,
                "duration": self._float(root.attrib.get("duration", 0)),
            },
            "tests": test_cases,
            "errors": errors,
        }

    def _execute(self, command, results_path, **kwargs):
        process = self.process_factory(command, **kwargs)
        deadline = time.monotonic() + self.timeout
        result_ready_at = None

        while True:
            exit_code = process.poll()
            if self._valid_result_xml(results_path):
                if result_ready_at is None:
                    result_ready_at = time.monotonic()
                if exit_code is not None:
                    return exit_code, False
                if time.monotonic() - result_ready_at >= self.result_grace:
                    self._stop_process(process)
                    return process.poll(), True
            elif exit_code is not None:
                return exit_code, False

            if time.monotonic() >= deadline:
                self._stop_process(process)
                raise subprocess.TimeoutExpired(command, self.timeout)
            time.sleep(0.1)

    @staticmethod
    def _valid_result_xml(path):
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return False
        try:
            ET.parse(path)
            return True
        except (OSError, ET.ParseError):
            return False

    @staticmethod
    def _stop_process(process):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _validate_environment(self):
        if not os.path.isfile(self.unity_path):
            return f"Unity Editor does not exist: {self.unity_path}"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            if not os.path.isdir(os.path.join(self.project_path, folder)):
                return f"Invalid Unity project, missing {folder}: {self.project_path}"
        if not self._csharp_files(self.production_source_path):
            return f"No production C# files: {self.production_source_path}"
        if not self._csharp_files(self.test_source_path):
            return f"No generated test C# files: {self.test_source_path}"
        return ""

    def _copy_project(self, sandbox_project):
        os.makedirs(sandbox_project)
        for folder in ("Assets", "Packages", "ProjectSettings"):
            shutil.copytree(
                os.path.join(self.project_path, folder),
                os.path.join(sandbox_project, folder),
            )

    def _prepare_sources(self, sandbox_project):
        generated_target = os.path.join(sandbox_project, "Assets", "Generated")
        tests_target = os.path.join(sandbox_project, "Assets", "Tests", "EditMode")
        if os.path.isdir(generated_target):
            shutil.rmtree(generated_target)
        if os.path.isdir(tests_target):
            shutil.rmtree(tests_target)
        os.makedirs(generated_target)
        os.makedirs(tests_target)

        production_files = self._copy_csharp(self.production_source_path, generated_target)
        test_files = self._copy_csharp(self.test_source_path, tests_target)
        runtime_references = self._runtime_references(sandbox_project)
        self._write_json(
            os.path.join(generated_target, "CodingAgent.Generated.asmdef"),
            {
                "name": "CodingAgent.Generated",
                "references": runtime_references,
                "autoReferenced": True,
            },
        )
        self._write_json(
            os.path.join(tests_target, "CodingAgent.Generated.Tests.asmdef"),
            {
                "name": "CodingAgent.Generated.Tests",
                "references": ["CodingAgent.Generated"],
                "includePlatforms": ["Editor"],
                "optionalUnityReferences": ["TestAssemblies"],
                "autoReferenced": False,
            },
        )
        return production_files, test_files

    @staticmethod
    def _csharp_files(path):
        if not os.path.isdir(path):
            return []
        return sorted(name for name in os.listdir(path) if name.endswith(".cs"))

    def _copy_csharp(self, source, target):
        files = self._csharp_files(source)
        for name in files:
            shutil.copy2(os.path.join(source, name), os.path.join(target, name))
        return files

    @staticmethod
    def _runtime_references(sandbox_project):
        manifest_path = os.path.join(sandbox_project, "Packages", "manifest.json")
        try:
            with open(manifest_path, "r", encoding="utf-8") as file:
                packages = json.load(file).get("dependencies", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            packages = {}
        references = []
        if "com.unity.textmeshpro" in packages:
            references.append("Unity.TextMeshPro")
        if "com.unity.ugui" in packages:
            references.append("Unity.ugui")
        return references

    @staticmethod
    def _write_json(path, value):
        with open(path, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")

    @staticmethod
    def _read_log(path):
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as file:
            return file.read()

    @staticmethod
    def _system_error(message, raw=""):
        return {
            "success": False,
            "system_error": True,
            "platform": "EditMode",
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "inconclusive": 0,
                "duration": 0.0,
            },
            "tests": [],
            "errors": [{"test": "", "message": message, "stack_trace": ""}],
            "production_files": [],
            "test_files": [],
            "exit_code": None,
            "raw": raw[-100000:],
            "sandbox_project": "",
            "sandbox_cleaned": True,
        }

    @staticmethod
    def _tag(element):
        return element.tag.rsplit("}", 1)[-1]

    @classmethod
    def _descendant_text(cls, element, tag):
        for descendant in element.iter():
            if cls._tag(descendant) == tag:
                return descendant.text or ""
        return ""

    @staticmethod
    def _int(value, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _count(tests, prefix):
        return sum(
            1 for test in tests if test.get("result", "").lower().startswith(prefix)
        )
