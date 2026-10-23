# JSONL retention: operatör kararları ve geçiş planı

Bu not, `docs/jsonl-retention-design.md` içindeki önerileri uygulama öncesi
kararlara ve geri dönüş kapılarına çevirir. Kaynak taslaktaki sayılar
**başlangıç önerisidir**; ölçülmüş üretim hacmi veya onaylanmış ürün politikası
değildir. Burada yeni limit seçilmez. Her satırın kabul edilmesi, değiştirilmesi
veya ertelenmesi uygulama sahibince karara bağlanmalıdır.

## Karar tablosu

| Konu | Mevcut taslak | Uygulama öncesi karar | Seçenekler ve etkileri |
|---|---|---|---|
| Mesaj segmenti ve kayıt boyu | 32 MiB veya 24 saat; satır başına 64 KiB | Ölçümden sonra eşikleri kabul et, değiştir veya ertelenmiş bırak. | Taslağı kabul etmek düşük ilk kapsam verir; hacme göre ayarlamak disk ve yanıt davranışını etkiler. Karar yoksa limit uygulanmamalı ve taslak “onaylı” diye sunulmamalı. |
| Ekran segmenti ve kayıt boyu | Kimlik başına 8 MiB veya 24 saat; satır başına 16 KiB | Eşiklerin gerçek ekran çıktılarına uygunluğunu belirle. | Tek kimlikte sık rotation arşiv sayısını artırabilir; daha büyük eşik disk tepesini büyütür. Uzun tek satırı kesmek JSON'u bozar; taslak bunu reddetmeyi önerir. |
| Mesaj arşivi | 90 gün veya 512 MiB toplam; hangisi önce gelirse en eski arşiv temizlenebilir. | Süre ve toplam bütçeyi, hangisinin öncelikli olduğunu ve limit dolunca yazma davranışını onayla. | “Önce gelen sınır” disk kullanımını sınırlar fakat kayıtları 90 günden önce silebilir. Minimum yaş garantisi istenirse bütçe dolduğunda yazmayı durdurma ya da daha fazla disk ayırma kararı gerekir; taslak bu ürün tercihini kesinleştirmiyor. |
| Ekran arşivi | Kimlik başına 7 gün; global 256 MiB; `/api/veri` için en yeni 128 kimlik önerisi | Yaş, bütçe ve kimlik görünürlük sınırını birlikte seç. | Global bütçe, düşük etkinlikli kimliklerin eski kayıtlarını önce silebilir. 128 kimlik önerisi yanıtı sınırlar fakat diğer kimlikleri API'de göstermemeyi gerektirir. |
| Son etkin ekran kimliği | `last_append_at` metadata'sıyla en yeni 128 kimlik; metadata henüz mevcut değil. | Metadata'nın kaynağını, dayanıklılığını ve yazıcıyla tutarlılığını seç. | Atomik manifest eklemek ek state ve kurtarma gerektirir; dosya mtime'ı harici kopyalama/restore ile değişebilir; sabit alfabetik seçim “en yeni” anlamı taşımaz. Bu alternatiflerden biri kararlaştırılmadan “en yeni 128” uygulanmış sayılamaz. |
| Okuma sınırı | Mesaj: en çok 1.200 satır/2 MiB; ekran: kimlik başına 60 satır ve toplam 4 MiB; `/api/veri`: toplam 8 MiB önerisi. | CLI, panel ve API'nin aynı byte/record davranışını ve kesilme bildirimini kabul et. | Daha düşük sınır daha az bellek/ağ kullanır, ancak geçmişin daha küçük bölümünü gösterir. `truncated` ve `omitted` olmadan kesinti boş/eksiksiz sonuçla karıştırılabilir. CLI `--n` pozitif sınıra clamp/reject edilmelidir. |
| Yedek kapsamı ve ömrü | Etkin KOK dışında; 30 gün ve 1 GiB taslak bütçesi. Hassas loglar ayrıca izin verilmedikçe yedeğe alınmamalı. | Sohbet/ekran JSONL'nin yedeklenmesine açıkça izin verilecek mi; ömür/bütçe ne olacak; silme nasıl denetlenecek? | Logları dışlamak hassas içeriğin kopyalarını azaltır fakat kurtarılabilir geçmişi azaltır. Dahil etmek kurtarmayı iyileştirir fakat yedekleri de aynı erişim, şifreleme ve silme kapsamına sokar. Geçiş rehberindeki tam KOK arşivi `mesaj.jsonl` ve `ekran/` dosyalarını da içerir; bu nedenle rehberin akışı seçilen yedek politikasıyla uyumlandırılmalıdır. |
| Arşiv sıkıştırma | İlk sürümde erteleme önerisi. | İlk geçişte sıkıştırma olacak mı? | Ertelemek geçiş durumlarını ve kilit dışı işlem yarışlarını azaltır, disk kazancını geciktirir. Sıkıştırma seçilirse geçici ad, checksum, rename ve kaynak silme sırası ayrıca kabul edilmeli. |
| Silme denetimi | Süresi/bütçesi dolan yedekler için tarih ve adet denetim kaydı öneriliyor; arşiv silme görünürlüğü de gerekli. | Olayın nereye, hangi metadata ile ve hangi erişimle yazılacağını belirle. | JSONL'ye içerik yazmak silinen hassas veriyi yeni bir logda tutabilir. İçerik taşımayan tarih, kayıt/byte sayısı, politika sürümü ve sonuç yeterli mi kararlaştırılmalı; audit hedefi belirlenmeden temizlik etkinleştirilmemeli. |
| Hata ve dolu disk | Okuma bütçesi aşıldığında görünür kesilme; append/rotation belirsizliği fail-closed olmalı. | Kullanıcıya/operatöre hangi CLI/API durumunun döneceğini ve yazmanın ne zaman duracağını belirle. | Sessiz kesme yanlış “tam geçmiş” izlenimi verir. Append/rename/fsync sonucu belirsizse #441 kurtarma akışı uzlaştırmadan otomatik retry veya silmeye izin vermez. Disk doluyken eski kayıtları bütçe için silmek saklama süresini kısaltabilir; yazmayı durdurmak ise yeni kayıt kaybettirir. |
| Çalışan sürümler | CLI ve panel aynı KOK ve `.kilit` inode'unu kullanmalı; eski/yeni writer-reader karışımı güvenli değil. | Eşzamanlı geçiş için ayrıca protokol kabul edilecek mi? | Mevcut belgeler eski/yeni sürümü aynı KOK'ta eşzamanlı çalıştırmamayı öneriyor. Kademeli rollout seçilirse okuyucu/writer uyumluluğu ayrıca kanıtlanmalı; aksi halde bakım penceresi ve ortak durdurma kullanılmalı. |

## Önerilen geçiş sırası

1. **Kararları kayda geçir:** Yukarıdaki eşikleri, yedek kapsamını, disk dolması
   davranışını, ekran seçimini ve silme audit'ini onayla veya açıkça ertele.
   Onaylanmamış taslak sayılarıyla retention temizliği etkinleştirme.
2. **Salt-okunur hacim envanteri çıkar:** Aktif mesaj/ekran dosyalarının sayısı,
   toplam baytı, satır boyutu dağılımı, ekran kimliği adedi ve API yanıt baytını
   içerik toplamadan ölç. Ölçüm başarısız veya eşikler aşırı düşük/yüksekse
   limitleri tekrar karara aç.
3. **Yedek politikasını çöz:** `docs/linux-gecis.md` bakım penceresinde panel,
   CLI ve yardımcı yazıcıları durdurup KOK'un tam yedeğini KOK dışına alma,
   checksum ve restore kontrolü yapma adımlarını tarif eder. Bu yöntem logları
   da kopyalar; log yedeği henüz onaylı değilse kapsamı ayrıca belirlemeden
   çalıştırma. Yedek owner/mode/ACL/xattr koruması ve hedef UID varsayımı
   doğrulanmalı.
4. **Tüm okuyucu/yazıcıları birlikte güncelle:** Aynı `YUVA_DIR` ve ortak kilit
   kullanıldığını doğrula; eski panel, CLI çağrıları ve daemon'lar tamamen
   durmadan yeni sürümü aynı KOK'a açma. JSONL dosyalarını yerinde dönüştürme.
   İlk aktif segmentin mevcut dosya olarak sürmesi ve arşiv adlandırma/manifest
   sözleşmesi rollout tasarımında açıkça belirtilmeli.
5. **Dry-run ile silme adaylarını incele:** Yaş/boyut hesabını içeriksiz bir
   raporda göster; hangi arşivlerin ve yedeklerin silineceğini, yeni toplam
   bütçeyi, yaş sınırı erken aşılacak kayıt miktarını ve atlanacak ekran
   kimliklerini operatöre sun. Dry-run hiçbir dosya silmemeli veya taşımamalı.
6. **Kabulden sonra sınırlı etkinleştir:** Arşivleme, okuyucu sınırları ve
   retention temizliği ayrı rollout adımlarıysa her birini ayrı izle.
   Temizleme ancak rapor, yedek geri yükleme ve audit hedefi kabul edilince
   etkinleşsin. Her silme/rotation sonrasında dosya sayısı, bayt, kayıt sayısı,
   kesilme/atlanan kimlik ve hata sayaçlarıyla karşılaştırma yap.
7. **Kurtarma koşullarını koru:** Son LF eksikliği, bozuk satır, `append_unknown`
   veya `rotation_unknown` görülürse #441'e göre yazmayı/temizlemeyi durdur;
   ham dosyayı koru, doğrulanmış yedeği ve manifesti uzlaştırmadan otomatik
   düzeltme yapma.

## Geri dönüş planı ve sınırlar

| Geçiş anı | Güvenli geri dönüş yolu | Veri riski / durdurma koşulu |
|---|---|---|
| Yeni sürüm açılmadan önce | Eski sürüm ve özgün KOK olduğu gibi kalır; geçiş iptal edilebilir. | Yedek doğrulaması yoksa yazma/rotation değişimine geçilmez. |
| Yeni okuyucu/yazıcı açıldı, henüz rotation veya retention silmesi olmadı | Tüm yeni süreçleri durdur; eski okuyucuya dönmeden önce yeni yazılan kayıtları koru ve eski sürümle aynı JSONL şemasını okuyabildiğini doğrula. Gerekiyorsa geçiş öncesi yedeğe dönmek yeni kayıtları kaybettirebilir. | Yeni kayıtlar varsa yedeği doğrudan etkin KOK üzerine açma; önce farkları uzlaştır. Eski ve yeni writer'ları birlikte çalıştırma. |
| Rotation başladı, arşiv segmentleri oluştu | Önce yeni okuyucuyla dosya/manifest envanterini sabitle. Eski sürüm arşiv segmentlerini okumuyorsa eski sürüme dönüş ancak doğrulanmış yedekten geri yükleme (sonradan yazılanları kaybetme riski) veya onaylı yeni-kopya birleştirme/kurtarma ile yapılabilir. | Arşivleri eski aktif dosyanın üstüne otomatik ekleme/rename etme. #441 operatör kararı olmadan yerinde birleştirme, truncate veya silme yok. |
| Retention silmesi başladı | Yalnız politika süresi içinde kalan yedekten geri yüklemek mümkündür; restore sonrası yaş/boyut manifesti yeniden uzlaştırılır. | Silinmiş ve yedekte bulunmayan kayıt geri getirilemez. Yedek ömrü/bütçesi bunu garanti etmiyorsa geri dönüş garantisi yoktur. |
| Rename/fsync/append sonucu belirsiz | Yazıcı ve temizlik kapalı kalır; aktif/arşiv adları, manifest, boyut ve LF kuyruğu salt-okunur uzlaştırılır. | Durum kesinleşmeden ikinci rotation, yedekten üzerine yazma, retry veya arşiv silme yapma. #441 sözleşmesi uygulanır. |

Rollback testinin kapsamı, gerçek dağıtımda kullanılacak eski sürüm ve yedek
biçimiyle ayrıca kabul edilmelidir. Bu belge kod davranışının uygulandığını,
ölçümlerin yapıldığını, limitlerin onaylandığını veya kurtarma testinin
geçtiğini iddia etmez.

## Kaynaklar

- `docs/jsonl-retention-design.md` — başlangıç eşikleri, append/rotation,
  bounded-tail limitleri, rollout ve hata sınıfları; taslak değerlerin henüz
  ölçülüp onaylanmadığı notu.
- `docs/linux-gecis.md`, “Yükseltme” ve “Geçiş” — writer'ları durdurma, KOK
  dışı yedek, checksum/restore kontrolü, aynı `YUVA_DIR` ve sürüm geçişi.
- `docs/jsonl-tail-recovery.md` — bozuk/kısmi kuyrukta ham veriyi koruma,
  operatör onayı ve yeni kopyada kurtarma.
- `docs/task-mutation-idempotency-outbox-design-437.md` — görev bildirimi ile
  JSONL'nin ayrı commit sınırı ve `commit_unknown` uzlaştırması.
- Yuva #449 — bu dokümanın kapsamı: mevcut limitlere yeni değer eklemeden
  uygulama öncesi kararları ve migration/rollback etkilerini görünür kılmak.
