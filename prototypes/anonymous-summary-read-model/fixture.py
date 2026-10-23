#!/usr/bin/env python3
"""Synthetic in-memory fixture for summary projection and UI consumption."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_source() -> dict[str, object]:
    return {
        "ok": True,
        "simdi": "2026-10-23T12:00:00+00:00",
        "online_sn": 60,
        "rev": 99,
        "snapshot_meta": {"partial": False},
        "kullanicilar": {
            "fixture-agent": {
                "ad": "PRIVATE_FIXTURE_NAME_593",
                "arac": "PRIVATE_FIXTURE_TOOL_593",
                "rol": "admin",
                "not_": "PRIVATE_FIXTURE_PROFILE_NOTE_593",
                "sorumlu_kimlik": "PRIVATE_FIXTURE_RELATION_593",
                "online": True,
                "presence_verified": True,
                "presence_state": "online",
                "son_kalp": "2026-10-23T11:59:40+00:00",
                "son_gorulme": "PRIVATE_FIXTURE_LAST_SEEN_593",
            },
            "fixture-idle": {
                "ad": "PRIVATE_FIXTURE_NAME_2_593",
                "online": False,
                "presence_verified": False,
                "presence_state": "unknown",
                "son_kalp": "PRIVATE_FIXTURE_HEARTBEAT_593",
            },
        },
        "gorevler": [
            {"id": 90001, "durum": "pending",
             "baslik": "PRIVATE_FIXTURE_TASK_TITLE_593",
             "detay": "PRIVATE_FIXTURE_TASK_BODY_593",
             "not": "PRIVATE_FIXTURE_TASK_NOTE_593",
             "gecmis": [{"not": "PRIVATE_FIXTURE_TASK_HISTORY_593"}]},
            {"id": 90002, "durum": "verified",
             "baslik": "PRIVATE_FIXTURE_OLD_TITLE_593"},
        ],
        "mesajlar": [{"mesaj": "PRIVATE_FIXTURE_CHAT_593"}],
        "ekranlar": {"fixture-agent": ["PRIVATE_FIXTURE_SCREEN_593"]},
        "ekranlar_meta": {"raw": "PRIVATE_FIXTURE_SCREEN_META_593"},
    }


def _contains_fixture_private(value: object) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "PRIVATE_FIXTURE_" in encoded


def run_fixture() -> dict[str, object]:
    projection = _load("anonymous_summary_projection_fixture",
                       HERE / "project_fixture.py")
    consumer = _load("anonymous_summary_ui_consumer_fixture",
                     HERE / "ui_consumer.py")
    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    source = _synthetic_source()

    # Default-off mode must not expose source values.
    disabled = projection.project_summary(source, now=now)
    disabled_view = consumer.consume_summary(disabled)

    complete = projection.project_summary(source, enabled=True, now=now)
    complete_view = consumer.consume_summary(complete)

    partial_source = _synthetic_source()
    partial_source["snapshot_meta"] = {"partial": True}
    partial = projection.project_summary(partial_source, enabled=True, now=now)
    partial_view = consumer.consume_summary(partial)

    missing_roster_source = _synthetic_source()
    del missing_roster_source["kullanicilar"]
    missing_roster = projection.project_summary(
        missing_roster_source, enabled=True, now=now)
    missing_roster_view = consumer.consume_summary(missing_roster)

    # Exercise each health prerequisite independently. No bad or absent
    # heartbeat state is interpreted as offline.
    presence_variants = {
        "online_false": lambda source: source["kullanicilar"][
            "fixture-agent"].update(online=False),
        "presence_unverified": lambda source: source["kullanicilar"][
            "fixture-agent"].update(presence_verified=False),
        "presence_not_online": lambda source: source["kullanicilar"][
            "fixture-agent"].update(presence_state="unknown"),
        "heartbeat_missing": lambda source: source["kullanicilar"][
            "fixture-agent"].pop("son_kalp"),
        "heartbeat_malformed": lambda source: source["kullanicilar"][
            "fixture-agent"].update(son_kalp="not-a-timestamp"),
        "heartbeat_without_timezone": lambda source: source["kullanicilar"][
            "fixture-agent"].update(son_kalp="2026-10-23T11:59:40"),
        "heartbeat_stale": lambda source: source["kullanicilar"][
            "fixture-agent"].update(son_kalp="2026-10-23T11:58:59+00:00"),
        "heartbeat_future": lambda source: source["kullanicilar"][
            "fixture-agent"].update(son_kalp="2026-10-23T12:00:01+00:00"),
    }
    presence_projections = {}
    presence_views = {}
    for case, mutate in presence_variants.items():
        variant = _synthetic_source()
        mutate(variant)
        presence_projections[case] = projection.project_summary(
            variant, enabled=True, now=now)
        presence_views[case] = consumer.consume_summary(presence_projections[case])

    invalid_ttl_projections = {}
    for ttl in (True, 0, 301, "60"):
        variant = _synthetic_source()
        variant["online_sn"] = ttl
        invalid_ttl_projections[str(ttl)] = projection.project_summary(
            variant, enabled=True, now=now)

    ttl_boundary_projections = {}
    for ttl, heartbeat in ((1, now), (300, now - timedelta(seconds=300))):
        variant = _synthetic_source()
        variant["online_sn"] = ttl
        variant["kullanicilar"]["fixture-agent"]["son_kalp"] = heartbeat.isoformat()
        ttl_boundary_projections[str(ttl)] = projection.project_summary(
            variant, enabled=True, now=now)

    roster_variants = {}
    roster_source = _synthetic_source()["kullanicilar"]
    roster_inputs = {
        "roster_wrong_type": None,
        "roster_invalid_identity": {"bad identity": {"ad": "private"}},
        "roster_one_invalid_identity": {
            "fixture-agent": roster_source["fixture-agent"],
            "bad identity": {"ad": "private"}},
        "member_wrong_type": {"fixture-agent": "not-an-object"},
    }
    for case, roster in roster_inputs.items():
        variant = _synthetic_source()
        variant["kullanicilar"] = roster
        projected = projection.project_summary(variant, enabled=True, now=now)
        roster_variants[case] = (projected, consumer.consume_summary(projected))

    task_variants = {}
    for case, task_source in (
            ("task_source_missing", "missing"),
            ("task_source_wrong_type", None),
            ("task_status_unknown", [{"durum": "not-an-allowlisted-status"}])):
        variant = _synthetic_source()
        if task_source == "missing":
            del variant["gorevler"]
        else:
            variant["gorevler"] = task_source
        projected = projection.project_summary(variant, enabled=True, now=now)
        task_variants[case] = (projected, consumer.consume_summary(projected))

    source_metadata_variants = {}
    for case, metadata in (("metadata_missing", "missing"),
                           ("metadata_wrong_type", []),
                           ("metadata_partial_wrong_type", {"partial": 0})):
        variant = _synthetic_source()
        if metadata == "missing":
            del variant["snapshot_meta"]
        else:
            variant["snapshot_meta"] = metadata
        projected = projection.project_summary(variant, enabled=True, now=now)
        source_metadata_variants[case] = (
            projected, consumer.consume_summary(projected))

    unavailable_inputs = {
        "null_transport": None,
        "transport_error": {"ok": False, "hata": "source_unavailable"},
        "wrong_schema": {"schema": "anonymous-summary/v2", "state": "complete_for_allowlist",
                         "partial": False, "task_counts": {"counts": {}}},
    }
    unavailable_views = {
        case: consumer.consume_summary(value)
        for case, value in unavailable_inputs.items()
    }

    allowed_roster_fields = {"id", "health"}
    scenario_values = [
        *presence_projections.values(), *presence_views.values(),
        *invalid_ttl_projections.values(),
        *ttl_boundary_projections.values(),
        *(item for pair in roster_variants.values() for item in pair),
        *(item for pair in task_variants.values() for item in pair),
        *(item for pair in source_metadata_variants.values() for item in pair),
        *unavailable_views.values(),
    ]
    output_objects = [disabled, disabled_view, complete, complete_view,
                      partial, partial_view, missing_roster, missing_roster_view,
                      *scenario_values]
    allowed_view_fields = {"state", "banner", "roster_label", "roster",
                           "task_counts"}
    checks = {
        "default_off": (disabled["state"] == "disabled"
                        and disabled_view["state"] == "disabled"),
        "allowlist_exact": all(
            set(entry) == allowed_roster_fields
            for entry in complete["roster"]["entries"]),
        "complete_ui_states_summary_scope": (
            complete_view["state"] == "complete_for_allowlist"
            and "Summary only" in complete_view["banner"]),
        "partial_ui_does_not_show_total_or_task_counts": (
            partial_view["state"] == "partial"
            and "total unknown" in partial_view["roster_label"]
            and partial_view["task_counts"] is None),
        "missing_roster_not_rendered_as_zero": (
            missing_roster_view["state"] == "partial"
            and missing_roster_view["roster_label"] == "Roster unavailable"),
        "each_presence_failure_is_unknown": all(
            result["roster"]["entries"][0]["health"] == "unknown"
            and view["roster"][0]["health"] == "unknown"
            and "offline" not in json.dumps(view, ensure_ascii=False).lower()
            for result, view in zip(presence_projections.values(),
                                    presence_views.values())),
        "invalid_ttl_values_are_unknown": all(
            result["roster"]["entries"][0]["health"] == "unknown"
            for result in invalid_ttl_projections.values()),
        "ttl_boundaries_are_inclusive": all(
            result["roster"]["entries"][0]["health"] == "online"
            for result in ttl_boundary_projections.values()),
        "malformed_rosters_are_not_zero": all(
            result["state"] == "partial"
            and view["state"] == "partial"
            and (view["roster_label"] == "Roster unavailable"
                 or "total unknown" in view["roster_label"])
            for result, view in roster_variants.values()),
        "valid_roster_with_bad_entry_is_lower_bound": (
            roster_variants["roster_one_invalid_identity"][0]["roster"]["shown_count"] == 1
            and "at least 1" in roster_variants[
                "roster_one_invalid_identity"][1]["roster_label"].lower()),
        "missing_or_unknown_task_source_has_no_counts": all(
            result["state"] == "partial"
            and result["task_counts"]["state"] == "unavailable"
            and result["task_counts"]["counts"] is None
            and view["task_counts"] is None
            for result, view in task_variants.values()),
        "missing_or_malformed_metadata_is_partial": all(
            result["state"] == "partial" and result["partial"] is True
            and "source_completeness_unknown" in result["partial_reasons"]
            and view["state"] == "partial"
            for result, view in source_metadata_variants.values()),
        "wrong_schema_and_transport_are_unavailable": all(
            view["state"] == "unavailable"
            and view["task_counts"] is None
            and view["roster_label"] == "Roster unavailable"
            for view in unavailable_views.values()),
        "ui_view_is_summary_only_and_read_only": (
            set(complete_view) == allowed_view_fields
            and all("action" not in key.lower() and "href" not in key.lower()
                    for key in complete_view)),
        "fixture_private_fields_absent": not any(
            _contains_fixture_private(value) for value in output_objects),
        "no_detail_sections_in_projection": not any(
            key in json.dumps(complete, ensure_ascii=False)
            for key in ("mesajlar", "ekranlar", "baslik", "detay", "not_", "gecmis")),
    }
    return {
        "fixture_only": True,
        "complete_projection": complete,
        "complete_ui_view": complete_view,
        "partial_ui_view": partial_view,
        "missing_roster_ui_view": missing_roster_view,
        "presence_failure_cases": list(presence_projections),
        "invalid_ttl_cases": list(invalid_ttl_projections),
        "ttl_boundary_cases": list(ttl_boundary_projections),
        "malformed_roster_cases": list(roster_variants),
        "task_incomplete_cases": list(task_variants),
        "source_metadata_cases": list(source_metadata_variants),
        "unavailable_consumer_cases": list(unavailable_views),
        "checks": checks,
    }


def main() -> int:
    try:
        result = run_fixture()
        if not all(result["checks"].values()):
            print(json.dumps({"fixture_only": True, "result": "failed"}))
            return 1
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"fixture_only": True,
                          "error": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
