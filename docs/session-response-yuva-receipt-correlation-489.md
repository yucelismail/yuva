# Yuva #489 — Provider yanıtı ve Yuva makbuzu korelasyon sözleşmesi

Kapsam: Yuva kullanıcı mesajından provider oturum isteğine, gözlenen provider olaylarına, çıktı kaydına ve Yuva teslim/review durumuna kadar kimlik ve durum bağları. Bu belge bir entegrasyon sözleşmesi önerisidir; prototiplerin üretime bağlı olduğu veya exactly-once sağlandığı anlamına gelmez. Canlı provider, test veya Yuva runtime'ı çalıştırılmadı.

## Kimlik katmanları

Tek bir `status` alanı; mesajın kaydedilmesini, provider isteğinin taşınmasını, model turunu, çıktının Yuva'ya kaydını ve review'ı kanıtlayamaz. Bunları ayrı kayıt ve durumlar olarak tut.

| Katman | Korelasyon anahtarı | Kanıtladığı şey |
| --- | --- | --- |
| Yuva ingress mesajı | `(yuva_instance, typed_message_id)` | Kullanıcı mesajı Yuva'da kaydedildi. Provider'a gönderildiğini göstermez. |
| Mantıksal operation | Kalıcı `operation_id` → ingress mesajı | Aynı Yuva mesajının yeniden işlenmesini aynı mantıksal gönderim/uzlaştırma kaydına bağlar. Aynı operation başka parametreyle kullanılırsa conflict ve gönderim durur. |
| Bilinçli deneme | Yeni `attempt_id`, varsa `run_id`/`task_id` | Operation için ayrı bir yürütme kararı. Önceki denemeler korunur; yeniden adlandırılmaz veya üstüne yazılmaz. |
| Taşıma isteği | Provider türü, hedef, `connection_generation`, yön ve typed yerel request ID | Hangi bağlantı/istek gözleminin eşleştiğini belirtir. Yerel JSON-RPC ID veya HTTP isteği uzak idempotency anahtarı değildir. |
| Provider nesnesi | Codex: `thread_id`, `turn_id`, `item_id`; OpenCode: server/session ve şemada gözlenen message/part ID | Provider tarafında kabul/çalışma/çıktı gözlemini belirli oturuma bağlar. Eksik veya çelişkili kimlik başarı kanıtı değildir. |
| Çıktı teslim makbuzu | `(operation_id, attempt_id, provider object IDs, artifact/message ID veya digest)` | Çıktı Yuva'ya veya belirlenen artifact store'a kalıcı kaydedildi. Provider'ın çıktıyı üretmesi bunu kanıtlamaz. |
| Yuva görevi ve review | Yuva `task_id` ve görev geçmişi | Yuva teslim kuyruğu ve reviewer kararı. Provider terminal olayı `pending_verification` ya da `verified` yazmaz. |

Yuva'da task/run yoksa varmış gibi kimlik uydurma; yalnız operation ve attempt scope'u kullan. Görev bağını, mesajı işleyen güvenilir orkestratör kurmalı; model/provider metninden task veya yetki türetilmemeli.

## Önerilen operation zarfı

Kalıcı receipt store her denemede en az şu alanları append-only gözlemlerden türetmelidir:

```text
operation_id
source = {yuva_instance, yuva_message_id: typed ID}
attempt_id, optional task_id/run_id
provider = {kind, configured_endpoint_identity, session/thread identity}
connection_generation
request = {direction, typed_request_id when available, method, redacted_params_digest}
transport_state = not_started | write_started | not_sent_proven | sent_observed | unknown
provider_state = unknown | accepted | running | terminal_observed
provider_terminal_outcome = exact observed provider outcome, if any
output_delivery = not_recorded | recorded | unknown
yuva_task_state = separate canonical Yuva state, if task-bound
observations[] = timestamp, source, IDs, payload digest, validation/correlation result
```

`attempt_id` yeni bir bilinçli gönderim denemesini belirtir. Aynı frame için taşımanın kesin sıfır byte yazdığını kanıtladığı tekrar, aynı attempt içindeki transport retry'sidir. Kısmi yazım, başarılı yazımdan sonra kayıp yanıt, flush belirsizliği, timeout veya süreç çökmesi sonucu belirsiz bırakır.

## Sağlayıcı farkları

| Özellik | Codex app-server | OpenCode server |
| --- | --- | --- |
| İstek kimliği | JSON-RPC request ID. Eşleşme `(connection_generation, direction, JSON türü korunmuş request_id)` ile yapılır; `7` ile `"7"` farklıdır. | HTTP istek/yanıtı ve hedef session. Kullanılan endpoint'in gerçek sürüm şeması sabitlenir; varsa request/response message ID alanı yalnız o şemada gözlendiyse kaydedilir. |
| Provider oturum/turn kimliği | `thread_id` ve `turn_id`; item ID'leri çıktı/approval bağlamını daraltabilir. Request ID bunların yerine geçmez. | `session_id`; message/part ID varsa provider event/history içindeki şema alanından alınır. Session ID Yuva task/operation değildir. |
| Kabul ve ilerleme kanıtı | Korele `turn/start` yanıtı `accepted`; aynı thread/turn için `turn/started` `running`; `turn/completed` terminal gözlemi sağlar. JSON-RPC error tek başına turn yaratılmadı anlamına gelmez. | `/session/:id/prompt_async` için belgelenen `204` HTTP yanıtı endpoint isteğine yanıt alındığını gösterir; Yuva makbuzu, provider turn terminali veya uzak dedupe garantisi değildir. Senkron message yanıtı ve session history ayrı provider kanıtlarıdır. |
| Olay akışı/reconnect | JSON-RPC response ve server notification'ları generation ile ilişkilendirilir. Yerel prototipin reconnect ledger'ı bellektedir; kalıcılık sağlamaz. | `/event` SSE ve `GET /session/status`, `GET /session/:id/message` gözlem/uzlaştırmaya girdi olabilir. #472'de incelenen resmi belgeler replay cursor/sequence veya kesinti boyunca eksiksiz event teslimi garantisi belirtmiyor; hedef `/doc` şeması sürüme bağlıdır. |
| Uzak idempotency | JSON-RPC request ID eşleştirme kimliğidir; uzak idempotency kanıtı değildir. | `messageID` veya session message ID alanının idempotency anahtarı olduğu #472 kaynaklarında doğrulanmamıştır. Bu alanı idempotency garantisi gibi kullanma. |

Codex adapter taslağı, OpenCode araştırma notu ve mevcut Yuva receipt tasarımları prototip/tasarım girdileridir; birleşik ve kalıcı üretim receipt sistemi değildir. OpenCode endpoint/payload alanları hedef server'ın `/doc` tanımıyla doğrulanmalıdır.

## Geçiş ve karar kuralları

1. **Yuva mesajını al:** Yuva mesajının kalıcı ID'sini ve redacted içerik fingerprint'ini kaydet. `recorded` yalnız Yuva ingress'i kanıtlar. Aynı typed Yuva ID aynı operation'ı bulur; değişmiş method/parametreyle tekrar kullanım `operation_conflict` üretir ve dış çağrı yapmaz.
2. **Denemeyi hazırla:** Orkestratör açık bir `attempt_id` ve provider hedefi seçer. Provider türü/sürümü, session veya thread bağlamı ve yeni bağlantı generation'ı zarfla kaydedilir. Provider isteğine ait sırlar log veya makbuza yazılmaz.
3. **Taşıma sonucunu kaydet:** Kesinlikle çağrı yapılmadan önce `not_started`; çağrı başlatıldıktan sonra `write_started`; yalnız sıfır byte yazıldığı kesin kanıtlanırsa `not_sent_proven`; tam yazım/flush gözlenirse `sent_observed`; tüm belirsiz durumlarda `unknown`. `sent_observed` provider kabulü değildir.
4. **Yanıt ve olayları ilişkilendir:** Yanıt aynı generation ve typed request ID'ye, event ise provider session/thread/turn/message kimliğine uymalıdır. Tam eşleşmeyen, birden fazla olası attempt'e bağlanan veya eski generation'dan gelen gözlemi orphan olarak koru; state'i `unknown` bırak. Yakın zaman, aynı prompt metni veya “tek açık iş var” varsayımı korelasyon kanıtı değildir.
5. **Duplicate ve sıra dışı olaylar:** Kaynak kararlı event ID sağlıyorsa `(provider, session, event namespace, source_event_id)` ve canonical payload fingerprint'i kullan. Aynı ID+aynı içerik tekrar gözlemidir; aynı ID+farklı içerik conflict'tir ve iki kanıt da korunur. Kararlı event ID yoksa payload fingerprint'i yalnız eş içerik adayıdır, event kimliği değildir; observation saklanır, reducer aynı kanıtı idempotent uygular. Arrival order gerçek provider sırası sayılmaz.
6. **Final output'u ayır:** Provider terminal gözlemi, Yuva'ya çıktı kaydı değildir. Çıktıyı redaction'dan geçir, yazma sonucunu ayrı makbuzla `recorded` yap. Yuva görevi için ancak kendi teslim geçişi `pending_verification` üretir; reviewer `verified` kararı ayrı yetkili Yuva geçişidir.

## Timeout, unknown ve reconnect

- **Timeout / kayıp yanıt:** Gönderimden önce kesin 0-byte kanıtı varsa aynı attempt ve request bağlamında transport retry değerlendirilebilir. Yazım başladıktan sonra timeout, kısmi yazım, yanıt kaybı veya flush belirsizliği `unknown`'dır. Kör resend yok.
- **Uzlaştırma:** Önce read-only provider status/history sorgusuyla aynı provider kimliğini ara. Yalnız operation'a zaten kesin bağlanmış provider message/turn ID veya tekil, protokolce doğrulanabilir bir bağ bulunursa attempt state'i ilerlet. Bulunmaması gönderim yapılmadığının kanıtı değildir; sonuç `unknown` kalır. Yuva output makbuzu da ayrıca okunur.
- **Reconnect:** Her yeni bağlantı/process generation yeni ID alır. Önceki generation'ın açık isteği/approval'ı yeni nesildeki aynı yerel ID ile eşleştirilmez. Yeniden bağlanınca status/history okunur, gözlemler append-only eklenir ve mevcut operation/attempt ile uzlaştırılır. SSE replay cursor veya sağlayıcıya özgü kalıcılık garantisi doğrulanmadıkça aralıkta olay kaybı olabileceği kabul edilir.
- **Yeni denemeye geçiş:** `unknown` eski attempt kapatmaz. Yeni bilinçli deneme ancak açık orkestratör/operatör kararıyla yeni `attempt_id` ve yeni provider request kimliği alır; eski attempt kanıtları silinmez. “Bulamadım” tek başına güvenli retry izni değildir.
- **Conflict:** Aynı operation'a farklı provider hedefi, aynı attempt'e çelişen thread/turn/message bağı veya aynı turn için farklı terminal outcome gelirse receipt `unknown/conflict` olur. Son gelen veya ilk gelen olayı sessizce kazanan yapma.

## Son kullanıcıya gösterilecek durum

Arayüz aşağıdaki aşamaları birbirinden ayrı göstermelidir:

1. “Yuva mesajı kaydedildi” — provider'a gönderildi demek değildir.
2. “Gönderim sonucu belirsiz / provider kabulü gözlendi / provider çalışıyor / provider terminal sonucu gözlendi” — attempt ve kanıt zamanı ile.
3. “Yanıt Yuva'ya kaydedildi” — yalnız output delivery receipt `recorded` olduğunda.
4. “Yuva incelemesi bekliyor / onaylandı / revizyon istendi” — yalnız canonical Yuva task state'ine göre.

Unknown, başarılı, başarısız, gönderilmedi veya tamamlandı diye kısaltılmaz. Provider terminal outcome da başarı olarak yeniden adlandırılmaz; Codex `failed`/`interrupted` gibi sonuçlar ve OpenCode event/status değerleri kendi protokol adlarıyla, gözlem kaynağıyla gösterilir.

## Kaynak temeli ve sınır

- `docs/opencode-session-bridge-options-472.md`: OpenCode resmi Server/CLI/Permissions/Plugins/TUI belgelerinden yapılan 2026-10-21 araştırma özeti; SSE replay ve `messageID` idempotency garantisinin doğrulanmadığını, `/doc` sürüm kontrolü gerektiğini belirtir.
- `prototypes/codex-app-server/receipt-integration-contract.md` ve `receipt-event-order-matrix.md`: operation/attempt/generation, typed request ID, turn, output delivery ve Yuva review ayrımlarını önerir.
- `prototypes/codex-app-server/README.md`, `reconnect_state.py` ve `yuva-receipt-comparison-473.md`: Codex gözlem/reconnect taslaklarının bellek içi ve entegrasyonsuz sınırlarını gösterir.
- Bu sözleşme exactly-once, provider dedupe, kalıcı receipt store veya çalışan Yuva/provider bağlantısı iddiası taşımaz. Bunlar ayrı uygulama ve kabul kapılarıdır.
