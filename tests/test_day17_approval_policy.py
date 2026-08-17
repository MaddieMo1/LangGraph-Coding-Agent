import unittest

from tools.approval_policy import (
    ApprovalActor,
    ApprovalPermissionError,
    ApprovalPolicy,
)


class ApprovalPolicyTest(unittest.TestCase):
    def test_loads_a_valid_startup_bound_actor(self):
        policy = ApprovalPolicy.from_environment({
            "APPROVAL_ACTOR_ID": "alice@example.com",
            "APPROVAL_ACTOR_ROLE": "APPROVER",
        })

        self.assertEqual(
            ApprovalActor("alice@example.com", "approver"),
            policy.actor,
        )
        self.assertEqual(
            (
                "approval.decide",
                "approval.read",
                "approval.review",
                "audit.export",
                "audit.read",
            ),
            policy.capabilities,
        )

    def test_missing_or_invalid_configuration_is_read_only(self):
        invalid_environments = [
            {},
            {"APPROVAL_ACTOR_ID": "alice", "APPROVAL_ACTOR_ROLE": ""},
            {"APPROVAL_ACTOR_ID": "alice\nadmin", "APPROVAL_ACTOR_ROLE": "approver"},
            {"APPROVAL_ACTOR_ID": "a" * 65, "APPROVAL_ACTOR_ROLE": "approver"},
            {"APPROVAL_ACTOR_ID": "alice", "APPROVAL_ACTOR_ROLE": "system"},
            {"APPROVAL_ACTOR_ID": "alice", "APPROVAL_ACTOR_ROLE": "owner"},
        ]

        for environment in invalid_environments:
            with self.subTest(environment=environment):
                policy = ApprovalPolicy.from_environment(environment)
                self.assertEqual(ApprovalActor("anonymous", "viewer"), policy.actor)
                self.assertFalse(policy.allows("approval.decide"))

    def test_enforces_the_least_privilege_role_matrix(self):
        expected = {
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

        for role, capabilities in expected.items():
            with self.subTest(role=role):
                policy = ApprovalPolicy.from_environment({
                    "APPROVAL_ACTOR_ID": "local-user",
                    "APPROVAL_ACTOR_ROLE": role,
                })
                self.assertEqual(tuple(sorted(capabilities)), policy.capabilities)
                for capability in set().union(*expected.values()):
                    self.assertEqual(
                        capability in capabilities,
                        policy.allows(capability),
                    )

    def test_permission_failure_is_bounded_and_sanitized(self):
        policy = ApprovalPolicy.from_environment({})

        with self.assertRaises(ApprovalPermissionError) as raised:
            policy.require("approval.decide")

        self.assertEqual("APPROVAL_PERMISSION_DENIED", raised.exception.code)
        self.assertEqual("approval permission denied", str(raised.exception))
        self.assertNotIn("APPROVAL_ACTOR", str(raised.exception))

    def test_require_returns_the_authoritative_actor(self):
        policy = ApprovalPolicy.from_environment({
            "APPROVAL_ACTOR_ID": "alice",
            "APPROVAL_ACTOR_ROLE": "approver",
        })

        self.assertEqual(policy.actor, policy.require("approval.decide"))
        self.assertEqual(
            {
                "actor_id": "alice",
                "role": "approver",
                "capabilities": list(policy.capabilities),
            },
            policy.context(),
        )

    def test_reserved_system_actor_has_no_human_permissions(self):
        actor = ApprovalPolicy.system_actor()

        self.assertEqual(ApprovalActor("system", "system"), actor)
        self.assertNotIn("system", ApprovalPolicy.ROLE_CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
