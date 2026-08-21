import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.unity_compile_tool import UnityCompileTool
from tools.unity_snapshot import UnitySnapshotBuilder, UnitySnapshotError
from tools.unity_worker_client import LocalUnityWorkerClient, UnityWorkerClientError
from tools.unity_worker_contract import build_job_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNITY_PATH = r"D:\Unity\Hub\Unity_Editor\2022.3.62f2c1\Editor\Unity.exe"
DEFAULT_PROJECT_PATH = r"D:\Unity\Unity_Project\CodingAgentTest"
DEFAULT_WORKER_STATE_PATH = PROJECT_ROOT.parent / "runtime-state" / "unity-worker"
INTEGRITY_CODES = {
    "ARTIFACT_HASH_MISMATCH", "ARTIFACT_MISSING", "ARTIFACT_SIZE_MISMATCH",
    "RESULT_EXPIRED", "RESULT_REPLAYED", "STALE_ATTEMPT", "WRONG_GATE",
    "WRONG_SNAPSHOT", "WORKER_RESULT_INVALID",
}


def compile_generated_sources():
    """Legacy direct compiler entry point retained for old integrations."""
    compiler = UnityCompileTool(
        unity_path=os.getenv("UNITY_EDITOR_PATH", DEFAULT_UNITY_PATH),
        project_path=os.getenv("UNITY_TEST_PROJECT_PATH", DEFAULT_PROJECT_PATH),
        source_path=os.path.realpath(
            os.path.abspath(os.getenv("GENERATED_SOURCE_PATH", PROJECT_ROOT / "generated"))
        ),
    )
    return compiler.compile()


def default_snapshot_builder():
    test_root = Path(
        os.getenv("GENERATED_TEST_SOURCE_PATH", PROJECT_ROOT / "generated_tests")
    ).resolve()
    return UnitySnapshotBuilder(
        project_path=os.getenv("UNITY_TEST_PROJECT_PATH", DEFAULT_PROJECT_PATH),
        production_source_path=os.getenv("GENERATED_SOURCE_PATH", PROJECT_ROOT / "generated"),
        editmode_test_source_path=test_root / "EditMode",
        playmode_test_source_path=test_root / "PlayMode",
    )


def default_worker_client():
    if os.getenv("UNITY_WORKER_MODE", "local").strip().lower() == "remote":
        from tools.remote_unity_worker_client import RemoteUnityWorkerClient

        return RemoteUnityWorkerClient(
            endpoint=os.getenv("UNITY_REMOTE_WORKER_URL", ""),
            credential=os.getenv("UNITY_REMOTE_WORKER_CREDENTIAL", ""),
            download_directory=(
                Path(os.getenv("UNITY_WORKER_STATE_PATH", DEFAULT_WORKER_STATE_PATH))
                / "remote-artifacts"
            ),
            timeout_seconds=_timeout_seconds(),
        )
    return LocalUnityWorkerClient(
        state_path=os.getenv("UNITY_WORKER_STATE_PATH", DEFAULT_WORKER_STATE_PATH),
        unity_path=os.getenv("UNITY_EDITOR_PATH", DEFAULT_UNITY_PATH),
        python_executable=sys.executable,
        client_timeout_seconds=_timeout_seconds(),
        network_isolation_enforced=_environment_bool(
            "UNITY_WORKER_NETWORK_ISOLATION_ENFORCED", False
        ),
    )


def dispatch_gate(state, gate, worker_client, clock=None):
    snapshot = state.get("unity_snapshot", {}) or {}
    history_key = {
        "compile": "compile_history",
        "editmode": "editmode_test_history",
        "playmode": "playmode_test_history",
    }[gate]
    attempt = len(state.get(history_key, []) or []) + 1
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    timeout = _timeout_seconds()
    job = build_job_manifest(
        thread_id=str(state.get("thread_id", "")),
        attempt=attempt,
        gate=gate,
        snapshot_sha256=snapshot.get("snapshot_sha256", ""),
        unity_version=snapshot.get("unity_version", ""),
        package_manifest_sha256=snapshot.get("package_manifest_sha256", ""),
        timeout_seconds=timeout,
        expires_at=(now + timedelta(seconds=timeout + 60))
        .astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        network_policy={
            "mode": os.getenv("UNITY_WORKER_NETWORK_MODE", "disabled").strip(),
            "allowlist": _network_allowlist(),
        },
        files=snapshot.get("files", []),
        display_name=f"{state.get('thread_id', '')}:{gate}:{attempt}",
    )
    try:
        active_client = worker_client or default_worker_client()
        accepted = active_client.dispatch(job, snapshot.get("archive_path", ""))
        result = _validation_result(gate, accepted["result"])
        job_record = {
            **job,
            "status": accepted["result"].get("status", ""),
            "failure_owner": accepted["result"].get("failure_owner", ""),
            "error_code": accepted["result"].get("error_code", ""),
            "result_sha256": accepted.get("result_sha256", ""),
        }
    except (UnityWorkerClientError, RuntimeError, OSError, ValueError) as error:
        code = str(getattr(error, "code", "WORKER_DISPATCH_FAILED"))
        result = _client_failure(gate, snapshot.get("snapshot_sha256", ""), code)
        job_record = {
            **job,
            "status": "rejected",
            "failure_owner": result["failure_owner"],
            "error_code": code,
            "result_sha256": "",
        }
    return result, job_record


def unity_compile_agent(
    state, *, snapshot_builder=None, worker_client=None,
    snapshot_directory=None, clock=None,
):
    """Build one pinned snapshot and dispatch its compile gate."""
    snapshot_root = Path(
        snapshot_directory
        or Path(os.getenv("UNITY_WORKER_STATE_PATH", DEFAULT_WORKER_STATE_PATH)) / "snapshots"
    ).resolve()
    try:
        snapshot = state.get("unity_snapshot", {}) or {}
        if not snapshot:
            builder = snapshot_builder or default_snapshot_builder()
            archive_path = snapshot_root / f"snapshot-{uuid.uuid4().hex}.unityjob"
            snapshot = builder.build(archive_path)
        result, job_record = dispatch_gate(
            {**state, "unity_snapshot": snapshot}, "compile", worker_client, clock=clock
        )
    except (UnitySnapshotError, OSError, ValueError) as error:
        snapshot = {}
        result = _client_failure("compile", "", "SNAPSHOT_BUILD_FAILED")
        result["errors"][0]["message"] = str(error)[:500]
        job_record = {}

    history = list(state.get("compile_history", []) or [])
    history.append(_history_entry("compile", result, len(history) + 1))
    jobs = list(state.get("unity_worker_jobs", []) or [])
    if job_record:
        jobs.append(job_record)
    return {
        "current_agent": "unity_compiler",
        "unity_worker_mode": os.getenv("UNITY_WORKER_MODE", "local"),
        "unity_snapshot": snapshot,
        "unity_worker_jobs": jobs[-100:],
        "compile_result": result,
        "compile_history": history,
    }


def unity_snapshot_agent(state, *, snapshot_builder=None, snapshot_directory=None):
    """Create the immutable bundle in its own checkpointed graph node."""
    builder = snapshot_builder or default_snapshot_builder()
    snapshot_root = Path(
        snapshot_directory
        or Path(os.getenv("UNITY_WORKER_STATE_PATH", DEFAULT_WORKER_STATE_PATH)) / "snapshots"
    ).resolve()
    archive_path = snapshot_root / f"snapshot-{uuid.uuid4().hex}.unityjob"
    try:
        snapshot = builder.build(archive_path)
        return {
            "current_agent": "unity_snapshot",
            "unity_worker_mode": os.getenv("UNITY_WORKER_MODE", "local"),
            "unity_snapshot": snapshot,
            "unity_validation_status": "snapshot_ready",
        }
    except (UnitySnapshotError, OSError, ValueError) as error:
        return {
            "current_agent": "unity_snapshot",
            "unity_snapshot": {},
            "unity_validation_status": "blocked",
            "compile_result": {
                **_client_failure("compile", "", "SNAPSHOT_BUILD_FAILED"),
                "errors": [{
                    "code": "SNAPSHOT_BUILD_FAILED",
                    "message": str(error)[:500],
                    "test": "",
                }],
            },
        }


def _validation_result(gate, worker_result):
    evidence = worker_result.get("evidence", {}) or {}
    summary = evidence.get("test_summary", {}) or {}
    status = worker_result.get("status", "")
    owner = worker_result.get("failure_owner", "")
    code = worker_result.get("error_code", "")
    success = status == "passed"
    if gate != "compile" and success and int(summary.get("total", 0) or 0) < 1:
        success, owner, code = False, "test", "NO_TESTS_EXECUTED"
    system_error = not success and owner not in {"code", "test"}
    compiler_errors = list(evidence.get("compiler_errors", []) or [])
    errors = compiler_errors or ([] if success else [{
        "code": code or "UNITY_VALIDATION_FAILED",
        "message": str(worker_result.get("message", "") or code)[:500],
        "test": "",
    }])
    return {
        "success": success,
        "system_error": system_error,
        "gate": gate,
        "platform": {"compile": "Compile", "editmode": "EditMode", "playmode": "PlayMode"}[gate],
        "summary": dict(summary),
        "errors": errors[:200],
        "error_code": "" if success else code,
        "failure_owner": "" if success else owner,
        "worker_status": status,
        "worker_id": worker_result.get("worker_id", ""),
        "job_id": worker_result.get("job_id", ""),
        "attempt": worker_result.get("attempt", 0),
        "snapshot_sha256": worker_result.get("snapshot_sha256", ""),
        "cleanup": dict(worker_result.get("cleanup", {}) or {}),
    }


def _client_failure(gate, snapshot_sha256, code):
    owner = "integrity" if code in INTEGRITY_CODES else (
        "timeout" if "TIMEOUT" in code else "worker"
    )
    return {
        "success": False, "system_error": True, "gate": gate,
        "platform": {"compile": "Compile", "editmode": "EditMode", "playmode": "PlayMode"}[gate],
        "summary": {},
        "errors": [{"code": code, "message": code, "test": ""}],
        "error_code": code, "failure_owner": owner, "worker_status": "rejected",
        "worker_id": "", "job_id": "", "attempt": 0,
        "snapshot_sha256": snapshot_sha256, "cleanup": {},
    }


def _history_entry(gate, result, round_number):
    return {
        "round": round_number, "gate": gate,
        "success": result.get("success", False),
        "system_error": result.get("system_error", False),
        "error_code": result.get("error_code", ""),
        "failure_owner": result.get("failure_owner", ""),
        "error_count": len(result.get("errors", []) or []),
        "job_id": result.get("job_id", ""),
        "snapshot_sha256": result.get("snapshot_sha256", ""),
        "summary": result.get("summary", {}),
    }


def _timeout_seconds():
    try:
        value = int(os.getenv("UNITY_WORKER_TIMEOUT_SECONDS", "900"))
    except ValueError:
        value = 900
    return min(max(value, 1), 3600)


def _network_allowlist():
    return sorted({
        item.strip().lower()
        for item in os.getenv("UNITY_WORKER_NETWORK_ALLOWLIST", "").split(",")
        if item.strip()
    })


def _environment_bool(name, default):
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes"}
