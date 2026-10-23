# Yuva #490 — Provider izinlerini Yuva üzerinden insan kararına bağlama

Kapsam: OpenCode permission akışı ile Codex app-server approval gözlem prototiplerini, Yuva'da bekleme/karar/reconnect kuralları açısından karşılaştırmak. Bu karar notudur; approval cevabı gönderen kod veya canlı entegrasyon değildir. Hiçbir onay otomatik verilmez.

## Karar

İlk köprü tasarımı **observe-only ve kapalı varsayılan** olmalı. Provider izni gelirse, exact provider/session/request kimliğiyle eşleşen ayrı bir Yuva approval kartı oluşturup yetkili bir insandan karar beklemeli. Sohbet mesajı, model metni, provider'ın “permission replied” bildirimi veya timeout tek başına Yuva kullanıcısının kararı değildir.

Provider cevabı yazmak ayrı ve henüz uygulanmamış bir capability olmalıdır. Bu capability etkinleşmeden approval kartında kullanıcı kararı kaydedilebilir, fakat provider'a approve/reject gönderildiği iddia edilemez.

## Sağlayıcı farkları

| Alan | OpenCode | Codex app-server |
| --- | --- | --- |
| İstek gözlemi | Resmi plugin dokümanı `permission.asked` ve `permission.replied` event adlarını listeler. Server API ayrıca `POST /session/:id/permissions/:permissionID` endpoint'ini; body için `{ response, remember? }` şeklini yayımlar. Plugin event'i API response yetkisini veya eksiksiz event replay'i kanıtlamaz. | Prototip, `item/commandExecution/requestApproval`, `item/fileChange/requestApproval` ve `item/permissions/requestApproval` server request'lerini JSON-RPC ID ile bekleyen kayıt olarak gözlemler. `threadId`, `turnId`, `itemId` bağı varsa korunur. Prototip hiçbir cevap yazmaz. |
| Yapılandırma / kapsam | Permission kuralı `allow`, `ask`, `deny`; resmi dokümanda `--auto` deny olmayan izin isteklerini otomatik kabul edebilir. UI'deki `once`, `always`, `reject` seçenekleri aynı kapsamda değildir; `always` önerilen pattern'leri o OpenCode session'ında gelecekte de kabul edebilir. Köprü `--auto` başlatmamalı ve etkili permission yapılandırmasını doğrulamadan approval beklediğini varsaymamalı. | Provider server-initiated request'e karşılık client JSON-RPC yanıtı bekler. Gerçek seçenekler hedef Codex sürümünün protokol şemasından alınmalıdır; yalnız prototipte bulunan karar adları veya farklı sürümün seçenekleri varsayılan yapılmamalı. Prototip yanıt oluşturamaz veya gönderemez. |
| Cevap yolu | HTTP permission endpoint'i var; `{response, remember}` alanlarının değer semantiğini hedef instance `/doc` şemasıyla sabitle. `permission.replied` aynı permission ID ve session ile eşleşen gözlem olarak işlenmeli. | Yanıt, özgün server request ID'sini ve o app-server bağlantı neslini kullanır. Cevap yazımı/sonucu belirsiz kalırsa otomatik cevap tekrarı yok. |
| Yeniden bağlanma | #472 araştırması SSE replay/cursor ve eksiksiz approval replay garantisi doğrulamıyor. Yeni status/history verisinin pending permission'ı içerdiği varsayılmamalı. | Prototip disconnect'te pending'i `pending_unknown` yapar; aynı request ID'nin yeni generation'da görünmesi çakışmadır. `serverRequest/resolved` bildirimi karar içermiyorsa sonuç `resolved_unknown` kalır. Bellek içi prototip restart dayanıklılığı sağlamaz. |

OpenCode'un `ask` politikasında görülen bir isteği kullanıcıya sunması, Codex'in server request/JSON-RPC cevabıyla aynı wire protokolü değildir. Ortak arayüz yalnız iki tarafta da var olan kanıtı gösterebilir; ortak bir “approve” endpoint'i varmış gibi davranamaz.

## Yuva approval kaydı ve görünümü

Her isteği ayrı, kalıcı bir nesne olarak tut:

```text
approval_id                 # köprü içi, kalıcı ve eşsiz
provider_kind               # opencode | codex_app_server
provider_instance/session   # doğru server ve oturum
connection_generation       # Codex'te zorunlu; OpenCode event bağlantı nesli
provider_request_id         # OpenCode permissionID veya typed Codex JSON-RPC ID
thread_id/turn_id/item_id   # sağlayıcı sunuyorsa ve doğrulanmışsa
action_summary + redacted details digest
state                       # pending | decision_recorded | response_started |
                            # response_observed | resolved | pending_unknown | conflict
decision                    # yalnız doğrulanmış insan kararı
actor/audit evidence        # karar veren doğrulanmış Yuva principal'ı
observations[]              # append-only event/HTTP/RPC sonuçları
```

Kart; sağlayıcıyı, session/thread ve istek kimliğini, yapılmak istenen eylemi, kapsamı ve etkili olacak izin süresini gösterir. Shell komutu, path, MCP argümanı ve benzeri ayrıntılar secret/redaction politikasından geçirilir. Eksik alan “zararsız” kabul edilmez; karar için gerekli alan gösterilemiyorsa kart approve seçeneği sunmaz ve `unknown`/inceleme durumunda kalır.

Karar, doğrulanmış actor'ın belirli `approval_id` ve gösterilen içerik digest'i için verdiği tekil seçim olmalıdır. Yuva sohbet mesajı bu seçim biçimi değildir. Aynı aktörün aynı kartı tekrar açması aynı approval'dır; farklı provider ID/payload ile tekrar aynı kart kimliği kullanılırsa conflict olur.

## Karar yaşam döngüsü

1. **İstek alındı:** Event/server request, provider instance + session/thread + generation + request ID ile korele edilip şema doğrulaması yapılır. Dedupe varsa aynı içerik aynı approval'a bağlanır; aynı ID/farklı içerik `conflict` olur. Eşleşmeyen event otomatik olarak en yeni göreve bağlanmaz.
2. **Yuva'ya taşındı:** Approval kaydı dayanıklı biçimde yazıldıktan sonra kullanıcıya `pending` gösterilir. Yuva write sonucu belirsizse kaydı tekrar oluşturmadan önce readback yapılır. Provider turn/session izin kararını bekler; busy/blocked kabul edilir. Genel görev tamamlandı veya provider cevap verdi denmez.
3. **Karar bekleniyor:** Yalnız yetkili insanın açık `onayla` veya `reddet` seçimi karar sayılır. İlk sürümde `always`, “session için hatırla”, geniş pattern grant, karar önerisi ve otomatik timeout kararı desteklenmez. Codex'in izin verdiği yanıt seti hedef şema ve varsa `availableDecisions` ile sınırlandırılır; onay UI'sı yalnız ilgili isteğin geçerli seçeneklerini sunar.
4. **Cevap gönderiliyor:** Yuva actor, karar, approval ID, provider request ID/generation ve gönderim operation ID audit kaydına bağlanır. Provider response yazarı/endpoint'i hedef sürüm için doğrulanmış değilse işlem burada durur; kart “provider yanıtı gönderildi” demez.
5. **Cevap sonucu:** Başarılı HTTP/RPC response yalnız endpoint'in cevabıdır; izin isteğinin çözüldüğünü ayrıca gözle. Eşleşen `permission.replied` veya Codex response/resolution kaydı varsa gözlemle. RPC/HTTP cevabı kaybolursa veya write sonucu belirsizse `response_unknown`; otomatik tekrar gönderme yok. Karar, provider çözümünden ayrı olarak `decision_recorded` kalabilir.
6. **Çözüldü:** Yalnız aynı provider request için karar/çözülme kanıtı `resolved` yapar. Bu, tool işleminin başarılı olduğu, turn'ün tamamlandığı veya Yuva görevinin teslim edildiği anlamına gelmez. Sonraki provider execution ve Yuva output/review aşamaları ayrı olaylardır.

### Reddetme, zaman aşımı ve kopma

- **Reddetme:** Reddetme pozitif, actor'a bağlı bir insan kararıdır. `reject`/Codex decline gibi wire değerleri yalnız hedef sürüm şemasında doğrulanır ve aynı request'e cevap olarak gider. Config düzeyindeki OpenCode `deny` kuralı ile belirli bir pending isteğe verilen insan reddi farklı olaylardır.
- **Yanıt gelmeyen kart:** UI deadline'ı aşarsa kart `pending_unknown`/süresi dolmuş karar bekliyor olarak işaretlenir, actor uyarılır; provider'a otomatik deny, cancel veya approve yollanmaz. Provider isteği hâlâ canlı olabilir. Timeout güvenli bir reddetme kanıtı değildir.
- **Kullanıcı approve/reject dedi, cevap yazımı belirsiz:** Karar ve provider sonucu ayrı tutulur. Response kaybolması, partial write veya timeout, provider'ın yanıtı almamış olduğu anlamına gelmez. Reconnect/readback ile aynı istek çözülemezse `response_unknown` kalır; otomatik tekrar yok.
- **Bağlantı koptu veya süreç yeniden başladı:** Açık istek `pending_unknown` olur; aynı numeric/string ID yeni generation'da eski istekle birleştirilmez. Read-only status/event/history yalnız exact approval ID ve aynı provider/session bağını kanıtlarsa state ilerletir. Provider tekrar yayınlamadı veya sorgu isteği bulamadı diye önceki karar silinmez ya da yeni approval yaratılmaz.
- **Provider başka kararla çözdü:** OpenCode TUI veya başka Codex client aynı izni çözmüş olabilir. Eşleşen provider-resolution gözlemi Yuva kartını “başka provider client'ı tarafından çözüldü; actor bilinmiyor” olarak kapatabilir; Yuva'da human approve kararı uydurulmaz. Çözüm olayı karar taşımıyorsa karar `unknown` kalır.

## Güvenlik ve kabul kapıları

- Köprü hiçbir modda `--auto`, varsayılan auto-approve handler, geniş `always` kuralı veya model metninden türeyen onay kullanmamalı. OpenCode dokümanı `--auto` modunun ask isteklerini otomatik onaylayabildiğini açıkça belirtir.
- OpenCode'da aktif izin kuralı istemi sessizce `allow` veya `deny` yapabilir; yalnız `permission.asked` beklemek yeterli değildir. Etkin config/session mode doğrulanamıyorsa onay köprüsü hazır sayılmaz.
- Hem OpenCode server `/doc` hem Codex app-server protocol/schema sürümü ve endpoint/request/response payload'ları kurulum başına sabitlenmelidir. Eski veya bilinmeyen method/field/decision fail-closed olur.
- Codex `serverRequest/resolved` tek başına hangi kararın verildiğini göstermez. OpenCode `permission.replied` da Yuva actor kimliğini kendi başına doğrulamaz. Yuva actor/audit bağı ayrı kanıt ister.
- Provider cevap writer'ı; auth, actor binding, exact request/generation korelasyonu, karar seçenekleri allowlist'i, response-lost recovery ve idempotent/unknown davranışı review edilmeden etkinleştirilmez.
- İnsan kararının Yuva'ya kaydı ile provider'a yanıtın yazımı atomik değildir. Ortak transaction/outbox yoksa iki taraf arasında kısmi commit olabilir; her iki taraf readback edilebilir olmalı, aksi durumda bilinmeyen sonuç korunmalıdır.

## Mevcut prototiplerin sınırı

Codex `retry_approval.py` ile `reconnect_state.py` request'leri gözleyip pending kayıt tutar; yanıt gönderen bir API içermez. Kopmada pending approval belirsizleşir ve connection generation bağlamı önemlidir. Bunlar bellek içi taslaklardır, kalıcı Yuva approval kuyruğu değildir. OpenCode için #472 raporu server API endpoint'ini, plugin event adlarını ve `ask`/`allow`/`deny` ayarlarını bulmuştur; hedef instance `/doc` payload'ı, event replay ve canlı cevap round-trip doğrulanmamıştır. Bu nedenle bu rapor cevap writer'ı veya üretim entegrasyonu varmış gibi sunmaz.

## Kaynaklar

- [OpenCode Permissions](https://docs.opencode.ai/docs/permissions/) — `allow`/`ask`/`deny`, `--auto`, `once`/`always`/`reject` davranışı. Resmi sayfa 2026-10-21'de kontrol edildi.
- [OpenCode Server](https://docs.opencode.ai/docs/server/) — HTTP API, `/doc` OpenAPI, auth ve server kapsamı; permission endpoint'inin `response` ve opsiyonel `remember` alanları. İzin cevabının kurulu sürüm payload'ı yine `/doc` ile doğrulanmalıdır.
- [OpenCode Plugins](https://docs.opencode.ai/docs/plugins/) — `permission.asked` ve `permission.replied` event adları; event adı kendi başına replay veya aktör doğrulaması değildir.
- [OpenAI Codex app-server overview](https://developers.openai.com/blog/codex-as-a-platform) — app-server'ın approval request'leri istemci protokolü içinde sunabildiği genel kapsam.
- [OpenAI Codex app-server protocol source](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/common.rs) — güncel upstream protokol tanımı; `main` hareketli olduğu için release kabulinde kurulu sürüm/commit sabitlenmelidir.
- Yerel prototipler: `prototypes/codex-app-server/retry_approval.py`, `reconnect_state.py`, `README.md`; ortak arayüz girdisi `docs/session-adapter-contract-474.md`; OpenCode araştırması `docs/opencode-session-bridge-options-472.md`.
