"""Fixture projection that keeps lease owner claims separate from identity."""

from __future__ import annotations

from collections.abc import Mapping


def project_task(task_snapshot: Mapping[str, object], *,
                 verified_request_principal: str | None = None,
                 cli_from_claim: str | None = None) -> dict:
    """Build CLI, API and UI examples without deriving identity from task data.

    `verified_request_principal` is an out-of-band value supplied by a trusted
    API authentication adapter. It identifies the requester only; this module
    has no lease-to-principal binding evidence.
    """
    if not isinstance(task_snapshot, Mapping):
        raise ValueError("task snapshot must be a mapping")
    task_id = task_snapshot.get("id")
    task_id = task_id if type(task_id) is int and task_id > 0 else None
    execution = task_snapshot.get("execution")
    execution = execution if isinstance(execution, Mapping) else {}

    owner_claim = execution.get("owner_claim")
    if not isinstance(owner_claim, str) or not owner_claim.strip():
        owner_claim = "unknown"
    epoch = execution.get("lease_epoch")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        epoch = None

    request_actor = None
    if (isinstance(verified_request_principal, str)
            and verified_request_principal.strip()):
        request_actor = {
            "principal_id": verified_request_principal,
            "trust": "verified_by_api_adapter",
            "relation_to_lease_owner": "not_established",
        }

    history = task_snapshot.get("gecmis")
    history_view = []
    if isinstance(history, list):
        for event in history:
            if not isinstance(event, Mapping):
                continue
            actor_claim = event.get("kimden", "unknown")
            if not isinstance(actor_claim, str):
                actor_claim = "unknown"
            note = event.get("not", "")
            if not isinstance(note, str):
                note = ""
            kind = event.get("olay", "unknown")
            if not isinstance(kind, str):
                kind = "unknown"
            history_view.append({
                "actor_claim": actor_claim,
                "actor_label": f"Beyan edilen aktör: {actor_claim}",
                "actor_trust": "unverified",
                "role": "unknown",
                "event": kind,
                "note": note,
            })

    owner_view = {
        "owner_claim": owner_claim,
        "claim_label": f"Beyan edilen lease sahibi: {owner_claim}",
        "claim_trust": "unverified",
        "verified_principal": None,
        "identity_status": "unknown",
        "role": "unknown",
        "presence": "unknown",
        "authority_scope": "none",
        "lease_epoch": epoch,
    }
    api_view = {
        "task_id": task_id,
        "lease_owner": owner_view,
        "request_actor": request_actor,
        "history": history_view,
    }
    cli_lines = [owner_view["claim_label"] + " (doğrulanmadı)"]
    if epoch is not None:
        cli_lines[0] += f" · epoch {epoch}"
    if not isinstance(cli_from_claim, str) or not cli_from_claim.strip():
        cli_from_claim = "unknown"
    cli_lines.extend((f"CLI --from beyanı: {cli_from_claim} (doğrulanmadı)",
                      "Kimlik: unknown · rol: unknown · presence: unknown",
                      "Yetki kapsamı: none"))
    ui_view = {
        "owner_label": owner_view["claim_label"],
        "owner_badge": "beyan · doğrulanmadı",
        "identity_label": "Doğrulanmış lease principal: yok",
        "role_label": "Rol: bilinmiyor",
        "presence_label": "Presence: bilinmiyor",
        "authority_label": "Görev/araç yetkisi: yok",
        "request_actor_label": (
            f"API isteği principal'ı: {verified_request_principal} · doğrulanmış"
            if request_actor else "API isteği principal'ı: doğrulanmadı")
            + (" · lease owner bağı kurulmamış" if request_actor else ""),
        "history": history_view,
    }
    return {"cli": cli_lines, "api": api_view, "ui": ui_view}
