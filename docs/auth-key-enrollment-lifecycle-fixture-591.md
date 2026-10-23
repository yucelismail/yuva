# Offline auth key enrollment ve lifecycle fixture prototipi (#591)

**Tarih:** 2026-10-23
**Durum:** Sentetik fixture ve hedefli testler tamamlandı; denetim için teslim ediliyor.
**Kapsam sınırı:** Yalnız `/tmp` altındaki geçici store ve sabit sentetik key byte'ları kullanıldı. Gerçek key/token üretilmedi veya çıktılandı; gerçek auth store, `YUVA_DIR`, auth gate, panel, servis ve host izinleri değiştirilmedi.

## Karar ve yetki sınırı

`yuva auth init` yalnız boş v2 store ve stable lock hazırlar; key enrollment veya auth açma yapmaz. #462 tasarımında önerilen HMAC key lifecycle mevcut endpoint/CLI değildir. #582 custody kararına göre broker/verifier UID'si, operator signer UID'si ve agent UID'leri ayrılıp hostta doğrulanana kadar **operator key enrollment, operator allowlist/custody işareti ve `operator` source sınıfı NO-GO** kalır. Owner-only `0600/0700` izinleri aynı UID process'lerini birbirinden ayırmaz. Aynı UID'deki agent key'i, signer'ı veya verifier store'u okuyabiliyorsa HMAC principal etiketi insan operatörü kanıtlamaz; auth kapalı kalmalıdır.

Enrollment ancak bağımsız operatör kökü ve kabul edilmiş custody ile değerlendirilebilir. Hedef principal ve audience önceden operator-managed allowlist'te olmalı; issuer key aktif ve allowlist'teki admin principal'a bağlı olmalı; istenen exact `METHOD /path` scope'ları issuer scope'larının alt kümesi olmalı. Enrollment expiry açık `now < expires_at <= issuer.expires_at` aralığında kalmalı ve ürünce onaylı kısa bir üst sınırla kısıtlanmalı. Store validator scope biçimini ve key/enrollment ilişkisini denetler; admin allowlist ve scope delegasyonu uygulama politikasıdır, store validator bunları tek başına garanti etmez.

## Lifecycle sırası

1. **Offline bootstrap:** Güvenilir host aracı ilk verifier key'i ve dış principal allowlist'ini bağımsız custody ile kurar. Secret yalnız hedef signer/verifier bileşenlerine korumalı kanaldan teslim edilir. URL, argv, environment, ortak sohbet, JSONL, ekran, log veya audit'e yazılmaz. `yuva auth init` bu adımın yerine geçmez.
2. **Enrollment oluşturma:** Doğrulanmış admin principal ve aktif issuer key için `operation_id`, hedef principal, audience, exact scope listesi ve expiry denetlenir. Ham enrollment token CSPRNG ile tek kullanımlık ve yüksek entropili üretilip yalnız kabul edilmiş kanaldan bir kez verilir; store'da sadece SHA-256 digest'iyle indekslenen `pending` kayıt kalır. Token digest'i audit/log'a yazılmaz. İstek, allowlist veya scope kontrolünü geçmezse state değişmez.
3. **Redeem:** İstemci kendi key'ini güvenilir istemci tarafında üretir ve yalnız kabul edilmiş korumalı redeem kanalında sunar; token geçerli/tek kullanımlık, enrollment pending ve süresi dolmamış, issuer aktif olmalıdır. Tek `AuthStateStore.transact()` içinde key eklenir, enrollment `consumed` yapılır; `operation_id`, key ID ve client-key fingerprint bağı aynı snapshot'a yazılır. Yanıt secret'ı tekrar içermez. Aynı operation ID, fingerprint ve key ID ile replay mevcut sonucu verir; farklı parametre veya operation ID tüketilmiş token'ı yeniden kullanamaz.
4. **Rotation:** Yeni key daha dar veya aynı zorunlu scope ve son kullanma tarihiyle ayrı enrollment üzerinden kurulur. Eski key yalnız yeni key'in onaylı, mutasyon yapmayan doğrulama yolunda çalıştığı kanıtlandıktan ve önceden kararlaştırılmış kısa overlap bitince revoke edilir. Kullanılabilir read-only probe yoksa endpoint deneme amaçlı çağrılmaz; rollout ilerlemez. Acil compromise'da overlap beklenmez; ilgili key ve issuer'ın pending enrollments tek transaction'da kapatılır, etkilenen client'lar yeni key ile yeniden provision edilir.
5. **Revoke:** Key silinmez; `revoked=true` tombstone'u tutulur. Issuer key iptalinde aynı transaction'da onun pending enrollment'ları `revoked` yapılır. Tüketilmiş enrollment/key bağı audit ve restore incelemesi için korunur. Revoke geri alınmaz; yeniden yetki yeni key/ID gerektirir.
6. **Readback ve recovery:** `CommitUnknown` sonrası kör retry, rollback, yeni operation ID veya anonim fallback yoktur. Consumer kapalı kalır. Aynı operation ID ve payload fingerprint/target ile state readback yapılır. Tam receipt eşleşirse mevcut commit sonucu kabul edilir; eksik/çelişkili/okunamayan state unresolved kalır ve offline operatör incelemesine gider. Store generation tek başına backup rollback'ini tespit etmez; güvenilir dış anchor yoksa eski snapshot'ı güvenli kabul etme.

## İşlem sonucu matrisi

| Olay | Beklenen sonuç | Sonraki işlem |
|---|---|---|
| Principal/operator allowlist yok; issuer bilinmiyor/revoked/expired | `principal_not_allowed` / `issuer_inactive` — transaction öncesi veya callback'te ret, state yazılmaz | Policy/issuer'ı operatör düzeltir; zayıf actor iddiasıyla devam yok. |
| Scope biçimi geçersiz veya issuer scope alt kümesi dışında | `scope_exceeds_issuer` — state yazılmaz | Yalnız önceden onaylı exact scope ile yeni işlem. |
| Enrollment expiry geçmiş, issuer expiry'sini aşıyor veya redeem sırasında dolmuş | `enrollment_expired*` — key kurulmaz | Pending kaydı kontrollü expire/revoke et; yeni enrollment/token, eski token tekrar kullanılmaz. |
| Enrollment digest zaten aynı alanlarla pending | Mevcut kayıt salt okunur karşılaştırılır; genel create-operation makbuzu yoksa yeni commit iddiası kurulmaz | Aynı state'i farklı operation sanma; operation map eklenmeden belirsiz create `CommitUnknown` otomatik çözülemez. |
| Aynı token ikinci kez, farklı operation/fingerprint/key ID ile redeem | `enrollment_already_consumed` — ikinci key yok | Fail-closed; credential sahibini ve olası compromise'ı incele. |
| `os.replace` öncesi kesin hata | Store API `commit_not_started`/mutation validation hatası | State readback ile doğrulanabilir; otomatik retry yok. Onaylı aynı operation ancak policy önkoşulları yeniden sağlanırsa değerlendirilebilir. |
| Replace gerçekleşti, directory `fsync` hata verdi veya sonuç belirsiz | `CommitUnknown` | Consumer kapalı; aynı redeem operation ID, fingerprint ve key ID ile readback. Tam enrollment/key ilişkisi eşleşirse committed; aksi halde unresolved. Kör tekrar yok. |
| Redeem CommitUnknown readback'te enrollment pending, receipt eksik, store bozuk veya alanlar çelişkili | unresolved / store error | Değişikliği tamamlandı varsayma veya yeni key ekleme; offline recovery ve güvenilir anchor incelemesi. |
| Create/revoke için CommitUnknown fakat genel operation receipt yok | Target state tek başına işlemin bu operation ID ile yapıldığını kanıtlayamaz | Mutasyonu tekrar etme; gelecekte bounded `operations` receipt'i aynı snapshot transaction'ına ekle veya operator-managed dış kayıtla uzlaştır. |
| Key revoke / pending enrollment revoke başarılı | Revoked tombstone ve enrollment değişiklikleri aynı snapshot generation'ında | Readback; audit event'i raw key/token/fingerprint olmadan ve atomik outbox kabul edilmeden başarı audit'i diye sunma. |

## Fixture ve kanıt

`prototypes/auth-key-lifecycle/fixture.py` gerçek `panel/auth_store_v2.py` `AuthStateStore` API'sini yalnız `TemporaryDirectory` altındaki işaretli, `0700` fixture root'a bağlar. İlk issuer ve client key'leri kod içindeki sabit sentinel byte'lardır; CSPRNG kullanılmaz, değerler stdout/log'a yazılmaz ve geçici store dışında saklanmaz. Prototip allowlist/scope/expiry kontrollerini, pending enrollment, redeem'in tek transaction'da key+consumed bağı kurmasını, rotation/revoke ve exact redeem readback'ini gösterir. Canlı auth handler, HTTP/CLI enrollment route'u veya key transferi uygulamaz.

`tests/test_auth_key_lifecycle_fixture.py` beş fixture senaryosunu doğrular:

1. Hedef principal allowlist'i, scope delegasyonu ve expiry reddinde generation ve store değişmez.
2. Redeem key'i bir kez tüketir; aynı operation replay'i yeni generation yazmaz; yanlış replay reddedilir; yeni key kurulup eski key revoke edilir.
3. Issuer revoke'u issuer key ile pending enrollment'ı aynı transaction'da kapatır; tekrar revoke idempotent `already_revoked` döner.
4. Redeem transaction'ı replace sonrası directory `fsync` hatasında `CommitUnknown` üretir; exact operation ID/fingerprint/key ID readback'i `committed`, mismatched key ID `unresolved` verir. Kod retry etmez.
5. Replace öncesi hata `commit_not_started` olarak kalır ve pending state değişmez; bozuk store `store_invalid` ile reddedilir.

Çalıştırma: `python3 -m unittest tests.test_auth_key_lifecycle_fixture -v` — **5 test geçti**.

## Üretim öncesi açık şartlar

Mevcut v2 schema'da redeem enrollment kaydı `operation_id` ve key fingerprint'ini tutar; create/revoke için genel operation receipt veya audit outbox yoktur. #462'de önerilen bounded operation/outbox alanı ve şema sürümü ayrı karar/uygulama gerektirir. Revoke'da sırf `revoked=true` readback'i bunun belli bir operation ID ile yapıldığını kanıtlamaz. Bu eksik kapanmadan create/revoke CommitUnknown idempotency'si üretim için çözüldü sayılamaz. Aynı UID custody sınırı, dış anti-rollback anchor, safe key transferi, bounded rate/body/store limitleri, operation receipt retention'ı, audit custody ve read-only client probe de kabul edilmeden enrollment API, `operator` source label veya `YUVA_AUTH_ENABLED=1` açılmamalıdır.

İlgili kararlar: `docs/auth-key-lifecycle-api-design-462.md`, `docs/auth-key-rotation-revoke-offline-501.md`, `docs/auth-init-578.md`, `docs/operator-hmac-custody-decision-582.md`.
