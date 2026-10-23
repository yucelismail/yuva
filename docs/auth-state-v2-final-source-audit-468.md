# Yuva #468 — Auth-state v2 operasyon kılavuzu son kaynak denetimi

## Sonuç

`docs/auth-state-v2-operations.md`, güncel `panel/auth_store_v2.py`, `panel/auth.py`, `panel/server.py`, `panel/auth_integration_draft.py` ve Yuva görev durumlarıyla yeniden karşılaştırıldı. İnceleme salt okunur yapıldı; kod, test ve runtime çalıştırılmadı.

Kılavuzun özellikle istenen dört güvenlik sınırı kaynakla uyumludur:

1. **Default-off:** `auth_gate_yukle()` içinde `YUVA_AUTH_ENABLED` yok veya `0` ise `None` döner; yalnız tam `1` gate kurmayı dener. Diğer değerler startup hatasıdır. Store root/audience eksikliği, import/store doğrulama hatası veya audience uyuşmazlığı da sunucu başlangıcını durdurur; anonim moda düşüş yoktur (`panel/server.py`, `auth_gate_yukle()` ve startup çağrısı).
2. **GET auth dışı:** `do_GET()` `/api/veri`, `/veri`, `/` ve `/index.html` yollarını işler; `AuthGate` çağırmaz. `do_POST()` ise gate ayarlıysa ham request-target/body doğrulamasını JSON parse ve handler dispatch öncesinde yapar. Bu yüzden GET snapshot ve HTML için auth/gizlilik sağlandığı varsayılamaz.
3. **Provisioning/backup aracı yok:** `AuthStateStore` önceden hazırlanmış root, snapshot ve sabit lock dosyası ister; bunları bootstrap etmez. `encode_initial_state()` yalnız bellekte serialize/doğrulama yapar, dosyaya yazmaz. `auth.py` doğrulama ve nonce tüketimi sunar; mevcut API route tablosunda key/enrollment yönetimi veya backup/restore endpoint'i yoktur. Bu nedenle kılavuzun elle canlı store düzenlemeyi desteklenen operasyon saymama ve onaylı host aracı/runbook olmadığını belirtme kararı doğrudur.
4. **Generation rollback sınırı:** Snapshot generation ve `last_wall_time` aynı state içinde artar. `generation_floor` opsiyoneldir, varsayılanı `None`; caller'ın verdiği dış floor'un altını reddeder fakat floor oluşturmaz veya güncellemez. Store tek başına eski ama tutarlı snapshot/backup restore'unu tespit edemez; kılavuzun restore sonrasında eski key/revoke/nonce durumunun geri gelebileceği uyarısı yerindedir.

## Güncel olmayan kılavuz ifadesi

Kılavuz §Durum ve kapsam, §Sunucudaki mevcut kapı ve ayarlar, ilk provisioning kararı ve §Açık hazırlık işleri bölümlerinde yinelenen `Content-Length` reddinin hâlâ #426 revizyonunda/beklemede olduğunu yazıyor. Görev panosunda #426 ve #429 `verified`. Güncel `do_POST()` öncesindeki `_govde_oku()` birden fazla `Content-Length` başlığını — değerleri eşit olsa bile — body okunmadan reddediyor; hata dönüşünde `do_POST()` bağlantıyı kapatıyor. `Transfer-Encoding` de reddediliyor. Dolayısıyla bu eski revizyon durumu güncellenmeli; kalan canlı hazırlık kapıları (özellikle GET gizliliği, host-side lifecycle araçları, restore/anchor ve işletim kabulü) yine açık kalır.

Kılavuzdaki `server.py` satır numaraları da kaynak evrimiyle eskimiş görünüyor. Yeniden kullanım için dosya satırlarını güncel sürümle eşleştirin veya `auth_gate_yukle()`, `do_GET()`, `do_POST()` ve `main()` gibi sembolleri esas alın. Ana davranış iddialarında içerik uyuşmazlığı saptanmadı.

## İncelenen kaynaklar

- `docs/auth-state-v2-operations.md`
- `panel/server.py`: `auth_gate_yukle()`, `_govde_oku()`, `do_GET()`, `do_POST()`, `main()`
- `panel/auth_integration_draft.py`: `AuthGate.authenticate_post()` ve `authorize_payload()`
- `panel/auth.py`: `HMACAuthenticator.verify_request()`
- `panel/auth_store_v2.py`: `AuthStateStore`, `generation_floor`, `encode_initial_state()` ve atomik snapshot yazımı
- `<YUVA_DATA_ROOT>/gorevler.json`: #426, #429, #447 durumları
