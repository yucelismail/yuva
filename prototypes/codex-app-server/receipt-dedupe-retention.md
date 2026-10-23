# Receipt ledger dedupe anahtarı ve saklama sınırları

Bu #411 için salt-okunur tasarım notudur. #408'deki ledger şemasını ve
#410'daki event karar matrisini tamamlar; store, üretim entegrasyonu veya test
eklemez. Temel kural: dedupe, olayın kimliğini kanıtlamaz. Güçlü bir olay kimliği
yoksa olası tekrarlar gözlem olarak saklanır; belirsiz kayıt sessizce silinmez.

## Kimlik türlerini ayır

Birbirinden farklı dört anahtar vardır. Tek bir `id` veya yalnızca payload hash'i
üzerinden tüm nesneleri dedupe etmek yanlış eşleşme ve kanıt kaybı üretir.

| Kayıt | Kimlik / unique kapsamı | Aynı anahtar aynı içerik | Aynı anahtar farklı içerik |
|---|---|---|---|
| Yuva kaynak mesajı / mantıksal operation | `operation_id = source_namespace + canonical_yuva_message_id` | Aynı operation'ın tekrar ingest'i; mevcut satıra bağla, yeni turn/attempt açma | `operation_conflict`; iki parametre digest'ini sakla, gönderimi durdur |
| JSON-RPC request | `(generation_id, direction, canonical_jsonrpc_id)` | Request'in aynı capture kaynağından replay'i ise duplicate observation; yeni yazım başlatma | Aynı nesilde ID çakışması; `unknown`, gönderim/yanıt eşleştirmesi bloke |
| Codex turn | `(thread_id, turn_id)` | Aynı turn'e ait başka event/observation | İki operation/attempt aynı turn'e sahip çıkıyorsa `turn_binding_conflict`; ikisini otomatik birleştirme |
| Codex item | `(thread_id, turn_id, item_id)` | Aynı item'in aynı kaynak sürümü/olayı tekrarı | Aynı item/event kimliği farklı içerikle görünürse `item_conflict`; eski digest'i koru |
| Protocol event | Kararlı source event ID varsa `(event_namespace, source_event_id)`; yoksa aşağıdaki composite identity | Aynı kimlik ve aynı canonical fingerprint duplicate olabilir | Aynı kimlik, farklı fingerprint: conflict; son yazan kazanmaz |

`generation_id` her stdio/app-server bağlantı nesli için yeni ve kalıcıdır.
Request yönü (`client_to_server` / `server_to_client`) ve JSON ID türü anahtara
dahildir. Örneğin `7`, `"7"` ve `true` birbirinden farklı JSON değerleridir;
boolean JSON-RPC ID olarak reddedilmelidir. Aynı request ID'nin aynı nesilde
başka operation'a verilmesi, ilk request terminal olsa bile, ledger politikası
gereği yasaktır. Yeni bağlantı nesli yeni ID alanıdır; ancak eski belirsiz
operation'ı tekrar göndermek için aynı Yuva operation kimliğini kullanmak yine
de izin değildir.

## Canonical fingerprint

Fingerprint bir içerik özetidir, event kimliği değildir. Tekrarlanabilir olması
için her hash şu girdileri sabit bir sıralı zarf içinde kullanır:

```text
SHA-256(
  "yuva-codex-receipt:event:v1\\0" ||
  canonicalizer_version || 0x00 ||
  source_namespace || 0x00 ||
  canonical_json(event_identity) || 0x00 ||
  canonical_json(redacted_protocol_payload)
)
```

Canonicalization sözleşmesi sürümlenir: nesne anahtarları deterministik sırada
serileştirilir, UTF-8 kullanılır, JSON türleri korunur, string değerleri Unicode
normalizasyonuyla değiştirilmez, NaN/Infinity ve JSON dışı değerler reddedilir.
Parametrelerden değişken/gizli alanları çıkarmak gerekiyorsa redaction kuralı da
sürümlenir ve tam payload ayrıcalıklı depoda tutulur; dedupe digest'i redaction
sonrası byte'lar üzerinden hesaplanır. Eski kayıtlar yeni canonicalizer ile
sessizce yeniden hash edilmez. Sürüm geçişinde eski fingerprint saklanır ve yeni
özet yalnız açık migration sırasında eklenir.

Kararlı event ID bulunmuyorsa composite event identity alanları, olayın şema
semantiğine göre seçilir: `(source_namespace, thread_id, turn_id, item_id,
method, event_kind, state/status, varsa protocol revision)`. Bunlar yoksa
identity sadece `(generation_id, stream_position)` olabilir. Yalnızca
`(method, payload_hash)` global unique yapmak güvenli değildir: aynı görünür
payload meşru biçimde iki kez üretilebilir. Timestamp, yakınlık veya “bu turn'de
tek event beklenirdi” tahmini de kimlik yerine geçmez.

## Dedupe ve çakışma kararları

1. **Operation ingest:** `operation_id` unique. Aynı ID ve aynı method/params
   digest'i mevcut operation'a bağlanır. Aynı ID ve farklı digest conflict'tir;
   yeni attempt/turn başlatılmaz. Operatör kararı eski operation'ı değiştirmez,
   yeni `attempt_id` açar.
2. **Request/response korelasyonu:** Response yalnız aynı
   `(generation_id, direction, typed_request_id)` altında bir request'e
   bağlanır. Reconnect sonrası eşleşen ID yeni nesildeki response'un eski
   request'i çözmesine izin vermez. Aynı nesilde ikinci response aynı ID'yi
   kullanırsa, tam capture replay olduğu kanıtlanırsa duplicate; başka payload
   veya farklı correlated result varsa conflict ve receipt `unknown`.
3. **Turn/item bağı:** Turn ID başka operation'a zaten bağlıysa otomatik
   rebind yok. Item ID turn kapsamındadır. Aynı item için ayrı, geçerli
   incremental output eventleri hash'leri farklı diye conflict değildir; event
   türü/revision alanları ayrı olmalı. Çelişki yalnız aynı event identity ya da
   aynı protocol revision farklı canonical payload ile geldiğinde kurulur.
4. **Kararlı event ID mevcut:** Aynı source event ID + aynı fingerprint no-op
   duplicate'dir. Aynı source event ID + farklı fingerprint `event_conflict`
   üretir; iki gözlem korunur, derived state `unknown`/inceleme olur.
5. **Kararlı event ID yok:** Aynı nesil ve aynı capture kaynağında kalıcı
   `stream_position` ile aynı identity/fingerprint yinelenmişse tekrar ingest
   sayılabilir. Reconnect/replay farklı capture kaynağındaysa exact fingerprint
   eşleşmesi yalnız “replay adayı” işaretidir; yeni observation saklanır. Derived
   transition idempotent uygulanır; bu, iki gerçek aynı event'in kaybolmasını
   önler.
6. **Çelişkili terminal olaylar:** Aynı `(thread_id, turn_id)` için farklı
   terminal outcome'lar varsa her event ayrı tutulur, state `unknown` ve
   conflict reason `terminal_conflict` olur. Zaman damgası veya arrival order ile
   birini seçme.

Database unique constraint ihlali tek başına “duplicate” demek değildir.
Çatışma halinde önce kayıtlı key, canonicalizer sürümü ve fingerprint okunur;
tam eşitse dedupe, değilse conflict satırı/observation eklenir. Bu kontrol ile
karar aynı transaction'da yapılır.

## Saklama ve bounded retention

Sınırsız ham payload saklamak maliyet ve gizlilik riski taşır; yalnız zaman
geçti diye operation kimliklerini veya unresolved state'i silmek ise duplicate
turn açma riskidir. Saklamayı kanıt sınıfına göre ayır:

| Veri sınıfı | Saklama sınırı | Temizleme davranışı |
|---|---|---|
| `prepared`, `write_started`, `accepted`, `running`, `unknown` operation | Süreye bağlı TTL yok; açık uzlaştırma/operatör kapama kararı olmadan silinmez | Alan baskısında yeni dış gönderimi durdur; bu satırlara öncelikli/rezerv kapasite ayır |
| Çözümlenmemiş request/approval ve bağlantı nesli eşlemesi | Bağlı operation belirsiz kaldığı sürece tutulur | ID + generation tombstone en az operation saklama ömrü kadar kalır |
| Terminal receipt, operation/task/run/attempt bağı ve dedupe tombstone | Ürün saklama politikasına bağlı uzun retention; payload temizlense de tombstone/digest tutulur | Tombstone süresi, kaynak Yuva mesajı yeniden ingest edilebildiği veya operation yeniden açılabildiği süreden kısa olamaz |
| Ham JSON-RPC payload ve büyük delta/output | Kısa, ayarlanabilir TTL ve byte bütçesi | Önce ham payload/content çıkar; timestamp, scope, ID, canonicalizer version, fingerprint, outcome ve conflict işaretini koru |
| Artifact içeriği | Ayrı içerik saklama politikası ve immutable ref | DB reference silmeden önce yetim kontrolü; bağlı receipt'in artifact digest metadatasını koru |
| Bağlantı/raw transport logları | En kısa operasyonel TTL | Credential/prompt/output içerebilir; varsayılan kapalı veya redacted; backup kopyaları da aynı policy'ye tabi |

TTL, hem yaş hem toplam byte/item bütçesiyle uygulanabilir; ancak evict sırası
`raw payload → büyük output/delta → çözümlenmiş terminal payload` olmalıdır.
`unknown`, unresolved, conflict ve tombstone kayıtları otomatik yaş temizliğine
girmez. Uzun süre sonra operator tarafından çözülen terminal operation'ın ham
payload'ı silinse bile operation ID, task/run/attempt, thread/turn, request
generation/ID, son state, terminal outcome, fingerprint sürümleri ve artifact
digest bağı kompakt tombstone olarak kalır.

Üst sınır aşılıp güvenli kompaksiyon yer açamıyorsa davranış fail-closed'dur:
ingress/turn başlatma durur ve “ledger capacity exhausted” görünür; ledger
satırları sessizce atılmaz ve dış istek gönderilip receipt kaydı sonradan
denenmez. WAL checkpoint/vacuum bakım işidir; açık transaction, backup veya
recovery sırasında dosya elle budanmaz.

## Restart ve replay garantileri

Restart sırasında `write_started`, `accepted` ve `running` terminal kanıtı
yoksa `unknown` yapılır; `last_known_state`, operation ve tombstone kimlikleri
kalır. Eski bağlantı nesli kapalı işaretlenir. Yeniden oynatılan Yuva mesajı
aynı `operation_id` ile mevcut operation'a bağlanır ve yeni turn oluşturmaz.

Replay event'i kararlı event ID ile gelirse source ID/fingerprint üzerinden
dedupe edilir. Event ID yoksa eski capture'ın kalıcı kaynağı + stream offset'i
aynıysa tekrar ingest no-op olabilir. Yeni reconnect stream'inde yalnız aynı
payload fingerprint'inin görülmesi duplicate kesinliği vermez; observation
eklenir, state transition idempotent kalır ve birbiriyle çelişen kanıt
`unknown` üretir.

SQLite yazım/transaction başarısızsa aynı transaction'daki operation ve
observation birlikte görünür olmalı ya da hiç görünmemelidir. Ledger yazımı
doğrulanmadan dış yan etki başlatılmaz. Disk doluluğu/bozuk DB/lock timeout'ta
çözülmemiş işin kaydı silinmez; runtime yeni gönderimleri kapatır ve operatör
recovery ister. Bu not exactly-once veya cross-system atomiklik iddia etmez.

## Kabul ölçütleri

- Aynı Yuva message ID + aynı request içeriği tekrar ingest edilince ikinci
  operation/turn açılmaz; aynı ID + farklı içerik conflict olur.
- JSON-RPC ID türü, yönü ve connection generation korelasyon anahtarında
  korunur; başka neslin response'u eski request'i çözmez.
- Aynı event identity + fingerprint duplicate olabilir; aynı identity + farklı
  fingerprint conflict'tir; payload fingerprint tek başına global unique
  değildir.
- Turn/item ID başka operation'a otomatik taşınmaz; terminal çelişki `unknown`
  olur ve iki kanıt korunur.
- Restart sonrası çözülmemiş kayıtlar ve dedupe tombstone'ları TTL/bütçe nedeniyle
  silinmez. Payload temizliği kimlik ve conflict metadata'sını korur.
- Kapasite yetersizliğinde ingress/gönderim kapanır; receipt kaybı başarı veya
  retry izni sayılmaz.
