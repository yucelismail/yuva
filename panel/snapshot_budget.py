"""Deterministic global JSON/UTF-8 snapshot byte selector for panel GETs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


RESPONSE_BYTE_BUDGET = 8 * 1024 * 1024
METADATA_RESERVE = 128 * 1024
GROUP_BUDGETS = {
    "kullanicilar": 1 * 1024 * 1024,
    "gorevler": 2 * 1024 * 1024,
    "mesajlar": 2 * 1024 * 1024,
    "ekranlar": 2 * 1024 * 1024,
}
ITEM_BUDGETS = {
    "kullanicilar": 64 * 1024,
    "gorevler": 256 * 1024,
    "mesajlar": 128 * 1024,
    "ekranlar": None,
}
GROUP_REASONS = {
    "kullanicilar": "users_output_byte_limit",
    "gorevler": "tasks_output_byte_limit",
    "mesajlar": "messages_output_byte_limit",
    "ekranlar": "screen_output_partial",
}
REASON_ORDER = (
    "users_output_byte_limit", "tasks_output_byte_limit",
    "messages_output_byte_limit", "screen_output_partial",
    "record_size_limit", "record_encoding_error", "final_response_byte_limit",
)
FIXED_FIELDS = ("ok", "simdi", "online_sn", "rev", "ekranlar_meta")
GROUP_FIELDS = ("kullanicilar", "gorevler", "mesajlar", "ekranlar")
STATUS_ORDER = (
    "assigned", "pending_revision", "pending_verification",
    "pending_gorevli_review", "pending",
)


@dataclass(frozen=True)
class SnapshotResponse:
    status: int
    body: bytes

    @property
    def content_length(self) -> int:
        return len(self.body)


def _encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def error_response(code: str) -> SnapshotResponse:
    """Return a bounded fixed error, distinct from a valid empty snapshot."""
    statuses = {
        "snapshot_source_limit": 503,
        "snapshot_response_unavailable": 503,
        "snapshot_read_failed": 500,
    }
    if code not in statuses:
        raise ValueError("unsupported fixture error code")
    return SnapshotResponse(statuses[code], _encode({"ok": False, "hata": code}))


def _empty_body_size(fixed: dict[str, bytes]) -> int:
    parts = []
    for key in FIXED_FIELDS[:4]:
        parts.append(_encode(key) + b":" + fixed[key])
    parts.extend((
        _encode("kullanicilar") + b":{}",
        _encode("gorevler") + b":[]",
        _encode("mesajlar") + b":[]",
        _encode("ekranlar") + b":{}",
        _encode("ekranlar_meta") + b":" + fixed["ekranlar_meta"],
        _encode("snapshot_meta") + b":{}",
    ))
    return len(b"{" + b",".join(parts) + b"}")


def _candidate(value: Any, key: str | None = None):
    value_bytes = _encode(value)
    key_bytes = _encode(key) if key is not None else None
    cost = len(value_bytes) if key_bytes is None else len(key_bytes) + 1 + len(value_bytes)
    return key, value_bytes, key_bytes, cost


def _ordered_candidates(group: str, values: Any, screen_order: list[str]):
    if group == "kullanicilar":
        valid_keys = []
        invalid_keys = []
        for key in values:
            if not isinstance(key, str):
                invalid_keys.append(key)
                continue
            try:
                key.encode("utf-8")
                valid_keys.append(key)
            except UnicodeError:
                invalid_keys.append(key)
        for key in sorted(valid_keys, key=lambda item: item.encode("utf-8")):
            try:
                candidate = _candidate(values[key], key)
                yield (*candidate, key)
            except (TypeError, ValueError, UnicodeError):
                yield key, None, None, None, key
        for key in invalid_keys:
            yield key, None, None, None, key
        return

    if group == "gorevler":
        def priority(index_task):
            index, task = index_task
            status = task.get("durum") if isinstance(task, dict) else None
            try:
                rank = STATUS_ORDER.index(status)
            except ValueError:
                rank = len(STATUS_ORDER)
            return (0 if rank < len(STATUS_ORDER) else 1, rank, -index)

        ordered = sorted(enumerate(values), key=priority)
    elif group == "mesajlar":
        ordered = list(enumerate(values[-200:]))
        offset = max(0, len(values) - 200)
        ordered = [(index + offset, message) for index, message in ordered]
        ordered.reverse()
    else:
        ordered = [(key, values.get(key)) for key in screen_order if key in values]

    for index_or_key, value in ordered:
        key = index_or_key if group == "ekranlar" else None
        try:
            candidate = _candidate(value, key)
            yield (*candidate, index_or_key)
        except (TypeError, ValueError, UnicodeError):
            yield key, None, None, None, index_or_key


def _select_group(group: str, values: Any, *, group_budget: int,
                  item_budget: int | None, global_remaining: int,
                  screen_order: list[str], source_omitted: int = 0):
    is_map = group in ("kullanicilar", "ekranlar")
    parts: list[tuple[Any, bytes]] = []
    used = 2  # Empty map or array brackets.
    included = 0
    omitted = source_omitted
    reasons: set[str] = set()
    if source_omitted:
        reasons.add(GROUP_REASONS[group])

    for key, value_bytes, key_bytes, item_cost, source_order in _ordered_candidates(
            group, values, screen_order):
        if value_bytes is None:
            omitted += 1
            reasons.add("record_encoding_error")
            continue
        if item_budget is not None and item_cost > item_budget:
            omitted += 1
            reasons.add("record_size_limit")
            continue
        addition = item_cost + (1 if parts else 0)
        if used + addition > group_budget or addition > global_remaining:
            omitted += 1
            reasons.add(GROUP_REASONS[group])
            continue
        if is_map:
            parts.append((source_order, key_bytes + b":" + value_bytes))
        else:
            parts.append((source_order, value_bytes))
        used += addition
        included += 1
        global_remaining -= addition

    if group in ("gorevler", "mesajlar"):
        parts.sort(key=lambda part: part[0])
    encoded_parts = [part for _, part in parts]
    if is_map:
        encoded_group = b"{" + b",".join(encoded_parts) + b"}"
    else:
        encoded_group = b"[" + b",".join(encoded_parts) + b"]"
    return encoded_group, included, omitted, reasons, global_remaining


def build_response(snapshot: Any, *, response_byte_budget: int = RESPONSE_BYTE_BUDGET,
                   group_budgets: dict[str, int] | None = None,
                   item_budgets: dict[str, int | None] | None = None,
                   metadata_reserve: int = METADATA_RESERVE,
                   screen_order: list[str] | None = None) -> SnapshotResponse:
    """Select complete records under one final JSON UTF-8 byte budget.

    Screen input is assumed to have already passed the #459 round-robin,
    per-file, row and screen-map selectors. ``screen_order`` carries that
    selector's deterministic order into the global pass; this function never
    advances a screen cursor or writes source state.
    """
    if (not isinstance(snapshot, dict) or type(response_byte_budget) is not int
            or response_byte_budget < 1 or type(metadata_reserve) is not int
            or metadata_reserve < 2):
        return error_response("snapshot_read_failed")
    required = set(FIXED_FIELDS + GROUP_FIELDS)
    if not required.issubset(snapshot):
        return error_response("snapshot_read_failed")
    if (not isinstance(snapshot["ekranlar_meta"], dict)
            or not isinstance(snapshot["kullanicilar"], dict)
            or not isinstance(snapshot["gorevler"], list)
            or not isinstance(snapshot["mesajlar"], list)
            or not isinstance(snapshot["ekranlar"], dict)):
        return error_response("snapshot_read_failed")
    if snapshot.get("ok") is not True:
        return error_response("snapshot_read_failed")

    group_budgets = dict(GROUP_BUDGETS if group_budgets is None else group_budgets)
    item_budgets = dict(ITEM_BUDGETS if item_budgets is None else item_budgets)
    if (set(group_budgets) != set(GROUP_FIELDS)
            or any(type(group_budgets[group]) is not int or group_budgets[group] < 2
                   for group in GROUP_FIELDS)
            or set(item_budgets) != set(GROUP_FIELDS)
            or any(value is not None and (type(value) is not int or value < 1)
                   for value in item_budgets.values())):
        return error_response("snapshot_response_unavailable")

    try:
        fixed = {field: _encode(snapshot[field]) for field in FIXED_FIELDS}
    except (TypeError, ValueError, UnicodeError):
        return error_response("snapshot_read_failed")
    empty_size = _empty_body_size(fixed)
    global_remaining = response_byte_budget - empty_size - (metadata_reserve - 2)
    if global_remaining < 0:
        return error_response("snapshot_response_unavailable")

    screen_order = (list(screen_order) if screen_order is not None
                    else list(snapshot["ekranlar"]))
    if (not all(isinstance(key, str) for key in screen_order)
            or len(set(screen_order)) != len(screen_order)
            or set(screen_order) != set(snapshot["ekranlar"])):
        return error_response("snapshot_response_unavailable")
    selected: dict[str, bytes] = {}
    included: dict[str, int] = {}
    omitted: dict[str, int] = {}
    all_reasons: set[str] = set()
    source_values = {
        "kullanicilar": snapshot["kullanicilar"],
        "gorevler": snapshot["gorevler"],
        "mesajlar": snapshot["mesajlar"],
        "ekranlar": snapshot["ekranlar"],
    }
    count_names = {
        "kullanicilar": "kullanicilar", "gorevler": "gorevler",
        "mesajlar": "mesajlar", "ekranlar": "ekran_dosyalari",
    }
    for group in GROUP_FIELDS:
        result = _select_group(
            group, source_values[group], group_budget=group_budgets[group],
            item_budget=item_budgets[group], global_remaining=global_remaining,
            screen_order=screen_order)
        selected[group], included[count_names[group]], omitted[count_names[group]], reasons, global_remaining = result
        all_reasons.update(reasons)

    screen_partial = snapshot["ekranlar_meta"].get("partial") is True
    if screen_partial:
        all_reasons.add("screen_output_partial")
    partial = any(omitted.values()) or screen_partial
    metadata = {
        "schema_version": 1,
        "partial": partial,
        "response_byte_budget": response_byte_budget,
        "included": included,
        "omitted": omitted,
        "partial_reasons": [reason for reason in REASON_ORDER if reason in all_reasons],
    }
    try:
        metadata_bytes = _encode(metadata)
    except (TypeError, ValueError, UnicodeError):
        return error_response("snapshot_response_unavailable")
    if len(metadata_bytes) > metadata_reserve:
        return error_response("snapshot_response_unavailable")

    fields = []
    for field in FIXED_FIELDS[:4]:
        fields.append(_encode(field) + b":" + fixed[field])
    for group in GROUP_FIELDS:
        fields.append(_encode(group) + b":" + selected[group])
    fields.append(_encode("ekranlar_meta") + b":" + fixed["ekranlar_meta"])
    fields.append(_encode("snapshot_meta") + b":" + metadata_bytes)
    body = b"{" + b",".join(fields) + b"}"
    if len(body) > response_byte_budget:
        return error_response("snapshot_response_unavailable")
    return SnapshotResponse(200, body)
