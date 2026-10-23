"""Reference fail-closed decision for task-writer compatibility evidence.

This is a policy fixture only. No CLI copy imports it; production identity,
release pinning, and schema checks still require a separate implementation.
"""

from dataclasses import dataclass
import re


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str


def task_writer_decision(profile: object, *, approved_sha256: str) -> GateDecision:
    """Allow only a pinned canonical writer with complete lock/schema proof."""
    if not isinstance(approved_sha256, str) or not _SHA256.fullmatch(approved_sha256):
        return GateDecision(False, "approved_writer_hash_invalid")
    if not isinstance(profile, dict):
        return GateDecision(False, "writer_profile_missing")
    required = {
        "sha256", "source_role", "recovery_only", "uses_shared_lock",
        "locks_full_read_modify_write", "validates_schema_version",
        "preserves_schema_version", "schema_version", "supported_schema_versions",
    }
    if set(profile) != required:
        return GateDecision(False, "writer_profile_incomplete")
    if profile["recovery_only"] is not False:
        return GateDecision(False, "recovery_copy_read_only")
    if profile["source_role"] != "canonical":
        return GateDecision(False, "writer_not_canonical")
    if (not isinstance(profile["sha256"], str)
            or not _SHA256.fullmatch(profile["sha256"])
            or profile["sha256"] != approved_sha256):
        return GateDecision(False, "writer_hash_unapproved")
    if profile["uses_shared_lock"] is not True or profile["locks_full_read_modify_write"] is not True:
        return GateDecision(False, "lock_contract_unproven")
    if (profile["validates_schema_version"] is not True
            or profile["preserves_schema_version"] is not True):
        return GateDecision(False, "schema_contract_unproven")
    supported = profile["supported_schema_versions"]
    version = profile["schema_version"]
    if (type(version) is not int or not isinstance(supported, (list, tuple, set, frozenset))
            or any(type(item) is not int for item in supported)
            or version not in supported):
        return GateDecision(False, "schema_version_unsupported")
    return GateDecision(True, "canonical_writer_compatible")
