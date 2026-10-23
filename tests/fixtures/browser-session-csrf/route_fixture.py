"""Synthetic browser-session/CSRF route gate for isolated acceptance tests.

This fixture does not import or configure the production panel. Its only state
is a caller-owned disposable ledger path.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path


HTML_PATHS = ("/", "/index.html")
SNAPSHOT_PATHS = ("/api/veri", "/veri")
POST_PATHS = (
    "/api/katil", "/api/kalp", "/api/ayril", "/api/ad", "/api/rol",
    "/api/sorumlu", "/api/bas-denetci", "/api/yaz", "/api/ekran",
    "/api/not", "/api/gorev",
)
CLOSED_PATHS = {"/api/not"}
UNAVAILABLE_PATHS = {"/api/kalp"}
SESSION_COOKIE = "yuva_session=fixture-valid-session"
CSRF_TOKEN = "fixture-session-bound-csrf"
LEDGER_LINE = b"fixture-mutation\n"
EXPECTED_ISSUER = "yuva-session-fixture"
EXPECTED_AUDIENCE = "panel-fixture"
EXPECTED_INSTANCE = "instance-fixture"
FIXTURE_NOW = 1_800_000_000
SESSION_RECORD = {
    "issuer": EXPECTED_ISSUER,
    "audience": EXPECTED_AUDIENCE,
    "instance": EXPECTED_INSTANCE,
    "expires_at": FIXTURE_NOW + 3600,
    "revoked": False,
    "principal": "fixture-user",
    "scopes": frozenset({
        "browser.shell", "snapshot.read", "presence.join", "presence.write",
        "presence.leave", "profile.write", "role.admin", "owner.admin",
        "reviewer.admin", "message.write", "screen.write", "task.admin",
        "notes.write",
    }),
}
PATH_SCOPES = {
    "/": "browser.shell", "/index.html": "browser.shell",
    "/api/veri": "snapshot.read", "/veri": "snapshot.read",
    "/api/katil": "presence.join", "/api/kalp": "presence.write",
    "/api/ayril": "presence.leave", "/api/ad": "profile.write",
    "/api/rol": "role.admin", "/api/sorumlu": "owner.admin",
    "/api/bas-denetci": "reviewer.admin", "/api/yaz": "message.write",
    "/api/ekran": "screen.write", "/api/not": "notes.write",
    "/api/gorev": "task.admin",
}


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def make_server(ledger_path: str | Path, *, auth_enabled: bool = True):
    """Build a loopback server with synthetic sessions and disposable writes."""
    ledger = Path(ledger_path)
    if not ledger.is_file():
        raise ValueError("fixture ledger must already exist")
    calls = {"html": 0, "snapshot": 0, "mutation": 0}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, status, value, *, html=False):
            body = (value.encode("utf-8") if isinstance(value, str)
                    else _json_bytes(value))
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8" if html
                             else "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _gate(self, *, post=False):
            if not auth_enabled:
                self._send(503, {"ok": False, "hata": "browser_auth_unavailable"})
                return False
            cookies = self.headers.get_all("Cookie", [])
            if len(cookies) != 1 or cookies[0] != SESSION_COOKIE:
                self._send(401, {"ok": False, "hata": "session_required"})
                return False
            session = SESSION_RECORD
            if (session["issuer"] != EXPECTED_ISSUER
                    or session["audience"] != EXPECTED_AUDIENCE
                    or session["instance"] != EXPECTED_INSTANCE
                    or session["expires_at"] <= FIXTURE_NOW
                    or session["revoked"]):
                self._send(401, {"ok": False, "hata": "session_invalid"})
                return False
            if PATH_SCOPES[self.path] not in session["scopes"]:
                self._send(403, {"ok": False, "hata": "scope_denied"})
                return False
            if post:
                origins = self.headers.get_all("Origin", [])
                expected_origin = f"http://127.0.0.1:{self.server.server_port}"
                csrf_values = self.headers.get_all("X-CSRF-Token", [])
                if origins != [expected_origin] or csrf_values != [CSRF_TOKEN]:
                    self._send(403, {"ok": False, "hata": "csrf_rejected"})
                    return False
            return True

        def do_GET(self):
            if self.path not in HTML_PATHS + SNAPSHOT_PATHS:
                return self._send(404, {"ok": False, "hata": "not_found"})
            if not self._gate():
                return
            if self.path in HTML_PATHS:
                calls["html"] += 1
                return self._send(200, "<html>fixture-shell</html>", html=True)
            calls["snapshot"] += 1
            return self._send(200, {"ok": True, "fixture": "snapshot"})

        def do_POST(self):
            if self.path not in POST_PATHS:
                return self._send(404, {"ok": False, "hata": "not_found"})
            if not self._gate(post=True):
                return
            if self.path in CLOSED_PATHS:
                return self._send(403, {"ok": False, "hata": "route_closed"})
            if self.path in UNAVAILABLE_PATHS:
                return self._send(503, {"ok": False, "hata": "route_unavailable"})
            calls["mutation"] += 1
            with ledger.open("ab") as stream:
                stream.write(LEDGER_LINE)
            return self._send(200, {
                "ok": True, "route": self.path,
                "principal": SESSION_RECORD["principal"],
            })

        def log_message(self, *_args):
            # Cookie and CSRF values must not be copied into fixture logs.
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.fixture_calls = calls
    return server
