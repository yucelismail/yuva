# Yuva #430 — HMAC çekirdeği v2 store bağımsız incelemesi

## Kapsam ve sonuç

Salt-okunur statik inceleme yapıldı: `panel/auth.py`, `panel/auth_store_v2.py`, `panel/auth_integration_draft.py`, `panel/AUTH_INTEGRATION_DRAFT.md` ve kabul edilen #412/#414/#415/#420 sözleşmeleri karşılaştırıldı. Dosya değiştirme, test ve runtime/panel çalıştırması yapılmadı.

`HMACAuthenticator` artık ayrı verifier/nonce dosyası kullanmıyor. İstenen tek-store kilit sınırı ve fail-closed davranışlar çekirdekte karşılanıyor. Bir orta önem düzeyinde, bilinen store rollback sınırı kalıyor: generation yalnız snapshot içinde olduğundan eski snapshot/backup geri yüklemesini dış çıpa olmadan saptamaz. HMAC çekirdeği server'a bağlanmamış ve feature-off durumda; bu inceleme canlı auth onayı değildir.

## Bulgular

### Orta — Eski store yedeği generation-floor olmadan kabul edilebilir

`panel/auth.py:173-186` önceden oluşturulmuş `AuthStateStore` alır; generation anchor zorunlu kılmaz. `panel/auth_store_v2.py:483-503` `generation_floor` değerini isteğe bağlı tutar, `514-516` yalnızca verilmiş tabandan düşük generation'ı reddeder. Bu nedenle varsayılan `generation_floor=None` ile aynı owner-only store'daki daha eski, kendi içinde geçerli snapshot ve ona ait lock geri yüklenirse daha önce iptal edilmiş bir anahtar yeniden etkin görünebilir ve tüketilmiş nonce kayıtları kaybolabilir. Bu, sistem saatinin geri sarılmasından ayrıdır: `transact()` mevcut duvar saatini snapshot `last_wall_time` ile karşılaştırıp rollback'i reddeder (`auth_store_v2.py:540-580`), fakat eski snapshot'ın kendi high-water/generation değerlerini geri getirmesini tanımaz.

Bu sınır #414 kabulünde tanımlandığı üzere offline, operatör kontrollü restore/re-provision işlemiyle yönetilmelidir; `auth_state_v2_store` modül belgesi de dış çıpa olmadan generation'ın backup rollback koruması olmadığını söyler (`auth_store_v2.py:1-15`, `476-485`). Restore sonrasında eski credential'ları kullanmamak ve anahtarları yeniden provision etmek gerekir. Çıpa sağlayan host entegrasyonu olmadan yedek geri dönüşüne karşı anti-rollback garantisi verilmemeli.

## Gereksinim eşlemesi

- **Anahtar bulma, iptal ve nonce tekilleştirmesi:** `auth.py:220-251` içindeki callback store'un kilitli snapshot'ında `keys` girdisini, `revoked`, audience, principal ve scope alanlarını denetliyor; HMAC'i aynı güncel kayıtla yeniden doğrulayıp nonce digest'ini `nonces` içine yazıyor. `AuthStateStore.transact()` callback'i tek persistent flock altında çalıştırıp tek atomik snapshot commit ediyor (`auth_store_v2.py:505-522`, `540-583`). Ayrı bir verifier okuması ile revoke yarışı kalmamış.
- **Nonce re-use ve sınır:** Aynı kapsam/principal/key/nonce digest'i varsa işlem `nonce_reused` ile reddediliyor; süresi geçmiş kayıtlar transaction içinde budanıyor ve `MAX_NONCES` doluysa `503 nonce_store_full` dönüyor (`auth.py:240-248`). Eski bağımsız nonce dosyasının eksik oluşunu boş store sayan yol kalmamış.
- **Clock high-water ve generation:** `transact(now=now)` aynı snapshot commit'inde `last_wall_time` ve `generation` değerlerini ilerletiyor; stored high-water'dan eski zaman callback'ten önce reddediliyor (`auth.py:205-215, 250-257`; `auth_store_v2.py:540-580`). Duvar saatinin geri sarımı fail-closed.
- **Eksik/bozuk store:** HMAC katmanı `AuthStateStore` örneği ister ve store hatalarını `AuthError`/503'e çevirir; eski dosyalara fallback yok (`auth.py:165-186, 250-257`). Store sabit lock ve snapshot dosyasını önceden provision edilmiş, private dosyalar olarak açar; eksik dosya `initialized_store_required`, bozuk şema `store_invalid` üretir (`auth_store_v2.py:308-330, 369-396, 476-481`).
- **Commit belirsizliği:** Store replace sonrası dizin `fsync` başarısızlığı `CommitUnknown` üretir (`auth_store_v2.py:399-446`); HMAC katmanı bunu `AuthError(503, "commit_unknown")` olarak döndürür ve principal vermez (`auth.py:250-262`). Nonce commit edilmiş olabilir; yeniden denemeyi kesin başarısız varsaymaz.
- **V1 uyumluluğu:** Constructor `verifier_path`/`nonce_path`/`lock_path` yerine tek `store` alıyor (`auth.py:165-186`). Eski ayrı dosyalar parse edilmiyor, otomatik migration veya fallback yok. V1'den geçiş offline operator provisioning gerektirir; v1 ve v2 consumer'larını ortak kullanmak güvenli migration sayılmaz (#412/#414).
- **Feature-off ve kapsam:** `panel/server.py` bu çekirdeği veya `auth_integration_draft.py`'yi import etmiyor; `HMACAuthenticator` kullanımı yalnız izole taslakta bulunuyor. Çekirdek entegrasyon görevi kapsam dışı olduğundan bu değişiklik auth'ı etkinleştirmiyor. Route gate, safe HTTP status dispatch'i, gerçek principal aktarımı ve CLI/HTTP fallback davranışı #426 entegrasyonunda ayrıca doğrulanmalı (#420).

## Açık blokajlar ve kabul kanıtı

1. Auth-state restore/rollback politikasını uygulama öncesi operator runbook'unda zorunlu kılın: eski snapshot dönüşü sonrasında anahtarları yeniden provision edin; dış trusted generation anchor eklenmedikçe eski snapshot'ın otomatik saptanacağını varsaymayın.
2. Server entegrasyonu hâlâ ayrı ve feature-off olmalı. AuthError'ın HTTP status'a dönüşmesi, auth'ın JSON parse/subprocess/handler'dan önce çalışması ve body kimliği yerine doğrulanmış principal kullanılması bu çekirdek incelemesiyle kanıtlanmış değildir.
3. Davranış testleri bu görevin kapsamı gereği çalıştırılmadı; bu rapor statik kod incelemesidir, runtime kabul kanıtı değildir.

## Kaynaklar

- `panel/auth.py:165-262` — store enjeksiyonu, auth kararları, nonce transaction'ı, store hata eşlemesi.
- `panel/auth_store_v2.py:308-396` — strict file/schema açılışı ve doğrulama.
- `panel/auth_store_v2.py:399-446` — atomic replace ve commit-unknown sınırı.
- `panel/auth_store_v2.py:476-583` — generation floor, stable lock, clock high-water ve transaction.
- `panel/AUTH_INTEGRATION_DRAFT.md:1-56`, `panel/auth_integration_draft.py:1-122` — feature-off route entegrasyon sözleşmesi.
- #412/#414/#415/#420 — v2 geçiş, recovery, fail-closed kabul ve mevcut çekirdek boşluk sözleşmeleri.
