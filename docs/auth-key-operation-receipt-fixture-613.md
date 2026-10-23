# Yuva #613 — Auth create/revoke operation receipt fixture'ı

**Tarih:** 2026-10-23
**Sonuç:** Fixture-only transaction prototipi ve hedefli testler tamamlandı. Üretim `AuthStateStore` v2 formatı/validator'ı değiştirilmedi; auth açılmadı, gerçek key/token üretilmedi veya custody varsayılmadı.

## Karar ve kapsam

Baş denetçi `@Codex` şu yönü onayladı: geçerli v2 auth state içeren fixture-only snapshot, sınırlı `operations` receipts, aynı `.kilit`, tek atomik replace; exact replay sonucu tekrar döner, aynı operation ID farklı request digest ile çatışır; `CommitUnknown` sonrası readback yapılır ve mutasyon körlemesine yinelenmez. Üretim v2 şemasına dokunulmaz.

Bu karar `AuthStateStore` v2'ye genel receipt map'i eklemez. `prototypes/auth-key-lifecycle/operation_receipts.py`, geçerli auth-state-v2 snapshot'ını gerçek `panel/auth_store_v2.py:validate_state()` ile doğrulayan, yalnız geçici fixture'da çalışan bir dış zarf prototipidir:

```text
fixture snapshot = {
  fixture_version: 1,
  auth_state: <strict v2 snapshot>,
  operations: <bounded receipt map>
}
```

Zarf ve domain state aynı JSON snapshot'ında tutulur; `.kilit` altında bir transaction yeni auth state ve receipt'i birlikte hazırlar, tek `os.replace` ile yayınlar, ardından dizin `fsync` yapar. Böylece replace sonrası fsync hatası `CommitUnknown` olarak döner ama transaction'ın iki parçası aynı snapshot'tadır.

## Receipt ve idempotency sözleşmesi

Receipt'in minimal alanları: `principal_id`, `operation_id`, operation `kind`, kanonik isteğin SHA-256 `request_digest`'i, sonuç kodu, küçük hedef/result alanı ve commit generation. Receipt'e secret, private key, ham token veya istek gövdesi yazılmaz. Enrollment target olarak yalnız token digest'i zaten kullanılan identifier alanında taşınır; receipt request digest'inde de token digest'i ham token değil.

| Durum | Davranış |
|---|---|
| Yeni `enrollment.create` veya `key.revoke` operation ID | İş kuralı ve v2 state doğrulanır; domain state + receipt aynı generation'da yazılır |
| Aynı ID, principal, kind ve request digest | `replayed` + önceki receipt döner; generation artmaz, domain mutasyonu tekrar çağrılmaz |
| Aynı ID, farklı principal/kind/request digest | `operation_id_conflict`; domain state, receipt map ve generation değişmez |
| `CommitUnknown` | Otomatik retry yok; aynı operation bilgileriyle salt okunur readback, tam eşleşme `committed`, farklı/eksik eşleşme `unresolved` |
| Receipt adedi veya byte bütçesi aşılır | `operation_receipt_limit`; yeni domain mutation ve generation commit edilmez; receipt silinmez/eviction yapılmaz |
| JSON bozuk, wrapper şeması hatalı veya iç auth state v2 değil | `store_invalid`; işlem kapalı kalır, varsayılana dönülmez |

Fixture limitleri: en çok 256 receipt, operation map için 256 KiB ve tüm fixture snapshot'ı için mevcut store'un 1 MiB üst sınırı. Limit dolunca fail-closed ret vardır; retention/prune politikası prototipte yoktur.

## Fixture senaryoları

`tests/test_auth_key_operation_receipts.py` sekiz izole test içerir:

1. Create commit'i, aynı istek replay'i, generation'ın değişmemesi ve exact create readback.
2. Aynı operation ID ile farklı istek digest'inde conflict; state ve receipt değişmez.
3. Revoke ve pending enrollment iptali aynı snapshot'ta; exact revoke readback, replay ve ID çatışması.
4. Create sonrası directory `fsync` hatasıyla `CommitUnknown`; operation ID + request digest + domain enrollment alanlarıyla readback `committed`, yanlış digest `unresolved`; ikinci mutasyon yapılmaz.
5. Revoke sonrası directory `fsync` hatasıyla `CommitUnknown`; exact revoke state readback'i, mismatch `unresolved`.
6. Bozuk fixture receipt ve unsupported `auth_state.version=99` fail-closed `store_invalid` üretir.
7. Receipt adedi sınırında yeni state/receipt yazımı yapılmaz.
8. Receipt byte bütçesinde yeni state/receipt yazımı yapılmaz.

Çalıştırılan komut:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_auth_key_operation_receipts -v
```

Sonuç: **8 test geçti.** Testlerin tümü `TemporaryDirectory` altında sabit sentetik issuer bytes ile çalıştı; client/private key üretilmedi; live auth store, servis veya host custody kullanılmadı.

## Sınırlar

- Bu zarf üretim dosya formatı değildir ve mevcut v2 store tarafından okunamaz. Üretime almak için ayrı schema-version, bounded retention, audit/outbox, migration, backup/restore ve custody kararları gerekir.
- Prototip enrollment allowlist/scope/expiry ve issuer revoke etkisini gösterir; HTTP/CLI enrollment endpoint'i, key transferi veya auth activation sağlamaz.
- Receipt, aynı aktif fixture snapshot'ında transaction ilişkisinin kanıtıdır; dış anti-rollback anchor, bağımsız audit custody veya aynı UID süreçlerine karşı gizlilik sağlamaz.
- `CommitUnknown` sonrasında doğru sonuç receipt ve domain state beraber doğrulanınca `committed` olur. Eşleşmeyen/readback hatalı state, yeni operation ID ile tekrar denenmez.

## Kaynaklar

- `docs/auth-key-enrollment-lifecycle-fixture-591.md` — önceki lifecycle fixture'ı ve create/revoke boşluğu.
- `docs/auth-key-lifecycle-api-design-462.md` — gelecekteki bounded operation receipt/outbox önerisi ve üretim öncesi kapılar.
- `panel/auth_store_v2.py` — strict v2 snapshot doğrulama, stable lock, `transact()` ve `CommitUnknown` sözleşmesi.
- `prototypes/auth-key-lifecycle/operation_receipts.py`, `tests/test_auth_key_operation_receipts.py` — fixture zarfı ve hedefli testler.

Bu teslim prototip ve test kanıtıdır; üretim auth create/revoke akışı veya canlı kabul anlamına gelmez.
