# #528 — OpenCode adaptörü için sürüm ve capability kapısı

Tarih: 2026-10-23
Kapsam: Statik karar notu. OpenCode/Yuva kodu değiştirilmedi; provider veya
harici servise bağlanılmadı; test, runtime ve deployment yapılmadı.

## Karar

OpenCode provider IO varsayılan olarak kapalıdır. Bir adapter generation'ı,
yalnızca hedef server'ın sağlıklı olduğu, `/doc` içeriğinin desteklenen biçimde
çözümlendiği ve **tam sürüm + kanonik OpenAPI parmak izi + OpenAPI sürümü**
üçlüsünün önceden incelenmiş bir compatibility kaydıyla eşleştiği durumda
capability değerlendirmesine geçebilir. Her capability ayrıca kendi endpoint,
request/response ve güvenlik sözleşmesi için onaylanır. Kayıt bulunmaması,
belirsizlik veya schema drift `unknown/closed` sonucudur; yakın semver, aynı
major sürüm, endpoint adlarının benzemesi ya da yalnız sürüm/parmak izi eşitliği
kapıyı açmaz.

Bu not bir runtime allowlist girdisi tanımlamaz. İncelenmiş bir OpenCode
version–schema çifti veya hedef instance `/doc` fixture'ı mevcut kaynaklarda
yoktur; dolayısıyla bugün hiçbir provider capability'si bu notla açılmış
sayılmaz.

## Başlangıç kapısı

Her yeni bağlantı generation'ında aşağıdaki sıra uygulanmalıdır:

1. **Origin sabitleme:** İstekler önceden yapılandırılmış tek origin'e gider;
   redirect izlenmez ve `/global/health`, `/doc` ile capability çağrıları
   arasında origin değişmez. Kimlik bilgisi, istek gövdesi veya ham provider
   içeriği karar loguna yazılmaz.
2. **Health ve sürüm:** `GET /global/health` beklenen HTTP cevabıyla JSON object
   döndürmeli; `healthy` tam olarak `true`, `version` boş olmayan ve uzunluğu
   sınırlandırılmış bir string olmalıdır. Bu yalnız erişilebilirlik kanıtıdır.
   Hata, belirsiz tür veya health ile sonraki schema kaydı arasındaki sürüm
   tutarsızlığı bütün provider IO'yu kapatır.
3. **`/doc` çözümleme:** Başarılı cevap içinden yalnız açıkça desteklenen OpenAPI
   3.1 sunum biçimi çıkarılır. Ham entity'nin JSON olduğu varsayılmaz. Genel
   regex ile HTML içinden spec arama, remote `$ref` fetch etme, redirect izleme
   veya belirsiz wrapper'ı tahmin etme yoktur. Eksik, hatalı, fazla büyük,
   çoklu/ambiguous veya tanınmayan biçim `unknown` üretir.
4. **Parmak izi ve kayıt:** Normalize OpenAPI nesnesinin canonical JSON UTF-8
   baytlarından SHA-256 hesaplanır. Object key sırası normalize edilir,
   semantik array sırası korunur. OpenAPI sürümü, `info.version`,
   path/method'lar, request/response şemaları ve security metadata fingerprint
   girdisidir. Ham HTTP entity digest'i yalnız teşhis içindir; compatibility
   anahtarı değildir. Exact `(provider=opencode, server_version,
   openapi_version, canonical_openapi_sha256)` kaydı yoksa kapı kapalı kalır.
5. **Capability sözleşmesi:** Exact pair incelenmiş olsa bile her capability
   için method/path, path parametreleri, body, başarı cevabı, ilgili security
   şeması ve kapsam ayrı ayrı karşılaştırılır. Eşleşmeyen capability kapalı
   kalır; diğerleri ancak kayıtta bağımsız olarak onaylanmışsa kullanılabilir.
6. **Generation tutarlılığı:** Health sürümü veya `/doc` fingerprint'i
   generation içinde değişirse yeni gönderim durur; devam eden mutation sonucu
   `unknown` olur. Yeni generation baştan doğrulanır. Önceki exact pair'e
   otomatik dönüş veya belirsiz gönderimi tekrar etme yoktur.

Karar kaydı yalnız sürüm, OpenAPI sürümü, canonical fingerprint, incelenmiş
manifest/fixture kimliği, reviewer/tarih ve capability durum/gerekçelerini
tutabilir. Secret, auth header, env değeri, hassas body ve ham schema loga
kopyalanmaz. Runtime'dan ilk kez görülen schema kendi başına onaylı fixture
değildir.

## Capability matrisi

Durumlar `supported`, `unsupported`, `unknown` olarak üç değerlidir. Başlangıç
durumu her zaman `unknown`'dır; yalnız exact pair için kaydedilmiş olumlu
endpoint sözleşmesi `supported` yapabilir. `unknown` hiçbir çağrı izni vermez.

| Capability | İnceleme/kanıt şartı | Kapalı kalma ve anlam sınırı |
|---|---|---|
| `health_version` | `/global/health` cevap türü, tam `healthy=true` ve bounded exact version | Başarısızsa diğer tüm provider IO kapalı; health, session/model hazır demek değildir. |
| `read_status` | `/session/status` response schema ve hedef session ile exact korelasyon yolu | Multi-session snapshot eşleşmiyorsa `unknown`; status snapshot turn sonucu veya Yuva receipt değildir. |
| `list_messages` | `/session/{id}/message` query sınırı ve item/message schema | Bounded history salt-okunur gözlemdir; eksik kayıt “gönderilmedi” kanıtı değildir. |
| `send_async` | `/session/{id}/prompt_async` exact request body ve beklenen HTTP cevabı/semantiği | Belirsiz transport/response sonucu `unknown`; `204` yalnız endpoint yanıtıdır. Otomatik retry yok. |
| `events` | `/event` response/content type, SSE zarfı ve hedef sürümde event payload yolları | Şema yok veya drift varsa kapalı. Event stream tek başına eksiksiz transcript/replay sağlamaz. |
| `event_replay` | Dokümante edilmiş cursor kapsamı, resume ve replay davranışı | Yalnız SSE veya opak SSE `id` varsa `unsupported`; generic `seq`, `sequence`, `version` cursor sayılmaz. |
| `respond_approval` | Permission route/body/status şeması ve ayrı, aynı permission isteğine bağlı insan yetkilendirmesi | Varsayılan kapalı. Route veya `permission.asked` olayı onay yetkisi vermez. |
| shell, TUI, session mutation | Ayrı ürün ve güvenlik kararı, dar endpoint allowlist'i ve insan yetkilendirmesi | Bu startup gate açmaz; route'un `/doc` içinde bulunması yeterli değildir. |

REST-only çalışma, ancak manifest ilgili exact pair için status/history/send
capability'lerini bağımsız biçimde onaylayıp event'leri `unsupported` olarak
işaretliyorsa düşünülebilir. Sessizce SSE yerine REST kullanmak veya eksik
capability'yi no-op gibi göstermek yasaktır.

## SSE ve REST uzlaştırma sınırı

- SSE event'i yalnız blank-line delimiter ile tamamlandığında dispatch edilir;
  EOF'taki yarım event atılır ve batch incomplete kalır. EOF, timeout, byte/event
  sınırı veya reconnect `idle`/başarı kanıtı değildir.
- `session.idle` ve `session.status`, yalnız hedef `/doc` tarafından doğrulanmış
  payload yolunda açık `properties.sessionID` hedef session ile eşleştiğinde o
  session için gözlem sayılabilir. Eksik, malformed, global veya başka session
  olayı eşleşmemiştir; hedef state'ini değiştirmez. Bu alan yolu prototipte
  beklenen biçimdir, hedef OpenCode schema'sında doğrulanmış değildir.
- SSE `id` opaque korelasyon metadatası olarak kalır. Replay cursor/sequence
  garantisi belgelenmedikçe reconnect sonrası eksiksiz event alımı varsayılmaz.
  Genel `sequence`, `seq` ve `version` alanları sıralama kanıtı değildir;
  çelişkili veya sırası belirsiz status geçişi `unknown` kalır.
- Kopma veya gönderim yanıtı kaybında önce yalnız-okunur
  `GET /session/status` ve `GET /session/{id}/message` gözlemleri alınabilir.
  Bunlar Yuva receipt'i, terminal turn sonucu ya da kayıp event'lerin tam
  karşılığı değildir. `not_found`, bounded history'de görünmeme veya eski
  snapshot “hiç gönderilmedi” demek değildir. Otomatik resend yapılmaz.
- `messageID` korelasyon/reconciliation girdisidir; idempotency garantisi
  olarak kabul edilmez. Yeni gönderim gerekiyorsa ayrı bir açık karar ve yeni
  attempt/receipt sözleşmesi gerekir.

Bu sınırlar #472 API araştırması, #487 HTTP adapter ve #488 SSE/REST
prototiplerinin tasarım varsayımlarını bir araya getirir. Onlar hedef server
fixture'ı veya canlı provider sözleşmesi değildir.

## Sürüm geçiş kararı

| Gözlem | Karar |
|---|---|
| Health yok/unhealthy/malformed veya version boş | Bütün provider IO `unknown/closed`. |
| `/doc` yok, tanınmıyor veya parse edilemiyor | Schema bağımlı tüm capability'ler `unknown/closed`; hardcoded contract fallback yok. |
| Yeni version, schema aynı fingerprint | Exact pair yeni olduğundan review bekler; kapalı. |
| Bilinen version, fingerprint değişmiş | Schema drift; etkilenen capability'ler kapalı, pair yeniden incelenir. |
| Exact pair kayıtlı, tek capability sözleşmesi uyuşmuyor | Yalnız o capability `unsupported/closed`; diğerleri kendi kaydına göre kalır. |
| Exact pair ve ilgili capability sözleşmesi incelenmiş | Yalnız kayıtlı capability `supported`; kapsam ve evidence provenance korunur. |
| Generation sırasında version/fingerprint değişmiş | Yeni gönderimler durur; in-flight mutation `unknown`; yeni startup gate gerekir. |

Allowlist girdisi yerinde sessizce güncellenmez; yeni pair ve inceleme kaydı
eklenir. Geri dönüş de açıkça seçilmiş eski reviewed pair için başlangıç
denetimini yeniden çalıştırmayı gerektirir.

## #509 bulgularının bugünkü prototiple karşılaştırması

#509 tarihsel statik incelemesinde session ID'siz status event'i, yarım SSE
event'inin EOF'ta dispatch edilmesi, `localhost` DNS çözümünün pinlenmemesi,
structured `unknown` send sonucu eksikliği, `HttpResult` repr sızıntısı,
genel sequence kullanımı ve sınırsız reducer listeleri raporlanmıştı. Bugünkü
`prototypes/opencode-adapter/README.md` ve ilgili kaynakta bunların çoğu için
karşılık gelen önlemler görünüyor: açık session eşleşmesi, delimiter şartı ve
EOF'ta incomplete sonuç, numeric loopback IP, typed `unknown`, repr'den body
gizleme, generic sequence'i kullanmama ve bounded koleksiyonlar.

Bu, kodun bağımsız doğrulandığı veya test edildiği anlamına gelmez; bu görevde
yalnız statik kaynak okuması yapılmıştır. Ayrıca #509'un güvenlik incelemesi,
adaptörün version fingerprint/capability negotiation, Yuva integration,
durable ledger ve redaction pipeline içermediğini belirtir. Özellikle event
payload'ındaki `properties.sessionID`, status cevabı ve gönderim request/response
şeması hedef `/doc` ile doğrulanana kadar entegrasyon sözleşmesi değildir.

## Kaynaklar ve açık kalan kanıt

- `docs/opencode-session-bridge-options-472.md` — endpoint anlamları, `/doc`,
  SSE replay sınırı, timeout/unknown ve approval sınırı.
- `prototypes/opencode-adapter/README.md`, `adapter.py`, `reconcile.py` — #487
  HTTP ve #488 SSE/REST prototiplerinin mevcut statik davranışı ve limitleri.
- `docs/opencode-capability-startup-check-500.md` — exact version/fingerprint
  eşleşmesi, fingerprint üretimi, capability manifest ve fail-closed matrisi.
- `docs/opencode-http-adapter-security-review-509.md` — tarihsel güvenlik
  bulguları ve öneriler.
- `docs/opencode-messageid-retry-risk-493.md` ve
  `docs/opencode-output-yuva-mapping-505.md` — idempotency, untrusted output ve
  Yuva receipt sınırı.

Hedef OpenCode sürümü, `/doc` entity'si, kanonik fingerprint, onaylı capability
manifest'i ve gerçek provider davranışı bu kaynaklarda doğrulanmamıştır. Bunlar
olmadan hiçbir uyumluluk veya canlı kullanıma hazır olma iddiası kurulamaz.
