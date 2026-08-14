import os
import tempfile
import unittest

from tools.unity_test_tool import UnityTestTool


PASS_XML = """<?xml version="1.0" encoding="utf-8"?>
<test-run testcasecount="1" result="Passed" total="1" passed="1" failed="0" skipped="0" inconclusive="0" duration="0.12">
  <test-suite type="Assembly" result="Passed">
    <test-case name="Adds" fullname="ProbeTests.Adds" result="Passed" duration="0.01" />
  </test-suite>
</test-run>
"""

FAIL_XML = """<?xml version="1.0" encoding="utf-8"?>
<test-run testcasecount="1" result="Failed" total="1" passed="0" failed="1" skipped="0" inconclusive="0" duration="0.15">
  <test-suite type="Assembly" result="Failed">
    <test-case name="Adds" fullname="ProbeTests.Adds" result="Failed" duration="0.02">
      <failure><message>Expected: 2 But was: 3</message><stack-trace>at ProbeTests.Adds()</stack-trace></failure>
    </test-case>
  </test-suite>
</test-run>
"""


class UnityTestToolTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.unity_path = os.path.join(self.temp_dir.name, "Unity.exe")
        open(self.unity_path, "w", encoding="utf-8").close()
        self.project_path = os.path.join(self.temp_dir.name, "UnityProject")
        for folder in ("Assets", "Packages", "ProjectSettings"):
            os.makedirs(os.path.join(self.project_path, folder))
        with open(
            os.path.join(self.project_path, "ProjectSettings", "ProjectVersion.txt"),
            "w",
            encoding="utf-8",
        ) as file:
            file.write("m_EditorVersion: 2022.3.62f2c1")
        with open(
            os.path.join(self.project_path, "Packages", "manifest.json"),
            "w",
            encoding="utf-8",
        ) as file:
            file.write('{"dependencies":{"com.unity.test-framework":"1.1.33"}}')

        self.production_path = os.path.join(self.temp_dir.name, "generated")
        self.tests_path = os.path.join(self.temp_dir.name, "generated_tests")
        os.makedirs(self.production_path)
        os.makedirs(self.tests_path)
        with open(os.path.join(self.production_path, "Probe.cs"), "w", encoding="utf-8") as file:
            file.write("public static class Probe { public static int Add(int a,int b)=>a+b; }")
        with open(os.path.join(self.tests_path, "ProbeTests.cs"), "w", encoding="utf-8") as file:
            file.write("public class ProbeTests {}")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _tool(self, process_factory=None):
        return UnityTestTool(
            self.unity_path,
            self.project_path,
            self.production_path,
            self.tests_path,
            process_factory=process_factory,
            result_grace=0,
        )

    @staticmethod
    def _process_factory(
        xml_content=None,
        returncode=0,
        stay_running=False,
        log_content="",
    ):
        class FakeProcess:
            def __init__(self, command, **kwargs):
                self.returncode = None if stay_running else returncode
                if xml_content is not None:
                    results_path = command[command.index("-testResults") + 1]
                    with open(results_path, "w", encoding="utf-8") as file:
                        file.write(xml_content)
                if log_content:
                    log_path = command[command.index("-logFile") + 1]
                    with open(log_path, "w", encoding="utf-8") as file:
                        file.write(log_content)

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

            def kill(self):
                self.returncode = -9

            def wait(self, timeout=None):
                return self.returncode

        return FakeProcess

    def test_parses_passing_and_failing_nunit_xml(self):
        passing = self._tool().parse_results(PASS_XML)
        failing = self._tool().parse_results(FAIL_XML)

        self.assertTrue(passing["success"])
        self.assertEqual(1, passing["summary"]["passed"])
        self.assertFalse(failing["success"])
        self.assertEqual(1, failing["summary"]["failed"])
        self.assertIn("Expected: 2", failing["tests"][0]["message"])

    def test_runs_in_sandbox_and_preserves_real_project(self):
        captured = {}

        base_factory = self._process_factory(PASS_XML)

        class InspectingProcess(base_factory):
            def __init__(inner_self, command, **kwargs):
                sandbox = command[command.index("-projectPath") + 1]
                captured["sandbox"] = sandbox
                self.assertNotEqual(os.path.realpath(self.project_path), os.path.realpath(sandbox))
                self.assertTrue(os.path.isfile(os.path.join(sandbox, "Assets", "Generated", "CodingAgent.Generated.asmdef")))
                self.assertTrue(os.path.isfile(os.path.join(sandbox, "Assets", "Tests", "EditMode", "ProbeTests.cs")))
                super().__init__(command, **kwargs)

        result = self._tool(InspectingProcess).run()

        self.assertTrue(result["success"])
        self.assertTrue(result["sandbox_cleaned"])
        self.assertFalse(os.path.exists(captured["sandbox"]))
        self.assertFalse(os.path.exists(os.path.join(self.project_path, "Assets", "Tests")))

    def test_assertion_failure_is_not_a_system_error(self):
        result = self._tool(self._process_factory(FAIL_XML, returncode=2)).run()

        self.assertFalse(result["success"])
        self.assertFalse(result["system_error"])
        self.assertEqual(1, result["summary"]["failed"])

    def test_missing_result_xml_is_a_system_error(self):
        result = self._tool(self._process_factory(returncode=1)).run()

        self.assertFalse(result["success"])
        self.assertTrue(result["system_error"])
        self.assertIn("result XML", result["errors"][0]["message"])

    def test_missing_xml_with_test_compilation_errors_is_retryable_code_failure(self):
        result = self._tool(
            self._process_factory(
                returncode=1,
                log_content=(
                    "Assets\\Tests\\EditMode\\DragEventsTests.cs(12,33): "
                    "error CS0246: The type or namespace name 'GameObject' could not be found\n"
                    "Scripts have compiler errors.\n"
                ),
            )
        ).run()

        self.assertFalse(result["success"])
        self.assertFalse(result["system_error"])
        self.assertEqual("TEST_ASSEMBLY_COMPILE_ERROR", result["error_code"])
        self.assertEqual("DragEventsTests.cs", result["errors"][0]["file"])
        self.assertEqual("CS0246", result["errors"][0]["code"])

    def test_running_process_is_stopped_after_result_xml(self):
        result = self._tool(
            self._process_factory(PASS_XML, stay_running=True)
        ).run()

        self.assertTrue(result["success"])
        self.assertFalse(result["system_error"])
        self.assertTrue(result["runner_stopped_after_results"])


if __name__ == "__main__":
    unittest.main()
