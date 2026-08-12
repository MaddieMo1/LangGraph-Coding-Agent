import os
import unittest
from unittest.mock import patch

from agents.unity_test import unity_test_agent


class FakeUnityTestTool:
    last_kwargs = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        type(self).last_kwargs = kwargs

    def run(self):
        return {
            "success": True,
            "system_error": False,
            "summary": {"total": 2, "passed": 2, "failed": 0},
        }


class UnityTestAgentTest(unittest.TestCase):
    def test_records_structured_test_history(self):
        configured = {
            "GENERATED_SOURCE_PATH": os.path.abspath("configured-production"),
            "GENERATED_TEST_SOURCE_PATH": os.path.abspath("configured-tests"),
        }
        with patch.dict(os.environ, configured), patch(
            "agents.unity_test.UnityTestTool", FakeUnityTestTool
        ):
            result = unity_test_agent(
                {"agent_history": [], "test_history": []}
            )

        self.assertEqual("unity_test", result["current_agent"])
        self.assertTrue(result["test_result"]["success"])
        self.assertEqual(2, result["test_history"][0]["summary"]["passed"])
        self.assertEqual(
            configured["GENERATED_SOURCE_PATH"],
            FakeUnityTestTool.last_kwargs["production_source_path"],
        )
        self.assertEqual(
            configured["GENERATED_TEST_SOURCE_PATH"],
            FakeUnityTestTool.last_kwargs["test_source_path"],
        )


if __name__ == "__main__":
    unittest.main()
