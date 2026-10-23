# Yuva #688 — `yuva wait` consumer cursor ve gözlem makbuzu sözleşmesi

**Tarih:** 2026-10-23
**Durum:** Consumer-side tasarım ve izole fixture kapsamı; production entegrasyon yok.
**Seçilen yol:** #677 uyarınca çağrı anında read-only/data-only `yuva wait`; push/provider delivery yok.

## Amaç ve iddia sınırı

Bu sözleşme, consumer'ın #614 `yuva wait` çıktısını okuyup kendi kalıcı cursor/receipt state'i ile tekrarları yönetmesi içindir. CLI reader salt okunur kalır; mesaj ve task ledger'ına ack/receipt yazmaz. Receipt store ayrıca consumer-owned bir bileşendir; CLI'dan otomatik yazılmaz.

Tek kabul edilebilir receipt türü **`read_observed`**'dır: consumer'a belirli bir message ID için untrusted/data-only envelope sunuldu ve bu gözlem için text içermeyen receipt kalıcılaştırıldı. Bu; bir agent'ın mesajı gördüğünü/okuduğunu/anladığını/kabul ettiğini, provider'a iletildiğini, task açıldığını veya görevin tamamlandığını kanıtlamaz. Producer ack, push, approval, retry, provider dispatch ve task-state mutation bu kapsam dışındadır.

## Bileşenler ve sahiplik

| Bileşen | Sorumluluk | Kalıcı veri/yan etki |
|---|---|---|
| Read-only `yuva wait` | Tam consumer roster key'i ve persisted cursor'dan sonra en fazla bir direct-target mesajı bulur; timeout veya source error ayırır. | Inbox/durum/görev/receipt yazmaz. Envelope `unverified`, `data_only`; `next_cursor` mesaj kimliği gözlem konumudur. |
| Consumer state owner | Sabit consumer ID ve persisted cursor'ı receipt store'dan okur; wait sonucunu consumer code'a verir; observation receipt'i commit eder. | Yalnız kendi private receipt store'una yazar; message text/body saklamaz. |
| Receipt store | Per-consumer ordered receipt chain, cursor compare-and-swap, dedupe, fail-closed parse/size/permission ve commit uncertainty. | Append-only `read_observed` kayıtları ve store-derived cursor. Producer/inbox/task ledger değişmez. |

Consumer identity ürün/run-time tarafından sabit ve yetkili kaynaktan atanmalıdır; `--from`, body `kimden` veya display name tek başına consumer auth kanıtı değildir. Bu protokol OS/user identity provision etmez. Aynı store'a aynı yetkiyle yazabilen süreçler aynı consumer kayıtlarını değiştirebilir veya okuyabilir; file mode same-UID süreçlerini ayırmaz.

## Receipt ve cursor kaydı

Receipt kayıtları canonical newline-delimited JSON, bounded, append-only ve text-free olmalıdır. En az aşağıdaki alanları taşır:

```text
schema_version
consumer_id
consumer_epoch
sequence
receipt_type = "read_observed"
message_id
previous_cursor
next_cursor
source_trust = "unverified"
source_class_trust = "unverified"
content_class = "data_only"
observed_at (consumer/store tarafından; yalnız diagnostic)
```

Mesaj body/metni, serbest envelope, secret/token, provider ID, task ID, approval veya `delivered/read/completed` claim'i yazılmaz. Cursor yalnız store'daki tutarlı receipt zincirinden türetilir; caller'ın belleğindeki `next_cursor` authoritative persistent cursor değildir. İlk consumer için başlangıç noktası explicit bootstrap kararıdır; implicit `None`/tail'e atlama yoktur.

## Commit sırası ve state machine

1. Consumer store'u private/valid olarak açıp kendi `consumer_epoch`, son cursor ve zincir integrity'sini okur. Eksik/bozuk/oversize/permission-unsafe store fail-closed'dur.
2. Consumer reader'a yalnız persisted cursor'ı `--after` olarak verir. Reader source'u bounded/O_NOFOLLOW salt okunur snapshot'ta inceler; source malformed ise `source_error`, süre biterse `timeout`, match bulunursa bir untrusted envelope ve `next_cursor` döndürür.
3. `timeout` durumunda cursor ve receipt store değişmez. `source_error`/cursor unavailable durumunda da receipt eklenmez; tekrar okumayı caller policy'si seçer.
4. `message` sonucu consumer'a data-only olarak gösterilebilir. Consumer, envelope untrusted olduğunu korur; content komut/approval olarak execute edilmez.
5. Store'a `expected_cursor=previous_cursor`, `message_id` ve `next_cursor` ile `observe()` çağrısı yapılır. Store aynı lock altında expected/current cursor karşılaştırır, consumer/message duplicate'ini arar ve text-free receipt'i append/fsync eder. Bu işlem producer ack değildir.
6. Receipt commit kesin başarıysa yeni store-derived cursor bir sonraki wait için kullanılabilir. Commit belirsizse `commit_unknown`: cursor ilerlemiş varsayılmaz, yeni bir message ID ile atlanmaz ve blind append retry yapılmaz. Salt-okunur exact receipt/cursor readback gerekiyorsa, sonuç unresolved ise owner müdahalesi.

`yuva wait` CLI ile receipt store arasında tek atomic transaction yoktur. Receipt commit'ten önce CLI mesajı döndürüp consumer process çökerse aynı message yeniden gözlenebilir; dedupe tekrarlı `read_observed` append'ini engeller. Consumer'a metni gösterme ile receipt commit arasındaki kesin sıralama uygulamanın consumer API tasarımında açık tutulmalıdır; receipt kaydı kullanıcıya/agent'a teslim garantisi vermez.

## Replay, cursor kaybı ve restore davranışı

| Durum | Beklenen sınıflama | Cursor/receipt etkisi |
|---|---|---|
| Aynı consumer, aynı message ID ve aynı active receipt chain | `duplicate_observation` | İkinci receipt yok; cursor mevcut store değerinde. `read_observed` gözlemidir, second delivery acknowledgement değildir. |
| İki consumer aynı message ID gözlüyor | Her consumer için bağımsız `read_observed` | Consumer ID/cursor chain'leri ayrı; birinin receipt'i diğerinin cursor'ını ilerletmez. |
| Aynı message ID source'tan replay gelir ama active receipt yok | Reader tekrar sunabilir; store mutation öncesi ID/cursor conflict kurallarına bakar. | Uyumlu `previous_cursor` varsa tek receipt; ID zaten zincirdeyse dedupe. Aynı ID ile farklı cursor/epoch çelişkisi `store_conflict`, no-write. |
| Caller cursor kayıp, `None`/yanlış/geriye cursor gönderiyor | `cursor_unavailable`/`cursor_conflict` | Store ile compare tutmaz; no-write, latest tail'e sessiz bootstrap yok. |
| Receipt tail yarım/JSON bozuk, duplicate field, schema/size/owner/mode/link hatası | `store_corrupt`/`store_unavailable` | Parse/append durur; repair, truncate veya temiz store ile devam yok. Ham içerik loglanmaz. |
| Wait sonlu sürede eşleşen mesaj bulmuyor | `timeout` | Receipt yok, cursor unchanged. Timeout mesaj yokluğunu kalıcı olarak kanıtlamaz. |
| Source unreadable/oversize/malformed ya da wait kaynak cursor'ını doğrulayamıyor | `source_error`/`cursor_unavailable` | Timeout veya successful observation diye sınıflanmaz; store yazımı yok. |
| Receipt append/fsync sonucu belirsiz | `commit_unknown` | Aynı operation kör tekrarlanmaz; salt-okunur exact readback ile çözülemiyorsa unresolved. Receipt varsa yalnız `read_observed`. |
| Receipt store eski backup'tan restore edilmiş | `restore_untrusted`/cursor state unknown | Store içi sequence eski ama geçerli olabilir; local chain tek başına rollback'i göremez. Consumer wait durur, no auto rewind/bootstrap. |
| Store ve consumer copy birlikte kayıp/eski snapshot'a dönmüş; external anchor yok | `history_unknown` | Geçmişin ileri alınmış receipt/cursor'ı ispatlanamaz. Operatör explicit new epoch/reset baseline kararı olmadan okumaya devam yok. |

Restore sonrası safe recovery: store'ları offline koru, son güvenilir consumer epoch/cursor'ı store dışı backup/audit ile karşılaştır, exact line/message state belirsizse `unknown` bırak. Eski bir backup'ın receipt ve cursor'ı birlikte geri getirdiği halde anchor yoksa otomatik tespit garantisi verilemez; bu limitation saklanamaz. Yeni consumer epoch/reset ancak explicit owner kararı ve documented starting boundary ile açılır. Eski mesajlar yeniden sunulabilir; bu delivery duplication'dır, agent receipt değil.

## İzole fixture kabul kapsamı

Fixture yalnız `TemporaryDirectory` altındaki işaretli private store, sentetik message envelope'ları ve source reader fixture'ı kullanır. Gerçek `YUVA_DIR`, inbox, panel, provider, agent runtime, task writer veya host key kullanmaz. Store parser'ı text-free alanları enforce eder; receipt çıktısı gerçek message body sentinel'ını içermez.

Gerekli senaryolar:

1. **Initial cursor/bootstrap:** Explicit approved initial cursor ile bir consumer açılır; implicit `None` ve unregistered consumer için no-write/error.
2. **Happy observation/restart:** Wait message → receipt append → store objesi yeniden kurulması; cursor aynı `next_cursor`; receipt fields data-only/unverified; message text yok.
3. **Same ID replay:** Aynı consumer/message eski `--after` ile tekrar görülür; `duplicate_observation`, receipt satır sayısı sabit, cursor ileri gitmez/çift append yok.
4. **Per-consumer isolation:** İki consumer aynı ID gözler; iki ayrı chain/cursor, exact consumer key dışında cross-read/write yok.
5. **Cursor loss/conflict:** Caller `None`, stale/old cursor veya ileri/yanlış cursor verir; no-write ve `cursor_unavailable/conflict`.
6. **Timeout:** Sonlu wait timeout döner; receipt bytes ve cursor unchanged; timeout source error'dan ayrıdır.
7. **Unknown/source error:** Incomplete/malformed/oversize source, symlink/owner-invalid inbox veya cursor bulunmaması; receipt no-write, success/timeout claim yok.
8. **Store corruption:** Malformed/partial JSONL tail, duplicate JSON field, bad schema/type, over-limit bytes/records, unsafe root/mode/link; no repair/truncate/append, original bytes unchanged.
9. **Append uncertainty:** Injected append/fsync/response failure: `commit_unknown`; automatic second append yok; exact readback classification committed/unresolved; message text kayda girmiyor.
10. **Restore/rollback:** Eski ama kendi içinde valid receipt snapshot + cursor; external anchor yoksa `restore_untrusted/history_unknown`, no auto continuation. Current cursor surviving while store regressed must conflict. Store+caller birlikte restore durumunun local-only olarak tespit edilemediği açıkça gösterilir.
11. **Malformed trust claims:** Envelope `verified`, `approval`, `operator`, `agent`, task-complete veya provider-delivered claim taşısa bile output/receipt `unverified`, `data_only`, `read_observed`; source claim yetki üretmez.
12. **Read-only invariants:** Inbox/durum/görev bytes çağrı öncesi/sonrası aynı; receipt store dışındaki dosya değişmez; body/path/provider payload receipt'e yazılmaz.

Fixture pass'i consumer-owned production persistence, crash durability, OS custody, anti-rollback, consumer UI delivery veya provider integration kanıtı değildir. #587/#623 testleri önceki fixture kanıtlarıdır; bu görevde yeniden çalıştırılmadı.

## Consumer API ve olası hata cevapları

Önerilen consumer call result enum'u sınırlı olsun: `read_observed`, `duplicate_observation`, `timeout`, `source_error`, `cursor_unavailable`, `cursor_conflict`, `store_corrupt`, `store_full`, `commit_unknown`, `restore_untrusted`. Sabit reason dışında exception/path/store line/message body dışarı verilmez.

`read_observed` yalnız bir receipt ledger event'i ve ilerlemiş store cursor'ı demektir. Consumer UI bunu “agent okudu” gibi göstermemelidir. Mesaj text'ini consumer'a sunma/read receipt persist etme ayrımı açık olmalı; uygulama bunu atomik/at-least-once güvence diye sunamaz.

## Kaynaklar ve kapsam sınırı

- `docs/yuva-wait-prototype-554.md` — info-mode, untrusted envelope ve read-only reader.
- `docs/yuva-wait-persistent-receipt-587.md` — text-free receipt store, expected cursor, duplicate ve corrupt/commit-unknown davranışı.
- `docs/yuva-wait-cli-fixture-614.md` — CLI contract, bounded source snapshot ve timeout/cursor semantiği.
- `docs/yuva-wait-duplicate-observation-receipt-623.md` — wait replay + receipt dedupe birleşik TemporaryDirectory fixture sınırı.
- Yuva #677 — verified kararı: çağrı anında read-only/data-only wait; push/provider delivery yok.

Bu teslim tasarım/fixture sözleşmesidir. Wait CLI, receipt store, provider, agent veya production path bağlanmadı; auth, service, task, inbox ve live data değiştirilmedi.
