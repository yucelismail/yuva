# #527 — Kalıcı session receipt ve uzlaştırma sözleşmesi

## Durum ve sınır

Bu not #410/#411 Codex olay sırası ve dedupe kararlarını, #489 provider/Yuva
korelasyonunu, #504 kalıcı store önerisini ve #505 OpenCode olay eşlemesini tek
receipt sözleşmesinde birleştirir. `prototypes/session-bridge/outbox.py`
bellek içi taslaktır; bu belge kalıcı store, provider bağlantısı, Yuva değişikliği
veya exactly-once teslim uygulamaz. Kod, provider, credential, test ve runtime
değiştirilmedi/çalıştırılmadı.

Kalıcı store için tek bir transactional backend (ör. ayrı SQLite DB) adaydır,
seçim değildir. Provider'ın idempotency/replay garantileri ve OpenCode hedef
`/doc` şeması doğrulanmış kabul edilmez. Yuva görev durumu yalnız Yuva'nın kendi
kanonik görev akışından gelir.

## Kimlik ve kanıt katmanları

Her ID yalnız tanımladığı katmanda benzersizdir; katmanlar birbirinin teslim,
başarı veya yetki kanıtı sayılmaz.

| Katman | Kalıcı kimlik | Kanıtladığı | Kanıtlamadığı |
|---|---|---|---|
| Yuva ingress | `(yuva_instance, typed_yuva_message_id)` | Kaynak mesaj Yuva'da kaydedildi | Provider'a gönderildiğini veya bir turn başlatıldığını |
| Mantıksal operation | `operation_id`, ingress ID'ye bağlı; immutable `request_digest` | Aynı kaynak isteğin tekrar işlenmesinin aynı operation'a bağlandığını | Yeni bir bilinçli deneme veya dış etkiyi |
| Attempt | Her bilinçli provider gönderim kararı için benzersiz `attempt_id`; gerekiyorsa `task_id/run_id` | Bu operation altında belirli bir gönderim niyetini | Transport'ın veya provider'ın isteği aldığına dair kanıtı |
| Bağlantı nesli | `provider_instance + connection_generation` | Yerel request ID'lerin hangi bağlantı alanına ait olduğunu | Provider tarafında idempotency'yi |
| Codex request/turn/item | Typed JSON-RPC request ID + direction + generation; sonra `thread_id/turn_id/item_id` | Response/event'in tekil request veya turn'e bağını | JSON-RPC ID'nin uzak idempotency key olduğunu |
| OpenCode session/message/part/event | Provider instance/endpoint + `session_id`; varsa şemada doğrulanmış `messageID/partID/event ID` | Gözlenen nesnenin provider session içindeki bağını | `messageID`'nin dedupe key, event sequence veya eksiksiz replay cursor garantisi olduğunu |
| Output receipt | `(operation_id, attempt_id, provider object IDs, Yuva artifact/message ID + digest)` | Çıktının Yuva/artifact store'a kalıcı kaydını | Provider terminal başarısını veya reviewer onayını |
| Yuva task/review | Kanonik `task_id` ve Yuva görev geçmişi | `pending_verification`, `verified` veya `pending_revision` gibi Yuva kararı | Provider event'inin bu durumu kendiliğinden yazmasını |

Yuva message ID, provider message ID ve Yuva output message/artifact ID ayrı
alanlardır. OpenCode `user`/`assistant` role'u Yuva `kimden`/actor değildir.
Task/run bağı yoksa uydurulmaz; varsa güvenilir orchestrator kurar. Provider
çıktısı veya terminal event'i tek başına Yuva teslimi ya da onayı değildir.

## Kalıcı transaction ve gönderim sözleşmesi

1. **Ingress'i kaydet:** Tek transaction içinde source ID, operation ID,
   canonical/redacted request digest'i ve `prepared` kaydı commit edilir.
   Aynı source ID + aynı digest tekrar ingest edilirse mevcut operation'a
   bağlanır. Aynı source ID + farklı digest `operation_conflict` olur; yeni
   attempt veya provider çağrısı açılmaz.
2. **Attempt ve write intent'i kaydet:** Yeni bilinçli denemeye yeni
   `attempt_id` verilir. Provider kind/endpoint/session hedefi, bağlantı nesli,
   typed request ID ve `write_started` sınırı dış write'dan önce transaction'da
   kalıcılaştırılır. DB transaction açıkken ağ çağrısı yapılmaz. Intent commit
   sonucu belirsizse dış çağrı başlatılmaz; aynı operation/digest ile readback
   yapılmadan devam edilmez.
3. **Transport sonucunu ayrı yaz:** Yalnız kesin sıfır byte gönderim kanıtı
   `not_sent_proven` verir. Kısmi yazım, flush hatası, timeout, bağlantı kaybı,
   response kaybı veya süreç kesintisi `unknown`'dır. Aynı frame ve aynı
   operation/attempt içindeki transport retry ancak zero-byte kanıtıyla
   düşünülebilir; yeni bilinçli deneme yeni `attempt_id` alır ve eski kanıtı
   silmez. Provider desteklemiyorsa yeni denemenin uzak duplicate riski kalır.
4. **Provider gözlemlerini ekle:** Response/event önce append-only observation
   olarak saklanır; state izdüşümü aynı DB transaction'ında güncellenir.
   Kanıt; provider, generation, typed request ID veya doğrulanmış turn/session
   ID bağını taşımalıdır. Zayıf/eşleşmeyen observation orphan kalır ve
   `unknown`'ı başarıya yükseltmez.
5. **Çıktıyı teslim et:** Provider terminal sonucu ile Yuva output kaydı ayrı
   durumdur. Çıktı redaction/size policy'den geçtikten sonra Yuva/artifact
   kaydı yapılır; durable output receipt ancak hedef kayıt ve digest
   doğrulanınca `recorded` olur. Ekran/sohbet append'i provider event ID'si
   taşıyamıyorsa tek başına dedupe makbuzu değildir.
6. **Yuva task ve bildirim sınırını koru:** Task snapshot'ı, geçmiş olayı ve
   task notification outbox kaydı mümkünse Yuva'nın tek commit sınırında
   yazılır. JSONL teslimi ayrı bir durable adım ve event ID ile uzlaştırılır;
   append'ten sonra outbox güncellenmeden çökülürse JSONL readback yapılır.
   Kısmi/bozuk/okunamayan tail `delivery_unknown` olur; otomatik truncate veya
   yeniden append yoktur. Yuva `verified` yalnız reviewer'ın ayrı Yuva geçişiyle
   oluşur.

Kalıcı store tek-yazıcı varsayımına bağlanmamalı; state transition'ları expected
old state/CAS benzeri koşulla serialize edilmelidir. Store seçimi (SQLite dahil),
fsync/WAL, izinler, çoklu writer protokolü, yedekleme ve restore ayrı kabul
kapılarıdır. Bunlar kararlaştırılana kadar prototype kapasite ayarları kalıcı
retention veya dayanıklılık politikası sayılmaz.

## Dedupe anahtarları ve sıra çatışmaları

| Nesne | Önerilen korelasyon/dedupe anahtarı | Duplicate ve conflict kuralı |
|---|---|---|
| Yuva operation | `yuva_instance + typed_message_id`; yanında immutable request digest | Aynı ID/digest: mevcut operation. Aynı ID/farklı digest: conflict, gönderim yok. |
| Codex JSON-RPC request/response | `(provider_instance, connection_generation, direction, JSON-typed request_id)` | `7`, `"7"` ve `true` farklı JSON değerleridir; response yalnız aynı generation/yön/typed ID'deki tek request'e bağlanır. Aynı key/farklı response digest'i conflict'tir. |
| Codex turn/item | `(provider_instance, thread_id, turn_id)` ve item için buna `item_id` eklenir | Başka operation/attempt'e otomatik rebind yok. Aynı turn için çelişkili terminal outcome `unknown/conflict` olur. |
| OpenCode event | Kararlı provider event ID belgelenmişse `(provider, session, event_namespace, source_event_id)`; yoksa session/message/part/type + generation/capture position + fingerprint gözlem indeksidir | Sağlayıcı event ID/sequence/replay cursor garantisi doğrulanmadıkça composite key güçlü event kimliği değildir. Aynı fingerprint tek başına global dedupe yapmaz; reconnect gözlemi replay adayı olarak eklenir. |
| Yuva output/outbox event | Stable `yuva_event_id` + payload digest | Aynı ID/digest tekrar teslim/readback; aynı ID/farklı digest conflict. Yuva task commit'i output JSONL teslimini otomatik kanıtlamaz. |

Canonical payload fingerprint içerik eşitliğini gösterir, olay kimliğini değil.
Canonicalizer/redaction sürümü kaydedilir; eski digest yeni kuralla sessizce
yeniden hesaplanmaz. Ham prompt, credential, tool input/output veya hassas
provider body makbuza kopyalanmaz. Digest de hassas içeriğe eşleştirilebilir
bilgi sızdırabilir; erişimi kısıtlı ledger'da tutulur, Yuva ekran/sohbetine
yazılmaz.

Olay sırası varış zamanından türetilmez. Codex için terminal `turn/completed`
tekil thread/turn bağıyla `turn/started` öncesinde gelse bile terminal kanıt
olarak saklanabilir; sonradan gelen uyumlu `started` terminali geriletmez.
Yanıt/turn kimlik çakışması veya aynı turn için zıt terminal sonuç `unknown`
ve conflict üretir; iki gözlem korunur. OpenCode `received_seq` yalnız yerel
alım sırasıdır; provider sırası değildir. Message/part'ın değişen payload'ı
normal bir update olabilir; yalnız aynı güçlü event identity/protocol revision
altında farklı içerik conflict sayılır. SSE kopması aradaki event'lerin
eksiksizliğini kanıtlamaz.

## Durable state ve restart karar tablosu

| Son dayanıklı kayıt / gözlem | Restart sonrası görünüm | Otomatik yeniden gönderim | Uzlaştırma sonucu |
|---|---|---|---|
| `prepared`, write intent commit'i kesin | `prepared` | İlk dispatch yapılabilir; öncesinde intent kalıcılaştırılır | Provider çağrısı henüz başlamadığı kayıttan kanıtlanır |
| Write intent DB commit'i `commit_unknown` | `unknown`/commit unresolved | Hayır | Aynı operation ID ve digest ile durable readback; kayıt yok/bozuk/çelişkiliyse fail-closed, yeni ID ile devam yok |
| `write_started`, transport cevabı yok | `unknown`, son bilinen `write_started` korunur | Hayır | Provider'a gönderilmiş olabilir; provider status/history aynı operation'a güvenilir bağ kurarsa ilerlet; `not_found` tek başına negatif kanıt değildir |
| Kesin zero-byte kanıtı | `not_sent_proven` | Yalnız aynı operation'da açık transport retry veya açıkça yeni `attempt_id` kararı | Zero-byte kanıtı ve request digest saklanır; başka parametreyle retry conflict'tir |
| Korele provider accept/response | `accepted` | Hayır | Kabul, turn çalışıyor veya teslim edildi demek değildir; turn event/history beklenir |
| Korele `running`/busy gözlemi | `running`/busy | Hayır | Reconnect'te aynı provider session/thread/turn ile salt-okunur reconcile |
| Provider terminal olayı korele ve tekil | Provider `completed` + exact `completed/failed/interrupted` outcome | Hayır | Output Yuva'ya ayrıca teslim edilmelidir; Yuva task state değişmez |
| Provider event ID/payload çakışması veya bağ birden çok adaya uyuyor | `unknown/conflict` | Hayır | Tüm observation/digest'leri koru; operatör/reviewer uzlaştırması gerekir |
| Output dosyası/artifact kalıcı, DB receipt commit'i belirsiz | `output_delivery_unknown` | Körlemesine yeni artifact/message üretme yok | Artifact ID/digest veya Yuva message ID ile readback; eşleşme yokluğu tek başına silme/yeniden yazma izni değildir |
| Yuva task snapshot commit'i `commit_unknown` | `task_commit_unknown` | JSONL outbox bildirimi dispatch edilmez | Kanonik task kaydı + operation key ile readback; `verified` türetilmez |
| Yuva JSONL append oldu, outbox `delivered` commit'i belirsiz | `delivery_unknown` | Kör append yok | Tam arşivde event ID/digest readback; bounded UI tail dedupe kanıtı değildir. Kuyruk bozuk/eksikse operatör kontrollü kurtarma |
| Store okunamıyor, schema/izin/kilit/kapasite hatası veya transaction belirsiz | Ledger unavailable/unknown | Yeni provider dispatch kapalı | Store ve yedek salt okunur korunur; sessiz evict, fallback, DB reset veya otomatik tekrar yok |

`commit_unknown` dört ayrı sınırda görülebilir ve aynı anlama gelmez: local
receipt DB transaction'ı, provider transport write'ı, Yuva task snapshot commit'i
ve Yuva JSONL output/outbox teslimi. Her birinin ayrı `operation_id/event_id`,
readback kaynağı ve uzlaştırma kararı olmalıdır. Bir sınırın başarılı olması
diğerini kanıtlamaz. İki ayrı store arasında distributed atomic commit veya
provider+Yuva arasında exactly-once varsayılmaz.

## Retention, kapasite ve recovery

- `prepared`, `write_started`, `accepted`, `running`, `unknown/conflict`,
  unresolved approval/request ve dedupe tombstone'ları süre doldu diye silinmez.
  Terminal payload temizlense bile operation/attempt/provider ID bağları,
  terminal outcome, digest sürümü, evidence referansı ve conflict sonucu
  kompakt tombstone olarak korunur.
- Ham provider payload/delta ve büyük output için ayrı, kısa TTL ve byte
  bütçesi olabilir; redaction ve artifact retention farklı policy'dir. Payload
  temizliği operation ID, dedupe key veya unknown sonucunu silmez.
- Tombstone retention; aynı Yuva source message'ın yeniden ingest edilebileceği,
  provider'ın reconcile/history penceresi ve insan retry kararının bekleyebileceği
  süreden kısa olamaz. Bu süreler ürün/operatörce henüz belirlenmemiştir; ID
  yeniden kullanma ve unknown eviction kapalı kalır.
- Alan/record sınırı unresolved kayıtları atarak aşılmaz. Güvenli kompaksiyon
  yer açmıyorsa ingress/provider dispatch durur, kapasite hatası ve operator
  recovery görünür olur.
- Provider `not_found`, bounded history'de bulunmama veya SSE replay olmaması
  gönderilmediğini kanıtlamaz. Reconnect her zaman yeni generation alır;
  eski request ID yeni generation'da eski request'i çözmez. Bilinçli yeni
  attempt, eski unknown kaydını kapatmaz/silmez.

## Açık uygulama kararları

1. Kalıcı backend, schema/version migration, writer concurrency, WAL/fsync,
   ownership, backup/restore ve store failure alarmı.
2. Codex/OpenCode sürüm/protocol şeması, kararlı event ID/sequence/replay
   garantileri, provider idempotency ve authoritative status/history lookup.
3. Operation/attempt/event ID namespace'i, canonicalizer/redaction sürümü,
   same-source conflict sahibi ve unknown sonrası yeni attempt için onay sahibi.
4. Payload/artifact/receipt/tombstone retention ve kapasite dolduğunda
   kullanıcıya gösterilecek fail-closed davranış.
5. Yuva task snapshot + operation outbox atomikliği; JSONL append/readback,
   bozuk tail kurtarması ve legacy writer rollout'u.
6. Provider terminal receipt, Yuva output kayıt makbuzu ve Yuva task reviewer
   onayının arayüzde ayrı gösterimi.

Bu kapılar çözülmeden provider dispatch, otomatik retry, unresolved receipt
temizliği veya Yuva görevinin provider event'inden otomatik değiştirilmesi
uygulanmış/kabul edilmiş sayılmaz.

## Dayanaklar

- `prototypes/codex-app-server/receipt-event-order-matrix.md` (#410)
- `prototypes/codex-app-server/receipt-dedupe-retention.md` (#411)
- `docs/session-response-yuva-receipt-correlation-489.md`
- `docs/session-bridge-persistent-receipt-store-504.md`
- `docs/opencode-output-yuva-mapping-505.md`
- `prototypes/session-bridge/outbox.py` ve `prototypes/session-bridge/README.md` — memory-only outbox sınırı
- `prototypes/codex-app-server/receipt-ledger-design.md` ve `receipt-integration-contract.md` — Codex receipt model girdileri
