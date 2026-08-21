import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tools.unity_worker_contract import build_worker_result


class WorkerJobStore:
    """Worker-owned atomic metadata and artifact store."""

    def __init__(self, database_path, state_path):
        self.database_path = Path(database_path).resolve()
        self.state_path = Path(state_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database_path, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                CREATE TABLE IF NOT EXISTS worker_jobs (
                    job_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    gate TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT NOT NULL,
                    failure_owner TEXT NOT NULL,
                    job_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS worker_nonces (
                    nonce TEXT PRIMARY KEY,
                    expires_at TEXT NOT NULL
                );
                """
            )

    def close(self):
        with self._lock:
            self._connection.close()

    def claim_nonce(self, nonce, expires_at, now):
        with self._transaction() as connection:
            connection.execute("DELETE FROM worker_nonces WHERE expires_at < ?", (now,))
            try:
                connection.execute(
                    "INSERT INTO worker_nonces(nonce, expires_at) VALUES (?, ?)",
                    (nonce, expires_at),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def create_job(self, job, bundle_bytes, now):
        job_id = job["job_id"]
        job_path = self.job_path(job_id)
        job_path.mkdir(parents=True, exist_ok=False)
        bundle_path = job_path / "bundle.unityjob"
        try:
            _atomic_write_bytes(bundle_path, bundle_bytes)
            _atomic_write_json(job_path / "job.json", job)
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO worker_jobs(
                        job_id, thread_id, gate, attempt, snapshot_sha256,
                        status, error_code, failure_owner, job_json, result_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'queued', '', '', ?, '', ?, ?)
                    """,
                    (
                        job_id, job["thread_id"], job["gate"], job["attempt"],
                        job["snapshot_sha256"], _canonical_json(job), now, now,
                    ),
                )
        except Exception:
            for child in job_path.glob("*"):
                child.unlink(missing_ok=True)
            job_path.rmdir()
            raise
        return bundle_path

    def get_job(self, job_id):
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM worker_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def job_manifest(self, job_id):
        row = self.get_job(job_id)
        return json.loads(row["job_json"]) if row else None

    def update_status(self, job_id, status, now, error_code="", failure_owner=""):
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE worker_jobs
                SET status = ?, error_code = ?, failure_owner = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, error_code, failure_owner, now, job_id),
            )
        return cursor.rowcount == 1

    def complete(self, job_id, result, artifacts, now):
        job_path = self.job_path(job_id)
        artifacts_path = job_path / "artifacts"
        artifacts_path.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            _atomic_write_bytes(artifacts_path / name, content)
        _atomic_write_json(job_path / "result.json", result)
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE worker_jobs
                SET status = ?, error_code = ?, failure_owner = ?,
                    result_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    result.get("status", "crashed"), result.get("error_code", ""),
                    result.get("failure_owner", ""), _canonical_json(result), now, job_id,
                ),
            )

    def result(self, job_id):
        row = self.get_job(job_id)
        if not row or not row["result_json"]:
            return None
        return json.loads(row["result_json"])

    def artifact_path(self, job_id, name):
        return self.job_path(job_id) / "artifacts" / name

    def job_path(self, job_id):
        return self.state_path / "jobs" / job_id

    def recover_incomplete(self, worker_id, now):
        with self._lock:
            rows = self._connection.execute(
                "SELECT job_json FROM worker_jobs WHERE status IN ('queued', 'running', 'cancelling')"
            ).fetchall()
        recovered = []
        for row in rows:
            job = json.loads(row["job_json"])
            result = build_worker_result(
                job,
                status="crashed",
                worker_id=worker_id,
                started_at=now,
                finished_at=now,
                failure_owner="worker",
                error_code="WORKER_RESTARTED",
                evidence={
                    "compiler_errors": [],
                    "test_summary": {
                        "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                        "inconclusive": 0, "duration": 0.0,
                    },
                },
                artifacts=[],
                cleanup={"sandbox_removed": False, "process_stopped": False},
                message="Remote worker restarted before completion.",
            )
            self.complete(job["job_id"], result, {}, now)
            recovered.append(job["job_id"])
        return recovered

    def _transaction(self):
        return _Transaction(self._connection, self._lock)


class _Transaction:
    def __init__(self, connection, lock):
        self.connection = connection
        self.lock = lock

    def __enter__(self):
        self.lock.acquire()
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def __exit__(self, error_type, _error, _traceback):
        try:
            self.connection.execute("ROLLBACK" if error_type else "COMMIT")
        finally:
            self.lock.release()


def _atomic_write_json(path, value):
    _atomic_write_bytes(
        path, (_canonical_json(value) + "\n").encode("utf-8")
    )


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _atomic_write_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
