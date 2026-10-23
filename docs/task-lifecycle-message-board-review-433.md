# Yuva #433 — Görev yaşam döngüsü, mesaj ve tahta tutarlılığı

Kapsam: CLI görev geçişleri, JSON/API köprüsü, terminal tahta ve panel görev tahtasının statik karşılaştırması. Kod değiştirilmedi; test veya runtime çalıştırılmadı.

## Bulgular

### Orta — Görev durumu ile bildirim ayrı yazılıyor; başarısızlık yanıtı commit belirsizliğini saklıyor

`gorev_guncelle()` görevi kilit altında `gorevler.json` dosyasına kaydedip kilidi bırakıyor (`bin/yuva:1675-1681`). Oluşturma, atama, teslim ve denetim bildirimleri ancak bundan sonra ayrı JSONL append'iyle yazılıyor (`1709-1713`, `1749-1757`, `1823-1829`, `1905-1909`). Bildirim append'i başarısız olursa görev durumu değişmiş olurken mesaj eksik kalır. Ayrıca `kaydet()` replace sonrası dizin fsync hatasında “değişmiş olabilir” diyerek hata veriyor (`bin/yuva:141-155`); panel köprüsü her non-zero CLI sonucunu HTTP 400 başarısızlık yanıtına çeviriyor (`panel/server.py:801-808`). Özellikle tekrar denenebilir `ekle` işleminde istemci hata görüp aynı görevi ikinci kez açabilir; teslim/denetim gibi işlemlerde de tahta durumu ilerlemiş olduğu halde hata görüntülenebilir.

**Öneri:** Görev değişikliği ve bildirim için ortak idempotent operation/event kimliği veya dayanıklı outbox kullanın. Commit sonucu belirsizse bunu API/CLI yanıtında ayrı ifade edin; istemci bunu kesin başarısızlık kabul edip körlemesine yeniden denememeli.

### Düşük — İptal durumu bildirim mesajı üretmiyor

`cmd_gorev_iptal()` `dropped` durumunu ve geçmiş olayını kaydediyor, sonra yalnız stdout'a başarı yazıyor (`bin/yuva:1912-1927`). Atama, teslim ve inceleme geçişlerinin tersine assignee'ye veya görev açana `mesaj_ekle()` çağrısı yok. Bu nedenle tahta güncel durumu gösterse de ilgili kişilerin gelen kutusunda iptal haberi oluşmuyor.

## Tutarlılığı doğrulanan noktalar

- CLI durum etiketleri ve panel etiketleri aynı altı bilinen durumu ve görevli ilk kontrol kuyruğunu temsil ediyor (`bin/yuva:41-46`, `panel/ui.html:489-494`).
- Bilinen durumlar panel tahtasında kendi sütunlarında; beklenmeyen durumlar ayrıca “Bilinmeyen durum” sütununda gösteriliyor (`panel/ui.html:920-949`). CLI tahtası da tanımadığı durumu `DURUM_AD` fallback'iyle ham değer olarak gösteriyor (`bin/yuva:1548-1559`).
- `pending_gorevli_review → pending_verification|pending_revision` ve `pending_verification → verified|pending_revision` geçişleri uygulama ve panel durumlarıyla eşleşiyor (`bin/yuva:1666-1674`, `1844-1909`). İptal terminal durum; `verified` ve `dropped` tekrar değiştirilemiyor (`1912-1924`).
- Her geçişin görev geçmişi görev kaydıyla birlikte güncelleniyor; mesajlar bunun ayrı, ikincil kaydı. Panel tahtası bu nedenle mesaj geçmişinden değil güncel `gorevler.json` durumundan besleniyor (`panel/server.py:858-861`).

## İncelenen konumlar

- `bin/yuva:1659-1681`, `1684-1927`
- `panel/server.py:739-808`, `858-861`
- `panel/ui.html:489-494`, `847-959`, `1013-1027`, `1171-1188`
