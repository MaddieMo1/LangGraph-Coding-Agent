import copy
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone


class ApprovalStore:
    """Persist immutable patch bundles and their human decisions."""

    SCHEMA_VERSION = 1
    SOURCES = {"coder", "repair"}
    TERMINAL_STATUSES = {
        "approved",
        "partially_approved",
        "rejected",
        "conflicted",
    }

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.data = self._load()

    def create_bundle(self, source, patches):
        if source not in self.SOURCES:
            raise ValueError("approval source must be coder or repair")
        if not isinstance(patches, list) or not patches:
            raise ValueError("approval bundle requires at least one patch")

        stored_patches = []
        files = set()
        patch_ids = set()
        for patch in patches:
            stored_patch = self._validate_patch(patch)
            file_name = stored_patch["file"]
            if file_name in files:
                raise ValueError(f"approval bundle contains duplicate file: {file_name}")
            files.add(file_name)
            patch_id = self._patch_id(stored_patch)
            if patch_id in patch_ids:
                raise ValueError(f"approval bundle contains duplicate patch: {file_name}")
            patch_ids.add(patch_id)
            stored_patch["patch_id"] = patch_id
            stored_patches.append(stored_patch)

        bundle = {
            "bundle_id": uuid.uuid4().hex,
            "source": source,
            "status": "pending",
            "created_at": self._now(),
            "decided_at": "",
            "patches": stored_patches,
            "decision": {},
            "error": "",
        }
        self.data["bundles"].append(bundle)
        self._save()
        return copy.deepcopy(bundle)

    def get(self, bundle_id):
        bundle = self._find(bundle_id)
        return copy.deepcopy(bundle) if bundle else None

    def list_pending(self):
        return [
            copy.deepcopy(bundle)
            for bundle in self.data["bundles"]
            if bundle.get("status") == "pending"
        ]

    def finalize(
        self,
        bundle_id,
        status,
        mode,
        accepted_patch_ids,
        note="",
        error="",
    ):
        bundle = self._find(bundle_id)
        if bundle is None:
            raise KeyError(f"approval bundle not found: {bundle_id}")
        if bundle["status"] != "pending":
            return copy.deepcopy(bundle)
        if status not in self.TERMINAL_STATUSES:
            raise ValueError(f"invalid approval status: {status}")
        if mode not in {"batch", "selected"}:
            raise ValueError(f"invalid approval mode: {mode}")
        if not isinstance(accepted_patch_ids, list):
            raise ValueError("accepted_patch_ids must be a list")

        all_ids = [patch["patch_id"] for patch in bundle["patches"]]
        unknown_ids = set(accepted_patch_ids).difference(all_ids)
        if unknown_ids:
            raise ValueError(f"unknown patch IDs: {sorted(unknown_ids)}")
        if len(set(accepted_patch_ids)) != len(accepted_patch_ids):
            raise ValueError("accepted patch IDs must be unique")

        accepted_ids = [
            patch_id for patch_id in all_ids if patch_id in accepted_patch_ids
        ]
        rejected_ids = [patch_id for patch_id in all_ids if patch_id not in accepted_ids]

        if status == "approved":
            if mode != "batch" or accepted_ids != all_ids:
                raise ValueError("approved batch must accept every patch")
        elif status == "partially_approved":
            if mode != "selected" or not accepted_ids:
                raise ValueError("selected approval requires at least one patch")
            if not rejected_ids:
                raise ValueError("partial approval must reject at least one patch")
        elif status == "rejected" and accepted_ids:
            raise ValueError("rejected bundle cannot contain accepted patches")

        bundle["status"] = status
        bundle["decided_at"] = self._now()
        bundle["decision"] = {
            "mode": mode,
            "accepted_patch_ids": accepted_ids,
            "rejected_patch_ids": rejected_ids,
            "note": str(note).strip(),
        }
        bundle["error"] = str(error).strip()
        self._save()
        return copy.deepcopy(bundle)

    def _find(self, bundle_id):
        for bundle in self.data["bundles"]:
            if bundle.get("bundle_id") == bundle_id:
                return bundle
        return None

    def _load(self):
        if not os.path.exists(self.path):
            return {"schema_version": self.SCHEMA_VERSION, "bundles": []}
        try:
            with open(self.path, "r", encoding="utf-8") as approval_file:
                data = json.load(approval_file)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to load approval history: {error}") from error
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != self.SCHEMA_VERSION
            or not isinstance(data.get("bundles"), list)
        ):
            raise ValueError("Invalid approval history schema")
        for bundle in data["bundles"]:
            self._validate_bundle(bundle)
        return data

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary_path = self.path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as approval_file:
                json.dump(self.data, approval_file, ensure_ascii=False, indent=2)
                approval_file.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def _validate_bundle(self, bundle):
        required = {
            "bundle_id",
            "source",
            "status",
            "created_at",
            "decided_at",
            "patches",
            "decision",
            "error",
        }
        if not isinstance(bundle, dict) or not required.issubset(bundle):
            raise ValueError("Invalid approval history bundle")
        if bundle["source"] not in self.SOURCES:
            raise ValueError("Invalid approval history source")
        if bundle["status"] not in {"pending", *self.TERMINAL_STATUSES}:
            raise ValueError("Invalid approval history status")
        if not isinstance(bundle["patches"], list) or not bundle["patches"]:
            raise ValueError("Invalid approval history patches")
        for patch in bundle["patches"]:
            self._validate_patch(patch, require_patch_id=True)

    @staticmethod
    def _validate_patch(patch, require_patch_id=False):
        required = {
            "version",
            "file",
            "operation",
            "before_hash",
            "after_hash",
            "changed",
            "diff",
            "hunks",
        }
        if not isinstance(patch, dict) or not required.issubset(patch):
            raise ValueError("approval patch is missing required fields")
        if require_patch_id and not patch.get("patch_id"):
            raise ValueError("approval patch is missing patch_id")
        if patch["operation"] not in {"create", "modify", "delete"}:
            raise ValueError("approval patch operation must change a file")
        if not patch["changed"] or not isinstance(patch["hunks"], list):
            raise ValueError("approval patch must contain a change")
        return copy.deepcopy(patch)

    @staticmethod
    def _patch_id(patch):
        identity = {
            "version": patch["version"],
            "file": patch["file"],
            "operation": patch["operation"],
            "before_hash": patch["before_hash"],
            "after_hash": patch["after_hash"],
        }
        canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
