"""Small UI view-model contract for the isolated summary fixture."""

from __future__ import annotations


def consume_summary(summary: object) -> dict[str, object]:
    """Never reinterpret missing/partial values as an empty complete snapshot."""
    if not isinstance(summary, dict) or summary.get("schema") != "anonymous-summary/v1":
        return {"state": "unavailable", "banner": "Summary unavailable",
                "roster_label": "Roster unavailable", "roster": [],
                "task_counts": None}
    state = summary.get("state")
    roster = summary.get("roster")
    entries = roster.get("entries") if isinstance(roster, dict) else None
    entries = entries if isinstance(entries, list) else []
    shown = roster.get("shown_count") if isinstance(roster, dict) else None
    if state == "disabled":
        return {"state": "disabled", "banner": "Summary mode is disabled",
                "roster_label": "Roster unavailable", "roster": [],
                "task_counts": None}
    if state == "unavailable":
        return {"state": "unavailable", "banner": "Summary unavailable",
                "roster_label": "Roster unavailable", "roster": [],
                "task_counts": None}
    if state != "complete_for_allowlist" or summary.get("partial") is not False:
        roster_label = (f"At least {shown} roster entries shown; total unknown"
                       if type(shown) is int else "Roster unavailable")
        return {"state": "partial",
                "banner": "Partial summary; missing data is not inferred",
                "roster_label": roster_label,
                "roster": entries if isinstance(entries, list) else [],
                "task_counts": None}

    counts_obj = summary.get("task_counts")
    counts = None
    if (isinstance(counts_obj, dict) and counts_obj.get("state") == "complete"
            and isinstance(counts_obj.get("counts"), dict)):
        counts = dict(counts_obj["counts"])
    return {"state": "complete_for_allowlist",
            "banner": "Summary only; task/chat/screen details are omitted",
            "roster_label": f"{shown} roster entries (summary scope)",
            "roster": entries,
            "task_counts": counts}
