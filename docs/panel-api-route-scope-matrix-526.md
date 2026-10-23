# #526 — Panel API route ve scope matrisi

## Kapsam ve sınır

`#455` GET snapshot erişim kararı, `#471` GET read-scope sözleşmesi, `#506`
feature-off GET prototipi ve mevcut `panel/server.py`,
`panel/auth_integration_draft.py`, `panel/auth.py` kaynakları statik olarak
karşılaştırıldı. Yalnız bu analiz notu eklendi; kod, auth flag, credential,
HTTP/runtime veya test işlemi yapılmadı. Canlı environment veya servis
ayarları incelenmedi; aşağıdaki “mevcut” kaynak davranışı gerçek deployment
durumunu kanıtlamaz.

## Genel karar

- `YUVA_AUTH_ENABLED` yok/`0` iken mevcut POST handler'ları legacy, doğrulanmamış
  body kimlikleriyle çalışır. Tam `1` iken server önceden provision edilmiş
  store'u doğrular; config/store hatasında startup durur, anonymous moda geri
  düşmez. Yetkilendirme tam olarak POST rotaları içindir.
- `GET /api/veri`, `GET /veri`, `GET /` ve `GET /index.html` için server'da
  `AuthGate` çağrısı yoktur. POST auth flag'i açılsa da snapshot ve HTML
  anonymous kalır.
- #506 `authenticate_get()` ve `authorize_get()` eklemiş olsa da bunlar yalnız
  `AuthGate(read_enabled=True)` ile kullanılabilen prototip metotlarıdır;
  `server.py` GET dispatch'ine bağlanmamış, `auth_gate_yukle()` tarafından
  etkinleştirilmemiştir. Bugünkü server'da `YUVA_AUTH_READ_ENABLED` ayarı yoktur.
- Protected POST'ta principal kaynağı request body'si değil, HMAC doğrulayıcının
  provision edilmiş key kaydı ve imzalı `X-Yuva-*` header'larıdır. Gate kapalı
  olduğunda handler'lar legacy body iddialarını kullanır; bunlar kimlik kanıtı
  değildir.

## Route matrisi

`Auth kapalı` sütunu mevcut varsayılan/legacy davranışı, `Auth açık` sütunu
`YUVA_AUTH_ENABLED=1` ile kaynakta bağlı POST gate'i gösterir. `Read-scope`
önerisi #471/#506 tasarımıdır; etkin server davranışı değildir.

| Method / route | Erişim sınıfı | Principal kaynağı | Fail-closed davranışı | Eksik kanıt / kalan kapı |
|---|---|---|---|---|
| `GET /api/veri` | Şu an anonymous read; auth flag'inden bağımsız | Yok. #471/#506 uygulanmış olsaydı `GET /api/veri` exact scope'lu HMAC principal gerekir | Mevcut server bu isteği `veri()` ile yanıtlar; HMAC read hatası yolu bağlı değil | İki auth flag'li gerçek GET dispatch, query/body/canonical-target retleri, nonce tüketiminin yanıta bağlanması ve store hatasında snapshot gönderilmediğinin kanıtı yok. Snapshot görev, sohbet ve ekran verisi içerir. |
| `GET /veri` | Şu an anonymous read; compatibility alias | Yok. Tasarımda ayrı `GET /veri` scope gerekir | Mevcut server aynı snapshot'ı döndürür; HMAC read gate yok | `/api/veri` scope'unun alias'a taşmaması ve alias'ın da gate'e alınması uygulanmadı. |
| `GET /` | Anonymous static HTML read | Yok; HTML request'i auth gate'e girmez | Kaynak/Host denetimi haricinde principal kontrolü yok | Browser session, CSRF/logout veya backend'e doğrudan erişim kapısı tasarlanmamış. HTML JavaScript'i anonymous snapshot endpoint'ini çağırır. |
| `GET /index.html` | Anonymous static HTML read | Yok | `/` ile aynı | `/` ile aynı; GET read-scope HTML/browser auth sağlamaz. |
| Diğer GET route'ları | Anonymous route lookup; read/write kapsamı tanımlı değil | Yok | `404` döner; snapshot handler'ına düşmez | Unknown/canonical olmayan request-target'ın auth açık moddaki davranışı yalnız önerilen GET prototipinde var; server entegrasyonu yok. |
| `POST /api/katil` | Legacy modda anonymous write; gate açıkken `self` | Gate açıkken HMAC principal; body `kimlik` principal ile eşleşmeli. Admin olmayan principal yalnız `isci` rolüyle katılabilir | Yanlış/eksik scope veya kimlik bağı `401/403`; bilinmeyen role yükseltmesi reddedilir; startup config/store hatası server'ı durdurur | Provision/enrollment akışı ve client secret dağıtımı yok. Bu endpoint enrollment token redeem etmez; yalnız mevcut Yuva kimlik kaydını yazar. |
| `POST /api/kalp` | Legacy modda anonymous isteği kabul edilen route, fakat state yazımı yok; gate açıkken `self` scope doğrulanır | Gate açıkken HMAC principal ve body `kimlik` eşleşmesi | Handler her durumda `503` ve `online:false` verir; verified heartbeat kaynağı bulunmadığından fail-closed | Provider session / host-supervised heartbeat kanıtı ve tam presence broker entegrasyonu yok. Auth nonce'i handler'ın `503` cevabından önce tüketilmiş olabilir. |
| `POST /api/ayril` | Legacy modda anonymous write; gate açıkken `self` | Gate açıkken HMAC principal; hedef body kimliği principal'a bağlanır | Principal uyuşmazlığı `403`; bilinmeyen kayıt `400`; gate açıkken başarısız auth'ta handler çalışmaz | Çıkışın tüm heartbeat/provider oturumlarını gerçekten kapattığına dair bu route matrisi dışında kanıt yok; endpoint yalnız Yuva durum kaydını değiştirir. |
| `POST /api/ad` | Legacy modda anonymous write; gate açıkken `self_or_admin` | HMAC principal; kendi görünen adını değiştirebilir veya operator config'teki admin başka hedefi seçebilir | Kendi dışındaki hedef için admin değilse `403`; auth/scope hatasında handler çağrılmaz | `YUVA_AUTH_ADMIN_PRINCIPALS` host config'inin korunması/rotasyonu ve gerçek deployment değeri bilinmiyor. |
| `POST /api/rol` | Legacy modda anonymous privilege/write; gate açıkken admin-only | Gate açıkken HMAC principal, admin allowlist'ten | Admin değilse `403`; route scope yoksa `403`; geçersiz domain geçişi `409` | Admin principal allowlist'inin operasyonel sahibi ve gerçek çevrimdışı değişiklik süreci doğrulanmadı. |
| `POST /api/sorumlu` | Legacy modda anonymous write; gate açıkken admin-only | Gate açıkken HMAC principal, admin allowlist'ten | Admin/scope reddi `403`; başarılı state mutasyonu sonrası audit append hatası `503`, cevap mutasyonun kaydedildiğini ve audit'in belirsiz kaldığını bildirir | Durum JSON değişikliğiyle audit JSONL append'i atomik değil; operation receipt/outbox veya bağımsız audit kanıtı yok. |
| `POST /api/bas-denetci` | Legacy modda anonymous privilege/write; gate açıkken admin-only | Gate açıkken HMAC principal, admin allowlist'ten | Admin/scope reddi `403`; domain kuralı ihlali `409`; audit append hatası sonrası `503` ve commit belirsizliği açıklaması | `sorumlu` ile aynı atomiklik/audit boşluğu; gerçek allowlist ve deployment durumu bilinmiyor. |
| `POST /api/yaz` | Legacy modda anonymous message write; gate açıkken `principal_actor` | Gate açıkken principal kimliği out-of-band handler'a geçer; `kimden` body iddiası actor seçmez | Exact POST scope yoksa `403`; rezerve provenance alanları body'de varsa `400`; auth hatasında mesaj writer çağrılmaz | Same-UID süreçler state/JSONL'ı doğrudan değiştirebilir; HMAC gate tek başına host UID izolasyonu veya güvenilir JSONL audit sağlamaz. |
| `POST /api/ekran` | Legacy modda anonymous screen write; gate açıkken `self` | Gate açıkken principal; body `kimlik` principal ile eşleşmeli | Scope/kimlik bağı hatasında `401/403`; auth kapalıyken body iddiası doğrulanmaz | Ekran çıktısının hassas veri/sır taşıyabilmesi ve retention/redaction kapsamı route auth'ından bağımsız. |
| `POST /api/not` | Legacy modda anonymous profile-note write; gate açıkken kapalı | Gate açıkken request önce exact POST scope doğrular, sonra `closed` policy kesin reddeder | Gate açıkken `403 route_closed`; handler çalışmaz. Gate kapalı legacy yolunda handler yazabilir | Endpoint kullanılmıyor olarak işaretli, fakat legacy mode'da route table'da ve yazılabilir. Auth açık değilken kapalı olduğu iddia edilemez. |
| `POST /api/gorev` | Legacy modda anonymous workflow write; gate açıkken admin-only | Gate açıkken HMAC principal; CLI alt sürecine `--from` olarak doğrulanmış principal aktarılır | Scope/admin reddinde subprocess başlamaz; girdi/domain hataları CLI köprüsünde `400`; CLI bulunmazsa `500` | Admin-only tüm görev işlemleri için geniş yetki verir; işlem bazlı scope/assignee yetkisi uygulanmıyor. Auth kapalı legacy route body `kimden` kullanır. |
| `OPTIONS *` | Yazma/read scope değil; CORS preflight kapalı | Yok | `405`, `Allow: GET, POST`, CORS allow header üretilmez ve bağlantı kapatılır | Bu ret, GET veya POST endpoint'lerinin auth edildiğini kanıtlamaz. |
| `POST` bilinmeyen route | Auth kapalıda parse sonrası route lookup; auth açıkta önce exact route allowlist | Gate açıkken bilinmeyen route için principal kurulmadan önce target reddedilir | Bilinmeyen route `404`; auth açıkken canonical olmayan/query'li POST da reddedilir ve handler dispatch edilmez | Bu yalnız POST gate'in bağlı olduğu yolu kapsar; GET için eşdeğer fail-closed gate yoktur. |

## Scope eşlemesi ve red sınırları

Gate açıkken `POST_ROUTE_POLICY` her mutasyon rotasını açıkça listeler. HMAC
doğrulayıcı header'lardaki principal/key/audience ile imzalı exact method/path,
body digest, timestamp ve nonce'u doğrular; store içindeki exact
`POST /path` scope, key durumu ve validity kontrol edilir. Başarılı doğrulama
nonce'u `AuthStateStore.transact()` içinde tüketir. Daha sonra payload policy
principal ile body hedefini bağlar; `/api/yaz` aktörü doğrudan doğrulanmış
principal'dan üretir. `/api/gorev` CLI actor'ı da principal'dan alır.

Auth açıkken eksik/bozuk env, store veya audience eşleşmesi anonymous fallback
değildir; server startup hatasıdır. Request auth/policy hatasında endpoint
handler'ı çağrılmaz. Bununla birlikte auth flag'i yok/`0` iken POST yazımları
legacy'dir ve client-supplied kimlik iddiaları işlenir. Statik kaynak analizi
hangi deployment'ta hangi modun çalıştığını göstermez.

## Eksik kanıt ve kararlar

1. `/api/veri`, `/veri`, `/` ve `/index.html` için yerel anonymous GET'in
   kabul edilip edilmediği ve hangi UID/network namespace kapsamının
   güvenildiği operatör kararıdır; #455 bunu karar olarak bırakır.
2. #471'in önerdiği ayrı read flag, exact GET route dispatch, ayrı
   `GET /api/veri` ve `GET /veri` scope'ları, nonce/error davranışı ve cache
   sözleşmesi #506 prototipinde yalnız kısmen modellendi; canlı server'a
   bağlanmadı. #506 server GET'e bağlamamayı özellikle şart koşmuştur.
3. Browser HTML için HMAC secret dağıtımı yoktur ve uygun değildir. Browser
   kullanılacaksa session/proxy, CSRF, logout/iptal ve backend'e doğrudan
   erişimin kapatılması ayrı tasarlanmalıdır.
4. `YUVA_AUTH_ENABLED` gerçek servis env'i, store içeriği, admin allowlist,
   GET'e erişen farklı UID'ler ve gerçek provider/session kaynağı bu analizde
   okunmadı. Auth gate'in deployment'ta açık veya güvenli olduğu sonucu
   çıkarılamaz.
5. HMAC-authenticated POST aynı UID süreçlerine karşı OS güvenlik sınırı
   değildir. Store/KOK sahipliği, key secrecy, audit atomikliği, admin key
   rotation/revoke ve restore/anti-rollback kararları ayrı kabul ister.

## Kaynaklar

- `docs/local-api-get-snapshot-decision-455.md`, `docs/hmac-get-read-scope-design-471.md`, Yuva #506 görev kartı
- `panel/server.py`: `auth_gate_yukle`, `UCLAR`, `do_GET`, `do_POST`, API handler'ları
- `panel/auth_integration_draft.py`: `POST_ROUTE_POLICY`, `GET_ROUTE_POLICY`, `AuthGate`
- `panel/auth.py`: `HMACAuthenticator.verify_request`, nonce ve exact-scope doğrulaması
- `panel/auth_store_v2.py`: `AuthStateStore.transact()` nonce persistence
- `<YUVA_DATA_ROOT>/gorevler.json`: #455, #471, #506 görev kapsamları
