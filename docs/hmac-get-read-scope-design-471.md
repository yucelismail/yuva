# Yuva #471 — GET snapshot için HMAC read-scope sözleşmesi

## Karar önerisi

`GET /api/veri` ve uyumluluk alias'ı `GET /veri`, mevcut HMAC v1 canonical byte biçimini yeniden kullanarak korunabilir. Her iki route da açık allowlist'e girmeli, imzalı method/path birebir doğrulanmalı ve yalnız GET yetkisi taşıyan exact scope kabul edilmelidir. Önerilen scope'lar birbirinden ayrıdır:

- `GET /api/veri`
- `GET /veri`

İstemcilerin tercih etmesi gereken canonical endpoint `/api/veri`'dir. Alias desteklenmeye devam ederse, onun için ayrı scope verin; tek bir scope'u iki yola sessizce genişletmeyin. Snapshot okumak için `admin` rolü gerekmez. Key'e yalnız ihtiyaç duyduğu read scope verilir; POST scope'ları bu izin yerine geçmez.

Bu, tasarım önerisidir. Mevcut `AuthGate` ve route tablosu GET doğrulaması uygulamıyor; şu anki GET erişimini korumaz veya değiştirildiğini iddia etmez.

## İmzalı GET isteği

Mevcut `canonical_request_bytes()` alan sırası ve framing'i method/path'i zaten kapsıyor. Byte sözleşmesini değiştirmeden şu değerlerle çağırın:

```text
method = "GET"
path = tam request-target: "/api/veri" veya "/veri"
body = b""
timestamp = canonical Unix seconds
nonce = bu istek için yeni, tahmin edilmesi güç değer
scope = "GET " + path
```

`audience`, `principal_id`, `key_id`, timestamp, nonce ve signature mevcut altı `X-Yuva-*` header'ında taşınır. Signature `GET`, exact path ve boş gövde digest'ini kapsar. Server, doğrulanan principal'ın store kaydında aynı audience ve exact GET scope bulunduğunu doğrular. `GET /api/veri` izni `POST /api/veri`, `POST /api/gorev`, başka GET yolu veya alias izni vermez.

Mevcut doğrulayıcı canonical timestamp, nonce, signature ve scope kontrolünü yapabiliyor; GET için gereken değişiklik bu sözleşmeyi `AuthGate`/server allowlist'ine eklemektir. `AuthGate.authenticate_post()` GET'i kabul edecek şekilde gelişigüzel genişletilmemeli; ayrı `authenticate_get()` veya açık method allowlist'li ortak yardımcı kullanılmalı, POST route ve payload policy aynı kalmalıdır.

## Request-target ve gövde normalizasyonu

Snapshot şu an query parametresiyle filtrelenmiyor. Bu nedenle imzalı GET için query string'i tamamen reddedin; parametreleri sıralama, decode etme veya imzadan sonra normalize etme kuralı tanımlamayın. Tam HTTP request-target aşağıdaki iki değer dışında ise reddedilsin:

```text
/api/veri
/veri
```

Şunlar reddedilmelidir: query/fragment, trailing slash, çift slash, nokta segmenti, yüzde kodlanmış alternatif, mutlak URI, bilinmeyen alias ve whitespace. `urlsplit()` ile path çıkarıp yalnız path'i imzalamak yeterli değildir; ham request-target seçilen exact route ile byte/metin olarak aynı olmalıdır. Böylece auth'ta doğrulanan path dispatch'te kullanılan path olur.

GET body desteklenmesin. Transfer-Encoding reddedilsin. Content-Length yoksa veya tek değer `0` ise imzalanan body `b""` olsun. Tekrarlı Content-Length, bozuk/negatif/ASCII olmayan uzunluk ve pozitif body uzunluğu reddedilsin; gövde okunmadan hata veriliyorsa bağlantı kapatılsın. Bu kural, handler'ın beklemediği body byte'larının sonraki keep-alive isteğiyle karışmasını önler. Mevcut POST framing sözleşmesi değişmeden kalmalıdır.

## Replay, zaman ve nonce

- Mevcut varsayılan timestamp toleransı ±60 saniyedir; yapılandırılan pencere 1–300 saniye arasında kalır. GET için yeni, gevşek bir pencere açmayın.
- Her GET için benzersiz nonce zorunludur. Doğrulama başarılı olmadan cevap verilmemeli; nonce mevcut `AuthStateStore.transact()` işlemi içinde tüketilmelidir. Aynı method/path/identity/key/audience/nonce tekrarında HMAC doğrulaması reddedilmelidir.
- Nonce tüketimi auth store'a yazma yapar; bu nedenle GET uygulama verisini değiştirmese de doğrulama sırasında auth-state mutasyonu vardır. Store hatası veya `CommitUnknown` durumunda snapshot gönderilmemeli.
- Timeout sonrası aynı imzalı istek körlemesine tekrar kullanılmamalı; yeni istek için yeni nonce ve timestamp üretin. Snapshot GET salt-okunur ve idempotent kalmalı, response üretimi auth/nonce mutation'ından ayrı bir side effect oluşturmamalıdır.
- Nonce alanı sınırlı kapasiteye sahiptir; ayrı rate limit tasarımı yoksa read scope ile sınırsız sorgu koruması sağlandığını iddia etmeyin. Başarılı ve başarısız isteklerde hassas snapshot, key varlığı veya signature materyali hata yanıtına/loga yazılmamalıdır.

## Yanıt ve hata sözleşmesi

Mevcut güvenli auth hata dönüşleriyle uyumlu kalın: bozuk framing/canonical target için `400`, eksik/geçersiz credential, timestamp veya replay için `401`, audience/scope/policy reddi için `403`, bilinmeyen/noncanonical route için `404`, auth store/clock/nonce kapasitesi ya da commit sonucu belirsizliği için `503`. Dış yanıtlar sınırlı, sır içermeyen hata kodları kullanmalı; başarısız doğrulama sonrası `veri()` veya başka handler çalışmamalıdır.

Başarılı yanıtın kapsamı `GET /api/veri` bugün ne döndürüyorsa onunla sınırlıdır. Yanıtta `Cache-Control: no-store` korunmalı; aracıların snapshot'ı ortak cache'te saklamasına izin vermeyin. HMAC isteği istemcinin kimliğini sunucuya doğrular; yanıtı şifrelemez veya response integrity sağlamaz. Mevcut loopback sınırını koruyun. Uzak erişim için ayrıca TLS ve uygun response/auth mimarisi gerekir.

## HTML ve tarayıcı sınırı

Tarayıcı koduna HMAC key koymayın. `panel/ui.html` içindeki JavaScript'te paylaşılan secret olması, tarayıcıyı bu secret'ı okuyabilen kullanıcıya karşı güvenli kılmaz.

GET gate etkinleştirilmiş dağıtımda iki desteklenen seçenek vardır:

1. `/` ve `/index.html` statik shell olarak açık kalsın; snapshot çağrısı read scope olmadan `401` alsın ve UI veriyi göstermesin. HTML'in kendisinde kullanıcıya özel snapshot/veri gömülü olmamalıdır.
2. Tarayıcı için ayrı doğrulanmış session/reverse-proxy köprüsü tasarlansın. Cookie, CSRF, Origin, logout/iptal ve backend'e doğrudan erişimin kapatılması ayrıca tanımlanmalıdır. Proxy kimliği doğrulanmış olsa bile aynı host'tan backend'e doğrudan erişim açık kalırsa gate bypass edilir.

GET HMAC'in HTML'i otomatik olarak koruduğu veya browser session yerine geçtiği söylenmemelidir. `Host`/`Origin` ve CORS kuralları kimlik doğrulama değildir.

## Feature flag ve POST uyumluluğu

Geriye uyum için GET okumayı açık bir opt-in olarak ayırın: önerilen yeni `YUVA_AUTH_READ_ENABLED` varsayılan yok/`0` iken mevcut GET davranışı sürsün; `1` yalnız HMAC doğrulama altyapısı (`YUVA_AUTH_ENABLED=1`) da açıksa kabul edilsin, aksi durumda startup fail-closed dursun. Bilinmeyen flag değerleri de startup hatası olmalıdır. Startup özeti `GET snapshot: public` veya `GET snapshot: HMAC read scope` durumunu açıkça bildirmeli; `YUVA_AUTH_ENABLED=1` ifadesi tek başına GET'in korunduğu anlamına gelmemelidir.

Bu ayrımla:

- POST signing biçimi, header seti, exact `POST /path` scope'ları ve `POST_ROUTE_POLICY` değişmez.
- `YUVA_AUTH_READ_ENABLED` kapalıysa POST auth'a dokunulmaz; GET legacy davranışı açıkça sürer.
- Read flag açıkken hem `/api/veri` hem uyumlu tutulan `/veri` auth kapısına girer. Bir alias'ı unutmak koruma atlaması yaratacağından GET route tablosu bütün veri alias'larını kapsamalıdır.
- Tarayıcı UI'sinin doğrudan HMAC GET yapmadığı, read flag açılınca mevcut UI'nin yetkisiz kalabileceği release/operasyon notunda açıklanmalıdır.

Tek flag ile `YUVA_AUTH_ENABLED=1` açıldığında tüm GET'in birden korunması da mümkündür; fakat bu, mevcut auth-on tarayıcı davranışını kırabilir. Ürün bu kırılmayı açıkça seçerse ayrı read flag yerine tek flag kullanılabilir. İki model aynı anda belirsiz uygulanmamalı; dağıtım matrisi ve startup durumu açık olmalıdır.

## Uygulamaya geçiş kapıları

1. Snapshot alanlarını ve hassasiyetini, hangi principal'ların okuyacağını ve alias desteğini operatör kararıyla netleştirin. Kimliksiz yerel-only model seçilirse bunu açık risk kabulü olarak belgeleyin.
2. Exact GET allowlist, method/path scope eşlemesi, query ve body framing retleri, nonce tüketimi ve hata eşlemesi için kod sözleşmesi çıkarın. GET'in hiçbir koşulda snapshot'ı auth öncesi üretmediğini/serialize etmediğini kontrol edin.
3. `YUVA_AUTH_READ_ENABLED` ve `YUVA_AUTH_ENABLED` birleşimini fail-closed başlatma tablosuyla belgeleyin; POST mevcut istemci imzalama sözleşmesiyle aynı kalsın.
4. `/`, `/index.html`, `/api/veri`, `/veri`, canonical olmayan varyantlar, eksik/yanlış scope, replay, stale timestamp, duplicate headers, body/framing ve store belirsizliğini auth kapalı/açık yapılandırmalarda ayrı kabul senaryolarıyla doğrulayın.
5. Browser session gerekiyorsa HMAC read scope'dan ayrı mimari olarak tasarlayıp backend'e doğrudan erişim yolunu kapatın. TLS, cache, logging, snapshot minimizasyonu ve read rate limit kararlarını ayrıca kabul edin.
6. Operasyon öncesi pre-provision/rotation/revoke, backup/restore ve anti-rollback anchor kararlarını tamamlayın. Bu tasarım notu credential üretmez, feature flag açmaz, GET'i uygulamaz veya canlı deployment'ı doğrulamaz.

## Kaynak dayanakları

- `docs/local-api-get-snapshot-decision-455.md`: GET snapshot risk seçenekleri ve geçiş kapıları.
- `panel/server.py`: `do_GET()`, `do_POST()`, `veri()`, `auth_gate_yukle()` ve mevcut GET alias'ları.
- `panel/auth.py`: `canonical_request_bytes()`, `HMACAuthenticator.verify_request()`, timestamp/nonce/scope doğrulaması.
- `panel/auth_integration_draft.py`: mevcut POST-only `POST_ROUTE_POLICY`, `AuthGate.authenticate_post()` ve payload policy.
- `panel/auth_store_v2.py`: exact scope validation, nonce store, `transact()` ve `generation_floor` sınırı.
- `panel/ui.html`: tarayıcının snapshot isteği.
