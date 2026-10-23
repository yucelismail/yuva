# #551 — İlk provider için release sonrası capability-gated plan

Tarih: 2026-10-23
Durum: Faz/backlog önerisi; provider seçimi ve entegrasyon onayı değildir.
Provider/credential erişimi, kod, test, runtime ve deployment yapılmadı. Bu iş
ilk yerel MVP'nin kapsamı veya Go/No-Go kapısı değildir.

## Karar

Provider entegrasyonu ilk yerel MVP'den sonra, ayrı ve varsayılanı kapalı bir
release adayı olarak ele alınmalıdır. Statik kaynaklara göre **OpenCode ilk
qualification/pilot adayı** olabilir: izole HTTP/SSE adaptör ve REST reconcile
prototipleri var; `/global/health` + exact `/doc` fingerprint için #528
capability-gate kararı da yazılıdır. Bu yalnız değerlendirme sırası önerisidir:
hedef OpenCode sürümü, `/doc` fixture'ı ve reviewed version/schema pair'i
bulunmadığından bugün açılabilir bir provider capability yoktur.

Codex app-server eşdeğer alternatif olarak backlog'da tutulmalıdır. #529 typed
JSON-RPC ID, connection generation, thread/turn/item ve approval gözlemlerini
ayırt eder; authenticated principal/thread binding, interrupt terminal cevabı
ve output-limit wire anlamı kesinleşmemiştir. Bir aday, aşağıdaki zorunlu seçim
kapılarından birini geçemiyorsa, iki aday da geçemiyorsa entegrasyon seçilmez.

Entegrasyonun durumu provider HTTP cevabı, terminal turn, Yuva output receipt
ve Yuva reviewer kararı için ayrı gösterilmelidir. Hiçbir provider olayı tek
başına Yuva teslimi, `verified` görev veya aktör yetkisi sayılmaz.

## Provider seçme ölçütü

Önce zorunlu kapılar uygulanır; kapı geçmeyen aday puanlanarak içeri alınmaz.

| Zorunlu kapı | Kabul edilebilir kanıt | Ret/fail-closed sonucu |
|---|---|---|
| Exact protokol kimliği | HTTP provider için exact server version + canonical OpenAPI/schema fingerprint + fixture/review kimliği; app-server için exact protocol/server build kimliği, versioned schema/fixture ve capability incelemesi | Sürüm, schema veya kaynak bağı belirsizse `unknown`; provider IO kapalı. |
| Dar session/thread bağlama | Kalıcı operation ile tek provider instance/session/thread ilişkisi, yeniden bağlantıda generation ve opaque ID kapsamı | Model/provider payload'ından actor/task/session türetme yok; bağ birden çok adaya uyuyorsa dispatch kapalı. |
| Recovery kanıtı | Salt-okunur status/history veya event reconciliation'ın kapsam ve sınırları açıkça yazılı | Replay/idempotency belgelenmediyse otomatik retry yok; `not_found` gönderilmedi kanıtı değil. |
| Capability azaltımı | Her route/method için `supported/unsupported/unknown`; send/status/history/events/approval ayrı | Bir route'un varlığı yetki değildir; bilinmeyen capability çağrılmaz. |
| İnsan onayı | Permission/approval request için exact provider request ID, session/thread, tool/scope; karar veren Yuva principal ve response receipt | Varsayılan `off`; model event'i veya provider'ın mevcut permission ayarı insan kararı değildir. |
| Veri ve işyeri sınırı | Workspace/session binding, credential scope, output redaction/size policy ve kabul edilmiş log/retention | Credential/log/output yolu belirsizse pilot başlamaz; secret veya ham output genel loga taşınmaz. |
| Çalıştırma/rollback yönetimi | Release artifact ile uyumlu minimum sürüm, feature-off başlangıç, operatör durdurma ve önceki release'e dönüş yolu | Kirli/unknown release veya canlı veri üstünde ilk kabul yok. |

Zorunlu kapıları geçen adaylar arasında ikinci aşamada şu ölçütlerle seçim
yapılır: istenen yerel workflow'a uygunluk; kullanılabilir exact schema
kanıtının edinilmesi; request/turn terminal kanıtının açık olması; status/
history reconciliation gücü; offline fixture üretilebilirliği; permission
modelinin insan kararıyla bağlanabilirliği; en dar credential/tool yetkisi;
redaction ve payload saklama maliyeti; test/rollback yükü; sürüm değişimi
sıklığı ve sahiplik. Ağırlık ve kabul eşiği ilk qualification öncesi ürün
sahibi tarafından kararlaştırılır; bu not sahte bir sayısal skor üretmez.

### Statik aday karşılaştırması

| Aday | Bu kaynaklarda görülen güç | Açık/kanıtsız alan | Önerilen konum |
|---|---|---|---|
| OpenCode HTTP/SSE | Health/version ve per-instance `/doc` keşfi; izole send/status/history/event adaptörü; #528 exact pair ve tri-state gate sözleşmesi | Hedef `/doc` yok; exact pair allowlist yok; SSE replay/order/idempotency belgelenmiş değil; permission response ve Yuva durable ledger bağlanmamış | İlk qualification adayı. Yalnız REST read/send ile sınırlı pilot ancak exact pair/manifest o capability'leri ayrı onaylarsa. Approval, shell, TUI ve session mutation kapalı. |
| Codex app-server | JSON-RPC typed ID + connection generation; thread/turn/item/terminal observation modeli; approval server-request ID'lerini ayıran #529 sözleşmesi | Hedef binary/protocol version fixture ve authenticated principal/thread binding kararı yok; interrupt RPC terminal kanıtı değil; provider output-limit wire semantiği unknown; durable receipt/Yuva delivery yok | Alternatif qualification adayı; aynı receipt, auth/session ve output kapıları uygulanmadan OpenCode'den daha hazır sayılmaz. |

Seçim “OpenCode şu anda destekleniyor” anlamına gelmez. İlk qualification
sonucu exact schema pair/fixture üretemezse OpenCode `blocked/unknown` kalır ve
Codex adayı aynı kapılardan değerlendirilir; hiçbiri geçmezse provider fazı
bekler, yerel MVP devam eder.

## Sıralı uygulama backlog'u

| Sıra | İş paketi ve çıktı | Kabul kapısı / bağımlılık |
|---|---|---|
| P0 — Seçim ve tehdit modeli | Kullanım senaryosu, desteklenen tek provider adayının instance/session sınırı, dış servis/credential sahipliği, allow/deny capability listesi ve geri dönüş sahibi | İlk yerel MVP'den ayrı release hedefi; veri sahibi/operatör onayı. Provider dispatch hâlâ kapalı. |
| P1 — Version/schema manifesti | Exact provider/build veya server version; HTTP ise OpenAPI 3.1 extraction ve canonical fingerprint; Codex ise protocol fixture/schema kimliği; kaynak hash'i, review ID/tarihi ve per-capability `supported/unsupported/unknown` | #528 HTTP çift şartı uygulanır; ilk görülen artifact kendi kendine allowlist olamaz. Bilinmeyen/changed pair kapalı kalır. |
| P2 — Principal ve session binding | Yuva operation/source identity'yi doğrulanmış actor'a bağlama; provider instance + session/thread seçimini out-of-band sabitleme; workspace/credential allowlist | `initialize` veya provider/model mesajı auth kanıtı olamaz (#529); aynı task/session'in başka bağa otomatik taşınması yasak. |
| P3 — Durable receipt altyapısı | Yerel transactional store; `operation_id`, immutable request digest, yeni `attempt_id`, provider instance, `connection_generation`, typed request ID ve append-only observations | Store/schema/izin/lock/backup/restore ve kapasite politikası incelenir. Store commit belirsizse provider write başlamaz. #527/#504. |
| P4 — Tek provider transport/reducer | Yalnız seçilmiş capability'ler için adapter; response/event correlation, bounded input/output, reconnect generation, salt-okunur reconcile ve doğru unknown state | `accepted`, provider turn terminali ve Yuva output ayrı tutulur. SSE yarım event dispatch edilmez; Codex out-of-order/conflict `unknown` kalır. |
| P5 — Retry ve recovery | Write öncesi durable intent; zero-byte kanıtı, partial/timeout/lost response ve restart davranışları; operatör uzlaştırma paneli/runbook'u | Yalnız aynı attempt için kesin zero-byte kanıtı sınırlı transport retry'sini değerlendirebilir. Diğer write-start belirsizliklerinde otomatik resend yok. Yeni bilinçli retry yeni `attempt_id`; eski unknown korunur. |
| P6 — Approval | Permission event/request'i ve insan kararını aynı provider/session/request ID'ye bağlayan UI/receipt; süre sonu, iptal ve response-loss sonucu | İlk değer `off`. İnsan actor, tool/capability, kapsam ve karar ayrı kanıtlanır; provider `resolved`/model metni tek başına yetki değildir. Önceki P0–P5 kabulü gerekir. |
| P7 — Redaction ve output storage | Prompt/output/log alan sınıfları; yazmadan önce redactor; byte/record limit; gerekirse sınırlı artifact storage ve output receipt | Redaction başarısız/ambiguous ise raw fallback yok. Ham provider output varsayılan kalıcı Yuva sohbeti değildir. Digest ve redacted summary de hassas ledger'da tutulur. |
| P8 — Yuva teslim ve review köprüsü | Stable `yuva_event_id`/payload digest ile artifact/mesaj yazımı; JSONL readback/outbox; görev state'i ve reviewer UI'si | Yuva output ancak durable write makbuzuyla `recorded`; görev yalnız Yuva lifecycle'da `pending_verification`; `verified` yalnız bağımsız reviewer geçişi (#527). |
| P9 — İzole kabul ve sınırlı pilot | Sürüm pinli fixture'lar, timeout/restart/conflict/approval/redaction/retention senaryoları; feature-off install; operatör opt-in ve rollback kaydı | Temporary data/store ve desteklenen release üzerinde kabul; live user data ile ilk doğrulama yok. Hata veya unknown artınca kapatma/rollback işlemi tanımlı. |

P0–P5 kabul edilmeden pilot provider write açılmaz. P4–P8 olmadan kullanıcıya
“gönderildi, tamamlandı, teslim edildi veya onaylandı” denmez. P9 kapsamındaki
doğrulama release adayı sonrasında ve ayrı kabul ile yapılır; yerel MVP'nin
çalışması için zorunlu değildir.

## Receipt, unknown ve retry ortak sözleşmesi

Her kaynak mesaj tek `operation_id` ve immutable digest alır. Her bilinçli
provider gönderimi yeni `attempt_id` taşır. Provider event/request ID'leri
namespace, connection generation, yön ve JSON türüyle saklanır; farklı katman
kimlikleri birbirinin yerine geçmez. Provider state ve receipt projection
ayrı gözlem/transaction kaydıdır.

- Write başlamadan önce intent/attempt kalıcılaşmalıdır. Intent commit'i
  `commit_unknown` ise aynı key/digest readback yapılmadan dış çağrı yapılmaz.
- Kesin sıfır byte dışı timeout, kısmi write, response kaybı, connection EOF,
  process restart ve store hatası `unknown` üretir. Otomatik resend/restart
  retry yoktur.
- Read-only status/history, exact session/thread/turn bağı varsa uzlaştırmaya
  yardım eder. `not_found`, stale/bounded history veya replay garantisi
  yokluğu gönderilmedi kanıtı değildir.
- Kapasite bittiğinde unresolved receipt/tombstone atılmaz; yeni dispatch
  fail-closed olur ve operatöre bildirilir. Tombstone süresi kaynak-message
  yeniden ingest, provider reconcile ve insan retry pencerelerinin en uzunu
  belirlenmeden seçilmez.

Bu ortak sözleşme `docs/persistent-session-receipt-contract-527.md`'deki
katmanları korur: provider `accepted` Yuva output delivery değildir; provider
terminal event'i Yuva task terminali değildir; Yuva output makbuzu reviewer
onayı değildir.

## Açık kararlar ve kaynaklar

Operatör/ürün sahibi henüz provider adayını, exact version/schema fixture'ını,
credential/session bağını, receipt backend/retention'ını, approval scope'unu,
output/artifact saklama süresini, redaction kurallarını ve rollback sahibini
seçmelidir. Bu alanlar tahmin edilip canlı kullanım izni olarak yorumlanamaz.

- `docs/persistent-session-receipt-contract-527.md` — identity katmanları,
  durable intent, unknown/retry, retention ve output/task review ayrımı.
- `docs/opencode-adapter-version-capability-contract-528.md` — exact version +
  canonical `/doc` fingerprint, per-capability startup gate, SSE/REST sınırları.
- `docs/codex-app-server-yuva-turn-contract-529.md` — typed JSON-RPC ID,
  thread/turn/item, approval, interrupt, occupancy ve output bilinmeyenleri.
- `docs/session-bridge-persistent-receipt-store-504.md` — transactional store,
  outbox, unknown ve tombstone tasarımı.
- `docs/session-response-yuva-receipt-correlation-489.md` — provider sonucu,
  Yuva receipt ve task review kanıtlarının ayrımı.
- `docs/provider-approval-bridge-decision-490.md` — insan onayı ve provider
  permission sınırı.
- `docs/opencode-output-yuva-mapping-505.md` — untrusted provider output,
  redaction ve event-to-Yuva sınırı.

Bu belge faz planıdır; provider pair'i onaylamaz, local MVP'ye blocker koymaz ve
entegrasyonun mevcut/çalışır olduğunu iddia etmez.
