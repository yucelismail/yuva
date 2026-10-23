# #500 — OpenCode version ve capability startup gate

Tarih: 2026-10-21
Kapsam: Salt-okunur tasarım notu. Adapter kodu, canlı server, test ve runtime
değiştirilmedi/çalıştırılmadı.

## Karar

Provider IO açılmadan önce hedef server'ın health/version bilgisi ve kendi
/doc OpenAPI 3.1 şeması doğrulanmalı. /global/health version string'i tek
başına endpoint uyumluluğunu kanıtlamaz; /doc parmak izi de server sürümünün
yerine geçmez. İkisi birlikte denetlenmiş bir capability allowlist kaydına
bağlanmalı.

İzin politikası exact reviewed pair olmalı:

    provider = opencode
    server_version = exact reported string
    openapi_sha256 = reviewed canonical schema fingerprint

Pair allowlist'te yoksa adapter kapalı başlar. Semver yakınlığı, aynı major
sürüm veya endpoint adlarının hâlâ görünmesi otomatik uyumluluk değildir.
Karar capability başına verilir; tek eksik optional feature diğer yetenekleri
yanlış sınıflandırmamalıdır.

OpenCode resmi Server belgesi GET /global/health için health ve version
döndüğünü, GET /doc için OpenAPI 3.1 spec sunduğunu belirtir. Belge /doc
görünümünü HTML page olarak tanımlar ve hedef instance'taki request/response
tiplerini incelemek için önerir. Dolayısıyla istemci /doc'un ham HTTP
gövdesinin doğrudan JSON olduğunu varsaymamalı; desteklenen biçimi ayrıştırıp
OpenAPI nesnesini çıkarmalı, çıkaramazsa fail closed olmalı.
Kaynak: https://docs.opencode.ai/docs/server/

## Başlangıç denetimi

1. **Config bound:** Base URL önceden onaylanmış server adresine bağlı,
   loopback/credential politikasına uygun olmalı. Redirect izlenmemeli.
   Health, doc ve session istekleri aynı normalized origin'e gider. Secret
   loga, hata metnine veya fingerprint metadata'sına yazılmaz.
2. **Health:** /global/health başarılı HTTP status ile JSON object dönmeli;
   healthy tam olarak true, version non-empty ve bounded string olmalı.
   Aksi halde provider operation'ları blocked/unknown kalır. Health success
   yalnız server availability kanıtıdır.
3. **Schema fetch/parse:** /doc başarılı status ve desteklenen OpenAPI 3.1
   biçiminde gelmeli. HTML wrapper varsa yalnız bilinen extraction uygulanmalı.
   Uzak $ref fetch edilmemeli. Spec eksik, çok büyük, parse edilemez veya
   ambiguous ise fail closed.
4. **Fingerprint:** OpenAPI nesnesini normalize et ve canonical JSON UTF-8
   baytlarının SHA-256'sını al. Object key sırası sabitlenir, semantik array
   sırası korunur. openapi sürümü, info.version, paths/methods, request/response
   schema ve security metadata hash'e girer. HTML nonce, whitespace ve UI
   görünümü hash'e girmez.
5. **Allowlist:** Exact server version + canonical fingerprint + OpenAPI
   sürümü için matrix kaydı yoksa write capability açılmaz. Bilinen version'da
   fingerprint değişimi schema drift'tir. Bilinen fingerprint ve yeni version
   da otomatik izin almaz; pair olarak review edilir.
6. **Capability gate:** Capability'nin HTTP method/path, path parameters,
   request body, success response ve ilgili security şeması fixture ile
   karşılaştırılır. Zorunlu contract uyuşmazsa sadece ilgili capability
   unsupported olur ve çağrıdan önce açık hata döner. Send contract doğrulanmazsa
   yeni prompt gönderilemez.
7. **Snapshot/log:** Denetlenebilir karar metadata'sı: server version, OpenAPI
   version, canonical fingerprint, matrix record ID, review tarihi, capability
   durumları ve sebepleri. Authorization header, secret, env değeri veya
   hassas request body kaydedilmez.

### Fingerprint kaydı

İki digest ayrı tutulabilir:

- raw_doc_sha256: HTTP entity gövdesinin digest'i; fixture tekrarı/teşhis için.
  HTML whitespace veya asset değişiminde değişebileceğinden compatibility
  anahtarı değildir.
- canonical_openapi_sha256: tanınan extraction sonrası parse edilen OpenAPI
  nesnesinin normalize JSON digest'i; version matrix anahtarıdır.

Extraction, ham HTML'de JSON.parse metni arayan genel regex'e dayanmamalı.
Yalnız uygulanan formatlar kabul edilmeli. HTML'de birden fazla spec, yeni
wrapper biçimi, remote ref, normalization hatası veya parser sınırı görülürse
sistem unknown dönmeli. Hash'i alıp sessiz kabul etmemeli.

Fingerprint provenance değildir. Allowlist girdisi review edilmiş source/
fixture, hedef sürüm, reviewer, gerekli capability contractları ve tarih
içermeli. Runtime'dan ilk kez alınan schema yeni, incelenmemiş artifact'tir.

## Capability manifest

Her capability üç değerden birini taşır: supported, unsupported, unknown.

| Capability | Minimum doğrulama | Fail-closed sonucu |
|---|---|---|
| health_version | GET /global/health; body types | başarısız/unknown ise tüm provider IO kapalı |
| read_status | GET /session/status; success response schema | status unknown |
| list_messages | GET /session/{id}/message; bounded query ve item schema | history unknown; reconciliation success değildir |
| send_async | POST /session/{id}/prompt_async; exact request body ve response semantics (matrix 204 bekliyorsa 204) | drift varsa gönderim yasak |
| events | GET /event; event-stream content type ve fixture assumptions | unavailable/unknown; REST-only ancak ayrı policy ile |
| event_replay | belgelenmiş replay cursor/sequence semantiği | yalnız SSE endpoint'i varsa unsupported |
| respond_approval | permission route/body/status ve ayrı human authorization | default off; route varlığı yetki vermez |
| shell, TUI, session mutation | route varlığı yanında ayrı product/security kararı | bu startup gate tarafından açılmaz |

Tehlikeli method/path yalnız spec'te bulunduğu için açılmaz. Pozitif allowlist
configured origin ve session kapsamına göre uygulanır; operationId metni
authorization sınırı değildir. #474'teki provider-specific opaque ID ve
capability report kuralları korunur. Unsupported işlem fake no-op olmaz.

## Yükseltme uyumluluk matrisi

Aşağıdakiler politika örneğidir; hiçbir OpenCode release'inin review edildiği
iddia edilmez.

| Health version | Schema fingerprint | Review durumu | Başlangıç kararı |
|---|---|---|---|
| Yanıt yok, unhealthy veya malformed version | yok | herhangi | bütün provider IO blocked/unknown |
| İncelenmemiş version | herhangi | matrix kaydı yok | blocked; otomatik allowlist ekleme yok |
| V, fingerprint H | exact pair review edilmiş | reviewed | her capability kendi fixture'ına göre değerlendirilir |
| Bilinen V, farklı H2 | schema drift | review bekliyor | etkilenen capability'ler kapalı |
| Yeni V2, eski H ile aynı | version drift | pair review yok | blocked; schema eşitliği tek başına authorization değildir |
| Exact approved pair, optional events yok | optional absence reviewed | REST capabilities açıkça kabul edilmişse çalışabilir; events unsupported |
| Exact pair, send request/response değişmiş | contract mismatch | review bekliyor | send_async kapalı, body/status tahmini yok |
| /doc biçimi veya extraction değişmiş | belirsiz | unknown | schema bağımlı tüm capability'ler kapalı |
| Yeni method/path eklenmiş | client allowlist dışı | yok | route erişilemez kalır |

Upgrade sonrası eski/yeni artifact, schema diff, etkilenen capability,
fixture değişimi ve açık reviewer kararı kaydedilir. Allowlist kaydı yerinde
değiştirilmez; yeni version/fingerprint kaydı eklenir. Rollback eski reviewed
pair'in açık seçimi olur ve başlangıçta health/doc tekrar doğrulanır.

## Hata davranışı

- /doc yoksa hardcoded endpoint contract'ına düşme.
- #487 prototipindeki örnek payload'ı doğrulanmış API schema'sı gibi kullanma.
- HTTP 204'ü completion veya Yuva receipt sayma.
- /global/health version bilgisini API uyumluluğu kanıtı sayma.
- Startup sırasında remote $ref çekme veya schema-server redirect izleme.
- Approval response, shell, TUI control veya session mutation'ı default açma.
- Server version/fingerprint adapter generation sırasında değişirse yeni send'i
  durdur; in-flight state unknown olsun; yeni generation için gate'i çalıştır.
  Belirsiz send'i otomatik tekrar etme.
- Provider state ile Yuva receipt/review state'i ayrı tut (#474).

## Mevcut tasarımlarla hizalama

- #472, /global/health ve /doc'u version-specific API yüzeyi olarak tanımlar;
  plugin event adlarının payload/replay contract'ını kanıtlamadığını belirtir.
- #474 capability'leri supported/unsupported/unknown raporlamayı, kanıt
  kaynağı/sürüm bildirimini, generation-aware reconnect'i ve fake success
  üretmemeyi şart koşar.
- #487 izole taslaktır; prompt_async body ve status cevabının hedef /doc ile
  doğrulanması gerektiğini söyler. Compatibility fixture değildir.
- Bu tasarım panel/server.py, canlı API, auth gate veya Yuva state'ini değiştirmez.

## Uygulama öncesi açık kabul koşulları

1. Desteklenen /doc entity formatı ve extraction kuralı.
2. Canonicalization standardı/uygulaması ve semantik schema diff yöntemi.
3. Version/fingerprint allowlist sahibi, imza/depolama/review ve rollback.
4. Required status/history/send/event fields ve response-size limitleri.
5. Health ile /doc version uyuşmazlığı veya denetim sırasında server restartı.
6. Basic Auth, redirect, loopback, remote ref, schema boyut sınırı ve log
   redaction güvenlik incelemesi.

Bu not yalnız tasarımdır; canlı OpenCode server/schema alınmadı ve hiçbir
capability uygulanmadı.
