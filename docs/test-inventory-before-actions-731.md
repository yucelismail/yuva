# Yuva #731 — GitHub Actions öncesi test envanteri

**Tarih:** 2026-10-23
**Kapsam:** Kaynak ağacının statik envanteri. Testler bu görevde çalıştırılmadı.

## Mevcut test giriş noktası

- `tests/` altında `test_*.py` kalıbına uyan **64 unittest modülü** var.
- Testler Python standart kütüphanesindeki `unittest` ile yazılmış. Repo kökünde
  `pyproject.toml`, `tox.ini`, `setup.cfg`, `pytest.ini`, `noxfile.py` veya
  requirements dosyası bulunmuyor.
- README, Linux ve Python 3.8+ gereksinimi bildiriyor; CLI/panel için üçüncü
  taraf pip bağımlılığı olmadığını söylüyor. Bu envanter 3.8 uyumluluğunu
  çalıştırarak doğrulamadı; desteklenen Python matrisi ayrıca çapraz
  doğrulanmalı.
- Bulunan bir `.github/workflows` CI tanımı yok. Envanter için standart
  keşif komutu:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Bu komutun toplam test sayısı ve temiz runner süresi burada ölçülmedi.

## Modül envanteri

| Alan | Adet | Modüller |
|---|---:|---|
| Auth | 5 | `test_auth_init_cli`, `test_auth_key_lifecycle_fixture`, `test_auth_key_operation_receipts`, `test_auth_provision_cli`, `test_auth_provision_threat_model` |
| Backup/restore | 2 | `test_backup_verify`, `test_restore_check_cli_write_guard` |
| Lease, presence ve broker | 8 | `test_heartbeat_flock`, `test_lease_completion`, `test_lease_owner_projection`, `test_lease_writer`, `test_operator_broker_peercred_fixture`, `test_operator_custody_source_class`, `test_panel_presence_broker_principal_fixture`, `test_panel_presence_unix_session_fixture` |
| Panel, HTTP ve UI | 17 | `test_browser_session_csrf_route_fixture`, `test_panel_atomic_write`, `test_panel_browser_session_handler_fixture`, `test_panel_csp_report_only_fixture`, `test_panel_error_ephemeral_http`, `test_panel_get_snapshot_acceptance`, `test_panel_lifecycle`, `test_panel_revision_validation`, `test_panel_role_fallback_xss`, `test_panel_security_response_headers`, `test_panel_snapshot_allowlist_fixture`, `test_panel_snapshot_budget`, `test_panel_snapshot_budget_integration`, `test_panel_snapshot_screen_cursor_integration`, `test_panel_source_policy`, `test_panel_ui_accessibility`, `test_panel_ui_workflow` |
| Release | 6 | `test_release_acceptance`, `test_release_decision_form`, `test_release_installer`, `test_release_manifest`, `test_release_rollback_data_decision_fixture`, `test_release_staging_inventory` |
| Screen ve mesaj | 6 | `test_history_secret_scan_canary`, `test_message_source_authority`, `test_screen_migration`, `test_screen_redaction`, `test_screen_snapshot_redaction`, `test_shared_chat_context` |
| Task, CLI ve ledger | 13 | `test_cli_copy_compatibility_fixture`, `test_cli_copy_compatibility_gate`, `test_code_data_roots`, `test_data_schema_compat`, `test_legacy_task_write_guard`, `test_pending_queue_visibility`, `test_task_assignment_ephemeral_http`, `test_task_board_live_update_consistency_fixture`, `test_task_ledger_integrity`, `test_task_outbox_canonical_schema_fixture`, `test_task_outbox_canonical_writer_compat_fixture`, `test_task_outbox_nested_schema_fixture`, `test_task_principal_gate` |
| Yuva wait | 5 | `test_yuva_wait_cli_fixture`, `test_yuva_wait_end_to_end_fixture`, `test_yuva_wait_info_mode`, `test_yuva_wait_receipt_store`, `test_yuva_wait_source_class` |
| Diğer | 2 | `test_doctor`, `test_error_redaction` |

Tablodaki modül adlarına `.py` uzantısı eklenebilir. Sayılar statik dosya
sayımıdır; unittest case/metot toplamı değildir.

## Runner gereksinimleri ve CI sınırları

- Repo Linux/POSIX özelliklerine dayanır: README `fcntl` ve Linux `/proc`
  kullanımını açıkça bildiriyor. `test_heartbeat_flock` ve bazı broker/lease
  testleri bu aileyi kullanıyor; Windows runner desteklenen hedef değildir.
- Geçici loopback HTTP server açan modüller: `test_browser_session_csrf_route_fixture`,
  `test_cli_copy_compatibility_fixture`, `test_panel_browser_session_handler_fixture`,
  `test_panel_csp_report_only_fixture`, `test_panel_error_ephemeral_http`,
  `test_panel_get_snapshot_acceptance`, `test_panel_snapshot_budget_integration`,
  `test_task_assignment_ephemeral_http`. CI runner ephemeral localhost bind'e
  izin vermeli.
- `test_panel_presence_unix_session_fixture` geçici AF_UNIX socket ve Linux
  `SO_PEERCRED` kullanır. `test_operator_broker_peercred_fixture` da peer
  credential/soket davranışıyla ilgili özellikler kullanır. Gerçek iki UID,
  root, servis veya key provision eden test bu keşif kalıbında yoktur.
- Alt süreç başlatan fixture'lar bulunuyor. CI job timeout'u ve temiz teardown
  önemlidir; statik tarama belirli bir testin takılma süresi için garanti vermez.
- Test modülleri temp root ve sentetik veri kullanacak şekilde tasarlanmış olsa
  da bu görev kapsamındaki envanter her birinin izolasyonunu audit etmedi.
  Gerçek `YUVA_DIR` erişimini ayrıca taramak ve testte kapatmak takip işidir.
- `tests/fixtures/` altında CSP/browser route örnekleri var; bunlar test
  kaynaklarıdır, `test_*.py` modülü sayısına dahil değildir.

## CI hazırlığı için kalan doğrulama

Bu envanter CI workflow'u eklemez. Workflow öncesinde Python sürüm aralığı,
testte gerçek data-root erişiminin engellenmesi, temp-root disiplini, loopback
socket/teardown, subprocess timeout/cleanup, dış ağ bağımlılığı, locale/timezone
ve discovery'nin sıfır testte başarıyla dönmemesi ayrı kabul maddeleri olarak
incelenmelidir. Bunlar mevcut sıradaki görevlerde ayrıca ele alınmaktadır.
