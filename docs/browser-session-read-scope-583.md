# Yuva #583 — Browser oturumu ve GET read-scope tasarımı

## Karar özeti

Tarayıcı için önerilen model, HMAC API anahtarını tarayıcıya vermeyen ve principal'ı güvenilir bir oturum sağlayıcısından alan HTTP oturum broker'ı/ters vekilidir. Broker doğrulanmış kimlik için sunucu tarafında oturum tutar; panel backend'ine yalnız broker ulaşır. Backend'in doğrudan erişimi de aynı oturum/yetki kararına tabi olmalı veya ağ/UDS sınırıyla broker dışındaki istemcilere kapatılmalıdır. `Host`, `Origin`, loopback adresi, Yuva roster kaydı, ekrandaki rol, `kimden` ve `--from` doğrulanmış browser principal değildir.

Tüm mevcut read path'leri korumaya alınır: `GET /` ve `GET /index.html` `browser.shell`; `GET /api/veri` ve `GET /veri` `snapshot.read` ister. İki snapshot yolu aynı mantıksal veriyi verdiği için aynı kapsamı kullanır; alias'ı atlamak koruma atlaması olur. `/` ile `/index.html` de aynı shell kapsamına bağlanır. HTML'in public bırakılması ayrı ürün kararıdır; bu tasarımda tüm dört yol için oturum zorunludur.

Bu yalnız tasarımdır. Kaynakta bugün bu dört yol anonimdir; bu belge davranışı değiştirmez, oturum sağlayıcısı veya TLS/proxy varlığını doğrulamaz.

## Bugünkü kaynak davranışı

`panel/server.py:do_GET()` query bölümünü kesip sondaki slash'ları normalize eder, sonra `_kaynak_denetimi()` uygular. `/api/veri` ve `/veri` snapshot, `/` ve `/index.html` HTML döndürür. Bu dispatch'te HMAC `AuthGate` çağrısı yoktur. `panel/auth_integration_draft.py` içindeki GET HMAC metotları ve `GET_ROUTE_POLICY` prototipidir; server'a bağlanmış browser session değildir. `ui.html` doğrudan `/api/veri` çağırır.

`_kaynak_denetimi()` Host/Origin biçimini ve loopback kaynağını kısıtlar. Bunlar DNS-rebinding/CSRF savunma sinyalleridir, kimlik kanıtı değildir: yerel süreçler aynı loopback'e erişebilir; istemci başlıkları uygulama principal'ı taşımaz. Origin'in bulunmaması mevcut CLI uyumluluğu için kabul edilir, bu yüzden yokluğu browser oturumunu doğrulayamaz. `Cache-Control: no-store` cache riskini azaltır, erişim denetimi yapmaz. HMAC POST gate yalnız POST handler'larını korur; GET/HTML kapsamı değildir. HMAC sırrı web bundle'ına ya da browser storage'a konamaz.

Mevcut route normalizasyonu `?x=...` query bölümünü düşürür, trailing slash'ı kabul edilen yola indirger. Oturum entegrasyonu bu davranışı sessizce auth kararından ayırmamalı: önerilen policy ham request-target'ı doğrulasın, belirsiz/alternatif biçimleri reddetsin ve auth ile dispatch'in aynı canonical route'u kullandığını garanti etsin.

## Principal ve oturum sözleşmesi

1. **Kimlik kaynağı:** Principal, broker'ın doğruladığı OS/kurumsal kimlik sağlayıcısı veya açıkça seçilmiş güvenilir IdP'den gelir. Yuva içindeki görünen rol/roster yalnız uygulama verisidir; kimlik sağlayıcısı değildir. Ortak OS UID altında çalışan yerel model/agent süreçlerini birbirinden ayırdığı iddia edilmez.
2. **Cookie:** Browser'a yalnız kriptografik olarak rastgele, anlamsız oturum tanıtıcısı verilir. Sunucuda bu tanıtıcı; principal, doğrulama zamanı, issuer/audience/instance, oluşturulma ve son etkinlik zamanı, mutlak/boşta son kullanma, iptal durumu ve atanmış scope'lara bağlanır. Cookie içine principal veya yetki yazıp istemciden güvenilmez biçimde geri alınmaz.
3. **Cookie koruması:** Üretim tarayıcı oturumu TLS üzerinden taşınır; `Secure`, `HttpOnly`, uygun `SameSite=Strict` (ürün akışı gerektiriyorsa Lax gerekçeli), `Path=/`, kısıtlı host-only cookie ve makul `Max-Age` kullanılır. Plain HTTP loopback üzerinde `Secure` niteliği taşınamaması nedeniyle bu profilin güvenlik garantileri sağlanmış sayılmaz; plaintext için “doğrulanmış ve korumalı browser session” iddiası yapılmaz. HMAC, TLS yerine geçmez.
4. **Yaşam döngüsü:** Başarılı girişte yeni session ID üretimi ve eski ID'nin iptali (session fixation önlemi), kısa boşta süre + mutlak süre, logout'ta server tarafı iptal, operatör/IdP iptalinin yansıtılması, broker restart/store hatasında fail-closed davranış gerekir. Yetki değişikliği session scope'larını yenilemeli veya oturumu iptal etmelidir. Session URL, query, browser localStorage veya loglara yazılmaz.
5. **Yetki:** Oturum geçerli olsa bile route scope'u açıkça doğrulanır. `browser.shell` HTML'i, `snapshot.read` birleşik kullanıcı/görev/mesaj/ekran snapshot'ını yetkilendirir. Admin rolü sırf okuma için varsayılmaz. Snapshot alanlarının hangi kullanıcıya görünmesi gerektiği ayrıca alan düzeyi politikadır; bu tasarım bütün snapshot'ı tek read scope olarak ele alır ve alan düzeyi gizlilik garantisi vermez.
6. **Hata davranışı:** Eksik/bozuk/sona ermiş/iptal edilmiş cookie, yanlış issuer/audience/instance, session store/provider arızası veya bilinmeyen scope hiçbir anonim moda düşmez. API 401/403 veya altyapı belirsizliğinde 503 döner; HTML için oturum açma yönlendirmesi ancak güvenilir broker tarafından yapılır ve login dönüş URL'si izin listesiyle sınırlandırılır. Uygulama verisi hatalı auth'tan önce okunmaz/serialize edilmez.

## Route, alias ve CSRF politikası

| İstek | Canonical erişim kararı | Kapsam ve davranış |
|---|---|---|
| `GET /` | Ham target tam `/` ise | Geçerli session + `browser.shell`; aksi durumda broker login akışı veya ret. |
| `GET /index.html` | Ham target tam `/index.html` ise | `GET /` ile aynı `browser.shell`; alias yolu açıkça gate'li. |
| `GET /api/veri` | Ham target tam `/api/veri` ise | Geçerli session + `snapshot.read`; `no-store`; sadece yetkili olduktan sonra `veri()` çağrılır. |
| `GET /veri` | Ham target tam `/veri` ise | Compatibility alias, aynı `snapshot.read`; ayrı route kontrolü ve log/metric'te alias görünürlüğü. |
| GET varyantları | Query, fragment, trailing slash, çift slash, yüzde kodlu/alternatif path veya belirsiz normalization | Korunan route'a normalize edip yetkiyi korumak kanıtlanmamışsa reddet; farklı handler'a/anonim yola düşürme. Snapshot query parametresi desteklenmediğinden query reddi önerilir. |
| Diğer GET | Bilinmeyen route | 404; shell/snapshot handler'ına fallback yok. |

Browser cookie'si otomatik gönderildiği için state değiştiren her cookie-auth isteği CSRF koruması ister: session'a bağlı synchronizer token (veya eşdeğer güvenli double-submit), token'ın özel header'da taşınması, tek ve tam Origin'in beklenen scheme+host+port ile eşleşmesi ve `Sec-Fetch-Site` gibi Fetch Metadata'nın savunma katmanı olarak değerlendirilmesi. `SameSite` tek savunma değildir. Eksik Origin, `null`, birden fazla veya farklı Origin browser mutation'ında reddedilir; CLI'nin Origin'siz HMAC akışı ayrı kimlik/yetki mekanizması olarak kalır. CORS kapalı kalır; OPTIONS izni auth yerine geçmez. GET'ler yan etkisiz olmalı; logout/işlem gibi mutation GET ile yapılmamalıdır.

HMAC POST ile session POST aynı principal türü sayılmaz. Mevcut agent/CLI HMAC yolu korunacaksa route başına hangi credential'ın kabul edildiği açık olmalı; cookie'li browser mutation'ı CSRF ile korunmalı, HMAC imzalı API çağrısı exact POST scope ve nonce doğrulamasını sürdürmelidir. Body'deki kimlik/rol iddiası hiçbirinde doğrulanmış principal'ı seçemez.

## Seçeneklerin karşılaştırması

| Seçenek | Browser için uygunluk | Güven sınırı ve açık karar |
|---|---|---|
| Mevcut loopback + anonymous GET | Yalnız bütün aynı namespace/UID erişimini güvenilir sayan tek kullanıcılı yerel MVP | Kimlik doğrulama değildir; farklı UID süreçleri loopback'e erişebilir, aynı UID süreçleri dosya izinleriyle ayrılamaz. Hassas snapshot'ı izole etmez. |
| HMAC GET read-scope | Browser doğrudan kullanımı için uygun değil; secret kullanıcıya gösterilir | CLI/broker anahtar tutabiliyorsa exact method/path/audience/scope ve replay korumasıyla kullanılabilir. `/api/veri` ve `/veri` izinlerinin kapsamı açık olmalı. HMAC POST scope GET'e geçmez; TLS/response gizliliği sağlamaz. |
| Doğrulanmış session cookie + broker/ters vekil | Önerilen browser modeli | Broker kimliği doğrular, server-side session ve route scope uygular; TLS, CSRF, logout/revoke, session store ve doğrudan backend erişimini kapatma gerekir. Proxy kimlik başlıkları istemciden silinip yalnız güvenilir proxy tarafından eklenmelidir. |
| Ayrı servis UID + UDS `SO_PEERCRED` | Yerel servis/agent izolasyonunda yararlı; browser tek başına kullanamaz | UDS peer UID doğrular, browser socket'e bağlanamaz. Farklı UID'ler ve servis sahipliği gerçekten ayrılmalı; browser için HTTP session broker gerekir. Aynı UID altında süreçleri ayırmaz. |
| Birleşik broker + ayrı servis UID/UDS | En güçlü yerel ayrım gerektiğinde önerilen hedef | Browser TLS/session katmanından geçer; broker backend'e izinli UDS üzerinden bağlanır. Backend'in loopback HTTP'si kapatılır veya yalnız broker'a sınırlandırılır. Ürün/operasyon karmaşıklığı ve credential custody kararı gerekir. |

Öneri: browser için TLS'li broker session'ı; gerçekten farklı OS principal'ları ayırma ihtiyacı varsa backend'i özel servis UID'si/UDS arkasına al. Aynı UID içindeki süreçleri ayırma gerekmiyorsa bunu açık risk kabulü olarak kaydet. Salt HMAC GET, tarayıcı oturumunun yerine konmamalı.

## Fail-closed kabul matrisi

| Senaryo | Beklenen sonuç | Kabul kanıtı |
|---|---|---|
| Her dört route'a geçerli, doğru instance/audience ve gerekli scope'lu session | İlgili shell/snapshot yanıtı | Route tablosu her alias'ı kapsar; handler yalnız auth + authorize sonrası çağrılır. |
| Cookie yok, bozuk, imza/lookup geçersiz, süresi dolmuş veya iptal edilmiş | API 401; HTML broker login/ret; snapshot yok | Yanıt gövdesi/veri okuma çağrısı ve cache'den veri sızıntısı yok. |
| Geçerli session, yanlış issuer/audience/instance veya istenen scope yok | 403 (session doğrulama ayrıntılarını açığa çıkarmadan); snapshot yok | Bir instance/session başka instance'a taşınamaz; `browser.shell` `snapshot.read` vermez, tersi de vermez. |
| `/api/veri` yetkisi var, `/veri` alias deneniyor (ve tersi) | Tasarımdaki ortak `snapshot.read` nedeniyle ikisi de aynı yetkiyi ister; policy ikisine de bağlı | Alias unutulması veya farklı handler fallback'i yok; ayrı HMAC istemcisi kullanılırsa #471'in ayrı exact scope kuralı korunur. |
| Query, fragment, trailing slash, çift slash veya encoded alternatifle protected path'e erişim | 400/404; normalizasyonla auth bypass yok | Ham target kararıyla dispatch route'u aynıdır; query sessizce atılmaz. |
| Shell session'ı yokken snapshot isteği veya public shell'den snapshot'a erişim | Snapshot 401/403; HTML içinden anonim fallback yok | UI hatalı auth'ta boş/anonim veriye geçmez; API `veri()` çalışmaz. |
| Cookie-auth mutation: CSRF token yok/yanlış; Origin yok, `null`, duplicate veya çapraz origin | 403; state değişmez | Mutation handler çağrılmaz. `SameSite` tek başına kabul kriteri değildir. |
| Geçerli CSRF, tam same-origin, geçerli session ve route scope | Yalnız izinli mutation (varsa) | Session principal body `kimden`/`kimlik` iddiasından bağımsızdır. |
| HMAC secret yok/yanlış veya yalnız POST scope ile GET deneniyor | Browser GET reddedilir; HMAC POST yetkisi read açmaz | Browser'da secret yok; HMAC policy exact GET scope olmadan okumayı kabul etmez. |
| Session sağlayıcısı veya server-side session store kapalı, erişilemez, tutarsız | 503/kapalı; anonymous fallback yok | Snapshot/HTML korumalı içerik üretmeden hata verir; cache'ten eski veri sunulmaz. |
| Reverse proxy kullanılırken doğrudan backend adresi/loopback portu deneniyor | Aynı auth kontrolü veya ağ/UDS seviyesinde erişim reddi | İstemcinin sahte `X-Forwarded-User`/identity header'ı temizlenir; proxy bypass testi başarısız olur. |
| Host hatalı, port yanlış, Origin çapraz veya CORS preflight | 403/405; hiçbir durumda principal kabulü yok | Kaynak filtresi oturum denetimine ek katmandır; başlıklardan kimlik çıkarılmaz. |
| Logout/iptal sonrası aynı cookie tekrar kullanılıyor | 401; eski session yeniden etkinleşmez | Server-side revoke kaydı/nesli doğrulanır; logout yalnız cookie silmekle sınırlı değildir. |
| Bilinmeyen GET veya `/api/veri` dışı route | 404 | Genel GET handler veya varsayılan public route yok. |

## Yayına geçiş kapıları

- IdP/OS kimliği, broker sahibi, principal biçimi, session store konumu ve instance/audience değerleri tanımlanmalı; `codex-kole1` gibi görev atama etiketleri kimlik kanıtı olarak kullanılmamalı.
- TLS sonlandırma ve cookie güvenlik nitelikleri, session TTL/rotasyon/iptal, login/logout ve hesap kurtarma akışı kabul edilmeli.
- Backend'e doğrudan erişimin nasıl kapatılacağı belirlenmeli; yalnız proxy eklemek yeterli değildir. Farklı UID'leri ayırma ihtiyacı varsa servis UID/UDS ve izin listesi tanımlanmalı.
- Dört GET route'u ve path varyantları için auth-before-handler kabulü; CSRF, cross-origin, alias, cache, auth store kesintisi ve proxy bypass senaryoları uygulamada ayrıca doğrulanmalı.
- `/api/veri` snapshot'ının mesaj/ekran alanları için veri minimizasyonu ve okuyucu grupları kararı alınmalı.

Bu iş için route, credential, servis, environment veya test değiştirilmedi; canlı deployment incelenmedi. Kaynak incelemesi mevcut kod davranışını gösterir, gerçek servis erişimini doğrulamaz.

## Kaynaklar

- `panel/server.py`: `do_GET()`, `_kaynak_denetimi()`, `_gonder()`, `auth_gate_yukle()`.
- `panel/auth_integration_draft.py`: POST gate ve henüz server'a bağlı olmayan GET HMAC prototipi.
- `panel/ui.html`: `/api/veri` browser fetch'i.
- `docs/local-api-get-snapshot-decision-455.md`, `docs/hmac-get-read-scope-design-471.md`, `docs/panel-origin-csrf-538.md`, `docs/panel-api-route-scope-matrix-526.md`.
