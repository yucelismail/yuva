# Codex adapter receipt prototipleri: birleşik entegrasyon sözleşmesi

Bu #418 için salt-okunur sentezdir. #396, #401, #402, #404, #408, #410 ve
#411 çıktılarındaki kimlik, attempt, korelasyon, reconnect, duplicate ve terminal
kararlarını birleştirir. #416'daki gizlilik incelemesi de saklama ve artifact
kapılarına girdi sağlar. Bu belge üretim entegrasyonu, runtime veya test
eklemez; aşağıdaki akış öneridir, mevcut sistem davranışı değildir.

## Ortak nesne modeli

Tek bir status alanı Yuva mesajının kaydını, socket yazımını, Codex turn'ünü,
çıktı teslimini ve reviewer kararını birbirine karıştırır. Kalıcı model bu
yaşam döngülerini ayrı tutmalıdır:

| Katman | Kimlik | Önerilen değerler | Ne kanıtlar |
|---|---|---|---|
| Yuva ingress | yuva_message_id (namespace + JSON türünü koruyan ID) | recorded, unavailable | Mesaj Yuva'da kaydedildi. Codex'e gönderim değildir. |
| Mantıksal operation | operation_id (Yuva mesajından türetilir) | sabit kimlik | Tek kullanıcı/başdenetçi mesajının gönderim ve uzlaştırma kaydı. Yeniden ingest aynı operation'ı bulur. |
| Orkestrasyon attempt | attempt_id, run_id, task_id (task varsa) | yeni, açık attempt başına yeni ID | Bir operation için hangi bilinçli yürütme denemesinin yapıldığı. Eski attempt silinmez veya yeniden yazılmaz. |
| JSON-RPC yazımı | (connection_generation, direction, typed_request_id) | not_started, write_started, not_sent_proven, sent_observed, unknown | Yerel taşıma gözlemi. sent_observed app-server kabulü değildir. |
| Turn receipt | operation + attempt + thread_id + turn_id | unknown, accepted, running, completed; ayrıca terminal_outcome | App-server turn kabulü/başlangıcı/terminal olayı için protokol kanıtı. |
| Çıktı teslimi | operation + attempt + item/artifact ID/digest | not_recorded, recorded, unknown | Codex çıktısının Yuva'ya/artifact store'a kalıcı kaydı. |
| Approval | (generation, direction, typed_request_id) ve thread/turn/item | pending, pending_unknown, response_observed | Sunucu onay isteği ve varsa haricen gözlenen cevabı. Prototip cevap göndermez. |
| Yuva review | Yuva task ID / Yuva denetim olayı | assigned, pending_verification, verified, pending_revision | Yalnız Yuva görev/reviewer iş akışı. Codex receipt bu alanı değiştirmez. |

Yuva'da task yoksa task_id/run_id/attempt_id varmış gibi üretilip Yuva görevi
iddia edilmez; adaptör yerel konuşma/operation scope'u kullanır. Task/run/attempt
kimliğinin hangi bileşen tarafından verileceği entegrasyon öncesi sabitlenmelidir.

## Normatif korelasyon ve retry kuralları

1. **Operation kimliği:** Aynı Yuva mesajı yeniden işlendiğinde aynı
   operation_id bulunur; method ve redacted params fingerprint'i eşleşmiyorsa
   operation_conflict oluşur ve dış gönderim durur. Operation bir attempt'in
   kendisi değildir.
2. **Attempt ile request ayrımı:** Yeni, bilinçli orkestrasyon denemesi yeni
   attempt_id ve yeni JSON-RPC request ID alır. Yalnız adapter'ın bu aynı
   frame için kesin 0 byte yazıldığını gözlediği taşıma retry'si aynı attempt
   ve aynı request ID ile tekrar hazırlanabilir; bu semantik olarak yeni attempt
   değildir. Kısmi write, tam write sonrası kayıp cevap, flush belirsizliği,
   timeout veya restart unknown olur; otomatik retry yasaktır.
3. **Bağlantı kapsamı:** Her bağlantı/process generation yeni ve kalıcı bir
   generation_id alır. Request/response, generation + yön + JSON türü
   korunmuş ID üzerinden eşleşir. Aynı generation içinde request ID'nin başka
   request'e tekrar verilmesi reddedilir. Yeni generation'da aynı sayı/metin ID
   görülebilir; bu önceki attempt'i çözmez ve tek başına resend izni vermez.
4. **Thread ve turn:** thread/start ve thread/resume yalnız session context
   kurar. Turn kabulü yalnız aynı generation'da tekil turn/start cevabından;
   çalışma turn/started event'inden; terminal sonuç aynı thread/turn için
   korele edilmiş turn/completed event'inden gelir. Orphan/ambiguous event
   saklanır, state unknown kalır.
5. **Event dedupe:** Protokol/kaynak kararlı event ID veriyorsa
   (event_namespace, source_event_id) + canonical fingerprint kullanılır.
   Aynı kimlik/fingerprint duplicate olabilir; aynı kimlik/farklı fingerprint
   conflict'tir. Kararlı event ID yoksa fingerprint tek başına event kimliği
   değildir: replay adayı olarak kaydedilir ve türetilmiş state idempotent
   güncellenir; farklı payload'lar sessizce ezilmez.
6. **Terminal çelişki:** Aynı turn için farklı terminal outcome veya aynı
   attempt'e çelişen thread/turn bağı varsa kanıtlar append-only kalır, turn
   receipt unknown/conflict olur. Son gelen event kazanmaz.
7. **Yuva review ve çıktı:** Codex turn'ünün terminal kanıtı, Yuva'ya çıktı
   kaydını veya reviewer kararını kanıtlamaz. completed protokol turn state'i
   ile output_delivery=recorded ayrı alanlardır. Kullanıcıya teslim tamam demek
   için ilgili Yuva/artifact write makbuzu gerekir; reviewer verified bundan da
   ayrıdır.
8. **Approval:** Approval request'i ayrı ID/nesne olarak pending'e alınır.
   Kopma/restart sonrası pending_unknown olur. Gözlenen client response
   kararı kanıtlayabilir ama otomatik cevap/karar üretilemez; approval sonucu
   turn terminal sonucu sayılmaz.

Önerilen state türetimi:

    Yuva message recorded
      → operation + attempt prepared
      → write_started
          ├─ proven 0 bytes → not_sent_proven (aynı attempt'te taşıma retry'si mümkün)
          ├─ uncertain/partial/lost → unknown (reconcile-only)
          └─ full frame + flush observed → sent_observed
                 ├─ correlated turn/start success → accepted
                 ├─ correlated turn/started → running
                 └─ correlated turn/completed → completed + terminal_outcome

    Codex terminal ≠ output recorded ≠ Yuva verified

## Mevcut çıktılardaki çelişkiler ve uzlaştırma

| Konu | Çıktılardaki fark | Birleştirilmiş karar |
|---|---|---|
| operation_id ve attempt kardinalitesi | #402 operation içinde attempt sayacı tutuyor. #408 SQL'de operations.operation_id primary key iken aynı satıra tek attempt_id, request/thread/turn alanı koyuyor; metinde ise yeni attempt açıp eskisini korumak isteniyor. | operations Yuva message ID başına bir satır; ayrı attempts tablosu operation başına çok satır taşımalı. Request ID ve thread/turn bağları attempt tablosunda tutulmalı. UNIQUE(task_id, run_id, attempt_id) attempt katmanında uygulanmalı. |
| Gönderildi | #401 yalnız tam frame + flush sonrası sent der. #402 byte yazım sonucunu taşır. #408 önceden write_started kalıcılaştırır. #410 dört turn receipt state'ine odaklanır. | Transport/write state ayrı tutulmalı. Tam yazım sent_observed demektir; Codex kabulü değildir. Yalnız kesin sıfır byte aynı attempt'in taşıma retry'sine izin verir. |
| Tamamlandı | #401 Codex terminal event yanında son çıktı/artifact'in Yuva'ya yazılmasını da tamamlanmış receipt için ister. #410 completed'ı korele edilmiş Codex terminal event olarak kullanır. | İki ayrı alan: turn_state=completed + terminal_outcome, ve output_delivery=recorded/unknown. Kullanıcıya teslim edildi demek için ilgili Yuva/artifact write makbuzu gerekir; reviewer verified bundan da ayrıdır. |
| Error response / reddedildi | #401 method/request'e bağlı error response'u rejected adlandırır. #402 şemaya uyan error'u rejected yapar. #410 genel receipt'i unknown tutup request_rejected kanıtını ayırır. #408 durum CHECK listesinde rejected yok. | JSON-RPC response error'ı rpc_outcome=error kanıtıdır. Şema/method semantiği bu kodun turn yaratmadığını açıkça garanti etmiyorsa turn state unknown kalır. Güvenilir method-specific ret varsa request_outcome=rejected yazılabilir; bunu Codex terminal failed veya Yuva iş reddiyle birleştirme. Protokol error-code eşlemesi ayrıca doğrulanmalı. |
| Request ID kapsamı | #396 adapter request map'i bellek içinde ID ile tutar. #402 tek request map'i, #404 generation-aware eşleme ve ID çakışmasını ele alır. | Production sözleşmesi #404'ün (generation, direction, typed ID) sınırını izler. #396/#402 bellek içi map'leri tek başına production korelasyon için yeterli değil. |
| Duplicate event | #410 kesin duplicate için güçlü event kimliği veya aynı source record ister. #411 canonical fingerprint'i içerik özeti sayar, kararlı event ID yoksa replay adayını saklar. | Fingerprint payload eşitliğini gösterir, uzak event kimliğini değil. Stable source ID yoksa gözlem saklanır ve reducer idempotent olur; cross-generation hash eşleşmesi tek başına birleştirilmez. |
| Terminal outcome | #402 completed, failed, interrupted değerlerini state olarak taşır. #410 receipt state'i completed altında outcome'a ayırır. #408 SQL state listesinde failed/cancelled bulunur. | Tek state sözlüğü kullan: turn_state için unknown/accepted/running/completed; terminal_outcome için şemada görülen exact değerler allowlist edilir. cancelled yalnız protokolde kanıtı ve anlamı varsa eklenir; request error'u turn outcome değildir. |
| Yuva mesajı ve Yuva task | #401 Yuva mesaj kaydının Codex'e gittiğini kanıtlamadığını söyler; #408 operation ID'yi message ID'den türetir ve task/run/attempt alanlarını bekler. | Message ingress makbuzu, operation, varsa task/run/attempt ve Codex transport birbirine ayrı bağlanır. Task olmayan sohbet mesajına sahte task receipt yazılmaz. |
| Reconnect/restart | #396/#402 yalnız in-memory; #404 unknown/pending_unknown; #408 persistent ledger ve reconcile önerir. | Production önkoşulu kalıcı transaction + generation kaydıdır. Restart sırasında terminal kanıtı olmayan write_started/accepted/running unknown; eski ID ile otomatik tekrar yok. |
| Approval | #401 response gözlenirse karar kaydetmeyi önerir; #402 writer/auto-decision içermez; #404 duplicate generation ID'yi belirsiz bırakır. | Server request, client response ve resolution ayrı observed event'lerdir. Yalnız exact generation ID eşleşmesi ve gerçekten gözlenmiş response kararı kaydeder. serverRequest/resolved karar içermiyorsa unknown; otomatik cevap yok. |

## Karar bekleyen ürün/protokol noktaları

1. **Yuva kimliği üretimi:** run_id ve attempt_id hangi güvenilir Yuva
   bileşeninden gelecek? Sohbet mesajı için task/run yoksa yerel operation
   scope'unun kalıcı kimlik formatı ne olacak?
2. **Yeni attempt yetkisi:** unknown uzlaştırılamadığında kim, hangi kanıtla
   aynı mesaj için yeni attempt açabilir? Öneri: açık operator/orchestrator
   kararı ve gerekçesi; yeni attempt ID ve yeni request ID.
3. **Codex protocol error semantiği:** Hangi turn/start error code'ları
   garantili turn yaratılmadı anlamına gelir? Kod/metin eşlemesi kanıtlanana
   kadar genel hata rpc_outcome=error, turn unknown olmalı.
4. **Terminalin kapsamı:** Kullanıcıya gösterilen tamamlanma, sadece Codex turn
   terminali mi, yoksa Yuva output/artifact kayıt makbuzu da mı gerektiriyor?
   Öneri: iki receipt ayrı; birleşik teslim tamam için ikisi de gerekli.
5. **Reconciliation kabiliyeti:** App-server hangi methodlarla thread/turn
   durumunu sorgulayabilir, history'den hangi kanıt alınabilir ve bunlar
   sürümler arasında ne kadar kararlı? Kabiliyet yoksa unknown için insan
   incelemesi gerekir.
6. **Event kimliği/sırası:** Protokol kararlı event ID, sequence veya revision
   sağlıyor mu? Yoksa cross-connection replay duplicate kesinliği vermez; yalnız
   gözlem + idempotent reducer uygulanır.
7. **Retention/privacy:** Raw prompt/output, HMAC/fingerprint, tombstone ve
   artifact için saklama süreleri, silme kapsamı, unknown escalation SLA'sı ve
   aynı UID güven sınırı kim tarafından onaylanacak? #416 riskleri kapatılmadan
   hassas payload kalıcılaştırılmamalı.
8. **Approval sahipliği:** Approval kararını kullanıcı/operatör nerede verir,
   onay response'unu hangi yetkili bileşen yazar, response kaybı nasıl
   uzlaştırılır? Mevcut prototipler bu işlemi gerçekleştirmez.

## Minimum uygulama sırası

1. #391 şemasına göre method/event/status alanlarını ve protokol error
   semantiğini sürümleyerek sabitle; yukarıdaki kimlik, receipt katmanları ve
   ürün kararlarını onayla. Henüz Codex'e bağlanma.
2. #408 SQL'i operation/attempt ayrımına göre düzelt; generation, observation,
   approval, artifact metadata ve migration sözleşmesini tasarla. Transaction,
   crash recovery ve backup/permission modelini belirle.
3. #411 dedupe/replay ilkelerini ve #416 privacy/path/cleanup kapılarını
   uygulamaya dahil et: canonicalizer sürümü, güvenli artifact root, içerik
   minimizasyonu, byte/disk limitleri, TTL ve unknown retention/escalation.
4. Önce pure reducer ve kalıcı ledger unit/transaction testleri yaz: aynı
   operation ingest, zero-byte retry, duplicate/conflicting event, restart,
   cross-generation response, disk-full, çelişkili terminal ve artifact
   rename/DB commit arası crash. Üretim taşımayı başlatmadan bu kapılar geçmeli.
5. Adapter'ı kalıcı ledger'a bağla; her dış write öncesi transaction commit
   et. In-memory #396/#402/#404 sketch'lerini authoritative state kaynağı
   sayma. Feature-off/opt-in modda yalnız fixture/captured trace ile gözlemle.
6. Read-only reconciliation ve operator conflict queue'su ekle; retry/approval
   response writer eklemeden önce ayrı yetki, kullanıcı deneyimi, auth ve
   audit incelemesi yap.
7. Yuva output/artifact write makbuzlarını output_delivery alanına ekle;
   Codex turn completion ile birleştirme. Yuva task state ve reviewer
   verified alanları ayrı yetki akışında kalsın.
8. Önceki kapılar ve privacy/security incelemeleri kapandıktan sonra dar
   production rollout planı, rollback/kill switch ve gözlemlenebilir unknown
   metriği hazırla. Exactly-once veya remote execution garantisi sunma.

Bu sıra yeni uygulama talimatı değil; üretim uygulamasından önceki en küçük
bağımlılık sırasıdır. #396/#402/#404 prototipleri gözlem/öğrenme artefaktlarıdır;
#408/#410/#411/#416 karar metinleriyle tutarlı hale getirilmeden production'a
import edilmemelidir.
