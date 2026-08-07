import os

from ui.approval_app import APPROVAL_CSS, ApprovalController, build_approval_app
from workflow.runtime import WorkflowRuntime


def configure_localhost_proxy_bypass():
    for name in ("NO_PROXY", "no_proxy"):
        entries = [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]
        for host in ("127.0.0.1", "localhost"):
            if host not in entries:
                entries.append(host)
        os.environ[name] = ",".join(entries)


def main():
    configure_localhost_proxy_bypass()
    database_path = os.getenv(
        "WORKFLOW_CHECKPOINT_PATH",
        os.path.join(os.path.dirname(__file__), "memory", "workflow_checkpoints.sqlite"),
    )
    runtime = WorkflowRuntime(database_path).open()
    demo = build_approval_app(ApprovalController(runtime))
    try:
        demo.launch(server_name="127.0.0.1", share=False, css=APPROVAL_CSS)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
