#!/usr/bin/env python3
"""Read-only local preview server for the candidate Yuva panel."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PREVIEW_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PREVIEW_DIR.parent
UI_FILE = PROJECT_DIR / "panel" / "ui.html"
FIXTURE_FILE = PREVIEW_DIR / "fixture.json"
HOST = "127.0.0.1"
DEFAULT_PORT = 8687
PREVIEW_BANNER = (
    '<div class="preview-banner" role="note">'
    'Salt okunur örnek önizleme · veriler sentetiktir</div>'
)
PREVIEW_STYLE = """<style>
body{grid-template-rows:auto auto auto 1fr}
.preview-banner{grid-row:1;grid-column:1;background:#5b3b00;color:#fff;
padding:7px 12px;border-bottom:2px solid #d29922;text-align:center;
font:600 13px/1.4 system-ui,sans-serif}
body>header{grid-row:2}body>#serit{grid-row:3}body>main{grid-row:4}
</style>"""


class PreviewHandler(BaseHTTPRequestHandler):
    server_version = "YuvaPreview/1.0"
    sys_version = ""

    def __getattr__(self, name):
        if name.startswith("do_"):
            return self._method_not_allowed
        raise AttributeError(name)

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _method_not_allowed(self):
        body = json.dumps(
            {"ok": False, "hata": "Salt okunur önizleme; değişiklik kaydedilmedi"},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.close_connection = True
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            html = UI_FILE.read_bytes()
            html = html.replace(b"<body>", ("<body>" + PREVIEW_BANNER).encode("utf-8"), 1)
            html = html.replace(b"</head>", PREVIEW_STYLE.encode("utf-8") + b"</head>", 1)
            self._send(200, "text/html; charset=utf-8", html)
        elif path == "/api/veri":
            self._send(200, "application/json; charset=utf-8", FIXTURE_BYTES)
        else:
            self.send_error(404, "Not Found")

    def do_HEAD(self):
        self._method_not_allowed()

    def do_POST(self):
        self._method_not_allowed()

    def do_PUT(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def do_PATCH(self):
        self._method_not_allowed()

    def do_OPTIONS(self):
        self._method_not_allowed()


def main():
    parser = argparse.ArgumentParser(description="Serve the panel with isolated demo data.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="local TCP port (default: 8687)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    httpd = HTTPServer((HOST, args.port), PreviewHandler)
    print("Preview: http://127.0.0.1:{}/ (Ctrl+C to stop)".format(args.port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview stopped.", flush=True)
    finally:
        httpd.server_close()


with FIXTURE_FILE.open("rb") as fixture_file:
    FIXTURE_BYTES = fixture_file.read()
json.loads(FIXTURE_BYTES)


if __name__ == "__main__":
    main()
