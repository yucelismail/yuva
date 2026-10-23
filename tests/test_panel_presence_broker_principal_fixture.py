import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "prototypes" / "panel-presence-principal" / "projection.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_panel_presence_principal_fixture", PATH,
    loader=SourceFileLoader("yuva_panel_presence_principal_fixture", str(PATH)))
projection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = projection
SPEC.loader.exec_module(projection)


class PanelPresenceBrokerPrincipalFixtureTests(unittest.TestCase):
    def setUp(self):
        self.peer = projection.PeerEvidence(101, 1001, 1001)
        self.bindings = {
            1001: projection.PrincipalBinding("agent-a", 1001, "map-7")
        }
        self.session = projection.SessionEvidence(
            "agent-a", "session-a", 101, 1001, "map-7", "epoch-3",
            "presence:read", True, True, 150.0)
        self.heartbeat = projection.HeartbeatEvidence(
            "session-a", 5, 100.0, "epoch-3")
        self.kwargs = dict(now_monotonic=110.0, current_map_revision="map-7",
                           current_broker_epoch="epoch-3", heartbeat_ttl=60,
                           feature_enabled=True)

    def project(self, **overrides):
        args = dict(peer=self.peer, bindings=self.bindings,
                    session=self.session, heartbeat=self.heartbeat)
        args.update(overrides)
        return projection.project_presence(**args, **self.kwargs)

    def test_only_matching_peer_current_principal_and_allowed_session_is_online(self):
        result = self.project()
        self.assertEqual((result.online, result.presence_state,
                          result.presence_verified, result.principal_id),
                         (True, "online", True, "agent-a"))

    def test_feature_off_is_unknown_even_with_complete_synthetic_evidence(self):
        result = projection.project_presence(
            self.peer, self.bindings, self.session, self.heartbeat,
            **{**self.kwargs, "feature_enabled": False})
        self.assertEqual(result.reason, "feature_off")
        self.assertFalse(result.online or result.presence_verified)

    def test_missing_or_unmapped_peer_and_session_fail_closed(self):
        self.assertEqual(self.project(peer=None).presence_state, "unknown")
        self.assertEqual(self.project(bindings={}).reason, "principal_map_missing")
        self.assertEqual(self.project(session=None).presence_state, "unknown")

    def test_stale_map_wrong_uid_or_inactive_principal_is_unknown(self):
        self.assertEqual(projection.project_presence(
            self.peer, self.bindings, self.session, self.heartbeat,
            **{**self.kwargs, "current_map_revision": "map-8"}).presence_state,
            "unknown")
        wrong_uid = projection.PeerEvidence(101, 1002, 1002)
        self.assertEqual(self.project(peer=wrong_uid).presence_state, "unknown")
        inactive = {1001: projection.PrincipalBinding(
            "agent-a", 1001, "map-7", active=False)}
        self.assertEqual(self.project(bindings=inactive).presence_state, "unknown")

    def test_unverified_disallowed_wrong_scope_or_stale_session_is_unknown(self):
        for changed in (
            {"authenticated": False}, {"allowed": False},
            {"scope": "presence:write"}, {"peer_pid": 102},
            {"principal_id": "agent-b"}, {"expires_at_monotonic": 110.0},
            {"broker_epoch": "epoch-2"},
        ):
            with self.subTest(changed=changed):
                session = projection.SessionEvidence(
                    **{**self.session.__dict__, **changed})
                self.assertEqual(self.project(session=session).presence_state,
                                 "unknown")

    def test_missing_stale_or_unbound_heartbeat_is_unknown(self):
        self.assertEqual(self.project(heartbeat=None).presence_state, "unknown")
        stale = projection.HeartbeatEvidence("session-a", 5, 40.0, "epoch-3")
        self.assertEqual(self.project(heartbeat=stale).presence_state, "unknown")
        wrong_session = projection.HeartbeatEvidence(
            "session-b", 5, 100.0, "epoch-3")
        self.assertEqual(self.project(heartbeat=wrong_session).presence_state,
                         "unknown")

    def test_body_claim_never_selects_or_spoofs_principal(self):
        matching = projection.HeartbeatEvidence(
            "session-a", 5, 100.0, "epoch-3", "agent-a")
        self.assertEqual(self.project(heartbeat=matching).principal_id, "agent-a")
        forged = projection.HeartbeatEvidence(
            "session-a", 5, 100.0, "epoch-3", "agent-b")
        self.assertEqual(self.project(heartbeat=forged).reason,
                         "body_principal_claim_conflicts")
        self.assertFalse(self.project(heartbeat=forged).presence_verified)

    def test_ambiguous_principal_map_is_unknown(self):
        bindings = {
            1001: projection.PrincipalBinding("agent-a", 1001, "map-7"),
            1002: projection.PrincipalBinding("agent-a", 1002, "map-7"),
        }
        self.assertEqual(self.project(bindings=bindings).reason,
                         "principal_map_invalid_or_ambiguous")


if __name__ == "__main__":
    unittest.main()
