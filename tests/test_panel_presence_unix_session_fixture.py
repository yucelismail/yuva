"""Disposable AF_UNIX/session fixture; no UID, key, service, or broker setup."""

import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest


class UnixPresenceBrokerFixture:
    """Small broker model using actual accepted-socket peer credentials."""

    def __init__(self, root: Path):
        if not hasattr(socket, "SO_PEERCRED"):
            raise unittest.SkipTest("Linux SO_PEERCRED is unavailable")
        self.socket_path = root / "broker.sock"
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(os.fspath(self.socket_path))
        self.listener.listen(1)
        self.listener.settimeout(3)
        self.lock = threading.RLock()
        self.connected = threading.Event()
        self.disconnected = threading.Event()
        self.now = 100.0
        self.epoch = "epoch-fixture-1"
        self.map_revision = "map-fixture-1"
        self.uid_map = {os.getuid(): "synthetic-principal"}
        self.ttl = 10.0
        self.session_lifetime = 60.0
        self.session = None
        self.error = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    @staticmethod
    def _send(stream, value):
        stream.write(json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n")
        stream.flush()

    @staticmethod
    def _read(stream):
        line = stream.readline(4097)
        if not line or len(line) > 4096 or not line.endswith(b"\n"):
            return None
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _serve(self):
        try:
            accepted, _ = self.listener.accept()
            with accepted:
                accepted.settimeout(3)
                raw = accepted.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                peer_pid, peer_uid, peer_gid = struct.unpack("3i", raw)
                with self.lock:
                    principal = self.uid_map.get(peer_uid)
                    if principal is not None:
                        self.session = {
                            "session_id": "synthetic-session-1",
                            "principal_id": principal,
                            "peer": (peer_pid, peer_uid, peer_gid),
                            "map_revision": self.map_revision,
                            "epoch": self.epoch,
                            "expires_at": self.now + self.session_lifetime,
                            "active": True,
                            "high_water": 0,
                            "last_observed": None,
                        }
                reader = accepted.makefile("rb")
                writer = accepted.makefile("wb")
                try:
                    self._send(writer, {
                        "session_id": self.session["session_id"] if self.session else None,
                        "principal_id": principal,
                        "peer_pid": peer_pid,
                        "peer_uid": peer_uid,
                        "epoch": self.epoch,
                    })
                    self.connected.set()
                    while True:
                        frame = self._read(reader)
                        if frame is None:
                            break
                        self._send(writer, self.heartbeat(frame))
                finally:
                    if self.session is not None:
                        with self.lock:
                            self.session["active"] = False
                    self.disconnected.set()
                    reader.close()
                    writer.close()
        except (OSError, ValueError) as exc:
            self.error = type(exc).__name__
            self.disconnected.set()
        finally:
            self.listener.close()

    def heartbeat(self, frame):
        with self.lock:
            session = self.session
            if not isinstance(frame, dict) or session is None or not session["active"]:
                return {"accepted": False, "reason": "session_unknown"}
            if self.epoch != session["epoch"] or frame.get("epoch") != session["epoch"]:
                return {"accepted": False, "reason": "session_epoch_stale"}
            if self.map_revision != session["map_revision"]:
                return {"accepted": False, "reason": "map_revision_stale"}
            if self.now >= session["expires_at"]:
                return {"accepted": False, "reason": "session_expired"}
            if frame.get("session_id") != session["session_id"]:
                return {"accepted": False, "reason": "session_mismatch"}
            claim = frame.get("principal_id")
            if claim is not None and claim != session["principal_id"]:
                return {"accepted": False, "reason": "principal_claim_conflict"}
            sequence = frame.get("sequence")
            if type(sequence) is not int or sequence < 1:
                return {"accepted": False, "reason": "sequence_invalid"}
            if sequence <= session["high_water"]:
                return {"accepted": False, "reason": "heartbeat_replay"}
            session["high_water"] = sequence
            session["last_observed"] = self.now
            return {"accepted": True, "sequence": sequence,
                    "principal_id": session["principal_id"]}

    def project(self):
        with self.lock:
            session = self.session
            if (session is None or not session["active"]
                    or self.epoch != session["epoch"]
                    or self.map_revision != session["map_revision"]
                    or self.now >= session["expires_at"]
                    or session["last_observed"] is None
                    or self.now - session["last_observed"] > self.ttl):
                return {"state": "unknown", "verified": False}
            return {"state": "online", "verified": True,
                    "principal_id": session["principal_id"],
                    "epoch": session["epoch"],
                    "sequence": session["high_water"]}

    def advance(self, seconds):
        with self.lock:
            self.now += seconds

    def restart_epoch(self, new_epoch):
        with self.lock:
            self.epoch = new_epoch


class UnixPresenceSessionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-presence-session-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.broker = UnixPresenceBrokerFixture(self.root)
        self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.client.settimeout(3)
        self.client.connect(os.fspath(self.broker.socket_path))
        self.reader = self.client.makefile("rb")
        self.writer = self.client.makefile("wb")
        self.welcome = UnixPresenceBrokerFixture._read(self.reader)
        self.assertTrue(self.broker.connected.wait(3))

    def tearDown(self):
        for stream in (getattr(self, "writer", None), getattr(self, "reader", None)):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        if getattr(self, "client", None) is not None:
            try:
                self.client.close()
            except OSError:
                pass
        broker = getattr(self, "broker", None)
        if broker is not None:
            broker.thread.join(timeout=3)
            if broker.thread.is_alive():
                broker.listener.close()

    def heartbeat(self, sequence, **claims):
        frame = {"session_id": self.welcome["session_id"],
                 "epoch": self.welcome["epoch"], "sequence": sequence,
                 **claims}
        UnixPresenceBrokerFixture._send(self.writer, frame)
        return UnixPresenceBrokerFixture._read(self.reader)

    def test_accepted_socket_credential_binds_synthetic_session(self):
        self.assertEqual(self.welcome["peer_uid"], os.getuid())
        self.assertEqual(self.welcome["peer_pid"], os.getpid())
        self.assertEqual(self.welcome["principal_id"], "synthetic-principal")
        self.assertEqual(self.broker.project(), {"state": "unknown", "verified": False})

        result = self.heartbeat(1, principal_id="forged-other-principal")
        self.assertEqual(result["reason"], "principal_claim_conflict")
        self.assertEqual(self.broker.project(), {"state": "unknown", "verified": False})

        accepted = self.heartbeat(1)
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["principal_id"], "synthetic-principal")
        self.assertTrue(self.broker.project()["verified"])

    def test_duplicate_and_stale_heartbeats_never_refresh_presence(self):
        self.assertTrue(self.heartbeat(5)["accepted"])
        observed_at = self.broker.session["last_observed"]
        replay = self.heartbeat(5)
        self.assertEqual(replay["reason"], "heartbeat_replay")
        self.assertEqual(self.broker.session["last_observed"], observed_at)
        self.broker.advance(self.broker.ttl + 1)
        self.assertEqual(self.broker.project(), {"state": "unknown", "verified": False})
        self.assertTrue(self.heartbeat(6)["accepted"])
        self.assertEqual(self.broker.project()["sequence"], 6)

    def test_session_expiry_and_epoch_restart_fail_closed(self):
        self.assertTrue(self.heartbeat(1)["accepted"])
        self.broker.map_revision = "map-fixture-2"
        stale_map = self.heartbeat(2)
        self.assertEqual(stale_map["reason"], "map_revision_stale")
        self.assertEqual(self.broker.session["high_water"], 1)
        self.broker.map_revision = self.broker.session["map_revision"]
        self.broker.restart_epoch("epoch-fixture-2")
        self.assertEqual(self.broker.project(), {"state": "unknown", "verified": False})
        old_epoch = self.heartbeat(2)
        self.assertEqual(old_epoch["reason"], "session_epoch_stale")

        self.broker.session["epoch"] = self.broker.epoch
        self.broker.session["expires_at"] = self.broker.now + 1
        self.welcome["epoch"] = self.broker.epoch
        self.broker.advance(2)
        expired = self.heartbeat(2)
        self.assertEqual(expired["reason"], "session_expired")
        self.assertEqual(self.broker.project(), {"state": "unknown", "verified": False})

    def test_disconnect_invalidates_session_and_presence(self):
        self.assertTrue(self.heartbeat(1)["accepted"])
        self.assertTrue(self.broker.project()["verified"])
        self.writer.close()
        self.reader.close()
        self.client.close()
        self.assertTrue(self.broker.disconnected.wait(3))
        self.assertEqual(self.broker.project(), {"state": "unknown", "verified": False})
        self.assertIsNone(self.broker.error)


if __name__ == "__main__":
    unittest.main()
