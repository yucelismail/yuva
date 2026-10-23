# Codex app-server olaylarını Yuva receipt ve occupancy ile eşleme (#529)

**Durum:** statik kaynaklardan çıkarılmış karar notu. Canlı Codex oturumu,
provider bağlantısı, authentication işlemi, kod/runtime veya test içermez. Yerel
prototipler fixture/stdio gözlem taslaklarıdır; kalıcı receipt veya Yuva
entegrasyonu değildir. Kaynakta doğrulanmayan protocol alanları ve anlamlar
`unknown` kalır.

## Kanıt ve otorite katmanları

Yuva message ingress'i, Codex JSON-RPC request'i, Codex turn terminali, output
makbuzu, session occupancy ve Yuva task/review ayrı durum alanları olmalıdır.
Birinin gözlemi diğerinin durumunu kendiliğinden güncellemez.

| Alan | Örnek durumlar | Yetkili kanıt |
|---|---|---|
| Bağlantı/auth | `disconnected`, `connecting`, `bound`, `unknown`, `revoked` | Güvenilir host/broker principal ve session binding kanıtı; JSON-RPC `initialize` cevabı tek başına actor/auth kanıtı değildir. |
| Thread/session | `unbound`, `bound`, `unknown` | Tekil, şema geçerli `thread/start` veya `thread/resume` cevabındaki thread ID ve doğrulanmış dış principal/session bağı. |
| Transport request | `not_started`, `write_started`, `not_sent_proven`, `sent_observed`, `unknown` | Kalıcı attempt/generation/request kaydı ve gerçek taşıma sonucu. Tam write, app-server kabulü değildir. |
| Codex turn | `unknown`, `accepted`, `running`, `terminal_observed` + exact `terminal_outcome` | Korele `turn/start` response, `turn/started`, `turn/completed` gözlemleri. |
| Session occupancy | `idle`, `busy`, `unknown` | Bu güvenilir session/thread'deki aktif veya çözümlenmemiş turn/approval kanıtı. |
| Output delivery | `not_recorded`, `recorded`, `unknown` | Yuva/artifact hedefinin ayrı, kalıcı write makbuzu ve ID/digest'i. |
| Yuva task/review | Kanonik Yuva lifecycle değerleri | Yuva görev mutation ve reviewer geçmişi; Codex event'i `pending_verification`/`verified` yazmaz. |

Dispatch fail-closed kalır: auth/session binding revoked, stale veya
doğrulanmamışsa; occupancy `unknown` ise; ya da ledger commit edilemiyorsa
turn başlatılmaz. Provider/model metni principal, actor, task veya permission
kanıtı değildir.

## Olay eşleme tablosu

| Codex gözlemi | Codex request/turn sonucu | Occupancy ve Yuva kararı |
|---|---|---|
| `initialize` client request / response | Aynı generation ve typed JSON-RPC ID ile eşleşmiş handshake gözlemi. Hatalı/eşleşmemiş sonuç `unknown`. | Protokol başlatma/görüşme kanıtı olarak kaydet; kimlik doğrulandı veya Yuva aktörü bağlandı deme. Auth state dışarıdan doğrulanana kadar `unknown`; turn kabul edilmez. |
| `thread/start` veya `thread/resume` başarılı response | Geçerli `thread.id` bağlanabilir. Prototip bunu context olarak tutar; bu request henüz user turn değildir. | Dış principal/session binding de kanıtlıysa thread `bound` olabilir; aksi halde `unknown`. Task accepted/busy denmez. |
| Eşleşen başarılı `turn/start` response | Tekil generation + yön + JSON türü korunmuş request ID ve geçerli `thread.id`/`turn.id` ile `accepted`. | Turn unresolved olduğu için `busy`. Yalnız request error gözlenirse genel turn sonucu `unknown`; method-specific, şema belgeli garanti yoksa rejected/not-sent çıkarımı yapılmaz. |
| `turn/started` | Event thread/turn ile tek bir attempt'e bağlanıyorsa `running`; response'tan önce gelebilir. | `busy`. Eşleşmeyen/çoklu aday event orphan olarak saklanır ve occupancy `unknown` olur. |
| `turn/completed` status `completed`, `failed`, `interrupted` | Aynı thread/turn'e tekil bağlı terminal gözlemi; exact status `terminal_outcome` olarak korunur. Çelişkili terminal event iki kanıtla `unknown/conflict` olur. | Turn artık aktif değildir; session binding sağlıklı ve başka unresolved turn/approval yoksa occupancy `idle` olabilir. `failed`/`interrupted` Yuva task başarısız/iptal veya başarılı teslim demek değildir. |
| `turn/completed` içindeki eksik, bilinmeyen veya terminal olmayan status (ör. `inProgress`) | Terminal kanıtı sayma; raw payload yerine güvenli alan/digest ve validation reason ile `unknown`. | Occupancy `unknown/busy`; yeni dispatch kapalı. Kaynak anlamı doğrulanana kadar bilinmeyen status'u terminal allowlist'e ekleme. |
| `item/started`, `item/completed`, `item/agentMessage/delta`, diff/patch/command output event'i | Item/thread/turn bağı varsa observation ve item ID kaydı. Item completion, output delta veya tool sonucu turn terminali değildir. | İlgili turn unresolved ise `busy`; turn state'i kendi kanıtına göre kalır. İçerik varsayılan untrusted ve hassastır; ham tool args/output/diff Yuva'ya doğrudan aktarılmaz. |
| Approval veya interaction server request (`item/.../requestApproval`, `item/tool/requestUserInput`, `mcpServer/elicitation/request`) | Aynı generation'daki typed server request ID ile `pending`; schema dışı/çakışan request `unknown/conflict`. | İlgili turn/session `busy` ve approval `pending`. Adapter otomatik cevap yazmaz; yalnız yetkili insan kararı ve ayrı response receipt süreci olabilir. |
| `serverRequest/resolved` | Prototip request'i kapatabilir ama notification kendi başına karar taşımıyor; karar `unknown` kalabilir. | Approval sonucu ve turn terminali çıkarma; aynı request'e bağlı gözlenmiş cevap/çözüm kanıtı gelene dek busy/unknown. |
| `turn/interrupt` request ve RPC response | Request yalnız interrupt niyetidir. Başarılı RPC cevabının kapsamı şemadan kesinleşmedikçe turn'ün durduğunu kanıtlamaz. | Turn terminal `interrupted` ancak korele terminal olay bunu bildirirse. Response kaybı, timeout veya disconnect `unknown/busy`; otomatik interrupt/resend yok. Yuva task state ayrıca değişmez. |
| Stream EOF/read timeout/disconnect/restart | Açık request ve approval'lar `unknown`/`pending_unknown`; son bilinen state ve generation korunur. Yeni generation'da aynı ID eski request'i çözmez. | Unresolved turn varsa `unknown/busy`; otomatik retry ve `idle` varsayımı yok. Read-only uzlaştırma yalnız aynı thread/turn'e tekil pozitif kanıtla ilerler. |

Olayların geliş sırası tek başına provider sırası değildir. `turn/started` response'tan
önce veya terminal event'ten sonra gelebilir: kanıtlar append-only tutulur; uyumlu
geç olay terminal state'i geriletmez. Aynı turn'e ait çelişkili kimlik/terminal
kanıtında ilk veya son event kazanmaz; projection `unknown/conflict` olur. JSON-RPC
ID `7` ile `"7"` farklıdır ve request ID uzak idempotency key değildir.

## Cancellation, output limit ve sonuç teslimi

### Cancellation

`turn/interrupt` gözlemini `cancel_requested` benzeri ayrı command/intent kaydı
olarak tutmak uygundur; bu status yerel tasarım alanıdır, Codex wire sonucu
iddiası değildir. Sadece request response veya kullanıcıdaki “iptal et” metni
terminal `interrupted` kanıtı sayılmaz. Aynı turn için doğrulanmış terminal event
gelene kadar occupancy `busy/unknown` kalır. Terminal `interrupted` ise Codex
turn'ü sonlanmıştır; Yuva görevinin `cancelled`/başarısız durumu ayrı, yetkili
Yuva lifecycle kararı gerektirir.

### Output limit

İncelenen app-server adapter'ı provider turn output/token limitini modellemiyor.
`ERROR_MESSAGE_INPUT_LIMIT` ve `ERROR_MESSAGE_OUTPUT_LIMIT` yalnız hata metni
projection'ı için yerel karakter sınırlarıdır; Codex turn limitini veya
truncation'ı kanıtlamaz. `turn/completed` dışında doküman/prototipte
doğrulanmış bir `output_limited` status/field bulunmadığından böyle bir değer
varsayılmaz.

İleride Yuva-side byte/token/artifact kotası aşılırsa bu ayrı
`output_capture=limited|truncated|unknown` gözlemi olmalıdır: alınan byte/öğe
sayısı ve güvenli digest kaydedilir; turn state yalnız Codex terminal kanıtına
göre kalır. Eksik capture, tamamlanmış Yuva output teslimi değildir. Provider
şeması ileride açık limit marker'ı sunarsa exact sürüm/field sabitlenip ayrıca
eşlenmeden terminal outcome'a çevrilmez.

### Tool ve approval sınırı

Tool item/command/file-change event'i provider'ın gözlediği bir işlem/çıktıdır;
Yuva shell komutu, uygulanmış repo değişikliği, başarı, yetki veya güvenilir
talimat değildir. Event payload'ı redaction ve byte limitinden geçmeden sohbet,
log ya da artifact'e taşınmaz. Approval event'i yalnız bekleyen izin talebini
kanıtlar. Yanıt writer'ı, actor doğrulaması ve response-loss uzlaştırması
prototip kapsamı dışıdır; `serverRequest/resolved` ya da model metni insan
kararını kanıtlamaz.

## Kalıcı geçiş için zorunlu kararlar

1. Her request/write öncesi Yuva operation + immutable attempt ID + connection
   generation + typed request ID + hedef binding kalıcı kaydedilir; commit
   belirsizse aynı key ile readback yapılmadan dış çağrı yoktur.
2. `initialize`/thread handshake, auth, transport, turn, item, approval,
   output delivery, occupancy ve Yuva review ayrı observation/state alanlarıdır.
   Gözlemler append-only; reducer correlation/evidence ile türetilir.
3. Restart'ta write_started, accepted/running veya pending approval terminal
   kanıtı yoksa `unknown`/`pending_unknown` yapılır. Sadece gerçek taşımanın aynı
   frame için kesin sıfır byte kanıtı güvenli transport retry'sini
   değerlendirebilir. Partial write, timeout, lost response veya interrupt
   cevabı belirsizliğinde otomatik tekrar yoktur.
4. Raw prompt/tool/output/error saklama varsayılan kapalıdır. ID, digest ve
   redacted özet de erişim/retention kontrollü metadata'dır. Yerel projection
   error limitleri output-store byte/token bütçesi değildir.
5. Codex terminal + output/artifact write receipt ayrı ayrı kanıtlanır; yalnız
   Yuva teslim transition'ı `pending_verification`, reviewer kararı `verified`
   üretebilir. Codex receipt state'i Yuva task API'sine yazma yetkisi vermez.

## Kaynaklar ve sınırlamalar

- Yuva #431 statik incelemesi — adapter/README'nin stdio fixture kapsamını,
  no Yuva/filesystem/provider writer ve generation/timeout sınırlarını
  değerlendiren güvenlik incelemesi; bulguları Yuva görev geçmişinde.
- `prototypes/codex-app-server/yuva-receipt-comparison-473.md` — adapter,
  retry/approval ve reconnect taslaklarının birbirine/kalıcı Yuva akışına bağlı
  olmadığını ve genel error, terminal conflict, attempt/generation boşluklarını
  karşılaştırır.
- `prototypes/codex-app-server/README.md`, `adapter.py` — şema listeli client
  method/notification gözlemi; output projection ve ID map'leri in-memory'dir.
- `prototypes/codex-app-server/retry_approval.py`, `reconnect_state.py` —
  zero-byte/reconcile-only, connection generation, pending approval ve
  disconnect unknown taslakları; disk/store yazmaz ve birbirine bağlanmış
  production ledger değildir.
- `prototypes/codex-app-server/session-busy-state-machine.md` — session
  occupancy'nin turn/task/output/review'dan ayrımı ve busy/unknown fail-closed.
- `prototypes/codex-app-server/receipt-event-order-matrix.md`,
  `receipt-integration-contract.md` — turn terminal allowlist, out-of-order,
  conflict ve output/Yuva review ayrımı.
- `prototypes/codex-app-server/message-bridge-output-privacy.md`,
  `docs/provider-approval-bridge-decision-490.md` — untrusted output ve
  approval/decision/write boundaries.

Mevcut kaynaklar `initialize` için authenticated principal kanıtı, Codex
output-limit wire semantiği veya `turn/interrupt` cevabının terminal garantisini
kurmuyor. Bu alanlarda tasarım `unknown` bırakır; yeni şema/field varsaymaz.
