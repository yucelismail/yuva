# #534 — Panel HTTP güvenlik başlıkları ve cache politikası

Tarih: 2026-10-23
Durum: Salt-okunur kaynak incelemesi ve politika önerisi. HTTP isteği veya
runtime yapılmadı; kod, auth ayarı, credential ya da servis değiştirilmedi.

## Karar özeti

Panelin `_gonder()` yolu API ve HTML cevaplarında açık `Content-Type` ile
`Cache-Control: no-store` üretiyor. `OPTIONS` ön-uçuşu `405` ile reddediliyor
ve `Access-Control-Allow-*` başlığı üretilmiyor. Bunlar doğru başlangıç
varsayımlarıdır. Ancak `X-Content-Type-Options`, CSP ve `Referrer-Policy`
başlıkları kaynakta görünmüyor. Ayrıca `BaseHTTPRequestHandler` üzerinden
`_gonder()` dışı üretilen varsayılan method/protocol hata cevapları ortak
başlık yordamından geçmiyor.

Öneri: kişisel snapshot içeren tüm API ve HTML cevaplarında `no-store`'u
koru; JSON/HTML MIME türlerini açıkça sabitle; tüm cevaplara `nosniff` ve
`no-referrer` ekle; CORS'u kapalı tut; CSP'yi inline JS/CSS yapısıyla uyumlu,
nonce/hash temelli şekilde HTML'de uygula. Hata yanıtlarını da aynı başlık
politikasına bağla. Bu başlıklar GET erişimini yetkilendirmez: `/api/veri` ve
HTML kaynakta anonymous GET'tir ve loopback/Host/Origin kontrolleri UID kimliği
kanıtı değildir.

## Statik kaynak bulguları

| Yanıt/kontrol | Kaynaktaki davranış | Değerlendirme |
|---|---|---|
| `GET /api/veri`, `GET /veri` | `do_GET()` aynı `veri()` snapshot'ını `_gonder()` ile JSON döndürür. | Birleşik snapshot görev, sohbet ve ekran verisi içerir; bu yüzden `no-store` uygun. `GET` HMAC/AuthGate kapsamına alınmamıştır. |
| `GET /`, `GET /index.html` | `sayfa()` veya fallback HTML, `_gonder(..., "text/html; charset=utf-8")` yolundan döner. | `no-store` HTML için de uygun; tarayıcı sonraki `/api/veri` isteğini ayrıca yapar. |
| API/uygulama hataları | Kaynak denetimi, JSON/gövde, auth ve route hataları çoğunlukla `_gonder()` üzerinden açık JSON MIME türü ve `no-store` ile döner. | Özel hata cevaplarının MIME/cache türü tutarlıdır. Handler dışı exception/protocol error yolları ayrıca ortaklaştırılmalı. |
| `OPTIONS` | `405`, `Allow: GET, POST`, `Cache-Control: no-store`, boş gövde ve `Connection: close`; `Access-Control-Allow-*` yok. | Preflight'a izin verilmediği kaynakta açık. Bu, diğer GET/POST'ların kimlik doğrulandığı anlamına gelmez. |
| CORS | Kaynakta hiçbir `Access-Control-Allow-Origin` veya credentials allow başlığı görünmüyor. `Origin` varsa Host authority ile eşleşmesi denetleniyor. | Tarayıcı çapraz-origin okumasına izin veren CORS opt-in'i yok. Origin kontrolü CSRF/rebinding savunmasıdır; principal/auth değildir. |
| `Content-Type` | `_gonder()` varsayılan JSON UTF-8; UI için açık `text/html; charset=utf-8`. `do_POST()` JSON medya türünü talep eder. | Beklenen cevap türleri doğru seçilmiş. `nosniff` yok; `send_error` ve benzeri `_gonder()` dışı cevaplarda tür/header davranışı ayrıca değişebilir. |
| CSP | `panel/ui.html` tek HTML içinde inline `<style>` ve inline `<script>` taşır; render sırasında inline `style=` nitelikleri de üretir. Header yok. | Varsayılan `script-src 'self'` tek başına mevcut UI'yi bozabilir. CSP önce nonce/hash veya asset ayrımıyla tasarlanmalı; `unsafe-eval` gereksinimi kaynakta görünmüyor. |
| Referrer | `Referrer-Policy` yok. UI'de harici fetch kaynağı görünmüyor; API istekleri same-origin relative URL kullanıyor. | `no-referrer` eklemek referrer bilgisinin başka hedeflere taşınmasını önleyen dar bir varsayılandır. |
| Diğer hata başlıkları | `H` sınıfında `send_error()` override'ı görünmüyor; `do_GET`, `do_POST`, `do_OPTIONS` dışında method handler'ı da görünmüyor. | Desteklenmeyen method ve bazı parser/protocol hataları ortak `_gonder()` header set'ini atlayabilir. `Server` kimliği de `server_version = "yuva/2.0"` olarak tanımlı. |

`panel/ui.html:536` fetch'i `cache: "no-store"` kullanıyor. Bu istemci tercihi,
HTTP response'un `Cache-Control` başlığının yerine geçmez; mevcut `_gonder()`
başlığı doğru biçimde server tarafında da uygulanmıştır.

## Önerilen başlık matrisi

| Başlık | JSON API ve API hataları | HTML ve HTML hataları | Politika |
|---|---|---|---|
| `Cache-Control` | `no-store` | `no-store` | `/api/veri` hassas/birleşik snapshot'tır. Hata cevapları ve `404` da dahil ortak uygula. |
| `Content-Type` | `application/json; charset=utf-8` | `text/html; charset=utf-8` | Her gövde için sabit tür. Başlıksız veya gövde türüyle çelişen hata cevabı bırakma. |
| `X-Content-Type-Options` | `nosniff` | `nosniff` | MIME türü tahminini kapat; içerik türü zaten açıkça seçiliyor. |
| `Referrer-Policy` | `no-referrer` | `no-referrer` | Panelin same-origin akışı için referrer gerekmiyor; URL/query bilgisini taşımayı azaltır. |
| `Content-Security-Policy` | JSON gövdesinde gerekli değil; istenirse ortak güvenli set kullanılabilir | Aşağıdaki inline içerik koşullarıyla enforce et | En az `default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; connect-src 'self'`. Script/style kaynaklarını ayrıca tanımla. |
| CORS `Access-Control-Allow-*` | Üretme | Üretme | Mevcut same-origin kullanım ve `OPTIONS 405` ile uyumlu. Wildcard veya istek Origin'ini yansıtma yok. |

CSP için script izin listesi `unsafe-inline` veya `unsafe-eval` ile açılmamalı.
Mevcut tek parça `<script>` ve `<style>` ya response başlığıyla uyumlu taze
nonce almalı ya da sabit içerik için build/release sırasında üretilmiş exact
hash'lerle allowlist'e bağlanmalıdır. Fallback HTML'nin inline `style=`
niteliği ve ana UI'deki dinamik inline stil nitelikleri ayrıca ele alınmalı;
tercihen sınıf tabanlı CSS'e taşınmalı veya dar `style-src-attr` istisnası
bilinçli olarak belgelenmelidir. CSP yalnız HTML'e uygulanan bir tarayıcı
kontrolüdür; API snapshot erişim kontrolü veya veri redaksiyonu değildir.

Uygulama yapılacaksa başlık üretimi tek bir cevap yordamından geçmelidir:
normal başarı, `_gonder()` hataları, `OPTIONS`, unsupported method ve
`send_error`/parser hataları. JSON API için CSP'den ziyade doğru MIME,
`nosniff`, no-store ve erişim kararı önemlidir. HSTS mevcut HTTP/loopback
sunucusuna eklenmemeli; ancak doğrulanmış TLS termination ve HTTPS origin
kararı verilirse ayrıca değerlendirilmelidir.

## Auth ve privacy kararlarıyla ilişki

- #451 tek güvenilen Unix UID altında loopback kullanımını varsayılan olarak
  kabul eder. Loopback uzak ağ yüzeyini daraltır; farklı UID'leri ayırmaz.
  Host/Origin kontrolleri de kimlik doğrulaması değildir.
- #455, `/api/veri`, alias'ları ve HTML'nin anonymous GET olduğunu; snapshot'ın
  görev, sohbet ve ekran içeriği taşıdığını kaydeder. Farklı UID'den gizlilik
  hedefleniyorsa ayrı servis UID/UDS veya browser bridge/session gibi erişim
  sınırı gerekir.
- #454 ve #526'ya göre auth integration taslağı default-off ve yalnız POST
  mutation route'larına bağlıdır. HMAC açık olsa dahi `GET /api/veri` ve HTML
  auth kapısından geçmez. Header eklemek anonymous GET kararını değiştirmez.
- #453'e göre sohbet/ekran içeriği yazma öncesi redakte edilmiyor; UI'da
  gizlemek veya API yanıtını sınırlamak diskteki ham kaydı ya da aynı UID
  erişimini korumaz. `no-store` tarayıcı/cache ömrünü sınırlar, içerik
  sınıflandırması değildir.

Bu nedenle önerilen header set'i browser cache ve içerik yorumlama savunmasıdır;
kimlik doğrulama, authorization, yerel UID izolasyonu, redaction veya JSONL
retention iddiası kurmaz.

## Kaynaklar ve sınırlar

- `panel/server.py`: `H.server_version`, `_kaynak_denetimi()`, `_gonder()`,
  `do_GET()`, `do_OPTIONS()`, `do_POST()`, `sayfa()` ve `HTML_YEDEK`.
- `panel/ui.html`: inline `<style>`/`<script>`, dynamic `style=` kullanımı ve
  `fetch("/api/veri", {cache:"no-store"})`.
- `docs/local-api-access-decision-451.md` ve
  `docs/local-api-access-boundary.md` — loopback/UID ve Host/Origin sınırı.
- `docs/local-api-get-snapshot-decision-455.md` — anonymous GET ve birleşik
  snapshot erişim kararı.
- `docs/auth-integration-static-checklist-454.md` ve
  `docs/panel-api-route-scope-matrix-526.md` — POST-only/default-off auth ve
  GET/HTML route kapsamı.
- `docs/panel-privacy-redaction-inventory-453.md` — snapshot, redaction ve
  retention sınırları.

Bu rapor yalnız mevcut kaynakları karşılaştırır. Canlı header'lar, proxy/TLS,
browser cache davranışı, `YUVA_AUTH_ENABLED` değeri, servis environment'ı veya
gerçek network erişimi incelenmedi; kaynak durumu deployment kanıtı değildir.
