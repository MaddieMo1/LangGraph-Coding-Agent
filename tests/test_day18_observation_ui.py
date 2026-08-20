import json
import unittest

import gradio as gr
from fastapi import APIRouter

from app import compose_application
from ui.observation_app import (
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
        self.assertIn("new EventSource", browser_code)
        self.assertIn("sessionStorage", browser_code)
        self.assertIn("tokenInput.value = ''", browser_code)
        self.assertNotIn("localStorage", browser_code)
        self.assertNotIn("?token=", browser_code)

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


if __name__ == "__main__":
    unittest.main()
