import importlib.util
import errno
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


SERVER_PATH = Path(__file__).resolve().parents[1] / "panel" / "server.py"
SPEC = importlib.util.spec_from_file_location("yuva_panel_under_test", SERVER_PATH)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class PanelAtomicWriteTests(unittest.TestCase):
    def test_yaz_fsyncs_parent_directory_after_replace(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "durum.json"
            events = []
            real_fsync = os.fsync
            real_replace = os.replace
            real_fchmod = os.fchmod

            def record_fchmod(fd, mode):
                events.append(("fchmod", stat.S_ISDIR(os.fstat(fd).st_mode)))
                return real_fchmod(fd, mode)

            def record_fsync(fd):
                events.append(("fsync", stat.S_ISDIR(os.fstat(fd).st_mode)))
                return real_fsync(fd)

            def record_replace(source, destination):
                events.append(("replace", Path(destination)))
                return real_replace(source, destination)

            with patch.object(server.os, "fchmod", side_effect=record_fchmod), \
                    patch.object(server.os, "fsync", side_effect=record_fsync), \
                    patch.object(server.os, "replace", side_effect=record_replace):
                server.yaz(target, {"ok": True})

            self.assertEqual(events, [
                ("fchmod", False),
                ("fsync", False),
                ("replace", target),
                ("fsync", True),
            ])
            self.assertEqual(server.oku(target, {}), {"ok": True})

    def test_directory_fsync_failure_reports_uncertainty_and_closes_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "durum.json"
            target.write_text('{"old": true}', encoding="utf-8")
            real_fsync = os.fsync
            real_open = os.open
            real_close = os.close
            directory_fds = []
            fsync_count = 0

            def record_open(path, flags, *args, **kwargs):
                fd = real_open(path, flags, *args, **kwargs)
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    directory_fds.append(fd)
                return fd

            def fail_directory_fsync(fd):
                nonlocal fsync_count
                fsync_count += 1
                if fsync_count == 2:
                    raise OSError(errno.EIO, "simulated directory fsync failure")
                return real_fsync(fd)

            with patch.object(server.os, "open", side_effect=record_open), \
                    patch.object(server.os, "fsync", side_effect=fail_directory_fsync), \
                    patch.object(server.os, "close", wraps=real_close) as close:
                with self.assertRaisesRegex(
                        server.DurumHatasi,
                        "değiştirildi ancak üst dizin dayanıklılığı doğrulanamadı"):
                    server.yaz(target, {"new": True})

            self.assertEqual(server.oku(target, {}), {"new": True})
            self.assertEqual(list(root.glob(".durum.json.*.tmp")), [])
            self.assertEqual(len(directory_fds), 1)
            close.assert_any_call(directory_fds[0])
            with self.assertRaises(OSError):
                os.fstat(directory_fds[0])


if __name__ == "__main__":
    unittest.main()
