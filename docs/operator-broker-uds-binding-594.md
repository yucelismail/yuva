# Yuva #594 — Operator signer ile ayrı UID broker arasında UDS/HMAC binding

## Amaç ve mevcut sınır

Bu sözleşme #582'nin hedef mimarisini somutlaştırır: agent'lardan ayrı OS UID'sinde operator signer, ayrı OS UID'sinde verifier/broker ve agent başına ayrı UID. Agent ne raw HMAC key'e ne broker verifier store'una ne de signer işlemini çağıran serbest bir imza API'sine erişebilir. Signer secret ile imzalar; broker secret'ın verifier kopyasını ve replay state'ini kendi owner-only store'unda tutar. HMAC shared-secret'tır: broker kompromisi operator imzası üretebilir ve non-repudiation sağlamaz.

Bu yalnız sözleşme ve in-memory sentetik fixture'dır. Socket/UID/account/key/store/service/auth kurulmuyor; gerçek HMAC veya canlı API kullanılmıyor. #582'nin güncel kararı aynı-UID HMAC'i reddeder. Signer, broker ve agent ayrımının hostta kanıtı, lifecycle aracı veya geçiş kabulü yoksa operator kaynağı `unknown/unverified` kalır ve açılış **NO-GO**'dur.

## UDS frame sözleşmesi

Bir bağlantı yalnız bir istek/cevap taşır; istekten sonra broker bağlantıyı kapatır. Her frame `uint32_be(payload_length) || payload` biçimindedir. Payload strict UTF-8 JSON'dur; duplicate object key, unknown/missing field, invalid UTF-8, sıfır/aşırı length, limit aşımı, yarım frame, fazla trailing byte veya ikinci frame reddedilir. Canlı uygulama exact-length read için deadline ve bir istek başına en çok 1 MiB raw body + sınırlı envelope bütçesi uygular.

İstek JSON nesnesi şu alanları **tam olarak** taşır:

```json
{
  "version": 1,
  "method": "POST",
  "path": "/api/yaz",
  "body_b64u": "<raw body bytes, unpadded canonical base64url>",
  "principal_id": "<operator principal>",
  "key_id": "<provisioned key id>",
  "audience": "<broker instance audience>",
  "timestamp": 1800000000,
  "nonce": "<fresh 22-128 character nonce>",
  "signature": "<unpadded canonical base64url HMAC-SHA256>"
}
```

Bu şekil alan açıklamalı örnektir; fixture değerleri, anahtar veya geçerli imza değildir. `peer_uid`, `scope`, `source_class`, `kimden`, `--from`, rol, HMAC key veya auth store bilgisi frame'e konmaz. Broker correlation ID'yi kendi üretir; frame içinden gelen request/trace ID authorization kanıtı değildir. UDS envelope dışına header, arbitrary options, env, signer path, key material veya verifier result eklenemez.

`body_b64u`, HTTP'ye gidecek ham body baytlarının canonical base64url gösterimidir. Signer önce JSON body'yi bir kez UTF-8'e çevirir, sonra aynı baytları imzalar ve frame'e koyar; broker canonical biçimde çözüp bu baytları HMAC doğrulamasında kullanır. JSON parse/yeniden serialize edip imza hesabındaki gövdeyi değiştirmez. HMAC v1 alanları mevcut #448 sözleşmesiyle aynı sıradadır: audience, principal, key ID, method, exact path, `SHA256(raw_body)`, canonical timestamp ve nonce. HTTP auth header'ları UDS'den aktarılmaz; uygulanacak HTTP adapter bunları yalnız broker tarafında üretir.

Response frame yalnız server tarafından üretilen correlation ID, `accepted`/`rejected`/`unknown` outcome ve içeriksiz sabit reason code taşır; signature, body, header, exception text veya ham downstream response taşımaz. Request işlenmiş olabilir ama response kaybolmuşsa sonuç `unknown`'dır; signer aynı frame'i veya aynı operation'ı otomatik tekrarlamaz. Mevcut `/api/yaz` sözleşmesinde broker operation receipt/idempotency kanıtı yoktur; belirsiz dispatch operatörce uzlaştırılmadan yeniden gönderim yapılmaz.

## Peer UID ile principal ve custody binding

1. Broker `accept()` sonrasında aynı connected socket'in kernel peer credentials'ını (`SO_PEERCRED`) okur; frame parse/dispatch öncesi numeric UID'yi root/operator yönetimli, unique ve enabled UID→principal mapping'e göre doğrular. Socket directory/group permission bağlantı erişimini daraltır; principal'ı body'den veya grup adından üretmez.
2. Başarılı mapping sonucu principal, ilgili aktif map revision ve signer rolüdür. Mapping eksik, duplicate, disabled, stale veya değişiklik anında revision uyuşmazsa istek reddedilir. Peer UID başlığı/frame alanından alınmaz ve `PID`, process name, `argv`, unit adı, `--from` veya `kimden` principal'a çevrilmez.
3. İmzalı HMAC `principal_id` kernel-UID map'inden çıkan operator principal'la; `key_id` o principal'ın aktif provision edilmiş key kaydıyla eşleşmelidir. HMAC doğrulayıcı configured `audience` değerini kullanır; istemci frame'indeki başka audience kabul edilmez. Key'in `revoked`, validity, exact scope ve store instance koşulları mevcut `HMACAuthenticator` kuralları gibi doğrulanır.
4. `operator` source label yalnız exact `POST /api/yaz` verified principal, operator allowlist ve ayrı operator custody marker/revision birlikte sağlanırsa server/broker tarafından üretilir. Body'deki source/actor alanları reddedilir; signer body'sinde `kimden` yoktur. Verified HMAC'i source-label'a otomatik yükseltmek yasaktır.
5. UDS peer UID kernel process kimliğini kanıtlar; insanın talimat verdiğini tek başına kanıtlamaz. Signer yalnız ayrı operatör oturum/confirm akışından gelen typed işlemi kabul eder; agent'ların erişebildiği `sign(arbitrary_method,path,body)` RPC'si sunmaz. Agent ile signer aynı UID'deyse veya agent signer process/memory/FD'lerine erişebiliyorsa custody başarısızdır.

## Route ve payload allowlist'i

İlk operatör UDS kapsamı tek route ve tek scope'dur:

| Alan | İzin |
|---|---|
| Method + exact path | `POST /api/yaz` |
| HMAC scope | `POST /api/yaz` — `POST_ROUTE_POLICY` içindeki `principal_actor` doğrulaması |
| Body keys | Yalnız `metin` (zorunlu, non-empty, sınırlı), `kime` (isteğe bağlı, string), `tur` (isteğe bağlı `not`/`soru` enum'u) |
| Principal/actor | Authenticated HMAC principal ayrı argument olarak; `kimden` veya `source_class` body'den alınmaz |
| Reddedilen yollar | GET snapshot/HTML, `/veri` alias'ı, `/api/gorev`, `/api/ekran`, role/admin routes, bilinmeyen route, query/trailing slash/encoded path |

Başka route/scope eklemek ayrı risk, operator onayı ve allowlist revizyonu ister. UDS bağlantısı broad API yetkisi veya admin hakkı vermez. GET/browser session ve agent identity bu kapsamın dışındadır. Mevcut `POST_ROUTE_POLICY` içinde başka key'lerin bulunması broker'ın hepsine izin verdiği anlamına gelmez.

## Doğrulama ve dispatch sırası

```mermaid
sequenceDiagram
    actor Human as Onaylı operator oturumu
    participant Signer as Operator signer UID
    participant UDS as UDS bağlantısı
    participant Broker as Broker/verifier UID
    participant Store as Broker auth store
    participant Writer as Yetkili Yuva message writer
    Human->>Signer: Typed, onaylanmış message intent
    Signer->>Signer: Scope/body doğrula; raw bytes üret; timestamp/nonce/HMAC imzala
    Signer->>UDS: Length-prefixed signed frame (raw key yok)
    UDS->>Broker: Kernel peer credentials + frame
    Broker->>Broker: SO_PEERCRED UID allowlist ve map revision doğrula
    Broker->>Broker: Frame/schema/size/exact route/body framing doğrula
    Broker->>Store: HMAC/key/scope/audience/time ve nonce'u atomik doğrula+tüket
    Store-->>Broker: VerifiedPrincipal veya fail-closed hata
    Broker->>Broker: JSON parse + payload allowlist + custody gate
    Broker->>Writer: Principal ayrı argümanla; server-set source class
    Writer-->>Broker: Bounded result / safe error code
    Broker-->>UDS: accepted/rejected/unknown + safe code
    Broker-->>Signer: Length-prefixed response, sonra bağlantı kapat
```

Host credential kontrolü frame'den önce; method/path allowlist ve framing HMAC doğrulamasından önce; JSON parse, body policy ve dispatch HMAC doğrulaması/nonce commit'inden sonra çalışır. HMAC verifier nonce'u atomik store transaction'ında tek kez tüketir. Broker ve downstream panel aynı nonce'u iki verifier ile tüketmeye çalışmamalı; broker tek verifier ise downstream'e principal'ı taşıyan ayrı, peer-authenticated internal dispatch sözleşmesi olmalıdır. Internal adapter güvenli değilse ikinci gate'i atlamak yerine iş akışı uygulanmaz.

## Replay, audience, kapanış ve belirsizlik

- `audience` broker instance'ına host config/provisioning ile sabitlenir. Request'ten audience seçerek başka servise yetki açılmaz. Instance değişimi key/scope re-provision ve custody kabulü gerektirir.
- Timestamp mevcut HMAC v1 varsayılan ±60 saniye pencere ve 1–300 saniye konfigürasyon sınırını izler. Her istek için yeni tahmin edilmesi güç nonce; duplicate key/header yok; nonce state broker store'unda atomik ve kalıcı olarak tüketilir. Restart nonce geçmişini sıfırlamaz.
- Peer reddi, frame/framing/schema/route hatası, yanlış key/principal/audience, signature, expiry, replay, custody veya store hatası dispatch üretmez. Store/clock/nonce commit `unknown` veya `CommitUnknown` ise snapshot/message handler çağrılmaz; aynı nonce veya frame kör retry edilmez.
- Socket connect/read deadline, client EOF, yarım frame, oversize veya trailing bytes durumda bağlantı kapatılır ve dispatch yapılmaz. Nonce commit'inden sonra body/policy reddi nonce'u geri almaz. Dispatch sonrası response kaybı `unknown` kalır; fresh nonce ile tekrar etmenin duplicate mesaj oluşturabileceği idempotency receipt yoksa otomatik denenmez.
- Broker restart sırasında tüm açık bağlantılar kapanır; pending frame kuyruklanıp sonradan yürütülmez. Config/store/peer map revision yüklenemezse servis bağlantıyı kabul etmez. Enabled mode'da startup auth-off veya legacy HTTP fallback'e dönmez.

## Hata ve broker compromise modeli

| Olay | Karar | Yeniden açma şartı |
|---|---|---|
| Agent UID frame'de operator principal iddia ediyor | `rejected`, dispatch yok, source `unknown` | Agent UID map'te signer değilse retry ile düzelmez. |
| UDS peer UID expected signer UID değil | Frame içeriğine güvenmeden hemen ret | Root-owned map/revision ve ayrı UID host kabulü. |
| HMAC principal, UID map veya key record uyuşmuyor | Ret; frame `kimden` alanı kullanılmaz | Yetkili mapping/enrollment readback. |
| Wrong audience, route/alias/query, scope veya body alanı | Ret; nonce başarılı HMAC sonrası tüketilmiş olabilir | Yeni, exact-scope typed request ve idempotency kararı. |
| Auth store/nonce persistence `CommitUnknown`, clock veya storage unavailable | `unknown`, dispatch yok; consumer closed | Store dışı audit/readback ve lifecycle owner kararı; kör retry yok. |
| Broker crash/compromise veya verifier store okuma şüphesi | Operator channel'ı durdur; `operator` label'ı kapat; HMAC shared key compromise kabul et | Broker/signing süreçlerini izole et, offline revoke/reprovision, key ID/secret yenile, dış bağımsız readback ve host UID/release kabulü. |
| Signer compromise / raw key agent'a ulaştı | İlgili key/issuer compromise; signer erişimini kapat ve revoke et | Yeni key, yeni custody doğrulaması, eski key rejection kanıtı. |
| Root/host compromise ya da agent signer UID'sinde çalışıyor | Bu mimari sınır kanıtlanamaz | Temiz host/UID separation sonrası yeniden provision; aksi halde NO-GO. |

HMAC shared secret'ı signer ve broker'da bulunduğundan broker compromise sadece availability değil authenticity kaybıdır: broker sahte imza oluşturabilir ve operator source üretebilir. HMAC imzası üçüncü tarafa karşı imzalayanı inkâr edilemez biçimde kanıtlamaz. Root/host admin iki UID, mapping, key ve binary'yi etkileyebilirse OS sınırı da kök admin'e karşı koruma iddia etmez.

## Sentetik fixture kapsamı

`prototypes/operator-broker-uds/fixture.py` uzunluk çerçevesi, strict alan allowlist'i, kernel UID'nin frame dışında tutulması, peer/principal/key/audience binding'i, exact route, injected signature sonucu, nonce ilk kullanım/replay, nonce `unknown`, custody ve duplicate/extra field retlerini bellek içinde modeller. Agent'ın operator claim'i ret alır. Fixture `signature_verdict` değerini sentetik test girdisi olarak enjekte eder; HMAC hesaplamaz, `SO_PEERCRED` çağırmaz, numeric OS UID veya socket açmaz. O nedenle kriptografik, Linux kernel veya gerçek multi-UID kabul testi değildir.

Çalıştırma:

```sh
python3 prototypes/operator-broker-uds/fixture.py
```

Linux kernel peer-credential davranışı için #615'te ayrı geçici UDS fixture'ı
eklendi: [`docs/operator-broker-peercred-fixture-615.md`](operator-broker-peercred-fixture-615.md).
Bu fixture mevcut UID'yi doğrular ve frame UID spoof girişimini reddeder;
farklı gerçek OS UID'lerini veya üretim broker custody'sini kabul etmez.

## Yayına geçiş kapıları

1. Signer, broker/verifier ve her agent için ayrı, gerçek OS UID; root-owned unique UID→principal map; owner-only key/store; grup/socket izinleri hostta doğrulanmalı.
2. Signer yalnız doğrulanmış operatör session/intent almalı; agent signer socket/API'sine erişememeli. `SO_PEERCRED` doğrulaması iki farklı gerçek UID ile host testi görmeli.
3. Auth key lifecycle/provision/revoke aracı, audience/scope mapping, `operator_custody_verified` revision, `CommitUnknown` readback ve external restore/rollback anchor kabul edilmeli. Mevcut kaynaklarda lifecycle aracı yoktur.
4. Broker'ın exact allowlist'i, imza verify/nonce tek tüketim noktası, internal writer dispatch'i, hata/unknown/idempotency ve safe response sınırları ayrı kod incelemesi ve kabul fixture'larından geçmeli.
5. Broker compromise runbook'u, signer/broker restart, revoke, restore, stale UID mapping ve legacy direct HTTP bypass kapanışı doğrulanmalı. Bu adımlar yapılana kadar auth açılmaz.

## Dayanak

- `docs/operator-hmac-custody-decision-582.md` — ayrı UID signer/broker hedefi ve same-UID NO-GO.
- `docs/hmac-client-signing-contract-448.md`, `panel/auth.py` — HMAC v1 canonical bytes, timestamp, nonce ve scope.
- `panel/auth_integration_draft.py` — exact POST policy ve `principal_actor`/custody sınıflandırması.
- `docs/agent-uid-host-operations-523.md`, `docs/w1b-broker-principal-granularity-513.md`, `docs/cli-session-key-storage-boundary-573.md` — UID peer, signer key custody ve host sınırı.
- `docs/auth-key-rotation-revoke-offline-501.md`, `docs/auth-state-v2-operations.md` — revoke, `CommitUnknown`, store ve restore sınırları.

Bu teslim socket, UID, key, service, auth flag, credential store, route veya canlı state değiştirmez; gerçek operator custody veya `SO_PEERCRED` doğrulaması yaptığı iddiasında değildir.
