"""Temporary example server for CSP Report-Only header acceptance tests."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit


MAX_REPORT_BYTES = 16 * 1024
REPORT_PATH = "/__csp-report"
REPORT_ONLY_POLICY = (
    "default-src 'none'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
    "script-src-attr 'none'; style-src 'self'; style-src-attr 'none'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "report-uri /__csp-report; report-to yuva-csp-fixture"
)
ENFORCE_POLICY = REPORT_ONLY_POLICY


def make_server(root: str | Path, report_sink, *, enforce: bool = False):
    """Build a loopback fixture; enforcement is an explicit opt-in."""
    if type(enforce) is not bool:
        raise ValueError("enforce must be a boolean")
    fixture_root = Path(root).resolve(strict=True)
    files = {
        "/": (fixture_root / "report-only.html", "text/html; charset=utf-8", True),
        "/report-only.html": (fixture_root / "report-only.html", "text/html; charset=utf-8", True),
        "/allowed.js": (fixture_root / "allowed.js", "text/javascript; charset=utf-8", False),
        "/allowed.css": (fixture_root / "allowed.css", "text/css; charset=utf-8", False),
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, status, body=b"", content_type=None, *, report_only=False,
                  enforce_policy=False, close=False):
            self.send_response(status)
            if content_type:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            if close:
                self.close_connection = True
                self.send_header("Connection", "close")
            if report_only or enforce_policy:
                endpoint = (f"http://127.0.0.1:{self.server.server_port}"
                            f"{REPORT_PATH}")
                policy_header = ("Content-Security-Policy" if enforce_policy
                                 else "Content-Security-Policy-Report-Only")
                policy = ENFORCE_POLICY if enforce_policy else REPORT_ONLY_POLICY
                self.send_header(policy_header, policy)
                self.send_header("Reporting-Endpoints",
                                 f'yuva-csp-fixture="{endpoint}"')
                self.send_header("Report-To", json.dumps({
                    "group": "yuva-csp-fixture", "max_age": 60,
                    "endpoints": [{"url": endpoint}],
                }, separators=(",", ":")))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            item = files.get(path)
            if item is None:
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            source, content_type, has_document_policy = item
            try:
                body = source.read_bytes()
            except OSError:
                return self._send(500, b"fixture unavailable", "text/plain; charset=utf-8")
            return self._send(
                200, body, content_type,
                report_only=has_document_policy and not enforce,
                enforce_policy=has_document_policy and enforce)

        def do_POST(self):
            if urlsplit(self.path).path != REPORT_PATH:
                return self._send(404, b"not found", "text/plain; charset=utf-8",
                                  close=True)
            lengths = self.headers.get_all("Content-Length", [])
            types = self.headers.get_all("Content-Type", [])
            if len(lengths) != 1 or len(types) != 1:
                return self._send(400, b"invalid report framing", "text/plain; charset=utf-8",
                                  close=True)
            try:
                size = int(lengths[0])
            except ValueError:
                return self._send(400, b"invalid report framing", "text/plain; charset=utf-8",
                                  close=True)
            if size < 1:
                return self._send(400, b"empty report", "text/plain; charset=utf-8",
                                  close=True)
            if size > MAX_REPORT_BYTES:
                return self._send(413, b"report too large", "text/plain; charset=utf-8",
                                  close=True)
            content_type = types[0].split(";", 1)[0].strip().lower()
            if content_type not in {"application/csp-report", "application/reports+json"}:
                return self._send(415, b"unsupported report type", "text/plain; charset=utf-8",
                                  close=True)
            raw_report = self.rfile.read(size)
            try:
                report = json.loads(raw_report.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                detail = (f"invalid report JSON ({len(raw_report)}/{size}; "
                          f"{type(error).__name__})").encode("ascii")
                return self._send(400, detail, "text/plain; charset=utf-8")
            if not isinstance(report, (dict, list)):
                return self._send(400, b"invalid report shape", "text/plain; charset=utf-8")
            # Keep only a fixture counter and request size; report details may
            # contain document URLs or user-controlled data.
            report_sink({"bytes": size, "content_type": content_type})
            return self._send(204)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)
