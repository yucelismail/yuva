#!/usr/bin/env python3
"""Disposable two-UID Linux SO_PEERCRED acceptance fixture.

Requires root and two existing non-root local UIDs. The only filesystem
mutation is a temporary directory/socket tree removed on exit. This exercises
the kernel peer-UID gate, not a production broker, signer, or writer.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any


PEERCRED_PATH = Path(__file__).with_name("peercred.py")
MAX_FRAME = 4096


def _load_peercred():
    import importlib.util

    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("yuva_two_uid_peercred", PEERCRED_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_frame(peer: socket.socket) -> dict[str, Any] | None:
    data = bytearray()
    while len(data) <= MAX_FRAME:
        chunk = peer.recv(min(1024, MAX_FRAME + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break
    if len(data) > MAX_FRAME or b"\n" not in data:
        return None
    try:
        value = json.loads(bytes(data).split(b"\n", 1)[0].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _serve(socket_path: Path, broker_uid: int, signer_uid: int) -> int:
    """Internal child: run the actual SO_PEERCRED helper as broker UID."""
    try:
        peercred = _load_peercred()
        if os.geteuid() != broker_uid:
            return 21
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(os.fspath(socket_path))
            os.chmod(socket_path, 0o666)
            listener.listen(2)
            for index in range(2):
                connection, _ = listener.accept()
                with connection:
                    auth_map = ({signer_uid: "fixture-signer"} if index == 0
                                else {broker_uid: "fixture-broker"})
                    auth = peercred.authorize_socket_peer(connection, auth_map)
                    frame = _read_frame(connection)
                    operation_ok = (isinstance(frame, dict)
                                    and frame.get("operation") == "fixture-noop")
                    dispatch_count = int(auth.accepted and operation_ok)
                    result = {
                        "broker_uid": os.geteuid(),
                        "peer_uid": auth.credentials.uid if auth.credentials else None,
                        "accepted": auth.accepted,
                        "reason": auth.reason,
                        "principal_id": auth.principal_id,
                        "fixture_dispatch_count": dispatch_count,
                    }
                    connection.sendall(json.dumps(result, sort_keys=True).encode("ascii") + b"\n")
    except (OSError, RuntimeError, ValueError):
        return 22
    return 0


def _client(socket_path: Path, claimed_uid: int, claimed_principal: str) -> int:
    frame = {"peer_uid": claimed_uid, "principal_id": claimed_principal,
             "operation": "fixture-noop"}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(os.fspath(socket_path))
        client.sendall(json.dumps(frame, separators=(",", ":")).encode("ascii") + b"\n")
        client.shutdown(socket.SHUT_WR)
        data = bytearray()
        while len(data) <= MAX_FRAME:
            chunk = client.recv(min(1024, MAX_FRAME + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b"\n" in chunk:
                break
    if len(data) > MAX_FRAME:
        return 31
    try:
        result = json.loads(bytes(data).split(b"\n", 1)[0].decode("ascii"))
    except (UnicodeError, json.JSONDecodeError):
        return 32
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def _setpriv_command(setpriv: str, uid: int, gid: int, *command: str) -> list[str]:
    return [setpriv, "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all",
            "--reuid", str(uid), "--regid", str(gid), "--clear-groups", "--", *command]


def _run_as(setpriv: str, uid: int, gid: int, *command: str,
            timeout: float = 8) -> subprocess.CompletedProcess:
    env = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(_setpriv_command(setpriv, uid, gid, *command),
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, timeout=timeout,
                          check=False)


def run_acceptance(broker_uid: int, signer_uid: int) -> dict[str, object]:
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise ValueError("linux_so_peercred_required")
    if os.geteuid() != 0:
        raise ValueError("root_required_for_disposable_uid_fixture")
    if (type(broker_uid) is not int or type(signer_uid) is not int
            or broker_uid <= 0 or signer_uid <= 0 or broker_uid == signer_uid):
        raise ValueError("two_distinct_non_root_uids_required")
    try:
        broker_gid = pwd.getpwuid(broker_uid).pw_gid
        signer_gid = pwd.getpwuid(signer_uid).pw_gid
    except KeyError:
        raise ValueError("both_uids_must_be_existing_local_accounts") from None
    setpriv = shutil.which("setpriv")
    if not setpriv:
        raise ValueError("setpriv_unavailable")

    script = os.fspath(Path(__file__).resolve())
    python = os.fspath(Path(sys.executable).resolve())
    with tempfile.TemporaryDirectory(prefix="yuva-peercred-two-uid-") as temporary:
        root = Path(temporary)
        root.chmod(0o711)
        socket_dir = root / "broker-runtime"
        socket_dir.mkdir(mode=0o711)
        os.chown(socket_dir, broker_uid, broker_gid)
        socket_dir.chmod(0o711)
        socket_path = socket_dir / "broker.sock"
        server = subprocess.Popen(
            _setpriv_command(setpriv, broker_uid, broker_gid, python, script,
                             "--serve", os.fspath(socket_path),
                             str(broker_uid), str(signer_uid)),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"},
            close_fds=True)
        try:
            deadline = time.monotonic() + 5
            while not socket_path.is_socket() and time.monotonic() < deadline:
                if server.poll() is not None:
                    raise ValueError("broker_fixture_start_failed")
                time.sleep(0.025)
            if not socket_path.is_socket():
                raise ValueError("broker_fixture_start_timeout")

            # Deliberately forge body identity claims. The server derives the
            # accepted principal from the signer's real kernel UID instead.
            positive = _run_as(
                setpriv, signer_uid, signer_gid, python, script, "--client",
                os.fspath(socket_path), str(broker_uid), "forged-principal")
            negative = _run_as(
                setpriv, signer_uid, signer_gid, python, script, "--client",
                os.fspath(socket_path), str(signer_uid), "fixture-signer")
            if positive.returncode or negative.returncode:
                raise ValueError("fixture_client_failed")
            try:
                positive_result = json.loads(positive.stdout.decode("ascii"))
                negative_result = json.loads(negative.stdout.decode("ascii"))
            except (UnicodeError, json.JSONDecodeError):
                raise ValueError("fixture_response_invalid") from None
            server_code = server.wait(timeout=5)
            if server_code != 0:
                raise ValueError("broker_fixture_failed")

            passed = (
                positive_result.get("broker_uid") == broker_uid
                and positive_result.get("peer_uid") == signer_uid
                and positive_result.get("accepted") is True
                and positive_result.get("principal_id") == "fixture-signer"
                and positive_result.get("fixture_dispatch_count") == 1
                and negative_result.get("broker_uid") == broker_uid
                and negative_result.get("peer_uid") == signer_uid
                and negative_result.get("accepted") is False
                and negative_result.get("reason") == "peer_uid_not_allowlisted"
                and negative_result.get("fixture_dispatch_count") == 0
            )
            return {
                "scope": "two-uid-kernel-peercred-fixture-only",
                "decision": "PASS" if passed else "FAIL",
                "host_acceptance": "not-verified",
                "uid_separation": broker_uid != signer_uid,
                "positive": {
                    "broker_uid": broker_uid,
                    "peer_uid": positive_result.get("peer_uid"),
                    "accepted": positive_result.get("accepted"),
                    "body_identity_ignored": positive_result.get("principal_id") == "fixture-signer",
                    "fixture_dispatch_count": positive_result.get("fixture_dispatch_count"),
                },
                "negative": {
                    "broker_uid": broker_uid,
                    "peer_uid": negative_result.get("peer_uid"),
                    "accepted": negative_result.get("accepted"),
                    "reason": negative_result.get("reason"),
                    "fixture_dispatch_count": negative_result.get("fixture_dispatch_count"),
                },
                "issues": [] if passed else ["two_uid_acceptance_assertion_failed"],
            }
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-uid", type=int, help="existing non-root broker fixture UID")
    parser.add_argument("--signer-uid", type=int, help="different existing non-root signer fixture UID")
    parser.add_argument("--serve", nargs=3, metavar=("SOCKET", "BROKER_UID", "SIGNER_UID"),
                        help=argparse.SUPPRESS)
    parser.add_argument("--client", nargs=3, metavar=("SOCKET", "CLAIMED_UID", "CLAIMED_PRINCIPAL"),
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.serve:
        return _serve(Path(args.serve[0]), int(args.serve[1]), int(args.serve[2]))
    if args.client:
        try:
            return _client(Path(args.client[0]), int(args.client[1]), args.client[2])
        except (OSError, ValueError, TimeoutError):
            return 33
    if args.broker_uid is None or args.signer_uid is None:
        parser.error("--broker-uid and --signer-uid are required")
    try:
        result = run_acceptance(args.broker_uid, args.signer_uid)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        code = str(error) if str(error) in {
            "linux_so_peercred_required", "root_required_for_disposable_uid_fixture",
            "two_distinct_non_root_uids_required", "both_uids_must_be_existing_local_accounts",
            "setpriv_unavailable", "broker_fixture_start_failed",
            "broker_fixture_start_timeout", "fixture_client_failed",
            "fixture_response_invalid", "broker_fixture_failed",
        } else "fixture_unavailable"
        result = {"scope": "two-uid-kernel-peercred-fixture-only",
                  "decision": "NO-GO", "host_acceptance": "not-verified",
                  "issues": [code]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
