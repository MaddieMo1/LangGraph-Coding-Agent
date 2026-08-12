import unittest
from types import SimpleNamespace

from ui.approval_app import (
    APPROVAL_CSS,
    SHOW_TASK_CENTER_JS,
    TASK_CENTER_CARD_JS,
    TASK_CENTER_FILTER_LOADING_JS,
    TASK_LOADING_SLOT,
    ApprovalController,
    build_approval_app,
    format_decision_hint,
    format_git_result,
    format_module_lockup,
    format_progress_activity,
    format_repair_context,
    format_proposal_info,
    format_review_meta,
    format_selection_summary,
    format_saved_task_detail,
    format_status_card,
    format_task_choices,
    format_task_time,
    format_task_center_cards,
    format_task_center_detail,
    paginate_task_center,
    prepare_task_center,
    task_center_stats,
    task_center_action_label,
    repair_review_context,
    format_workflow_rail,
    patch_choices,
    select_patch_diff,
)
from ui.view_state import map_agent_state


def pending_request():
    return {
        "bundle_id": "bundle-1",
        "source": "coder",
        "status": "pending",
        "patches": [
            {
                "patch_id": "patch-a",
                "file": "A.cs",
                "operation": "create",
                "diff": "--- /dev/null\n+++ b/A.cs\n+class A {}",
            },
            {
                "patch_id": "patch-b",
                "file": "B.cs",
                "operation": "modify",
                "diff": "--- a/B.cs\n+++ b/B.cs\n+class B {}",
            },
        ],
    }


class FakeInterrupt:
    def __init__(self, value):
        self.value = value


class FakeRuntime:
    def __init__(self):
        self.request = pending_request()
        self.resume_result = {"approval_status": "approved", "approval_result": {}}
        self.archive_result = {
            "success": True,
            "status": "archived",
            "stash_commit": "d" * 40,
            "label": "coding-agent-recovery-thread1",
            "files": ["A.cs"],
        }
        self.decisions = []
        self.active_task = None
        self.new_thread_calls = 0

    def new_thread_id(self):
        self.new_thread_calls += 1
        return "thread-1"

    def find_active_task(self):
        return self.active_task

    def abandon_active_task(self, thread_id):
        self.abandoned_thread_id = thread_id
        self.active_task = None
        return {
            "success": True,
            "archive_result": {
                "success": True,
                "status": "archived",
                "files": ["A.cs"],
                "label": "coding-agent-abandoned-thread1",
                "stash_commit": "e" * 40,
            },
        }

    def invoke(self, state, thread_id):
        self.started_state = state
        self.started_thread_id = thread_id
        return {"__interrupt__": [FakeInterrupt(self.request)]}

    def stream(self, state, thread_id):
        self.started_state = state
        self.started_thread_id = thread_id
        yield {**state, "current_agent": "coordinator", "agent_history": ["Coordinator完成"]}
        yield {**state, "approval_status": "pending", "approval_request": self.request}

    def list_threads(self):
        return [
            {
                "thread_id": "thread-1",
                "query": "生成背包系统",
                "status": "pending",
                "current_agent": "human_approval",
                "updated_at": "2026-08-07T00:00:00Z",
            }
        ]

    def delete_thread(self, thread_id):
        self.deleted_thread_id = thread_id
        return {
            "success": True,
            "thread_id": thread_id,
            "deleted_checkpoints": 1,
            "deleted_writes": 1,
        }

    def delete_threads(self, thread_ids):
        self.deleted_thread_ids = list(thread_ids)
        return {"success": True, "thread_ids": list(thread_ids), "deleted_threads": len(thread_ids)}

    def get_state(self, thread_id):
        self.loaded_thread_id = thread_id
        return SimpleNamespace(
            values=getattr(
                self,
                "state_values",
                {
                    "approval_status": "pending",
                    "approval_request": self.request,
                },
            )
        )

    def resume(self, thread_id, decision):
        self.decisions.append((thread_id, decision))
        return self.resume_result

    def resume_stream(self, thread_id, decision):
        self.decisions.append((thread_id, decision))
        yield {
            "approval_status": "approved",
            "current_agent": "human_approval",
            "git_status": "prepared",
        }
        yield {
            "approval_status": "approved",
            "current_agent": "code_checker",
            "code_check_result": {"success": True},
            "git_status": "prepared",
        }
        yield {
            "approval_status": "approved",
            "current_agent": "finish_task",
            "code_check_result": {"success": True},
            "compile_result": {"success": True},
            "test_result": {"success": True},
            "review": {"pass": True},
            "git_status": "committed",
            "git_result": {"success": True, "commit_hash": "c" * 40},
        }

    def archive_dirty_worktree(self, thread_id):
        self.archived_thread_id = thread_id
        return self.archive_result

    def retry_test_generation_stream(self, thread_id):
        self.retried_thread_id = thread_id
        yield {
            **self.state_values,
            "current_agent": "test_generator",
            "test_generation_result": {"success": True, "attempts": 2},
        }
        yield {
            **self.state_values,
            "current_agent": "finish_task",
            "test_generation_result": {"success": True, "attempts": 2},
            "code_check_result": {"success": True},
            "compile_result": {"success": True},
            "test_result": {"success": True},
            "review": {"pass": True},
            "git_status": "committed",
            "git_result": {"success": True, "commit_hash": "c" * 40},
        }

    def retry_failed_repair_stream(self, thread_id):
        self.retried_repair_thread_id = thread_id
        yield {
            **self.state_values,
            "current_agent": "reviewer",
            "repair_count": 0,
            "repair_retry_result": {"success": True, "status": "retrying"},
        }
        yield {
            **self.state_values,
            "current_agent": "human_approval",
            "approval_status": "pending",
            "repair_count": 1,
            "proposal_source": "repair",
            "approval_request": pending_request(),
            "repair_retry_result": {"success": True, "status": "retrying"},
        }

    def retry_baseline_compile_stream(self, thread_id):
        self.retried_baseline_thread_id = thread_id
        yield {
            **self.state_values,
            "current_agent": "baseline_compiler",
            "baseline_compile_status": "passed",
            "baseline_compile_result": {"success": True},
            "baseline_retry_result": {"success": True, "status": "retrying"},
        }
        yield {
            **self.state_values,
            "current_agent": "coordinator",
            "baseline_compile_status": "passed",
            "baseline_compile_result": {"success": True},
            "baseline_retry_result": {"success": True, "status": "retrying"},
        }

    def continue_active_task_stream(self, thread_id):
        self.continued_thread_id = thread_id
        if getattr(self, "continue_error", ""):
            yield {
                **self.state_values,
                "continue_result": {
                    "success": False,
                    "error_code": "WORKFLOW_NODE_ERROR",
                    "error": self.continue_error,
                    "retryable": True,
                },
            }
            return
        yield {
            **self.state_values,
            "current_agent": "repair",
            "approval_status": "approved",
        }
        yield {
            **self.state_values,
            "current_agent": "human_approval",
            "approval_status": "pending",
            "approval_request": pending_request(),
        }


class ApprovalControllerTest(unittest.TestCase):
    def setUp(self):
        self.runtime = FakeRuntime()
        self.controller = ApprovalController(self.runtime)

    def test_start_creates_thread_and_pending_view(self):
        view = self.controller.start("生成背包系统")

        self.assertEqual("thread-1", view["thread_id"])
        self.assertEqual("pending", view["status"])
        self.assertEqual("生成背包系统", self.runtime.started_state["query"])
        self.assertEqual(["patch-a", "patch-b"], view["selected_patch_ids"])

    def test_start_stream_exposes_running_progress_before_approval(self):
        views = list(self.controller.start_stream("生成背包系统"))

        self.assertEqual("running", views[0]["status"])
        self.assertEqual("coordinator", views[1]["current_agent"])
        self.assertEqual("pending", views[-1]["status"])

    def test_start_redirects_to_the_existing_active_task(self):
        self.runtime.active_task = {
            "thread_id": "owner-thread",
            "can_continue": True,
            "can_abandon": True,
            "updated_at": "2026-08-11T08:00:00Z",
        }

        view = self.controller.start("不得创建的新任务")

        self.assertEqual("owner-thread", view["thread_id"])
        self.assertEqual(0, self.runtime.new_thread_calls)
        self.assertEqual("owner-thread", self.runtime.loaded_thread_id)
        self.assertTrue(view["active_task_lock"])

    def test_abandon_active_task_returns_to_the_new_task_entry(self):
        self.runtime.active_task = {
            "thread_id": "thread-1",
            "can_continue": True,
            "can_abandon": True,
            "updated_at": "2026-08-11T08:00:00Z",
        }

        view = self.controller.abandon_active_task("thread-1")

        self.assertEqual("thread-1", self.runtime.abandoned_thread_id)
        self.assertEqual("idle", view["status"])
        self.assertEqual("archived", view["git_status"])
        self.assertFalse(view["active_task_lock"])

    def test_reload_pending_thread(self):
        view = self.controller.reload("thread-1")

        self.assertEqual("thread-1", self.runtime.loaded_thread_id)
        self.assertEqual("bundle-1", view["bundle_id"])

    def test_selects_diff_by_patch_id(self):
        self.assertIn("B.cs", select_patch_diff(pending_request()["patches"], "patch-b"))
        self.assertEqual("", select_patch_diff(pending_request()["patches"], "missing"))

    def test_accept_all_uses_batch_mode(self):
        self.controller.accept_all("thread-1", "bundle-1", "looks good")

        self.assertEqual(
            {
                "bundle_id": "bundle-1",
                "action": "approve",
                "mode": "batch",
                "note": "looks good",
            },
            self.runtime.decisions[0][1],
        )

    def test_reject_all_does_not_send_patch_selection(self):
        self.controller.reject_all("thread-1", "bundle-1", "not safe")

        self.assertEqual("reject", self.runtime.decisions[0][1]["action"])
        self.assertNotIn("patch_ids", self.runtime.decisions[0][1])

    def test_advanced_selection_sends_selected_patch_ids(self):
        self.controller.accept_selected(
            "thread-1",
            "bundle-1",
            ["patch-b"],
            "only B",
        )

        decision = self.runtime.decisions[0][1]
        self.assertEqual("selected", decision["mode"])
        self.assertEqual(["patch-b"], decision["accepted_patch_ids"])

    def test_conflict_is_rendered_as_actionable_status(self):
        self.runtime.resume_result = {
            "approval_status": "conflicted",
            "approval_result": {"error": "source hash changed"},
        }

        view = self.controller.accept_all("thread-1", "bundle-1", "")

        self.assertEqual("conflicted", view["status"])
        self.assertIn("source hash changed", view["message"])

    def test_rejection_does_not_report_missing_git_commit_as_an_error(self):
        view = self.controller._view_from_result(
            "thread-1",
            {
                "current_agent": "finish_task",
                "approval_status": "rejected",
                "git_status": "prepared",
            },
        )

        self.assertEqual("rejected", view["status"])
        self.assertNotIn("未创建本地提交", view["message"])

    def test_accept_all_stream_exposes_apply_and_validation_progress(self):
        views = list(
            self.controller.accept_all_stream(
                "thread-1",
                "bundle-1",
                "looks good",
            )
        )

        self.assertEqual("validating", views[0]["status"])
        self.assertEqual("human_approval", views[0]["current_agent"])
        self.assertEqual("code_checker", views[2]["current_agent"])
        self.assertEqual("completed", views[-1]["status"])

    def test_duplicate_decision_is_reported_without_error(self):
        self.runtime.resume_result = {
            "approval_status": "approved",
            "approval_result": {"already_decided": True},
        }

        view = self.controller.accept_all("thread-1", "bundle-1", "")

        self.assertEqual("validating", view["status"])
        self.assertEqual("approved", view["approval_status"])
        self.assertIn("已处理", view["message"])

    def test_completed_view_exposes_local_git_commit(self):
        view = self.controller._view_from_result(
            "thread-1",
            {
                "approval_status": "approved",
                "git_status": "committed",
                "git_branch": "agent/abc123",
                "git_base_commit": "b" * 40,
                "git_result": {
                    "success": True,
                    "commit_hash": "c" * 40,
                    "message": "feat: 提交已批准的 AI 代码变更",
                },
            },
        )

        self.assertEqual("committed", view["git_status"])
        self.assertEqual("agent/abc123", view["git_branch"])
        self.assertEqual("c" * 40, view["git_commit_hash"])

    def test_git_error_is_actionable_in_view(self):
        view = self.controller._view_from_result(
            "thread-1",
            {
                "git_status": "error",
                "git_result": {
                    "success": False,
                    "error_code": "DIRTY_BASELINE",
                    "error": "repository must be clean",
                    "changed_files": ["A.cs", "New.cs"],
                },
            },
        )

        self.assertEqual("DIRTY_BASELINE", view["git_error_code"])
        self.assertIn("repository must be clean", view["message"])
        self.assertEqual(["A.cs", "New.cs"], view["git_changed_files"])
        self.assertTrue(view["can_archive_dirty"])

    def test_archiving_dirty_baseline_returns_to_a_clean_task_entry(self):
        view = self.controller.archive_dirty("thread-1")

        self.assertEqual("thread-1", self.runtime.archived_thread_id)
        self.assertEqual("idle", view["status"])
        self.assertEqual("archived", view["git_status"])
        self.assertEqual("d" * 40, view["git_stash_commit"])
        self.assertIn("安全归档", view["message"])
        self.assertFalse(view["can_archive_dirty"])

    def test_archiving_failure_keeps_the_current_failed_view(self):
        self.runtime.archive_result = {
            "success": False,
            "error_code": "DIRTY_BASELINE_DRIFT",
            "error": "worktree changed",
        }

        view = self.controller.archive_dirty("thread-1")

        self.assertEqual("failed", view["status"])
        self.assertIn("worktree changed", view["message"])

    def test_test_generator_parse_failure_offers_same_task_retry(self):
        view = self.controller._view_from_result(
            "thread-1",
            {
                "current_agent": "finish_task",
                "approval_status": "approved",
                "proposal_source": "coder",
                "git_status": "prepared",
                "test_generation_result": {
                    "success": False,
                    "errors": ["Unable to parse generated tests: truncated JSON"],
                },
            },
        )

        self.assertEqual("failed", view["status"])
        self.assertTrue(view["can_retry_test_generation"])
        self.assertIn("重试生成测试", view["recovery_hint"])

    def test_retry_test_generation_stream_preserves_the_same_thread(self):
        self.runtime.state_values = {
            "current_agent": "finish_task",
            "approval_status": "approved",
            "proposal_source": "coder",
            "git_status": "prepared",
            "test_generation_result": {
                "success": False,
                "error_code": "MODEL_OUTPUT_PARSE_ERROR",
                "retryable": True,
            },
        }

        views = list(self.controller.retry_test_generation_stream("thread-1"))

        self.assertEqual("thread-1", self.runtime.retried_thread_id)
        self.assertEqual("validating", views[0]["status"])
        self.assertEqual("test_generator", views[0]["current_agent"])
        self.assertEqual("completed", views[-1]["status"])

    def test_retry_progress_message_does_not_leak_into_repair_approval(self):
        view = self.controller._view_from_result(
            "thread-1",
            {
                "current_agent": "human_approval",
                "approval_status": "pending",
                "approval_request": pending_request(),
                "retry_result": {"success": True, "status": "retrying"},
            },
        )

        self.assertEqual("pending", view["status"])
        self.assertNotIn("重新生成 EditMode 测试", view["message"])

    def test_failed_repair_offers_same_task_repair_retry(self):
        view = self.controller._view_from_result(
            "thread-1",
            {
                "current_agent": "finish_task",
                "approval_status": "no_changes",
                "proposal_source": "repair",
                "git_status": "prepared",
                "approved_changes": [{"file": "A.cs", "after_hash": "hash"}],
                "repair_count": 3,
                "compile_result": {"success": False, "system_error": False},
            },
        )

        self.assertTrue(view["can_retry_failed_repair"])
        self.assertIn("重新修复当前任务", view["recovery_hint"])

    def test_retry_failed_repair_stream_preserves_thread_and_returns_to_approval(self):
        self.runtime.state_values = {
            "current_agent": "finish_task",
            "approval_status": "no_changes",
            "proposal_source": "repair",
            "git_status": "prepared",
            "git_branch": "agent/owner",
            "approved_changes": [{"file": "A.cs", "after_hash": "hash"}],
            "repair_count": 3,
            "compile_result": {"success": False, "system_error": False},
        }

        views = list(self.controller.retry_failed_repair_stream("thread-1"))

        self.assertEqual("thread-1", self.runtime.retried_repair_thread_id)
        self.assertEqual("validating", views[0]["status"])
        self.assertEqual("reviewer", views[0]["current_agent"])
        self.assertEqual("pending", views[-1]["status"])

    def test_active_failed_repair_shows_retry_and_abandon_actions(self):
        self.runtime.state_values = {
            "current_agent": "finish_task",
            "approval_status": "no_changes",
            "proposal_source": "repair",
            "git_status": "prepared",
            "approved_changes": [{"file": "A.cs", "after_hash": "hash"}],
            "repair_count": 3,
            "compile_result": {"success": False, "system_error": False},
        }
        self.runtime.active_task = {
            "thread_id": "thread-1",
            "can_continue": False,
            "can_retry_repair": True,
            "can_abandon": True,
            "updated_at": "2026-08-11T09:50:00Z",
        }

        view = self.controller.active_task_view()
        config = build_approval_app(self.controller, view).get_config_file()
        components = {
            component.get("props", {}).get("elem_id"): component.get("props", {})
            for component in config["components"]
        }

        self.assertTrue(components["retry-failed-repair"]["visible"])
        self.assertTrue(components["abandon-active-task"]["visible"])

    def test_baseline_system_failure_offers_same_task_retry(self):
        self.runtime.state_values = {
            "query": "new task",
            "current_agent": "finish_task",
            "git_status": "prepared",
            "baseline_compile_status": "failed",
            "baseline_compile_result": {
                "success": False,
                "system_error": True,
                "errors": [
                    {
                        "code": "UNITY_LICENSE_UNAVAILABLE",
                        "message": "Unity Editor 许可证不可用",
                    }
                ],
            },
        }
        self.runtime.active_task = {
            "thread_id": "thread-1",
            "can_continue": False,
            "can_retry_repair": False,
            "can_retry_baseline": True,
            "can_abandon": True,
            "updated_at": "2026-08-12T02:05:00Z",
        }

        view = self.controller.active_task_view()
        config = build_approval_app(self.controller, view).get_config_file()
        components = {
            component.get("props", {}).get("elem_id"): component.get("props", {})
            for component in config["components"]
        }

        self.assertTrue(view["can_retry_baseline_compile"])
        self.assertIn("许可证", view["message"])
        self.assertTrue(components["retry-baseline-compile"]["visible"])

    def test_retry_baseline_compile_preserves_the_same_thread(self):
        self.runtime.state_values = {
            "current_agent": "finish_task",
            "git_status": "prepared",
            "baseline_compile_status": "failed",
            "baseline_compile_result": {"success": False, "system_error": True},
        }
        self.runtime.active_task = {
            "thread_id": "thread-1",
            "can_continue": False,
            "can_retry_repair": False,
            "can_retry_baseline": True,
            "can_abandon": True,
            "updated_at": "2026-08-12T02:05:00Z",
        }

        views = list(self.controller.retry_baseline_compile_stream("thread-1"))

        self.assertEqual("thread-1", self.runtime.retried_baseline_thread_id)
        self.assertEqual("baseline_compiler", views[0]["current_agent"])
        self.assertEqual("coordinator", views[-1]["current_agent"])

    def test_continue_active_task_stream_resumes_the_saved_workflow(self):
        self.runtime.state_values = {
            "current_agent": "reviewer",
            "approval_status": "approved",
            "proposal_source": "repair",
            "git_status": "prepared",
        }
        self.runtime.active_task = {
            "thread_id": "thread-1",
            "can_continue": True,
            "can_retry_repair": False,
            "can_abandon": True,
            "updated_at": "2026-08-11T10:11:00Z",
        }

        views = list(self.controller.continue_active_task_stream("thread-1"))

        self.assertEqual("thread-1", self.runtime.continued_thread_id)
        self.assertEqual("repair", views[1]["current_agent"])
        self.assertEqual("pending", views[-1]["status"])

    def test_continue_node_error_finishes_loading_with_a_retryable_message(self):
        self.runtime.state_values = {
            "current_agent": "reviewer",
            "approval_status": "approved",
            "proposal_source": "coder",
            "git_status": "prepared",
        }
        self.runtime.continue_error = "repair: [Errno 22] Invalid argument"
        self.runtime.active_task = {
            "thread_id": "thread-1",
            "can_continue": True,
            "can_retry_repair": False,
            "can_abandon": True,
            "updated_at": "2026-08-12T01:00:00Z",
        }

        views = list(self.controller.continue_active_task_stream("thread-1"))

        self.assertEqual(2, len(views))
        self.assertIn("继续任务失败", views[-1]["message"])
        self.assertIn("Invalid argument", views[-1]["message"])
        self.assertTrue(views[-1]["can_continue_active"])

    def test_view_state_maps_each_user_visible_mode(self):
        cases = [
            ({"current_agent": "git_prepare"}, "preflight"),
            ({}, "idle"),
            ({"current_agent": "coder"}, "running"),
            ({"approval_status": "pending"}, "pending"),
            ({"current_agent": "unity_compiler"}, "validating"),
            ({"current_agent": "finish_task", "git_status": "committed"}, "completed"),
            ({"current_agent": "finish_task", "baseline_compile_status": "failed"}, "failed"),
            ({"approval_status": "rejected"}, "rejected"),
            ({"approval_status": "conflicted"}, "conflicted"),
        ]

        for state, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, map_agent_state(state)["mode"])

    def test_failed_view_state_identifies_gate_and_never_reports_completed(self):
        view_state = map_agent_state(
            {
                "current_agent": "finish_task",
                "approval_status": "error",
                "approval_result": {"error": "invalid approval bundle"},
                "git_status": "prepared",
            }
        )

        self.assertEqual("failed", view_state["mode"])
        self.assertEqual("human_approval", view_state["failed_gate"])
        self.assertEqual("approval", view_state["failure_kind"])
        self.assertIn("invalid approval bundle", view_state["error_summary"])
        self.assertNotIn("approve_all", view_state["available_actions"])

    def test_failed_view_exposes_context_and_requires_a_new_task(self):
        view = self.controller._view_from_result(
            "thread-1",
            {
                "query": "生成背包系统",
                "current_agent": "finish_task",
                "project_context_status": "success",
                "project_context": {
                    "project": {"name": "CodingAgentTest"},
                    "modules": [{"name": "Inventory"}],
                },
                "dependency_graph_status": "success",
                "dependency_graph": {"summary": {"nodes": 7, "edges": 4}},
                "memory_status": "success",
                "memory_context": {"matched_error_codes": ["CS0246"]},
                "compile_result": {"success": False, "errors": [{"message": "missing type"}]},
                "compile_history": [{"round": 1, "success": False}],
                "repair_count": 2,
                "repair_history": [{"round": 1}, {"round": 2}],
                "git_status": "prepared",
            },
        )

        self.assertEqual("failed", view["status"])
        self.assertEqual("CodingAgentTest", view["project_name"])
        self.assertEqual("1 modules", view["project_summary"])
        self.assertEqual("7 nodes · 4 edges", view["dependency_summary"])
        self.assertEqual("CS0246", view["memory_summary"])
        self.assertEqual("2 rounds", view["repair_summary"])
        self.assertFalse(view["resumable"])
        self.assertIn("发起新任务", view["recovery_hint"])

    def test_pending_view_state_exposes_only_approval_actions(self):
        view_state = map_agent_state({"approval_status": "pending"})

        self.assertEqual(
            ["approve_all", "approve_selected", "reject"],
            view_state["available_actions"],
        )
        self.assertTrue(view_state["show_review"])
        self.assertTrue(view_state["show_decision_bar"])

    def test_git_result_panel_escapes_repository_values(self):
        rendered = format_git_result(
            {
                "git_status": "prepared",
                "git_branch": "agent/<unsafe>",
                "git_base_commit": "b" * 40,
                "git_commit_hash": "",
                "git_commit_message": "",
                "git_error_code": "",
                "git_error": "",
                "git_changed_files": ["<unsafe>.cs"],
            }
        )

        self.assertIn("prepared", rendered)
        self.assertIn("agent/&lt;unsafe&gt;", rendered)
        self.assertNotIn("agent/<unsafe>", rendered)
        self.assertIn("&lt;unsafe&gt;.cs", rendered)

    def test_review_helpers_localize_approval_context(self):
        choices = patch_choices(pending_request()["patches"])

        self.assertEqual(("A.cs · 新增", "patch-a"), choices[0])
        self.assertIn("Coder 初始提案", format_review_meta("coder", 2))
        self.assertIn("2 个文件", format_review_meta("coder", 2))
        self.assertIn("等待审批", format_status_card("pending", "请检查变更"))

    def test_repair_review_explains_why_another_approval_is_required(self):
        result = {
            "proposal_source": "repair",
            "repair_count": 2,
            "approval_history": [{"status": "approved"}, {"status": "approved"}],
            "code_check_result": {"success": False, "errors": [{"message": "type mismatch"}]},
            "compile_result": {"success": False, "errors": [{"message": "CS0019 mismatch"}]},
            "repair_result": {
                "round": 2,
                "actions": [
                    {
                        "success": True,
                        "files": ["InventoryManager.cs"],
                        "root": {
                            "error_code": "CS0019",
                            "description": "int 与 string 物品 ID 类型不一致",
                            "source_file": "InventoryItem.cs",
                            "target_file": "InventoryManager.cs",
                            "fix_action": {
                                "details": "统一物品 ID 为 string",
                            },
                        },
                    }
                ],
            },
        }

        context = repair_review_context(result)
        rendered = format_repair_context(context)

        self.assertTrue(context["visible"])
        self.assertEqual(2, context["round"])
        self.assertEqual(3, context["approval_sequence"])
        self.assertEqual(["静态检查", "Unity 编译"], context["failed_gates"])
        self.assertIn("CS0019", rendered)
        self.assertIn("int 与 string 物品 ID 类型不一致", rendered)
        self.assertIn("InventoryItem.cs", rendered)
        self.assertIn("统一物品 ID 为 string", rendered)
        self.assertIn("第 2 轮 Repair", format_review_meta("repair", 1, context))

    def test_coder_review_does_not_render_repair_context(self):
        context = repair_review_context({"proposal_source": "coder"})

        self.assertFalse(context["visible"])
        self.assertEqual("", format_repair_context(context))

    def test_repair_context_escapes_checkpoint_text(self):
        rendered = format_repair_context(
            {
                "visible": True,
                "round": 1,
                "approval_sequence": 2,
                "failed_gates": ["Unity 编译"],
                "error_codes": ["CS0019"],
                "reasons": ["<script>unsafe</script>"],
                "files": ["<unsafe>.cs"],
                "strategies": ["replace <type>"],
            }
        )

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;unsafe&gt;.cs", rendered)

    def test_status_card_escapes_runtime_errors(self):
        rendered = format_status_card("conflicted", "<script>unsafe</script>")

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn('role="status"', rendered)
        self.assertIn('aria-live="polite"', rendered)

    def test_pending_workflow_highlights_review_stage(self):
        rendered = format_workflow_rail("pending")

        self.assertIn("02", rendered)
        self.assertIn("审阅变更", rendered)
        self.assertIn("is-active", rendered)

    def test_failed_validation_keeps_apply_complete_and_marks_validation_error(self):
        rendered = format_workflow_rail(
            "failed",
            "finish_task",
            approval_status="approved",
            failed_gate="unity_compiler",
        )

        self.assertIn(
            'workflow-step is-complete"><span class="stage-index">03',
            rendered,
        )
        self.assertIn(
            'workflow-step is-error"><span class="stage-index">04',
            rendered,
        )

    def test_topbar_module_title_follows_the_current_workflow_state(self):
        self.assertIn("审阅变更", format_module_lockup("pending"))
        self.assertIn("应用与验证", format_module_lockup("validating"))
        self.assertIn("执行失败", format_module_lockup("failed"))

    def test_failed_activity_names_the_failed_gate_instead_of_completion(self):
        rendered = format_progress_activity(
            "failed",
            "finish_task",
            ["Reviewer Agent完成"],
            failed_gate="unity_compiler",
        )

        self.assertIn("编译项目失败", rendered)
        self.assertNotIn("完成任务", rendered)

    def test_proposal_info_summarizes_patch_operations(self):
        rendered = format_proposal_info("coder", "thread-1", pending_request()["patches"])

        self.assertIn("Coder 初始提案", rendered)
        self.assertIn("thread-1", rendered)
        self.assertIn("1 新增", rendered)
        self.assertIn("1 修改", rendered)

    def test_decision_hint_changes_after_approval(self):
        self.assertIn("等待你的审批决策", format_decision_hint("pending"))
        self.assertIn("审批已处理", format_decision_hint("approved"))

    def test_task_history_and_selection_summary_are_human_readable(self):
        choices = format_task_choices(self.controller.list_tasks())

        self.assertIn("生成背包系统", choices[0][0])
        self.assertEqual("thread-1", choices[0][1])
        self.assertIn("2 / 5", format_selection_summary(["a", "b"], 5))

    def test_saved_task_choice_is_compact_and_detail_keeps_full_context(self):
        tasks = self.controller.list_tasks()
        choices = format_task_choices(tasks)
        detail = format_saved_task_detail("thread-1", tasks)

        self.assertNotIn("thread-1", choices[0][0])
        self.assertLessEqual(len(choices[0][0]), 45)
        self.assertIn("thread-1", detail)
        self.assertIn("2026-08-07 08:00", detail)

    def test_delete_saved_task_requires_confirmation(self):
        result = self.controller.delete_saved_task("thread-1", False)

        self.assertFalse(result["success"])
        self.assertFalse(hasattr(self.runtime, "deleted_thread_id"))

    def test_delete_saved_task_calls_runtime_after_confirmation(self):
        result = self.controller.delete_saved_task("thread-1", True)

        self.assertTrue(result["success"])
        self.assertEqual("thread-1", self.runtime.deleted_thread_id)

    def test_task_center_pins_active_task_and_sorts_remaining_by_update_time(self):
        tasks = [
            {"thread_id": "old", "query": "old", "status": "completed", "updated_at": "2026-08-01T00:00:00Z"},
            {"thread_id": "active", "query": "active", "status": "pending", "updated_at": "2026-07-01T00:00:00Z"},
            {"thread_id": "new", "query": "new", "status": "failed", "updated_at": "2026-08-02T00:00:00Z"},
        ]

        prepared = prepare_task_center(tasks, active_thread_id="active")

        self.assertEqual(["active", "new", "old"], [item["thread_id"] for item in prepared])
        self.assertTrue(prepared[0]["is_active"])

    def test_task_center_stats_and_cards_expose_required_information(self):
        tasks = [
            {"thread_id": "a", "query": "active", "status": "pending", "current_agent": "human_approval", "updated_at": "2026-08-01T00:00:00Z", "repair_count": 2, "is_active": True},
            {"thread_id": "b", "query": "failed", "status": "failed", "error": "compile failed", "updated_at": "2026-08-02T00:00:00Z", "is_active": False},
            {"thread_id": "c", "query": "done", "status": "completed", "updated_at": "2026-08-03T00:00:00Z", "is_active": False},
        ]

        stats = task_center_stats(tasks)
        cards = format_task_center_cards(tasks, ["b"])
        detail = format_task_center_detail("b", tasks)

        self.assertEqual({"all": 3, "active": 1, "attention": 1, "completed": 1}, stats)
        self.assertIn("Repair 2 轮", cards)
        self.assertIn("disabled", cards)
        self.assertIn("task-card-selected", cards)
        self.assertIn("compile failed", detail)
        self.assertEqual("进入审批", task_center_action_label("pending"))
        self.assertEqual("查看结果", task_center_action_label("completed"))

    def test_controller_batch_delete_delegates_all_selected_threads(self):
        result = self.controller.delete_saved_tasks(["thread-1", "thread-2"])

        self.assertTrue(result["success"])
        self.assertEqual(["thread-1", "thread-2"], self.runtime.deleted_thread_ids)

    def test_task_history_appends_shanghai_execution_time(self):
        choices = format_task_choices(self.controller.list_tasks())

        self.assertTrue(choices[0][0].startswith("08-07 08:00"))
        self.assertEqual("2026-08-07 08:00", format_task_time("2026-08-07T00:00:00Z"))
        self.assertEqual("时间未知", format_task_time("invalid"))

    def test_builds_approval_workspace(self):
        app = build_approval_app(self.controller)

        self.assertIsNotNone(app)

    def test_task_center_components_keep_workspace_and_global_status_available(self):
        task_center_css = APPROVAL_CSS.split("#task-center-view {", 1)[1].split("}", 1)[0]
        self.assertNotIn("display: none", task_center_css)
        config = build_approval_app(self.controller).get_config_file()
        components = {
            component.get("props", {}).get("elem_id"): component.get("props", {})
            for component in config["components"]
        }

        self.assertIn("topbar-status", components)
        self.assertIn("topbar-context", components)
        self.assertIn("primary-navigation", components)
        self.assertIn("workspace-grid", components)
        self.assertIn("task-center-view", components)
        self.assertFalse(components["task-center-view"]["visible"])
        self.assertEqual(components["workspace-nav"]["variant"], "primary")
        self.assertEqual(components["task-center-nav"]["variant"], "secondary")
        self.assertIn("task-detail-drawer", components)
        self.assertIn("task-delete-confirm", components)

    def test_task_center_and_drawer_force_dark_component_surfaces(self):
        self.assertIn("#task-center-cards .html-container", APPROVAL_CSS)
        self.assertIn("#task-center-view .loading", APPROVAL_CSS)
        self.assertIn("--block-background-fill: #091320", APPROVAL_CSS)
        self.assertIn("#task-detail-content", APPROVAL_CSS)
        self.assertIn("--block-background-fill: #091525", APPROVAL_CSS)
        self.assertNotIn("#primary-navigation button:first-child", APPROVAL_CSS)
        self.assertIn("#primary-navigation button.primary", APPROVAL_CSS)
        self.assertIn("#task-selection-summary", APPROVAL_CSS)
        self.assertIn("background: transparent !important", APPROVAL_CSS)

    def test_task_center_pagination_limits_each_page_to_ten(self):
        tasks = [{"thread_id": f"task-{index}"} for index in range(23)]

        first, first_page, total_pages = paginate_task_center(tasks, 1)
        last, last_page, _ = paginate_task_center(tasks, 99)

        self.assertEqual(len(first), 10)
        self.assertEqual(first_page, 1)
        self.assertEqual(total_pages, 3)
        self.assertEqual(len(last), 3)
        self.assertEqual(last_page, 3)

    def test_task_center_has_page_selection_and_navigation_controls(self):
        config = build_approval_app(self.controller).get_config_file()
        component_ids = {
            component.get("props", {}).get("elem_id") for component in config["components"]
        }

        self.assertIn("task-select-page", component_ids)
        self.assertIn("task-page-previous", component_ids)
        self.assertIn("task-page-info", component_ids)
        self.assertIn("task-page-next", component_ids)

    def test_task_center_uses_local_skeletons_for_delayed_content(self):
        self.assertIn(".task-local-loader", APPROVAL_CSS)
        self.assertIn("task-loader-shimmer", APPROVAL_CSS)
        self.assertIn("#task-center-view.task-client-visible", APPROVAL_CSS)
        self.assertIn("正在加载任务列表", SHOW_TASK_CENTER_JS)
        self.assertIn("removeAttribute('hidden')", SHOW_TASK_CENTER_JS)
        self.assertIn("setProperty('display', 'flex', 'important')", SHOW_TASK_CENTER_JS)
        self.assertIn("正在加载任务详情", TASK_CENTER_CARD_JS)
        self.assertIn("task-detail-loading-host", TASK_CENTER_CARD_JS)
        self.assertIn("task-center-loading-overlay", SHOW_TASK_CENTER_JS)
        self.assertIn(".task-loading-slot", SHOW_TASK_CENTER_JS)
        self.assertIn("data-task-loader", SHOW_TASK_CENTER_JS)
        self.assertIn("12000", SHOW_TASK_CENTER_JS)
        self.assertIn(".task-loading-slot", TASK_CENTER_CARD_JS)
        self.assertIn("加载超时，请重试", TASK_CENTER_CARD_JS)
        self.assertIn("task-loading-slot", TASK_LOADING_SLOT)
        self.assertIn(".task-card-open:hover", APPROVAL_CSS)

    def test_task_center_removes_outer_and_status_control_borders(self):
        task_center_css = APPROVAL_CSS.split("#task-center-view,", 1)[1].split("}", 1)[0]
        status_wrap_css = APPROVAL_CSS.split("#task-center-status .wrap {", 1)[1].split("}", 1)[0]
        status_control_css = APPROVAL_CSS.split(
            '#task-center-status [role="combobox"],', 1
        )[1].split("}", 1)[0]

        self.assertIn("border: none !important", task_center_css)
        self.assertIn("outline: none !important", task_center_css)
        self.assertIn("border: 0 !important", status_wrap_css)
        self.assertIn("background: transparent !important", status_wrap_css)
        self.assertIn("border: 1px solid var(--deck-line) !important", status_control_css)
        self.assertIn("box-shadow: none !important", status_control_css)

    def test_task_center_status_and_refresh_use_consistent_dark_controls(self):
        self.assertIn("button#task-center-refresh", APPROVAL_CSS)
        self.assertIn("#task-center-refresh button", APPROVAL_CSS)
        self.assertIn("#task-center-refresh button:hover", APPROVAL_CSS)
        self.assertIn("background: #0b1626 !important", APPROVAL_CSS)
        self.assertIn("border-color: var(--deck-cyan) !important", APPROVAL_CSS)
        self.assertIn("min-height: 44px !important", APPROVAL_CSS)
        self.assertIn("padding: 0 14px !important", APPROVAL_CSS)

    def test_task_center_matches_workspace_width_and_aligns_filter_controls(self):
        task_center_css = APPROVAL_CSS.split("#task-center-view,", 1)[1].split("}", 1)[0]
        filter_css = APPROVAL_CSS.split(
            "#task-center-filters > .form {", 1
        )[1].split("}", 1)[0]

        self.assertIn("width: 100% !important", task_center_css)
        self.assertIn("max-width: none !important", task_center_css)
        self.assertIn("margin: 0 !important", task_center_css)
        self.assertIn("border-radius: 0 !important", task_center_css)
        self.assertIn("display: grid !important", filter_css)
        self.assertIn("grid-template-columns: minmax(0, 3fr)", filter_css)
        self.assertIn("align-items: end !important", filter_css)
        self.assertIn("width: 100% !important", filter_css)
        self.assertIn("max-width: none !important", filter_css)
        self.assertIn("#task-center-refresh {\n    align-self: end !important", APPROVAL_CSS)
        self.assertNotIn("margin-top: 27px", APPROVAL_CSS)
        self.assertIn("#task-center-search input", APPROVAL_CSS)
        self.assertIn("height: 44px !important", APPROVAL_CSS)

    def test_task_center_loading_hosts_do_not_add_root_layout_gaps(self):
        loading_host_css = APPROVAL_CSS.split(
            "#task-center-loading-host,", 1
        )[1].split("}", 1)[0]

        self.assertIn("position: fixed !important", loading_host_css)
        self.assertIn("min-height: 0 !important", loading_host_css)
        self.assertIn("margin: 0 !important", loading_host_css)

    def test_task_center_status_filter_has_local_loading_feedback(self):
        self.assertIn("task-center-loading-host", TASK_CENTER_FILTER_LOADING_JS)
        self.assertIn(".task-loading-slot", TASK_CENTER_FILTER_LOADING_JS)
        self.assertIn("正在筛选任务列表", TASK_CENTER_FILTER_LOADING_JS)
        self.assertIn("data-task-loader", TASK_CENTER_FILTER_LOADING_JS)
        self.assertIn("12000", TASK_CENTER_FILTER_LOADING_JS)

    def test_saved_task_sidebar_manager_is_hidden_in_favor_of_task_center(self):
        config = build_approval_app(self.controller).get_config_file()
        components = {
            component.get("props", {}).get("elem_id"): component.get("props", {})
            for component in config["components"]
        }

        self.assertFalse(components["recovery-drawer"]["visible"])
        self.assertIn("open-task-center", components)
        self.assertIn("task-center-cards", components)

    def test_idle_layout_hides_review_and_decision_surfaces(self):
        config = build_approval_app(self.controller).get_config_file()
        components = {
            component.get("props", {}).get("elem_id"): component.get("props", {})
            for component in config["components"]
        }

        self.assertTrue(components["task-entry-panel"]["visible"])
        self.assertFalse(components["execution-panel"]["visible"])
        self.assertFalse(components["review-workspace-shell"]["visible"])
        self.assertFalse(components["right-inspector"]["visible"])
        self.assertFalse(components["decision-bar"]["visible"])

    def test_pending_layout_exposes_only_review_surfaces(self):
        pending_view = self.controller.start("生成背包系统")
        config = build_approval_app(self.controller, pending_view).get_config_file()
        components = {
            component.get("props", {}).get("elem_id"): component.get("props", {})
            for component in config["components"]
        }

        self.assertFalse(components["task-entry-panel"]["visible"])
        self.assertFalse(components["execution-panel"]["visible"])
        self.assertTrue(components["review-workspace-shell"]["visible"])
        self.assertTrue(components["proposal-card"]["visible"])
        self.assertFalse(components["git-card"]["visible"])
        self.assertTrue(components["note-card"]["visible"])
        self.assertTrue(components["decision-bar"]["visible"])

    def test_page_scrolls_and_drawer_titles_remain_readable(self):
        self.assertIn('overflow-y: auto', APPROVAL_CSS)
        self.assertIn('height: auto !important', APPROVAL_CSS)
        self.assertIn('#new-task-drawer > button *', APPROVAL_CSS)
        self.assertIn('color: #c2d0e0 !important', APPROVAL_CSS)

    def test_loading_and_disabled_selection_states_keep_dark_surfaces(self):
        self.assertIn('--background-fill-primary: #081321', APPROVAL_CSS)
        self.assertIn('#new-task-drawer .wrap.default', APPROVAL_CSS)
        self.assertIn('label:has(input:checked:disabled)', APPROVAL_CSS)
        self.assertIn('#git-card .styler', APPROVAL_CSS)

    def test_responsive_and_keyboard_accessibility_contract(self):
        self.assertIn('@media (max-width: 980px)', APPROVAL_CSS)
        self.assertIn(':focus-visible', APPROVAL_CSS)
        self.assertIn('outline: 2px solid var(--deck-cyan)', APPROVAL_CSS)
        self.assertIn('@media (forced-colors: active)', APPROVAL_CSS)
        self.assertIn('@media (prefers-reduced-motion: reduce)', APPROVAL_CSS)
        self.assertIn('min-height: 44px', APPROVAL_CSS)

    def test_diff_uses_a_fixed_internal_scroll_viewport(self):
        self.assertIn('#diff-view {', APPROVAL_CSS)
        self.assertIn('height: clamp(360px, 58vh, 620px) !important', APPROVAL_CSS)
        self.assertIn('#diff-view .cm-scroller', APPROVAL_CSS)
        self.assertIn('overflow: auto !important', APPROVAL_CSS)

    def test_active_lock_and_diff_wrappers_follow_the_dark_single_scroll_contract(self):
        self.assertIn('#active-task-lock {', APPROVAL_CSS)
        self.assertIn('#active-task-lock .html-container', APPROVAL_CSS)
        self.assertIn('background: var(--deck-surface) !important', APPROVAL_CSS)
        self.assertIn('#diff-view .code_wrap', APPROVAL_CSS)
        self.assertIn('overflow: hidden !important', APPROVAL_CSS)

    def test_repair_context_html_keeps_the_dark_transparent_surface(self):
        self.assertIn('#repair-context-info {', APPROVAL_CSS)
        self.assertIn('#repair-context-info .html-container', APPROVAL_CSS)
        self.assertIn('#repair-context-info .prose', APPROVAL_CSS)
        self.assertIn('#repair-context-info .prose > div', APPROVAL_CSS)
        self.assertIn('#repair-context-info .repair-review-card', APPROVAL_CSS)
        self.assertIn('--block-background-fill: transparent', APPROVAL_CSS)

    def test_repair_context_disables_gradio_default_prose_surface(self):
        pending_view = self.controller.reload("thread-1")
        pending_view["source"] = "repair"
        pending_view["repair_context"] = {
            "visible": True,
            "round": 1,
            "approval_sequence": 2,
            "failed_gates": ["Unity 编译"],
            "error_codes": ["CS0122"],
            "reasons": ["访问级别错误"],
            "files": ["GroundClickManager.cs"],
            "strategies": ["修改声明处 API"],
        }

        config = build_approval_app(self.controller, pending_view).get_config_file()
        component = next(
            item
            for item in config["components"]
            if item.get("props", {}).get("elem_id") == "repair-context-info"
        )

        self.assertFalse(component["props"]["apply_default_css"])
        self.assertFalse(component["props"]["container"])
        self.assertIn('background: transparent !important', APPROVAL_CSS)


if __name__ == "__main__":
    unittest.main()
