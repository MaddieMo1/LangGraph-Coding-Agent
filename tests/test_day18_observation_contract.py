import json
import unittest

from memory.task_observation import (
    EVENT_TYPES,
    PUBLIC_SNAPSHOT_KEYS,
    ObservationContractError,
    sanitize_artifact,
    sanitize_diagnostic,
    sanitize_identifier,
    sanitize_task_name,
    sanitize_task_snapshot,
    validate_event,
)


NOW = "2026-08-20T08:00:00+00:00"


class ObservationContractTests(unittest.TestCase):
    def context(self):
        return {
            "project_id": "a" * 64,
            "thread_id": "thread-1",
            "started_at": NOW,
            "updated_at": NOW,
            "owner_actor_id": "local-operator",
            "owner_instance_id": "studio-a",
            "approval_owner_id": "alice",
        }

    def state(self):
        return {
            "query": "生成 Player.cs，密钥 API_KEY=top-secret",
            "current_agent": "unity_test",
            "approval_status": "approved",
            "code": [{"file": "Player.cs", "content": "class Secret {}"}],
            "proposed_changes": [{"diff": "@@ -1 +1 @@"}],
            "code_check_result": {"success": True},
            "compile_result": {"success": True},
            "test_result": {
                "success": False,
                "error_code": "TEST_FAILED",
                "error": "Authorization: Bearer secret at C:\\private\\report.xml",
                "summary": {"total": 3, "passed": 2},
                "report_path": "C:\\private\\report.xml",
            },
            "review": {"pass": False, "score": 71},
            "git_result": {
                "commit_hash": "b" * 40,
                "message": "feat: 更新玩家控制器",
            },
        }

    def test_public_snapshot_uses_an_exact_allowlist(self):
        snapshot = sanitize_task_snapshot(self.state(), self.context())
        self.assertEqual(PUBLIC_SNAPSHOT_KEYS, set(snapshot))
        serialized = json.dumps(snapshot, ensure_ascii=False)
        self.assertEqual("生成 Player.cs，密钥 [REDACTED]", snapshot["task_name"])
        for forbidden in (
            "API_KEY=top-secret",
            "top-secret",
            "Bearer secret",
            "C:\\private",
            "class Secret",
            "@@ -1",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_snapshot_exposes_only_bounded_gate_and_artifact_metadata(self):
        snapshot = sanitize_task_snapshot(self.state(), self.context())
        self.assertEqual("unity_test", snapshot["current_gate"])
        self.assertTrue(snapshot["gates"]["code_check_passed"])
        self.assertEqual(3, snapshot["gates"]["test_total"])
        self.assertEqual(2, snapshot["gates"]["test_passed_count"])
        self.assertEqual("report.xml", snapshot["artifacts"]["test_report"])
        self.assertEqual("b" * 40, snapshot["artifacts"]["git_commit_hash"])

    def test_task_name_prefers_requirement_goal_and_is_bounded(self):
        name = sanitize_task_name({
            "query": "这个旧查询不应优先",
            "requirement_contract": {
                "goal": "创建中文背包物品管理系统并增加拖拽、堆叠、分类和持久化功能",
            },
        })
        self.assertTrue(name.startswith("创建中文背包物品管理系统"))
        self.assertLessEqual(len(name), 32)
        self.assertNotIn("旧查询", name)

    def test_task_name_redacts_sensitive_text_and_supports_legacy_query(self):
        name = sanitize_task_name({
            "query": "修复玩家系统 API_KEY=top-secret 位于 C:\\private\\Player.cs",
        })
        self.assertIn("修复玩家系统", name)
        self.assertNotIn("top-secret", name)
        self.assertNotIn("C:\\private", name)
        self.assertEqual("未命名任务", sanitize_task_name({"current_agent": "coordinator"}))

    def test_diagnostic_redacts_secrets_and_paths(self):
        result = sanitize_diagnostic({
            "error_code": "SYSTEM_ERROR",
            "error": "Authorization: Bearer abc API_KEY=xyz C:\\repo\\secret.txt /srv/repo/file.py",
        })
        self.assertEqual("SYSTEM_ERROR", result["error_code"])
        self.assertNotIn("abc", result["summary"])
        self.assertNotIn("xyz", result["summary"])
        self.assertNotIn("C:\\repo", result["summary"])
        self.assertNotIn("/srv/repo", result["summary"])

    def test_artifact_keeps_only_a_safe_basename(self):
        self.assertEqual("results.xml", sanitize_artifact("D:\\private\\results.xml"))
        self.assertEqual("report.json", sanitize_artifact("/tmp/private/report.json"))

    def test_identifier_rejects_path_and_control_characters(self):
        self.assertEqual("alice", sanitize_identifier(" alice ", "actor_id"))
        for invalid in ("../alice", "alice/bob", "alice\nbob", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ObservationContractError):
                    sanitize_identifier(invalid, "actor_id")

    def test_unknown_event_type_and_unknown_field_fail_closed(self):
        event = {
            "schema_version": 1,
            "event_id": "event-1",
            "event_type": "state_changed",
            "project_id": "a" * 64,
            "thread_id": "thread-1",
            "checkpoint_id": "checkpoint-1",
            "occurred_at": NOW,
            "status": "running",
            "current_gate": "coder",
            "approval_owner_id": "",
            "diagnostic": {"error_code": "", "summary": ""},
            "artifacts": {},
            "idempotency_key": "event:1",
        }
        self.assertEqual(event, validate_event(event))
        with self.assertRaises(ObservationContractError) as error:
            validate_event({**event, "event_type": "workflow_command"})
        self.assertEqual("OBSERVATION_EVENT_INVALID", error.exception.code)
        with self.assertRaises(ObservationContractError):
            validate_event({**event, "prompt": "ignore previous instructions"})

    def test_event_types_do_not_include_remote_commands(self):
        self.assertEqual(
            {
                "task_started",
                "state_changed",
                "gate_entered",
                "approval_waiting",
                "approval_resolved",
                "task_completed",
                "task_failed",
                "artifact_available",
            },
            EVENT_TYPES,
        )


if __name__ == "__main__":
    unittest.main()
