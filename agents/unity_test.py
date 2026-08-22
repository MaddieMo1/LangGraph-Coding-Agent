import os
from pathlib import Path

from agents.unity_compiler import (
    _history_entry,
    dispatch_gate,
)
from tools.unity_test_tool import UnityTestTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def unity_test_agent(state, *, worker_client=None, clock=None):
    """Run authoritative EditMode and PlayMode jobs on one pinned snapshot."""
    if not state.get("unity_snapshot"):
        return _legacy_unity_test_agent(state)

    editmode, edit_job = dispatch_gate(state, "editmode", worker_client, clock=clock)
    intermediate = {
        **state,
        "editmode_test_history": list(state.get("editmode_test_history", []) or [])
        + [_history_entry(
            "editmode", editmode,
            len(state.get("editmode_test_history", []) or []) + 1,
        )],
    }
    playmode, play_job = dispatch_gate(intermediate, "playmode", worker_client, clock=clock)
    edit_history = intermediate["editmode_test_history"]
    play_history = list(state.get("playmode_test_history", []) or [])
    play_history.append(_history_entry("playmode", playmode, len(play_history) + 1))
    aggregate = aggregate_test_results(editmode, playmode)
    legacy_history = list(state.get("test_history", []) or [])
    legacy_history.append({
        "round": len(legacy_history) + 1,
        "success": aggregate["success"],
        "system_error": aggregate["system_error"],
        "summary": aggregate["summary"],
        "snapshot_sha256": aggregate["snapshot_sha256"],
    })
    jobs = list(state.get("unity_worker_jobs", []) or []) + [edit_job, play_job]
    return {
        "current_agent": "unity_test",
        "editmode_test_result": editmode,
        "playmode_test_result": playmode,
        "editmode_test_history": edit_history,
        "playmode_test_history": play_history,
        "test_result": aggregate,
        "test_history": legacy_history,
        "unity_worker_jobs": jobs[-100:],
        "unity_validation_status": (
            "passed" if aggregate["success"]
            else "blocked" if aggregate["system_error"]
            else "failed"
        ),
        "agent_history": list(state.get("agent_history", []) or [])
        + ["Unity EditMode 与 PlayMode 验证完成"],
    }


def aggregate_test_results(editmode, playmode):
    results = (editmode or {}, playmode or {})
    snapshot_hashes = {item.get("snapshot_sha256", "") for item in results}
    same_snapshot = len(snapshot_hashes) == 1 and "" not in snapshot_hashes
    success = same_snapshot and all(item.get("success", False) for item in results)
    system_error = not same_snapshot or any(
        item.get("system_error", False) for item in results
    )
    failed = next((item for item in results if not item.get("success", False)), {})
    summary = {}
    for field in ("total", "passed", "failed", "skipped", "inconclusive"):
        summary[field] = sum(int(item.get("summary", {}).get(field, 0) or 0) for item in results)
    summary["duration"] = sum(
        float(item.get("summary", {}).get("duration", 0) or 0) for item in results
    )
    errors = []
    for item in results:
        for error in item.get("errors", []) or []:
            errors.append({**error, "platform": item.get("platform", "")})
    return {
        "success": success,
        "system_error": system_error,
        "platform": "EditMode+PlayMode",
        "summary": summary,
        "errors": errors[:200],
        "error_code": (
            "SNAPSHOT_MISMATCH" if not same_snapshot
            else "" if success else failed.get("error_code", "UNITY_TEST_FAILED")
        ),
        "failure_owner": (
            "integrity" if not same_snapshot else failed.get("failure_owner", "")
        ),
        "snapshot_sha256": next(iter(snapshot_hashes)) if same_snapshot else "",
        "platform_results": {
            "EditMode": editmode,
            "PlayMode": playmode,
        },
    }


def _legacy_unity_test_agent(state):
    """Allow old checkpoints to render/resume without satisfying Day19 Git gates."""
    tool = UnityTestTool(
        unity_path=os.getenv(
            "UNITY_EDITOR_PATH",
            r"D:\Unity\Hub\Unity_Editor\2022.3.62f2c1\Editor\Unity.exe",
        ),
        project_path=os.getenv(
            "UNITY_TEST_PROJECT_PATH", r"D:\Unity\Unity_Project\CodingAgentTest"
        ),
        production_source_path=os.getenv(
            "GENERATED_SOURCE_PATH", PROJECT_ROOT / "generated"
        ),
        test_source_path=os.getenv(
            "GENERATED_TEST_SOURCE_PATH", PROJECT_ROOT / "generated_tests"
        ),
    )
    result = tool.run()
    history = list(state.get("test_history", []) or [])
    history.append({
        "round": len(history) + 1,
        "success": result.get("success", False),
        "system_error": result.get("system_error", False),
        "summary": result.get("summary", {}),
    })
    return {
        "current_agent": "unity_test",
        "test_result": result,
        "test_history": history,
        "agent_history": list(state.get("agent_history", []) or []) + ["Unity Test完成"],
    }
