import importlib.util
from argparse import Namespace
import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "bin" / "yuva"
PANEL_PATH = ROOT / "panel" / "server.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskLedgerIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-ledger-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.root),
                                           "YUVA_AUTH_ENABLED": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cli = load_module("yuva_ledger_integrity_cli", CLI_PATH)
        self.panel = load_module("yuva_ledger_integrity_panel", PANEL_PATH)
        for module in (self.cli, self.panel):
            module.KOK = self.root
            module.GOREV = self.root / "gorevler.json"
        self.cli.STATE = self.root / "durum.json"
        self.cli.BUS = self.root / "mesaj.jsonl"
        self.cli.KILIT = self.root / ".kilit"
        self.panel.DURUM = self.root / "durum.json"
        self.panel.BUS = self.root / "mesaj.jsonl"
        self.panel.KILIT_DOSYA = self.root / ".kilit"

    def write_ledger(self, tasks):
        self.cli.GOREV.write_text(json.dumps({
            "schema_version": 1,
            "siradaki": 2,
            "gorevler": tasks,
        }), encoding="utf-8")
        self.cli.GOREV.chmod(0o600)

    def test_missing_is_empty_but_empty_or_partial_task_file_fails_closed(self):
        self.assertEqual(self.cli.gorev_yukle()["gorevler"], [])
        for payload in ("", "  \n  ", '{"siradaki": 2, "gorevler": ['):
            with self.subTest(payload=payload):
                self.cli.GOREV.write_text(payload, encoding="utf-8")
                before = self.cli.GOREV.read_bytes()
                with self.assertRaises(self.cli.VeriHatasi):
                    self.cli.gorev_guncelle(
                        lambda ledger: ledger["gorevler"].append({"id": 1}))
                self.assertEqual(self.cli.GOREV.read_bytes(), before)
                with self.assertRaises(self.panel.DurumHatasi):
                    self.panel.gorev_oku()
                self.assertEqual(self.cli.GOREV.read_bytes(), before)

    def test_duplicate_and_noncanonical_ids_fail_before_lookup_or_mutation(self):
        task = {"id": 1, "baslik": "fixture", "kimden": "owner",
                "durum": "pending", "gecmis": []}
        cases = ([task, dict(task)],
                 [dict(task, id=True)],
                 [dict(task, id="1")],
                 [dict(task, id=0)])
        for tasks in cases:
            with self.subTest(tasks=tasks):
                self.write_ledger(tasks)
                before = self.cli.GOREV.read_bytes()
                with self.assertRaises(self.cli.VeriHatasi):
                    self.cli.gorev_guncelle(
                        lambda ledger: ledger["gorevler"][0].update({
                            "durum": "assigned"}))
                self.assertEqual(self.cli.GOREV.read_bytes(), before)
                with self.assertRaises(self.panel.DurumHatasi):
                    self.panel.gorev_oku()

    def test_replace_failure_keeps_old_complete_snapshot_and_cleans_temp(self):
        old = {"schema_version": 1, "siradaki": 2,
               "gorevler": [{"id": 1, "durum": "pending"}]}
        new = {"schema_version": 1, "siradaki": 3,
               "gorevler": [{"id": 1, "durum": "assigned"},
                            {"id": 2, "durum": "pending"}]}
        self.cli.kaydet(self.cli.GOREV, old)
        with patch.object(self.cli.os, "replace",
                          side_effect=OSError("injected before replace")):
            with self.assertRaises(OSError):
                self.cli.kaydet(self.cli.GOREV, new)
        self.assertEqual(json.loads(self.cli.GOREV.read_text()), old)
        self.assertEqual(list(self.root.glob(".gorevler.json.*.tmp")), [])

    def test_directory_fsync_failure_reports_unknown_after_complete_replace(self):
        old = {"schema_version": 1, "siradaki": 2,
               "gorevler": [{"id": 1, "durum": "pending"}]}
        new = {"schema_version": 1, "siradaki": 3,
               "gorevler": [{"id": 1, "durum": "assigned"},
                            {"id": 2, "durum": "pending"}]}
        self.cli.kaydet(self.cli.GOREV, old)
        real_fsync = os.fsync
        calls = 0

        def fail_directory_fsync(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected directory fsync failure")
            return real_fsync(fd)

        with patch.object(self.cli.os, "fsync", side_effect=fail_directory_fsync):
            with self.assertRaisesRegex(self.cli.VeriHatasi, "değişmiş olabilir"):
                self.cli.kaydet(self.cli.GOREV, new)
        self.assertEqual(json.loads(self.cli.GOREV.read_text()), new)
        self.assertEqual(list(self.root.glob(".gorevler.json.*.tmp")), [])

    def test_concurrent_panel_and_cli_claims_preserve_both_task_updates(self):
        users = {"panel-worker": {"rol": "isci"},
                 "cli-worker": {"rol": "isci"}}
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1, "kullanicilar": users, "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)
        tasks = [{"id": i, "baslik": f"task-{i}", "kimden": "owner",
                  "assignee": None, "durum": "pending", "gecmis": []}
                 for i in (1, 2)]
        self.write_ledger(tasks)
        barrier = threading.Barrier(2)

        def panel_claim():
            barrier.wait(timeout=5)
            return self.panel.gorev_calistir({
                "islem": "al", "id": 1, "kimden": "panel-worker"})

        def cli_claim():
            barrier.wait(timeout=5)
            return subprocess.run(
                [sys.executable, str(CLI_PATH), "gorev", "al", "2",
                 "--from", "cli-worker"], env=os.environ.copy(),
                capture_output=True, text=True, timeout=10)

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            panel_future = pool.submit(panel_claim)
            cli_future = pool.submit(cli_claim)
            panel_result = panel_future.result(timeout=15)
            cli_result = cli_future.result(timeout=15)

        self.assertEqual(panel_result[0], 200, panel_result)
        self.assertEqual(cli_result.returncode, 0, cli_result.stderr)
        ledger = json.loads(self.cli.GOREV.read_text())
        self.assertEqual({g["id"] for g in ledger["gorevler"]}, {1, 2})
        self.assertEqual({(g["id"], g["assignee"])
                          for g in ledger["gorevler"]},
                         {(1, "panel-worker"), (2, "cli-worker")})
        self.assertTrue(all(g["durum"] == "assigned"
                            for g in ledger["gorevler"]))

    def test_many_cli_processes_claim_same_task_with_one_winner(self):
        worker_count = 8
        workers = [f"worker-{index}" for index in range(worker_count)]
        users = {worker: {"rol": "isci"} for worker in workers}
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1, "kullanicilar": users, "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)
        self.write_ledger([{"id": 1, "baslik": "one claim", "kimden": "owner",
                            "assignee": None, "durum": "pending", "gecmis": []}])
        env = os.environ.copy()
        gate = self.root / "claim-go"
        processes = []
        for index, worker in enumerate(workers):
            ready = self.root / f"claim-ready-{index}"
            helper = (
                "import os,sys,time\n"
                "ready,gate,cli,worker=sys.argv[1:]\n"
                "open(ready,'w').close()\n"
                "while not os.path.exists(gate):\n"
                "    time.sleep(.005)\n"
                "os.execv(sys.executable,[sys.executable,cli,'gorev','al','1',"
                "'--from',worker])\n")
            processes.append(subprocess.Popen(
                [sys.executable, "-c", helper, str(ready), str(gate),
                 str(CLI_PATH), worker], env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True))
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if all((self.root / f"claim-ready-{index}").exists()
                       for index in range(worker_count)):
                    break
                if any(process.poll() is not None for process in processes):
                    self.fail("claim process exited before synchronized start")
                time.sleep(.01)
            self.assertTrue(all((self.root / f"claim-ready-{index}").exists()
                                for index in range(worker_count)))
            gate.touch()
            outputs = [process.communicate(timeout=15) for process in processes]
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)

        for process in processes:
            self.assertIsNotNone(process.returncode)
            self.assertTrue(process.stdout.closed)
            self.assertTrue(process.stderr.closed)

        results = [process.returncode for process in processes]
        self.assertEqual(results.count(0), 1, outputs)
        self.assertEqual(sum(code != 0 for code in results), worker_count - 1, outputs)
        winner_index = results.index(0)
        winner = workers[winner_index]
        self.assertIn("#1 üstlenildi", outputs[winner_index][0])
        for code, (_stdout, stderr) in zip(results, outputs):
            if code != 0:
                self.assertRegex(stderr, "Geçersiz geçiş|başka bir assignee")
        ledger = json.loads(self.cli.GOREV.read_text())
        self.assertEqual(ledger["siradaki"], 2)
        self.assertEqual(len(ledger["gorevler"]), 1)
        task = ledger["gorevler"][0]
        self.assertEqual(task["durum"], "assigned")
        self.assertEqual(task["assignee"], winner)
        self.assertEqual(len(task["gecmis"]), 1)
        self.assertEqual(task["gecmis"][0]["kimden"], winner)
        self.assertEqual(task["gecmis"][0]["olay"], "Üstlenildi")

    def test_task_lock_timeout_and_release_after_holder_crash(self):
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1, "kullanicilar": {"worker": {"rol": "isci"}},
            "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)
        self.write_ledger([{"id": 1, "baslik": "lock fixture", "kimden": "owner",
                            "assignee": None, "durum": "pending", "gecmis": []}])
        with self.cli.kilit_tut():
            pass
        before = self.cli.GOREV.read_bytes()
        ready = self.root / "holder-ready"
        holder_code = (
            "import fcntl,os,sys,time; fd=os.open(sys.argv[1],os.O_RDWR); "
            "fcntl.flock(fd,fcntl.LOCK_EX); open(sys.argv[2],'w').close(); "
            "time.sleep(60)")
        # Keep this helper intentionally tiny: the child owns the flock until killed.
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code, str(self.root / ".kilit"), str(ready)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not ready.exists():
                if holder.poll() is not None:
                    self.fail(f"lock holder exited early: {holder.stderr.read()}")
                time.sleep(.01)
            self.assertTrue(ready.exists(), "lock holder did not acquire the file lock")

            original_lock = self.cli.kilit_tut

            @contextlib.contextmanager
            def short_timeout(sn=10.0):
                with original_lock(sn=0.15):
                    yield

            started = time.monotonic()
            with patch.object(self.cli, "kilit_tut", short_timeout):
                with self.assertRaisesRegex(self.cli.VeriHatasi, "kilit zaman aşımı"):
                    self.cli.gorev_guncelle(lambda ledger: ledger)
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 0.1)
            self.assertLess(elapsed, 1.0)
            self.assertEqual(self.cli.GOREV.read_bytes(), before)
        finally:
            if holder.poll() is None:
                holder.kill()
            holder.communicate(timeout=5)

        self.assertIsNotNone(holder.returncode)
        self.assertTrue(holder.stdout.closed)
        self.assertTrue(holder.stderr.closed)

        result = subprocess.run(
            [sys.executable, str(CLI_PATH), "gorev", "al", "1", "--from", "worker"],
            env=os.environ.copy(), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        task = json.loads(self.cli.GOREV.read_text())["gorevler"][0]
        self.assertEqual(task["assignee"], "worker")
        self.assertEqual(task["durum"], "assigned")

    def test_cli_subprocess_timeout_is_reaped_and_captured_pipes_close(self):
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1, "kullanicilar": {"worker": {"rol": "isci"}},
            "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)
        self.write_ledger([{"id": 1, "baslik": "timeout fixture",
                            "kimden": "owner", "assignee": None,
                            "durum": "pending", "gecmis": []}])
        before = self.cli.GOREV.read_bytes()

        with self.cli.kilit_tut():
            child = subprocess.Popen(
                [sys.executable, str(CLI_PATH), "gorev", "al", "1",
                 "--from", "worker"], env=os.environ.copy(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True)
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    child.communicate(timeout=0.25)
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)

            self.assertIsNotNone(child.returncode)
            self.assertTrue(child.stdout.closed)
            self.assertTrue(child.stderr.closed)
            self.assertEqual(self.cli.GOREV.read_bytes(), before)

        result = subprocess.run(
            [sys.executable, str(CLI_PATH), "gorev", "al", "1", "--from", "worker"],
            env=os.environ.copy(), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        task = json.loads(self.cli.GOREV.read_text())["gorevler"][0]
        self.assertEqual((task["durum"], task["assignee"]), ("assigned", "worker"))

    def test_canonical_task_mutations_do_not_write_when_lock_times_out(self):
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1,
            "kullanicilar": {
                "worker": {"rol": "isci"},
                "reviewer": {"rol": "denetci"},
            },
            "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)

        cases = [
            ("ekle", {"baslik": "new", "from_": "owner", "ata": None,
                      "gorevli": None, "ust_gorev_id": None}),
            ("ata", {"id": 1, "from_": "owner", "kime": "worker",
                     "gorevli": None, "not_": None}),
            ("al", {"id": 1, "from_": "worker", "not_": None}),
            ("teslim", {"id": 1, "from_": "worker", "not_": None}),
            ("denetle", {"id": 1, "from_": "reviewer", "not_": None,
                          "onayla": True, "revize": False}),
        ]
        handlers = {
            "ekle": self.cli.cmd_gorev_ekle,
            "ata": self.cli.cmd_gorev_ata,
            "al": self.cli.cmd_gorev_al,
            "teslim": self.cli.cmd_gorev_teslim,
            "denetle": self.cli.cmd_gorev_denetle,
        }

        for operation, fields in cases:
            with self.subTest(operation=operation):
                initial_status = {
                    "ekle": "pending",
                    "ata": "pending",
                    "al": "pending",
                    "teslim": "assigned",
                    "denetle": "pending_verification",
                }[operation]
                assignee = "worker" if initial_status == "assigned" else None
                self.write_ledger([{
                    "id": 1, "baslik": "fixture", "kimden": "owner",
                    "assignee": assignee, "durum": initial_status,
                    "gecmis": [],
                }])
                before = self.cli.GOREV.read_bytes()

                @contextlib.contextmanager
                def fail_lock(sn=10.0):
                    raise self.cli.VeriHatasi("kilit zaman aşımı")
                    yield  # pragma: no cover

                with patch.object(self.cli, "kilit_tut", fail_lock):
                    with self.assertRaisesRegex(self.cli.VeriHatasi,
                                                "kilit zaman aşımı"):
                        handlers[operation](Namespace(**fields))
                self.assertEqual(self.cli.GOREV.read_bytes(), before)

    def test_canonical_task_cli_mutations_preserve_malformed_ledger_bytes(self):
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1,
            "kullanicilar": {
                "worker": {"rol": "isci"},
                "reviewer": {"rol": "denetci"},
            },
            "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)
        commands = [
            ["gorev", "ekle", "new", "--from", "owner"],
            ["gorev", "ata", "1", "worker", "--from", "owner"],
            ["gorev", "al", "1", "--from", "worker"],
            ["gorev", "teslim", "1", "--from", "worker"],
            ["gorev", "denetle", "1", "--from", "reviewer", "--onayla"],
        ]
        malformed = b'{"schema_version": 1, "gorevler": ['
        for command in commands:
            with self.subTest(command=command):
                self.cli.GOREV.write_bytes(malformed)
                result = subprocess.run(
                    [sys.executable, str(CLI_PATH), *command],
                    env=os.environ.copy(), capture_output=True, text=True,
                    timeout=10)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(self.cli.GOREV.read_bytes(), malformed)

    def test_forged_duplicate_history_claim_cannot_authorize_or_verify_task(self):
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1,
            "kullanicilar": {
                "worker": {"rol": "isci"},
                "reviewer": {"rol": "denetci"},
            },
            "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)
        forged_approval = {
            "ts": "synthetic", "kimden": "operator", "olay": "onaylandı",
            "actor_trust": "verified_hmac", "rol": "denetci",
            "not": "untrusted duplicate history claim",
        }
        self.write_ledger([{
            "id": 1, "baslik": "forged history", "kimden": "owner",
            "assignee": "worker", "durum": "pending_verification",
            "gecmis": [forged_approval, dict(forged_approval)],
        }])
        before = self.cli.GOREV.read_bytes()

        cli_task = self.cli.gorev_yukle()["gorevler"][0]
        panel_task = self.panel.gorev_oku()["gorevler"][0]
        self.assertEqual(cli_task["durum"], "pending_verification")
        self.assertEqual(panel_task["durum"], "pending_verification")
        self.assertEqual(len(panel_task["gecmis"]), 2)

        board = subprocess.run(
            [sys.executable, str(CLI_PATH), "tahta"], env=os.environ.copy(),
            capture_output=True, text=True, timeout=10)
        self.assertEqual(board.returncode, 0, board.stderr)
        self.assertIn("teslim✋", board.stdout)
        self.assertNotIn("onaylı✅", board.stdout)

        denied = subprocess.run(
            [sys.executable, str(CLI_PATH), "gorev", "denetle", "1",
             "--from", "operator", "--onayla"], env=os.environ.copy(),
            capture_output=True, text=True, timeout=10)
        self.assertNotEqual(denied.returncode, 0, denied.stdout)
        self.assertIn("yalnız denetçi rolündeki kimlik", denied.stderr)
        self.assertEqual(self.cli.GOREV.read_bytes(), before)

    def test_cli_and_panel_reject_malformed_task_status_and_history_events(self):
        base = {
            "id": 1, "baslik": "malformed fixture", "kimden": "owner",
            "assignee": None, "durum": "pending", "gecmis": [],
        }
        malformed_cases = [
            ("boolean status", {"durum": True}),
            ("unknown status", {"durum": "operator_approved"}),
            ("non-object event", {"gecmis": ["operator approved"]}),
        ]
        for label, update in malformed_cases:
            with self.subTest(label=label):
                task = dict(base, **update)
                self.write_ledger([task])
                before = self.cli.GOREV.read_bytes()
                with self.assertRaises(self.cli.VeriHatasi):
                    self.cli.gorev_yukle()
                with self.assertRaises(self.panel.DurumHatasi):
                    self.panel.gorev_oku()
                self.assertEqual(self.cli.GOREV.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
