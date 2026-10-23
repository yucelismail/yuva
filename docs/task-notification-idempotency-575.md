# #575 — Görev commit'i ve sohbet bildirimi için idempotency sözleşmesi

Bu not, mevcut görev mutasyonu ile sohbet bildirimi arasındaki hata sınırını
ve hedeflenen operation/outbox davranışını belirler. Yalnız tasarım kararıdır;
bu görev kapsamında canlı gönderim, `gorevler.json` değişikliği veya worker
uygulaması yoktur.

## Mevcut sınır

`bin/yuva` içindeki `gorev_guncelle()` görev snapshot'ını `.kilit` altında
atomik değiştirir. Görev oluşturma, atama, claim, teslim, ilk kontrol ve denetim
komutları bundan sonra `mesaj_ekle()` ile ayrı `mesaj.jsonl` append'i yapar.
Dolayısıyla görev kaydı commit edilmişken mesaj append'i veya komut yanıtı
kaybolabilir. Aynı komutun tekrar çalışması yeni görev ID'si, yeni geçmiş
olayı veya yinelenen bildirim üretebilir. `gorevler.json` şu an operation
makbuzu/outbox saklamaz. İptal komutu şu an bildirim üretmiyor; bu tasarım
ileride bildirim eklenirse aynı sözleşmeyi uygular.

Bu durum #437 tasarımı ve #452 hata matrisiyle uyumludur. #561 görev
snapshot'ının atomik yazımını ve commit/bildirim ayrımını doğrular, fakat
idempotency makbuzu veya outbox uygulamaz.

## Normatif operation sözleşmesi

1. İstemci bir mantıksal mutasyon için bir kez yüksek entropili `operation_id`
   üretir; timeout/bağlantı kesintisinde aynı ID ve aynı normalize edilmiş
   payload ile tekrarlar. `operation_id` yetkilendirme veya actor kimliği
   değildir; `--from`/`kimden` key namespace'i ya da sahiplik kanıtı olmaz.
2. Canonical writer ortak `.kilit` altında operation receipt'ini arar.
   Kayıtlı `request_digest` aynıysa görev geçişini tekrar uygulamadan kayıtlı
   sonucu döndürür ve bekleyen bildirimi uzlaştırır. Aynı ID farklı digest'e
   bağlıysa `idempotency_conflict`/409 döner; hiçbir alan değiştirilmez.
3. Receipt bulunmazsa payload ve geçiş önkoşulları doğrulanır. Başarılı geçiş,
   `gecmis` olayı, receipt ve gerekiyorsa notification outbox kaydı tek
   `gorevler.json` snapshot'ına eklenip aynı atomik replace/fsync yolunda commit
   edilir. Bu commit kesinleşmeden sohbet JSONL'sine bildirim yazılmaz.
4. Receipt en az `operation_id`, canonical digest, operation türü, hedef task
   ID, `committed` sonucu, sonuç task durumu, geçiş event ID'si ve notification
   event ID/durumu taşır. Outbox metni, alıcısı ve türü commit anında
   sabitlenir; worker sonradan değişken task alanlarından yeniden üretmez.
5. Outbox `pending` olayı ayrı worker tarafından teslim edilir. Bildirim
   JSONL'sinde `id=event_id` kullanılır. Worker append'ten önce aynı ID'nin
  varlığını ortak `.kilit` altında tam kayıt kaynağında arar; yoksa aynı kilit
  tutulurken append eder, varsa append'i atlayıp outbox'ı `delivered` yapar.
  Append sonrası crash/restart aynı ID ile dedupe edilir. Bounded panel/CLI
  tail'i tek başına dedupe kanıtı değildir.
6. JSONL tail kısmi/bozuksa veya append sonucu belirsizse outbox
   `delivery_unknown` olur ve worker yeni append'i durdurur. Tail incelenmeden
   kör retry yapılmaz. Görev commit'i kesin, bildirim sonucu belirsizse
   operation `committed` kalır; mutasyon reddedilmiş gibi gösterilmez.
7. `os.replace` sonrası directory `fsync`, child CLI veya HTTP response
   belirsizliğinde durum `commit_unknown`'dır. Aynı ID ile tekrar önce canonical
   defterde receipt'i arar; kayıt varsa dayanıklılığı uzlaştırıp kayıtlı sonucu
   döndürür, yoksa aynı ID ile mutation'ı tekrar değerlendirebilir. Yeni ID ile
   kör tekrar yoktur.
8. Başarılı receipt/tombstone retention'ı retry penceresi bitmeden silinmez.
   İlk MVP'de receipt'ler görev defteriyle birlikte saklanır; otomatik TTL
   temizliği yoktur. Yalnız doğrulama/önkoşul hatasıyla reddedilen ve hiçbir
   kalıcı yan etkisi olmayan istek ID'yi tüketmez. Aynı ID'nin reddedilmiş
   payload sonrasında farklı bir payload ile kullanılması ancak ilk denemede
   receipt yazılmadığı kesin ise kabul edilir.

## Kayıt taslağı

`gorevler.json` kökünde append-only/korunur makbuz haritası ve outbox listesi
önerilir. Alan adları uygulama öncesi doğrulanabilir; davranış sözleşmesi
normatiftir.

```json
{
  "operations": {
    "task.mutate:<operation_id>": {
      "request_digest": "sha256(canonical request)",
      "operation": "task.deliver",
      "task_id": 42,
      "status": "committed",
      "result": {"task_status": "pending_verification"},
      "transition_event_id": "task-event-id",
      "notification_event_id": "message-event-id",
      "notification": "pending"
    }
  },
  "outbox": [{
    "event_id": "message-event-id",
    "operation_id": "<operation_id>",
    "task_id": 42,
    "kind": "task.delivered",
    "recipient": "@reviewer",
    "message": "...",
    "delivery": "pending"
  }]
}
```

Digest, operation türü, canonical task ID ve normalize edilmiş iş etkisi
payload'ını kapsar. Alias çözümü, varsayılan alanlar, string/boolean türleri ve
Unicode canonicalization uygulama sözleşmesinde sabitlenmelidir. Bir
`operation_id` yalnız tek bir logical operation scope'unda kullanılır; bir
kaç deneme aynı ID'yi, farklı mantıksal işlem yeni ID'yi kullanır.

## Hata ve retry matrisi

| Hata/yarış | Görev ve makbuz | Bildirim | Yanıt ve güvenli adım |
|---|---|---|---|
| Ön doğrulama veya geçiş reddi | Görev değişmez; receipt yok | Outbox yok | Domain/validation hatası. Önkoşulu düzelt; aynı ID kalıcı duruma bağlanmadı. |
| Aynı ID + aynı digest tekrarı | İlk commit'in sonucu değişmez; ikinci mutation yok | Aynı event ID uzlaştırılır | Receipt sonucu döner; `pending` ise yalnız bildirim teslimi sürdürülür. |
| Aynı ID + farklı digest | Görev ve ilk receipt korunur | Değişmez | `idempotency_conflict`/409; yeni mantıksal işlemse yeni ID. |
| Temp yazımı/replace öncesi hata | Eski snapshot korunur; yeni receipt yok | Yok | Eski snapshot doğrulanmadan kesin ret denmez; aynı ID ile uzlaştır/tekrar et. |
| Replace sonrası directory `fsync` belirsiz | Yeni snapshot görünür olabilir; durability bilinmiyor | Outbox worker bekler | `commit_unknown`; aynı ID ile receipt/state sorgula, yeni ID üretme. |
| Görev + receipt + outbox commit, worker öncesi crash | `committed` receipt durur | `pending`, JSONL'de yok | Restart sonrası worker aynı event'i append eder; task operation tekrarlanmaz. |
| JSONL append sonrası `delivered` işaretinden önce crash | Receipt `committed`; outbox `pending` görünebilir | Event ID JSONL'de vardır | Readback ID'yi bulur, ikinci satır eklemeden `delivered` işaretler. |
| Append sonucu veya JSONL tail belirsiz/bozuk | Görev commit'i kesin kalır | `delivery_unknown`; otomatik append durur | Aynı event ID ile uzlaştır; tail incelemesi/onayı olmadan retry yok. |
| HTTP yanıtı kaybolur veya panel child timeout olur | Makbuz varsa tek mutation commit'tir; yoksa sonuç `commit_unknown` olabilir | Receipt durumuna göre pending/delivered/unknown | Status/aynı ID sorgusu; yeni operation veya kör task retry yok. |
| Receipt retention süresi biter | Eski ve yeni retry ayırt edilemeyebilir | Eski event teslim edilmiş olabilir | MVP otomatik silmez. İleride tombstone ve maksimum retry penceresi beraber tasarlanır. |

## Duplicate önleme kabul ölçütleri

- Aynı ID/digest için eşzamanlı iki çağrı tek task transition, tek history olayı,
  tek receipt ve tek outbox/event ID bırakır; ikisi de aynı kayıtlı sonucu alır.
- Aynı ID/farklı digest çağrılarından en fazla biri commit eder; diğeri conflict
  alır ve kazananın verisini değiştiremez.
- Görev commit'i sonrası yanıt veya bildirim kaybında aynı ID sonucu
  uzlaştırır; ikinci task, history olayı veya JSONL satırı oluşmaz.
- JSONL append sonrası crash'te event ID readback ikinci append'i önler.
- Kısmi tail, commit belirsizliği ve receipt bulunamaması başarı/ret varsayımına
  çevrilmez. Operation ID hiçbir durumda actor/task/provider yetkisi oluşturmaz.

Uygulama kapısı: task CLI, panel bridge, operation status sorgusu ve JSONL
dedupe/worker birlikte tasarlanıp fixture ile sınanmadan bu sözleşme canlı
bildirim gönderimine açılmamalıdır. Eski writer'ların yeni root alanlarını
koruduğu garanti edilmeden karışık release kullanımı da kabul edilmez.
