import argparse
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tools.unity_snapshot import UnitySnapshotError, safe_extract_snapshot
from tools.unity_worker_contract import (
    build_worker_result,
    validate_job_manifest,
    validate_worker_result,
)
from worker.unity_executor import EMPTY_TEST_SUMMARY, UnityExecutor


_JOB_ID = re.compile(r"^[0-9a-f]{64}$")


class UnityWorkerRunError(ValueError):
    pass


def run_worker_job(
    job_path,
    bundle_path,
    result_path,
    *,
    unity_path,
    worker_id,
    network_isolation_enforced=False,
    executor=None,
    state_path=None,
    keep_sandbox=False,
    clock=None,
):
    clock = clock or (lambda: datetime.now(timezone.utc))
    job = _read_job(job_path)
    started_at = _timestamp(clock())
    marker_path = _write_running_marker(state_path, job, started_at)
    sandbox_root = Path(tempfile.mkdtemp(prefix="coding-agent-unity-worker-"))
    sandbox_project = sandbox_root / "Project"
    outcome = None
    sandbox_removed = False

    try:
        policy = job.get("network_policy", {})
        if policy.get("mode") in {"disabled", "allowlist"} and not network_isolation_enforced:
            outcome = _failure(
                "rejected",
                "infrastructure",
                "NETWORK_ISOLATION_UNAVAILABLE",
                "Worker cannot enforce the requested network policy.",
            )
        else:
            snapshot = safe_extract_snapshot(bundle_path, sandbox_project)
            mismatch = _snapshot_mismatch(job, snapshot)
            if mismatch:
                outcome = _failure(
                    "rejected",
                    "integrity",
                    "SNAPSHOT_MISMATCH",
                    "Snapshot does not match the pinned worker job.",
                )
            else:
                active_executor = executor or UnityExecutor(unity_path)
                outcome = active_executor.execute(job, str(sandbox_project))
    except UnitySnapshotError:
        outcome = _failure(
            "rejected",
            "integrity",
            "SNAPSHOT_INVALID",
            "Snapshot validation failed.",
        )
    except Exception:
        outcome = _failure(
            "crashed",
            "worker",
            "WORKER_CRASHED",
            "Unity worker execution crashed.",
            process_stopped=False,
        )
    finally:
        if not keep_sandbox:
            shutil.rmtree(sandbox_root, ignore_errors=True)
            sandbox_removed = not sandbox_root.exists()

    finished_at = _timestamp(clock())
    result = build_worker_result(
        job,
        status=outcome["status"],
        worker_id=worker_id,
        started_at=started_at,
        finished_at=finished_at,
        failure_owner=outcome["failure_owner"],
        error_code=outcome["error_code"],
        evidence=outcome["evidence"],
        artifacts=outcome["artifacts"],
        cleanup={
            "sandbox_removed": sandbox_removed,
            "process_stopped": bool(outcome.get("process_stopped", True)),
        },
        message=outcome.get("message", ""),
    )
    _atomic_write_json(result_path, result)
    _complete_running_marker(marker_path)
    return result


def recover_incomplete_jobs(state_path, *, worker_id, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    state_path = Path(state_path).resolve()
    running_path = state_path / "running"
    results_path = state_path / "results"
    if not running_path.is_dir():
        return []
    results_path.mkdir(parents=True, exist_ok=True)
    recovered = []
    for marker_path in sorted(running_path.glob("*.json")):
        job_id = marker_path.stem
        if not _JOB_ID.fullmatch(job_id):
            continue
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            job = marker.get("job")
            if validate_job_manifest(job) or job.get("job_id") != job_id:
                continue
            result_path = results_path / f"{job_id}.json"
            if result_path.is_file():
                existing = json.loads(result_path.read_text(encoding="utf-8"))
                if not validate_worker_result(job, existing, now=clock()):
                    marker_path.unlink(missing_ok=True)
                    continue
            result = build_worker_result(
                job,
                status="crashed",
                worker_id=worker_id,
                started_at=marker.get("started_at", _timestamp(clock())),
                finished_at=_timestamp(clock()),
                failure_owner="worker",
                error_code="WORKER_RESTARTED",
                evidence=_empty_evidence(),
                artifacts=[],
                cleanup={"sandbox_removed": False, "process_stopped": False},
                message="Worker restarted before the job produced an authoritative result.",
            )
            _atomic_write_json(result_path, result)
            marker_path.unlink(missing_ok=True)
            recovered.append(job_id)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return recovered


def _read_job(path):
    try:
        job = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnityWorkerRunError(f"unable to read worker job: {error}") from error
    errors = validate_job_manifest(job)
    if errors:
        raise UnityWorkerRunError("invalid worker job: " + "; ".join(errors))
    return job


def _snapshot_mismatch(job, snapshot):
    return any(
        (
            job.get(field) != snapshot.get(field)
            for field in (
                "snapshot_sha256",
                "unity_version",
                "package_manifest_sha256",
                "files",
            )
        )
    )


def _failure(status, owner, code, message, process_stopped=True):
    return {
        "status": status,
        "failure_owner": owner,
        "error_code": code,
        "evidence": _empty_evidence(),
        "artifacts": [],
        "message": message,
        "process_stopped": process_stopped,
    }


def _empty_evidence():
    return {"compiler_errors": [], "test_summary": dict(EMPTY_TEST_SUMMARY)}


def _write_running_marker(state_path, job, started_at):
    if not state_path:
        return None
    running_path = Path(state_path).resolve() / "running"
    running_path.mkdir(parents=True, exist_ok=True)
    marker_path = running_path / f"{job['job_id']}.json"
    _atomic_write_json(marker_path, {"job": job, "started_at": started_at})
    return marker_path


def _complete_running_marker(marker_path):
    if marker_path is not None:
        marker_path.unlink(missing_ok=True)


def _atomic_write_json(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _timestamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise UnityWorkerRunError("worker clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _bool_environment(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one pinned Unity worker job")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--job", required=True)
    run_parser.add_argument("--bundle", required=True)
    run_parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        result = run_worker_job(
            args.job,
            args.bundle,
            args.result,
            unity_path=os.getenv("UNITY_EDITOR_PATH", ""),
            worker_id=os.getenv("UNITY_WORKER_ID", "local-worker"),
            network_isolation_enforced=_bool_environment(
                "UNITY_WORKER_NETWORK_ISOLATION_ENFORCED"
            ),
            state_path=os.getenv("UNITY_WORKER_STATE_PATH") or None,
        )
        return 0 if result.get("status") == "passed" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
