"""Deterministic projection from durable workflow state to public observation events."""

from memory.task_observation import (
    SCHEMA_VERSION,
    sanitize_task_snapshot,
    semantic_fingerprint,
)


class TaskObservationProjector:
    """Create a sanitized, idempotent projection without executing the graph."""

    def __init__(
        self,
        store,
        project_id,
        owner_actor_id="",
        owner_instance_id="",
    ):
        self.store = store
        self.project_id = project_id
        self.owner_actor_id = owner_actor_id
        self.owner_instance_id = owner_instance_id or store.get_or_create_instance_id()

    def project(
        self,
        thread_id,
        checkpoint_id,
        values,
        updated_at,
        started_at="",
        approval_owner_id="",
    ):
        previous = self.store.get_task(self.project_id, thread_id)
        context = {
            "project_id": self.project_id,
            "thread_id": thread_id,
            "started_at": started_at or (previous or {}).get("started_at") or updated_at,
            "updated_at": updated_at,
            "owner_actor_id": (previous or {}).get("owner_actor_id") or self.owner_actor_id,
            "owner_instance_id": (
                (previous or {}).get("owner_instance_id") or self.owner_instance_id
            ),
            "approval_owner_id": approval_owner_id,
        }
        snapshot = sanitize_task_snapshot(values, context)
        event_types = self._event_types(previous, snapshot)
        events = [
            self._event(event_type, checkpoint_id, snapshot)
            for event_type in event_types
        ]
        stored = self.store.append_projection(snapshot, events, checkpoint_id=checkpoint_id)
        return {"snapshot": snapshot, "events": events, **stored}

    def reconcile(self, **kwargs):
        return self.project(**kwargs)

    @staticmethod
    def _event_types(previous, snapshot):
        if previous is None:
            types = ["task_started"]
            if snapshot["current_gate"] != "idle":
                types.append("gate_entered")
            if snapshot["status"] == "waiting_approval":
                types.append("approval_waiting")
            if snapshot["status"] == "completed":
                types.append("task_completed")
            elif snapshot["status"] in {"failed", "rejected", "conflicted"}:
                types.append("task_failed")
            if any(snapshot["artifacts"].values()):
                types.append("artifact_available")
            return types

        types = []
        if previous["current_gate"] != snapshot["current_gate"]:
            types.append("gate_entered")
        if previous["status"] != "waiting_approval" and snapshot["status"] == "waiting_approval":
            types.append("approval_waiting")
        if previous["status"] == "waiting_approval" and snapshot["status"] != "waiting_approval":
            types.append("approval_resolved")
        if previous["status"] != "completed" and snapshot["status"] == "completed":
            types.append("task_completed")
        elif previous["status"] not in {"failed", "rejected", "conflicted"} and snapshot[
            "status"
        ] in {"failed", "rejected", "conflicted"}:
            types.append("task_failed")
        if previous["artifacts"] != snapshot["artifacts"] and any(snapshot["artifacts"].values()):
            types.append("artifact_available")
        if _meaningful_snapshot(previous) != _meaningful_snapshot(snapshot):
            types.append("state_changed")
        return types

    @staticmethod
    def _event(event_type, checkpoint_id, snapshot):
        semantic = {
            "event_type": event_type,
            "checkpoint_id": checkpoint_id,
            "status": snapshot["status"],
            "current_gate": snapshot["current_gate"],
            "approval_owner_id": snapshot["approval_owner_id"],
            "diagnostic": snapshot["diagnostic"],
            "artifacts": snapshot["artifacts"],
        }
        fingerprint = semantic_fingerprint(semantic)
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"event-{fingerprint[:32]}",
            "event_type": event_type,
            "project_id": snapshot["project_id"],
            "thread_id": snapshot["thread_id"],
            "checkpoint_id": checkpoint_id,
            "occurred_at": snapshot["updated_at"],
            "status": snapshot["status"],
            "current_gate": snapshot["current_gate"],
            "approval_owner_id": snapshot["approval_owner_id"],
            "diagnostic": snapshot["diagnostic"],
            "artifacts": snapshot["artifacts"],
            "idempotency_key": f"observation:{fingerprint}",
        }


def _meaningful_snapshot(snapshot):
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"started_at", "updated_at"}
    }
