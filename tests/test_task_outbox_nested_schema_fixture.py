"""Focused disposable fixture checks for bounded nested task outbox fields."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "prototypes" / "task-outbox" / "outbox_schema.py"
SPEC = importlib.util.spec_from_file_location("yuva_outbox_schema_fixture", SCHEMA_PATH)
schema = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = schema
SPEC.loader.exec_module(schema)
sys.path.insert(0, str(SCHEMA_PATH.parent))
from task_outbox import LedgerCompatibilityError, TaskOutbox  # noqa: E402


def valid_snapshot():
    digest = hashlib.sha256(b"synthetic-request").hexdigest()
    return {
        "schema_version": 1,
        "siradaki": 2,
        "gorevler": [{"id": 1, "baslik": "synthetic", "kimden": "fixture",
                       "durum": "pending", "gecmis": []}],
        "operations": {
            "op-1": {
                "request_digest": digest,
                "operation": "task.status",
                "task_id": 1,
                "status": "committed",
                "result": {"task_id": 1, "task_status": "assigned"},
                "transition_event_id": "task:op-1",
                "notification_event_id": "event-1",
                "notification": "pending",
            },
        },
        "outbox": [{
            "event_id": "event-1",
            "operation_id": "op-1",
            "task_id": 1,
            "kind": "task.status",
            "message": "synthetic notice",
            "delivery": "pending",
        }],
        "unknown_root_extension": {"preserve": True},
    }


class TaskOutboxNestedSchemaFixtureTests(unittest.TestCase):
    def test_temp_ledger_accepts_contract_and_preserves_unknown_root_field(self):
        with tempfile.TemporaryDirectory(prefix="yuva-outbox-schema-") as temp:
            path = Path(temp, "gorevler.json")
            value = valid_snapshot()
            schema.validate_extensions(value)
            path.write_text(json.dumps(value), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
            schema.validate_extensions(loaded)
            self.assertEqual(loaded["unknown_root_extension"], {"preserve": True})

    def test_duplicate_event_id_and_duplicate_event_for_operation_rejected(self):
        value = valid_snapshot()
        value["outbox"].append(dict(value["outbox"][0]))
        with self.assertRaises(schema.OutboxSchemaError):
            schema.validate_extensions(value)

        value = valid_snapshot()
        value["outbox"].append({**value["outbox"][0], "event_id": "event-2"})
        with self.assertRaises(schema.OutboxSchemaError):
            schema.validate_extensions(value)

    def test_unknown_nested_field_and_wrong_scalar_type_rejected(self):
        for mutate in (
            lambda value: value["operations"]["op-1"].update(extra="unknown"),
            lambda value: value["operations"]["op-1"].update(task_id=True),
            lambda value: value["outbox"][0].update(delivery="future"),
        ):
            value = valid_snapshot()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(schema.OutboxSchemaError):
                schema.validate_extensions(value)

    def test_message_and_canonical_entry_byte_caps_rejected(self):
        value = valid_snapshot()
        value["outbox"][0]["message"] = "x" * (schema.MAX_MESSAGE_BYTES + 1)
        with self.assertRaises(schema.OutboxSchemaError):
            schema.validate_extensions(value)

        value = valid_snapshot()
        value["operations"]["op-1"]["result"]["task_status"] = "x" * schema.MAX_ENTRY_BYTES
        with self.assertRaises(schema.OutboxSchemaError):
            schema.validate_extensions(value)

    def test_operation_and_event_count_caps_are_enforced(self):
        value = valid_snapshot()
        value["operations"] = {
            f"op-{index}": dict(value["operations"]["op-1"])
            for index in range(schema.MAX_OPERATIONS + 1)
        }
        value["outbox"] = []
        with self.assertRaises(schema.OutboxSchemaError):
            schema.validate_extensions(value)

        value = valid_snapshot()
        value["outbox"] *= (schema.MAX_OUTBOX_EVENTS + 1)
        with self.assertRaises(schema.OutboxSchemaError):
            schema.validate_extensions(value)

    def test_fixture_reader_rejects_nested_schema_and_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory(prefix="yuva-outbox-schema-read-") as temp:
            store = TaskOutbox(temp)
            path = Path(temp, "gorevler.json")
            malformed = valid_snapshot()
            malformed["operations"]["op-1"]["unexpected"] = "unknown"
            raw = json.dumps(malformed).encode("utf-8")
            path.write_bytes(raw)
            with self.assertRaises(LedgerCompatibilityError):
                store.apply_operation("new-op", 1, "assigned", "new-event", "notice")
            self.assertEqual(path.read_bytes(), raw)

            duplicate_key = (
                b'{"schema_version":1,"siradaki":1,"gorevler":[],'
                b'"operations":{"op-1":{},"op-1":{}},"outbox":[]}')
            path.write_bytes(duplicate_key)
            with self.assertRaises(LedgerCompatibilityError):
                store.apply_operation("new-op", 1, "assigned", "new-event", "notice")
            self.assertEqual(path.read_bytes(), duplicate_key)


if __name__ == "__main__":
    unittest.main()
