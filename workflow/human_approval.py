from langgraph.types import interrupt


class ChangeProposalNode:
    """Turn validated code changes into one durable approval request."""

    def __init__(self, proposal_tool, approval_store):
        self.proposal_tool = proposal_tool
        self.approval_store = approval_store

    def run(self, state):
        source = state.get("proposal_source", "")
        changes = state.get("proposed_changes", [])
        if not changes:
            return {
                "current_agent": "change_proposal",
                "change_proposal": {
                    "source": source,
                    "patches": [],
                    "unchanged_files": [],
                },
                "approval_request": {},
                "approval_status": "no_changes",
            }
        try:
            proposal = self.proposal_tool.propose(changes, source)
            if not proposal["patches"]:
                return {
                    "current_agent": "change_proposal",
                    "change_proposal": proposal,
                    "approval_request": {},
                    "approval_status": "no_changes",
                }
            bundle = self.approval_store.create_bundle(source, proposal["patches"])
        except (OSError, ValueError) as error:
            return {
                "current_agent": "change_proposal",
                "change_proposal": {},
                "approval_request": {},
                "approval_status": "error",
                "approval_result": {
                    "success": False,
                    "error_code": "PROPOSAL_ERROR",
                    "error": str(error),
                },
            }
        return {
            "current_agent": "change_proposal",
            "change_proposal": proposal,
            "approval_request": self._safe_request(bundle),
            "approval_status": "pending",
        }

    @staticmethod
    def _safe_request(bundle):
        return {
            "bundle_id": bundle["bundle_id"],
            "source": bundle["source"],
            "status": bundle["status"],
            "created_at": bundle["created_at"],
            "patches": [
                {
                    "patch_id": patch["patch_id"],
                    "file": patch["file"],
                    "operation": patch["operation"],
                    "before_hash": patch["before_hash"],
                    "after_hash": patch["after_hash"],
                    "diff": patch["diff"],
                }
                for patch in bundle["patches"]
            ],
        }


class HumanApprovalNode:
    """Interrupt for a human decision, then apply the matching bundle once."""

    def __init__(self, approval_tool, interrupt_fn=interrupt):
        self.approval_tool = approval_tool
        self.interrupt_fn = interrupt_fn

    def run(self, state):
        request = state.get("approval_request", {})
        bundle_id = request.get("bundle_id", "")
        if not bundle_id:
            return self._error_update(state, "APPROVAL_REQUEST_MISSING", "approval request is missing")

        decision = self.interrupt_fn(request)
        if not isinstance(decision, dict):
            return self._error_update(state, "INVALID_DECISION", "approval decision must be an object")
        if decision.get("bundle_id") != bundle_id:
            return self._error_update(
                state,
                "BUNDLE_MISMATCH",
                "approval decision does not match the interrupted bundle",
            )

        result = self.approval_tool.apply_decision(bundle_id, decision)
        status = result.get("status", "error") if result.get("success", False) else (
            "conflicted" if result.get("status") == "conflicted" else "error"
        )
        update = {
            "current_agent": "human_approval",
            "approval_status": status,
            "approval_result": result,
            "approval_history": state.get("approval_history", [])
            + [self._history_record(request, result, status)],
            "proposed_changes": [],
        }
        if status in {
            "approved",
            "partially_approved",
        }:
            accepted_patches = self._accepted_patches(bundle_id)
            accepted_files = {patch["file"] for patch in accepted_patches}
            update["approved_changes"] = self._merge_approved_changes(
                state.get("approved_changes", []),
                accepted_patches,
            )
        if request.get("source") == "coder" and status in {
            "approved",
            "partially_approved",
        }:
            update["code"] = [
                item
                for item in state.get("code", [])
                if item.get("file") in accepted_files
            ]
        return update

    def _accepted_patches(self, bundle_id):
        bundle = self.approval_tool.approval_store.get(bundle_id) or {}
        accepted_ids = set(bundle.get("decision", {}).get("accepted_patch_ids", []))
        return [
            {
                "file": patch["file"],
                "operation": patch["operation"],
                "after_hash": patch["after_hash"],
            }
            for patch in bundle.get("patches", [])
            if patch.get("patch_id") in accepted_ids
        ]

    @staticmethod
    def _merge_approved_changes(existing, accepted):
        by_file = {
            item["file"]: {
                "file": item["file"],
                "operation": item["operation"],
                "after_hash": item["after_hash"],
            }
            for item in existing
        }
        for item in accepted:
            by_file[item["file"]] = item
        return [by_file[file_name] for file_name in sorted(by_file)]

    def _error_update(self, state, error_code, error):
        result = {
            "success": False,
            "status": "error",
            "bundle_id": state.get("approval_request", {}).get("bundle_id", ""),
            "patch_ids": [],
            "already_decided": False,
            "error_code": error_code,
            "error": error,
        }
        return {
            "current_agent": "human_approval",
            "approval_status": "error",
            "approval_result": result,
            "approval_history": state.get("approval_history", [])
            + [
                self._history_record(
                    state.get("approval_request", {}),
                    result,
                    "error",
                )
            ],
        }

    @staticmethod
    def _history_record(request, result, status):
        return {
            "bundle_id": request.get("bundle_id", ""),
            "source": request.get("source", ""),
            "status": status,
            "patch_ids": result.get("patch_ids", []),
            "error_code": result.get("error_code", ""),
            "error": result.get("error", ""),
        }
