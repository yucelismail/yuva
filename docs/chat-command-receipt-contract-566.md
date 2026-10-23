# Yuva #566 — Chat komut idempotency ve agent receipt sözleşmesi

**Durum:** Önerilen sözleşme ve sentetik sequence fixture'ı. Provider, panel,
Yuva servisi veya gerçek agent session'ına bağlanılmadı; gönderim/retry
çalıştırılmadı.

## Karar

Chat kaydı, mantıksal komut operation'ı, gönderim attempt'i, taşıyıcının kabulü,
agent session receipt'i, provider turn sonucu, çıktı kaydı ve Yuva reviewer
kararı ayrı nesne/kanıt olarak kalmalıdır. Tek bir `delivered`/`done` biti bu
kanıtları birleştirmemelidir.

Gönderim yaşam döngüsü task'te istenen beş değeri kullanır:

| Durum | Kesin anlam | İzin verilen sonraki adım |
|---|---|---|
| `queued` | Yuva source message ID'si ve değişmez request digest'i bir operation'a bağlandı; taşıyıcı write başlamadı. | İlk attempt için durable intent commit et. Aynı source ID/digest tekrarında mevcut operation'ı döndür. |
| `send_attempted` | Attempt kaydı write öncesinde kalıcılaştı ve taşıyıcıya dış etki başlama sınırı geçildi. | Yalnız aynı attempt'e bağlı kabul/ret kanıtı bekle veya salt okunur reconcile yap. |
| `accepted` | Belirtilen taşıyıcı/consumer, aynı operation + attempt için pozitif kabul kanıtı verdi. Kabul katmanı (`wait_consumer`, `provider_http`, `provider_rpc`) ayrıca kayıtlıdır. | Agent receipt ayrı beklenebilir; bu statü tek başına modele ulaştı/çalıştı demek değildir. |
| `unknown` | Write, kabul, receipt veya durable kayıt sonucu etki oluşmuş da olabilecek biçimde belirsizdir. `unknown` son bilinen state'i silmez. | Yeni send yok. Aynı operation ile read-only receipt/history uzlaştır; çözülemezse operator kararı bekle. |
| `rejected` | Aynı attempt için taşıyıcının istek etkisi başlamadığını garanti eden, şemaya uygun ve korele ret kanıtı var. | Kayıtlı ret görünür; değişen/yeniden gönderilecek istek yeni operation veya açık yeni attempt kararı gerektirir. |

Durum projection'ı attempt geçmişini saklar; yeni attempt eskisini silmez.
Operation `accepted` sayılabilmesi için pozitif kabulün yanında başka
etkilenmiş olabilecek unresolved attempt bulunmamalıdır. Önceki attempt
`unknown` iken bir insan yeni attempt'i onaylarsa yeni attempt kabul edilse bile
operation toplamı duplicate riski çözülene kadar `unknown/conflict` kalır.
`unknown` terminal değildir; ancak otomatik retry izni de değildir.

## Kimlikler ve receipt alanları

Önerilen minimal immutable zarf:

```json
{
  "source": {
    "yuva_instance": "local-yuva",
    "message_id": "typed-id-preserved",
    "source_digest": "sha256:redacted-canonical-request"
  },
  "operation_id": "stable-for-this-source-message",
  "request_digest": "sha256:canonical-payload",
  "target": {
    "agent_claim": "worker-label",
    "provider": "opencode|codex-app-server|yuva-wait",
    "provider_instance": "instance-namespace",
    "session_ref": "opaque-session-ref"
  },
  "attempts": [{
    "attempt_id": "new-for-each-conscious-send",
    "state": "queued|send_attempted|accepted|unknown|rejected",
    "acceptance_layer": null,
    "transport_receipt_ref": null,
    "agent_receipt": {
      "state": "none|received|started|unknown|conflict",
      "receipt_id": null,
      "session_binding_ref": null,
      "evidence_ref": null,
      "trust": "unverified"
    }
  }]
}
```

`operation_id` aynı logical source tekrarında sabittir; her yeni bilinçli
gönderim `attempt_id` alır. `request_digest` aynı operation ID'nin farklı
payload ile sessizce yeniden kullanılmasını önler. Kararlı ID + aynı digest
idempotent replay'dir; aynı ID + farklı digest `operation_conflict` verir ve
taşıyıcı çağrısı açmaz. Provider request/message ID'si, Yuva message ID'sinden
ayrı namespaced opaque referanstır; kendi başına uzak idempotency anahtarı
değildir.

İşçi adı veya `--from` actor claim'dir, principal kanıtı değildir. Agent
receipt'i doğrulanmış sayılacaksa exact `operation_id + attempt_id`, hedeflenen
session generation, assignee/agent bağlamı ve receipt kaynağı dış katmanca
doğrulanmalı; salt metin içindeki “aldım” yeterli değildir. Bu kanıt yoksa
receipt `unverified` veya `none` kalır.

## Kanıt katmanlarını ayırma

| Gözlem | Kaydedilecek katman | Kanıtlamadığı |
|---|---|---|
| Yuva JSONL mesaj satırı ve `message_id` | `source_recorded` | Agent'e push, okuma, provider kabulü |
| `yuva wait` sorgusunun mesajı seçip stdout/envelope döndürmesi | `read_observed` + consumer/cursor metadata | Modelin/session'ın metni aldığı veya işleyeceği; `--from` kimliği doğrulamaz |
| Provider HTTP/JSON-RPC kabul cevabı | `transport_acceptance=accepted` ve endpoint/generation/ref | Agent/model receipt'i, turn başlama/tamamlama |
| Exact session-bound agent ack | `agent_receipt=received` (kanıt/binding ile) | Task completion, provider terminal sonucu, Yuva teslim/review |
| Provider `started`/terminal event | `provider_turn=running/completed/failed/...` | Yuva artifact receipt veya reviewer `verified` |
| Yuva `son_okuma` watermark'ı | Chat kullanıcı okuma görünümü | Agent okuması veya agent receipt'i |
| `presence_state=online`/heartbeat | Ayrı presence gözlemi | Bu operation/session'ın receipt'i; güncel kaynakta presence `unknown` |

`agent_receipt` değerleri agent bildirimi/kabul iddiasını tutar; tool output,
model metni, screenshot veya `son_okuma` ile sentezlenmez. `completed` bu
receipt state listesinde yoktur: agent ack'i çalışma bitişi yerine geçmez.
Provider turn terminali, output/artifact kalıcı kaydı ve Yuva task review'ı
ayrı alanlardır.

Chat gövdesi, içindeki “sistem talimatı”, rol/onay iddiası veya prompt injection
metni dâhil, `data_only` kalır. Receipt yalnız exact zarfın hangi taşıyıcıya ya
da doğrulanmış oturuma ulaştığını gösterir; mesaj içeriğine talimat, tool,
permission veya görev mutation yetkisi vermez. Eylem için kanonik görev
kapsamı ve ayrı action authorization gerekir.

## Duplicate, timeout, ack loss ve retry kuralları

1. **Duplicate source ingest:** `(yuva_instance, typed_message_id)` + aynı
   canonical/redacted digest mevcut operation'a bağlanır; ikinci attempt yok.
   Aynı source ID farklı içerik/digest ise conflict, hiçbir provider write yok.
2. **Write öncesi kesin ret:** attempt `send_attempted` olmamış ve taşıyıcı
   çağrısı başlamamışsa `queued` kalabilir. Gönderim kararı verildiğinde attempt
   ve immutable intent, dış write'dan önce durable commit edilir.
3. **Kesin 0-byte:** Aynı transport frame için sıfır byte yazıldığı kanıtlanırsa
   aynı attempt içinde taşıma katmanı retry'si düşünülebilir. Bu provider'ın
   aynı request'i almadığını kanıtlayan transport kanıtıdır; provider
   `messageID` dedupe varsayımı değildir.
4. **Partial/full write, timeout, lost response, disconnect, restart:**
   `unknown`. Otomatik tekrar yok. Önce tam provider instance/session ve eski
   attempt'e bağlı salt okunur status/history/event reconcile yapılır. “ID
   bulunamadı” veya timeout negatif gönderilmedi kanıtı değildir.
5. **Provider accepted:** Exact attempt'e korele pozitif endpoint/RPC kabulü
   `accepted` olur. Model cevap vermese de transport kabulü geriye alınmaz;
   `agent_receipt=none` kalabilir. HTTP 204, yazım cevabı veya JSON-RPC success
   tek başına agent receipt değildir.
6. **Explicit rejected:** `rejected`, yalnız method-specific sözleşme hatanın
   bu attempt'te hiçbir iş başlatmadığını kanıtlarsa verilir. Generic HTTP 500,
   exception, parse/ack kaybı ve timeout `unknown`'dır.
7. **Agent ack kaybı:** operation accepted ise kabul state'i korunur;
   receipt katmanı ayrı `unknown` olur. Receipt ID/digest ile durable readback
   yap. Ack kaydı kesin commit olmuşsa aynı receipt ID/digest tekrarında no-op;
   farklı digest conflict'tir. Readback yok/sonucu belirsizse agent'a komutu
   yeniden göndermek yerine receipt unknown kalır.
8. **İnsan onaylı yeni deneme:** Uzlaştırma sonuçsuzsa operator olası duplicate
   etkisini açıkça kabul etmeden yeni provider attempt açılmaz. Açılırsa yeni
   `attempt_id` ve yeni provider request ID; önceki unknown kayıt immutable
   kalır, karar/gerekçe/actor/risk receipt'e bağlanır.

## `yuva wait` ve provider prototiplerine bağlanan sequence

`yuva wait` #553 kararında önerilmiştir; mevcut CLI'de uygulanmış değildir.
`wait` pull/okuma yoludur: mesajın seçilip dönüşü `read_observed` olabilir,
fakat tek başına `accepted` ya da agent session receipt'i olmaz. Ayrı,
idempotent consumer ack yolu eklense bile `--from` bir doğrulanmış session
binding'i kanıtlamaz.

```mermaid
sequenceDiagram
  participant C as Yuva chat JSONL
  participant O as Durable operation/attempt ledger (öneri)
  participant W as yuva wait consumer (öneri)
  participant A as Agent session/provider adapter
  participant R as Receipt reconciler (read-only)

  C->>O: message_id + immutable digest
  O->>O: queued commit (aynı ID/digest replay => aynı operation)
  W->>O: poll/read --from worker --after cursor
  O-->>W: envelope + operation_id (read_observed; receipt değil)
  W->>O: prepare exact envelope dispatch
  O->>O: attempt_id + send_attempted commit before external write
  W->>A: exact envelope (yalnız bağlı agent wrapper varsa)
  alt pozitif provider kabulü
    A-->>O: correlated accept (provider ref / generation)
    O->>O: accepted; agent_receipt ayrı none
    opt exact session-bound ack (varsa)
      A->>O: receipt_id + operation_id + attempt_id
      O->>O: durable idempotent ack commit
      O->>O: agent_receipt=received; provider turn/output ayrı kalır
      O--xA: ack response lost
      A->>O: same receipt_id readback/retry
      O-->>A: existing receipt; no-op
    end
  else transport response kaybı / bağlantı kopması
    A--xO: acceptance result belirsiz
    O->>O: unknown (otomatik resend yok)
    R->>A: status/history lookup (salt okunur)
    A-->>R: positive exact match ya da inconclusive/not_found
    R->>O: yalnız korele kanıtı ekle; not_found => unknown
  end
```

### Sentetik fixture/sequence örneği

Bu örnek sözleşme yürüyüşüdür; test veya gerçek provider işlemi değildir.

| Sıra | Fixture olayı | Operation/attempt sonucu | Agent receipt |
|---|---|---|---|
| 1 | `yuva_instance=local`, typed `message_id="m-42"`, digest `d1` ingest edilir. | `operation_id=op-m42`, `queued`; attempt yok. | `none` |
| 2 | Aynı `m-42/d1` tekrar ingest edilir. | `op-m42` mevcut makbuzu döner; yeni attempt/write yok. | Değişmez |
| 3 | `m-42` farklı digest `d2` ile gelir. | `operation_conflict`; transport çağrılmaz. | Değişmez |
| 4 | `yuva wait` envelope'ı döndürür; sadece `--from` label var. | `read_observed`; provider mode'da dispatch kabulüne çevrilmez. | `none/unverified` |
| 5 | Fixture adapter `attempt=a1` ve `send_attempted` commit eder, fake HTTP timeout verir. | `unknown`; no retry. | `none` |
| 6 | Read-only reconcile exact provider/session ref içinde `m-42` kaydını bulamaz. | `unknown` kalır; `not_found` retry izni değildir. | `none` |
| 7 | Operator yeni denemeyi açıkça kabul ederse `attempt=a2` oluşturulur. | `a1=unknown` korunur; `a2` ayrı kaydedilir; olası duplicate riski operation projection'ında kalır. | `none` |
| 8 | Fake `a2` için provider accept ve sonra exact receipt `ack-9/digest-r` verir; ack HTTP cevabı kaybolur. | `a2=accepted`; duplicate ack readback aynı receipt'i döndürür/no-op. | Tam session binding varsa `received`, yoksa unverified. |

## Mevcut prototiplere eşleme ve sınır

| Prototip | Bu sözleşmeye katkı | Kullanılmayan garanti |
|---|---|---|
| `prototypes/session-bridge/outbox.py` | Stable event ID + payload digest; same-key replay/conflict; exception/ambiguous callback `unknown`; yalnız explicit `not_sent_proven` retry; `not_found` unknown kalır. | Bellek içi; process restart, durable delivery ve authentication sağlamaz. |
| `prototypes/opencode-adapter/` | `prompt_async` response-observed/unknown, bounded status/history/SSE gözlemi ve read-only reconcile. | 204 veya `messageID` idempotency/agent ack değildir; event replay ve schema canlıda doğrulanmış değil. |
| `prototypes/codex-app-server/` | Typed JSON-RPC ID + connection generation korelasyonu; ambiguous write/no blind retry; turn receipt ve Yuva output/review ayrımı. | Stdio projection only; provider connection, durable ledger, output writer yok. |
| `prototypes/mock-adapter/` | Sentetik accepted/running/completed/failed lifecycle ve duplicate/conflict fixture şekli. | Fake transport accepted'i gerçek agent receipt'i veya kalıcı store yapmaz. |
| `yuva wait` (#553) | Provider bağımsız pull/`read_observed` yüzeyi için gelecek entegrasyon noktası. | CLI komutu, persistent cursor/ack store ve provider dispatch mevcut değil. |

Kalıcı uygulama öncesi durable operation+attempt+ack ledger seçimi, writer
CAS/lock ve commit unknown davranışı, ID/digest canonicalization+retention,
provider version/schema capability, agent/session binding ve receipt
authorization, output privacy ve restart reconcile ayrı kabul kapılarıdır. Bu
belge hiçbirini uygulamış veya mevcut prototiplerin test edildiğini iddia etmez.

## Dayanaklar

- `docs/chat-command-delivery-mvp-553.md` — `yuva wait` kararı ve güven sınırı.
- `docs/persistent-session-receipt-contract-527.md` — operation/attempt,
  provider/output/task katmanları ve restart unknown davranışı.
- `docs/session-adapter-contract-474.md` — provider bağımsız send observation
  ve reconcile sınırı.
- `docs/opencode-messageid-retry-risk-493.md` — message ID ve timeout sonrası
  kör retry riski.
- `prototypes/session-bridge/README.md`, `prototypes/session-bridge/outbox.py`;
  `prototypes/opencode-adapter/README.md`;
  `prototypes/codex-app-server/receipt-integration-contract.md` ve
  `receipt-event-order-matrix.md`; `prototypes/mock-adapter/README.md`.
