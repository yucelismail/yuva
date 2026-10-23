# Codex oturum adaptörü: gönderim ve busy/idle durum makinesi

Bu #421 için salt-okunur protokol tasarımıdır. #386/#389 feasibility
incelemeleri, #396/#402/#404 prototipleri ve #408–#411 receipt kararları birlikte
ele alınır. Repoda mevcut bir Yuva→Codex dispatch/session adapter'ı olduğu iddia
edilmez. Panel UI, üretim kodu, test veya runtime eklenmemiştir.

## Dispatch önkoşulu

Yuva sohbet mesajı veya model çıktısı kendi başına çalıştırılabilir iş değildir.
Dispatch adayı yalnız doğrulanmış kullanıcı/denetçi kaynağı, açıkça onaylanmış
task envelope, hedef principal/session binding ve değişmemiş instruction
revision/digest ile oluşur. #386 bulgusuna göre mevcut sohbet endpoint'i mesajı
kaydediyor; canlı push/dispatch ya da model session receipt sağlamıyor.
#389'da yerel Codex CLI yardımında app-server stdio görünse de Yuva adapter'ı,
TUI thread keşfi veya uçtan uca gönderim doğrulanmamıştır. Bu nedenle aşağıdaki
makine hedef session güvenilir broker/adapter tarafından bağlanana kadar
tasarımdır.

Gönderimden önce şu kayıtlar kalıcı olmalıdır: Yuva message/operation ID, varsa
task/run/attempt ID, recipient principal ve session binding, instruction
revision/digest, app-server thread ID, yeni connection generation ve yeni
JSON-RPC request ID. Ledger transaction commit edilemiyorsa dış gönderim
başlatılmaz.

## Ayrı session ve task durumları

Session busy/idle durumu task receipt ile aynı alan değildir.

| Alan | Değerler | Kaynak |
|---|---|---|
| session bağlantısı | unbound, connecting, bound, disconnected, stale, revoked | Broker/adapter kimlik ve bağlantı kanıtı |
| session işgali | idle, busy, unknown | Aktif turn için korele edilmiş kanıt |
| task dispatch | awaiting_approval, queued_unclaimed, dispatch_ready, write_started, sent_observed, accepted, running, approval_pending, unknown, terminal | Yuva envelope + JSON-RPC taşıma + Codex olayları |
| çıktı teslimi | not_recorded, recording, recorded, unknown | Artifact/Yuva write receipt |
| Yuva review | pending_verification, verified, pending_revision | Yuva reviewer olayı |

Busy durumdayken adapter yeni task'ı session için iç kuyruğa alıp sonra otomatik
göndermez. Yuva görevi kendi atama/queued state'inde kalır veya açık bir dış
scheduler kararı bekler; turn accepted olduğu iddia edilmez. Session binding,
auth, revoked durumu veya mevcut occupancy doğrulanamıyorsa dispatch kapalıdır.

## Durum makinesi

    stateDiagram-v2
      [*] --> Unbound
      Unbound --> Connecting: trusted binding + explicit task
      Connecting --> Idle: session/thread binding confirmed
      Connecting --> Disconnected: bind/connect failure
      Idle --> WriteStarted: task approved, ledger commit, session idle
      Idle --> QueuedAtYuva: task arrives while session busy
      QueuedAtYuva --> Idle: explicit scheduler rechecks and claims later
      WriteStarted --> NotSent: proven zero bytes
      NotSent --> WriteStarted: same attempt/request ID transport retry
      WriteStarted --> SentObserved: full frame + flush observed
      WriteStarted --> UnknownBusy: partial write / timeout / crash
      SentObserved --> Accepted: correlated turn/start success
      SentObserved --> UnknownBusy: lost response / timeout / disconnect
      Accepted --> Running: correlated turn/started
      Accepted --> Completed: correlated terminal event arrives first
      Running --> Completed: correlated turn/completed
      Accepted --> ApprovalPending: server approval request observed
      Running --> ApprovalPending: server approval request observed
      ApprovalPending --> Running: authorized response observed and correlated
      ApprovalPending --> UnknownBusy: disconnect / response outcome unknown
      UnknownBusy --> Reconcile: reconnect and read-only status/history lookup
      Reconcile --> Running: evidence says same turn remains active
      Reconcile --> Completed: correlated terminal event recovered
      Reconcile --> UnknownBusy: no decisive evidence or conflict
      Completed --> Idle: terminal receipt durable; session binding still valid
      Disconnected --> Connecting: new generation + authenticated rebind
      Disconnected --> UnknownBusy: unresolved old turn exists
      UnknownBusy --> Disconnected: connection lost
      Completed --> [*]

    Not: QueuedAtYuva adapter/session kuyruğu değildir ve acceptance anlamına gelmez.

Yuva queue geçişi yalnız uygunluk durumudur. Task, target busy iken adapter'ın
in-memory send kuyruğuna kopyalanmaz.

## Geçiş ve kanıt tablosu

| Olay | Gerekli kanıt | Task/turn kararı | Session kararı | Otomatik işlem |
|---|---|---|---|---|
| Açıkça onaylı task, doğrulanmış bağlı session idle | Principal/session binding fresh, target thread known veya açık new-thread policy, revision digest eşleşiyor | operation + attempt prepared | idle | Ledger commit, sonra tek request hazırlığı |
| Yeni task gelirken session busy | Correlated active turn veya pending approval | Task Yuva assigned/queued state'inde; accepted değil | busy | Session'a gönderim/kuyruklama yok; scheduler/user sonra yeniden değerlendirir |
| Occupancy unknown, stale/revoked binding veya ledger unavailable | Freshness/auth/state kanıtı eksik | dispatch_ready olmaz | unknown/stale | Fail closed; turn başlatma yok |
| Write öncesi ledger commit başarısız | Kalıcı operation/attempt/request bağı yok | gönderim başlamadı | idle (transport çağrılmadıysa) | App-server write yapılmaz |
| write_started sonrası kesin 0 byte | Transport bu frame için kanıtlıyor | not_sent_proven | idle | Aynı attempt + request ID ile taşıma retry mümkün; semantik olarak yeni attempt değil |
| Kısmi byte, flush belirsizliği, timeout veya process crash | Kesin 0 byte kanıtı yok | unknown | unknown_busy | Resend yok |
| Tam frame ve flush gözlendi | Transport write result | sent_observed; app-server accepted değil | busy/awaiting_receipt | İkinci turn gönderme yok |
| Eşleşen turn/start başarılı response | Aynı generation + yön + typed request ID; geçerli thread/turn result | accepted | busy | ID bağlarını kalıcı kaydet |
| turn/started, start response'tan önce | Event tekil olarak aynı thread/attempt'e bağlanıyor | running; bağ belirsizse unknown | busy/unknown | Provisional observation; zaman yakınlığıyla bağ kurma |
| Server approval request geldi | Exact generation request ID ve thread/turn/item korele | approval_pending | busy | İnsan/authorized operator kararı bekle; auto-approve/auto-response yok |
| Approval response yazımı/cevabı belirsiz | Response write outcome kesin değil | approval pending_unknown / turn unknown | unknown_busy | Response'u otomatik tekrarlama; ayrı uzlaştırma |
| Eşleşen turn/completed terminal event | Aynı thread/turn ve attempt bağı; status allowlist'te | Turn terminal; terminal_outcome ayrıca yazılır | Kanıt sonrası bağlantı sağlamsa idle | Output/artifact'i ayrı kaydet; task success veya Yuva verified türetme |
| Turn terminal fakat output/Yuva write belirsiz | Codex terminal var, output commit receipt yok | turn completed, output_delivery unknown | Codex session idle olabilir | Turn'u tekrar başlatma; output'u idempotent key ile uzlaştır |
| Bağlantı kopması/restart; active turn terminal değil | Önceki generation'da write_started/sent/accepted/running | unknown | unknown_busy/disconnected | Yeni turn kabul etme; yeni generation kur ve read-only reconcile et |
| Resume/history aynı turn'ün çalıştığını gösteriyor | Authenticated same thread binding ve tekil turn ID | running | busy | Eski operation'a bağla; yeni operation/attempt açma |
| Resume/history aynı turn'ün terminalini gösteriyor | Kararlı correlated terminal evidence | completed + terminal_outcome | Binding fresh ise idle | Observation kaydet; output receipt'i ayrıca uzlaştır |
| Uzlaştırmada kayıt yok/erişilemiyor veya terminal çelişkisi var | Negatif sonuç definitive değil veya evidence conflict | unknown | unknown_busy | Otomatik resend yok; operator conflict review |
| Terminal event sonrası task Yuva'ya teslim | Codex terminal + output/artifact write makbuzu | pending_verification olabilir | Session ayrı ölçümle idle | Yuva verified yalnız reviewer yazar |

## Busy/idle invariant'ları

- Session idle yalnız bağlı, yetkili ve active turn bulunmadığı güvenilir biçimde
  biliniyorsa işaretlenir. Turn response bekleniyor, approval pending, timeout,
  write belirsiz, reconnect uzlaştırması eksik veya event çelişkiliyse occupancy
  busy/unknown'dur; yeni turn dispatch edilmez.
- Correlated terminal event Codex turn'ünü kapatır. Output kaydı başarısız olsa
  bile bu turn'u yeniden çalıştırmak için gerekçe değildir. Operation'ın output
  delivery alanı unknown kalır ve ayrı uzlaştırılır.
- Failed/interrupted terminal outcome turn'ün bittiğini gösterir; başarılı
  tamamlanma değildir. Partial output incomplete etiketiyle artifact olabilir,
  fakat bu otomatik yeni attempt başlatmaz.
- Thread concurrency desteklenip desteklenmediği protokol/runtime
  doğrulamasıyla belirlenene kadar aynı session/thread için en fazla bir active
  veya unresolved turn'e izin verilir.
- thread/start veya thread/resume success, user task turn'ünün kabul edildiği
  anlamına gelmez. Session ready/identity binding ve task turn receipt ayrıdır.
- Hedef thread ID unknown ise rastgele yerel TUI/CLI oturumuna push yapılmaz.
  #389'da mevcut Codex TUI thread'ini bulma/bağlama desteklenmiş değildir.

## Kimlik ve retry kuralları

Operation Yuva message ID'sine bağlı sabit mantıksal iş; attempt ise açıkça
başlatılan yürütme denemesidir. #408 SQL taslağındaki tek operation satırına tek
attempt/request/thread/turn koyma biçimi bu kardinaliteyi temsil etmiyor; gerçek
uygulama operation ve attempt kayıtlarını ayırmalıdır.

- operation_id: Yuva message namespace + type-preserving canonical message ID.
- attempt_id: her açık orkestrasyon denemesi için yeni, immutable ID; run_id ve
  varsa task_id ile ilişkili.
- request_id: her attempt/JSON-RPC generation için type-preserving ID; aynı
  generation içinde başka request için reuse yok. Yalnız kesin 0-byte taşıma
  retry'sinde aynı request ID ve attempt korunur.
- thread_id/turn_id/item_id: yalnız protocol evidence ile bağlanır; ID eşleşmesi
  principal/session authentication yerine geçmez.
- Yuva task/output için stable operation/delivery idempotency anahtarı olmalı;
  event hash'i tek başına delivery key değildir.

## Açık doğrulama ve kararlar

1. #389 feasibility raporu Codex CLI 0.163.0 help çıkışında stdio app-server
   taşımasını gözledi; request/event/schema ve approval wire ayrıntıları yerel
   runtime'da doğrulanmadı. Güvenli fixture/izole profile ile schema ve
   start/response/started/completed ordering doğrulanmalı.
2. Aynı app-server thread'in concurrency, busy error ve thread/resume davranışı
   exact CLI/protocol sürümünde belirlenmeli. O zamana kadar serialized policy
   kullanılır.
3. Mevcut Codex TUI thread ID'sinin güvenilir biçimde elde edilip edilemediği
   unknown; doğrulanana kadar adapter'ın kendi açtığı/atanmış thread dışında
   hedef seçilmez.
4. Approval response writer, user confirmation UI ve response-lost recovery
   mevcut prototiplerde yoktur. Yetki, principal ve audit contract'i olmadan
   bu state machine pending/unknown'da durur.
5. Yuva message→task envelope, recipient principal/session proof, revocation,
   output storage receipt ve reviewer transition mevcut runtime'da bağlı
   değildir. Bu sözleşme bunu varmış gibi göstermiyor; her biri ayrı
   implementation/acceptance gate gerektirir.

Bu makine #418 entegrasyon sözleşmesiyle tutarlıdır: transport, turn, output ve
Yuva review ayrı kanıt katmanlarıdır; unknown güvenli biçimde durur; otomatik
retry, approval veya Yuva verified geçişi yoktur.
