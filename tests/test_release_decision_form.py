from __future__ import annotations

import unittest
from pathlib import Path

import release_decision_form


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/release-operator-decision-form-617.md"


def complete_form() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    field_values = {
        "Host/instance etiketi": "fixture-host-01",
        "Release ID / commit / payload SHA-256": "a" * 40 + "-" + "b" * 64,
        "INSTALL_ROOT / `current` target": "/opt/yuva/releases/fixture/current",
        "`YUVA_DIR` (mutlak, gerçek yol)": "/var/lib/yuva-fixture",
        "Operatör / veri sahibi": "operator-fixture / owner-fixture",
        "Güvenlik kabul sahibi": "security-fixture",
        "Kanıt paketi URI/yolu ve tarih": "evidence/release-01/index.json; 2026-10-23",
        "Değerlendirme tarihi": "2026-10-23",
    }
    lines = []
    for line in text.splitlines():
        if line.startswith("|") and line.endswith("|"):
            cells = line[1:-1].split("|")
            if len(cells) >= 2 and cells[0].strip() in field_values:
                cells[1] = " " + field_values[cells[0].strip()] + " "
                line = "|" + "|".join(cells) + "|"
            elif len(cells) >= 5 and cells[0].strip().startswith("**") and cells[0].strip()[2:3].isdigit():
                cells[1:4] = [" [x] ", " [ ] ", " [ ] "]
                cells[4] = " evidence/gates/gate-" + cells[0].strip()[2:].split(".", 1)[0] + ".json; fixture-owner; 2026-10-23 "
                line = "|" + "|".join(cells) + "|"
            elif len(cells) >= 4 and cells[0].strip() in release_decision_form.RISK_ROWS:
                cells[1:4] = [" fixture risk disposition ", " fixture-owner ", " evidence/risks/closed.json "]
                line = "|" + "|".join(cells) + "|"
        elif line.startswith("- [ ] İnsan-only erişim sınırı"):
            line = line.replace("[ ]", "[x]", 1)
        elif line.startswith("Kanıt referansı:"):
            line = "Kanıt referansı: evidence/exception/record.json  Sorumlu: fixture-owner"
        elif line.startswith("- Arşiv digest'i:"):
            line = "- Arşiv digest'i: " + "c" * 64
        elif line.startswith("- Digest'in arşiv/sidecar'dan bağımsız kaynak ve custody kanıtı:"):
            line = "- Digest'in arşiv/sidecar'dan bağımsız kaynak ve custody kanıtı: evidence/backup/custody.json"
        elif line.startswith("- Integrity/şema verify makbuzu:"):
            line = "- Integrity/şema verify makbuzu: evidence/backup/verify.json"
        elif line.startswith("- Scratch restore-check makbuzu ve hedef:"):
            line = "- Scratch restore-check makbuzu ve hedef: evidence/backup/restore.json"
        elif "--expected-sha256" in line:
            line = line.replace("[ ]", "[x]", 1)
        elif line.startswith("- Sonuç (yalnız biri):"):
            line = line.replace("[ ]", "[x]", 1)
        elif line.startswith("- Karar:"):
            line = line.replace("[ ]", "[x]", 1)
        elif line.startswith("- Kapsam dışı kalan risklerin açık kabulü / gerekçe:"):
            line = "- Kapsam dışı kalan risklerin açık kabulü / gerekçe: Fixture kapsamı; host kabulü değildir."
        elif line.startswith("- Release sorumlusu imza:"):
            line = "- Release sorumlusu imza: fixture-signer Tarih: 2026-10-23"
        elif line.startswith("- Veri sahibi imza:"):
            line = "- Veri sahibi imza: fixture-owner Tarih: 2026-10-23"
        elif line.startswith("- Güvenlik kabul sahibi imza:"):
            line = "- Güvenlik kabul sahibi imza: fixture-security Tarih: 2026-10-23"
        elif line.startswith("- Karar kaydı / kanıt paketi:"):
            line = "- Karar kaydı / kanıt paketi: evidence/decision/record.json"
        lines.append(line)
    return "\n".join(lines) + "\n"


def set_gate_status(text: str, number: int, status: str) -> str:
    markers = {"PASS": "[x] | [ ] | [ ]", "FAIL": "[ ] | [x] | [ ]",
               "UNKNOWN": "[ ] | [ ] | [x]"}[status]
    lines = text.splitlines()
    prefix = f"| **{number}."
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            start = line.index("[x] | [ ] | [ ]")
            lines[index] = line[:start] + markers + line[start + len("[x] | [ ] | [ ]"):]
            return "\n".join(lines) + "\n"
    raise AssertionError(f"gate {number} missing from fixture")


class ReleaseDecisionFormTests(unittest.TestCase):
    def test_syntactically_complete_form_is_local_go_only(self):
        result = release_decision_form.validate(complete_form())
        self.assertEqual("GO", result["decision"], result["issues"])
        self.assertEqual("not-verified", result["host_acceptance"])
        self.assertEqual("local-form-completeness-only", result["scope"])

    def test_release_identity_must_have_digest_or_release_id_shape(self):
        text = complete_form().replace("a" * 40 + "-" + "b" * 64, "release-latest", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("release_identity_format", result["issues"])

    def test_payload_sha256_form_is_accepted_and_malformed_value_rejected(self):
        text = complete_form().replace("a" * 40 + "-" + "b" * 64, "sha256:" + "d" * 64, 1)
        self.assertEqual("GO", release_decision_form.validate(text)["decision"])
        text = text.replace("sha256:" + "d" * 64, "sha256:abc", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("release_identity_format", result["issues"])

    def test_host_identity_must_be_a_single_bounded_label(self):
        text = complete_form().replace("fixture-host-01", "host name with spaces", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("host_identity_format", result["issues"])

    def test_dates_must_be_real_iso_calendar_dates(self):
        text = complete_form().replace("| Değerlendirme tarihi | 2026-10-23 |",
                                       "| Değerlendirme tarihi | 2026-02-30 |", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("assessment_date_format", result["issues"])

    def test_gate_evidence_requires_reference_owner_and_iso_date(self):
        text = complete_form().replace("evidence/gates/gate-1.json; fixture-owner; 2026-10-23",
                                       "not-a-reference; fixture-owner; yesterday", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("gate_evidence_format:1", result["issues"])

    def test_every_gate_pass_is_accepted_but_fail_and_unknown_are_no_go(self):
        base = complete_form()
        for number in range(1, 13):
            with self.subTest(gate=number, status="PASS"):
                self.assertEqual("GO", release_decision_form.validate(base)["decision"])
            for status in ("FAIL", "UNKNOWN"):
                with self.subTest(gate=number, status=status):
                    result = release_decision_form.validate(set_gate_status(base, number, status))
                    self.assertEqual("NO-GO", result["decision"])
                    self.assertIn(f"gate_not_pass:{number}", result["issues"])

    def test_gate_requires_exactly_one_status_checkbox(self):
        text = complete_form().replace("[x] | [ ] | [ ]", "[ ] | [ ] | [ ]", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("gate_status:1", result["issues"])
        text = complete_form().replace("[x] | [ ] | [ ]", "[x] | [x] | [ ]", 1)
        self.assertIn("gate_status:1", release_decision_form.validate(text)["issues"])

    def test_backup_digest_and_references_have_syntax_checks(self):
        text = complete_form().replace("c" * 64, "digest-unpinned", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("backup_digest_format", result["issues"])

    def test_signature_rows_require_signer_text_and_iso_date(self):
        text = complete_form().replace("fixture-signer Tarih: 2026-10-23",
                                       "fixture-signer Tarih: 23/10/2026", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("signature_or_date:Release sorumlusu imza", result["issues"])

    def test_all_three_signature_rows_are_required(self):
        for signer in ("Release sorumlusu", "Veri sahibi", "Güvenlik kabul sahibi"):
            with self.subTest(signer=signer):
                lines = [line for line in complete_form().splitlines()
                         if not line.startswith(f"- {signer} imza:")]
                result = release_decision_form.validate("\n".join(lines) + "\n")
                self.assertEqual("NO-GO", result["decision"])

    def test_unknown_or_placeholder_required_data_stays_no_go(self):
        text = complete_form().replace("/var/lib/yuva-fixture", "UNKNOWN", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertTrue(any(issue.startswith("release_field:") or
                            issue.startswith("absolute_path_format:")
                            for issue in result["issues"]))

    def test_record_reference_must_look_like_a_reference(self):
        text = complete_form().replace("evidence/decision/record.json", "just some words", 1)
        result = release_decision_form.validate(text)
        self.assertEqual("NO-GO", result["decision"])
        self.assertIn("signature_or_record:Karar kaydı / kanıt paketi", result["issues"])


if __name__ == "__main__":
    unittest.main()
