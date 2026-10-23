# Yuva #437 — Görev mutasyonlarında idempotency ve bildirim outbox tasarımı

## Karar

Görev değişikliği, idempotency sonucu ve bildirim outbox kaydı tek bir `gorevler.json` atomik commit’inde yazılsın. Mesaj JSONL’sine teslim, commit’ten sonra outbox worker tarafından yapılsın. Her mantıksal mutasyon istemcinin yeniden kullanacağı kararlı bir `operation_id` taşısın. Böylece HTTP yanıtı kaybolduğunda aynı operation tekrarlandığında görev ikinci kez değiştirilmez; önceki makbuz döndürülür ve bekleyen bildirim teslimi sürdürülür.

`operation_id` kimlik doğrulama veya yetkilendirme sağlamaz. Mevcut `kimden`/`--from` iddiaları aktör kanıtı değildir; idempotency katmanı bunları yetkili kimlik gibi kullanmamalıdır.

## Bugünkü akış ve risk

- `gorev_guncelle()` görev kaydını `.kilit` altında okuyup `gorevler.json` içine atomik yazar (`bin/yuva:122-155`, `1675-1681`). `gorev_olay_ekle()` geçiş geçmişini aynı kayda ekler (`1659-1663`).
- Komutlar bu commit döndükten sonra bildirim JSONL’sine ayrı append yapar. Bu sıra oluşturma, atama, üstlenme, teslim, ilk kontrol ve denetimde görülür (`1709-1713`, `1749-1757`, `1781-1784`, `1823-1829`, `1867-1871`, `1905-1909`). İptal şu anda inbox bildirimi üretmiyor (`1912-1927`).
- `kaydet()` replace sonrası dizin `fsync` hatasında “değişmiş olabilir” diyerek hata döndürür (`bin/yuva:141-155`). Panel köprüsü CLI non-zero sonucunu HTTP 400, `subprocess.run(..., timeout=15)` hatasını HTTP 500 yapar (`panel/server.py:801-808`). İstemci bu yanıtları kesin başarısızlık sanıp tekrar edebilir; timeout sırasında çocuk süreç mutasyonu commit etmiş olabilir.
- Task kaydı ve mesaj JSONL’si ayrı dosyalar olduğundan ikisine tek filesystem transaction’ı uygulanamaz. “Tam exactly-once” iddiası yerine atomik görev/outbox commit’i, kararlı event kimliği ve idempotent JSONL teslimi kullanılmalı.

## Önerilen kayıt modeli

`gorevler.json` köküne geriye uyumlu ek alanlar:

```json
{
  "operations": {
    "<scope>:<operation_id>": {
      "request_digest": "sha256(canonical operation and payload)",
      "status": "committed",
      "result": {"task_id": 123, "task_status": "pending_verification"},
      "event_id": "<stable event id>",
      "created_at": "..."
    }
  },
  "outbox": [{
    "event_id": "<stable event id>",
    "operation_id": "<operation id>",
    "task_id": 123,
    "kind": "task.delivered",
    "recipient": "...",
    "message": "...",
    "delivery": "pending"
  }]
}
```

Alan adları taslak sözleşmedir; mevcut `gorevler` ve her görevin `gecmis` şekli korunabilir.

Her mutasyon için tek kritik bölüm:

1. Aynı `.kilit` altında mevcut operation makbuzunu ara.
2. Makbuz varsa digest eşleşmesini denetle. Eşleşiyorsa kayıtlı sonucu döndür ve outbox teslimini devam ettir; eşleşmiyorsa HTTP 409 / `idempotency_conflict` döndür, hiçbir state değiştirme.
3. Yoksa geçiş önkoşullarını doğrula; görev durumunu ve geçmiş olayını değiştir; `operations` makbuzunu ve `outbox` olayını aynı `kaydet()` çağrısına ekle.
4. Atomik yazımın dosya ve üst dizin `fsync` adımları başarıyla dönmeden bildirimi yayımlama.
5. Commit kesinleşince outbox olayı JSONL’ye yaz. Mesaj `id` alanı outbox `event_id` olsun. `.kilit` altında bu ID’nin daha önce yazıldığını kontrol et; varsa yeniden append etme. Append’i fsync/readback ile doğruladıktan sonra outbox kaydını `delivered` yap. Append ile teslim işareti arasındaki çökmede aynı ID ile uzlaştırma tekrar append’i engeller. Append sonucu belirsizse veya JSONL’nin son satırı kısmi/bozuksa `delivery_unknown` olarak dur; hatalı tail’i incelemeden yeni satır ekleme.

Anahtar aynı operation’ın tekrarlarında sabit kalmalı; her HTTP denemesine ayrı transport/request ID verilebilir. Fingerprint operation türü, hedef task ID ve normalize edilmiş mutasyon payload’ını kapsamalı. Aynı anahtar + aynı digest önceki makbuzu verir; aynı anahtar + farklı digest reddedilir. Anahtar gelecek kimlik doğrulamasıyla kurulursa namespace’e doğrulanmış principal eklenir. Bugünkü feature-off/kimliksiz yerel akışta anahtar rastgele ve yüksek entropili olmalı; `kimden` alanı güvenilir principal namespace’i değildir.

## Yanıt sınıfları

| Durum | Makbuz/yanıt | İstemci davranışı |
|---|---|---|
| Doğrulama veya mutasyon öncesi hata | `rejected`, 4xx; mutation yok | Düzeltmeden tekrar etme |
| Görev + operation + outbox commit’i tamamlandı | `committed`, operation ID ve kayıtlı sonuç | Aynı key ile güvenle tekrar sorgulanabilir |
| Commit kesin, bildirim outbox’ta bekliyor | `committed`, `notification=pending` (202 veya açık sonuç alanı) | Yeni operation açma; aynı key ile makbuzu al; bildirim uzlaştırılır |
| Replace sonrası dizin fsync veya subprocess/HTTP sonucu belirsiz | `commit_unknown`, operation ID; mevcut köprüde 400/500 yerine ayrı semantik | Yeni key üretme ve kör tekrar yapma; aynı key ile makbuz/status uzlaştırması yap |
| Aynı key, farklı payload | `idempotency_conflict`, 409 | Yeni mantıksal işlem isteniyorsa yeni key kullan |

`commit_unknown` durumunda outbox yayımlanmaz. Aynı key ile retry önce snapshot içindeki operation kaydını arar. Kayıt varsa mutation tekrarlanmaz; directory durability yeniden denenip makbuz döndürülür. Kayıt yoksa mutation/outbox da aynı atomik snapshot içinde olmadığı için görünür state’te commit yoktur; aynı key ile işlem yeniden çalıştırılabilir. Başarılı response yazımının kendisi de bağlantı kopmasıyla kaybolabilir; aynı key’in makbuzu bu durumu çözer.

Panel `gorev_calistir()` CLI stdout’undaki serbest metin yerine yapılandırılmış operation makbuzunu HTTP yanıtına taşımalı (`panel/server.py:739-808`). `TimeoutExpired`, child return-code hatası ve `kaydet()` sonrası belirsiz dayanıklılık ayrı sınıflandırılmalı. Mutasyon commit edilmiş fakat bildirim bekliyorsa CLI bunu process failure olarak vermemeli; açık bir committed/pending makbuzu döndürmeli.

## Rollout ve uyumluluk

1. Önce yalnız veri modeli ve makbuz sorgulama sözleşmesini ekle; eski `gorevler`/`gecmis` kayıtlarını yerinde migrate etmeden oku, eksik `operations` ve `outbox` alanlarını boş kabul et. Eski JSONL kayıtları geçerli kalmalı.
2. CLI ve panel köprüsünü birlikte güncelle: panelin `operation_id` değerini CLI’ye geçirmesi için API body/header ve CLI `--operation-id` desteği ekle. UI/client bir mantıksal POST için key’i bir kez üretip timeout/bağlantı hatalarında aynen saklamalı.
3. JSONL yazıcısına sabit `event_id` ile dedupe/readback ekle; outbox kaydını ancak başarılı teslim veya aynı ID’nin mevcut olduğunun doğrulanmasıyla tamamla. Worker restart sonrası yalnız `pending`/`unknown` olayları uzlaştırsın.
4. Yeni istemcilerde mutasyon key’ini zorunlu kıl; legacy istemcileri geçiş penceresinde açıkça “idempotency garantisi yok” olarak tut, sonra kapat. Eski ve yeni writer’ların aynı dosyayı yazdığı karışık rollout’u destekleme veya eski writer’ın yeni kök alanları koruduğunu sürüm kapısıyla doğrula.
5. Makbuzları en az istemcinin maksimum retry/uzlaştırma penceresi boyunca sakla. Süre dolunca key’i unutup yeni mutation yapma riski için küçük tombstone/retention politikası belirle. Outbox olayı teslim ve denetim gereksinimi karşılanmadan silinmemeli.

## Kapsam sınırı ve kabul ölçütleri

- Idempotency güvenli tekrar ve duplicate önleme sağlar; actor authorization, admin yetkisi veya aynı UID izolasyonu sağlamaz.
- Kabulde şu yarışlar sentetik testlerle ayrıca doğrulanmalı: aynı key/same payload eşzamanlı tekrar; aynı key/different payload; task commit sonrası bildirim öncesi çökme; JSONL append sonrası delivered işareti öncesi çökme; üst dizin fsync hatası; HTTP response kaybı; CLI timeout.
- Her kabul testi görev kaydı, `gecmis`, operation makbuzu, outbox ve JSONL event ID’sini önce/sonra karşılaştırmalı. Bu tasarım notu test sonucu veya uygulama onayı değildir.
