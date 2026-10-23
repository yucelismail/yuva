#!/usr/bin/env python3
"""Memory-only synthetic fixture for narrow command/output projection."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _duration_bucket(value_ms: int) -> str:
    if type(value_ms) is not int or value_ms < 0:
        return "unknown"
    if value_ms < 1000:
        return "under_1s"
    if value_ms < 10_000:
        return "1_to_10s"
    return "over_10s"


def _safe_report(observation: dict[str, object]) -> dict[str, object]:
    """Build a report from fixed fields; never inspect free-form output fields."""
    exit_code = observation.get("exit_code")
    if type(exit_code) is not int or not -255 <= exit_code <= 255:
        outcome = "unknown"
    else:
        outcome = "success" if exit_code == 0 else "failed"
    return {
        "schema": "command-summary/v1",
        "operation_id": "fixture-operation-01",
        "operation_class": "local_tool",
        "outcome": outcome,
        "duration_bucket": _duration_bucket(observation.get("duration_ms")),
        "output_policy": "stdout_stderr_omitted",
        "environment_policy": "values_not_recorded",
        "headers_policy": "values_not_recorded",
    }


def run_fixture() -> dict[str, object]:
    screen_redaction = _load_module(
        "yuva_output_fixture_screen_redaction", ROOT / "yuva_screen_redaction.py")
    agent_adapter = _load_module(
        "yuva_output_fixture_agent_adapter",
        ROOT / "prototypes/codex-app-server/adapter.py")

    # These sentinels are intentionally synthetic and remain in memory only.
    synthetic_unknown = "SYNTHETIC_UNKNOWN_SECRET_590_DO_NOT_USE"
    synthetic_bearer = "Bearer fixturetoken0123456789abcdef"
    observation = {
        "argv": ["tool", "--api-token", synthetic_unknown],
        "environment": {"API_TOKEN": synthetic_unknown,
                        "PRIVATE_CONFIG": "SYNTHETIC_ENV_VALUE_590"},
        "headers": {"Authorization": synthetic_bearer,
                    "X-Private-Header": synthetic_unknown},
        "stdout": f"completed; token={synthetic_unknown}; {synthetic_bearer}",
        "stderr": f"debug secret={synthetic_unknown}",
        "exit_code": 0,
        "duration_ms": 1500,
    }

    report = _safe_report(observation)
    screen_record = screen_redaction.redact_screen_record({
        "ts": "2026-10-23T12:00:00+00:00",
        "kimlik": "fixture-agent",
        "ad": "fixture-agent",
        "tur": "sonuc",
        # Fixed safe status text; no stdout/stderr or user-controlled content.
        "satir": "local tool completed; command output omitted",
    })

    # The protocol adapter gets an outputDelta event containing synthetic
    # content. Its current projection is expected to retain metadata only.
    adapter = agent_adapter.JsonRpcAdapter()
    projected_event = adapter.consume({
        "jsonrpc": "2.0",
        "method": "item/commandExecution/outputDelta",
        "params": {
            "threadId": "fixture-thread-01",
            "turnId": "fixture-turn-01",
            "item": {"id": "fixture-item-01"},
            "delta": f"{synthetic_unknown} {synthetic_bearer}",
        },
    })

    report_sink = io.StringIO()
    screen_sink = io.StringIO()
    protocol_sink = io.StringIO()
    report_sink.write(json.dumps(report, sort_keys=True, separators=(",", ":")))
    screen_sink.write(json.dumps(screen_record, sort_keys=True,
                                 separators=(",", ":")))
    protocol_sink.write(json.dumps(projected_event, sort_keys=True,
                                   separators=(",", ":")))
    sinks = (report_sink.getvalue(), screen_sink.getvalue(), protocol_sink.getvalue())

    known_pattern_after_redaction = screen_redaction.redact_text(synthetic_bearer)
    unknown_pattern_after_redaction = screen_redaction.redact_text(synthetic_unknown)
    return {
        "report": report,
        "screen_record": screen_record,
        "agent_protocol_projection": projected_event,
        "checks": {
            "synthetic_values_absent_from_report_screen_and_protocol": all(
                secret not in sink for secret in
                (synthetic_unknown, synthetic_bearer) for sink in sinks),
            "known_bearer_example_redacted": synthetic_bearer not in
                known_pattern_after_redaction,
            "unknown_secret_example_survives_regex_redaction":
                synthetic_unknown in unknown_pattern_after_redaction,
            "stdout_stderr_and_environment_omitted_by_allowlist": (
                "stdout" not in report and "stderr" not in report
                and "environment" not in report and "argv" not in report
                and "headers" not in report),
        },
    }


def main() -> int:
    try:
        result = run_fixture()
        if not all(result["checks"].values()):
            print(json.dumps({"fixture_only": True, "result": "failed"}))
            return 1
        print(json.dumps({"fixture_only": True, **result}, sort_keys=True))
        return 0
    except Exception as exc:
        # Error output is class-only; no fixture payload or exception text.
        print(json.dumps({"fixture_only": True,
                          "error": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
