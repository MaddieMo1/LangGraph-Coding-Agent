import os
import re
from dataclasses import dataclass


ACTOR_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")


@dataclass(frozen=True)
class ApprovalActor:
    actor_id: str
    role: str


class ApprovalPermissionError(PermissionError):
    def __init__(self):
        self.code = "APPROVAL_PERMISSION_DENIED"
        super().__init__("approval permission denied")


class ApprovalPolicy:
    ROLE_CAPABILITIES = {
        "viewer": {
            "approval.read",
            "audit.read",
            "audit.export",
        },
        "reviewer": {
            "approval.read",
            "approval.review",
            "audit.read",
            "audit.export",
        },
        "approver": {
            "approval.read",
            "approval.review",
            "approval.decide",
            "audit.read",
            "audit.export",
        },
        "operator": {
            "approval.read",
            "audit.read",
            "audit.export",
            "task.operate",
        },
    }

    def __init__(self, actor):
        if not isinstance(actor, ApprovalActor):
            raise TypeError("approval actor is invalid")
        if actor.role not in self.ROLE_CAPABILITIES:
            raise ValueError("approval actor role is invalid")
        self.actor = actor

    @classmethod
    def from_environment(cls, environment=None):
        values = os.environ if environment is None else environment
        actor_id = str(values.get("APPROVAL_ACTOR_ID", "") or "").strip()
        role = str(values.get("APPROVAL_ACTOR_ROLE", "") or "").strip().lower()
        if (
            ACTOR_PATTERN.fullmatch(actor_id) is None
            or role not in cls.ROLE_CAPABILITIES
        ):
            return cls(ApprovalActor("anonymous", "viewer"))
        return cls(ApprovalActor(actor_id, role))

    @property
    def capabilities(self):
        return tuple(sorted(self.ROLE_CAPABILITIES[self.actor.role]))

    def allows(self, capability):
        return capability in self.ROLE_CAPABILITIES[self.actor.role]

    def require(self, capability):
        if not self.allows(capability):
            raise ApprovalPermissionError()
        return self.actor

    def context(self):
        return {
            "actor_id": self.actor.actor_id,
            "role": self.actor.role,
            "capabilities": list(self.capabilities),
        }

    @staticmethod
    def system_actor():
        return ApprovalActor("system", "system")
