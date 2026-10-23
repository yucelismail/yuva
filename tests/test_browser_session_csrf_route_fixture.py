import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "browser-session-csrf"
SPEC = importlib.util.spec_from_file_location(
    "yuva_browser_session_csrf_fixture", FIXTURE / "route_fixture.py")
route_fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route_fixture)


class BrowserSessionCsrfRouteFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-browser-session-csrf-")
        self.ledger = Path(self.temp.name) / "fixture-ledger.jsonl"
        self.ledger.write_bytes(b"baseline-ledger\n")
        self.servers = []

    def tearDown(self):
        for server, thread in reversed(self.servers):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.temp.cleanup()

    def start_server(self, *, auth_enabled=True):
        server = route_fixture.make_server(self.ledger, auth_enabled=auth_enabled)
        thread = threading.Thread(target=server.serve_forever, daemon=False)
        thread.start()
        self.servers.append((server, thread))
        return server

    def request(self, server, method, path, *, session=False, csrf=False):
        headers = {}
        if session:
            headers["Cookie"] = route_fixture.SESSION_COOKIE
        if csrf:
            headers["X-CSRF-Token"] = route_fixture.CSRF_TOKEN
            headers["Origin"] = f"http://127.0.0.1:{server.server_port}"
        body = b"{}" if method == "POST" else None
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=2)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()
            decoded = (response_body.decode("utf-8") if method == "GET"
                       and path in route_fixture.HTML_PATHS
                       and response.status == 200
                       else json.loads(response_body) if response_body else None)
            return response.status, decoded, response.getheader("Content-Length")
        finally:
            connection.close()

    def test_get_aliases_reject_missing_session_and_auth_off_before_handlers(self):
        server = self.start_server()
        for path in route_fixture.HTML_PATHS + route_fixture.SNAPSHOT_PATHS:
            with self.subTest(path=path, session="missing"):
                status, body, _ = self.request(server, "GET", path)
                self.assertEqual((status, body),
                                 (401, {"ok": False, "hata": "session_required"}))
                self.assertNotIn("fixture-shell", repr(body))
                self.assertNotIn("snapshot", repr(body))
        self.assertEqual(server.fixture_calls, {"html": 0, "snapshot": 0, "mutation": 0})

        for path in route_fixture.HTML_PATHS + route_fixture.SNAPSHOT_PATHS:
            with self.subTest(path=path, session="valid"):
                status, body, _ = self.request(server, "GET", path, session=True)
                self.assertEqual(status, 200)
                if path in route_fixture.HTML_PATHS:
                    self.assertEqual(body, "<html>fixture-shell</html>")
                else:
                    self.assertEqual(body, {"ok": True, "fixture": "snapshot"})
        self.assertEqual(server.fixture_calls, {"html": 2, "snapshot": 2, "mutation": 0})

        auth_off = self.start_server(auth_enabled=False)
        for path in route_fixture.HTML_PATHS + route_fixture.SNAPSHOT_PATHS:
            with self.subTest(path=path, auth="off"):
                status, body, _ = self.request(auth_off, "GET", path, session=True)
                self.assertEqual((status, body), (
                    503, {"ok": False, "hata": "browser_auth_unavailable"}))
        self.assertEqual(auth_off.fixture_calls,
                         {"html": 0, "snapshot": 0, "mutation": 0})

    def test_all_post_routes_reject_missing_session_without_ledger_writes(self):
        server = self.start_server()
        for path in route_fixture.POST_PATHS:
            before = self.ledger.read_bytes()
            with self.subTest(path=path):
                status, body, _ = self.request(server, "POST", path)
                self.assertEqual((status, body),
                                 (401, {"ok": False, "hata": "session_required"}))
                self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(server.fixture_calls["mutation"], 0)

    def test_all_post_routes_reject_missing_csrf_without_ledger_writes(self):
        server = self.start_server()
        for path in route_fixture.POST_PATHS:
            before = self.ledger.read_bytes()
            with self.subTest(path=path):
                status, body, _ = self.request(server, "POST", path, session=True)
                self.assertEqual((status, body),
                                 (403, {"ok": False, "hata": "csrf_rejected"}))
                self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(server.fixture_calls["mutation"], 0)

    def test_auth_off_rejects_every_post_before_route_or_ledger_access(self):
        server = self.start_server(auth_enabled=False)
        for path in route_fixture.POST_PATHS:
            before = self.ledger.read_bytes()
            with self.subTest(path=path):
                status, body, _ = self.request(server, "POST", path,
                                               session=True, csrf=True)
                self.assertEqual((status, body), (
                    503, {"ok": False, "hata": "browser_auth_unavailable"}))
                self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(server.fixture_calls["mutation"], 0)

    def test_valid_session_csrf_allows_only_fixture_permitted_mutations(self):
        server = self.start_server()
        before_total = self.ledger.read_bytes()
        succeeded = 0
        for path in route_fixture.POST_PATHS:
            before = self.ledger.read_bytes()
            with self.subTest(path=path):
                status, body, content_length = self.request(
                    server, "POST", path, session=True, csrf=True)
                if path in route_fixture.CLOSED_PATHS:
                    self.assertEqual((status, body),
                                     (403, {"ok": False, "hata": "route_closed"}))
                    self.assertEqual(self.ledger.read_bytes(), before)
                elif path in route_fixture.UNAVAILABLE_PATHS:
                    self.assertEqual((status, body),
                                     (503, {"ok": False, "hata": "route_unavailable"}))
                    self.assertEqual(self.ledger.read_bytes(), before)
                else:
                    expected = {"ok": True, "route": path,
                                "principal": "fixture-user"}
                    self.assertEqual((status, body), (200, expected))
                    self.assertEqual(self.ledger.read_bytes(),
                                     before + route_fixture.LEDGER_LINE)
                    self.assertEqual(int(content_length), len(json.dumps(
                        expected, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")))
                    succeeded += 1
        self.assertEqual(succeeded, len(route_fixture.POST_PATHS)
                         - len(route_fixture.CLOSED_PATHS)
                         - len(route_fixture.UNAVAILABLE_PATHS))
        self.assertEqual(self.ledger.read_bytes(),
                         before_total + route_fixture.LEDGER_LINE * succeeded)
        self.assertEqual(server.fixture_calls["mutation"], succeeded)


if __name__ == "__main__":
    unittest.main()
