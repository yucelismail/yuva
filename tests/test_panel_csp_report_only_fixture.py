import http.client
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "panel-csp-transition"
SPEC = importlib.util.spec_from_file_location(
    "yuva_panel_csp_report_only_fixture", FIXTURE / "report_only_server.py")
report_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_server)


class PanelCspReportOnlyFixtureTests(unittest.TestCase):
    def test_temporary_http_server_scopes_report_only_and_cleans_up(self):
        temp = tempfile.TemporaryDirectory(prefix="yuva-csp-report-only-")
        temp_path = Path(temp.name)
        root = temp_path / "site"
        root.mkdir(mode=0o700)
        for name in ("report-only.html", "allowed.css", "allowed.js"):
            shutil.copyfile(FIXTURE / name, root / name)

        reports = []
        server = report_server.make_server(root, reports.append)
        thread = threading.Thread(target=server.serve_forever, daemon=False)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                                    timeout=2)
            connection.request("GET", "/")
            response = connection.getresponse()
            html = response.read().decode("utf-8")
            headers = response.headers
            self.assertEqual(response.status, 200)
            self.assertEqual(headers.get_all("Content-Security-Policy-Report-Only"),
                             [report_server.REPORT_ONLY_POLICY])
            self.assertIsNone(headers.get("Content-Security-Policy"))
            self.assertIn("report-uri /__csp-report", report_server.REPORT_ONLY_POLICY)
            self.assertIn("report-to yuva-csp-fixture", report_server.REPORT_ONLY_POLICY)
            endpoint = f"http://127.0.0.1:{server.server_port}/__csp-report"
            self.assertEqual(headers["Reporting-Endpoints"],
                             f'yuva-csp-fixture="{endpoint}"')
            self.assertEqual(json.loads(headers["Report-To"]), {
                "group": "yuva-csp-fixture", "max_age": 60,
                "endpoints": [{"url": endpoint}],
            })
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertNotIn("http-equiv=\"Content-Security-Policy\"", html)
            self.assertIn("<style>", html)
            self.assertIn("style=\"color: red\"", html)
            self.assertIn("onclick=", html)
            self.assertIn("<script>", html)
            connection.close()

            # Only same-origin fixture resources are served as allowed assets;
            # CSP reports are routed to the temporary receiver, not persisted.
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                                    timeout=2)
            connection.request("GET", "/allowed.js")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.getheader("Content-Security-Policy-Report-Only"))
            self.assertIn("allowed.js çalıştı", response.read().decode("utf-8"))
            connection.close()

            posted_reports = [
                (json.dumps({"csp-report": {
                    "violated-directive": "script-src-elem",
                    "document-uri": "http://fixture.invalid/private",
                }}, separators=(",", ":")).encode("utf-8"),
                 "application/csp-report"),
                (json.dumps([{"type": "csp-violation",
                              "url": "http://fixture.invalid/private",
                              "body": {"blockedURL": "inline"}}],
                            separators=(",", ":")).encode("utf-8"),
                 "application/reports+json"),
            ]
            for report_body, content_type in posted_reports:
                report_connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=2)
                try:
                    report_connection.request("POST", "/__csp-report", body=report_body,
                                              headers={"Content-Type": content_type})
                    report_response = report_connection.getresponse()
                    report_response_body = report_response.read()
                    self.assertEqual(report_response.status, 204,
                                     report_response_body.decode("utf-8", errors="replace"))
                finally:
                    report_connection.close()
            self.assertEqual(reports, [
                {"bytes": len(body), "content_type": content_type}
                for body, content_type in posted_reports
            ])
            self.assertNotIn("private", repr(reports))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            temp.cleanup()

        self.assertFalse(thread.is_alive())
        self.assertFalse(temp_path.exists())

    def test_enforce_policy_is_explicit_and_document_scoped(self):
        with tempfile.TemporaryDirectory(prefix="yuva-csp-enforce-opt-in-") as temp:
            root = Path(temp) / "site"
            root.mkdir(mode=0o700)
            for name in ("report-only.html", "allowed.css", "allowed.js"):
                shutil.copyfile(FIXTURE / name, root / name)
            reports = []
            server = report_server.make_server(root, reports.append, enforce=True)
            thread = threading.Thread(target=server.serve_forever, daemon=False)
            thread.start()
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=2)
                connection.request("GET", "/")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_all("Content-Security-Policy"),
                                 [report_server.ENFORCE_POLICY])
                self.assertIsNone(response.getheader("Content-Security-Policy-Report-Only"))
                self.assertIn("report-uri /__csp-report",
                              response.getheader("Content-Security-Policy"))
                response.read()

                connection.request("GET", "/allowed.js")
                asset = connection.getresponse()
                self.assertEqual(asset.status, 200)
                self.assertIsNone(asset.getheader("Content-Security-Policy"))
                self.assertIsNone(asset.getheader("Content-Security-Policy-Report-Only"))
                self.assertIn("allowed.js çalıştı", asset.read().decode("utf-8"))
                connection.close()
                self.assertEqual(reports, [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
            self.assertFalse(thread.is_alive())

    def test_enforce_flag_rejects_non_boolean_values(self):
        with tempfile.TemporaryDirectory(prefix="yuva-csp-enforce-config-") as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                report_server.make_server(root, lambda _report: None, enforce=1)

    def test_report_receiver_rejects_oversize_and_wrong_route(self):
        with tempfile.TemporaryDirectory(prefix="yuva-csp-report-reject-") as temp:
            root = Path(temp) / "site"
            root.mkdir(mode=0o700)
            for name in ("report-only.html", "allowed.css", "allowed.js"):
                shutil.copyfile(FIXTURE / name, root / name)
            reports = []
            server = report_server.make_server(root, reports.append)
            thread = threading.Thread(target=server.serve_forever, daemon=False)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                                        timeout=2)
                connection.request("POST", "/wrong-report-path", body=b"{}",
                                   headers={"Content-Type": "application/csp-report"})
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                response.read()

                connection.request("POST", "/__csp-report",
                                   body=None, headers={
                                       "Content-Type": "application/csp-report",
                                       "Content-Length": str(report_server.MAX_REPORT_BYTES + 1),
                                       "Connection": "close",
                                   })
                response = connection.getresponse()
                self.assertEqual(response.status, 413)
                response.read()
                self.assertEqual(reports, [])
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
