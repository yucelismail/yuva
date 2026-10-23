# #538 — Local MVP browser Origin/CSRF sınırı

Durum: Kaynak düzeltmesi ve fixture regresyonları tamamlandı. Canlı HTTP,
servis/runtime veya deployment incelemesi yapılmadı; `YUVA_AUTH_ENABLED` değeri
okunmadı ya da değiştirilmedi.

## Uygulanan kaynak politikası

- `Host` tam olarak bir kez bulunmalı, loopback allowlist'inde olmalı ve
  yapılandırılmış gerçek panel portunu taşımalı. Böylece DNS-rebinding alan adı
  Host olarak kullanılamaz.
- `Origin` varsa tam olarak bir kez bulunmalı ve geçerli bir HTTP origin'i
  olmalı. Yalnız loopback allowlist'indeki host ve aynı port kabul edilir;
  userinfo, path, query, fragment, bozuk port, `null`, HTTPS ve farklı origin
  reddedilir.
- `POST` için tek `Content-Type` başlığı ve `application/json` gerekir.
  HTML form türleri (`application/x-www-form-urlencoded`, `multipart/form-data`,
  `text/plain`) reddedilir. `OPTIONS` preflight `405` döndürür ve CORS izin
  başlığı üretmez.
- Bu kontroller kaynak/CSRF filtresidir; istemci veya aynı makinedeki yerel
  süreç kimliğini doğrulamaz. `Origin` başlığının bulunmaması CLI istemcileri
  için kabul edilmeye devam eder.

## GET gizliliği ve auth sınırı

`GET /api/veri` ve `/veri`, kullanıcı profili, görevler, mesajlar ve ekran
satırlarını içeren birleşik snapshot'ı döndürür. `_gonder()` `Cache-Control:
no-store` kullanır, ancak snapshot anonimliğe açıktır; Host/Origin, CORS veya
no-store kimlik doğrulaması ve yerel UID izolasyonu sağlamaz. Kaynakta HMAC
kapısı yalnız `YUVA_AUTH_ENABLED=1` açıkça yapılandırılırsa yüklenir ve mevcut
GET route'u bu POST kapısına girmez. Bu görev auth bayrağını açmadı; gerçek
deployment değeri hakkında çıkarım yapılmadı.

## Fixture doğrulaması

`tests/test_panel_source_policy.py`, handler kontrollerini soket açmadan sınar:
aynı-origin JSON POST; çapraz-origin fetch; DNS-rebinding hostname; basit form
Content-Type'ları; hatalı/ayrıcalıklı Origin biçimleri; yinelenen güvenlik
başlıkları ve CORS'suz `OPTIONS 405`.
