# Yuva #686 — Browser GET/HTML session, CSRF ve erişim sınırı taslağı

**Tarih:** 2026-10-23
**Durum:** Kaynak temelli mimari taslak; auth, route, servis veya deployment değişmedi.
**Karar:** Üretim browser erişimi için **NO-GO**; mevcut davranış anonim GET'tir.

## Mevcut davranış ve tehdit

`panel/server.py::H.do_GET()` kaynak/Host kontrollerinden sonra `/api/veri` ve `/veri` için `veri()`, `/` ve `/index.html` için `sayfa()` çağırır. Bu dispatch HMAC `AuthGate`'ine girmez. `YUVA_AUTH_ENABLED=1` mevcut GET/HTML yollarına session veya GET scope eklemez. #640 gerçek `H` fixture'ında dört GET alias'ının cookie/scope yokken 200 ile callback'e ulaştığını ve adapter çağrısının olmadığını doğrulamıştır. Servisin gerçek auth/env durumu bu görevde okunmamıştır.

`Host`, `Origin`, loopback, CORS'suz `OPTIONS`, `Cache-Control: no-store`, roster adı/rolü veya body kimliği kullanıcı principal'ı değildir. Aynı loopback network namespace'teki ayrı UID süreçleri HTTP'ye erişebilir; aynı UID process'leri dosya izinleriyle ayrılmaz. `/api/veri` snapshot'ı görev, chat ve ekran içeriği taşır. #574 bu tam anonim snapshot'ı varsayılan NO-GO sayar. Erişim katmanı ile veri minimizasyonu ayrı kapılardır.

## Güvenilir kimlik hatları: browser session ve CLI HMAC

| İstemci | Principal kaynağı | Credential | Yetki | Koruma |
|---|---|---|---|---|
| Browser | Güvenilir session issuer/IdP'de doğrulanmış kullanıcı; server-side session kaydı | Opaque, rastgele session cookie; browser'a HMAC secret verilmez | Ayrı `browser.shell`, `snapshot.read` veya mutation scope'ları | TLS, Secure/HttpOnly/host-only cookie, session lifecycle ve cookie-auth mutation'ında CSRF + Origin kontrolü |
| CLI/agent HMAC | Exact method/path/body/timestamp/nonce imzasını doğrulayan HMAC principal | Yalnız CLI/broker custody'sindeki HMAC key | Explicit exact POST scope; HMAC POST yetkisi browser GET'i veya shell'i vermez | Signature, audience, nonce/replay ve payload policy; browser cookie/CSRF identity değildir |

Bu iki identity space otomatik olarak birbirine çevrilmez. Browser cookie'den CLI principal çıkarılmaz; HMAC `principal_id`, `/api/veri` browser session'ı değildir. Body'deki `kimlik`, `kimden`, rol, `X-Forwarded-User` veya `X-Yuva-*` header'ı yetki seçemez. Bir kullanıcı iki yolu da kullanacaksa issuer/principal eşlemesi ve denetim kaydı ayrı bir kararla kurulmalıdır.

## Route ve asset politikası

| Yöntem/yol | Hedef politika | Başarısızlık ve alias kuralı |
|---|---|---|
| `GET /`, `GET /index.html` | Doğrulanmış browser session + `browser.shell` | Session yoksa shell içeriği yok; güvenilir issuer login/ret yönlendirebilir. İki yol aynı policy'de. |
| `GET /api/veri`, `GET /veri` | Aynı session issuer + `snapshot.read`; authorization snapshot okunmadan önce | Her ikisi aynı read scope ve no-store kararını uygular. Yetkisiz istek için `veri()` çağrısı sıfır olmalı. |
| Statik asset (gelecekte `/static/...`) | Public yalnız versioned, kullanıcı/veri/session içermeyen immutable asset için; diğer durumda `browser.shell` session'ına bağla | Path traversal, alias veya proxy filesystem fallback yok. Personalized HTML/JSON `no-store`; public statik asset explicit allowlist ve bağımsız cache policy ister. |
| Bilinmeyen GET ve var olmayan asset | 404 | Shell, snapshot veya public directory fallback yok. |
| Tüm state-changing POST | Browser session + route-specific permission + CSRF; CLI HMAC ayrı policy lane | Cookie auth varsa CSRF zorunlu; closed route session ile de açılamaz. |

Snapshot API'nin compatibility alias'ı `/veri`, canonical `/api/veri` ile aynı authorization fonksiyonuna ve handler'a bağlanır. Path kararında ham request-target tek defa canonicalize edilir. Belirsiz query, trailing slash, çift slash, encoded slash/dot-segment veya duplicate path varyantı reddedilir; auth bir normalize edilmiş yola, dispatch başka yola bakamaz.

## Session ve CSRF tasarım sınırı

1. TLS sonlandıran güvenilir issuer login'i doğrular ve server-side store'a opaque session kaydı yazar. Kayıt principal, issuer/audience, instance, expiry/idle timeout, revoke durumu ve açık scopes ile bağlıdır. Cookie principal/scope taşıyan imzalı client state'i olarak kabul edilmez.
2. Cookie TLS üzerinde `Secure`, `HttpOnly`, host-only, `Path=/`, uygun `SameSite` ve sınırlı ömürle verilir. Girişte session ID rotate edilir; logout/issuer revoke server-side invalidation yapar. Session store/proxy/clock hatasında korumalı route fail-closed olur.
3. Her dört GET'te session doğrulaması ve exact route scope, `sayfa()` veya `veri()` çağrısından önce yapılır. API `401/403`/güvenli `503` dönebilir; hassas cache fallback'i veya anonim boş/tam snapshot dönüşü yoktur. HTML login yönlendirmesi yalnız allowlist dönüş URL'si olan güvenilir issuer tarafından yapılır.
4. GET yan etkisizdir. Cookie ile state değiştiren POST için session'a bağlı synchronizer CSRF token'ı özel request header'ında ve tek Origin kontrolü gerekir. Eksik, `null`, duplicate veya cross-origin Origin reddedilir. `SameSite`/Fetch Metadata ek savunmadır; tek başına CSRF kabulü değildir. CLI HMAC çağrısı cookie taşımadığı için bu browser CSRF mekanizmasına bağlanmaz.
5. `Cache-Control: no-store` yetkisiz yanıt ve personalized shell/snapshot'larda korunur; cache hit auth kontrolünü atlayamaz. CSP ve diğer security headers ayrıca kabul edilir, session yetkisi yerine geçmez.

## Reverse proxy ve doğrudan backend bypass

Önerilen browser akışı: Browser → TLS/session issuer/proxy → dar kapsamlı panel backend. Proxy dışarıdan gelen tüm identity başlıklarını siler; yalnız doğruladığı session bağını backend'e aktarır. Backend proxy-origin/audience/credential'ını doğrular ve proxy dışı caller'ı reddeder.

En güçlü backend sınırı private UDS veya yalnız proxy servis UID'sinin eriştiği private listener'dır. Backend loopback TCP'de kalacaksa loopback tek başına yeterli değildir: aynı host/namespace'teki süreçler portu çağırabilir. Ağ firewall/namespace ve backend-level authenticated proxy assertion birlikte kabul edilmelidir. `X-Forwarded-User` gibi client-controlled header'ı kabul etmek güven sınırını bozar. Host/network ayarı bu görev kapsamında okunmamış veya değiştirilmemiştir.

Proxy yoksa panel'in kendi server-side browser session doğrulaması gerekir; reverse proxy varlığı varsayılamaz. Hangi bileşenin session authority olduğuna dair tekil ve dokümante edilmiş owner olmalıdır. Hem proxy hem panel doğrulaması yapılıyorsa issuer/audience/route scopes aynı olmalı ve bir katman diğeri atlandığında anonim backend erişimi oluşmamalıdır.

## Fail-closed kabul ölçütleri

Kabul yalnız disposable test release ve sentetik data root'ta, gerçek handler/session adapter'ına bağlanmış negatif/pozitif fixture ile gösterilmelidir. Her istek için ham route, status, body/cache header, handler read/dispatch sayısı ve state hash farkı kaydedilir; cookie/CSRF secret'ları rapora yazılmaz.

| Negatif/pozitif vaka | Beklenen sonuç |
|---|---|
| Cookie yok, bozuk, expired, revoked veya session store unavailable; dört GET alias | 401/403/503/issuer ret; shell/snapshot callback hiç çağrılmaz; auth-off fallback yok |
| Session var ama issuer/audience/instance yanlış ya da `browser.shell`/`snapshot.read` scope'u eksik | 403; korunan handler çağrısı yok |
| `/api/veri` veya `/veri` alias'ı session kontrolünden kaçırılmaya çalışılır | Aynı read policy; handler çağrısı sıfır |
| Query/trailing slash/encoded/double slash path normalization varyantları | 400/404; anonim/başka handler'a dispatch yok |
| Cross-origin veya cookie'siz HTML→snapshot fetch | Snapshot 401/403; HTML public bırakılmadığı sürece login shell'i anonymous data yüklemez |
| Doğrudan backend IP/loopback/port erişimi, proxy header spoof veya proxy down | Network/UDS ret veya backend auth ret; veri handler'ına erişim yok |
| Cookie-auth POST'ta CSRF eksik/yanlış/başka session'a ait; Origin absent/null/duplicate/cross-origin | 403; bütün mutation callback'lerinde sıfır çağrı, state byte'ları aynı |
| Geçerli browser session+CSRF+route permission | Yalnız allowlisted route çalışır, principal session'dan gelir; body actor claim'i göz ardı edilir |
| CLI HMAC exact POST scope ile GET dener | GET reddedilir; HMAC POST policy session/shell/snapshot scope'a genişlemez |
| Bilinmeyen GET/static path | 404; dosya sistemi veya shell fallback yok |

GO için bunlara ek olarak canlıya özgü bind/proxy/backend ownership, TLS cookie özellikleri, GET data-owner kararı, session revoke/logout ve access logging/retention kabulü gerekir. Tek fixture'ın geçmesi host/network/firewall güveni kanıtlamaz.

## Uygulama ve rollback sırası

1. **Yetki sahibini seç:** Session issuer, browser user principal, snapshot okuyucu kitlesi, route scopes ve backend erişim yolunu ürün/güvenlik sahipleri imzalar. #574 anonime tam snapshot NO-GO kararı çözülmeden public full snapshot'a devam edilmez.
2. **Server-side gate tasarla/uygula:** Ham route/canonical path, session lookup, audience/instance, scope ve policy kararını her dört route'a tek fonksiyonda uygula; GET data/shell handler'ı ancak authorization sonrası çağrılır. Auth provider yoksa deployment readiness başarısız veya protected routes kapalıdır; legacy anonymous fallback yok.
3. **Proxy/CSRF ve static asset policy:** Backend bypass kapatılır; public statik dosya allowlist'i veri taşıyan route'lardan ayrılır. Cookie POST route'larında token+Origin zorunlu; HMAC lane açıkça ayrı kalır.
4. **Canary kabulü:** Test release'te tam negatif/pozitif matris, session revoke/restart/provider failure, alias/canonicalization ve backend bypass sınanır. Production auth flag'i veya servis bu taslak kapsamında açılmaz.
5. **Release geçişi:** Yeni server ve UI/asset sürümü birlikte dağıtılır; eski client veya paralel backend/sessionless release devrede kalırsa rollback kapısı açık tutulur.
6. **Rollback:** Önce yeni session admission/route erişimi kapatılır. Geri dönülecek release anonymous GET/HTML sunuyorsa onu açmak rollback sayılmaz; korunan route'ları 503/kapalı tut, servisi güvenli biçimde durdur veya yalnız aynı access boundary'yi sağlayan önceki release'e dön. Cookie/session key/state migration ayrı recovery planına tabidir; eski session'ları doğrulamadan yeniden etkinleştirme. HMAC CLI kapsamını browser scope'u yapmak fallback değildir.

## Mevcut karar ve sınırlar

Kaynak, dört GET route'unun anonim olduğunu ve HMAC POST gate dışında kaldığını gösterir; #640 gerçek Handler fixture'ı da gate çağrısının olmadığını doğrular. #608/#583 hedef session ve CSRF kabul matrisidir, uygulama değildir. Bu taslakta auth/session flag'i açılmadı, route/servis/proxy değiştirilmedi, host veya browser testi çalıştırılmadı. Production browser access için sonuç **NO-GO** kalır.

## Kaynaklar

- `panel/server.py`: `H.do_GET()`, `_kaynak_denetimi()`, `H.do_POST()`, `auth_gate_yukle()`.
- `panel/auth_integration_draft.py`: HMAC POST policy; browser session değildir.
- `docs/browser-session-route-acceptance-matrix-608.md` — route ve CSRF kabul vakaları.
- `docs/browser-session-read-scope-583.md` — browser session ve read scope hedefi.
- `docs/panel-origin-csrf-538.md` — Host/Origin/Content-Type kaynak filtresinin kimlik sınırı.
- `docs/panel-browser-session-handler-fixture-640.md` — gerçek H fixture gözlemi ve production session sınırı.
- `docs/panel-anonymous-snapshot-data-minimization-574.md` — snapshot hassasiyeti ve anonim GET NO-GO.
