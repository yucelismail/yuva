"""Crash/restart contract fixture using only disposable temporary YUVA_DIRs."""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

from task_outbox import (CommitUnknown, IdempotencyConflict,
                         LedgerCompatibilityError, SimulatedCrash, TaskOutbox)


def _root(parent: str, case: str) -> Path:
    root = Path(parent, case)
    root.mkdir()
    (root / "gorevler.json").write_text(json.dumps({
        "schema_version": 1,
        "siradaki": 2,
        "gorevler": [{"id": 1, "baslik": "fixture task", "kimden": "fixture",
                       "assignee": "fixture-worker", "durum": "pending",
                       "gecmis": []}],
        "fixture_extension": {"preserve": True},
    }), encoding="utf-8")
    os.environ["YUVA_DIR"] = str(root)
    return root


def duplicate_operation(parent: str) -> dict[str, str]:
    root = _root(parent, "duplicate")
    stores = [TaskOutbox(os.environ["YUVA_DIR"]) for _ in range(2)]
    barrier = Barrier(2)

    def apply(store):
        barrier.wait(timeout=3)
        return store.apply_operation("op-1", 1, "assigned", "event-1", "assigned")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(apply, store) for store in stores]
        first, again = [future.result(timeout=5) for future in futures]
    assert first == again
    snapshot = stores[0].snapshot()
    task = snapshot["gorevler"][0]
    assert task["durum"] == "assigned"
    assert len(task["gecmis"]) == 1
    assert len(snapshot["operations"]) == 1
    assert len(snapshot["outbox"]) == 1
    assert snapshot["siradaki"] == 2
    assert snapshot["fixture_extension"] == {"preserve": True}
    try:
        stores[0].apply_operation("op-1", 1, "cancelled", "event-1", "assigned")
    except IdempotencyConflict:
        pass
    else:
        raise AssertionError("same operation ID with changed request must conflict")
    return {"case": "duplicate_operation", "state": "one_commit_conflict_on_reuse"}


def schema_compatibility_gate(parent: str) -> dict[str, str]:
    root = _root(parent, "schema-v1-compat")
    ledger_path = root / "gorevler.json"
    legacy = json.loads(ledger_path.read_text(encoding="utf-8"))
    legacy.pop("schema_version")
    ledger_path.write_text(json.dumps(legacy), encoding="utf-8")
    store = TaskOutbox(os.environ["YUVA_DIR"])
    store.apply_operation("op-v1", 1, "assigned", "event-v1", "assigned")
    v1 = store.snapshot()
    assert v1["schema_version"] == 1
    assert v1["siradaki"] == 2
    assert v1["gorevler"][0]["baslik"] == "fixture task"
    assert v1["fixture_extension"] == {"preserve": True}

    future_root = Path(parent, "schema-unknown")
    future_root.mkdir()
    future_path = future_root / "gorevler.json"
    future_path.write_text(json.dumps(dict(legacy, schema_version=2)), encoding="utf-8")
    os.environ["YUVA_DIR"] = str(future_root)
    future_store = TaskOutbox(os.environ["YUVA_DIR"])
    before = future_path.read_bytes()
    try:
        future_store.apply_operation("op-v2", 1, "assigned", "event-v2", "assigned")
    except LedgerCompatibilityError:
        pass
    else:
        raise AssertionError("unknown schema must fail closed before any ledger write")
    assert future_path.read_bytes() == before

    malformed_root = Path(parent, "schema-malformed")
    malformed_root.mkdir()
    malformed_path = malformed_root / "gorevler.json"
    malformed_path.write_text(json.dumps(dict(legacy, schema_version=1,
                                              gorevler=[{"id": True}])),
                              encoding="utf-8")
    os.environ["YUVA_DIR"] = str(malformed_root)
    malformed_store = TaskOutbox(os.environ["YUVA_DIR"])
    malformed_before = malformed_path.read_bytes()
    try:
        malformed_store.apply_operation("op-malformed", 1, "assigned",
                                        "event-malformed", "assigned")
    except LedgerCompatibilityError:
        pass
    else:
        raise AssertionError("malformed v1 task shape must fail closed")
    assert malformed_path.read_bytes() == malformed_before
    return {"case": "schema_compatibility_gate",
            "state": "legacy_v1_additive_write_unknown_and_malformed_unchanged"}


def replace_fsync_uncertainty(parent: str) -> dict[str, str]:
    root = _root(parent, "replace-fsync")
    store = TaskOutbox(os.environ["YUVA_DIR"])
    store.faults.add("directory_fsync")
    try:
        store.apply_operation("op-2", 1, "delivered", "event-2", "done")
    except CommitUnknown:
        pass
    else:
        raise AssertionError("post-replace directory fsync fault must be commit_unknown")
    reopened = TaskOutbox(os.environ["YUVA_DIR"])
    receipt = reopened.lookup("op-2")
    assert receipt is not None and receipt["status"] == "committed"
    snapshot = reopened.snapshot()
    assert snapshot["gorevler"][0]["durum"] == "delivered"
    assert len(snapshot["gorevler"][0]["gecmis"]) == 1
    assert len(snapshot["operations"]) == len(snapshot["outbox"]) == 1
    assert reopened.message_records() == []
    return {"case": "replace_fsync_uncertainty", "state": "commit_unknown_reconciled_by_operation_id"}


def append_then_crash_restart(parent: str) -> dict[str, str]:
    root = _root(parent, "append-crash")
    store = TaskOutbox(os.environ["YUVA_DIR"])
    store.apply_operation("op-3", 1, "delivered", "event-3", "done")
    store.faults.add("after_append")
    try:
        store.deliver_pending()
    except SimulatedCrash:
        pass
    else:
        raise AssertionError("fixture must crash after durable append")
    assert len(store.message_records()) == 1
    reopened = TaskOutbox(os.environ["YUVA_DIR"])
    result = reopened.deliver_pending()
    assert result == [{"event_id": "event-3", "state": "delivered_readback"}]
    assert len(reopened.message_records()) == 1
    assert reopened.snapshot()["outbox"][0]["delivery"] == "delivered"
    assert reopened.lookup("op-3")["notification"] == "delivered"
    return {"case": "append_then_crash_restart", "state": "readback_without_duplicate_append"}


def append_fsync_uncertainty(parent: str) -> dict[str, str]:
    root = _root(parent, "append-fsync")
    store = TaskOutbox(os.environ["YUVA_DIR"])
    store.apply_operation("op-5", 1, "assigned", "event-5", "assigned")
    store.faults.add("append_fsync")
    first = store.deliver_pending()
    assert first == [{"event_id": "event-5", "state": "delivery_unknown"}]
    before = store.messages_path.read_bytes()
    reopened = TaskOutbox(os.environ["YUVA_DIR"])
    recovered = reopened.deliver_pending()
    assert recovered == [{"event_id": "event-5", "state": "delivered_readback"}]
    assert reopened.messages_path.read_bytes() == before
    assert len(reopened.message_records()) == 1
    return {"case": "append_fsync_uncertainty", "state": "readback_resolved_without_retry"}


def ambiguous_absence_never_retries(parent: str) -> dict[str, str]:
    root = _root(parent, "append-unknown-absent")
    store = TaskOutbox(os.environ["YUVA_DIR"])
    store.apply_operation("op-8", 1, "assigned", "event-8", "assigned")
    store.faults.add("append_before_write")
    first = store.deliver_pending()
    assert first == [{"event_id": "event-8", "state": "delivery_unknown"}]
    assert store.messages_path.read_bytes() == b""
    reopened = TaskOutbox(os.environ["YUVA_DIR"])
    again = reopened.deliver_pending()
    assert again == [{"event_id": "event-8", "state": "delivery_unknown"}]
    assert reopened.messages_path.read_bytes() == b""

    # A readback error is also ambiguous. A later empty read cannot authorize
    # appending because the earlier lookup outcome was not trustworthy.
    readback_root = _root(parent, "readback-unknown-absent")
    readback_store = TaskOutbox(os.environ["YUVA_DIR"])
    readback_store.apply_operation("op-9", 1, "assigned", "event-9", "assigned")
    readback_store.faults.add("readback_error")
    first_readback = readback_store.deliver_pending()
    assert first_readback == [{"event_id": "event-9", "state": "delivery_unknown"}]
    later = readback_store.deliver_pending()
    assert later == [{"event_id": "event-9", "state": "delivery_unknown"}]
    assert readback_store.messages_path.read_bytes() == b""
    return {"case": "ambiguous_absence_never_retries",
            "state": "unknown_append_and_readback_absence_stay_no_retry"}


def corrupt_tail_no_retry(parent: str) -> dict[str, str]:
    root = _root(parent, "corrupt-tail")
    store = TaskOutbox(os.environ["YUVA_DIR"])
    store.apply_operation("op-4", 1, "assigned", "event-4", "assigned")
    with store.messages_path.open("ab") as stream:
        stream.write(b'{"id":"partial"')
        stream.flush()
        os.fsync(stream.fileno())
    before = store.messages_path.read_bytes()
    first = store.deliver_pending()
    after_first = store.messages_path.read_bytes()
    second = store.deliver_pending()
    after_second = store.messages_path.read_bytes()
    assert first == [{"event_id": "event-4", "state": "delivery_unknown"}]
    assert second == [{"event_id": "event-4", "state": "delivery_unknown"}]
    assert before == after_first == after_second
    assert store.snapshot()["outbox"][0]["delivery"] == "delivery_unknown"
    assert store.lookup("op-4")["notification"] == "delivery_unknown"
    return {"case": "corrupt_tail_no_retry", "state": "delivery_unknown_append_stopped"}


def event_readback_conflicts_no_retry(parent: str) -> dict[str, str]:
    cases = (
        ("event-conflict", [b'{"id":"event-6","metin":"conflicting"}\n']),
        ("event-duplicate", [b'{"id":"event-7","metin":"same"}\n'] * 2),
    )
    for name, lines in cases:
        root = _root(parent, name)
        event_id = "event-6" if name == "event-conflict" else "event-7"
        store = TaskOutbox(os.environ["YUVA_DIR"])
        store.apply_operation(f"op-{event_id}", 1, "assigned", event_id, "expected")
        store.messages_path.write_bytes(b"".join(lines))
        before = store.messages_path.read_bytes()
        first = store.deliver_pending()
        second = store.deliver_pending()
        assert first == second == [{"event_id": event_id, "state": "delivery_unknown"}]
        assert store.messages_path.read_bytes() == before
        assert store.snapshot()["outbox"][0]["delivery"] == "delivery_unknown"
    return {"case": "event_readback_conflicts_no_retry",
            "state": "conflict_and_duplicate_event_ids_stay_unknown"}


def main() -> None:
    cases = (schema_compatibility_gate, duplicate_operation, replace_fsync_uncertainty,
             append_then_crash_restart, append_fsync_uncertainty,
             ambiguous_absence_never_retries,
             corrupt_tail_no_retry, event_readback_conflicts_no_retry)
    with tempfile.TemporaryDirectory(prefix="yuva-task-outbox-") as temp_root:
        results = [case(temp_root) for case in cases]
    # Avoid printing temporary paths or fixture contents.
    print(json.dumps({"fixture": "task-outbox-crash-restart-v1",
                      "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
