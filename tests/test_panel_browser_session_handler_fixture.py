"""Exercise the real panel H dispatcher over disposable loopback HTTP."""

import http.client
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "panel" / "server.py"
POST_PATHS = (
    "/api/katil", "/api/kalp", "/api/ayril", "/api/ad", "/api/rol",
    "/api/sorumlu", "/api/bas-denetci", "/api/yaz", "/api/ekran",
    "/api/not", "/api/gorev",
)
GET_PATHS = ("/", "/index.html", "/api/veri", "/veri")
SESSION_COOKIE = "yuva_session=fixture-session"
CSRF_TOKEN = "fixture-session-csrf"
CLOSED_PATHS = {"/api/not"}


class FixtureAuthError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


class FixturePrincipal:
    def __init__(self, principal_id, scope):
        self.principal_id = principal_id
        self.scope = scope


class FixtureAuthenticatedRequest:
    def __init__(self, route, principal):
        self.route = route
        self.principal = principal


class SyntheticSessionCsrfAdapter:
    """Small cookie/CSRF adapter implementing the real H POST gate protocol."""

    def __init__(self, port, scopes):
        self.port = port
        self.scopes = set(scopes)
        self.post_auth_calls = 0
        self.get_auth_calls = 0

    def authenticate_get(self, request_target, headers, raw_body):
        self.get_auth_calls += 1
        cookies = headers.get_all("Cookie", [])
        if cookies != [SESSION_COOKIE]:
            raise FixtureAuthError(401, "session_required")
        route = request_target
        if route not in GET_PATHS:
            raise FixtureAuthError(404, "unknown_route")
        needed = "browser.shell" if route in ("/", "/index.html") else "snapshot.read"
        if needed not in self.scopes:
            raise FixtureAuthError(403, "scope_denied")
        return FixtureAuthenticatedRequest(
            route, FixturePrincipal("fixture-user", f"GET {route}"))

    def authorize_get(self, route, scope, cookie):
        self.get_auth_calls += 1
        if cookie != SESSION_COOKIE or route not in GET_PATHS:
            return False
        needed = "browser.shell" if route in ("/", "/index.html") else "snapshot.read"
        if scope != needed or needed not in self.scopes:
            raise PermissionError("scope denied")
        return True

    def authenticate_post(self, request_target, headers, raw_body):
        self.post_auth_calls += 1
        if request_target not in POST_PATHS:
            raise FixtureAuthError(404, "unknown_or_noncanonical_route")
        cookies = headers.get_all("Cookie", [])
        if cookies != [SESSION_COOKIE]:
            raise FixtureAuthError(401, "session_required")
        expected_origin = f"http://127.0.0.1:{self.port}"
        if (headers.get_all("Origin", []) != [expected_origin]
                or headers.get_all("X-CSRF-Token", []) != [CSRF_TOKEN]):
            raise FixtureAuthError(403, "csrf_rejected")
        scope = f"POST {request_target}"
        principal_scope = (scope if scope in self.scopes
                           else "POST fixture/insufficient-scope")
        return FixtureAuthenticatedRequest(
            request_target, FixturePrincipal("fixture-user", principal_scope))

    def authorize_payload(self, authn, payload):
        if authn is None:
            raise FixtureAuthError(401, "session_required")
        if authn.principal.scope != f"POST {authn.route}":
            raise FixtureAuthError(403, "scope_denied")
        if authn.route in CLOSED_PATHS:
            raise FixtureAuthError(403, "route_closed")
        return "fixture_route_scope"


class PanelBrowserSessionHandlerFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-panel-session-handler-")
        self.root = Path(self.temp.name)
        self.data_root = self.root / "yuva-data"
        self.data_root.mkdir(mode=0o700)
        self.ledger = self.root / "synthetic-ledger.jsonl"
        self.ledger.write_bytes(b"baseline\n")
        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(self.data_root),
            "YUVA_AUTH_ENABLED": "0",
        })
        self.env.start()

        name = f"yuva_panel_session_handler_{id(self)}"
        spec = importlib.util.spec_from_file_location(name, SERVER_PATH)
        self.panel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.panel)
        self.servers = []

    def tearDown(self):
        for server, thread in reversed(self.servers):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.panel.H.AUTH_GATE = None
        self.panel.H.BROWSER_SESSION_GATE = None
        self.env.stop()
        self.temp.cleanup()

    def start_server(self, *, gate):
        self.panel.H.AUTH_GATE = gate
        self.panel.H.BROWSER_SESSION_GATE = gate
        self.panel.H.IZINLI_HOSTLAR = {"localhost", "127.0.0.1"}
        server = self.panel.Sunucu(("127.0.0.1", 0), self.panel.H)
        port = server.server_address[1]
        self.panel.H.SUNUCU_PORT = port
        if gate is not None:
            gate.port = port
        thread = threading.Thread(target=server.serve_forever, daemon=False)
        thread.start()
        self.servers.append((server, thread))
        return server

    def request(self, server, method, path, *, session=False, csrf=False,
                extra_headers=None):
        headers = {"Host": f"127.0.0.1:{server.server_port}"}
        body = b"{}" if method == "POST" else None
        if method == "POST":
            headers["Content-Type"] = "application/json"
        if session:
            headers["Cookie"] = SESSION_COOKIE
        if csrf:
            headers["X-CSRF-Token"] = CSRF_TOKEN
            headers["Origin"] = f"http://127.0.0.1:{server.server_port}"
        if extra_headers:
            headers.update(extra_headers)
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=2)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            try:
                decoded = json.loads(raw) if raw else None
            except (ValueError, UnicodeError):
                decoded = raw.decode("utf-8")
            return response.status, decoded, response.getheaders()
        finally:
            connection.close()

    def install_synthetic_routes(self):
        calls = []

        def handler_for(route):
            def handle(payload, principal=None, authorization=None):
                with self.ledger.open("ab") as stream:
                    stream.write((route + "\n").encode("ascii"))
                calls.append((route, getattr(principal, "principal_id", None),
                              authorization))
                return 200, {"ok": True, "route": route}
            return handle

        replacements = {route: handler_for(route) for route in POST_PATHS}
        return calls, patch.dict(self.panel.UCLAR, replacements)

    def test_real_get_dispatch_requires_the_browser_session_scope_adapter(self):
        gate = SyntheticSessionCsrfAdapter(0, {
            "browser.shell", "snapshot.read"})
        server = self.start_server(gate=gate)
        reads = {"html": 0, "snapshot": 0}

        def shell():
            reads["html"] += 1
            return "<html>fixture-shell</html>"

        def snapshot():
            reads["snapshot"] += 1
            return {"ok": True, "fixture": "snapshot"}

        with patch.object(self.panel, "sayfa", side_effect=shell), \
                patch.object(self.panel, "veri", side_effect=snapshot):
            for path in GET_PATHS:
                with self.subTest(path=path):
                    before_reads = dict(reads)
                    status, body, headers = self.request(server, "GET", path)
                    self.assertEqual(status, 401)
                    self.assertEqual(body, {
                        "ok": False, "hata": "browser_session_required"})
                    self.assertEqual(reads, before_reads)

                    status, body, _ = self.request(
                        server, "GET", path, session=True)
                    self.assertEqual(status, 200)
                    self.assertTrue(any(k.lower() == "cache-control" and v == "no-store"
                                        for k, v in headers))
                    if path in ("/", "/index.html"):
                        self.assertEqual(body, "<html>fixture-shell</html>")
                    else:
                        self.assertEqual(body, {"ok": True, "fixture": "snapshot"})

                    gate.scopes.clear()
                    status, body, _ = self.request(server, "GET", path, session=True)
                    self.assertEqual(status, 403)
                    self.assertEqual(body, {"ok": False, "hata": "browser_scope_denied"})
                    gate.scopes.update({"browser.shell", "snapshot.read"})

        self.assertEqual(gate.get_auth_calls, 12)
        self.assertEqual(reads, {"html": 2, "snapshot": 2})

    def test_missing_browser_session_adapter_fails_closed_before_get_handlers(self):
        server = self.start_server(gate=None)
        reads = {"html": 0, "snapshot": 0}

        def shell():
            reads["html"] += 1
            return "fixture shell must remain unreachable"

        def snapshot():
            reads["snapshot"] += 1
            return {"ok": True, "fixture": "must remain unreachable"}

        with patch.object(self.panel, "sayfa", side_effect=shell), \
                patch.object(self.panel, "veri", side_effect=snapshot):
            for path in GET_PATHS:
                with self.subTest(path=path):
                    status, body, _ = self.request(server, "GET", path, session=True)
                    self.assertEqual(status, 503)
                    self.assertEqual(body, {
                        "ok": False, "hata": "browser_session_unavailable"})

        self.assertEqual(reads, {"html": 0, "snapshot": 0})

    def test_get_alias_normalization_and_invalid_sessions_never_dispatch(self):
        gate = SyntheticSessionCsrfAdapter(0, {
            "browser.shell", "snapshot.read"})
        server = self.start_server(gate=gate)
        reads = {"html": 0, "snapshot": 0}

        def shell():
            reads["html"] += 1
            return "fixture shell"

        def snapshot():
            reads["snapshot"] += 1
            return {"ok": True}

        malformed = {
            "/?next=/api/veri": 400,
            "/index.html?x=1": 400,
            "/index.html/": 400,
            "/api/veri?cache=1": 400,
            "/api/veri/": 400,
            "/veri?x=1": 400,
            "/veri/": 400,
            "//api/veri": 404,
            "/api%2Fveri": 404,
            "/api/%76eri": 404,
        }
        with patch.object(self.panel, "sayfa", side_effect=shell), \
                patch.object(self.panel, "veri", side_effect=snapshot):
            for route in GET_PATHS:
                for cookie in ("yuva_session=invalid", "yuva_session=expired",
                               "yuva_session=revoked"):
                    with self.subTest(route=route, cookie=cookie):
                        status, body, _ = self.request(
                            server, "GET", route,
                            extra_headers={"Cookie": cookie})
                        self.assertEqual(status, 401)
                        self.assertEqual(body, {
                            "ok": False, "hata": "browser_session_required"})

            for route, expected in malformed.items():
                with self.subTest(route=route):
                    status, _body, _ = self.request(
                        server, "GET", route, session=True)
                    self.assertEqual(status, expected)

            for route in GET_PATHS:
                with self.subTest(valid_route=route):
                    status, _body, _ = self.request(
                        server, "GET", route, session=True)
                    self.assertEqual(status, 200)

        self.assertEqual(reads, {"html": 2, "snapshot": 2})

    def test_direct_backend_and_proxy_identity_headers_do_not_bypass_auth_off_gate(self):
        # The fixture connects directly to the ephemeral backend socket; no proxy
        # process is present to authenticate or rewrite these client headers.
        server = self.start_server(gate=None)
        reads = {"html": 0, "snapshot": 0}

        def shell():
            reads["html"] += 1
            return "must not dispatch"

        def snapshot():
            reads["snapshot"] += 1
            return {"ok": True}

        spoof_headers = [
            {"X-Forwarded-User": "fixture-user"},
            {"X-Remote-User": "fixture-user"},
            {"X-Yuva-Principal": "fixture-user"},
            {"Forwarded": "for=127.0.0.1;host=localhost"},
            {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "trusted.example"},
            {"Cookie": SESSION_COOKIE, "X-Forwarded-User": "fixture-user"},
        ]
        with patch.object(self.panel, "sayfa", side_effect=shell), \
                patch.object(self.panel, "veri", side_effect=snapshot):
            for route in GET_PATHS:
                for headers in spoof_headers:
                    with self.subTest(route=route, headers=headers):
                        status, body, _ = self.request(
                            server, "GET", route, extra_headers=headers)
                        self.assertEqual(status, 503)
                        self.assertEqual(body, {
                            "ok": False, "hata": "browser_session_unavailable"})

        self.assertEqual(reads, {"html": 0, "snapshot": 0})

    def test_real_post_dispatch_applies_session_csrf_scope_and_closed_policy(self):
        gate = SyntheticSessionCsrfAdapter(0, {f"POST {path}" for path in POST_PATHS})
        server = self.start_server(gate=gate)
        calls, route_patch = self.install_synthetic_routes()
        route_patch.start()
        try:
            for path in POST_PATHS:
                before = self.ledger.read_bytes()
                status, body, _ = self.request(
                    server, "POST", path,
                    extra_headers={"X-Forwarded-User": "fixture-user",
                                   "X-Yuva-Principal": "fixture-user",
                                   "X-CSRF-Token": CSRF_TOKEN})
                self.assertEqual((status, body),
                                 (401, {"ok": False, "hata": "session_required"}))
                self.assertEqual(self.ledger.read_bytes(), before)

                status, body, _ = self.request(
                    server, "POST", path, session=True,
                    extra_headers={"X-Forwarded-User": "fixture-user",
                                   "X-Yuva-Principal": "fixture-user"})
                self.assertEqual((status, body),
                                 (403, {"ok": False, "hata": "csrf_rejected"}))
                self.assertEqual(self.ledger.read_bytes(), before)

                gate.scopes.remove(f"POST {path}")
                status, body, _ = self.request(
                    server, "POST", path, session=True, csrf=True)
                self.assertEqual((status, body),
                                 (403, {"ok": False, "hata": "scope_denied"}))
                self.assertEqual(self.ledger.read_bytes(), before)
                gate.scopes.add(f"POST {path}")

                status, body, _ = self.request(
                    server, "POST", path, session=True, csrf=True)
                if path in CLOSED_PATHS:
                    self.assertEqual((status, body),
                                     (403, {"ok": False, "hata": "route_closed"}))
                    self.assertEqual(self.ledger.read_bytes(), before)
                else:
                    self.assertEqual((status, body), (200, {"ok": True, "route": path}))
                    self.assertEqual(self.ledger.read_bytes(),
                                     before + (path + "\n").encode("ascii"))
            self.assertEqual([item[0] for item in calls],
                             [path for path in POST_PATHS if path not in CLOSED_PATHS])
        finally:
            route_patch.stop()

    def test_real_post_dispatch_is_open_when_auth_gate_is_off(self):
        server = self.start_server(gate=None)
        calls, route_patch = self.install_synthetic_routes()
        route_patch.start()
        try:
            for path in POST_PATHS:
                before = self.ledger.read_bytes()
                status, body, _ = self.request(server, "POST", path)
                if path in CLOSED_PATHS:
                    self.assertEqual(status, 200)
                    self.assertEqual(body, {"ok": True, "route": path})
                else:
                    self.assertEqual((status, body), (200, {"ok": True, "route": path}))
                self.assertEqual(self.ledger.read_bytes(),
                                 before + (path + "\n").encode("ascii"))
            self.assertEqual([item[0] for item in calls], list(POST_PATHS))
        finally:
            route_patch.stop()

    def test_real_handler_unknown_routes_are_closed(self):
        server = self.start_server(gate=SyntheticSessionCsrfAdapter(0, set()))
        before = self.ledger.read_bytes()
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                status, body, _ = self.request(server, method, "/fixture-unknown")
                self.assertEqual((status, body),
                                 (404, {"ok": False, "hata": "İstenen yol bulunamadı."})
                                 if method == "GET" else
                                 (404, {"ok": False,
                                        "hata": "unknown_or_noncanonical_route"}))
                self.assertEqual(self.ledger.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
