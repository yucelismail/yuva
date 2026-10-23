#!/usr/bin/env python3
"""Fail-closed completeness checker for the operator release decision form.

Checks Markdown completeness only; it cannot verify host state, evidence, or
the truth of operator statements.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import re

REQUIRED_FIELDS = (
    "Host/instance etiketi", "Release ID / commit / payload SHA-256",
    "INSTALL_ROOT / `current` target", "`YUVA_DIR` (mutlak, gerçek yol)",
    "Operatör / veri sahibi", "Güvenlik kabul sahibi",
    "Kanıt paketi URI/yolu ve tarih", "Değerlendirme tarihi",
)
RISK_ROWS = (
    "Process/namespace ve same-UID okuyucu görünürlüğü",
    "Gerçek browser/session/auth modu ve route kapsamı",
    "Proxy/tunnel/backend bypass",
    "Güncel release, PATH, unit, çalışan process ve eski writer'lar",
    "Gerçek `YUVA_DIR`, sahiplik, şema ve rollback uyumu",
    "Backup digest provenance/custody ve restore kararı", "Diğer",
)
PLACEHOLDER = re.compile(r"^(?:_+|\[\s*\]|todo|tbd|unknown|unset|n/?a|none|null|\.\.\.)$", re.I)
UNRESOLVED = re.compile(r"\b(?:unknown|tbd|todo|açık|bekliyor|kanıtlanmadı|doğrulanmadı|no-go|fail|başarısız|belirsiz)\b", re.I)
RELEASE_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})-[0-9a-f]{64}\Z")
SHA256 = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z", re.I)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
ISO_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?\Z")


def _cell(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^\*\*(.*)\*\*$", r"\1", value)
    value = re.sub(r"^`(.*)`$", r"\1", value)
    return value.strip()


def _filled(value: str) -> bool:
    value = _cell(value)
    if not value or PLACEHOLDER.fullmatch(value) or UNRESOLVED.search(value):
        return False
    return bool(re.sub(r"[_\s|:*`.-]", "", value))


def _valid_release_identity(value: str) -> bool:
    tokens = re.findall(r"(?<![0-9a-f])(?:[0-9a-f]{64}(?:-[0-9a-f]{64})?|"
                        r"[0-9a-f]{40}(?:-[0-9a-f]{64})?)(?![0-9a-f])",
                        value, flags=re.I)
    return any(RELEASE_ID.fullmatch(token) or SHA256.fullmatch(token)
               for token in tokens)


def _valid_iso_date(value: str) -> bool:
    value = _cell(value)
    try:
        if ISO_DATE.fullmatch(value):
            return date.fromisoformat(value).isoformat() == value
        if ISO_DATETIME.fullmatch(value):
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
    except ValueError:
        return False
    return False


def _valid_evidence_ref(value: str) -> bool:
    value = _cell(value)
    if value.lower().startswith("ref="):
        value = value[4:].strip()
    if not value or PLACEHOLDER.fullmatch(value) or UNRESOLVED.search(value):
        return False
    if SHA256.fullmatch(value):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", value):
        return True
    if value.startswith("/"):
        return not any(part in ("", ".", "..") for part in value.split("/")[1:])
    return ("/" in value and not any(ch.isspace() for ch in value)
            and not any(part in ("", ".", "..") for part in value.split("/")))


def _valid_gate_evidence(value: str) -> bool:
    parts = [part.strip() for part in value.split(";")]
    if len(parts) != 3:
        return False
    ref, owner, evidence_date = parts
    if ref.lower().startswith("ref="):
        ref = ref[4:].strip()
    if owner.lower().startswith("owner="):
        owner = owner[6:].strip()
    if evidence_date.lower().startswith("date="):
        evidence_date = evidence_date[5:].strip()
    return (_valid_evidence_ref(ref) and _filled(owner)
            and _valid_iso_date(evidence_date))


def _valid_evidence_package(value: str) -> bool:
    parts = [part.strip() for part in value.split(";")]
    if len(parts) != 2:
        return False
    reference, evidence_date = parts
    if evidence_date.lower().startswith("date="):
        evidence_date = evidence_date[5:].strip()
    return _valid_evidence_ref(reference) and _valid_iso_date(evidence_date)


def _valid_host_identity(value: str) -> bool:
    value = _cell(value)
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value))


def _valid_absolute_path(value: str) -> bool:
    value = _cell(value)
    return (value.startswith("/") and (value == "/" or
            not any(part in ("", ".", "..") for part in value.split("/")[1:])))


def _rows(text: str):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            yield [_cell(part) for part in line[1:-1].split("|")]


def _section(text: str, heading: str, next_heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    start = text.find("\n", start)
    end = text.find(next_heading, start + 1)
    return text[start:end if end >= 0 else len(text)]


def _checks(line: str) -> list[bool]:
    return [mark.lower() == "x" for mark in re.findall(r"\[([ xX])\]", line)]


def validate(text: str) -> dict[str, object]:
    issues: list[str] = []
    lines = text.splitlines()
    all_rows = list(_rows(text))
    if "operatör karar formu (#617)" not in text.lower():
        issues.append("form_identity")

    fields = {row[0]: row[1] for row in all_rows if len(row) >= 2}
    for label in REQUIRED_FIELDS:
        if not _filled(fields.get(label, "")):
            issues.append("release_field:" + label)
    if not _valid_host_identity(fields.get("Host/instance etiketi", "")):
        issues.append("host_identity_format")
    if not _valid_release_identity(fields.get("Release ID / commit / payload SHA-256", "")):
        issues.append("release_identity_format")
    for label in ("INSTALL_ROOT / `current` target", "`YUVA_DIR` (mutlak, gerçek yol)"):
        if not _valid_absolute_path(fields.get(label, "")):
            issues.append("absolute_path_format:" + label)
    if not _valid_evidence_package(fields.get("Kanıt paketi URI/yolu ve tarih", "")):
        issues.append("evidence_package_format")
    if not _valid_iso_date(fields.get("Değerlendirme tarihi", "")):
        issues.append("assessment_date_format")

    gate_text = _section(text, "## Zorunlu karar kapıları", "### İnsan-only istisnası")
    gates = []
    for row in _rows(gate_text):
        if len(row) < 5 or not re.match(r"\*\*\d+\.", row[0]):
            continue
        number = re.match(r"\*\*(\d+)\.", row[0]).group(1)
        selected = [i for i, cell in enumerate(row[1:4]) if re.search(r"\[[xX]\]", cell)]
        status = ("PASS", "FAIL", "UNKNOWN")[selected[0]] if len(selected) == 1 else None
        evidence = row[4]
        gates.append(number)
        if len(selected) != 1:
            issues.append("gate_status:" + number)
        elif status != "PASS":
            issues.append("gate_not_pass:" + number)
        if not _filled(evidence):
            issues.append("gate_evidence:" + number)
        elif UNRESOLVED.search(evidence):
            issues.append("gate_evidence_unresolved:" + number)
        elif not _valid_gate_evidence(evidence):
            issues.append("gate_evidence_format:" + number)
    if len(gates) != 12:
        issues.append("gate_rows_incomplete")

    exception = _section(text, "### İnsan-only istisnası", "### Backup pin ve authenticity kararı")
    exception_lines = [line for line in exception.splitlines() if "[ ]" in line or "[x]" in line.lower()]
    exception_checks = [value for line in exception_lines for value in _checks(line)]
    if len(exception_checks) != 3 or sum(exception_checks) != 1:
        issues.append("human_only_exception_selection")
    elif exception_checks[2]:
        issues.append("human_only_exception_declined_or_unknown")
    if exception_checks and exception_checks[0]:
        evidence_line = next((line for line in exception.splitlines()
                              if line.startswith("Kanıt referansı:")), "")
        match = re.fullmatch(r"Kanıt referansı:\s*(\S+)\s+Sorumlu:\s*(.+)", evidence_line)
        if not match or not _valid_evidence_ref(match.group(1)):
            issues.append("human_only_exception_evidence")
        elif not _filled(match.group(2)):
            issues.append("human_only_exception_owner")

    backup = _section(text, "### Backup pin ve authenticity kararı", "## Kalan `UNKNOWN` / risk kaydı")
    backup_fields = {}
    for line in backup.splitlines():
        if line.startswith("- ") and ":" in line:
            label, value = line[2:].split(":", 1)
            backup_fields[label.strip()] = value.strip()
    for label in ("Arşiv digest'i", "Digest'in arşiv/sidecar'dan bağımsız kaynak ve custody kanıtı",
                  "Integrity/şema verify makbuzu", "Scratch restore-check makbuzu ve hedef"):
        if not _filled(backup_fields.get(label, "")):
            issues.append("backup_field:" + label)
    if not SHA256.fullmatch(_cell(backup_fields.get("Arşiv digest'i", ""))):
        issues.append("backup_digest_format")
    for label in ("Digest'in arşiv/sidecar'dan bağımsız kaynak ve custody kanıtı",
                  "Integrity/şema verify makbuzu", "Scratch restore-check makbuzu ve hedef"):
        if not _valid_evidence_ref(backup_fields.get(label, "")):
            issues.append("backup_reference_format:" + label)
    expected = next((line for line in backup.splitlines() if "--expected-sha256" in line), "")
    if len(_checks(expected)) != 2 or sum(_checks(expected)) != 1:
        issues.append("backup_expected_digest_selection")
    backup_lines = backup.splitlines()
    auth_index = next((i for i, line in enumerate(backup_lines)
                       if "Sonuç (yalnız biri)" in line), -1)
    auth_line = backup_lines[auth_index] if auth_index >= 0 else ""
    if auth_index >= 0 and auth_index + 1 < len(backup_lines):
        if re.search(r"\[[ xX]\]", backup_lines[auth_index + 1]):
            auth_line += " " + backup_lines[auth_index + 1]
    auth = _checks(auth_line)
    if len(auth) != 3 or sum(auth) != 1:
        issues.append("backup_authenticity_selection")
    elif auth[2]:
        issues.append("backup_authenticity_not_proven")

    risk_text = _section(text, "## Kalan `UNKNOWN` / risk kaydı", "## Operatör kararı ve imzalar")
    risk_fields = {row[0]: row[1:] for row in _rows(risk_text)
                   if len(row) >= 4 and row[0] in RISK_ROWS}
    if set(risk_fields) != set(RISK_ROWS):
        issues.append("risk_rows_incomplete")
    for label in RISK_ROWS:
        values = risk_fields.get(label, [])
        if len(values) < 3 or any(not _filled(value) for value in values[:3]):
            issues.append("risk_record_incomplete:" + label)
        elif any(UNRESOLVED.search(value) for value in values[:3]):
            issues.append("risk_unresolved:" + label)

    decision = next((line for line in lines if line.strip().startswith("- Karar:")), "")
    decision_checks = _checks(decision)
    if len(decision_checks) != 2 or sum(decision_checks) != 1:
        issues.append("decision_selection")
    elif not decision_checks[0]:
        issues.append("operator_selected_no_go")

    for label in ("Kapsam dışı kalan risklerin açık kabulü / gerekçe",):
        line = next((line for line in lines if label in line), "")
        value = line.split(":", 1)[1] if ":" in line else ""
        if not _filled(value):
            issues.append("signature_or_record:" + label)
        elif UNRESOLVED.search(value):
            issues.append("signature_or_record_unresolved:" + label)
    for label in ("Release sorumlusu imza", "Veri sahibi imza", "Güvenlik kabul sahibi imza"):
        line = next((line for line in lines if label in line), "")
        value = line.split(":", 1)[1] if ":" in line else ""
        signature, separator, date = value.partition("Tarih:")
        if not separator or not _filled(signature) or not _valid_iso_date(date.strip()):
            issues.append("signature_or_date:" + label)
    label = "Karar kaydı / kanıt paketi"
    line = next((line for line in lines if label in line), "")
    value = line.split(":", 1)[1] if ":" in line else ""
    if not _valid_evidence_ref(value):
        issues.append("signature_or_record:" + label)

    issues = list(dict.fromkeys(issues))
    return {"scope": "local-form-completeness-only",
            "decision": "NO-GO" if issues else "GO",
            "host_acceptance": "not-verified", "gate_rows": len(gates), "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("form", type=Path, help="filled #617 Markdown form")
    args = parser.parse_args(argv)
    try:
        text = args.form.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        report = {"scope": "local-form-completeness-only", "decision": "NO-GO",
                  "host_acceptance": "not-verified", "issues": ["form_unreadable"]}
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2
    report = validate(text)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
