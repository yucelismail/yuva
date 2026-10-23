import json
import unittest

from prototypes.panel_snapshot_budget import snapshot_budget as budget


def empty_snapshot():
    return {
        "ok": True,
        "simdi": "fixture-now",
        "online_sn": 30,
        "rev": 1,
        "kullanicilar": {},
        "gorevler": [],
        "mesajlar": [],
        "ekranlar": {},
        "ekranlar_meta": {"partial": False, "selection_mode": "fixture"},
    }


def generous_groups(value=16 * 1024):
    return {name: value for name in budget.GROUP_FIELDS}


def json_value(response):
    return json.loads(response.body.decode("utf-8"))


class PanelSnapshotBudgetTests(unittest.TestCase):
    def test_empty_success_is_distinct_from_source_errors(self):
        empty = budget.build_response(empty_snapshot(), response_byte_budget=2048,
                                      group_budgets=generous_groups(),
                                      metadata_reserve=256)
        self.assertEqual(empty.status, 200)
        self.assertTrue(json_value(empty)["ok"])
        self.assertFalse(json_value(empty)["snapshot_meta"]["partial"])

        source_error = budget.error_response("snapshot_read_failed")
        source_limit = budget.error_response("snapshot_source_limit")
        self.assertEqual((source_error.status, source_limit.status), (500, 503))
        self.assertFalse(json_value(source_error)["ok"])
        self.assertFalse(json_value(source_limit)["ok"])
        self.assertNotIn("snapshot_meta", json_value(source_error))

    def test_ascii_and_multibyte_utf8_use_exact_wire_bytes_at_boundary(self):
        snapshot = empty_snapshot()
        snapshot["mesajlar"] = [{"id": "m1", "metin": "é🙂" * 7}]
        broad = budget.build_response(snapshot, response_byte_budget=4096,
                                      group_budgets=generous_groups(),
                                      metadata_reserve=512)
        self.assertEqual(broad.status, 200)
        decoded_text = broad.body.decode("utf-8")
        self.assertGreater(broad.content_length, len(decoded_text))
        self.assertEqual(broad.content_length, len(broad.body))

        metadata = json_value(broad)["snapshot_meta"]
        metadata_bytes = len(json.dumps(
            metadata, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False).encode("utf-8"))
        exact = budget.build_response(
            snapshot, response_byte_budget=broad.content_length,
            group_budgets=generous_groups(), metadata_reserve=metadata_bytes)
        self.assertEqual(exact.status, 200)
        self.assertLessEqual(exact.content_length, broad.content_length)
        self.assertEqual(json_value(exact)["mesajlar"], snapshot["mesajlar"])

        message_group_bytes = len(json.dumps(
            snapshot["mesajlar"], ensure_ascii=False, separators=(",", ":"),
            allow_nan=False).encode("utf-8"))
        exact_group_caps = generous_groups()
        exact_group_caps["mesajlar"] = message_group_bytes
        exact_group = budget.build_response(
            snapshot, response_byte_budget=4096,
            group_budgets=exact_group_caps, metadata_reserve=512)
        self.assertEqual(json_value(exact_group)["mesajlar"], snapshot["mesajlar"])

        one_byte_short_caps = dict(exact_group_caps)
        one_byte_short_caps["mesajlar"] = message_group_bytes - 1
        partial = budget.build_response(
            snapshot, response_byte_budget=4096,
            group_budgets=one_byte_short_caps, metadata_reserve=512)
        self.assertEqual(partial.status, 200)
        self.assertLessEqual(partial.content_length, broad.content_length - 1)
        body = json_value(partial)
        self.assertTrue(body["snapshot_meta"]["partial"])
        self.assertEqual(body["snapshot_meta"]["omitted"]["mesajlar"], 1)
        self.assertEqual(body["mesajlar"], [])

    def test_global_budget_caps_all_groups_and_repeated_selection_is_stable(self):
        snapshot = empty_snapshot()
        snapshot["kullanicilar"] = {
            f"user-{i:02}": {"ad": "Ü" * 35, "rol": "worker"}
            for i in range(12)
        }
        snapshot["gorevler"] = [
            {"id": i, "durum": "pending", "detay": "çalışma" * 35}
            for i in range(20)
        ]
        snapshot["mesajlar"] = [
            {"id": f"m{i}", "metin": "漢字🙂" * 22} for i in range(30)
        ]
        snapshot["ekranlar"] = {
            "worker-a": ["satır-α" * 20],
            "worker-b": ["satır-β" * 20],
        }
        caps = {
            "kullanicilar": 1500, "gorevler": 1500,
            "mesajlar": 1500, "ekranlar": 1500,
        }
        kwargs = dict(response_byte_budget=4096, group_budgets=caps,
                      metadata_reserve=512, screen_order=["worker-b", "worker-a"])
        first = budget.build_response(snapshot, **kwargs)
        second = budget.build_response(snapshot, **kwargs)
        self.assertEqual(first.status, 200)
        self.assertEqual(first.body, second.body)
        self.assertLessEqual(first.content_length, kwargs["response_byte_budget"])
        result = json_value(first)
        self.assertTrue(result["snapshot_meta"]["partial"])
        self.assertEqual(result["snapshot_meta"]["included"]["ekran_dosyalari"],
                         len(result["ekranlar"]))
        self.assertEqual(list(result["ekranlar"]), [
            key for key in kwargs["screen_order"] if key in result["ekranlar"]])
        self.assertEqual(result["ekranlar_meta"]["selection_mode"], "fixture")

        # Selection prioritizes the newest tasks, while output retains source order.
        task_snapshot = empty_snapshot()
        task_snapshot["gorevler"] = [
            {"id": i, "durum": "pending", "detay": "x" * 70}
            for i in range(8)
        ]
        task_caps = {name: 2 for name in budget.GROUP_FIELDS}
        task_caps["gorevler"] = 250
        selected = budget.build_response(
            task_snapshot, response_byte_budget=4096,
            group_budgets=task_caps, metadata_reserve=512)
        selected_tasks = json_value(selected)["gorevler"]
        self.assertGreater(len(selected_tasks), 0)
        self.assertEqual([task["id"] for task in selected_tasks],
                         sorted(task["id"] for task in selected_tasks))

    def test_record_and_group_caps_skip_whole_items_then_try_smaller_candidates(self):
        snapshot = empty_snapshot()
        snapshot["kullanicilar"] = {
            "a-large": {"ad": "x" * 80},
            "b-small": {"ad": "ok"},
        }
        caps = {name: 2 for name in budget.GROUP_FIELDS}
        caps["kullanicilar"] = 64
        item_caps = dict(budget.ITEM_BUDGETS)
        item_caps["kullanicilar"] = 40
        result = budget.build_response(
            snapshot, response_byte_budget=2048, group_budgets=caps,
            item_budgets=item_caps, metadata_reserve=256)
        self.assertEqual(result.status, 200)
        body = json_value(result)
        self.assertEqual(body["kullanicilar"], {"b-small": {"ad": "ok"}})
        self.assertEqual(body["snapshot_meta"]["included"]["kullanicilar"], 1)
        self.assertEqual(body["snapshot_meta"]["omitted"]["kullanicilar"], 1)
        self.assertIn("record_size_limit", body["snapshot_meta"]["partial_reasons"])

    def test_existing_message_count_and_screen_partial_limits_are_preserved(self):
        snapshot = empty_snapshot()
        snapshot["mesajlar"] = [{"id": str(i), "metin": "m"} for i in range(205)]
        snapshot["ekranlar"] = {f"file-{i}": [f"line-{i}"] for i in range(3)}
        snapshot["ekranlar_meta"]["partial"] = True
        snapshot["ekranlar_meta"]["partial_reasons"] = ["file_count_limit"]
        caps = {name: 16 * 1024 for name in budget.GROUP_FIELDS}
        result = budget.build_response(
            snapshot, response_byte_budget=16 * 1024, group_budgets=caps,
            metadata_reserve=512, screen_order=["file-2", "file-0", "file-1"])
        self.assertEqual(result.status, 200)
        body = json_value(result)
        self.assertEqual(len(body["mesajlar"]), 200)
        self.assertEqual(body["mesajlar"][0]["id"], "5")
        self.assertEqual(body["mesajlar"][-1]["id"], "204")
        self.assertEqual(body["snapshot_meta"]["omitted"]["mesajlar"], 0)
        self.assertTrue(body["snapshot_meta"]["partial"])
        self.assertIn("screen_output_partial", body["snapshot_meta"]["partial_reasons"])


if __name__ == "__main__":
    unittest.main()
