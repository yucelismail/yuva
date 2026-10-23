#!/usr/bin/env python3
"""In-memory contract fixture for the operator signer -> broker UDS boundary.

No socket, OS UID, HMAC key, verifier store, service or live Yuva route is used.
Signature and peer-credential outcomes are injected synthetic fixture inputs.
"""

from __future__ import annotations

import base64
import json
import re
import struct


MAX_FRAME_BYTES = 1_500_000
MAX_BODY_BYTES = 1_048_576
ALLOWED_FIELDS = {
    "version", "method", "path", "body_b64u", "principal_id", "key_id",
    "audience", "timestamp", "nonce", "signature",
}
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
ROUTE_SCOPE = "POST /api/yaz"


class FrameError(ValueError):
    pass


def encode_frame(frame: dict[str, object]) -> bytes:
    raw = json.dumps(frame, ensure_ascii=False, separators=(",", ":"),
                     sort_keys=True).encode("utf-8")
    if not raw or len(raw) > MAX_FRAME_BYTES:
        raise FrameError("frame_size_invalid")
    return struct.pack(">I", len(raw)) + raw


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FrameError("duplicate_frame_key")
        result[key] = value
    return result


def decode_frame(packet: bytes) -> dict[str, object]:
    if not isinstance(packet, bytes) or len(packet) < 5:
        raise FrameError("frame_truncated")
    length = struct.unpack(">I", packet[:4])[0]
    if length < 2 or length > MAX_FRAME_BYTES or len(packet) != length + 4:
        raise FrameError("frame_length_invalid")
    try:
        frame = json.loads(packet[4:].decode("utf-8"), object_pairs_hook=_unique_object)
    except FrameError:
        raise
    except (UnicodeError, json.JSONDecodeError):
        raise FrameError("frame_json_invalid") from None
    if not isinstance(frame, dict) or set(frame) != ALLOWED_FIELDS:
        raise FrameError("frame_schema_invalid")
    return frame


def _body_bytes(value: object) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise FrameError("body_encoding_invalid")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise FrameError("body_encoding_invalid")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, base64.binascii.Error):
        raise FrameError("body_encoding_invalid") from None
    if (not raw or len(raw) > MAX_BODY_BYTES
            or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value):
        raise FrameError("body_encoding_invalid")
    return raw


def _validate_payload(raw_body: bytes) -> bool:
    try:
        payload = json.loads(raw_body.decode("utf-8"), object_pairs_hook=_unique_object)
    except (FrameError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or not set(payload) <= {"metin", "kime", "tur"}:
        return False
    if not isinstance(payload.get("metin"), str) or not payload["metin"].strip():
        return False
    try:
        text_size = len(payload["metin"].encode("utf-8", errors="strict"))
    except UnicodeError:
        return False
    if text_size > 16_384:
        return False
    if "kime" in payload and not isinstance(payload["kime"], str):
        return False
    if "tur" in payload:
        if not isinstance(payload["tur"], str) or payload["tur"] not in {"not", "soru"}:
            return False
    return True


def broker_decision(packet: bytes, *, peer_uid: object, expected_peer_uid: object,
                    expected_principal: str, expected_key_id: str,
                    expected_audience: str, timestamp_now: int,
                    signature_verdict: str, nonce_state: set[str],
                    nonce_commit: str = "committed",
                    custody_verified: bool = True) -> dict[str, object]:
    """Model policy ordering; inputs named peer_uid/signature are fixture-only."""
    # In deployment, peer_uid comes from getsockopt(SO_PEERCRED), never frame data.
    if peer_uid != expected_peer_uid:
        return {"decision": "rejected", "reason": "peer_uid_not_allowlisted",
                "dispatch": False, "source_class": "unknown"}
    try:
        frame = decode_frame(packet)
    except FrameError as exc:
        return {"decision": "rejected", "reason": str(exc), "dispatch": False,
                "source_class": "unknown"}

    if type(frame["version"]) is not int or frame["version"] != 1:
        return {"decision": "rejected", "reason": "protocol_version_unsupported",
                "dispatch": False, "source_class": "unknown"}
    method, path = frame["method"], frame["path"]
    if method != "POST" or path != "/api/yaz":
        return {"decision": "rejected", "reason": "route_not_allowlisted",
                "dispatch": False, "source_class": "unknown"}
    if (frame["principal_id"] != expected_principal
            or frame["key_id"] != expected_key_id
            or frame["audience"] != expected_audience):
        return {"decision": "rejected", "reason": "principal_key_or_audience_mismatch",
                "dispatch": False, "source_class": "unknown"}
    if (not isinstance(frame["principal_id"], str)
            or not ID_RE.fullmatch(frame["principal_id"])
            or not isinstance(frame["key_id"], str)
            or not ID_RE.fullmatch(frame["key_id"])
            or not isinstance(frame["audience"], str)
            or not ID_RE.fullmatch(frame["audience"])):
        return {"decision": "rejected", "reason": "identifier_invalid",
                "dispatch": False, "source_class": "unknown"}
    if (type(frame["timestamp"]) is not int
            or abs(timestamp_now - frame["timestamp"]) > 60):
        return {"decision": "rejected", "reason": "timestamp_out_of_window",
                "dispatch": False, "source_class": "unknown"}
    if not isinstance(frame["nonce"], str) or not NONCE_RE.fullmatch(frame["nonce"]):
        return {"decision": "rejected", "reason": "nonce_invalid",
                "dispatch": False, "source_class": "unknown"}
    try:
        raw_body = _body_bytes(frame["body_b64u"])
    except FrameError as exc:
        return {"decision": "rejected", "reason": str(exc), "dispatch": False,
                "source_class": "unknown"}

    # Test harness injects a symbolic crypto result; this does not perform HMAC.
    if signature_verdict == "unavailable":
        return {"decision": "unknown", "reason": "verifier_unavailable",
                "dispatch": False, "source_class": "unknown"}
    if signature_verdict != "valid_fixture":
        return {"decision": "rejected", "reason": "signature_invalid",
                "dispatch": False, "source_class": "unknown"}
    if frame["nonce"] in nonce_state:
        return {"decision": "rejected", "reason": "nonce_replay",
                "dispatch": False, "source_class": "unknown"}
    if nonce_commit == "unknown":
        return {"decision": "unknown", "reason": "nonce_commit_unknown",
                "dispatch": False, "source_class": "unknown"}
    if nonce_commit != "committed":
        return {"decision": "unknown", "reason": "nonce_store_unavailable",
                "dispatch": False, "source_class": "unknown"}

    # Mirrors the real auth contract: nonce is consumed before body parsing or dispatch.
    nonce_state.add(frame["nonce"])
    if not _validate_payload(raw_body):
        return {"decision": "rejected", "reason": "payload_schema_invalid",
                "dispatch": False, "source_class": "unknown",
                "nonce_consumed": True}
    if not custody_verified:
        return {"decision": "rejected", "reason": "operator_custody_unverified",
                "dispatch": False, "source_class": "unknown",
                "nonce_consumed": True}
    return {"decision": "accepted", "reason": "authorized_exact_scope",
            "dispatch": True, "source_class": "operator",
            "nonce_consumed": True}


def _make_frame(*, nonce: str = "fixture_nonce_0000000000001",
                path: str = "/api/yaz", principal: str = "fixture-operator",
                audience: str = "fixture-yuva-instance",
                body: bytes | None = None) -> bytes:
    body = body or b'{"metin":"synthetic fixture message","kime":"@hepsi","tur":"not"}'
    frame = {
        "version": 1,
        "method": "POST",
        "path": path,
        "body_b64u": base64.urlsafe_b64encode(body).rstrip(b"=").decode("ascii"),
        "principal_id": principal,
        "key_id": "fixture-operator-key-id",
        "audience": audience,
        "timestamp": 1_800_000_000,
        "nonce": nonce,
        "signature": "SYNTHETIC_SIGNATURE_NOT_CRYPTOGRAPHIC",
    }
    return encode_frame(frame)


def run_fixture() -> dict[str, object]:
    # Strings are labels only: no local accounts or numeric UIDs are created.
    expected_peer = "synthetic-peer:operator-signer"
    agent_peer = "synthetic-peer:agent"
    args = {
        "expected_peer_uid": expected_peer,
        "expected_principal": "fixture-operator",
        "expected_key_id": "fixture-operator-key-id",
        "expected_audience": "fixture-yuva-instance",
        "timestamp_now": 1_800_000_000,
        "signature_verdict": "valid_fixture",
        "custody_verified": True,
    }
    results: dict[str, dict[str, object]] = {}
    results["authorized_exact_route"] = broker_decision(
        _make_frame(), peer_uid=expected_peer, nonce_state=set(), **args)
    results["agent_claims_operator"] = broker_decision(
        _make_frame(), peer_uid=agent_peer, nonce_state=set(), **args)
    results["wrong_principal_binding"] = broker_decision(
        _make_frame(principal="fixture-agent"), peer_uid=expected_peer,
        nonce_state=set(), **args)
    results["disallowed_task_route"] = broker_decision(
        _make_frame(path="/api/gorev"), peer_uid=expected_peer,
        nonce_state=set(), **args)
    results["query_variant_route"] = broker_decision(
        _make_frame(path="/api/yaz?x=1"), peer_uid=expected_peer,
        nonce_state=set(), **args)
    results["wrong_audience"] = broker_decision(
        _make_frame(audience="fixture-other-instance"), peer_uid=expected_peer,
        nonce_state=set(), **args)
    results["bad_signature"] = broker_decision(
        _make_frame(), peer_uid=expected_peer, nonce_state=set(),
        **{**args, "signature_verdict": "invalid_fixture"})
    results["nonce_commit_unknown"] = broker_decision(
        _make_frame(), peer_uid=expected_peer, nonce_state=set(),
        nonce_commit="unknown", **args)
    results["custody_unverified"] = broker_decision(
        _make_frame(), peer_uid=expected_peer, nonce_state=set(),
        **{**args, "custody_verified": False})
    results["body_identity_claim"] = broker_decision(
        _make_frame(body=b'{"metin":"synthetic fixture message",'
                         b'"kimden":"fixture-operator"}'),
        peer_uid=expected_peer, nonce_state=set(), **args)

    replay_state: set[str] = set()
    packet = _make_frame(nonce="fixture_nonce_replay_00000001")
    results["nonce_first_use"] = broker_decision(
        packet, peer_uid=expected_peer, nonce_state=replay_state, **args)
    results["nonce_replay"] = broker_decision(
        packet, peer_uid=expected_peer, nonce_state=replay_state, **args)

    # Extra identity/secret fields and duplicate JSON keys are rejected.
    extra = decode_frame(_make_frame())
    extra["peer_uid"] = expected_peer
    extra["raw_key"] = "must-not-exist-in-frame"
    results["extra_identity_or_secret_fields"] = broker_decision(
        encode_frame(extra), peer_uid=expected_peer, nonce_state=set(), **args)

    duplicate_json = (b'{"version":1,"method":"POST","method":"GET"}'
                      b'')
    duplicate_packet = struct.pack(">I", len(duplicate_json)) + duplicate_json
    results["duplicate_frame_field"] = broker_decision(
        duplicate_packet, peer_uid=expected_peer, nonce_state=set(), **args)

    expected = {
        "authorized_exact_route": ("accepted", True, "operator"),
        "agent_claims_operator": ("rejected", False, "unknown"),
        "wrong_principal_binding": ("rejected", False, "unknown"),
        "disallowed_task_route": ("rejected", False, "unknown"),
        "query_variant_route": ("rejected", False, "unknown"),
        "wrong_audience": ("rejected", False, "unknown"),
        "bad_signature": ("rejected", False, "unknown"),
        "nonce_commit_unknown": ("unknown", False, "unknown"),
        "custody_unverified": ("rejected", False, "unknown"),
        "body_identity_claim": ("rejected", False, "unknown"),
        "nonce_first_use": ("accepted", True, "operator"),
        "nonce_replay": ("rejected", False, "unknown"),
        "extra_identity_or_secret_fields": ("rejected", False, "unknown"),
        "duplicate_frame_field": ("rejected", False, "unknown"),
    }
    checks = {
        name: (results[name]["decision"], results[name]["dispatch"],
               results[name]["source_class"]) == expected[name]
        for name in expected
    }
    return {"fixture_only": True, "cases": results, "checks": checks}


def main() -> int:
    try:
        result = run_fixture()
        if not all(result["checks"].values()):
            print(json.dumps({"fixture_only": True, "result": "failed"}))
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"fixture_only": True, "error": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
