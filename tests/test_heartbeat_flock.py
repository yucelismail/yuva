import argparse
import errno
import importlib.util
import io
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch


YUVA_PATH = Path(__file__).resolve().parents[1] / "bin" / "yuva"
SPEC = importlib.util.spec_from_file_location(
    "yuva_under_test", YUVA_PATH,
    loader=SourceFileLoader("yuva_under_test", str(YUVA_PATH)))
yuva = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(yuva)


class HeartbeatFlockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-heartbeat-")
        self.root = Path(self.temp.name)
        yuva.KOK = self.root
        yuva.KILIT = self.root / ".kilit"
        yuva.BUS = self.root / "mesaj.jsonl"
        yuva.STATE = self.root / "durum.json"
        yuva.GOREV = self.root / "gorevler.json"
        yuva.EKRAN = self.root / "ekran"

    def tearDown(self):
        self.temp.cleanup()

    def test_lock_contention_is_distinct_from_lock_io_failure(self):
        fd = yuva.daemon_kilit_ac("agent-test")
        self.assertIsNotNone(fd)
        try:
            self.assertIsNone(yuva.daemon_kilit_ac("agent-test"))
        finally:
            os.close(fd)

        with patch.object(yuva.os, "open",
                          side_effect=OSError(errno.EIO, "disk error")):
            with self.assertRaises(OSError) as raised:
                yuva.daemon_kilit_ac("agent-test")
        self.assertEqual(raised.exception.errno, errno.EIO)

    def test_flock_io_failure_propagates_and_closes_open_descriptor(self):
        opened = []
        real_open = yuva.os.open

        def capture_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd

        with patch.object(yuva.os, "open", side_effect=capture_open), \
                patch.object(yuva.fcntl, "flock",
                             side_effect=OSError(errno.EIO, "flock I/O error")):
            with self.assertRaises(OSError) as raised:
                yuva.daemon_kilit_ac("flock-error")
        self.assertEqual(raised.exception.errno, errno.EIO)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(OSError):
            os.fstat(opened[0])

    def test_lock_rejects_symlink_and_multiple_links(self):
        path = yuva.daemon_kilit_dosyasi("symlink")
        outside = self.root / "outside"
        outside.write_text("", encoding="utf-8")
        path.symlink_to(outside)
        with self.assertRaises(OSError):
            yuva.daemon_kilit_ac("symlink")

        linked = yuva.daemon_kilit_dosyasi("linked")
        linked.touch()
        os.link(linked, self.root / "alias")
        with self.assertRaises(OSError):
            yuva.daemon_kilit_ac("linked")

    def test_lock_rejects_file_not_owned_by_current_user(self):
        with patch.object(yuva.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(PermissionError):
                yuva.daemon_kilit_ac("wrong-owner")

    def test_daemon_start_fails_closed_without_broker_principal(self):
        marker = yuva.dur_dosyasi("agent-test")
        marker.write_text("keep stopped\n", encoding="utf-8")
        with patch.object(yuva, "kilit_tut") as state_lock, \
                patch.object(yuva, "daemon_kilit_ac") as lock, \
                patch.object(yuva.subprocess, "Popen") as popen:
            result = yuva.daemon_baslat("agent-test", 10, None,
                                        temizle_dur=True)

        self.assertEqual(result, (
            None, "doğrulanmış broker principal yok; heartbeat daemonı başlatma kapalı",
            None))
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep stopped\n")
        state_lock.assert_not_called()
        lock.assert_not_called()
        popen.assert_not_called()

    def test_host_daemon_start_fails_closed_without_broker_principal(self):
        with patch.object(yuva.subprocess, "run") as run, \
                patch.object(yuva, "kilit_tut") as state_lock:
            result = yuva.host_kalp_baslat("agent-test", 10, None)

        self.assertEqual(result, (
            None, "doğrulanmış broker principal yok; heartbeat başlatma kapalı"))
        run.assert_not_called()
        state_lock.assert_not_called()

    def test_single_heartbeat_command_requires_verified_broker_identity(self):
        args = argparse.Namespace(from_="agent-test", panel=None)
        with patch.object(yuva, "http_iste") as request, \
                patch.object(yuva, "saglik_guncelle") as health:
            with self.assertRaisesRegex(
                    yuva.VeriHatasi, "doğrulanmış broker kimliği olmadan"):
                yuva.cmd_kalp(args)
        request.assert_not_called()
        health.assert_not_called()

    def test_daemon_loop_requires_principal_without_touching_fd_or_sinks(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        args = argparse.Namespace(from_="agent-test", pid=0, ata_baslangic=0,
                                  ttl=0, sn=1, panel=None, kilit_fd=lock_fd)
        try:
            with patch.object(yuva, "saglik_guncelle") as health, \
                    patch.object(yuva, "http_iste") as request:
                with self.assertRaisesRegex(
                        yuva.VeriHatasi, "broker principal doğrulanmadı"):
                    yuva.cmd_kalp_dongu(args)
            health.assert_not_called()
            request.assert_not_called()
            os.fstat(lock_fd)
        finally:
            os.close(lock_fd)

    def test_daemon_child_cleanup_kills_and_reaps_after_terminate_timeout(self):
        child = SimpleNamespace(pid=4327, poll=lambda: None,
                                terminate=lambda: None, kill=lambda: None)
        child.wait = unittest.mock.Mock(
            side_effect=[yuva.subprocess.TimeoutExpired("yuva", 0.5), 0])
        with patch.object(child, "terminate", wraps=child.terminate) as terminate, \
                patch.object(child, "kill", wraps=child.kill) as kill:
            yuva.daemon_child_temizle(child)
        terminate.assert_called_once_with()
        kill.assert_called_once_with()
        self.assertEqual(child.wait.call_count, 2)

    def test_daemon_rejects_descriptor_for_a_different_file(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        unrelated = os.open(self.root / "unrelated", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            self.assertTrue(yuva.daemon_kilit_fd_dogrula(lock_fd, "agent-test"))
            self.assertFalse(yuva.daemon_kilit_fd_dogrula(unrelated, "agent-test"))
        finally:
            os.close(unrelated)
            os.close(lock_fd)

    def test_roster_join_does_not_claim_heartbeat_or_clear_stop_marker(self):
        yuva.STATE.write_text(json.dumps({"kullanicilar": {}, "rev": 0}),
                              encoding="utf-8")
        marker = yuva.dur_dosyasi("agent-test")
        marker.write_text("stopped\n", encoding="utf-8")
        args = argparse.Namespace(kimlik="agent-test", arac="codex", rol="isci",
                                  ad=None, panel=None, kalp=True, kalp_sn=10,
                                  kalp_ttl=0)
        output = io.StringIO()
        with patch.object(yuva, "http_iste", return_value=(True, {
                "ok": True, "ad": "Fixture Agent"})), \
                patch.object(yuva, "daemon_baslat") as daemon_start, \
                patch.object(yuva, "host_kalp_baslat") as host_start, \
                redirect_stdout(output):
            yuva.cmd_baglan(args)

        user = yuva.durum_oku()["kullanicilar"]["agent-test"]
        self.assertEqual(user["arac"], "codex")
        self.assertEqual(user["rol"], "isci")
        self.assertNotIn("bagli", user)
        self.assertNotIn("son_kalp", user)
        self.assertTrue(marker.exists())
        self.assertIn("broker principal doğrulanmadığı için", output.getvalue())
        daemon_start.assert_not_called()
        host_start.assert_not_called()

    def test_stop_writes_marker_without_reading_pid_or_signaling(self):
        legacy_pid = self.root / ".kalp-agent-test.pid"
        legacy_pid.write_text("stale-pid\n", encoding="utf-8")
        with patch.object(yuva.os, "kill") as kill:
            self.assertTrue(yuva.daemon_durdur("agent-test", "test detach"))
        kill.assert_not_called()
        self.assertTrue(yuva.dur_dosyasi("agent-test").exists())
        self.assertEqual(legacy_pid.read_text(encoding="utf-8"), "stale-pid\n")


if __name__ == "__main__":
    unittest.main()
