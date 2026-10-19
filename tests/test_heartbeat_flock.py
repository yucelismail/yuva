import argparse
import errno
import importlib.util
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch


YUVA_PATH = Path(__file__).resolve().parents[1] / "bin" / "yuva"
SPEC = importlib.util.spec_from_file_location(
    "yuva_under_test", YUVA_PATH,
    loader=SourceFileLoader("yuva_under_test", str(YUVA_PATH)))
yuva = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(yuva)


def bildir_hazirlik(args, mesaj="READY"):
    fd = int(args[args.index("--hazirlik-fd") + 1])
    os.write(fd, (mesaj + "\n").encode("utf-8"))


class HeartbeatFlockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
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

        with patch.object(yuva.os, "open", side_effect=OSError(errno.EIO, "disk error")):
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

    def test_daemon_start_does_not_spawn_when_flock_is_busy(self):
        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "daemon_kilit_ac", return_value=None), \
                patch.object(yuva.subprocess, "Popen") as popen:
            pid, status, parent = yuva.daemon_baslat("agent-test", 10, None)
        self.assertIsNone(pid)
        self.assertIn("zaten çalışıyor", status)
        self.assertIsNone(parent)
        popen.assert_not_called()

    def test_reconnect_retries_after_old_daemon_releases_lock_outside_state_lock(self):
        legacy_lock_acquire = yuva.daemon_kilit_ac
        old_fd = legacy_lock_acquire("agent-test")
        yuva.dur_dosyasi("agent-test").write_text("old daemon saw this\n")
        lock_contexts = []
        started = {}

        class StateLock:
            def __enter__(self):
                lock_contexts.append(self)
                return self

            def __exit__(self, *_exc):
                # Simulate the exiting daemon completing shutdown only after the
                # starter has released the global state lock.
                if len(lock_contexts) == 1:
                    os.close(old_fd)

        def fake_popen(args, **kwargs):
            bildir_hazirlik(args)
            started["child_fd"] = os.dup(kwargs["pass_fds"][0])
            return SimpleNamespace(pid=4567)

        with patch.object(yuva, "kilit_tut", side_effect=StateLock), \
                patch.object(yuva, "daemon_kilit_ac", wraps=legacy_lock_acquire) as acquire, \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva, "daemon_hazirlik_bekle", return_value="READY"), \
                patch.object(yuva, "time") as mocked_time, \
                patch.object(yuva.subprocess, "Popen", side_effect=fake_popen) as popen:
            pid, status, parent = yuva.daemon_baslat(
                "agent-test", 10, None, temizle_dur=True)

        self.assertEqual((pid, status, parent), (4567, True, 1234))
        self.assertEqual(acquire.call_count, 2)
        self.assertEqual(len(lock_contexts), 2)
        mocked_time.sleep.assert_called_once_with(0.05)
        popen.assert_called_once()
        self.assertFalse(yuva.dur_dosyasi("agent-test").exists())
        self.assertIsNone(yuva.daemon_kilit_ac("agent-test"))
        os.close(started["child_fd"])

    def test_reconnect_does_not_clear_a_new_detach_marker_during_retry(self):
        original_acquire = yuva.daemon_kilit_ac
        old_fd = original_acquire("agent-test")
        yuva.dur_dosyasi("agent-test").write_text("old marker\n")
        lock_contexts = []

        class StateLock:
            def __enter__(self):
                lock_contexts.append(self)

            def __exit__(self, *_exc):
                if len(lock_contexts) == 1:
                    os.close(old_fd)
                    yuva.dur_dosyasi("agent-test").write_text("new detach\n")

        with patch.object(yuva, "kilit_tut", side_effect=StateLock), \
                patch.object(yuva, "daemon_kilit_ac", return_value=None), \
                patch.object(yuva.subprocess, "Popen") as popen:
            pid, status, _parent = yuva.daemon_baslat(
                "agent-test", 10, None, temizle_dur=True)
        self.assertIsNone(pid)
        self.assertIn("durduruldu işareti var", status)
        self.assertEqual(len(lock_contexts), 2)
        self.assertEqual(yuva.dur_dosyasi("agent-test").read_text(), "new detach\n")
        popen.assert_not_called()

    def test_daemon_start_hands_lock_fd_to_child_and_closes_parent_copy(self):
        legacy_pid = self.root / ".kalp-agent-test.pid"
        legacy_pid.write_text("stale-pid\n", encoding="utf-8")
        captured = {}

        def fake_popen(args, **kwargs):
            bildir_hazirlik(args)
            fd = kwargs["pass_fds"][0]
            captured["fd"] = fd
            captured["child_fd"] = os.dup(fd)
            captured["args"] = args
            captured["kwargs"] = kwargs
            with self.assertRaises(BlockingIOError):
                probe = os.open(yuva.daemon_kilit_dosyasi("agent-test"), os.O_RDWR)
                try:
                    import fcntl
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(probe)
            return SimpleNamespace(pid=4321)

        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva.subprocess, "Popen", side_effect=fake_popen):
            pid, status, parent = yuva.daemon_baslat("agent-test", 10, None)

        self.assertEqual(pid, 4321)
        self.assertIs(status, True)
        self.assertEqual(parent, 1234)
        fd = captured["fd"]
        self.assertIn("--kilit-fd", captured["args"])
        start_index = captured["args"].index("--ata-baslangic")
        self.assertEqual(captured["args"][start_index + 1], "5678")
        self.assertEqual(captured["kwargs"]["pass_fds"][0], fd)
        self.assertEqual(len(captured["kwargs"]["pass_fds"]), 2)
        with self.assertRaises(OSError):
            os.fstat(fd)
        self.assertIsNone(yuva.daemon_kilit_ac("agent-test"))
        os.close(captured["child_fd"])
        retry_fd = yuva.daemon_kilit_ac("agent-test")
        self.assertIsNotNone(retry_fd)
        os.close(retry_fd)
        self.assertEqual(legacy_pid.read_text(encoding="utf-8"), "stale-pid\n")

    def test_daemon_start_failure_releases_lock_and_preserves_legacy_pid(self):
        legacy_pid = self.root / ".kalp-agent-test.pid"
        legacy_pid.write_text("stale-pid\n", encoding="utf-8")
        captured = {}

        def failed_popen(args, **kwargs):
            captured["fd"] = kwargs["pass_fds"][0]
            raise OSError(errno.EAGAIN, "spawn failed")

        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva.subprocess, "Popen", side_effect=failed_popen), \
                patch.object(yuva, "saglik_guncelle"):
            pid, status, _parent = yuva.daemon_baslat("agent-test", 10, None)

        self.assertIsNone(pid)
        self.assertIn("spawn failed", status)
        with self.assertRaises(OSError):
            os.fstat(captured["fd"])
        retry_fd = yuva.daemon_kilit_ac("agent-test")
        self.assertIsNotNone(retry_fd)
        os.close(retry_fd)
        self.assertEqual(legacy_pid.read_text(encoding="utf-8"), "stale-pid\n")

    def test_daemon_start_waits_for_readiness_before_success(self):
        def ready_popen(args, **kwargs):
            bildir_hazirlik(args)
            return SimpleNamespace(pid=4322)

        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva.subprocess, "Popen", side_effect=ready_popen):
            pid, status, parent = yuva.daemon_baslat("agent-test", 10, None)

        self.assertEqual((pid, status, parent), (4322, True, 1234))

    def test_real_child_can_take_state_lock_before_reporting_readiness(self):
        kimlik = "agent-real-child"
        yuva.STATE.write_text(json.dumps({"kullanicilar": {
            kimlik: {"bagli": True, "ad": kimlik}}, "rev": 0}), encoding="utf-8")
        real_popen = yuva.subprocess.Popen
        children = []

        def capture_popen(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        try:
            with patch.dict(os.environ, {"YUVA_DIR": str(self.root)}), \
                    patch.object(yuva, "ata_pid_oku", return_value=(os.getpid(), [])), \
                    patch.object(yuva.subprocess, "Popen", side_effect=capture_popen):
                pid, status, parent = yuva.daemon_baslat(
                    kimlik, 1, "http://127.0.0.1:1")

            self.assertTrue(status, status)
            self.assertEqual(parent, os.getpid())
            self.assertEqual(pid, children[0].pid, status)
            self.assertTrue(yuva.saglik_dosyasi(kimlik).exists())
        finally:
            if children and children[0].poll() is None:
                yuva.daemon_durdur(kimlik, "test cleanup")
                try:
                    children[0].wait(timeout=4)
                except yuva.subprocess.TimeoutExpired:
                    yuva.daemon_child_temizle(children[0])

    def test_daemon_start_timeout_cleans_up_child_and_reports_failure(self):
        child = SimpleNamespace(pid=4323, poll=lambda: None, terminate=lambda: None,
                                wait=lambda **kwargs: 0)
        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva, "daemon_hazirlik_bekle", return_value=None), \
                patch.object(yuva, "daemon_child_temizle") as temizle, \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva.subprocess, "Popen", return_value=child):
            pid, status, _parent = yuva.daemon_baslat("agent-test", 10, None)

        self.assertIsNone(pid)
        self.assertIn("zaman aşımı", status)
        temizle.assert_called_once_with(child)
        retry_fd = yuva.daemon_kilit_ac("agent-test")
        self.assertIsNotNone(retry_fd)
        os.close(retry_fd)

    def test_daemon_start_reports_child_validation_error(self):
        child = SimpleNamespace(pid=4324, poll=lambda: 1, wait=lambda **kwargs: 0)

        def failed_popen(args, **kwargs):
            bildir_hazirlik(args, "ERR: heartbeat kilit FD'si doğrulanamadı")
            return child

        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva.subprocess, "Popen", side_effect=failed_popen):
            pid, status, _parent = yuva.daemon_baslat("agent-test", 10, None)

        self.assertIsNone(pid)
        self.assertIn("FD'si doğrulanamadı", status)
        retry_fd = yuva.daemon_kilit_ac("agent-test")
        self.assertIsNotNone(retry_fd)
        os.close(retry_fd)

    def test_daemon_start_reports_child_exit_without_readiness(self):
        child = SimpleNamespace(pid=4325, poll=lambda: 1, wait=lambda **kwargs: 0)

        def exited_popen(_args, **_kwargs):
            return child

        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva, "daemon_hazirlik_bekle", return_value=""), \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva.subprocess, "Popen", side_effect=exited_popen):
            pid, status, _parent = yuva.daemon_baslat("agent-test", 10, None)

        self.assertIsNone(pid)
        self.assertIn("hazır olmadan kapandı", status)
        retry_fd = yuva.daemon_kilit_ac("agent-test")
        self.assertIsNotNone(retry_fd)
        os.close(retry_fd)

    def test_daemon_start_catches_child_exit_immediately_after_ready(self):
        child = SimpleNamespace(pid=4326, poll=lambda: 0, wait=lambda **kwargs: 0)

        def exited_after_ready(args, **_kwargs):
            bildir_hazirlik(args)
            return child

        with patch.object(yuva, "kilit_tut", return_value=nullcontext()), \
                patch.object(yuva, "ata_pid_oku", return_value=(1234, [])), \
                patch.object(yuva, "proc_baslangic", return_value=5678), \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva.subprocess, "Popen", side_effect=exited_after_ready):
            pid, status, _parent = yuva.daemon_baslat("agent-test", 10, None)

        self.assertIsNone(pid)
        self.assertIn("hemen kapandı", status)
        retry_fd = yuva.daemon_kilit_ac("agent-test")
        self.assertIsNotNone(retry_fd)
        os.close(retry_fd)

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

    def test_daemon_loop_validates_lock_and_keeps_detach_check(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        args = argparse.Namespace(from_="agent-test", pid=0, ata_baslangic=0,
                                  ttl=0, sn=1, panel=None, kilit_fd=lock_fd)
        with patch.object(yuva, "durum_oku", return_value={"kullanicilar": {
                    "agent-test": {"bagli": False}}}), \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva, "http_iste") as http, \
                patch.object(yuva, "daemon_kilit_fd_dogrula",
                             wraps=yuva.daemon_kilit_fd_dogrula) as validate:
            yuva.cmd_kalp_dongu(args)
        http.assert_not_called()
        validate.assert_called_once_with(lock_fd, "agent-test")
        with self.assertRaises(OSError):
            os.fstat(lock_fd)

    def test_daemon_loop_rejects_unrelated_fd_before_heartbeat(self):
        unrelated = os.open(self.root / "unrelated", os.O_CREAT | os.O_RDWR, 0o600)
        args = argparse.Namespace(from_="agent-test", pid=0, ata_baslangic=0,
                                  ttl=0, sn=1, panel=None, kilit_fd=unrelated)
        with patch.object(yuva, "saglik_guncelle") as health, \
                patch.object(yuva, "http_iste") as http:
            yuva.cmd_kalp_dongu(args)
        health.assert_called_once_with(
            "agent-test", "hata", "heartbeat kilit FD'si doğrulanamadı")
        http.assert_not_called()
        os.close(unrelated)

    def test_daemon_loop_reports_readiness_after_first_heartbeat_attempt(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        hazir_oku, hazir_yaz = os.pipe()
        args = argparse.Namespace(from_="agent-test", pid=0, ata_baslangic=0,
                                  ttl=1, sn=1, panel=None, kilit_fd=lock_fd,
                                  hazirlik_fd=hazir_yaz)
        with patch.object(yuva, "time") as mocked_time, \
                patch.object(yuva, "durum_oku", return_value={"kullanicilar": {
                    "agent-test": {"bagli": True}}}), \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva, "kullanici_dokun"), \
                patch.object(yuva, "http_iste", return_value=(True, {"ok": True})), \
                patch.object(yuva, "daemon_kapan"):
            mocked_time.time.side_effect = [0, 0, 2]
            mocked_time.sleep.return_value = None
            yuva.cmd_kalp_dongu(args)
        self.assertEqual(os.read(hazir_oku, 32), b"READY\n")
        os.close(hazir_oku)

    def test_daemon_loop_reports_fd_validation_failure_to_starter(self):
        unrelated = os.open(self.root / "unrelated", os.O_CREAT | os.O_RDWR, 0o600)
        hazir_oku, hazir_yaz = os.pipe()
        args = argparse.Namespace(from_="agent-test", pid=0, ata_baslangic=0,
                                  ttl=0, sn=1, panel=None, kilit_fd=unrelated,
                                  hazirlik_fd=hazir_yaz)
        with patch.object(yuva, "saglik_guncelle"):
            yuva.cmd_kalp_dongu(args)
        self.assertEqual(os.read(hazir_oku, 128),
                         "ERR: heartbeat kilit FD'si doğrulanamadı\n".encode())
        os.close(hazir_oku)
        os.close(unrelated)

    def test_daemon_loop_exits_when_parent_starttime_changes(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        args = argparse.Namespace(from_="agent-test", pid=1234, ata_baslangic=5678,
                                  ttl=0, sn=1, panel=None, kilit_fd=lock_fd)
        with patch.object(yuva, "proc_baslangic", return_value=9876), \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva, "daemon_kapan") as kapan, \
                patch.object(yuva, "http_iste") as http:
            yuva.cmd_kalp_dongu(args)
        kapan.assert_called_once_with("agent-test", "ebeveyn süreç yok")
        http.assert_not_called()
        with self.assertRaises(OSError):
            os.fstat(lock_fd)

    def test_daemon_loop_exits_when_parent_proc_entry_is_missing(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        args = argparse.Namespace(from_="agent-test", pid=1234, ata_baslangic=5678,
                                  ttl=0, sn=1, panel=None, kilit_fd=lock_fd)
        with patch.object(yuva, "proc_baslangic", return_value=None), \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva, "daemon_kapan") as kapan, \
                patch.object(yuva, "http_iste") as http:
            yuva.cmd_kalp_dongu(args)
        kapan.assert_called_once_with("agent-test", "ebeveyn süreç yok")
        http.assert_not_called()
        with self.assertRaises(OSError):
            os.fstat(lock_fd)

    def test_daemon_loop_exits_at_ttl_without_network_or_real_shutdown(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        args = argparse.Namespace(from_="agent-test", pid=0, ata_baslangic=0,
                                  ttl=1, sn=1, panel=None, kilit_fd=lock_fd)
        with patch.object(yuva, "time") as mocked_time, \
                patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva, "daemon_kapan") as kapan, \
                patch.object(yuva, "http_iste") as http:
            mocked_time.time.side_effect = [100, 101]
            yuva.cmd_kalp_dongu(args)
        kapan.assert_called_once_with("agent-test", "ttl doldu", durdur=True)
        http.assert_not_called()
        with self.assertRaises(OSError):
            os.fstat(lock_fd)

    def test_daemon_loop_exits_on_dur_marker_without_network(self):
        lock_fd = yuva.daemon_kilit_ac("agent-test")
        yuva.dur_dosyasi("agent-test").write_text("stop\n")
        args = argparse.Namespace(from_="agent-test", pid=0, ata_baslangic=0,
                                  ttl=0, sn=1, panel=None, kilit_fd=lock_fd)
        with patch.object(yuva, "saglik_guncelle"), \
                patch.object(yuva, "daemon_kapan") as kapan, \
                patch.object(yuva, "http_iste") as http:
            yuva.cmd_kalp_dongu(args)
        kapan.assert_called_once_with("agent-test", "ayrilma işareti")
        http.assert_not_called()
        with self.assertRaises(OSError):
            os.fstat(lock_fd)

    def test_detach_and_reconnect_commands_update_local_state_and_start_once(self):
        yuva.STATE.write_text(json.dumps({"kullanicilar": {
            "agent-test": {"bagli": True, "ad": "agent-test"}}, "rev": 0}))
        detach_args = argparse.Namespace(from_="agent-test", panel=None)
        with patch.object(yuva, "http_iste", return_value=(False, None)), \
                patch.object(yuva, "host_kontrol_var_mi", return_value=True), \
                patch.object(yuva, "host_birim_durdur", return_value=None), \
                patch.object(yuva, "host_linger_durumu", return_value=True), \
                patch.object(yuva, "host_kalp_baslat",
                             return_value=("yuva-kalp-test.service", None)) as baslat:
            yuva.cmd_ayril(detach_args)
            self.assertFalse(yuva.durum_oku()["kullanicilar"]["agent-test"]["bagli"])
            self.assertTrue(yuva.dur_dosyasi("agent-test").exists())

            connect_args = argparse.Namespace(kimlik="agent-test", arac="codex", rol="isci",
                                              ad=None, panel=None, kalp=True, kalp_sn=10,
                                              kalp_ttl=0)
            yuva.cmd_baglan(connect_args)
            self.assertTrue(yuva.durum_oku()["kullanicilar"]["agent-test"]["bagli"])
            self.assertFalse(yuva.dur_dosyasi("agent-test").exists())
        baslat.assert_called_once()

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
