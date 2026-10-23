import contextlib
import http.client
import importlib.util
import io
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from prototypes.panel_snapshot_budget import snapshot_budget


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "panel" / "server.py"


def load_panel(name):
    spec = importlib.util.spec_from_file_location(
        name, SERVER_PATH, loader=SourceFileLoader(name, str(SERVER_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PanelGetSnapshotAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-panel-get-acceptance-")
        self.data = Path(self.temp.name) / "synthetic-yuva"
        self.data.mkdir(mode=0o700)
        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(self.data), "YUVA_AUTH_ENABLED": "0",
        })
        self.env.start()
        self.panel = load_panel(f"yuva_panel_get_acceptance_{id(self)}")
        self.old_handler = (self.panel.H.AUTH_GATE, self.panel.H.BROWSER_SESSION_GATE,
                            self.panel.H.SUNUCU_PORT, self.panel.H.IZINLI_HOSTLAR)
        self.panel.H.AUTH_GATE = None
        class FixtureBrowserSessionGate:
            def authorize_get(_self, route, scope, cookie):
                return (cookie == "yuva_session=fixture-session"
                        and scope == self.panel.BROWSER_GET_ROUTE_POLICY[route])
        self.panel.H.BROWSER_SESSION_GATE = FixtureBrowserSessionGate()
        self.panel.H.IZINLI_HOSTLAR = {"localhost", "127.0.0.1"}

        class BudgetFixtureHandler(self.panel.H):
            RESPONSE_BYTE_BUDGET = 4096

            def _gonder(handler, kod, govde,
                        tur="application/json; charset=utf-8", kapat=False):
                if (kod == 200 and isinstance(govde, dict)
                        and {"ok", "simdi", "online_sn", "rev", "kullanicilar",
                             "gorevler", "mesajlar", "ekranlar", "ekranlar_meta"}
                        <= set(govde)):
                    bounded = snapshot_budget.build_response(
                        govde,
                        response_byte_budget=handler.RESPONSE_BYTE_BUDGET,
                        group_budgets={
                            name: 100_000 for name in snapshot_budget.GROUP_FIELDS},
                        metadata_reserve=512,
                        screen_order=list(govde["ekranlar"]))
                    return super(BudgetFixtureHandler, handler)._gonder(
                        bounded.status, bounded.body, tur, kapat)
                return super(BudgetFixtureHandler, handler)._gonder(
                    kod, govde, tur, kapat)

        self.handler_class = BudgetFixtureHandler
        self.server = self.panel.Sunucu(("127.0.0.1", 0), BudgetFixtureHandler)
        self.panel.H.SUNUCU_PORT = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=False)
        self.thread.start()
        self.chat_secret = "SYNTHETIC_CHAT_BEARER_123456789"
        self.provenance_secret = "SYNTHETIC_PROVENANCE_TOKEN_123456789"
        self.screen_secret = "SYNTHETIC_SCREEN_TOKEN_123456789"
        self._write_fixture_state()

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
        return path

    def _write_fixture_state(self):
        self._write_json("durum.json", {
            "schema_version": 1, "rev": 7,
            "kullanicilar": {"fixture-agent": {
                "ad": "Fixture", "arac": "test", "rol": "isci",
                "bas_denetci": False, "sorumlu_kimlik": None,
                "son_okuma": None, "not_": "PRIVATE_ROSTER_SENTINEL",
                "extra_secret": "PRIVATE_ROSTER_EXTRA_SENTINEL",
            }},
            "private_root": "PRIVATE_STATE_SENTINEL",
        })
        self._write_json("gorevler.json", {
            "schema_version": 1, "siradaki": 2,
            "gorevler": [{
                "id": 1, "baslik": "Fixture task", "detay": "ordinary fixture text",
                "durum": "pending", "kimden": "fixture-agent", "assignee": None,
                "gorevli_kimlik": None, "inceleyen_kimlik": None,
                "ust_gorev_id": None, "gecmis": [],
                "private_task_field": "PRIVATE_TASK_SENTINEL",
            }],
            "private_root": "PRIVATE_TASK_ROOT_SENTINEL",
        })
        messages = []
        for index in range(8):
            messages.append({
                "id": f"message-{index}", "ts": f"2026-10-23T12:00:0{index}+03:00",
                "kimden": "fixture-agent", "ad": "Fixture", "kime": "@hepsi",
                "metin": (f"fixture message {index} Authorization: Bearer "
                          f"{self.chat_secret} " + "m" * 800),
                "tur": "not", "kanal": "sohbet",
                "schema_version": 2,
                "provenance": {
                    "source": "fixture", "trust": "unverified", "actor_id": None,
                    "auth_method": "none",
                    "identity_claim": {"value": "token=" + self.provenance_secret,
                                       "source": "unknown", "trust": "unverified",
                                       "actor_id": None},
                },
                "private_chat_field": "PRIVATE_CHAT_FIELD_SENTINEL",
            })
        self.message_path = self.data / "mesaj.jsonl"
        self.message_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                                for row in messages), encoding="utf-8")
        self.message_path.chmod(0o600)

        self.screen_dir = self.data / "ekran"
        self.screen_dir.mkdir(mode=0o700)
        self.screen_path = self.screen_dir / "fixture-agent.jsonl"
        self.screen_record = {
            "ts": "2026-10-23T12:00:00+03:00", "kimlik": "fixture-agent",
            "ad": "Fixture", "tur": "ekran",
            "satir": "Authorization: Bearer " + self.screen_secret,
        }
        self.screen_path.write_text(json.dumps(self.screen_record) + "\n",
                                    encoding="utf-8")
        self.screen_path.chmod(0o600)
        self.chat_bytes_before = self.message_path.read_bytes()
        self.screen_bytes_before = self.screen_path.read_bytes()

    def request(self, path):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("GET", path, headers={
                "Cookie": "yuva_session=fixture-session"})
            response = connection.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), body
        finally:
            connection.close()

    def test_handler_budget_caps_real_route_response_after_redaction(self):
        fixture_findings = {
            "auth_session": "anonymous GET is reachable; this is not authentication",
            "data_minimization": "sensitive chat/task/screen fields remain in scope",
            "known_pattern_redaction": "fixture checks only shared high-confidence patterns",
            "response_budget": "4096-byte budget is attached to the synthetic HTTP Handler",
        }
        with patch.object(snapshot_budget, "build_response",
                          wraps=snapshot_budget.build_response) as budget_spy:
            for route in ("/api/veri", "/veri"):
                with self.subTest(route=route):
                    status, headers, raw = self.request(route)
                    self.assertEqual(status, 200)
                    self.assertIn("no-store", headers.get("Cache-Control", "").lower())
                    self.assertEqual(int(headers["Content-Length"]), len(raw))
                    self.assertLessEqual(len(raw), self.handler_class.RESPONSE_BYTE_BUDGET)
                    snapshot = json.loads(raw)
                self.assertEqual(set(snapshot), {
                    "ok", "simdi", "online_sn", "rev", "kullanicilar", "gorevler",
                    "mesajlar", "ekranlar", "ekranlar_meta", "snapshot_meta",
                })
                self.assertEqual(set(snapshot["kullanicilar"]["fixture-agent"]), {
                    "kimlik", "ad", "arac", "rol", "bas_denetci", "sorumlu_kimlik",
                    "son_okuma", "online", "presence_state", "presence_verified",
                })
                self.assertEqual(set(snapshot["gorevler"][0]), {
                    "id", "baslik", "detay", "durum", "kimden", "assignee",
                    "gorevli_kimlik", "inceleyen_kimlik", "ust_gorev_id", "gecmis",
                })
                message = snapshot["mesajlar"][-1]
                self.assertEqual(set(message), {
                    "id", "ts", "kimden", "ad", "kime", "metin", "tur",
                    "source_class", "source_class_trust", "provenance",
                })
                if "fixture-agent" in snapshot["ekranlar"]:
                    self.assertEqual(set(snapshot["ekranlar"]["fixture-agent"][0]), {
                        "ts", "kimlik", "ad", "tur", "satir",
                    })
                encoded = raw.decode("utf-8")
                for secret in (self.chat_secret, self.provenance_secret, self.screen_secret,
                               "PRIVATE_ROSTER_SENTINEL", "PRIVATE_ROSTER_EXTRA_SENTINEL",
                               "PRIVATE_STATE_SENTINEL", "PRIVATE_TASK_SENTINEL",
                               "PRIVATE_TASK_ROOT_SENTINEL", "PRIVATE_CHAT_FIELD_SENTINEL"):
                    self.assertNotIn(secret, encoded)
                self.assertIn(self.panel._EKRAN_REDAKSIYON.REDACTED, encoded)
                self.assertEqual(self.message_path.read_bytes(), self.chat_bytes_before)
                self.assertEqual(self.screen_path.read_bytes(), self.screen_bytes_before)

            self.assertEqual(2, budget_spy.call_count)
            for call in budget_spy.call_args_list:
                # The selector receives the route's projected object, after
                # message/provenance/screen redaction and before wire JSON.
                projected = call.args[0]
                encoded_projected = json.dumps(projected, ensure_ascii=False)
                for secret in (self.chat_secret, self.provenance_secret,
                               self.screen_secret):
                    self.assertNotIn(secret, encoded_projected)
                self.assertIn(self.panel._EKRAN_REDAKSIYON.REDACTED,
                              encoded_projected)

        # The budget result is now the actual body sent by this synthetic
        # Handler wrapper. It still says nothing about production auth.
        status, _headers, raw = self.request("/api/veri")
        bounded_snapshot = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertLessEqual(len(raw), self.handler_class.RESPONSE_BYTE_BUDGET)
        self.assertTrue(bounded_snapshot["snapshot_meta"]["partial"])
        self.assertGreater(bounded_snapshot["snapshot_meta"]["omitted"]["mesajlar"], 0)
        for secret in (self.chat_secret, self.provenance_secret, self.screen_secret):
            self.assertNotIn(secret, raw.decode("utf-8"))

        # Successful filtering is not an access-control result.
        self.assertIn("not authentication", fixture_findings["auth_session"])
        self.assertIn("remain in scope", fixture_findings["data_minimization"])
        self.assertIn("only", fixture_findings["known_pattern_redaction"])
        self.assertIn("synthetic HTTP Handler", fixture_findings["response_budget"])

    def test_error_body_and_handler_logs_do_not_repeat_secret_revision_input(self):
        sentinel = (f"Authorization: Bearer {self.chat_secret} token={self.screen_secret} "
                    '\"><img src=x onerror=alert(1)>')
        self._write_json("durum.json", {
            "schema_version": 1, "rev": sentinel, "kullanicilar": {},
        })
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status, _headers, body = self.request("/api/veri")
        self.assertEqual(status, 500)
        self.assertNotIn(sentinel.encode("utf-8"), body)
        self.assertNotIn(sentinel, stderr.getvalue())
        self.assertNotIn(b"Traceback", body)

    def test_snapshot_source_exact_byte_limit_is_parsed(self):
        path = self.data / "bounded.json"
        prefix = b'{"kullanicilar":{},"rev":0,"padding":"'
        suffix = b'"}'
        limit = 128
        raw = prefix + b"x" * (limit - len(prefix) - len(suffix)) + suffix
        self.assertEqual(len(raw), limit)
        path.write_bytes(raw)

        parsed = self.panel.oku_bayt_sinirli(path, None, limit, "durum")

        self.assertEqual(parsed["rev"], 0)
        self.assertEqual(len(path.read_bytes()), limit)

    def test_snapshot_source_limit_plus_one_rejects_before_json_parse(self):
        path = self.data / "oversized.json"
        limit = 128
        path.write_bytes(b'{"padding":"' + b"x" * (limit - 12) + b'"}')
        original = path.read_bytes()
        with patch.object(self.panel.json, "loads", wraps=self.panel.json.loads) as loads:
            with self.assertRaises(self.panel.SnapshotSourceLimit) as caught:
                self.panel.oku_bayt_sinirli(path, None, limit, "durum")

        self.assertEqual(caught.exception.source, "durum")
        self.assertEqual(caught.exception.limit_bytes, limit)
        loads.assert_not_called()
        self.assertEqual(path.read_bytes(), original)

    def test_task_ledger_snapshot_source_uses_its_own_byte_ceiling(self):
        path = self.data / "gorevler.json"
        path.write_bytes(b'{"gorevler":[] ,"padding":"' + b"x" * 80 + b'"}')
        with patch.object(self.panel, "SNAPSHOT_GOREV_KAYNAK_BAYT_AZAMI", 64):
            with self.assertRaises(self.panel.SnapshotSourceLimit) as caught:
                self.panel.gorev_oku(snapshot=True)

        self.assertEqual(caught.exception.source, "gorevler")
        self.assertEqual(caught.exception.limit_bytes, 64)
        self.assertGreater(path.stat().st_size, 64)

    def test_snapshot_source_limit_http_is_fixed_503_without_partial_data(self):
        path = self.data / "durum.json"
        original = path.read_bytes()
        with patch.object(self.panel, "SNAPSHOT_DURUM_KAYNAK_BAYT_AZAMI", 64):
            path.write_bytes(b'{"large":"' + b"x" * 100 + b'"}')
            oversized = path.read_bytes()
            status, _headers, body = self.request("/api/veri")

        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {
            "ok": False, "hata": "snapshot_source_limit",
            "kaynak": "durum", "limit_bayt": 64,
        })
        self.assertEqual(path.read_bytes(), oversized)
        self.assertNotEqual(oversized, original)

    def test_snapshot_source_malformed_json_fails_without_modifying_bytes(self):
        path = self.data / "malformed.json"
        original = b'{"kullanicilar":['
        path.write_bytes(original)

        with self.assertRaises(self.panel.DurumHatasi):
            self.panel.oku_bayt_sinirli(path, None, 128, "durum")

        self.assertEqual(path.read_bytes(), original)

    def test_snapshot_source_change_during_read_fails_before_parse(self):
        path = self.data / "changing.json"
        path.write_text('{"kullanicilar":{},"rev":0}', encoding="utf-8")
        original_fstat = self.panel.os.fstat
        calls = 0

        def mutate_before_second_fstat(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                path.write_text('{"kullanicilar":{},"rev":1}', encoding="utf-8")
            return original_fstat(fd)

        with patch.object(self.panel.os, "fstat", side_effect=mutate_before_second_fstat):
            with patch.object(self.panel.json, "loads", wraps=self.panel.json.loads) as loads:
                with self.assertRaisesRegex(self.panel.DurumHatasi, "değişti"):
                    self.panel.oku_bayt_sinirli(path, None, 128, "durum")

        self.assertEqual(calls, 2)
        loads.assert_not_called()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["rev"], 1)


if __name__ == "__main__":
    unittest.main()
