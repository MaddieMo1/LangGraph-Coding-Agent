import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from memory.approval_audit import (
    GENESIS_HASH,
    ApprovalAuditError,
    ApprovalAuditStore,
    project_fingerprint,
)


class ApprovalAuditStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository_root = self.root / "generated-repository"
        self.repository_root.mkdir()
        self.path = self.root / "approval_audit.jsonl"
        self.project_id = project_fingerprint(self.repository_root)
        self.fixed_time = datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc)

    def store(self, project_id=None):
        return ApprovalAuditStore(
            self.path,
            project_id or self.project_id,
            clock=lambda: self.fixed_time,
        )

    def event(self, event_type="proposal_created", **overrides):
        event = {
            "event_type": event_type,
            "thread_id": "thread-1",
            "bundle_id": "bundle-1",
            "source": "coder",
            "actor_id": "alice",
            "role": "approver",
            "files": [
                {
                    "file": "SafeCounter.cs",
                    "operation": "modify",
                    "before_hash": "a" * 64,
                    "after_hash": "b" * 64,
                }
            ],
            "action": "review",
            "result": "recorded",
            "note": "looks safe",
            "error_code": "",
        }
        event.update(overrides)
        return event

    def test_project_fingerprint_is_stable_without_exposing_the_path(self):
        first = project_fingerprint(self.repository_root)
        second = project_fingerprint(str(self.repository_root / "."))

        self.assertEqual(first, second)
        self.assertEqual(64, len(first))
        self.assertNotIn(str(self.repository_root), first)

    def test_appends_and_reloads_a_verified_chain(self):
        store = self.store()

        first = store.append(self.event())
        second = store.append(self.event("proposal_viewed", action="view"))

        self.assertEqual(1, first["sequence"])
        self.assertEqual(GENESIS_HASH, first["previous_hash"])
        self.assertEqual(2, second["sequence"])
        self.assertEqual(first["event_hash"], second["previous_hash"])
        self.assertEqual(
            [first, second],
            self.store().list_events(),
        )
        self.assertTrue(self.store().verify())

    def test_writes_one_canonical_json_line_per_event(self):
        stored = self.store().append(self.event())

        raw = self.path.read_text(encoding="utf-8")
        self.assertEqual(1, len(raw.splitlines()))
        self.assertEqual(stored, json.loads(raw))
        self.assertTrue(raw.endswith("\n"))
        self.assertNotIn(": ", raw)

    def test_records_a_utc_timestamp_and_required_metadata(self):
        stored = self.store().append(self.event())

        self.assertEqual("2026-08-17T09:30:00+00:00", stored["recorded_at"])
        self.assertEqual(1, stored["schema_version"])
        self.assertEqual(self.project_id, stored["project_id"])
        self.assertEqual(32, len(stored["event_id"]))
        self.assertEqual(64, len(stored["event_hash"]))

    def test_rejects_a_chain_from_another_project(self):
        self.store().append(self.event())
        other_project = "f" * 64

        with self.assertRaises(ApprovalAuditError) as raised:
            self.store(other_project)

        self.assertEqual("AUDIT_PROJECT_MISMATCH", raised.exception.code)

    def test_rejects_malformed_or_truncated_json(self):
        for raw in ("not-json\n", '{"schema_version":1'):
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ApprovalAuditError) as raised:
                    self.store()
                self.assertEqual("AUDIT_CHAIN_INVALID", raised.exception.code)

    def test_rejects_sequence_and_payload_tampering(self):
        first = self.store().append(self.event())
        original = self.path.read_text(encoding="utf-8")

        for field, value in (("sequence", 4), ("bundle_id", "changed")):
            with self.subTest(field=field):
                tampered = dict(first)
                tampered[field] = value
                self.path.write_text(
                    json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaises(ApprovalAuditError) as raised:
                    self.store()
                self.assertEqual("AUDIT_CHAIN_INVALID", raised.exception.code)
                self.path.write_text(original, encoding="utf-8")

    def test_append_revalidates_and_never_overwrites_external_tampering(self):
        store = self.store()
        stored = store.append(self.event())
        tampered = dict(stored)
        tampered["result"] = "forged"
        raw = json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n"
        self.path.write_text(raw, encoding="utf-8")

        with self.assertRaises(ApprovalAuditError):
            store.append(self.event("proposal_viewed", action="view"))

        self.assertEqual(raw, self.path.read_text(encoding="utf-8"))

    def test_rejects_invalid_event_metadata_before_creating_a_file(self):
        invalid_events = [
            self.event(event_type="unknown"),
            self.event(thread_id=""),
            self.event(files="SafeCounter.cs"),
            self.event(files=[{"file": "../Secret.cs"}]),
        ]

        for event in invalid_events:
            with self.subTest(event=event):
                with self.assertRaises(ApprovalAuditError) as raised:
                    self.store().append(event)
                self.assertEqual("AUDIT_EVENT_INVALID", raised.exception.code)
                self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
