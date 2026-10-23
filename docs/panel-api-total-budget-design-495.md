# `/api/veri` toplam JSON bütçesi tasarımı (#495)

- **Durum:** Tasarım notu; uygulama veya yük testi değildir.
- **Kapsam:** `/api/veri` ve `/veri` snapshot gövdesi; `durum.json`, `gorevler.json`, sohbet ve ekran alanlarının birlikte oluşturduğu kaynak/bellek yükü.
- **İlişki:** #459 yalnız `ekranlar` map'ini en çok 2 MiB ile sınırlar. Bu not onun yerine geçmez; son HTTP JSON gövdesine ayrıca tavan getirir.

## Mevcut durum

`panel/server.py:1400-1434` kullanıcı map'ini, bütün görev listesini, en çok 200 sohbet mesajını ve `tum_ekranlar()` sonucunu tek snapshot'ta toplar. #459 ekran map'ine ayrı 2 MiB JSON bütçesi koyar (`docs/panel-api-screen-budget-459.md`); kullanıcı ve görev listesi için benzer seçim sınırı yoktur. Sohbet okuyucusu ham tail'i en çok 2 MiB ve kayıt başına 64 KiB ile sınırlar (`panel/server.py:777-785`), fakat normalize edilmiş sohbet listesinin ve tüm cevabın seri hale getirilmiş boyutuna tavan koymaz. `oku()` durum/görev JSON dosyalarını bütünsellikle belleğe alıp parse eder (`panel/server.py:285-307`), `_gonder()` da JSON gövdesinin tamamını üretip UTF-8 baytlarını ayrıca bellekte tutar (`panel/server.py:1551-1565`). Bu yüzden ekran sınırı tüm yanıtı veya snapshot tepe belleğini sınırlamaz.

## Önerilen sınırlar

Başlangıç için aşağıdaki sınırlar tek bir ayarlı bütçe tablosu olarak tanımlansın. Bayt sayımı JSON serileştirmesinden sonra UTF-8 wire gövdesi üzerinden yapılsın; Python nesne boyutunun tahmini bu sayım yerine kullanılmasın.

| Bölüm | Önerilen alan bütçesi | Tek kayıt bütçesi | Seçim kuralı |
| --- | ---: | ---: | --- |
| `kullanicilar` | 1 MiB | 64 KiB | Kimlik anahtarına göre artan sözlük sırası |
| `gorevler` | 2 MiB | 256 KiB | Aktif görevler (`assigned`, `pending_revision`, `pending_verification`) önce; sonra `pending`; sonra diğerleri. Her sınıfta kaynak listedeki sondan başa seçim, çıktı kaynak sıra düzeninde. |
| `mesajlar` | 2 MiB | 128 KiB | En yeni mesajlardan başlayarak seçim; çıktı kronolojik sıra düzeninde. Mevcut en çok 200 kayıt sınırı korunur. |
| `ekranlar` | 2 MiB | #459 sınırları | Mevcut #459 deterministik ekran seçimi ve map bütçesi uygulanır. |
| Sabit alanlar + metadata | 128 KiB rezerve | — | Tek, küçük ve sabit şekilli metadata nesnesi; atlanan kayıt ID'lerini listeleme. |
| **Tüm JSON yanıtı** | **8 MiB kesin tavan** | — | Bölüm payları toplamından bağımsız son güvenlik kapısı. |

Bölüm bütçeleri toplamı ve rezerv, 8 MiB global tavanın altında kalır; fark final serileştirmesi, alan anahtarları ve beklenmeyen büyüme için paydır. Üst sınırlar ileride ölçümle değiştirilebilir, ama global 8 MiB tavan bölüm ayarlarından bağımsız ve aşılmaz kalmalıdır. Her kayıt bütçesi, alan adı/ayraç dahil o kaydın nihai JSON gösteriminin UTF-8 baytlarıdır. Bütçeyi aşan kayıt kesilmez; tüm nesne atlanır ve sonraki adaylar değerlendirilir.

## Üretim algoritması

1. `durum` ve `gorevler` için kaynak dosyaları okurken boyutu sınırlı oku (`limit + 1` bayt). Başlangıç kaynak tavanı `durum.json` için 4 MiB, `gorevler.json` için 16 MiB olsun. Tavan aşılırsa sessiz varsayılan ya da yarım JSON üretme; aşağıdaki açık kaynak-hatasını döndür. Dosyalar bozuk veya beklenmeyen şemadaysa mevcut katı hata davranışını koru.
2. Her kayıt adayını tek tek JSON'a serileştirip bayt say; tek kayıt ve ilgili alan bütçeleriyle sığanları seç. Ekran alanını #459'un ürettiği haliyle al; yeni toplam bütçe hesabı `ekranlar_meta` ve map şeklini korusun.
3. Snapshot'ın üst seviye alanlarını mevcut isim ve tiplerle tut: `ok`, `simdi`, `online_sn`, `rev`, `kullanicilar` nesnesi, `gorevler` dizisi, `mesajlar` dizisi, `ekranlar` nesnesi. Yeni `snapshot_meta` alanı ekle. Metadata `partial`, `included`/`omitted` sayaçları, uygulanan limitler ve sabit kodlu `partial_reasons` değerlerini taşısın. İçerik veya kayıt ID listesi taşımasın; metadata kendi rezervine sığmalı.
4. JSON gövdesini **tek kez** kesin cevap bütçesi altında üret. Bölüm seçimleri ve sabit metadata 8 MiB tavanı garanti eder; son serileştirme yine de limiti aşarsa en düşük öncelikli tam kayıtları deterministik biçimde çıkarıp yeniden serileştir. Alan tiplerini hiçbir durumda `null` veya metinle değiştirme. En küçük sabit zarf dahi sığmazsa veri döndürülmüş izlenimi vermek yerine sınırlı servis hatası ver.
5. Aynı kilitli snapshot içinden alınan `rev` ve kalan alanlar tek cevapta kalmalı. Bütçe nedeniyle kısmi sonuç üretmek disk durumunu değiştirmemeli, mesaj yazmamalı veya cursor/offset ilerletmemeli. Ekran seçiminin kendi mevcut rotasyon davranışı #459'un sorumluluğunda kalır.

Alan payı içinde bir kaydın atlanması aynı alandaki daha küçük sonraki kayıtların seçilmesini engellememeli. Görev öncelik sırası ve mesaj newest-first seçimi sonuç setini belirler; dönülen liste sırası UI'nın alışık olduğu sıra olarak korunur. Önceliği eşit kayıtlarda deterministik kaynak sırası/kimlik sırası kullanılır.

## Metadata ve hata sözleşmesi

Başarılı, kısmi yanıtta HTTP **200** ve `ok: true` korunur; `snapshot_meta.partial: true` eksikliği açıkça bildirir. Örnek:

```json
{
  "ok": true,
  "snapshot_meta": {
    "schema_version": 1,
    "partial": true,
    "included": {"kullanicilar": 40, "gorevler": 180, "mesajlar": 80},
    "omitted": {"kullanicilar": 0, "gorevler": 12, "mesajlar": 0},
    "partial_reasons": ["tasks_output_byte_limit"]
  }
}
```

Kodlar alan kapsamlı ve sınırlı enum olmalı: `users_output_byte_limit`, `tasks_output_byte_limit`, `messages_output_byte_limit`, `record_size_limit`, `final_response_byte_limit`, `record_encoding_error`. #459 `ekranlar_meta.partial` alanı değişmeden kalır; genel `snapshot_meta.partial` ekran kısmi olduğunda da true olur ve `screen_output_partial` gibi bir neden eklenebilir.

Hata ayrımı:

- Kayıt bütçesinden dolayı kayıt atlama: `200`, tutarlı alan tipleri, `snapshot_meta.partial=true`.
- Durum/görev kaynak dosyası boyut tavanı: küçük, sabit gövdeli `503` (`ok:false`, `hata:"snapshot_source_limit"`, kaynak alanı ve limit); bu veri kısmiymiş gibi gösterilmez.
- Bozuk JSON, şema veya disk okuma hatası: mevcut görünür kalıcı durum hatası yolu (`500`) korunur; boş varsayılana sessiz düşülmez.
- Kodlama hatalı tek kayıt: bütün cevabı düşürmek yerine tam kayıt atlanır ve kısmi metadata işaretlenir. Zarf/kilit alanı kodlanamıyorsa sınırlı `500`.

`206 Partial Content` önerilmez: mevcut tarayıcı `fetch()` yolu `Response.ok` ve `d.ok` denetimi yapar (`panel/ui.html:533-553`); 200 ile zarf uyumluluğu korunurken kısmi olma bilgisi gövdede taşınır. Hatalı/bozuk snapshot için UI'nın mevcut bağlantı-hatası görünümü çalışmaya devam eder.

## UI ve geriye uyumluluk

Mevcut UI `ekranlar_meta.partial` uyarısını gösteriyor (`panel/ui.html:1844-1857`), fakat genel snapshot kısmi olmasını henüz denetlemiyor. Toplam tavanı etkinleştirecek değişiklik aynı dağıtımda `snapshot_meta.partial` için görünür bir genel uyarı eklemeli. Kısmi sonuçta UI, görülen adetleri toplam kayıt sayısı gibi sunmamalı; “gösterilen” diye etiketlemeli ve eksik kullanıcı/görev yokluğundan çevrimdışı, atanmadı veya tamamlandı sonucu çıkarmamalı. Eksik veriye bağlı seçenekleri kullanan yazma/atama eylemleri, tam snapshot gelene kadar kapalı olmalı ya da hedef kaydı ayrı ve tam doğrulayan bir uçtan çekmelidir.

Üst seviye mevcut alanların isimleri ve JSON tipleri korunur; ek metadata tam snapshot durumunda da mevcut olur (`partial:false`). Bu JSON şekli açısından eklemeli uyumluluktur, ancak eski istemciler bilinmeyen `snapshot_meta` alanını görmezden gelip kısmi listeyi tam sanabilir. Bu nedenle sunucu tarafı kısmi yanıtı devreye alınmadan önce birlikte dağıtılan UI güncellenmeli; bilinen harici istemciler de metadata sözleşmesine geçirilmelidir. Şema/tip değiştiren yeni `/api/veri` sözleşmesi yapılmamalıdır.

## Bellek sınırı ve uygulama kapısı

8 MiB wire tavanı tek başına heap sınırı değildir. `json.loads` Python nesnelerini kaynak metninden daha büyük yapabilir; bugünkü `oku()` tüm kaynak JSON metnini ve parse edilmiş ağacı birlikte tutabilir. Önerilen 4/16 MiB kaynak tavanları her okumanın ham girdisini sınırlayıp en kötü durum girdisini sonlu kılar, ama tam RSS bayt tavanı ispatlamaz. Kayıt başına ve kaynak başına sınırlar, büyük tek görevin response alanını yutmasını ve tüm gövdenin büyümesini engeller.

Kesin süreç belleği limiti gerekiyorsa üretim tasarımında durum/görev JSON'u için sabit kaynak tavanları yanında kayıt akışlı parser veya izole worker/RSS limiti ve kalibre edilmiş ölçüm gerekir. Standart `json.loads` ile yalnızca son yanıtı budamak, parse tepe belleği problemini çözmüş sayılmaz. Bu işte test/runtime talep edilmediği için kaynak tavanları başlangıç tasarımıdır; canlı veri boyutları ve UI dağıtım yolu ölçülüp gözden geçirilmeden kod değişikliği yapılmamalıdır.

## Kapsam dışı

Bu belge yalnız tasarımdır. Kod, panel davranışı veya veri şeması değiştirilmedi; test ve runtime çalıştırılmadı. Retention/silme politikası, sayfalı yeni API, ekranların #459 seçimi ve `GET /api/veri` erişim yetkisi bu tasarımın kapsamı dışındadır.

## Dayanak

- `docs/panel-api-screen-budget-459.md` — mevcut ekran map bütçesi ve kısmi metadata.
- `panel/server.py:285-307, 777-851, 1400-1434, 1551-1565, 1610-1622` — kaynak yükleme, mesaj ve ekran sınırları, snapshot ve HTTP JSON serileştirmesi.
- `panel/ui.html:533-553, 571-596, 1844-1858` — fetch hata davranışı, snapshot tüketimi ve ekran kısmi uyarısı.
- `docs/local-api-get-snapshot-decision-455.md` — snapshot hassasiyeti ve erişim sınırının bu boyut bütçesinden ayrı olduğu.
