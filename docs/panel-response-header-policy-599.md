# Yuva #599 — Panel response header kapsamı ve CSP kararı

## Uygulanan ortak başlıklar

`panel/server.py:H.end_headers()` her tamamlanan HTTP header bloğuna artık tek ortak policy ekliyor:

| Başlık | Değer | Kapsam |
|---|---|---|
| `Cache-Control` | `no-store` | Başarı, uygulama hatası, OPTIONS, standart handler/protocol hatası ve erken ret yanıtları |
| `X-Content-Type-Options` | `nosniff` | Tüm tamamlanan yanıtlar |
| `Referrer-Policy` | `no-referrer` | Tüm tamamlanan yanıtlar |
| `X-Frame-Options` | `DENY` | Tüm tamamlanan yanıtlar |

Önceden `Cache-Control: no-store` yalnız `_gonder()` ve `do_OPTIONS()` içinde ekleniyordu. Bu iki özel ekleme kaldırılarak ortak policy'ye taşındı; böylece duplicate header oluşmuyor. `_gonder()` panel success/error JSON ve HTML yanıtları ile GET/POST erken dönüşlerini; `do_OPTIONS()` özel `405` yanıtını; `BaseHTTPRequestHandler.send_error()` ise bozuk request/unsupported-method gibi standart HTTP hata yanıtlarını ortak `end_headers()` yoluna verir. `end_headers()` olmadan taşıma/bağlantı hatası nedeniyle sonlanmış bir istek HTTP response üretmediğinden header beklentisi de yoktur.

## Fixture doğrulaması

Hedefli fixture komutu:

```sh
python3 -m unittest tests.test_panel_security_response_headers -v
```

**4 test geçti.** Sentetik handler doğrudan gerçek handler metotlarını çağırarak JSON success, `OPTIONS 405`, `send_error(501)` ve Host/Origin kaynak denetimindeki erken GET/POST retlerini kontrol eder. Her yanıtta dört başlığın da tekil ve beklenen değerde olduğu doğrulanır. Test gerçek soket açmaz, servis başlatmaz ve browser uyumluluğunu kanıtlamaz.

## CSP kapsamı ve inline uyumluluk kararı

Bu değişiklik `Content-Security-Policy` veya `Content-Security-Policy-Report-Only` eklemiyor. `panel/ui.html` sabit inline `<script>` ve `<style>` blokları içeriyor; JavaScript ayrıca dinamik `style=` nitelikleri üretiyor. Dar bir `script-src 'self'`/`style-src 'self'` politikası mevcut UI kodunu engeller. `unsafe-inline` eklemek CSP'nin bu katmandaki temel korumasını gevşetir; nonce yalnız `<script>/<style>` bloklarıyla sınırlıdır ve dinamik style attribute'larını çözmez.

CSP için ayrı geçiş gerekir: script/style kodunu same-origin dosyalara çıkar; inline event/style kullanımını sınıflara taşı; kalan sabit bloklar için hash veya yanıt başına nonce seç; rapor-only ile tarayıcı ihlallerini ölç; sonra enforce politikasını kademeli aç. Bu görevde CSP uygulanmaması, mevcut UI uyumluluğunu bozmayacak bilinçli sınırdır. Yeni ortak başlıklar yetkilendirme, anonim GET snapshot gizliliği veya XSS sanitizasyonu yerine geçmez.

Canlı servis, route veya CSP değiştirilmedi; yalnız ortak header ekleme noktası ve hedefli fixture değişti.
