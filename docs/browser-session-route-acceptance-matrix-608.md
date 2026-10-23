# Yuva #608 — Browser session ve CSRF route kabul matrisi

**Tarih:** 2026-10-23
**Durum:** Tasarım/kabul belgesi; üretim auth ayarı ve canlı servis değiştirilmedi.

## Amaç ve kaynak davranışı

Bu belge #583'teki doğrulanmış browser session tasarımını, mevcut `panel/server.py` route tablosuna göre sınanabilir kabul koşullarına çevirir. Browser cookie'siyle sunulan tüm HTML ve snapshot yolları session kontrolünden geçmeli; cookie ile state değiştiren POST'lar ayrıca CSRF kontrolünden geçmelidir. HMAC/CLI çağrıları browser cookie'sinden ayrı bir kimlik yolu olarak kalır.

Kaynakta şu an `GET /`, `/index.html`, `/api/veri` ve `/veri` anonim yanıtlanır. POST handler'ları `YUVA_AUTH_ENABLED` kapalıyken legacy body kimlikleriyle dispatch edilir; açıkken HMAC POST gate kullanılır. Kaynakta browser session veya session-CSRF entegrasyonu yoktur. Dolayısıyla bu kabul matrisi mevcut davranışın geçtiğini iddia etmez; etkinleştirilmemiş auth veya anonim snapshot ile release kabulü **başarısızdır**. `YUVA_AUTH_ENABLED` değeri bu çalışma kapsamında okunmadı ve değiştirilmedi.

## Route envanteri ve hedef erişim politikası

| Yöntem | Canonical path | Alias / eş davranış | Hedef browser kontrolü |
|---|---|---|---|
| GET | `/` | `/index.html` | Doğrulanmış session + `browser.shell`; alias aynı scope ve login/ret davranışı |
| GET | `/api/veri` | `/veri` | Doğrulanmış session + `snapshot.read`; alias aynı scope ve aynı snapshot erişim kararı |
| POST | `/api/katil` | Yok | Session + yalnız bu route için verilmiş mutation yetkisi + CSRF |
| POST | `/api/kalp` | Yok | Session + route yetkisi + CSRF; mevcut handler'ın `503` davranışı auth kabulü sayılmaz |
| POST | `/api/ayril` | Yok | Session + route yetkisi + CSRF |
| POST | `/api/ad` | Yok | Session + route yetkisi; başka principal adına değişiklik için admin yetkisi + CSRF |
| POST | `/api/rol` | Yok | Admin yetkisi + CSRF |
| POST | `/api/sorumlu` | Yok | Admin yetkisi + CSRF |
| POST | `/api/bas-denetci` | Yok | Admin yetkisi + CSRF |
| POST | `/api/yaz` | Yok | Session + `principal_actor`/mesaj yazma yetkisi + CSRF; actor session principal'ından alınır |
| POST | `/api/ekran` | Yok | Session + route yetkisi + CSRF |
| POST | `/api/not` | Yok | Kapalı route ise session olsa da `403 route_closed`; CSRF aşılması kapalı route'u açmaz |
| POST | `/api/gorev` | Yok | Admin/görev yönetimi yetkisi + CSRF; actor doğrulanmış principal'dır |
| GET/POST | Bilinmeyen path | Yok | `404`; korumalı handler'a fallback yok |

POST listesinin kaynağı `panel/server.py:UCLAR`'dır. Mevcut HMAC gate'in route ve payload policy ayrıntısı #526'da kayıtlıdır. Browser session'a bu yetkiler otomatik verilmez; sağlayıcıda her route için açık scope/policy kaydı gerekir. Mevcut HMAC principal'ı browser session principal'ı yerine kullanılamaz.

## Her testte kaydedilecek ortak kanıt

Test, izole test servisi ve disposable veri kökü üzerinde yapılır. Her vaka için request method + ham request-target, response status/başlıkları, handler çağrısı, veri okuma/yazma etkisi ve auth/audit kaydı saklanır. Korumalı snapshot testinde `veri()` çağrısının yapılmadığı kanıtlanır; mutation testinde state hash'i veya ilgili kayıtların önce/sonra karşılaştırması kullanılır. Gerçek mesaj/ekran snapshot'ı kullanılmaz.

Hedef cookie, sunucu tarafında doğrulanabilen opaque session ID'dir; test kaydına cookie değeri veya CSRF token'ı yazılmaz. Geçerli session fixture'ı issuer, audience, instance, expiry, revoke durumu ve scope'ları kontrol edilebilir biçimde tanımlar. Testlerde Host/Origin/loopback/roster adı tek başına kimlik kabul edilmez.

## GET ve HTML kabul senaryoları

| ID | İstek ve kurulum | Beklenen sonuç | Geçiş kanıtı |
|---|---|---|---|
| G1 | Geçerli session, doğru issuer/audience/instance, `browser.shell`; `GET /` ve ayrı ayrı `GET /index.html` | Her ikisi HTML `200` | Her iki handler çağrılır; aynı shell policy loglanır; cookie `Secure`, `HttpOnly`, host-only, `Path=/` ve seçilen SameSite niteliğine sahiptir |
| G2 | G1 session'ı yok; `GET /` ve `GET /index.html` | İçerik verilmez; güvenilir broker login'e `302` yönlendirebilir veya `401/403` döner | Yanıtta panel HTML/inline hassas veri yok; login dönüş URL'si izin listesinde; HTML handler'a anonim erişim kaydı yok |
| G3 | Cookie yok/bozuk/bilinmeyen, süresi geçmiş, idle/absolute timeout olmuş veya revoke edilmiş session; her dört GET yolu | API `401`; HTML yalnız güvenilir broker login/ret; anonim fallback yok | `/api/veri` ve `/veri` için `veri()` çağrısı sıfır; API response cache'siz ve snapshot içermiyor |
| G4 | Geçerli session ancak yanlış issuer, audience, instance veya `browser.shell` scope'u yok; `GET /` ve `/index.html` | `403` veya güvenilir broker ret | HTML handler çağrısı yok; session tanı ayrıntıları response'a sızmıyor |
| G5 | Geçerli session ancak `snapshot.read` yok; `GET /api/veri` ve `/veri` | Her ikisi `403` | Her iki alias'ta `veri()` çağrısı sıfır; alias policy bypass'ı yok |
| G6 | `snapshot.read` olan geçerli session; `GET /api/veri` ve `/veri` | Her ikisi API `200`, aynı erişim kararı ve sözleşmeli snapshot | Her iki ham route audit/metric'te ayırt edilebilir; `Cache-Control: no-store`; alias canonical yolun denetimini devralmaz/atlamaz |
| G7 | Her korumalı GET için query, trailing slash, çift slash, yüzde kodlu path, encoded slash, dot-segment veya belirsiz normalize edilmiş target | `400` veya `404`; hiçbir varyant anonymous/korumasız handler'a düşmez | Auth ve dispatch aynı tek canonicalization sonucunu kullanır; reddedilen target için `veri()`/HTML handler çağrısı sıfır |
| G8 | Bilinmeyen GET | `404` | HTML veya snapshot fallback'i çağrılmaz |
| G9 | Geçerli cookie olsa da session store/provider erişilemiyor veya tutarsız | `503` veya güvenli ret; stale cache'ten cevap yok | Fail-closed; HTML/snapshot handler çağrısı ve cache-served hassas içerik yok |
| G10 | Auth/session özelliği kapalı veya session provider yapılandırılmamış; her dört GET yolu | Korumalı browser route'ları hazır olmaz; kontrollü `503`/başlangıç readiness başarısızlığı | Anonymous shell/snapshot sunulmadığı kanıtlanır. Kaynaktaki bugünkü anonim GET davranışı bu kabulü **geçmez**; canlı ayar değiştirilmez |

## Browser POST ve CSRF kabul senaryoları

Bu bölümde her test, `UCLAR` tablosundaki **11 POST path'inin her birinde** tekrarlanır: `/api/katil`, `/api/kalp`, `/api/ayril`, `/api/ad`, `/api/rol`, `/api/sorumlu`, `/api/bas-denetci`, `/api/yaz`, `/api/ekran`, `/api/not`, `/api/gorev`. Her istek JSON body biçiminde ve güvenli test verisiyle gönderilir.

| ID | İstek ve kurulum | Beklenen sonuç | Geçiş kanıtı |
|---|---|---|---|
| P1 | Her route'a cookie yok/bozuk/expired/revoked session ile POST | `401`; handler çalışmaz | State ve görev/chat/ekran dosyaları değişmez; auth hatası sonrası route yan etkisi yok |
| P2 | Her route'a geçerli session fakat route scope'u yok, yanlış audience/instance veya uygun admin yetkisi yok | `403`; handler çalışmaz | Body'deki `kimden`, `kimlik`, rol veya admin iddiası yetki kazandırmaz; state değişmez |
| P3 | Cookie geçerli, yetki yeterli; CSRF token header'ı eksik, hatalı, başka session'a ait veya tekrar kullanım politikası gereği geçersiz | `403`; handler çalışmaz | State değişmez; token URL/body/log'da taşınmaz; CSRF reddi audit edilir |
| P4 | Geçerli session + geçerli CSRF token; Origin eksik, `null`, birden fazla değerli veya beklenen scheme/host/port'tan farklı | `403`; handler çalışmaz | State değişmez; `SameSite` veya `Sec-Fetch-Site` tek başına isteği kabul ettirmez |
| P5 | Geçerli session + route scope + session'a bağlı geçerli CSRF header + tam tek same-origin Origin | Yalnız route policy'nin izin verdiği mutation çalışır | Handler principal'ı doğrulanmış session'dan alır; path'e özgü invariant ve audit sonucu kaydedilir |
| P6 | Browser cookie'si ile `POST /api/not`, session ve CSRF geçerli | Route kapalıysa `403 route_closed` | Handler/yazma yolu çalışmaz; auth/CSRF geçmek kapalı policy'yi değiştirmez |
| P7 | Browser isteğinde sahte `X-Forwarded-User`, `X-Yuva-*` veya proxy identity header'ı; geçerli session/CSRF yok | `401/403` | İstemci header'ı principal oluşturmaz; güvenilir proxy varsa dış header silinip broker tarafından yeniden yazılır |
| P8 | Auth/session özelliği kapalı veya provider/store hazır değil; her mutation path'e anonim POST | İstek reddedilir/servis readiness başarısızdır; anonim legacy handler çağrısı yok | State değişmez. Kaynaktaki bugünkü auth-off POST davranışı bu kabulü **geçmez**; production flag değiştirilmez |
| P9 | Cookie session ve geçerli CSRF olmadan HMAC imzalı CLI POST; yalnız bu route için doğru HMAC credential/scope ile | Mevcut HMAC sözleşmesi ayrıca bu actor'ı kabul ediyorsa browser CSRF şartı CLI yoluna uygulanmaz | HMAC exact method/path/body/timestamp/nonce denetimleri çalışır; browser session üretilmez. HMAC credential GET veya başka POST scope'u vermez |
| P10 | Cookie ile aynı Origin olsa da preflight `OPTIONS` veya GET üzerinden mutation denemesi | `OPTIONS` `405`; mutation GET'le gerçekleşmez | CORS başlıkları auth yerine geçmez; GET handler yan etkisizdir |

P5'te başarılı olabilecek POST route'ları ayrıca mevcut domain policy ile sınırlıdır: `/api/kalp` şu an `503` döndürür ve online durum yazmaz; `/api/not` policy kapalıdır. Bu iki route için “auth başarılı” kanıtı, domain işleminin başarılı olduğu anlamına gelmez.

## #621 geçici negatif fixture sonucu

`tests/fixtures/browser-session-csrf/route_fixture.py` yalnız test için sentetik bir loopback HTTP servisi kurar; production `panel/server.py`'yi import etmez, auth ortam değişkenlerini okumaz/değiştirmez ve gerçek session/anahtar üretmez. Her çalıştırma disposable geçici dizinde kendi ledger dosyasını oluşturur. `tests/test_browser_session_csrf_route_fixture.py` tüm dört GET alias'ını ve `UCLAR` listesindeki 11 POST path'ini ham HTTP isteğiyle sınar.

| Durum | GET `/`, `/index.html`, `/api/veri`, `/veri` | 11 POST yolu | Geçici ledger etkisi |
|---|---|---|---|
| Oturum yok | `401`, `{"ok":false,"hata":"session_required"}` | Her biri `401`, aynı JSON hata zarfı | Her POST'ta byte'lar aynı; hiçbir route handler çağrılmaz |
| Oturum var, CSRF yok | HTML/snapshot `200` | Her biri `403`, `{"ok":false,"hata":"csrf_rejected"}` | Her POST'ta byte'lar aynı; hiçbir mutation handler çağrılmaz |
| Auth kapalı | Her biri `503`, `{"ok":false,"hata":"browser_auth_unavailable"}` | Her biri `503`, aynı JSON hata zarfı | Handler çağrılmaz; tüm POST byte'ları aynı |
| Geçerli fixture oturumu + CSRF + tek same-origin | Her biri `200` | Dokuz sentetik mutation `200`; `/api/not` `403 route_closed`; `/api/kalp` `503 route_unavailable` | Yalnız dokuz izinli fixture mutation'ı her biri sabit satır ekler; iki reddedilen route'ta byte'lar aynı |

Başarılı HTML yanıt gövdesi `<html>fixture-shell</html>`, başarılı iki snapshot alias'ının gövdesi `{"ok":true,"fixture":"snapshot"}` olur. Başarılı dokuz POST'un gövdesi `{"ok":true,"route":"<request-path>","principal":"fixture-user"}`; kapalı ve kullanılamayan route gövdeleri sırasıyla `{"ok":false,"hata":"route_closed"}` ve `{"ok":false,"hata":"route_unavailable"}` olur. Test, başarılı POST'larda `Content-Length` değerinin kompakt UTF-8 JSON gövde uzunluğuna eşitliğini de doğrular.

GET reddi öncesinde HTML/snapshot handler sayaçlarının sıfır olduğu; CSRF/auth-off reddinde mutation sayaçlarının sıfır olduğu da test edilir. Geçerli fixture session'ı shell/snapshot ve tüm route scope'larını sentetik olarak taşır; bu, production provider/authorization kabulü değildir. Test edilen beklenen status/body değerleri fixture'ın kendi route gate sözleşmesidir.

**Üretim sonucu değişmedi: NO-GO.** Bu fixture, #608'de belirtilen mevcut browser session ve CSRF entegrasyonu boşluğunu kapatmaz veya gerçek panelin negatif testleri geçtiğini göstermez. Panel kaynak kodu, auth ayarı, canlı servis ve canlı ledger üzerinde değişiklik yapılmadı. Üretim kabulü için aynı senaryolar gerçek handler/session entegrasyonuna bağlanmalı; bu fixture tek başına o kanıtı sağlamaz.

## Reverse proxy ve backend bypass kabul senaryoları

| ID | İstek ve kurulum | Beklenen sonuç | Geçiş kanıtı |
|---|---|---|---|
| B1 | Browser üzerinden normal proxy adresi, session yok | Proxy/API panel içeriğini vermeden login/ret uygular | Proxy doğrulama ve backend route kontrolü aynı principal/audience politikasını izler |
| B2 | Proxy'nin arkasındaki backend IP/port/loopback/alternate bind'e doğrudan erişim | Ağ/UDS katmanında reddedilir veya backend aynı session doğrulamasını uygular | Doğrudan istek HTML/snapshot/mutation'a ulaşamaz; proxy'ye ait header taklit etmek bypass sağlamaz |
| B3 | İstemci proxy identity header'larını kendisi gönderir | Header'lar silinir; session olmadan ret | Backend logunda yalnız güvenilir proxy tarafından eklenmiş kimlik bulunabilir; dışarıdan gelen değer principal değildir |
| B4 | Proxy header'ı eksik/duplicate, backend güvenli proxy hop bilgisi yok veya proxy audience yanlış | Fail-closed `401/403/503` | Anonymous fallback ve `veri()`/mutation handler çağrısı yok |
| B5 | Proxy session doğruluyor fakat backend doğrudan erişime açık | Bypass testi başarısız; release kabulü başarısız | Backend'in yalnız proxy erişimi olduğuna dair network/UDS kuralı ve negatif bağlantı testi kaydı gerekir |

## Auth-off ve yayın kabul kararı

`YUVA_AUTH_ENABLED=0` mevcut kaynakta yalnız HMAC POST gate'ini kapatır ve legacy POST dispatch'ini bırakır; GET/HTML ise auth flag'inden bağımsız anonimdir. Bu nedenle auth-off durumu güvenli, anonim browser modu olarak kabul edilemez. Kaynakta ayrıca browser session flag'i/provider bağlantısı bulunmadığı için hedef matrisi mevcut kod tarafından karşılanmış sayılmaz.

Kabul koşulları: dört GET/HTML path'i ve alias'ları session/scope kontrolüne bağlı; 11 POST path'i cookie auth'unda CSRF + route policy uygular; HMAC istemci yolu ayrı exact-scope olarak kalır; auth kapalı/provider hatalı durumda anonim korumalı route açılmaz; backend bypass kapalı; bütün testler izole ortamda geçer. Bu koşullardan biri yoksa sonuç **NO-GO** olarak kaydedilir. Bu belge auth ayarını açma, canlı servise istek gönderme veya route kodu değiştirme yetkisi/işlemi içermez.

## Kaynaklar

- `docs/browser-session-read-scope-583.md` — session, scope, alias, CSRF ve proxy tasarımı.
- `docs/panel-api-route-scope-matrix-526.md` — mevcut GET/POST davranışı ve HMAC route policy.
- `docs/panel-anonymous-snapshot-data-minimization-574.md` — anonim snapshot'ın hassas alanları ve NO-GO gerekçesi.
- `panel/server.py` — `UCLAR`, `do_GET()`, `do_POST()`, `do_OPTIONS()`, `auth_gate_yukle()`.

Statik kaynak incelemesidir; gerçek deployment, session provider, proxy topology veya auth env'i doğrulanmadı.
