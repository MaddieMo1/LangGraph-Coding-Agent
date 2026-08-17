class ApprovalTool:
    """Apply a human-approved patch subset as one compensated transaction."""

    def __init__(self, approval_store, diff_tool, patch_history, audit_store=None):
        self.approval_store = approval_store
        self.diff_tool = diff_tool
        self.patch_history = patch_history
        self.audit_store = audit_store

    def apply_decision(self, bundle_id, decision, audit_context=None):
        bundle = self.approval_store.get(bundle_id)
        if bundle is None:
            return self._failure("BUNDLE_NOT_FOUND", "approval bundle not found")
        if bundle["status"] != "pending":
            return {
                "success": bundle["status"] != "conflicted",
                "status": bundle["status"],
                "bundle_id": bundle_id,
                "patch_ids": self._history_ids(bundle_id),
                "already_decided": True,
                "error_code": "" if bundle["status"] != "conflicted" else "CONFLICT",
                "error": bundle.get("error", ""),
            }

        try:
            action, mode, accepted_ids, note = self._normalize_decision(bundle, decision)
        except ValueError as error:
            return self._failure("INVALID_DECISION", str(error), bundle_id)

        if action == "reject" or not accepted_ids:
            rejected = self.approval_store.finalize(
                bundle_id,
                "rejected",
                mode,
                [],
                note,
            )
            try:
                self._record_application(
                    bundle,
                    audit_context,
                    "application_succeeded",
                    "rejected",
                    action,
                    mode,
                    note,
                )
            except ValueError as error:
                return self._compensate_audit_failure(
                    bundle,
                    mode,
                    [],
                    note,
                    error,
                )
            return self._success(rejected, [])

        selected_patches = [
            patch for patch in bundle["patches"] if patch["patch_id"] in accepted_ids
        ]
        previews = []
        for patch in selected_patches:
            preview = self.diff_tool.preview_patch(patch)
            if not preview.get("success", False):
                conflicted = self.approval_store.finalize(
                    bundle_id,
                    "conflicted",
                    mode,
                    accepted_ids,
                    note,
                    preview.get("error", "patch preflight failed"),
                )
                try:
                    self._record_application(
                        bundle,
                        audit_context,
                        "application_conflicted",
                        "conflicted",
                        action,
                        mode,
                        note,
                        preview.get("error_code", "CONFLICT"),
                    )
                except ValueError as error:
                    return self._failure(
                        getattr(error, "code", "AUDIT_FAILED"),
                        str(error),
                        bundle_id,
                        status="conflicted",
                    )
                return self._failure(
                    preview.get("error_code", "CONFLICT"),
                    conflicted.get("error", "patch preflight failed"),
                    bundle_id,
                    status="conflicted",
                )
            previews.append(preview)

        applied = []
        for patch, preview in zip(selected_patches, previews):
            result = self.diff_tool.apply_patch(patch)
            if not result.get("success", False):
                rollback_error = self._rollback(applied)
                error = result.get("error", "patch apply failed")
                if rollback_error:
                    error += f"; rollback failed: {rollback_error}"
                self.approval_store.finalize(
                    bundle_id,
                    "conflicted",
                    mode,
                    accepted_ids,
                    note,
                    error,
                )
                try:
                    self._record_application(
                        bundle,
                        audit_context,
                        "application_conflicted",
                        "conflicted",
                        action,
                        mode,
                        note,
                        result.get("error_code", "APPLY_FAILED"),
                    )
                except ValueError as audit_error:
                    return self._failure(
                        getattr(audit_error, "code", "AUDIT_FAILED"),
                        str(audit_error),
                        bundle_id,
                        status="conflicted",
                    )
                return self._failure(
                    result.get("error_code", "APPLY_FAILED"),
                    error,
                    bundle_id,
                    status="conflicted",
                )
            applied.append((patch, preview, result))

        records = []
        try:
            records = self.patch_history.record_batch(
                [
                    {
                        "patch": patch,
                        "before_content": preview["before_content"],
                        "after_content": preview["after_content"],
                        "apply_result": result,
                    }
                    for patch, preview, result in applied
                ],
                metadata={"approval_bundle_id": bundle_id},
            )
            status = (
                "approved"
                if len(accepted_ids) == len(bundle["patches"])
                else "partially_approved"
            )
            finalized = self.approval_store.finalize(
                bundle_id,
                status,
                "batch" if status == "approved" else "selected",
                accepted_ids,
                note,
            )
            self._record_application(
                bundle,
                audit_context,
                "application_succeeded",
                status,
                action,
                mode,
                note,
            )
        except (OSError, ValueError, KeyError) as error:
            if records:
                self.patch_history.remove_records(
                    [record["patch_id"] for record in records]
                )
            rollback_error = self._rollback(applied)
            message = str(error)
            if rollback_error:
                message += f"; rollback failed: {rollback_error}"
            self.approval_store.restore_bundle(bundle)
            self.approval_store.finalize(
                bundle_id,
                "conflicted",
                mode,
                accepted_ids,
                note,
                message,
            )
            return self._failure(
                getattr(error, "code", "TRANSACTION_FAILED"),
                message,
                bundle_id,
                status="conflicted",
            )

        return self._success(
            finalized,
            [record["patch_id"] for record in records],
        )

    def _record_application(
        self,
        bundle,
        context,
        event_type,
        result,
        action,
        mode,
        note,
        error_code="",
    ):
        if self.audit_store is None or context is None:
            return
        self.audit_store.append(
            {
                "event_type": event_type,
                "thread_id": context["thread_id"],
                "bundle_id": bundle["bundle_id"],
                "source": bundle["source"],
                "actor_id": context["actor_id"],
                "role": context["role"],
                "files": [
                    {
                        "file": patch["file"],
                        "operation": patch["operation"],
                        "before_hash": patch["before_hash"],
                        "after_hash": patch["after_hash"],
                    }
                    for patch in bundle["patches"]
                ],
                "action": f"{action}:{mode}",
                "result": result,
                "note": note,
                "error_code": error_code,
            },
            idempotency_key=(
                f"application:{context['thread_id']}:{bundle['bundle_id']}"
            ),
        )

    def _compensate_audit_failure(
        self,
        bundle,
        mode,
        accepted_ids,
        note,
        error,
    ):
        self.approval_store.restore_bundle(bundle)
        self.approval_store.finalize(
            bundle["bundle_id"],
            "conflicted",
            mode,
            accepted_ids,
            note,
            str(error),
        )
        return self._failure(
            getattr(error, "code", "AUDIT_FAILED"),
            str(error),
            bundle["bundle_id"],
            status="conflicted",
        )

    def _normalize_decision(self, bundle, decision):
        if not isinstance(decision, dict):
            raise ValueError("approval decision must be an object")
        action = decision.get("action", "")
        mode = decision.get("mode", "batch")
        note = str(decision.get("note", "")).strip()
        if action not in {"approve", "reject"}:
            raise ValueError("approval action must be approve or reject")
        if mode not in {"batch", "selected"}:
            raise ValueError("approval mode must be batch or selected")
        all_ids = [patch["patch_id"] for patch in bundle["patches"]]
        if action == "reject":
            return action, mode, [], note
        accepted_ids = (
            all_ids
            if mode == "batch"
            else decision.get("accepted_patch_ids", [])
        )
        if not isinstance(accepted_ids, list):
            raise ValueError("accepted_patch_ids must be a list")
        if len(set(accepted_ids)) != len(accepted_ids):
            raise ValueError("accepted patch IDs must be unique")
        unknown = set(accepted_ids).difference(all_ids)
        if unknown:
            raise ValueError(f"unknown patch IDs: {sorted(unknown)}")
        return action, mode, [item for item in all_ids if item in accepted_ids], note

    def _rollback(self, applied):
        errors = []
        for patch, preview, _ in reversed(applied):
            inverse = self.diff_tool.create_patch(
                patch["file"],
                preview["after_content"],
                preview["before_content"],
            )
            result = self.diff_tool.apply_patch(inverse)
            if not result.get("success", False):
                errors.append(result.get("error", patch["file"]))
        return "; ".join(errors)

    def _history_ids(self, bundle_id):
        return [
            record["patch_id"]
            for record in self.patch_history.list_records()
            if record.get("approval_bundle_id") == bundle_id
        ]

    @staticmethod
    def _success(bundle, patch_ids):
        return {
            "success": True,
            "status": bundle["status"],
            "bundle_id": bundle["bundle_id"],
            "patch_ids": patch_ids,
            "already_decided": False,
            "error_code": "",
            "error": "",
        }

    @staticmethod
    def _failure(error_code, error, bundle_id="", status="failed"):
        return {
            "success": False,
            "status": status,
            "bundle_id": bundle_id,
            "patch_ids": [],
            "already_decided": False,
            "error_code": error_code,
            "error": error,
        }
