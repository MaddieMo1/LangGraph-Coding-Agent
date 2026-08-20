import json
import unittest

import gradio as gr
from fastapi import APIRouter
from starlette.testclient import TestClient

from app import compose_application
from ui.observation_app import (
    OBSERVATION_CSS,
    OBSERVATION_HTML,
    OBSERVATION_JS,
    ObservationSettings,
    build_observation_app,
)


READ_TOKEN = "day18-read-only-token-with-at-least-32-chars"


class ObservationUiTests(unittest.TestCase):
    def test_observation_page_renders_the_read_only_status_fields(self):
        config = build_observation_app().get_config_file()
        rendered = json.dumps(config, ensure_ascii=False)
        for label in (
            "连接状态",
            "任务状态",
            "当前门禁",
            "任务所有者",
            "审批所有者",
            "在线观察者",
            "诊断摘要",
            "最终产物",
        ):
            self.assertIn(label, rendered)

    def test_observation_component_tree_has_no_workflow_mutation_controls(self):
        config = build_observation_app().get_config_file()
        types = {component["type"] for component in config["components"]}
        self.assertNotIn("button", types)
        rendered = (OBSERVATION_HTML + OBSERVATION_JS).lower()
        for forbidden in (
            "approve",
            "reject",
            "task-retry",
            "cancel-task",
            "continue-task",
            "abandon-task",
            "git push",
            "git merge",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_browser_code_uses_cookie_session_sse_and_forgets_the_read_token(self):
        browser_code = OBSERVATION_HTML + OBSERVATION_JS
        self.assertIn(".observation-login[hidden]", OBSERVATION_CSS)
        self.assertIn("new EventSource", browser_code)
        self.assertIn("sessionStorage", browser_code)
        self.assertIn("tokenInput.value = ''", browser_code)
        self.assertNotIn("localStorage", browser_code)
        self.assertNotIn("?token=", browser_code)

    def test_observation_header_and_login_feedback_use_explicit_contrast_colors(self):
        for expected_rule in (
            ".observation-header h1 { color: #f4f8ff !important; }",
            ".observation-header p { color: #b8c6d9 !important; }",
            ".observation-login input::placeholder { color: #9aabc0; opacity: 1; }",
            "#observation-login-error { min-height: 20px; margin-top: 8px; color: #ff9aa8 !important; }",
        ):
            self.assertIn(expected_rule, OBSERVATION_CSS)

    def test_observation_page_explains_token_source_and_styles_native_task_options(self):
        self.assertIn("OBSERVATION_READ_TOKEN", OBSERVATION_HTML)
        self.assertIn("请通过安全渠道获取", OBSERVATION_HTML)
        for expected_rule in (
            "#observation-task-select { width: 100%;",
            "color-scheme: dark;",
            "#observation-task-select option { background-color: #0d1b2d !important; color: #f4f8ff !important;",
            "#observation-task-select option:checked { background-color: #173451 !important; color: #ffffff !important;",
        ):
            self.assertIn(expected_rule, OBSERVATION_CSS)

    def test_task_selector_uses_readable_name_and_keeps_short_diagnostic_id(self):
        self.assertIn('task.task_name || "未命名任务"', OBSERVATION_JS)
        self.assertIn("task.thread_id.slice(0, 8)", OBSERVATION_JS)
        self.assertNotIn("task.current_gate} · ${task.thread_id", OBSERVATION_JS)

    def test_read_routes_are_registered_before_gradio_mounts(self):
        settings = ObservationSettings.from_environment({
            "OBSERVATION_ENABLED": "true",
            "OBSERVATION_READ_TOKEN": READ_TOKEN,
        })
        router = APIRouter()

        @router.get("/observe/tasks")
        def tasks():
            return []

        with gr.Blocks() as control:
            gr.Markdown("control")
        observation = build_observation_app()
        application = compose_application(
            control,
            observation_demo=observation,
            observation_router=router,
            settings=settings,
        )
        routes = application.routes
        included_index = next(
            index for index, route in enumerate(routes)
            if hasattr(route, "original_router")
            and "/observe/tasks" in {
                getattr(item, "path", "") for item in route.original_router.routes
            }
        )
        observation_index = next(
            index for index, route in enumerate(routes)
            if getattr(route, "path", "") == "/observe/ui"
        )
        root_index = next(
            index for index, route in enumerate(routes)
            if getattr(route, "path", None) == "" and not hasattr(route, "router")
        )
        self.assertLess(included_index, observation_index)
        self.assertLess(observation_index, root_index)

    def test_remote_client_can_only_reach_the_observation_surface(self):
        settings = ObservationSettings.from_environment({
            "OBSERVATION_ENABLED": "true",
            "OBSERVATION_READ_TOKEN": READ_TOKEN,
        })
        router = APIRouter()

        @router.get("/observe/tasks")
        def tasks():
            return []

        with gr.Blocks() as control:
            gr.Markdown("control")
        application = compose_application(
            control,
            observation_demo=build_observation_app(),
            observation_router=router,
            settings=settings,
        )

        remote = TestClient(application, client=("192.168.10.20", 50000))
        self.assertEqual(200, remote.get("/observe/tasks").status_code)
        self.assertEqual(403, remote.get("/").status_code)
        self.assertEqual(403, remote.get("/docs").status_code)

        local = TestClient(application, client=("127.0.0.1", 50000))
        self.assertEqual(200, local.get("/").status_code)


if __name__ == "__main__":
    unittest.main()
