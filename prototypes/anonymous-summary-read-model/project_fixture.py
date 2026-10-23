"""Opt-in, fixture-only anonymous summary projection; not a server route."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import re


SUMMARY_SCHEMA = "anonymous-summary/v1"
OMITTED_SECTIONS = [
    "task_text", "task_notes", "task_history", "chat_content", "screen_rows",
    "profile_notes", "display_names", "roles", "tools", "relationships",
    "heartbeat_timestamps", "raw_presence_fields",
]
TASK_STATUSES = (
    "pending", "assigned", "pending_revision", "pending_gorevli_review",
    "pending_verification", "verified", "dropped",
)
IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _health(member: object, *, now: datetime, online_sn: object) -> str:
    """Expose only fresh verified-online; every other state remains unknown."""
    if not isinstance(member, dict):
        return "unknown"
    if (member.get("online") is not True
            or member.get("presence_verified") is not True
            or member.get("presence_state") != "online"):
        return "unknown"
    if (type(online_sn) is not int or not 1 <= online_sn <= 300):
        return "unknown"
    heartbeat = member.get("son_kalp")
    if not isinstance(heartbeat, str):
        return "unknown"
    try:
        stamp = datetime.fromisoformat(heartbeat)
        if stamp.tzinfo is None or now.tzinfo is None:
            return "unknown"
        age = (now - stamp).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    return "online" if 0 <= age <= online_sn else "unknown"


def _disabled() -> dict[str, object]:
    return {
        "schema": SUMMARY_SCHEMA,
        "state": "disabled",
        "partial": True,
        "scope": "summary_only",
        "omitted_sections": list(OMITTED_SECTIONS),
        "roster": {"state": "unavailable", "shown_count": None, "entries": []},
        "task_counts": {"state": "unavailable", "counts": None},
    }


def project_summary(source: object, *, enabled: bool = False,
                    now: datetime | None = None) -> dict[str, object]:
    """Project allowlisted fields; disabled mode ignores source entirely."""
    if not enabled:
        return _disabled()
    now = now or datetime.now().astimezone()
    if not isinstance(source, dict) or source.get("ok") is not True:
        result = _disabled()
        result["state"] = "unavailable"
        return result

    metadata = source.get("snapshot_meta")
    source_complete = (isinstance(metadata, dict)
                       and metadata.get("partial") is False)
    partial_reasons: list[str] = []
    if not source_complete:
        partial_reasons.append("source_completeness_unknown")

    roster_source = source.get("kullanicilar")
    roster_entries: list[dict[str, str]] = []
    roster_valid = isinstance(roster_source, dict)
    if roster_valid:
        for identity, member in sorted(roster_source.items()):
            if not isinstance(identity, str) or not IDENTITY_RE.fullmatch(identity):
                roster_valid = False
                continue
            roster_entries.append({
                "id": identity,
                "health": _health(member, now=now,
                                  online_sn=source.get("online_sn")),
            })
            if not isinstance(member, dict):
                roster_valid = False
    if not roster_valid:
        partial_reasons.append("roster_incomplete")

    tasks_source = source.get("gorevler")
    task_counts = None
    tasks_valid = isinstance(tasks_source, list)
    if tasks_valid:
        counts = Counter({status: 0 for status in TASK_STATUSES})
        for task in tasks_source:
            status = task.get("durum") if isinstance(task, dict) else None
            if not isinstance(status, str) or status not in TASK_STATUSES:
                tasks_valid = False
                break
            counts[status] += 1
        if tasks_valid:
            task_counts = {status: counts[status] for status in TASK_STATUSES}
    if not tasks_valid:
        partial_reasons.append("task_counts_incomplete")

    complete = source_complete and roster_valid and tasks_valid
    state = "complete_for_allowlist" if complete else "partial"
    section_state = "complete" if complete else "partial"
    return {
        "schema": SUMMARY_SCHEMA,
        "state": state,
        "partial": not complete,
        "scope": "summary_only",
        "partial_reasons": partial_reasons,
        "omitted_sections": list(OMITTED_SECTIONS),
        "roster": {
            "state": (section_state if roster_valid else
                      "partial" if roster_entries else "unavailable"),
            # If some entries were validated before an invalid identity/member
            # made the roster partial, expose only that visible lower bound.
            # An unusable map or a partial roster with no valid entries has no
            # defensible count and remains null.
            "shown_count": (len(roster_entries)
                            if roster_valid or roster_entries else None),
            "entries": roster_entries,
        },
        "task_counts": {
            "state": section_state if tasks_valid else "unavailable",
            "counts": task_counts if complete else None,
        },
    }
