import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import gradio as gr
import uvicorn

from memory.task_observation import TaskObservationStore
from ui.approval_app import (
    APPROVAL_CSS,
    APPROVAL_JS,
    ApprovalController,
    build_approval_app,
)
from ui.observation_app import (
    OBSERVATION_CSS,
    OBSERVATION_JS,
    ObservationReader,
    ObservationSettings,
    ObserverSessionStore,
    build_observation_app,
    create_observation_router,
)
from workflow.runtime import WorkflowRuntime
from workflow.task_observation import TaskObservationProjector


def configure_localhost_proxy_bypass():
    for name in ("NO_PROXY", "no_proxy"):
        entries = [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]
        for host in ("127.0.0.1", "localhost"):
            if host not in entries:
                entries.append(host)
        os.environ[name] = ",".join(entries)


def compose_application(
    control_demo,
    observation_demo=None,
    observation_router=None,
    settings=None,
):
    """Register read-only routes before Gradio mounts in one ASGI process."""

    settings = settings or ObservationSettings()
    application = FastAPI(title="LangGraph Unity Coding Agent")
    if settings.enabled and observation_router is not None and observation_demo is not None:
        application.include_router(observation_router)

        @application.get("/observe", include_in_schema=False)
        def observation_entry():
            return RedirectResponse("/observe/ui/")

        application = gr.mount_gradio_app(
            application,
            observation_demo,
            path="/observe/ui",
            server_name=settings.server_name,
            server_port=settings.server_port,
            footer_links=[],
            show_error=False,
            css=OBSERVATION_CSS,
            js=OBSERVATION_JS,
        )
    application = gr.mount_gradio_app(
        application,
        control_demo,
        path="/",
        server_name=(settings.server_name if settings.enabled else "127.0.0.1"),
        server_port=settings.server_port,
        footer_links=[],
        show_error=True,
        css=APPROVAL_CSS,
        js=APPROVAL_JS,
    )
    return application


def create_application(runtime, settings=None):
    settings = settings or ObservationSettings.from_environment()
    control_demo = build_approval_app(ApprovalController(runtime))
    if not settings.enabled:
        return compose_application(control_demo, settings=settings)

    project_id = runtime.workflow.approval_audit.project_id
    store = TaskObservationStore(runtime.database_path, project_id)
    sessions = ObserverSessionStore(runtime.database_path, project_id, settings)
    actor = runtime.workflow.approval_policy.actor
    runtime.observation_projector = TaskObservationProjector(
        store,
        project_id,
        owner_actor_id=actor.actor_id,
        owner_instance_id=settings.instance_id or store.get_or_create_instance_id(),
    )
    runtime.reconcile_observations()
    reader = ObservationReader(store, project_id, sessions)
    application = compose_application(
        control_demo,
        observation_demo=build_observation_app(),
        observation_router=create_observation_router(reader, sessions, settings),
        settings=settings,
    )
    application.state.observation_reader = reader
    application.state.observation_sessions = sessions
    return application


def main():
    configure_localhost_proxy_bypass()
    database_path = os.getenv(
        "WORKFLOW_CHECKPOINT_PATH",
        os.path.join(os.path.dirname(__file__), "memory", "workflow_checkpoints.sqlite"),
    )
    settings = ObservationSettings.from_environment()
    runtime = WorkflowRuntime(database_path).open()
    application = create_application(runtime, settings)
    host = settings.server_name if settings.enabled else "127.0.0.1"
    try:
        uvicorn.run(
            application,
            host=host,
            port=settings.server_port,
            ssl_certfile=settings.tls_certfile or None,
            ssl_keyfile=settings.tls_keyfile or None,
        )
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
