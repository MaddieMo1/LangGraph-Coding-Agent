import unittest
from types import SimpleNamespace

from ui.approval_app import (
    ApprovalController,
    build_approval_app,
    format_review_meta,
    format_status_card,
    patch_choices,
    select_patch_diff,
)


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
        self.decisions = []

    @staticmethod
    def new_thread_id():
        return "thread-1"

    def invoke(self, state, thread_id):
        self.started_state = state
        self.started_thread_id = thread_id
        return {"__interrupt__": [FakeInterrupt(self.request)]}

    def get_state(self, thread_id):
        self.loaded_thread_id = thread_id
        return SimpleNamespace(
            values={
                "approval_status": "pending",
                "approval_request": self.request,
            }
        )

    def resume(self, thread_id, decision):
        self.decisions.append((thread_id, decision))
        return self.resume_result


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

    def test_duplicate_decision_is_reported_without_error(self):
        self.runtime.resume_result = {
            "approval_status": "approved",
            "approval_result": {"already_decided": True},
        }

        view = self.controller.accept_all("thread-1", "bundle-1", "")

        self.assertEqual("approved", view["status"])
        self.assertIn("已处理", view["message"])

    def test_review_helpers_localize_approval_context(self):
        choices = patch_choices(pending_request()["patches"])

        self.assertEqual(("A.cs · 新增", "patch-a"), choices[0])
        self.assertIn("Coder 初始提案", format_review_meta("coder", 2))
        self.assertIn("2 个文件", format_review_meta("coder", 2))
        self.assertIn("等待审批", format_status_card("pending", "请检查变更"))

    def test_status_card_escapes_runtime_errors(self):
        rendered = format_status_card("conflicted", "<script>unsafe</script>")

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_builds_approval_workspace(self):
        app = build_approval_app(self.controller)

        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
