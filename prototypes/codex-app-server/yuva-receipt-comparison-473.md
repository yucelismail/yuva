# #473 — Codex app-server prototipleri ve Yuva receipt/task karşılaştırması

## Sonuç

Prototipler JSON-RPC gözlemini Yuva görevi veya teslim makbuzu saymamak,
belirsiz yazımı otomatik tekrar etmemek ve approval yanıtını kendiliğinden
üretmemek açısından doğru sınırlar çiziyor. Ancak adapter, reconnect ve
retry/approval ledger'ları ayrı, bellek içi taslaklar. Birlikte çalışan kalıcı
bir akış değiller ve Yuva task/mutation/outbox sözleşmesini uygulamıyorlar.

Önemli farklar: bazı ledger'lar genel JSON-RPC error'ını rejected sayıyor;
Yuva receipt sözleşmesi method-specific kanıt yoksa turn'ü unknown tutuyor.
Retry taslağı 0-byte retry'de attempt değerini artırıyor; ortak sözleşmede bu
aynı attempt'in transport retry'sidir. Çelişkili terminal turn olaylarında
retry ledger ilk terminal durumu koruyor; Yuva receipt tasarımı çatışmayı
unknown/conflict olarak görünür tutmayı istiyor.

Bu salt kaynak karşılaştırmasıdır. Prototipler veya canlı Codex/Yuva runtime'ı
çalıştırılmadı; herhangi bir bağlantı, turn, approval yanıtı ya da Yuva state
mutasyonu yapılmadı.

## Yuva tarafındaki karşılaştırma zemini

- Gerçek CLI task geçişleri pending/pending_revision → assigned →
  pending_verification → verified veya pending_revision olarak ayrıdır
  (bin/yuva:1979-1985, 2078-2085, 2131-2141, 2204-2214). Codex turn sonucu
  Yuva teslimi veya reviewer verified kararı değildir.
- #437 operation receipt + task mutation + outbox'ı aynı dayanıklı task
  snapshot'ına bağlayan tasarımdır, mevcut uygulama değildir.
  docs/task-mutation-failure-matrix-452.md ayrıca commit_unknown ile
  delivery_unknown ayrımını, timeout/response kaybında kör retry yapılmamasını
  ve outbox readback gereğini belirtir.
- Codex receipt için
  prototypes/codex-app-server/receipt-integration-contract.md operation,
  attempt, bağlantı nesli, typed request ID, thread/turn, çıktı teslimi ve
  Yuva review'ını ayrı katmanlar olarak tarif eder. Bu da tasarım
  sözleşmesidir; Yuva CLI'ye entegre edilmiş özellik değildir.

## Gözlenen akış ve mevcut kapsam

adapter.py bidirectional trace içindeki client thread/start, thread/resume,
turn/start ve diğer tanımlı çağrıları JSON-RPC ID ile beklemeye alır
(adapter.py:113-160). Eşleşen başarılı thread yanıtından thread.id,
turn yanıtından turn.id bağlar (162-212); turn/started ve turn/completed
bildirimlerinden kimlik/status projeksiyonu çıkarır (241-307). Bu bir receipt
state machine değildir: temel adapter her mesajı ayrı gözlem olarak verir.

retry_approval.py ayrı bir operation durum taslağı sunar: sıfır byte yazıldığı
açıkça kaydedilmedikçe reconcile_only, eşleşen turn start yanıtında accepted,
turn olayında running/terminal durum; approval request'ini saklar ve hiçbir
yanıt göndermez (retry_approval.py:82-160, 162-239, 241-307).
reconnect_state.py bağlantı neslini ayrıca tutar; kopmada açık işleri unknown,
approval'ları pending_unknown yapar ve yeni nesilde ID çakışmasını
uzlaştırmaya bırakır (reconnect_state.py:76-111, 113-168, 211-290).

Bu üç bileşen aynı process içinde ortak tek receipt üretmez. Adapter'da
generation yok; retry ledger request/approval map'lerinde generation yok;
generation'ı bilen reconnect ledger ise ayrı ve bellekte çalışır. README de
prototiplerin birbirine veya Yuva'ya entegre olmadığını ve kalıcılık
sağlamadığını açıkça söylüyor.

## Somut uyumsuzluklar ve boşluklar

| Önem | Bulgu | Yuva sözleşmesine etkisi |
|---|---|---|
| Yüksek | Genel RPC error rejected olarak yükseltiliyor. RetryApprovalLedger.record_response() ve ReconnectLedger.observe_response() şemaya uyan integer error code görünce request'i rejected yapıyor (retry_approval.py:172-182; reconnect_state.py:188-196). | JSON-RPC error yalnız RPC hata cevabının kanıtıdır. #418 sözleşmesi method-specific protokol semantiği “turn yaratılmadı” demedikçe rpc_outcome=error, turn unknown ister (receipt-integration-contract.md, “Error response / reddedildi”). Yuva task'ı da reddedilmiş sayılmaz. |
| Yüksek | Çelişkili terminal event ilk state'i koruyor. record_turn_event() completed/failed/interrupted/rejected state'ten sonra başka terminal event gelirse terminal_state_is_immutable döndürüp yeni kanıtı state'e/conflict kaydına yansıtmıyor (retry_approval.py:210-226). | Yuva receipt matrisinde aynı turn için zıt terminal outcome unknown + conflict olmalı; iki gözlem de korunmalı (receipt-event-order-matrix.md:40, 43). Son gelen kazanmasın kadar ilk gelen de sessizce kazanmış sayılmamalı. |
| Orta | Attempt kardinalitesi iki taslakta da ayrışıyor. retry() aynı operation ve request ID'yi koruyarak kesin 0-byte retry'de attempt += 1 yapıyor (retry_approval.py:113-134); reconnect ledger ise operation başına tek RequestRecord tutuyor ve ayrı attempt_id modellemiyor (reconnect_state.py:38-50, 131-168). | #418'de yalnız kesin 0-byte retry aynı attempt'in transport retry'sidir. Yeni bilinçli orchestrator denemesi yeni attempt_id ve yeni JSON-RPC ID alır; aynı Yuva mesajı/operation altında birden fazla attempt saklanabilmelidir. Prototip sayacı transport_write_attempt olarak ayrılmalı veya bu geçişte artırılmamalı; operation ile attempt kardinalitesi eklenmeli. |
| Orta | Retry ledger generation-aware değil. request_to_operation ve approval map'leri yalnız typed request ID ile anahtarlanıyor; approval response/resolution da yalnız ID ile aranıyor (retry_approval.py:77-80, 162-170, 241-304). | Aynı ID yeni bağlantı neslinde yeniden kullanılınca eski request/approval ile karışma riski var. reconnect_state.py bunu connection ID ile ayırıyor ve pending eski approval çakışmasını pending_unknown yapıyor; fakat bu ledger retry/adapter akışına bağlı değil. |
| Orta | Thread conflict cevabı kaydı unknown yapmıyor. record_turn_event() bilinen record.thread_id ile gelen thread ID uyuşmazsa yeni bir unknown dict döndürüyor, ama record.state eski accepted/running değerinde kalıyor (retry_approval.py:209-214). | Çağıran yalnız dönüş objesini loglayıp ledger'ı okursa çatışma kaybolur. Conflict gözlemi saklanmalı ve receipt izdüşümü unknown/conflict olmalı; güvenilir yeniden uzlaştırmaya kadar terminal/başarı sayılmamalı. |
| Orta | Adapter thread/turn map'leri connection generation kapsamı taşımıyor ve receipt reducer'a bağlı değil. outstanding, thread_context, turn_context, pending_server_requests düz ID map'leridir (adapter.py:104-111, 162-212, 214-307). | Yeniden bağlantı veya ID tekrar kullanımı için #418'in (generation, direction, typed ID) korelasyon kuralını tek başına karşılamaz. reconnect_state.py generation-aware olsa da adapter'a beslendiğine dair kod yok. Turn event'i ile task/run/attempt eşlemesi Yuva tarafından kanıtlanmış olmaz. |
| Yüksek | Restart/dayanıklılık/Yuva commit bağı yok. Bütün ledger'lar bellekte; ReconnectLedger.snapshot() yalnız JSON-compatible değer döndürür, dosyaya atomik yazmaz (reconnect_state.py:292-323). Adapter JSONL biçimindeki projeksiyonu stdout'a yazar; bu kendi başına kalıcı kayıt değildir ve Yuva task mutation ile ortak commit sınırında olamaz. | Process çökmesi, receipt kaydı kaybı ve Yuva task/outbox yazımının belirsizliğini çözmez. #437/#452 sözleşmesinde durable operation makbuzu, commit_unknown/delivery_unknown ayrımı ve event ID uzlaştırması gerekir. In-memory örneklerden exactly-once veya Yuva'ya teslim çıkarılamaz. |

## Korunması gereken doğru sınırlar

- Request ID string "1" ile integer 1 ayrımı _id_key() içinde korunuyor;
  generation ledger'ı stale connection response'unu yeni bağlantı kaydıyla
  eşleştirmiyor.
- Partial write, flush belirsizliği, yanıt kaybı ve disconnect otomatik resend
  yerine unknown/reconcile yönünde ele alınıyor. Yuva #452'nin kör retry
  yasağıyla uyumlu yön budur.
- serverRequest/resolved tek başına approval kararı sayılmıyor; gözlenen
  client response yoksa unknown korunuyor. Hiçbir modül approval yanıtı
  göndermiyor.
- README'de Codex completed, çıktı/artifact'in Yuva'ya kaydı ve Yuva reviewer
  verified kararı ayrı tutuluyor. Bu ayrım CLI task lifecycle'ıyla uyumludur.

## Entegrasyon için sonuç

Prototipleri üretim akışına bağlamadan önce bir durable receipt sahibi
seçilmelidir. Ortak model en az Yuva ingress message ID/operation, açık
attempt ID, connection generation + direction + typed JSON-RPC ID,
thread/turn/item bağları, write outcome, append-only gözlemler, Codex turn
state/terminal outcome, output delivery makbuzu, approval ve Yuva task/reviewer
state'lerini ayrı tutmalıdır. Atomik sınır, idempotency anahtarı, terminal
çelişki ve restart uzlaştırması #418/#437/#452 normatif kararlarıyla
uyumlandırılmalıdır.

Unknown durumunu pending_verification, verified, Yuva mesajının kaydedildiği
veya Codex'e gönderildiği anlamına çevirmeyin. Yuva'ya teslim için ayrı durable
write makbuzu; reviewer kabulü için de mevcut Yuva denetim geçişi gerekir.
