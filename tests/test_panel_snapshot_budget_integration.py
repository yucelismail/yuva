import http.client
import importlib.util
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "panel" / "server.py"


def load_panel(name):
    spec = importlib.util.spec_from_file_location(
        name, SERVER_PATH, loader=SourceFileLoader(name, str(SERVER_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PanelSnapshotBudgetIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-panel-budget-integration-")
        self.data = Path(self.temp.name) / "yuva"
        self.data.mkdir(mode=0o700)
        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(self.data),
            "YUVA_AUTH_ENABLED": "0",
        })
        self.env.start()
        os.environ.pop("YUVA_SNAPSHOT_BUDGET_ENABLED", None)
        self.panel = load_panel(f"yuva_panel_budget_integration_{id(self)}")
        self.old_handler = (self.panel.H.AUTH_GATE, self.panel.H.BROWSER_SESSION_GATE,
                            self.panel.H.SUNUCU_PORT, self.panel.H.IZINLI_HOSTLAR)
        self.panel.H.AUTH_GATE = None
        class FixtureBrowserSessionGate:
            def authorize_get(_self, route, scope, cookie):
                return cookie == "yuva_session=fixture-session"
        self.panel.H.BROWSER_SESSION_GATE = FixtureBrowserSessionGate()
        self.panel.H.IZINLI_HOSTLAR = {"localhost", "127.0.0.1"}
        self.server = self.panel.Sunucu(("127.0.0.1", 0), self.panel.H)
        self.panel.H.SUNUCU_PORT = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=False)
        self.thread.start()
        self._write_json("durum.json", {
            "schema_version": 1, "rev": 1, "kullanicilar": {}})
        self._write_json("gorevler.json", {
            "schema_version": 1, "siradaki": 1, "gorevler": []})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        (self.panel.H.AUTH_GATE, self.panel.H.BROWSER_SESSION_GATE,
         self.panel.H.SUNUCU_PORT,
         self.panel.H.IZINLI_HOSTLAR) = self.old_handler
        self.env.stop()
        self.temp.cleanup()

    def _write_json(self, name, value):
        path = self.data / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)

    def _write_screen(self):
        directory = self.data / "ekran"
        directory.mkdir(mode=0o700)
        path = directory / "fixture.jsonl"
        path.write_text(json.dumps({
            "ts": "2026-10-23T12:00:00+03:00", "kimlik": "fixture",
            "ad": "Fixture", "tur": "ekran", "satir": ["synthetic line"],
        }) + "\n", encoding="utf-8")
        path.chmod(0o600)

    def _get(self, path="/api/veri"):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=2)
        connection.request("GET", path, headers={
            "Host": f"127.0.0.1:{self.server.server_port}",
            "Cookie": "yuva_session=fixture-session"})
        response = connection.getresponse()
        headers = dict(response.getheaders())
        body = response.read()
        connection.close()
        return response.status, headers, body

    def _assert_error_response_policy(self, headers, body):
        normalized = {name.lower(): value for name, value in headers.items()}
        self.assertEqual(normalized.get("cache-control"), "no-store")
        self.assertEqual(normalized.get("x-content-type-options"), "nosniff")
        self.assertEqual(normalized.get("referrer-policy"), "no-referrer")
        self.assertEqual(normalized.get("x-frame-options"), "DENY")
        self.assertEqual(normalized.get("content-type"),
                         "application/json; charset=utf-8")
        self.assertEqual(int(normalized["content-length"]), len(body))

    def test_budget_feature_is_off_by_default_and_preserves_legacy_body(self):
        status, headers, body = self._get()
        decoded = json.loads(body)
        self.assertEqual(status, 200)
        self.assertNotIn("snapshot_meta", decoded)
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_enabled_production_handler_sends_selector_bytes_and_metadata(self):
        os.environ["YUVA_SNAPSHOT_BUDGET_ENABLED"] = "1"
        status, headers, body = self._get("/veri")
        decoded = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.assertLessEqual(len(body), 8 * 1024 * 1024)
        self.assertEqual(decoded["snapshot_meta"]["response_byte_budget"],
                         8 * 1024 * 1024)
        self.assertFalse(decoded["snapshot_meta"]["partial"])

    def test_production_selector_receives_only_allowlisted_redacted_projection(self):
        os.environ["YUVA_SNAPSHOT_BUDGET_ENABLED"] = "1"
        secrets = (
            "SYNTHETIC_CHAT_BEARER_123456789",
            "SYNTHETIC_SCREEN_BEARER_123456789",
        )
        self._write_json("durum.json", {
            "schema_version": 1, "rev": 5,
            "kullanicilar": {"fixture": {
                "ad": "Fixture", "arac": "test", "rol": "isci",
                "bas_denetci": False, "sorumlu_kimlik": None,
                "son_okuma": None, "not_": "PRIVATE_ROSTER_SENTINEL",
                "extra_secret": "PRIVATE_ROSTER_EXTRA_SENTINEL",
            }},
            "private_root": "PRIVATE_STATE_ROOT_SENTINEL",
        })
        self._write_json("gorevler.json", {
            "schema_version": 1, "siradaki": 2,
            "gorevler": [{
                "id": 1, "baslik": "Fixture task", "detay": "ordinary task",
                "durum": "pending", "kimden": "fixture", "assignee": None,
                "gorevli_kimlik": None, "inceleyen_kimlik": None,
                "ust_gorev_id": None, "gecmis": [],
                "private_task_field": "PRIVATE_TASK_SENTINEL",
            }],
            "private_root": "PRIVATE_TASK_ROOT_SENTINEL",
        })
        message = {
            "id": "synthetic-message", "ts": "2026-10-23T12:00:00+03:00",
            "kimden": "fixture", "ad": "Fixture", "kime": "@all",
            "metin": "Authorization: Bearer " + secrets[0], "tur": "not",
            "private_chat_field": "PRIVATE_CHAT_SENTINEL",
        }
        message_path = self.data / "mesaj.jsonl"
        message_path.write_text(json.dumps(message) + "\n", encoding="utf-8")
        message_path.chmod(0o600)
        message_bytes_before = message_path.read_bytes()
        screen_dir = self.data / "ekran"
        screen_dir.mkdir(mode=0o700)
        screen_path = screen_dir / "fixture.jsonl"
        screen_record = {
            "ts": "2026-10-23T12:00:00+03:00", "kimlik": "fixture",
            "ad": "Fixture", "tur": "ekran",
            "satir": "Authorization: Bearer " + secrets[1],
        }
        screen_path.write_text(json.dumps(screen_record) + "\n", encoding="utf-8")
        screen_path.chmod(0o600)
        screen_bytes_before = screen_path.read_bytes()

        selector = self.panel._snapshot_budget_modulu_yukle()
        with patch.object(selector, "build_response", wraps=selector.build_response) as spy:
            status, headers, body = self._get("/api/veri")

        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.assertEqual(spy.call_count, 1)
        projected = spy.call_args.args[0]
        self.assertEqual(set(projected), {
            "ok", "simdi", "online_sn", "rev", "kullanicilar", "gorevler",
            "mesajlar", "ekranlar", "ekranlar_meta",
        })
        self.assertEqual(set(projected["kullanicilar"]["fixture"]), {
            "kimlik", "ad", "arac", "rol", "bas_denetci", "sorumlu_kimlik",
            "son_okuma", "online", "presence_state", "presence_verified",
        })
        self.assertEqual(set(projected["gorevler"][0]), {
            "id", "baslik", "detay", "durum", "kimden", "assignee",
            "gorevli_kimlik", "inceleyen_kimlik", "ust_gorev_id", "gecmis",
        })
        self.assertEqual(set(projected["mesajlar"][-1]), {
            "id", "ts", "kimden", "ad", "kime", "metin", "tur",
            "source_class", "source_class_trust", "provenance",
        })
        self.assertEqual(set(projected["ekranlar"]["fixture"][0]), {
            "ts", "kimlik", "ad", "tur", "satir",
        })
        self.assertNotIn("private_chat_field", projected["mesajlar"][-1])
        projected_json = json.dumps(projected, ensure_ascii=False)
        for marker in ("PRIVATE_ROSTER_SENTINEL", "PRIVATE_ROSTER_EXTRA_SENTINEL",
                       "PRIVATE_STATE_ROOT_SENTINEL", "PRIVATE_TASK_SENTINEL",
                       "PRIVATE_TASK_ROOT_SENTINEL", "PRIVATE_CHAT_SENTINEL",
                       *secrets):
            self.assertNotIn(marker, projected_json)
            self.assertNotIn(marker.encode("utf-8"), body)
        self.assertIn(self.panel._EKRAN_REDAKSIYON.REDACTED, projected_json)
        self.assertEqual(message_path.read_bytes(), message_bytes_before)
        self.assertEqual(screen_path.read_bytes(), screen_bytes_before)

    def test_invalid_feature_flag_fails_closed(self):
        os.environ["YUVA_SNAPSHOT_BUDGET_ENABLED"] = "enabled"
        status, headers, body = self._get()
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {
            "ok": False, "hata": "snapshot_budget_configuration_invalid"})
        self._assert_error_response_policy(headers, body)

    def test_source_limit_error_preserves_security_and_no_store_headers(self):
        os.environ["YUVA_SNAPSHOT_BUDGET_ENABLED"] = "1"
        failure = self.panel.SnapshotSourceLimit("fixture-source.json", 32)
        with patch.object(self.panel, "veri", side_effect=failure):
            status, headers, body = self._get()

        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {
            "ok": False, "hata": "snapshot_source_limit",
            "kaynak": "fixture-source.json", "limit_bayt": 32,
        })
        self._assert_error_response_policy(headers, body)

    def test_screen_cursor_commits_only_after_successful_selection(self):
        os.environ["YUVA_SNAPSHOT_BUDGET_ENABLED"] = "1"
        self._write_screen()
        with patch.object(self.panel, "_ekran_secim_ilerlet") as commit:
            status, _headers, _body = self._get()
        self.assertEqual(status, 200)
        commit.assert_called_once_with(None, "fixture.jsonl")

        selector = self.panel._snapshot_budget_modulu_yukle()
        failure = selector.error_response("snapshot_response_unavailable")
        with patch.object(selector, "build_response", return_value=failure), \
                patch.object(self.panel, "_ekran_secim_ilerlet") as rejected_commit:
            status, _headers, body = self._get()
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {
            "ok": False, "hata": "snapshot_response_unavailable"})
        self._assert_error_response_policy(_headers, body)
        rejected_commit.assert_not_called()

    def test_wire_bytes_length_partial_metadata_and_utf8_records_match_selector(self):
        os.environ["YUVA_SNAPSHOT_BUDGET_ENABLED"] = "1"
        large_marker = "巨大🙂-RECORD-"
        tasks = [
            {
                "id": 1, "baslik": "Küçük görev 🌱", "detay": "küçük UTF-8 kayıtı: é雪🙂",
                "durum": "pending", "kimden": "fixture", "assignee": None,
                "gorevli_kimlik": None, "inceleyen_kimlik": None,
                "ust_gorev_id": None, "gecmis": [],
            },
            {
                "id": 2, "baslik": "Büyük görev", "detay": large_marker + "界🙂" * 140_000,
                "durum": "pending", "kimden": "fixture", "assignee": None,
                "gorevli_kimlik": None, "inceleyen_kimlik": None,
                "ust_gorev_id": None, "gecmis": [],
            },
        ]
        self._write_json("gorevler.json", {
            "schema_version": 1, "siradaki": 3, "gorevler": tasks})
        selector = self.panel._snapshot_budget_modulu_yukle()

        with patch.object(selector, "build_response", wraps=selector.build_response) as build:
            status, headers, body = self._get()

        self.assertEqual(status, 200)
        self.assertEqual(build.call_count, 1)
        projected_snapshot = build.call_args.args[0]
        expected = selector.build_response(
            projected_snapshot, **build.call_args.kwargs)
        self.assertEqual(body, expected.body)
        self.assertEqual(int(headers["Content-Length"]), len(expected.body))
        self.assertLessEqual(len(body), 8 * 1024 * 1024)

        decoded = json.loads(body)
        self.assertTrue(decoded["snapshot_meta"]["partial"])
        self.assertEqual(decoded["snapshot_meta"]["omitted"]["gorevler"], 1)
        self.assertEqual([task["id"] for task in decoded["gorevler"]], [1])
        self.assertEqual(decoded["gorevler"][0]["detay"], "küçük UTF-8 kayıtı: é雪🙂")
        self.assertIn("é雪🙂".encode("utf-8"), body)
        self.assertNotIn(large_marker.encode("utf-8"), body)


if __name__ == "__main__":
    unittest.main()
