# Yuva #677 — Chat komutunun agente ulaşması: MVP seçenek kararı

**Karar:** İlk sürüm için mevcut, çağıranın başlattığı read-only `yuva wait`
yolu korunsun. Bu, mesajı hedef agent'ın okuma anında data-only gözlemesine
yardım eder; agent'ı uyandırmaz ve provider session'a gönderim yapmaz. Tmux
enjeksiyonu seçilmedi. Provider session API'si ileriki bir aşama için daha
yapılandırılmış taşıma adayıdır; credential, session binding, kalıcı attempt
receipt ve operator approval kapıları tamamlanmadan prompt dispatch açılmaz.

Bu karar notu #553/#554/#603 ve #614/#623 kanıtlarını karşılaştırır. Kaynak,
prototip ve fixture belgeleri okundu; tmux/provider'a bağlanma, latency ölçümü,
test veya canlı agent dispatch'i yapılmadı.

## Bugünkü MVP'nin gerçek sınırı

- `bin/yuva wait --from <exact-id> --after <message-id>` read-only CLI
  adapter'ı #614'te geçici inbox ile sınanmıştır. Mesaj `data_only` ve
  `unverified` projection olarak döner; görev, rol, inbox veya provider state'i
  değiştirmez.
- CLI timeout'u 0–300 saniye, poll interval `(0, 2]` saniye aralığındadır;
  fixture varsayılan poll'u 0.25 saniyedir. Mesaj ancak wait çağrısı sırasında
  ve sonraki poll/read'de görülür. Bu push/uyanma değildir.
- CLI kalıcı consumer cursor'ı veya receipt yazmaz. #623, ayrı fixture receipt
  store'u ile replay dedupe ve `cursor_unavailable` dallarını sınar; receipt
  CLI'ın kendi kalıcı ack'i değildir ve agent'ın mesajı gerçekten okuyup
  anladığını kanıtlamaz.
- #603, `read_observed` makbuzunun metinsiz olmasını ve trust'ın
  `unverified/data_only` kalmasını sınar; bu da provider delivery veya agent
  acceptance kanıtı değildir.

## Seçenek karşılaştırması

| Seçenek | Gecikme | Duplicate / unknown receipt | Source trust | Operator approval ve yan etki | Karar |
|---|---|---|---|---|---|
| **`yuva wait` polling** | Poll aralığı kaynaklı gözlem gecikmesi vardır; 0.25 sn varsayılan ve 2 sn üst sınırdır. Her poll bounded local JSONL read yapar. Ölçülmüş p95/p99 veya end-to-end latency yoktur. Wait çağrısı yoksa gecikme sınırsızdır. | Aynı `--after` replay yapabilir. #623'te ayrı fixture receipt store aynı message ID'yi ikinci receipt'e çevirmiyor; CLI receipt/cursor persist etmediğinden bu garanti CLI özelliği değildir. Eksik cursor `cursor_unavailable`; bu mesaj yok veya teslim edildi demek değildir. | Mesaj `source_trust=unverified`, `content_class=data_only` kalır. `kimden`, `verified`, approval veya actor iddiaları yükseltilmez. | Provider'a yazma, uyandırma veya görev mutation'ı yok. Çalışma/approval yetkisi atanmış kanonik task ve ayrı policy'de kalır. | **İlk MVP**: en küçük yan etki ve mevcut çalışan info-mode yolu. Yalnız gözlem. |
| **tmux / terminal input bridge** | Tuş/metin enjeksiyonu hızlı olabilir; agent'in input'u okuması veya işleme latency'si bilinmez. Repo'da tmux bridge/benchmark yoktur. | Pane'e yazma başarı cevabı terminalde kabul/okuma/işleme makbuzu değildir. Session/pane yeniden bağlanması, terminal state'i veya response loss sonrası güvenilir duplicate dedupe/readback kanıtı yoktur; belirsiz write `unknown` kalmalıdır. | Terminale yazılan chat hâlâ untrusted data'dır. Pane/session adı veya terminal prompt'u actor/auth kanıtı değildir. | Yanlış pane, açık shell/prompt'a yazma ve istemeden komut yürütme riski vardır. Exact host/session/pane allowlist'i ve kullanıcı onayı olmadan göndermemeli; `send-keys` başarısı tool/approval yetkisi vermez. | **Seçilmedi**: düşük taşıma gecikmesi olasılığı, zayıf hedef/receipt ve daha yüksek side-effect riski karşılığında geliyor. |
| **Provider session API** | Local server/API round-trip'i hızlı olabilir ancak provider turn/queue/stream gecikmesi değişkendir. Bu depoda canlı ölçüm yoktur. HTTP 204 veya RPC response yalnız taşıma/endpoint yanıtıdır; turn completion değildir. | En güçlü typed correlation olanağı var: `operation_id`, `attempt_id`, connection generation, session/thread/turn ve event/message ID. Fakat provider request ID veya OpenCode `messageID` için remote idempotency garantisi belgelenmemiştir. Partial/full write sonrası timeout `unknown`; read-only status/history ile reconcile et, yokluk resend izni değildir. Yeni deneme ayrı attempt ve operator kararı ister. | Gönderilen Yuva mesajı data-only/untrusted kalır; provider output'u da task/approval authority üretmez. Session ID yalnız provider oturum bağını gösterir; Yuva task/principal değildir. | Credential, sabit endpoint/session/workspace binding, capability allowlist, kalıcı privacy-safe receipt, read-only reconcile ve ayrı insan approval gerekir. Provider permission cevaplama kapalı varsayılan olmalı. | **İleriki aşama adayı**: yalnız observe-only entegrasyon ve güvenlik/receipt kapıları geçtikten sonra prompt writer değerlendirilir. |

Latency satırları **tasarım/konfigürasyon düzeyindeki nitel karşılaştırmadır**;
ölçülmüş SLA, performans sonucu veya canlı kurulum iddiası değildir.

## Seçilen yol ve kabul sırası

1. **Şimdiki MVP:** Agent/consumer `yuva wait`'i açıkça çağırır. Bir direct-target
   mesaj en fazla bir kez döner; gözlem cursor'ı `next_cursor` olarak gösterilir.
   Broadcast otomatik kişisel kuyruğa girmez. Mesaj data-only kalır.
2. **Consumer cursor/receipt:** Entegrasyon bunu ekleyecekse durable store'un
   sahibi (agent consumer mı Yuva mı), cursor/ack transaction sınırı, duplicate
   policy, retention ve loss/restore sonucu tanımlanır. `read_observed` yalnız
   gözlem makbuzudur; agent-read, provider-accepted veya task-complete durumuna
   yükseltilmez.
3. **Dikkat/uyandırma ihtiyacı:** Tmux'a geçmeden önce provider'ın desteklediği
   typed session API/broker yolu incelenir. Provider capability, sürüm, hedef
   session/workspace, credential custody ve read-only reconcile önceden
   sabitlenir. Gerçek API `/doc`/protokol şeması sürüme göre doğrulanmadan
   endpoint veya event field varsayılmaz.
4. **Prompt write kapısı:** Prompt dispatch için her mantıksal ingress'e kalıcı
   `operation_id`, her bilinçli gönderime ayrı `attempt_id`, redacted request
   fingerprint'i ve provider correlation kimlikleri yazılır. Authorization her
   retry'da tekrar yapılır. Başarısız/unknown gönderime otomatik resend yok;
   yeni attempt ancak kayıtlı operator kararıyla açılır.
5. **Approval kapısı:** Provider tool/permission isteği önce observe-only,
   exact session/request correlation ile gösterilir. İnsan kararı Yuva'da
   ayrı kaydedilir. Provider'a approve/reject capability'si ayrı, kapalı
   varsayılan ve ayrıca kabul edilmiş işlem olur; chat içeriği, model output'u,
   timeout veya provider'ın kendi `permission.replied` olayı insan kararının
   yerine geçmez.
6. **Dış eylem sınırı:** Prompt'tan tool/shell çalışması, permission yanıtı,
   Yuva task mutation'ı veya `verified` geçişi otomatik üretilmez. Task
   completion, output'ın Yuva'ya kaydı ve reviewer kararı ayrı makbuz/lifecycle
   aşamalarıdır.

## Unknown ve receipt kararı

Taşıma sonucu için en az şu ayrım korunmalı:

| Durum | Ne kanıtlar | Güvenli devam |
|---|---|---|
| `not_started` / request kesin yapılmadı | Provider çağrısı başlamadı | Aynı operation/attempt içinde başlatma değerlendirilebilir. |
| `write_started` veya partial write | Çağrı byte'ları çıkmış olabilir | `unknown`; kör retry yok. |
| `sent_observed` / korele endpoint yanıtı | Request endpoint'e taşındı/yanıtlandı | Provider acceptance veya turn completion sayılmaz; provider event/status ile korelasyon gerekir. |
| `accepted` / `running` / terminal provider event | Yalnız typed provider request ve aynı session/thread/turn ile korele gözlem | Yuva output delivery veya task review değildir; sonraki aşamayı ayrıca kaydet. |
| Status/history'de event bulunamadı | Yalnız mevcut readback'te görünmedi | Gönderilmedi kanıtı değildir; `unknown` korunur. |
| Exact Yuva output receipt | Çıktı Yuva/artifact store'a kaydedildi | Reviewer/task state yalnız canonical Yuva transition ile değişir. |

## Kaynak dayanakları

- [#553 MVP kararı](chat-command-delivery-mvp-553.md) — pull-based `wait`,
  data-only mesaj ve sonraki provider seçeneklerinin sınırı.
- [#554 wait prototipi](yuva-wait-prototype-554.md),
  [#614 CLI fixture](yuva-wait-cli-fixture-614.md) — polling, timeout,
  cursor, salt-okunur reader ve CLI yan etkisizliği.
- [#603 end-to-end fixture](yuva-wait-end-to-end-fixture-603.md),
  [#623 replay/receipt fixture](yuva-wait-duplicate-observation-receipt-623.md)
  — fixture receipt kapsamı ve gerçek agent ack olmadığı.
- [#489 provider receipt correlation](session-response-yuva-receipt-correlation-489.md)
  ve [#493 OpenCode retry riski](opencode-messageid-retry-risk-493.md) —
  typed operation/attempt/provider IDs, unknown ve no-blind-retry.
- [#490 provider approval kararı](provider-approval-bridge-decision-490.md)
  — observe-only, closed-default human approval boundary.
- [#504 persistent receipt store](session-bridge-persistent-receipt-store-504.md),
  [#509 adapter review](opencode-http-adapter-security-review-509.md) —
  receipt kalıcılığı, endpoint/session bağlama ve adapter residual risk'leri.

Bu karar #553'te seçilen `wait` yönünü güncel #614/#623 kanıtıyla netleştirir;
provider veya tmux entegrasyonu başlatmaz ve bu seçenekleri üretim için onaylamaz.
