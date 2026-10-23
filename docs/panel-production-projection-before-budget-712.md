# Production snapshot projection ve redaction sırası (#712)

**Durum:** Sentetik `TemporaryDirectory` + ephemeral HTTP fixture'ı. Gerçek `YUVA_DIR`, canlı panel, anonymous GET veya host verisi kullanılmadı/değişmedi.

## Kaynak incelemesi

#626 allowlist ve redaction'ın budget selector'dan önce uygulanmasını ister; #656 test-only Handler fixture'ı projection/redaction sırasını gösterir ama production bağlantısı olduğunu iddia etmez; #685 de production selector entegrasyonunun ve GET access kararının ayrı kalması gerektiğini belirtir. Güncel checkout'ta #695 selector `panel/server.py` production `Handler`'ına `YUVA_SNAPSHOT_BUDGET_ENABLED=1` ile bağlanmıştır. Request yolu `veri(defer_screen_cursor=True)` ile başlar, sonra `_snapshot_gonder()` selector'a geçer; selector final compact UTF-8 gövdesini aynı bayt dizisiyle gönderir ve yalnız başarılı seçimden sonra screen cursor ilerler. Varsayılan feature flag `0`/unset kalır.

Allowlist ve redaction selector çağrısından önce `veri()`/alt projection'lardadır:

| Veri | Projection/redaction öncesi boundary | Bütçeye giden biçim |
|---|---|---|
| Roster/state | `veri()` root kullanıcı kaydından yalnız UI alanlarını yeni dict'e alır; root/internal ve not/katılma/heartbeat girdileri seçilmez | `kimlik`, `ad`, `arac`, `rol`, `bas_denetci`, `sorumlu_kimlik`, `son_okuma` ve unverified presence enumları |
| Görev ledger | `_gorev_snapshot_proje()` task/event alanlarını allowlist eder; nested root/task/event unknown alanları taşınmaz | Task UI field set'i ve dar history event kayıtları |
| Chat/provenance | `mesajlar()` legacy/v1/v2 kaynaklarını doğrular/normalize eder, `_mesaj_snapshot_proje()` message/provenance alt alanlarını allowlist eder ve bilinen pattern'leri metinsel alanlarda redakte eder | UI message fields + dar provenance; `unknown/unverified` iddiaları authority olmaz |
| Screen | `tum_ekranlar()` bounded source reader'dan sonra her satırı `redact_screen_record()` üzerinden geçirir; invalid/unknown shape selector'a girmez | Doğrulanmış `{ts, kimlik, ad, tur, satir}` kayıtları ve sabit partial metadata |

Sıra: bounded source/read → field/item projection → known-pattern redaction → production global byte selection → final serialized bytes / `Content-Length`. Bilinmeyen credential biçimi, tam DLP, anonymous access veya kaynak içeriğinin kalıcı temizliği garanti edilmez.

## Yeni production-path fixture'ı

`tests/test_panel_snapshot_budget_integration.py` içine gerçek production `panel.server.H` ve production `panel/snapshot_budget.py` üzerinden geçen sentetik HTTP testi eklendi. Fixture state/task/chat/screen kayıtlarına beklenmeyen private root/row alanları ve synthetic bearer değerleri koyar. Selector `build_response()` spy'ı ile **selector'ın aldığı input** doğrudan incelenir: üst seviye ve nested roster/task/message/screen field set'leri exact allowlist ile eşleşir; secret canary'leri ve private sentinel'lar selection öncesi yoktur; redacted marker selector input'unda bulunur. Kaynak JSONL byte'ları request'ten sonra aynı kalır. HTTP body'nin `Content-Length` değeri actual response byte uzunluğuna eşittir ve raw canary içermez.

Çalıştırma:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_snapshot_budget_integration -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_snapshot_allowlist_fixture tests.test_panel_get_snapshot_acceptance -v
```

İlk suite production selector bağını, ikinci suite pure allowlist ve #656 test-only GET/wire fixture'ını kapsar. Ephemeral HTTP server yalnız geçici data rootu, stub browser session ve loopback port kullanır.

## Karar ve kalan sınır

Fixture, production selector'a forbidden private fields'in girmediğini ve redaction'ın global budget'tan önce yapıldığını kanıtlar; allowlist/redaction'ın `YUVA_DIR`'in tüm hassas verisini kaldırdığını göstermez. #574 anonymous full snapshot kararı **NO-GO** kalır. Budget feature unset/0 iken production eski wire body korunur; bu feature flag access control değildir ve selector'ı kapatmak GET'in riskini çözmez. Dış erişim, auth/session gate, owner onayı, unknown secret detection, RSS tavanı veya deployment kabulü bu görev kapsamında değildir.
