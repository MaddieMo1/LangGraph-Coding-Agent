import unittest

from llm.invocation import RoleModel, invoke_model, model_state_update
from llm.model_router import ModelInvocationResult
from workflow.graph import AgentWorkflow


class FakeRouter:
    def __init__(self):
        self.calls = []

    def invoke(self, role, prompt, state=None, validator=None):
        self.calls.append((role, prompt, state, validator))
        return ModelInvocationResult(
            "response",
            {
                "role": role,
                "complexity": "standard",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "attempts": 1,
                "latency_ms": 10,
                "input_tokens": 3,
                "output_tokens": 5,
                "usage_available": True,
                "status": "success",
            },
        )


class LegacyLLM:
    def invoke(self, prompt):
        return "legacy"


class Day13WorkflowTests(unittest.TestCase):
    def test_workflow_binds_all_six_llm_roles_without_new_agents(self):
        workflow = AgentWorkflow()
        self.assertEqual("architecture", workflow.architecture.llm.role)
        self.assertEqual("file_planner", workflow.file_planner.llm.role)
        self.assertEqual("coder", workflow.coder.llm.role)
        self.assertEqual("test_generator", workflow.test_generator.llm.role)
        self.assertEqual("reviewer", workflow.reviewer.llm.role)
        self.assertEqual("repair", workflow.repair.llm.role)

    def test_role_model_passes_role_state_and_validator(self):
        router = FakeRouter()
        model = RoleModel(router, "reviewer")
        validator = lambda content: True
        result = invoke_model(model, "prompt", {"repair_count": 2}, validator)
        self.assertEqual("response", result.content)
        self.assertEqual("reviewer", router.calls[0][0])
        self.assertEqual(2, router.calls[0][2]["repair_count"])
        self.assertIs(validator, router.calls[0][3])

    def test_legacy_fake_llm_remains_supported(self):
        result = invoke_model(LegacyLLM(), "prompt", {"files": []})
        self.assertEqual("legacy", result.content)
        self.assertIsNone(result.record)

    def test_model_state_update_is_bounded_and_aggregates_usage(self):
        state = {
            "model_routing_history": [{"role": "old"}] * 100,
            "model_usage": {
                "deepseek/deepseek-v4-flash": {
                    "requests": 2,
                    "input_tokens": 7,
                    "output_tokens": 9,
                    "latency_ms": 20,
                }
            },
        }
        record = {
            "role": "architecture",
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "attempts": 1,
            "input_tokens": 3,
            "output_tokens": 5,
            "latency_ms": 10,
            "status": "success",
            "attempt_trace": [
                {
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "requests": 1,
                    "latency_ms": 10,
                }
            ],
        }
        update = model_state_update(state, [record])
        self.assertEqual(100, len(update["model_routing_history"]))
        self.assertEqual(record, update["model_route"])
        usage = update["model_usage"]["deepseek/deepseek-v4-flash"]
        self.assertEqual(3, usage["requests"])
        self.assertEqual(10, usage["input_tokens"])
        self.assertEqual(14, usage["output_tokens"])
        self.assertEqual(30, usage["latency_ms"])
        self.assertEqual(24, update["tokens"])


if __name__ == "__main__":
    unittest.main()
