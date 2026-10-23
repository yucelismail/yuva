# HMAC auth entegrasyonu statik kontrol listesi (#454)

Bu liste, `panel/auth.py`, `panel/auth_integration_draft.py` ve #426 ile
eklenen `panel/server.py` akışının inceleme/işletim kabulünde kullanılmak
üzere hazırlanmıştır. Kaynakta görülen bir kod yolu canlı serviste etkin olduğu
veya uçtan uca doğrulandığı anlamına gelmez. Bu belge hazırlanırken test,
runtime veya panel çalıştırılmadı.

## İnceleme durumu ve sınır

- Yuva kayıtlarında #429 bağımsız route/actor incelemesi kabul edildi; #426'nın
  yinelenen `Content-Length` düzeltmesi de kabul edildi. `_govde_oku()`
  `get_all()` ile birden fazla Content-Length'i body okumadan reddediyor ve
  `do_POST()` framing hatasında bağlantıyı kapatıyor. Bu kaynak/Yuva durumu
  bilgisi canlı HTTP davranışının test edildiğini göstermez.
- Entegrasyon yalnız `YUVA_AUTH_ENABLED=1` ile sunucu başlangıcında yüklenir.
  Ayar yoksa veya `0` ise gate yoktur ve legacy POST davranışı çalışır. Bu
  nedenle canlı config, bu kaynak incelemesinden çıkarılamaz.
- Gate POST mutasyonlarına uygulanır. `GET /api/veri`, `/veri`, `/` ve
  `/index.html` bu gate'ten geçmez; GET snapshot gizliliği sağlamaz.
- Kod yalnız loopback dinlemesini destekler. Bu, aynı makinedeki farklı UID
  erişimini veya aynı UID'deki süreç ayrımını tek başına çözmez.

## Kabul kontrolü

Her maddeyi hedef dağıtım ve kabul edilen kaynak revizyonu üzerinde
işaretleyin. “Kaynakta mevcut” notu statik gözlemdir; canlı kanıt yerine
geçmez.

| Kontrol | Kabul ölçütü | Mevcut kaynak gözlemi / açık nokta |
|---|---|---|
| Varsayılan kapalı | `YUVA_AUTH_ENABLED` yokken veya `0` iken auth modülleri/gate yüklenmemeli; `1` dışındaki değer startup'ı durdurmalı. | `auth_gate_yukle()` bu davranışı tanımlıyor (`server.py:1025-1037`). Çalışan servisin environment değeri bilinmiyor. |
| Zorunlu config ve store | `1` iken `YUVA_AUTH_STORE_ROOT`, `YUVA_AUTH_AUDIENCE`, önceden provision edilmiş geçerli store ve eşleşen audience zorunlu; hata anonim moda düşmemeli. | Startup loader config'i, store'u ve audience'ı kontrol ediyor (`server.py:1039-1070, 1400-1406`). Deployment kanıtı ayrıca alınmalı. |
| Admin allowlist | `YUVA_AUTH_ADMIN_PRINCIPALS` yalnız güvenilir operator config'inden gelmeli; boş/bozuk/tekrarlı değerler reddedilmeli. Request body/rol kaydı admin yetkisi üretmemeli. | Loader ID biçimi ve duplicate kontrolü yapıyor; gate allowlist'i payload'dan değil loader'dan alıyor (`server.py:1042-1069`, `auth_integration_draft.py:65-72`). Gerçek allowlist ve sahibi deployment'a göre incelenmeli. |
| İstek framing | `Transfer-Encoding` reddedilmeli; CL yoksa tanımlı boş-body davranışı korunmalı; tek CL ASCII decimal, sıfır veya pozitif ve body sınırının altında olmalı. Yinelenen CL aynı değeri taşısa bile body okunmadan 400 + bağlantı kapatma olmalı; TE ile CL birlikte kabul edilmemeli. | `_govde_oku()` bu kontrolleri içeriyor ve Yuva #426 revizyonu kabul edilmiş (`server.py:1287-1322`). Dinamik framing/keep-alive davranışı bu görevde test edilmedi. |
| HMAC header'ları | Altı auth header'ının her biri tam bir kez, boş olmayan değerle gelmeli; duplicate/missing değer 401 ile durmalı. Header değerlerinin trim/canonical davranışı belgeli olmalı. | `AuthGate.authenticate_post()` `headers.get_all()` ile auth header duplicate/missing kontrolü yapıyor (`auth_integration_draft.py:80-98`). Header değerlerini `strip()` ediyor; aradaki proxy/framework normalizasyonu ayrıca değerlendirilmelidir. |
| Method, raw path ve body | İmzalanan method `POST`; HMAC'e verilen path exact canonical route; body JSON parse/normalizasyon öncesi alınan ham byte'lar olmalı. Query, alias, trailing slash, bilinmeyen path veya dispatch farklılığı reddedilmeli. | Handler raw `self.path`/`ham` ile doğrular; `AuthGate` exact allowlist ve route eşitliği uygular; auth açıkken dispatch `authn.route` kullanır (`server.py:1343-1380`, `auth_integration_draft.py:74-110`). Reverse proxy varsa request-target dönüşümü deployment'ta doğrulanmalı. |
| Sıralama | Kaynak/gövde sınır kontrolleri → raw body okuma → auth/nonce tüketimi → JSON parse → payload binding → handler/subprocess. Auth hatasında sonraki adıma geçilmemeli. | `do_POST()` sırası bu şekilde (`server.py:1343-1390`). Framing hatası da body/JSON/handler öncesinde terminal olmalı. |
| Scope ve payload policy | Key, principal, audience, exact `POST path` scope ve süre doğrulanmalı. Self/admin/closed policy handler'dan önce uygulanmalı; body kimliği doğrulanmış principal'ın yerine kullanılmamalı. | HMAC verifier scope/key/timestamp'ı doğruluyor (`auth.py:197-257`); gate policy tablosu 11 route'u kapsıyor, `/api/not` kapalı (`auth_integration_draft.py:28-40, 112-153`). `/api/kalp` yetkili olsa da handler'ın mevcut 503 cevabı ve sıfır mutasyon koşulu korunmalı (`server.py:726-734`). |
| Principal aktarımı ve actor kullanımı | Başarılı HMAC'ten dönen principal ayrı argümanla handler'a geçmeli. Actor-sensitive handler principal'ı kullanmalı; body `kimden`/`kimlik` actor kanıtı sayılmamalı. | Dispatcher bütün auth'lu POST handler'larına `principal=` veriyor (`server.py:1381-1385`). #429, `/api/sorumlu` ve `/api/bas-denetci` principal'ı kullanmadığını/audit etmediğini, `mesaj_ekle()` kalıcı provenance'ının hâlâ `unverified` kaldığını buldu (`server.py:526-548, 838-860`; `docs/auth-gate-review-429.md`). Yetki kontrolü, actor audit iziyle aynı şey değildir. |
| HTTP hata status'u | `400` biçim/canonical alan hatası; `401` credential, timestamp window veya nonce reddi; `403` audience/policy; `404` bilinmeyen/noncanonical route; `503` clock/store/nonce kapasitesi/`commit_unknown` gibi geçici veya belirsiz auth-state hatası için kullanılmalı. Auth hataları tanımlı status ve güvenli kodla yanıtlanmalı; geçersiz hata nesnesi güvenli 503'e inmeli. Auth/store hatası JSON parse, handler, mutation veya fallback'e devam etmemeli. | `auth_hata_yaniti()` yalnız 400/401/403/404/503 ve ASCII kod biçimini geçirir, aksi halde generic 503 döndürür (`server.py:1100-1109`). Auth hata kolları terminal return yapıyor (`server.py:1354-1367, 1373-1378`). Canlı HTTP yanıtı test edilmedi. |
| `commit_unknown` | Store commit sonucu belirsizse principal dönmemeli, mutation/CLI çağrılmamalı; 503 ve `commit_unknown` kodu üst katmana taşınmalı. Otomatik kör retry olmamalı. | `HMACAuthenticator` tüm `AuthStateError`'ları aynı code/status ile `AuthError`'a çeviriyor; store `CommitUnknown` 503'tür (`auth.py:254-258`, `auth_store_v2.py:37-45`). Handler gate hatasında dönüyor. İstemci retry/idempotency protokolü ayrı kabul edilmelidir. |
| CLI/subprocess fallback | Auth açıkken doğrulama/binding/config/store hatası yerel CLI veya anonim endpoint fallback'i başlatmamalı. Yetkili `/api/gorev` dispatch'inde `--from` doğrulanmış principal'dan gelmeli. | CLI subprocess'i yalnız handler dispatch sonrasında çalışır; `gorev_calistir()` principal varsa `--from` için onu kullanıyor (`server.py:963-1040, 1381-1390`). Gate kapalıyken legacy body kimliği yolu vardır; bu varsayılan davranıştır, auth hatası fallback'i değildir. |
| Rate limit ve hata sızıntısı | Kimlik doğrulama/nonce/store kapasite hataları sırrı, key varlığını gereksiz ayırt eden ayrıntıyı veya hassas request verisini dökmemeli. Handler exception'ları da secret/path/body sızdırmamalı. Rate limit gerekiyorsa gerçek enforcement, limit anahtarı/TTL ve 429/503 politikası belirlenmeli. | Auth hata yanıtları sınırlı code kullanıyor; fakat handler exception kolu 500 yanıtına `str(e)` ekliyor (`server.py:1388-1393`), bu metnin hassas veri içermediği ayrıca gözden geçirilmeli. `rate_limits` alanının store şeması dışında verifier/HTTP request rate-limit enforcement bulunmuyor (`auth_store_v2.py:143-159, 243-249`; kaynak araması). `MAX_NONCES` kapasite sınırıdır, oran sınırlaması değildir. Ürün/işletim kararı ve kötüye kullanım sınırı açık kalır. |
| GET ve yerel erişim sınırı | POST HMAC'in GET snapshot'ı koruduğu varsayılmamalı; hassasiyet ve erişim hedefi ayrı kararlaştırılmalı. Loopback'in farklı UID veya aynı UID'yi ayırmadığı açık olmalı. | `do_GET()` `/api/veri`/`/veri` ve HTML'i AuthGate olmadan veriyor (`server.py:1319-1331`). #451 kararındaki yerel UID ve GET sınırlarıyla uyumludur; GET auth/session veya socket/peer-credential kapısı bu entegrasyonun parçası değildir. |

## Kabul öncesi açık kapılar

- #426 framing düzeltmesi ve #429 route/actor incelemesi Yuva'da kabul edildi.
  Bu kabul GET gizliliğini, `/api/sorumlu`/`/api/bas-denetci` actor audit
  izini, mesaj provenance'ında HMAC doğrulamasının saklanmasını veya rate
  limiting'i çözmez.
- Canlı environment, store izinleri/audience, admin listesi, proxy yolu ve
  servis UID'si ayrı işletim kanıtlarıyla doğrulanmalı. Buradaki kaynak
  incelemesi bunların canlıda açık veya güvenli olduğunu iddia etmez.
- Auth hatası sonrası handler/subprocess çağrılmadığı ve HTTP yanıtlarının
  beklenen status'u verdiği dinamik olarak bu görevde test edilmedi.

## Kaynaklar

- `panel/server.py`: `auth_gate_yukle()`, `auth_hata_yaniti()`,
  `_govde_oku()`, `do_POST()`, `do_GET()`, `api_sorumlu()`,
  `api_bas_denetci()`, `gorev_calistir()`.
- `panel/auth_integration_draft.py`: `POST_ROUTE_POLICY`,
  `AuthGate.authenticate_post()`, `AuthGate.authorize_payload()`.
- `panel/auth.py`: `HMACAuthenticator.verify_request()`.
- `panel/auth_store_v2.py`: store schema, nonce ve `CommitUnknown`.
- `docs/auth-gate-review-429.md`, `panel/AUTH_INTEGRATION_DRAFT.md`,
  `docs/local-api-access-decision-451.md`.
