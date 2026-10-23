"""Source-preserving projection for cross-agent context; no Yuva/provider I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


MAX_SOURCE_ID_LENGTH = 160
MAX_TEXT_LENGTH = 64 * 1024


class Origin(str, Enum):
    SHARED_CHAT = "shared_chat"
    CANONICAL_TASK = "canonical_task"
    REVIEWER_TASK = "reviewer_task"
    REVIEWER_OUTPUT = "reviewer_output"
    WORKER_OUTPUT = "worker_output"
    PROVIDER_OUTPUT = "provider_output"
    TOOL_OUTPUT = "tool_output"


@dataclass(frozen=True)
class ControlReferences:
    """Out-of-band references only; never assembled from a chat record."""

    user_request_id: str | None = None
    canonical_task_id: str | None = None
    assigned_to: str | None = None
    reviewer_event_id: str | None = None


@dataclass(frozen=True)
class ContextItem:
    origin: Origin
    source_id: str
    actor_claim: str
    source_claim: str
    trust_claim: str
    source_class_claim: str
    source_class_trust: str
    identity_status: str
    content_class: str
    authority_scope: str
    text: str


@dataclass(frozen=True)
class ContextPacket:
    control: ControlReferences
    data_items: tuple[ContextItem, ...]


class ContextInputError(ValueError):
    pass


def project_item(origin: Origin, record: Mapping[str, object]) -> ContextItem:
    """Preserve a record's source claims while granting it no authority.

    `origin` comes from the adapter/caller, not from fields in `record`.
    Identity, trust, role, task scope, and permission fields in the record stay
    claims or are ignored; no message can manufacture ControlReferences.
    """
    if not isinstance(origin, Origin):
        raise ContextInputError("origin must be supplied by a trusted adapter enum")
    if not isinstance(record, Mapping):
        raise ContextInputError("record must be an object")

    source_id = record.get("id", record.get("source_id", record.get("event_id")))
    if (not isinstance(source_id, str) or not source_id
            or len(source_id) > MAX_SOURCE_ID_LENGTH):
        raise ContextInputError("stable source ID required")
    text = record.get("metin", record.get("text", record.get("content")))
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT_LENGTH:
        raise ContextInputError("text must be a bounded string")

    actor = record.get("kimden", record.get("actor_id", "unknown"))
    source = record.get("source", "unknown")
    trust = record.get("trust", "unknown")
    source_class = record.get("source_class", "unknown")
    if not isinstance(source_class, str) or source_class not in {"operator", "agent", "unknown"}:
        source_class = "unknown"
    return ContextItem(
        origin=origin,
        source_id=source_id,
        actor_claim=actor if isinstance(actor, str) else "unknown",
        source_claim=source if isinstance(source, str) else "unknown",
        trust_claim=trust if isinstance(trust, str) else "unknown",
        source_class_claim=source_class,
        source_class_trust="unverified",
        identity_status="unknown",
        content_class="data_only",
        authority_scope="none",
        text=text,
    )


def build_packet(
    control: ControlReferences,
    records: Iterable[tuple[Origin, Mapping[str, object]]],
) -> ContextPacket:
    """Keep outer control references structurally separate from data items."""
    if not isinstance(control, ControlReferences):
        raise ContextInputError("control references must come from the caller")
    items = tuple(project_item(origin, record) for origin, record in records)
    return ContextPacket(control=control, data_items=items)


def ui_label(origin: Origin) -> str:
    """Return a fixed display label; content never supplies its own role label."""
    labels = {
        Origin.SHARED_CHAT: "Yuva ortak sohbet · veri",
        Origin.CANONICAL_TASK: "Kanonik görev kaydı",
        Origin.REVIEWER_TASK: "Denetçi görevi",
        Origin.REVIEWER_OUTPUT: "Denetçi çıktısı · veri",
        Origin.WORKER_OUTPUT: "İşçi çıktısı · veri",
        Origin.PROVIDER_OUTPUT: "Provider çıktısı · veri",
        Origin.TOOL_OUTPUT: "Araç çıktısı · veri",
    }
    return labels[origin]
