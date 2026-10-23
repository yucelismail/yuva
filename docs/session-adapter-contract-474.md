# Sağlayıcıdan bağımsız oturum adaptörü sözleşmesi

Bu #474 karar notu, Codex app-server prototipleri ve #472 OpenCode API
eşleştirmesi üzerinden ortak adaptör sınırını tarif eder. Üretim adaptörü,
dispatch, kalıcı receipt veya Yuva entegrasyonu değildir. Buradaki tipler
öneridir; repo içindeki prototipler çalışır entegrasyon garantisi vermez.

## Karar

Ortak adaptör, bir sağlayıcı oturumuna bağlanma, mesaj gönderme, durum/çıktı
gözlemi, approval gözlemi ve uzlaştırma işlemlerini sunar. Sağlayıcıya özgü
kimlikleri, olay gövdelerini ve semantiği kayıpsız ya da açıkça opak referanslar
olarak taşır. Yalnız ortak yaşam döngüsünün güvenle karşılaştırılabilen
parçaları normalize edilir.

Üç kanıt hattı ayrı kalır:

1. **Transport/send:** Yerel istek yazıldı mı, sağlayıcı kabulünü açıkça
   bildirdi mi?
2. **Provider session/turn:** Sağlayıcı işi çalıştırıyor mu, terminal duruma
   geldi mi?
3. **Yuva teslim/review:** Çıktı Yuva'ya kalıcı kaydedildi mi, Yuva görevi
   doğrulandı mı?

Bir hattın sonucu diğerinin yerine geçmez. Sağlayıcı `completed` olayı Yuva
mesaj teslimi veya reviewer `verified` kararı değildir.

## Asgari ortak veri tipleri

```text
SessionRef {
  provider: string                 # ör. codex-app-server, opencode
  provider_instance: string        # server/process/workspace namespace
  native_session: OpaqueRef        # sağlayıcının gerçek session/thread kimliği
  owner_binding: TrustedBinding?   # dış katmanca doğrulanmış Yuva principal/task
  workspace_binding: OpaqueRef?    # proje/dizin referansı; serbest ad iddiası değil
}

OpaqueRef {
  namespace: string                # ID türü ve sağlayıcı namespace'i
  value: string | integer | object # uygulama ID türünü ezmeden sakla
  generation: string?              # bağlantı/process nesli gerekiyorsa
}

OperationRef {
  operation_id: string             # mantıksal Yuva ingress/message ile kararlı bağ
  attempt_id: string                # bilinçli gönderim denemesi; her yeni denemede yeni
  source_message_ref: OpaqueRef?    # Yuva message/event kimliği ve türü
}
```

`SessionRef` sağlayıcı kimliğini tek bir `session_id` string'ine indirgemez.
Codex'te `thread_id`, `turn_id`, `item_id` ve JSON-RPC request ID farklı
kimliklerdir; `thread_id` session, turn/item ise yürütme kapsamıdır. OpenCode'da
session ID, message ID ve permission ID ayrı kapsam taşır. Her referans
`provider_instance` ve gerektiğinde `generation` ile eşleştirilir. Provider
ID'leri opaque saklanır; yalnız kayıpsız temsil edilebilen türler serialize
edilir.

`owner_binding` yalnız yetkili dış orkestratörün doğruladığı principal/task
bağıdır. Adapter, `kimden`, görünen ad, model çıktısı veya sağlayıcıya gönderilen
prompt içinden yetkili Yuva aktörü türetmez.

## Send receipt ve idempotency

```text
SendObservation {
  operation: OperationRef
  transport: not_started | write_started | not_sent_proven |
             sent_observed | unknown
  provider_outcome: not_observed | accepted | rejected | unknown
  provider_refs: OpaqueRef[]
  evidence: EvidenceRef[]
  observed_at: timestamp
}
```

- `sent_observed` yalnız taşımanın yerel yazım kanıtıdır; provider kabulü
  değildir. `accepted` için sağlayıcıdan operation/attempt ile tekil eşleşen
  açık kabul kanıtı gerekir.
- `rejected` yalnız doğrulanmış protokol semantiği isteğin iş başlatmadığını
  garanti ediyorsa verilebilir. Genel RPC/HTTP hatası veya timeout turn
  başlamadı kanıtı sayılmaz; `unknown` kalır.
- Aynı `operation_id` ve aynı payload parmak izi yeniden ingest edilirse aynı
  mantıksal operation bulunur. Farklı payload aynı operation ile gelirse
  `operation_conflict` ve gönderim durur.
- JSON-RPC request ID, OpenCode message ID veya HTTP 204 tek başına uzak
  idempotency garantisi değildir. Sağlayıcı özelinde belgelenmiş idempotency
  kanıtı yoksa sadece yerel tekrarları engelle; belirsiz dış sonucu tekrar
  gönderme.
- Yalnız kesin sıfır-byte yazım kanıtı aynı attempt ve aynı taşıma isteği için
  retry adayı olabilir. Kısmi yazım, tam yazım sonrası yanıt kaybı, timeout,
  flush belirsizliği veya restart `unknown` üretir. Yeniden deneme kararı ayrı
  ve açık bir yeni attempt'tir; önce salt-okunur uzlaştırma yapılır.

Operation/attempt, provider turn ve Yuva output receipt farklı kayıtlar olarak
tutulur. Yuva task/run/attempt yoksa sahte Yuva kimliği üretilmez; yerel
conversation scope kullanılır.

## Durum ve çıktı olayları

Ortak durum görünümü:

```text
SessionObservation {
  session: SessionRef
  activity: unknown | idle | busy | waiting_approval
  provider_status: OpaqueRef?       # kaynak status'u kayıpsız sakla
  evidence: EvidenceRef[]
  observed_at: timestamp
}

OutputEvent {
  session: SessionRef
  operation: OperationRef?
  source_event: OpaqueRef?          # yoksa kararlı event ID uydurma
  kind: text_delta | message | tool | diff | status | error | unknown
  payload: ProviderPayloadRef       # ham/provider-özel şema ortak tipe ezilmez
  sequence: string | integer?       # yalnız sağlayıcı veriyorsa
  observed_at: timestamp
}
```

`activity` karşılaştırılabilir bir görünüm sağlar, `provider_status` ise
sağlayıcının özgün değerini korur. Terminal turn sonucu ayrıca
`completed | failed | interrupted | unknown` ve sağlayıcıya özgü terminal
outcome olarak tutulur; `idle` terminal başarı demek değildir. Bağlantı
kesilmesi, boş event kuyruğu veya event gelmemesi `idle` kanıtı değildir.

Output event'lerinde kaynak kararlı event ID/sequence sunmuyorsa fingerprint
yalnız içerik eşitliği gösterebilir; uzak event kimliği veya replay kanıtı
değildir. Duplicate event state reducer'ı idempotent olmalı; aynı kimlik/farklı
payload çakışma üretmeli. Kimliği veya operation bağı kurulamayan event
`unknown`/orphan kalır. Model çıktısı, hata metni, diff veya tool argümanı tek
başına Yuva talimatı, komut ya da approval kararı sayılmaz.

## Approval sınırı

```text
ApprovalObservation {
  session: SessionRef
  operation: OperationRef?
  request: OpaqueRef                 # sağlayıcı request ID + generation
  state: pending | response_observed | resolved | pending_unknown | unknown
  decision: OpaqueRef?               # yalnız gerçekten gözlenen kesin yanıt
  evidence: EvidenceRef[]
}
```

Approval/interaction, genel session `busy` durumundan ayrı nesnedir. Adapter
approval beklemesini gösterebilir ve sağlayıcının cevap verdiğine dair gözlemi
kaydedebilir; yetkili kullanıcı kararını kendisi üretemez. `resolved` olayı
kararı içermiyorsa karar `unknown` kalır. Bağlantı kopunca açık istek
`pending_unknown` olur; otomatik approve/reject, otomatik izin yükseltme veya
model metninden karar çıkarımı yoktur. Approval response yazma yeteneği ayrı
kapability ve yetkilendirme kapısıdır; ilk adaptör için varsayılan
observe-only olmalıdır.

## Reconnect ve uzlaştırma

Her gerçek bağlantı/process nesli yeni `generation` alır. Eski neslin request
ID'si yeni nesilde yanıtla eşleştirilmez; eski pending send/approval sonuçları
kanıt gelene kadar `unknown` olur. Adapter şunları açıkça bildirir:

- event stream'in scope'u (instance, project, session),
- replay/cursor/sequence kabiliyeti ve cursor kapsamı,
- bağlantı açıldığında initial snapshot veya status sorgusu gerekip gerekmediği,
- REST/status/history sorgularının neyi kanıtladığı ve neleri kanıtlamadığı.

Reconnect akışı yeni prompt göndermeden önce salt-okunur `reconcile()` yapar:
provider status, session messages/history ve varsa cursor üzerinden olayları
toplar; her bulguyu eski operation/attempt'e yalnız tekil kimlik bağı varsa
bağlar. Stream replay garantisi yoksa event kaybı telafi edildi varsayılmaz.
Sonuç çözülemiyorsa `unknown` korunur; aynı operation körlemesine tekrar
gönderilmez.

Yuva receipt reducer'ı için event ingestion append-only gözlem olarak
tasarlanmalıdır. Yuva görev makinesi, provider event'inden `teslim edildi`,
`verified` veya `pending_revision` türetmez; task değişimi ve review kendi
yetkili Yuva akışında gerçekleşir.

## Capability beyanı

Capability, ortak arayüzde varsayılan mevcut metod gibi görünmemelidir. Adapter
bir `CapabilityReport` sunmalı; her yeteneği `supported`, `unsupported` veya
`unknown` olarak ve varsa API/protokol sürümü, kanıt kaynağı, sınırlama ile
bildirmelidir. Asgari capability adları:

| Capability | Açıklama |
|---|---|
| `attach_existing_session` / `create_session` | Oturuma bağlanma veya yeni oturum açma |
| `send_sync` / `send_async` | Senkron sonuç ya da asenkron admission |
| `list_messages` / `read_status` | Reconcile için salt-okunur kaynak |
| `events` / `event_replay` | Canlı event ve belgelenmiş replay/cursor |
| `observe_approval` / `respond_approval` | Approval gözlemi ve ayrı yanıt yazarı |
| `interrupt` | Çalışmayı durdurma; başarı ve terminal kanıtı ayrıca tanımlı |

Desteklenmeyen capability hata değildir ve sahte no-op ile örtülmez. Çağıran
önce raporu okur; unsupported işlem açık `unsupported_capability` sonucu
üretir. Capability değişimi yeni gözlem/versiyon kaydıdır.

## Prototiplere uygulama

| Ortak kavram | Codex app-server prototipi | OpenCode Server belgeleri |
|---|---|---|
| Session | `thread_id` | `session.id` |
| Work/turn | `turn_id`; item'lar `item_id` | Session mesajı ve status/event; API'de ortak Codex turn kimliği yok |
| Request/approval | JSON-RPC ID + connection generation; server request | HTTP/message ID ve permission ID; provider-specific namespace |
| Send | JSON-RPC frame yazım gözlemi ve korele yanıt | `/session/:id/message` veya `/prompt_async`; HTTP sonucu kendi başına Yuva receipt değildir |
| Busy/idle | thread/turn status/terminal notifications | `/session/status` ve `session.status`/`session.idle` olayları |
| Output | item/message/diff notifications | message/part event ve session history |
| Reconnect | prototip generation-aware; kalıcı ledger ve gerçek transport yok | `/event` stream; resmi dokümanda reconnect replay/cursor garantisi belirtilmiyor, REST reconciliation gerekir |
| Approval | prototip request'i gözler, response yazmaz | permission istek/cevap yolu belgeli; karar yetkisi adaptör dışı kalmalı |

OpenCode dokümantasyonu `opencode serve` API'sini, `/doc` OpenAPI şemasını,
session/status/message uçlarını ve `/event` SSE'yi tarif eder. Sunucu varsayılan
loopback'tedir; Basic Auth yapılandırılabilir. Sürüm-spesifik gerçek şema
entegrasyon öncesi hedef instance'ın `/doc` çıktısından doğrulanmalıdır.
Codex prototipi yalnız yakalanmış JSON-RPC gözlemini işler; canlı Codex'e
bağlanmaz ve Yuva state'i yazmaz. Bu sözleşme iki sağlayıcı için üretim
capability'si iddia etmez.

## Gerekli sonraki kapılar

1. Her provider/versiyon için opaque ID namespace'i, status/event semantiği ve
   terminal kanıtlarını resmi şema veya fixture ile doğrula.
2. Operation/attempt ve Yuva task/run bağının yetkili üreticisini; Yuva output
   receipt ve reviewer transition sınırını kararlaştır.
3. Durable receipt/outbox, dedupe retention, privacy/redaction, authentication
   ve approval owner sözleşmelerini ayrı tasarım ve review ile kapat.
4. Önce saf reducer ve fake adapter geçişleri doğrulansın; canlı taşıma ancak
   bu kapılar, ayrı approval kararı ve feature-off/kill-switch kabulünden sonra
   ele alınsın.

Bu belge mevcut davranışın veya güvenlik kontrolünün kanıtı değildir. #418
Codex receipt sözleşmesi, #421 Codex busy/idle tasarımı ve #472 OpenCode
araştırmasından türetilmiş bir arayüz önerisidir.
