"""Pure source-classification sketch for a future session bridge.

This module consumes structured origin evidence supplied by a trusted caller.
It does not inspect message text, authenticate a principal, authorize an action,
connect to a provider, or integrate with Yuva.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceKind(str, Enum):
    USER_INSTRUCTION = "user_instruction"
    VERIFIED_OPERATOR = "verified_operator"
    CANONICAL_TASK = "canonical_task"
    YUVA_CHAT = "yuva_chat"
    WORKER_MESSAGE = "worker_message"
    TOOL_OUTPUT = "tool_output"
    UNKNOWN = "unknown"


class Authority(str, Enum):
    USER_REQUEST = "user_request"
    OPERATOR_CONTROL = "operator_control"
    TASK_SCOPE = "task_scope"
    DATA_ONLY = "data_only"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TaskBindingEvidence:
    """Caller-verified linkage from a canonical task record to its context."""

    task_id: str | int
    session_id: str | None
    workspace_id: str | None
    assignee_id: str | None
    record_lookup_verified: bool = False
    session_binding_verified: bool = False
    workspace_binding_verified: bool = False
    assignee_binding_verified: bool = False


@dataclass(frozen=True)
class VerifiedTaskBinding:
    """Task and session context that classify_origin verified structurally."""

    task_id: int
    session_id: str
    workspace_id: str
    assignee_id: str


@dataclass(frozen=True)
class OriginEvidence:
    """Transport-side labels; never derive these fields from the message body."""

    source: SourceKind | str
    transport_verified: bool = False
    principal_id: str | None = None
    task_id: str | int | None = None
    task_binding: TaskBindingEvidence | None = None


@dataclass(frozen=True)
class Classification:
    source: SourceKind
    authority: Authority
    may_supply_instruction: bool
    may_authorize_external_action: bool
    reason: str
    task_binding: VerifiedTaskBinding | None = None


def _canonical_task_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if (isinstance(value, str) and value.isascii()
            and value.isdecimal() and value[0] in "123456789"):
        return int(value)
    return None


def _context_id_valid(value: object) -> bool:
    return (isinstance(value, str) and bool(value)
            and value == value.strip() and len(value) <= 256)


def _unknown(reason: str) -> Classification:
    return Classification(
        SourceKind.UNKNOWN, Authority.UNKNOWN,
        may_supply_instruction=False,
        may_authorize_external_action=False,
        reason=reason,
    )


def _data_only(source: SourceKind, reason: str) -> Classification:
    return Classification(
        source, Authority.DATA_ONLY,
        may_supply_instruction=False,
        may_authorize_external_action=False,
        reason=reason,
    )


def _verified_task_binding(evidence: OriginEvidence) -> VerifiedTaskBinding | None:
    raw = evidence.task_binding
    task_id = _canonical_task_id(evidence.task_id)
    if not isinstance(raw, TaskBindingEvidence) or task_id is None:
        return None
    bound_task_id = _canonical_task_id(raw.task_id)
    if (bound_task_id != task_id
            or raw.record_lookup_verified is not True
            or raw.session_binding_verified is not True
            or raw.workspace_binding_verified is not True
            or raw.assignee_binding_verified is not True
            or not _context_id_valid(raw.session_id)
            or not _context_id_valid(raw.workspace_id)
            or not _context_id_valid(raw.assignee_id)):
        return None
    return VerifiedTaskBinding(
        task_id=task_id,
        session_id=raw.session_id,
        workspace_id=raw.workspace_id,
        assignee_id=raw.assignee_id,
    )


def classify_origin(evidence: OriginEvidence) -> Classification:
    """Classify a transport label without inspecting or elevating its content.

    The booleans and IDs here are caller assertions, not cryptographic proof.
    A production caller must construct this evidence only after validating the
    actual ingress channel, identity, task record lookup, task binding, and
    session scope.
    """
    if not isinstance(evidence, OriginEvidence):
        return _unknown("invalid_evidence_type")
    try:
        source = SourceKind(evidence.source)
    except (TypeError, ValueError):
        return _unknown("unrecognized_source")

    if source is SourceKind.USER_INSTRUCTION:
        if evidence.transport_verified is not True:
            return _unknown("user_channel_not_verified")
        return Classification(
            source, Authority.USER_REQUEST,
            may_supply_instruction=True,
            may_authorize_external_action=False,
            reason="direct_user_request; outer policy must scope any side effect",
        )

    if source is SourceKind.VERIFIED_OPERATOR:
        if (evidence.transport_verified is not True
                or not isinstance(evidence.principal_id, str)
                or not evidence.principal_id.strip()
                or len(evidence.principal_id) > 128):
            return _unknown("operator_identity_not_verified")
        return Classification(
            source, Authority.OPERATOR_CONTROL,
            may_supply_instruction=True,
            may_authorize_external_action=False,
            reason="verified_operator_source; exact action approval is a separate check",
        )

    if source is SourceKind.CANONICAL_TASK:
        binding = _verified_task_binding(evidence)
        if binding is None:
            return _data_only(source, "task_record_or_context_binding_not_verified")
        return Classification(
            source, Authority.TASK_SCOPE,
            may_supply_instruction=True,
            may_authorize_external_action=False,
            reason="bounded_task_scope; task cannot grant new permissions",
            task_binding=binding,
        )

    if source in {SourceKind.YUVA_CHAT, SourceKind.WORKER_MESSAGE,
                  SourceKind.TOOL_OUTPUT}:
        return Classification(
            source, Authority.DATA_ONLY,
            may_supply_instruction=False,
            may_authorize_external_action=False,
            reason="content_is_data_not_authority",
        )

    return _unknown("source_is_unknown")
