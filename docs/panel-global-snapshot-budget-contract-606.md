# Panel snapshot global response bütçesi ve partial sözleşmesi (#606)

**Tarih:** 2026-10-23
**Durum:** Uygulamaya hazır tasarım/acceptance sözleşmesi; üretim davranışı değiştirilmedi.
**Kapsam:** `GET /api/veri` ve uyumlu alias `/veri` için UTF-8 JSON wire boyutu, deterministik kısmi seçim, hata zarfı ve UI yorumu.

## Karar

Tek bir `/api/veri` gövdesi JSON serileştirmesi ve UTF-8 kodlamasından sonra en fazla **8 MiB (8,388,608 byte)** olabilir. Bütçe karakter veya Python nesne boyutu üzerinden ölçülmez. Gövdenin tamamı tek response olarak kalır; `206 Partial Content` kullanılmaz.

Her başarılı yanıtta mevcut alan ve tipler korunur; ek `snapshot_meta` alanı tam yanıtta da bulunur. Kısmi snapshot `HTTP 200`, `ok: true`, `snapshot_meta.partial: true` ile döner. Atlanan içerik kırpılmaz; bir kayıt bütçeye sığmıyorsa bütünüyle atlanır ve aynı gruptaki sonraki küçük adaylar denenir. Kaynak verinin okunamaması veya asgari zarfın bütçeye sığmaması başarı gibi gösterilmez.

Bu byte tavanı heap/RSS sınırı, anonim GET yetkilendirmesi veya veri gizliliği kontrolü değildir.

## Bütçe tablosu

Bölüm bütçeleri nihai kompakt JSON içindeki grup alanının UTF-8 byte maliyetini ve o grupta seçilen item'ları kapsar. Üst seviye anahtar, ayraç, `snapshot_meta` ve sabit alanlar ayrıca ayrılmış rezerve dahildir. Bütün bölümler toplamı ve rezerv 8 MiB altında kalır.

| Grup | Başlangıç bütçesi | Tek item tavanı | Seçim sırası |
|---|---:|---:|---|
| `kullanicilar` | 1 MiB | 64 KiB | Kimlik anahtarına göre artan UTF-8 sırası |
| `gorevler` | 2 MiB | 256 KiB | Önce açık işler; sonra arşiv. Açık işlerde `assigned`, `pending_revision`, `pending_verification`, `pending_gorevli_review`, `pending` sırası; her sınıfta kaynak sırasının sonundan geriye seçim. Çıktı seçilen kayıtların kaynak sırasını korur. |
| `mesajlar` | 2 MiB | 128 KiB | En yeni kayıt önce seçilir; çıktı kronolojik sırayı korur ve mevcut 200 kayıt tavanını aşmaz. |
| `ekranlar` | 2 MiB | #459 satır/dosya sınırları | Mevcut round-robin dosya seçimi ve ekran-map bütçesi korunur. Global seçim ekran dosyalarını ayrıca düşürürse metadata kısmi dosya sayısını belirtir. |
| Sabit zarf + metadata | 128 KiB rezerv | — | Sabit alanlar, sayaçlar, limitler ve sınırlı neden enum'ları. Kimlik, görev ID'si veya metin listesi yok. |
| **Global gövde** | **8 MiB kesin üst sınır** | — | Son kapı; bölüm bütçeleri uygulanmış olsa bile zorunlu. |

`2 MiB × 3 + 1 MiB + 128 KiB = 7.125 MiB`; 8 MiB ile kalan fark, JSON anahtarları/ayraçları ve sabit alanların hesabı içindir. Serileştirme biçimi `ensure_ascii=False`, `separators=(",", ":")` olarak sabitlenir; limit bu gerçek wire biçiminde hesaplanır. Bir item maliyetine map anahtarı veya dizi ayraçlarının payı dahil edilir.

`durum.json` için 4 MiB, `gorevler.json` için 16 MiB ham kaynak okuma tavanı önerilir. Okuyucu `limit + 1` byte kontrolü yapar; tavan aşılınca JSON parse etmez, sessiz boş varsayılana veya partial state'e düşmez. Bu kaynak tavanları da heap kullanımı için kesin RSS garantisi değildir.

## Tutarlı seçim ve response üretimi

1. Kullanıcı, görev, mesaj ve ekran kaynakları aynı snapshot revizyonuna bağlanır; mevcut kilitli okuma bölgesi korunur. Bütçe seçimi hiçbir dosyaya yazmaz, mesaj eklemez veya mesaj okuyucu cursor'ını ilerletmez.
2. Her aday kayıt tam olarak bir kez, sabit JSON encoder ile UTF-8 byte dizisine çevrilir. Boyutu tek item tavanını aşan kayıt atlanır; `record_size_limit` nedeni eklenir. Bu kayıt gövdesi kesilmez.
3. Adaylar grup sırası ve bütçe tablosu uyarınca seçilir. Bir item sığmazsa aynı gruptaki sonraki adaya devam edilir; böylece büyük ilk item küçük kayıtları aç bırakmaz. Dahil/atlanan sayaçları kayıt sayar; `ekranlar` sayaçları dosya sayar.
4. Ekran dosya seçimi #459'un var olan round-robin/ilerletme sözleşmesine aittir. Global bütçe uygulanırken dosya map'ten çıkarılırsa `snapshot_meta` bunu belirtir; #459 cursor'ı okunmamış dosyaları atlayacak şekilde ilerletilemez. Uygulama birleşik seçici gerektirirse ekran cursor commit'i, final response seçimi başarılı olduktan sonra ve yalnız gerçekten değerlendirilmiş son dosyaya kadar yapılır.
5. Bölüm ve metadata rezervleri son şeklin 8 MiB altında kalmasını garanti eder. Seçimden sonra JSON gövdesi bir kez encode edilir ve final byte length invariant olarak kontrol edilir. Bu kontrol limit üstü görürse bu bir uygulama/sözleşme hatasıdır; snapshot'ı tekrar tekrar serialize ederek budamak yerine sabit küçük `503` döner. Son gönderilecek gövde yalnız bir kez yazılır; `_gonder()` aynı JSON nesnesini ikinci kez serialize edip büyük geçici string üretmemelidir.
6. Asgari sabit zarf ve metadata dahi 8 MiB içine sığmıyorsa sabit küçük `503` hata gövdesi döner. Üretilmiş snapshot'tan veri silerek veya JSON'u kırparak geçerli cevap taklidi yapılmaz.

Kodlama hatalı tek item içerik olarak dışarı verilmez, atlanır ve `record_encoding_error` sayılır. Zarfın kendisi kodlanamıyorsa sabit hata zarfı kullanılır. JSON kaynağı bozuksa mevcut `500` kalıcı durum hata yolu korunur.

## Partial response şekli

Tam ve kısmi başarılı yanıtta aşağıdaki alanlar bulunur; partial olsa da üst seviye mevcut alanların tipi değişmez:

```json
{
  "ok": true,
  "snapshot_meta": {
    "schema_version": 1,
    "partial": true,
    "response_byte_budget": 8388608,
    "included": {
      "kullanicilar": 40,
      "gorevler": 180,
      "mesajlar": 80,
      "ekran_dosyalari": 32
    },
    "omitted": {
      "kullanicilar": 0,
      "gorevler": 12,
      "mesajlar": 0,
      "ekran_dosyalari": 2
    },
    "partial_reasons": ["tasks_output_byte_limit", "screen_output_partial"]
  }
}
```

`partial` yalnızca bu genel selection'ın ürettiği eksikliği ve `ekranlar_meta.partial` değerini birleştirir; `ekranlar_meta` mevcut şeklini korur. Sayaçlar non-negative integer'dır. Nedenler sabit, ASCII enum listesinden sıralı ve tekildir: `users_output_byte_limit`, `tasks_output_byte_limit`, `messages_output_byte_limit`, `screen_output_partial`, `record_size_limit`, `record_encoding_error`, `final_response_byte_limit`. Metadata içerik, hata metni, ID veya path taşımaz. Limit dışı kaynak okuma ve bozuk veri başarılı partial değil hata response'udur.

Hata sözleşmesi:

| Koşul | HTTP | Gövde/yorum |
|---|---:|---|
| Item veya bölüm bütçesi nedeniyle kayıt atlandı | 200 | `ok:true`, değişmeyen alan tipleri, `snapshot_meta.partial:true` |
| `durum.json`/`gorevler.json` kaynak byte tavanı aşıldı | 503 | Küçük sabit `snapshot_source_limit`; kaynak adı enum ve tavan. Partial veri yok. |
| Bozuk JSON/şema veya kalıcı okuma hatası | 500 | Mevcut güvenli durum hata zarfı; sessiz boş snapshot yok. |
| Sabit zarf bütçeye sığmıyor | 503 | Küçük sabit `snapshot_response_unavailable`; snapshot gövdesi yok. |

`Content-Length` encode edilmiş nihai byte dizisinin uzunluğudur. `/api/veri` ve `/veri` aynı handler, byte bütçesi ve hata sözleşmesini kullanır.

## UI ve geriye uyumluluk

`snapshot_meta.partial` varsa panel tüm veri bölümlerinde görünür bir “Kısmi snapshot · gösterilen X · atlanan Y” uyarısı gösterir. Gösterilen sayı toplam sayı olarak sunulmaz. Eksik kullanıcıdan “yok/çevrimdışı”, eksik görevden “atanmadı/tamamlandı” sonucu çıkarılamaz. Kullanıcı listesi kısmi olduğunda hedef seçimine bağlı yönlendirme/rol eylemleri; görev listesi kısmi olduğunda liste kapsamına bağlı görev mutasyonları tam snapshot veya ayrı tam hedef doğrulaması gelene kadar kapatılır. Gözlem ve mevcut öğelerin salt okunur render'ı sürebilir. Sohbet ve ekran alanı için ilgili lokal partial uyarıları korunur.

Eski UI yeni metadata'yı görmezden gelebilir ve kısmi listeyi tam sanabilir. Bu nedenle server partial yanıtı ile onu anlayan UI aynı release içinde devreye alınmalıdır. Sunucu şema/tip değiştiren alternatif alan döndürmez; `snapshot_meta` eklemeli uzantıdır. Bilinen harici `/api/veri` tüketicilerinin de yeni sözleşmeyi anladığı kabul edilmeden partial modu açılmaz.

## Fixture kabul matrisi

Sentetik, geçici fixture şu durumları sınamalıdır; host verisi veya canlı servis kullanılmaz:

1. Nihai JSON gövdesi tam olarak 8 MiB ise kabul; 8 MiB + 1 UTF-8 byte ise kayıt çıkarımı veya sabit hata ile red. Çok-byte UTF-8 metin ve JSON escape maliyetleri Python karakter sayısıyla karıştırılmaz.
2. Her bölüm ve kayıt sınırında tam sınır / sınır + 1; büyük ilk adayın atlanıp küçük sonraki adayın dahil edilmesi; seçim ve metadata sayaçlarının tekrar çağrıda deterministik olması.
3. Çıktıda ID/text/path yokluğu, enum tekrar/sıralama, byte sayaçlarının gerçek encode edilmiş gövdeyle eşleşmesi ve tüm kısmi alan tiplerinin tam yanıtla aynı kalması.
4. `ekranlar_meta.partial` genel `snapshot_meta.partial`'a taşınır; ekran round-robin cursor'ı seçilmemiş dosyaları atlamaz.
5. Kaynak dosyası limit + 1 byte ise 503; bozuk snapshot 500; her ikisinde disk byte'ları değişmeden kalır ve partial başarı zarfı üretilmez.
6. Metadata/zarf rezervi aşırı büyük veya item kodlanamazsa sabit fail-closed davranış; yanıta ham hata/serbest metin sızmaz.
7. Handler seviyesinde `/api/veri` ve `/veri` için aynı exact `Content-Length`, status ve gövde byte kontrolü.

Mevcut #605 fixture yalnız kullanıcı alan allowlist'ini, JSONL ham/kayıt limitini ve ekran map limitini doğrular; global 8 MiB sözleşmesinin kanıtı değildir. #459 ekran çıktısı bütçesini korur, bu tasarım onun yerine geçmez.

## Operasyon ve kapsam sınırları

8 MiB JSON wire tavanı HTTP output ve final serialized value boyutunu sınırlar; `json.loads` sonucu Python heap'inde daha büyük olabilir. Ham durum/görev file caps sınırlı en kötü girdi sağlar, fakat kesin RSS tavanı iddiası vermez. Süreç bellek tavanı gerekiyorsa stream parser veya RSS-limited worker ve ayrıca ölçüm gerekir.

Bu belge API erişim yetkisi, retention, sayfalama, anonim GET kararı veya live rollout onayı değildir. `GET /api/veri` erişim kontrolü #455/#557 kararından ayrı kalır. Üretim kabulünden önce UI birlikte güncellenmeli, fixture matrisi uygulanmalı, harici istemciler envanteri çıkarılmalı ve release/host kabulü ayrıca yapılmalıdır.

İlgili belgeler: [#495 önceki toplam bütçe tasarımı](panel-api-total-budget-design-495.md), [#459 ekran bütçesi](panel-api-screen-budget-459.md), [#605 alan allowlist fixture'ı](panel-snapshot-allowlist-fixture-605.md), [#574 anonim snapshot veri minimizasyonu](panel-anonymous-snapshot-data-minimization-574.md), [#455 GET erişim kararı](local-api-get-snapshot-decision-455.md).
