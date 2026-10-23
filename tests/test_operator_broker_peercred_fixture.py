import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "prototypes" / "operator-broker-uds" / "peercred.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_operator_broker_peercred_fixture", MODULE_PATH,
    loader=SourceFileLoader("yuva_operator_broker_peercred_fixture", str(MODULE_PATH)))
peercred = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = peercred
SPEC.loader.exec_module(peercred)


@unittest.skipUnless(sys.platform == "linux" and hasattr(socket, "SO_PEERCRED"),
                     "Linux SO_PEERCRED fixture")
class OperatorBrokerPeerCredentialFixtureTests(unittest.TestCase):
    def test_kernel_uid_controls_allowlist_not_frame_claim(self):
        with tempfile.TemporaryDirectory(prefix="yuva-peercred-") as temp:
            root = Path(temp)
            root.chmod(0o700)
            socket_path = root / "broker.sock"
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(socket_path))
                socket_path.chmod(0o600)
                server.listen(1)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(str(socket_path))
                    with server.accept()[0] as accepted:
                        expected_uid = os.geteuid()
                        claimed_uid = expected_uid + 1
                        frame = json.dumps({"peer_uid": claimed_uid,
                                            "principal_id": "operator-signer"}).encode()
                        client.sendall(frame)

                        allowed = peercred.authorize_socket_peer(
                            accepted, {expected_uid: "operator-signer"})
                        self.assertTrue(allowed.accepted)
                        self.assertEqual(allowed.principal_id, "operator-signer")
                        self.assertEqual(allowed.credentials.uid, expected_uid)
                        self.assertEqual(allowed.credentials.pid, os.getpid())
                        self.assertEqual(accepted.recv(1024), frame)

                        # The forged frame value would match this map, but the
                        # kernel UID does not, so authorization fails.
                        forged = peercred.authorize_socket_peer(
                            accepted, {claimed_uid: "operator-signer"})
                        self.assertFalse(forged.accepted)
                        self.assertEqual(forged.reason, "peer_uid_not_allowlisted")
                        self.assertEqual(forged.credentials.uid, expected_uid)

    def test_invalid_mapping_and_unavailable_credentials_fail_closed(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            invalid_maps = (
                {True: "operator-signer"},
                {os.geteuid(): "same", os.geteuid() + 1: "same"},
                {os.geteuid(): ""},
            )
            for mapping in invalid_maps:
                with self.subTest(mapping=mapping):
                    result = peercred.authorize_socket_peer(left, mapping)
                    self.assertFalse(result.accepted)
                    self.assertEqual(result.reason, "uid_mapping_invalid")

            with patch.object(peercred.sys, "platform", "darwin"):
                result = peercred.authorize_socket_peer(
                    left, {os.geteuid(): "operator-signer"})
            self.assertFalse(result.accepted)
            self.assertEqual(result.reason, "peer_credentials_unavailable")
        finally:
            left.close()
            right.close()

    def test_non_unix_or_non_stream_socket_is_rejected(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as datagram:
            with self.assertRaisesRegex(peercred.PeerCredentialError, "peer_socket_invalid"):
                peercred.read_peer_credentials(datagram)


if __name__ == "__main__":
    unittest.main()
