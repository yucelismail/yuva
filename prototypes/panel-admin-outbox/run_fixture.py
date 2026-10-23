"""Synthetic state/audit outbox scenarios; all data stays in TemporaryDirectory."""

from __future__ import annotations

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from admin_outbox import (CommitUnknown, IdempotencyConflict, PanelAdminOutbox,
                          SimulatedCrash)


def root(parent: str, name: str) -> Path:
    path = Path(parent, name)
    path.mkdir()
    return path


def duplicate_and_conflict(parent: str) -> dict[str, str]:
    path = root(parent, "duplicate-conflict")
    store = PanelAdminOutbox(path)
    peer = PanelAdminOutbox(path)
    barrier = Barrier(2)

    def apply(target: PanelAdminOutbox):
        barrier.wait(timeout=3)
        return target.apply("op-duplicate", "synthetic-target", "synthetic-owner")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, again = [future.result(timeout=5)
                        for future in (pool.submit(apply, store), pool.submit(apply, peer))]
    assert first == again
    snapshot = store.snapshot()
    assert snapshot["rev"] == 1
    assert len(snapshot["operations"]) == len(snapshot["outbox"]) == 1
    before = store.state_path.read_bytes()
    try:
        store.apply("op-duplicate", "synthetic-target", "different-owner")
    except IdempotencyConflict:
        pass
    else:
        raise AssertionError("same operation ID with changed request must conflict")
    assert store.state_path.read_bytes() == before
    delivered = store.deliver_pending()
    assert delivered == [{"event_id": first["event_id"], "state": "delivered"}]
    replay = store.apply("op-duplicate", "synthetic-target", "synthetic-owner")
    assert replay["event_id"] == first["event_id"]
    assert replay["result"] == first["result"]
    assert replay["audit_delivery"] == "delivered"
    assert len(store.audit_events()) == 1
    return {"case": "duplicate_and_conflict", "state": "one_commit_one_exact_event"}


def state_commit_unknown(parent: str) -> dict[str, str]:
    path = root(parent, "state-commit-unknown")
    store = PanelAdminOutbox(path)
    store.faults.add("state_directory_fsync")
    try:
        store.apply("op-commit-unknown", "synthetic-target", "synthetic-owner")
    except CommitUnknown:
        pass
    else:
        raise AssertionError("post-replace directory fsync must be commit_unknown")
    before = store.state_path.read_bytes()
    reopened = PanelAdminOutbox(path)
    receipt = reopened.apply("op-commit-unknown", "synthetic-target", "synthetic-owner")
    assert receipt["status"] == "committed"
    assert reopened.state_path.read_bytes() == before
    assert reopened.audit_events() == []
    return {"case": "state_commit_unknown", "state": "receipt_readback_no_second_mutation"}


def state_fd_close_and_lock_fd_close(parent: str) -> dict[str, str]:
    path = root(parent, "state-directory-close")
    store = PanelAdminOutbox(path)
    store.faults.add("state_directory_close")
    try:
        store.apply("op-state-close", "synthetic-target", "synthetic-owner")
    except CommitUnknown:
        pass
    else:
        raise AssertionError("post-replace directory FD close error must be commit_unknown")
    committed = store.snapshot()
    assert committed["rev"] == 1
    assert len(committed["operations"]) == len(committed["outbox"]) == 1
    assert list(path.glob(".durum.*.tmp")) == []
    assert store.audit_events() == []

    lock_path = root(parent, "lock-fd-close")
    lock_store = PanelAdminOutbox(lock_path, faults={"lock_fd_close"})
    try:
        lock_store.apply("op-lock-close", "synthetic-target", "synthetic-owner")
    except OSError as exc:
        assert "lock descriptor close" in str(exc)
    else:
        raise AssertionError("injected lock FD close error must reach the caller")
    before = lock_store.state_path.read_bytes()
    replay = PanelAdminOutbox(lock_path).apply(
        "op-lock-close", "synthetic-target", "synthetic-owner")
    after = lock_store.state_path.read_bytes()
    assert before == after
    assert replay["status"] == "committed"
    assert lock_store.snapshot()["rev"] == 1
    assert len(lock_store.snapshot()["outbox"]) == 1
    return {"case": "state_fd_close_and_lock_fd_close",
            "state": "post_replace_unknown_and_lock_released_idempotently"}


def append_crash_and_fsync(parent: str) -> dict[str, str]:
    path = root(parent, "append-crash")
    faults = {"after_append_crash"}
    store = PanelAdminOutbox(path, faults=faults)
    receipt = store.apply("op-after-append", "synthetic-target", "synthetic-owner")
    try:
        store.deliver_pending()
    except SimulatedCrash:
        pass
    else:
        raise AssertionError("fixture must crash after append before marker")
    assert len(store.audit_events()) == 1
    reopened = PanelAdminOutbox(path)
    result = reopened.deliver_pending()
    assert result == [{"event_id": receipt["event_id"],
                       "state": "delivered_readback"}]
    assert len(reopened.audit_events()) == 1
    assert reopened.snapshot()["operations"]["op-after-append"]["audit_delivery"] == "delivered"

    fsync_path = root(parent, "append-fsync-unknown")
    fsync_store = PanelAdminOutbox(fsync_path, faults={"append_fsync"})
    fsync_receipt = fsync_store.apply("op-append-fsync", "synthetic-target", "synthetic-owner")
    first = fsync_store.deliver_pending()
    assert first == [{"event_id": fsync_receipt["event_id"], "state": "delivery_unknown"}]
    before = fsync_store.audit_path.read_bytes()
    restarted = PanelAdminOutbox(fsync_path)
    second = restarted.deliver_pending()
    assert second == [{"event_id": fsync_receipt["event_id"],
                       "state": "delivered_readback"}]
    assert restarted.audit_path.read_bytes() == before
    return {"case": "append_crash_and_fsync", "state": "exact_readback_without_duplicate"}


def uncertain_absence_never_retries(parent: str) -> dict[str, str]:
    path = root(parent, "uncertain-append-absent")
    store = PanelAdminOutbox(path, faults={"append_before_write"})
    receipt = store.apply("op-append-absent", "synthetic-target", "synthetic-owner")
    first = store.deliver_pending()
    assert first == [{"event_id": receipt["event_id"], "state": "delivery_unknown"}]
    assert store.audit_path.read_bytes() == b""
    reopened = PanelAdminOutbox(path)
    second = reopened.deliver_pending()
    assert second == [{"event_id": receipt["event_id"], "state": "delivery_unknown"}]
    assert reopened.audit_path.read_bytes() == b""
    return {"case": "uncertain_absence_never_retries", "state": "unknown_no_blind_append"}


def partial_append_and_readback_io(parent: str) -> dict[str, str]:
    partial_path = root(parent, "partial-append")
    partial = PanelAdminOutbox(partial_path, faults={"partial_append"})
    receipt = partial.apply("op-partial", "synthetic-target", "synthetic-owner")
    first = partial.deliver_pending()
    assert first == [{"event_id": receipt["event_id"], "state": "delivery_unknown"}]
    before = partial.audit_path.read_bytes()
    assert before and not before.endswith(b"\n")
    second = PanelAdminOutbox(partial_path).deliver_pending()
    assert second == [{"event_id": receipt["event_id"], "state": "delivery_unknown"}]
    assert partial.audit_path.read_bytes() == before
    assert partial.snapshot()["outbox"][0]["delivery"] == "delivery_unknown"

    readback_path = root(parent, "readback-io")
    readback = PanelAdminOutbox(readback_path, faults={"readback_error"})
    readback_receipt = readback.apply(
        "op-readback-io", "synthetic-target", "synthetic-owner")
    first_readback = readback.deliver_pending()
    assert first_readback == [{"event_id": readback_receipt["event_id"],
                               "state": "delivery_unknown"}]
    assert readback.audit_path.read_bytes() == b""
    retry = PanelAdminOutbox(readback_path).deliver_pending()
    assert retry == [{"event_id": readback_receipt["event_id"],
                      "state": "delivery_unknown"}]
    assert readback.audit_path.read_bytes() == b""
    return {"case": "partial_append_and_readback_io",
            "state": "malformed_tail_and_readback_error_no_retry"}


def conflict_duplicate_malformed_readback(parent: str) -> dict[str, str]:
    for name, record in (
        ("body-conflict", {"id": "placeholder", "operation_id": "wrong",
                            "operation": "sorumlu.set", "target_id": "synthetic-target",
                            "before": None, "after": "unexpected"}),
        ("duplicate-id", None),
        ("malformed-tail", b'{"id":"incomplete"'),
    ):
        path = root(parent, name)
        store = PanelAdminOutbox(path)
        receipt = store.apply(f"op-{name}", "synthetic-target", "synthetic-owner")
        event = store.snapshot()["outbox"][0]
        expected = {key: event[key] for key in
                    ("id", "operation_id", "operation", "target_id", "before", "after")}
        if name == "body-conflict":
            record = {**record, "id": receipt["event_id"]}
            store.audit_path.write_bytes(json.dumps(record).encode("utf-8") + b"\n")
        elif name == "duplicate-id":
            raw = json.dumps(expected, separators=(",", ":")).encode("utf-8") + b"\n"
            store.audit_path.write_bytes(raw + raw)
        else:
            store.audit_path.write_bytes(record)
        before = store.audit_path.read_bytes()
        result = store.deliver_pending()
        assert result == [{"event_id": receipt["event_id"],
                           "state": "delivery_unknown"}]
        assert store.audit_path.read_bytes() == before
    return {"case": "conflict_duplicate_malformed_readback",
            "state": "unknown_without_append"}


def main() -> None:
    cases = (duplicate_and_conflict, state_commit_unknown,
             state_fd_close_and_lock_fd_close, append_crash_and_fsync,
             uncertain_absence_never_retries, partial_append_and_readback_io,
             conflict_duplicate_malformed_readback)
    with tempfile.TemporaryDirectory(prefix="yuva-admin-outbox-") as temp:
        results = [case(temp) for case in cases]
    print(json.dumps({"fixture": "panel-admin-state-audit-outbox-v1",
                      "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
