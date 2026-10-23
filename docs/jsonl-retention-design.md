# Yuva JSONL saklama, rotation ve bounded-tail tasarımı

## Karar

Mesaj ve ekran JSONL dosyaları için append-only aktif segmentler, ortak kilit altında boyut eşiğine göre rotation ve ayrı retention temizliği kullanılsın. Okuyucular aktif dosyanın tamamını `read_text()` ile belleğe almak yerine aktif segment ve gereken en yeni arşiv segmentlerinden byte/record bütçesi içinde sondan okusun. Mesaj ve ekran kayıtlarının hassas içerik taşıdığı varsayılsın; arşiv ve yedek izinleri aktif dosyalar kadar sıkı olsun.

Aşağıdaki sayılar başlangıç politikasıdır; uygulamadan önce mevcut log hacmi ölçülüp gerekirse ayarlanmalı. Boyut limiti aşılınca yaş limiti beklenmeden en eski arşivi silmek retention süresini kısaltabilir; bu durum gözlemlenebilir olmalı.

## Başlangıç limitleri

| Kayıt | Aktif segment | Tek satır üst sınırı | Yaş üst sınırı | Kök altındaki arşiv bütçesi | API/CLI tail bütçesi |
|---|---:|---:|---:|---:|---:|
| `mesaj.jsonl` | 32 MiB veya 24 saat | 64 KiB | 90 gün | 512 MiB toplam | en çok 1.200 satır / 2 MiB okuma |
| `ekran/<kimlik>.jsonl` | 8 MiB / kimlik veya 24 saat | 16 KiB | 7 gün | 256 MiB toplam; 128 son etkin kimlik | 60 satır / kimlik, 4 MiB toplam okuma |

- `/api/veri` için mesaj sayısı mevcut 200, ekran satırı kimlik başına mevcut 60 olarak kalabilir; fakat yeni toplam byte ve kimlik sınırı da uygulanmalı. Yanıta `truncated`/`omitted` sayıları eklenmeli ki az kayıt dönmesi boş veri gibi yorumlanmasın. CLI `--n` değeri pozitif sınır içinde clamp/reject edilmeli; bugünkü sınırsız kullanıcı değeri bounded-memory garantisini bozar.
- Segment, yeni satır eklenince aktif boyutu aşacaksa önce döndürülür; ayrıca 24 saatlik yaşa ulaştığında günlük housekeeping kilit altında rotate eder (yazma olmasa da). Tek satır limiti aşan mesaj/ekran kaydı reddedilir; kesilip bozuk JSON üretmek yasaktır.
- Mesaj arşivleri toplam 512 MiB veya 90 gün eşiğinden hangisi önce gelirse en eski segmentten başlayarak temizlenir. Ekran arşivleri benzer biçimde kimlik başına son 7 gün ve global 256 MiB sınırıyla temizlenir. `/api/veri` ekran limiti aşarsa yazıcı/manifest tarafından güvenilir biçimde tutulan `last_append_at` değerine göre en yeni 128 kimlik seçilir; bu metadata mevcut şemada yoksa retention uygulamasıyla birlikte tanımlanır; diğerleri `omitted` alanında sayılır. Diğer ekran dosyaları arşiv bütçesi ve yaş temizliğine dahildir.
- Yedekler etkin KOK dışında tutulur (mevcut geçiş rehberindeki ilke: `docs/linux-gecis.md:56-83`). Başlangıç yedek politikası 30 günlük süre ve 1 GiB toplam bütçedir; her iki sınır da uygulanır. Yedek için kalıcı arşiv varsayılmaz. Süresi/bütçesi dolan yedeklerin silinmesi tarih ve adet bilgisiyle denetim kaydına yazılır; hassas log içeriği yedekleme kapsamına ayrıca izin verilmedikçe alınmaz.

## Yazıcılar ve rotation

Bugünkü CLI ve panel yazıcıları aynı `KOK/.kilit` dosyasında flock kullanıyor (`bin/yuva:73-99`, `170-175`; `panel/server.py:76-80`, `84-127`, `224-231`). Append ve rotation aynı kilitle koordine edilmeli; kilit yalnız kısa dosya işlemi boyunca tutulmalı. CLI/panel farklı lock inode'u veya farklı `YUVA_DIR` kullanırsa bu garantiler geçersizdir (`README.md:93-97`, `docs/linux-gecis.md:119-135`).

1. Writer JSON satırını UTF-8 olarak serialize edip newline dahil byte boyutunu önceden hesaplar. Mesaj/ekran payload'ları ilgili satır limitini aşarsa yazımı reddeder.
2. Ortak kilit altında dosya boyutu kontrol edilir. Eşik aşılacaksa aktif dosya flush + `fdatasync` edilir; benzersiz, üzerine yazılamayan arşiv adına rename edilir; yeni aktif dosya güvenli izinlerle açılır; üst dizin `fsync` edilir. Sonra yeni satır aktif dosyaya append edilir. CLI ve server append'leri bu sıra içinde birbirini kesmez.
3. Rotation sırasında arşiv sıkıştırması yapılacaksa önce kilit altında segmenti sabit bir “işleniyor” adına al; sıkıştırmayı kilit dışında geçici dosyaya yap, boyut/checksum doğrula ve atomik rename + dizin `fsync` sonrası kaynağı kaldır. İlk sürümde sıkıştırmayı ertelemek daha az durum üretir; boyut bütçesi zaten sert sınırdır.
4. Yaş/bütçe temizliği yalnız kapalı arşiv segmentlerinde yapılır, aktif dosya silinmez. Okuyucu segmentleri açarken ortak kilit altında dosya tanıtıcılarını seçip açar; sonra kilidi bırakıp bu tanıtıcılardan sabit boyut sınırında okuyabilir. Böylece rotation veya unlink açık tanıtıcıyı geçersiz kılmaz.
5. Dizin ve dosya izinleri `#434` güvenli append işinin kabul koşuluna uygun olmalı: gizli KOK/ekran dizinleri owner-only; aktif, arşiv ve geçici segment dosyaları owner-only; açılışta owner/regular-file/no-follow kontrolü. Rotation bunu gevşetmemeli.

Tek bir `mesaj.jsonl` veya ekran dosyasına eklenen kayıtların mevcut `id`/stable event ID alanı korunmalı; arşivleme sırasında JSON satırları değiştirilmemeli. Okuyucu en yeni segmentten eskiye doğru tail toplar, seçilen satırları kronolojik sırada döndürür. Panelin bugünkü mesaj/ekran limitleri satır sayısını sınırlasa da bütün dosyanın okunmasını sınırlamıyor (`panel/server.py:414-474`, `484-500`); CLI de bütün dosyayı okuduktan sonra son satırları seçiyor (`bin/yuva:337-390`, `1269-1295`).

## Bounded-tail okuyucu sözleşmesi

- Okuyucu en fazla tanımlı `max_bytes` ve `max_records` kadar veri ayırır; dosya boyutunun tamamına göre bellek kullanımı artmaz. `max_records` için CLI’nin `mesajlar(400)`/`mesajlar(120)` çağrılarını, panelin 200 mesaj/60 ekran satırı sözleşmesini koru; byte sınırı geçerse daha az tam satır döndür ve `truncated=true` bilgisini üst katmana ver.
- Dosya sonunda geriye doğru sabit bloklarla tara. İlk bulunan kısmi satırı parse etme; eski arşiv segmentine geç veya byte bütçesi bitti ise kesilme uyarısıyla dön. UTF-8/JSON hata sayısını ve bozuk tail varlığını ölçülebilir uyarı olarak üst katmana taşı; bozuk satırları sessizce yok sayıp “tam sonuç” izlenimi verme. Kısmi append'in kurtarma/operatör sözleşmesi `docs/jsonl-tail-recovery.md` kararına bırakılır.
- `/api/veri` için toplam JSONL çıktı bütçesi 8 MiB olsun. Önce en yeni mesajlar, sonra kimlik ekranları sabit sıralamayla bütçeye alınsın; kesilen mesaj sayısı ve atlanan ekran kimlikleri yanıtta açıkça verilsin. Alternatif bir öncelik gerekiyorsa endpoint sözleşmesinde belirle; dosya sistemi sıralamasına göre rastgele kesme yapma.
- Hata halinde okuyucu tam dosyayı veya sınırsız fallback'i denemez. Panelde `{ok:false, hata:..., truncated:false}`/ayrı kaynak hata durumu dönsün; CLI stderr'e dosya/segment ve kesilme uyarısı yazsın. Okuma başarısızlığını boş liste olarak sessizce sunma.

## Hata ve commit-belirsizliği davranışı

JSONL append, mevcut durumda `open(..., "a")` + `write()` ile bitiyor ve `fsync` yapmıyor (`bin/yuva:170-175`; `panel/server.py:224-231`). Bu yüzden process-level write başarısı ani güç kaybına karşı dayanıklılık kanıtı değil. Yeni sözleşmede:

- **Append öncesi hata:** kilit, serialization, limit veya dosya açma hatası yan etki olmadığını kanıtlıyorsa açık `not_written`/I/O hatası dön; hiçbir fallback path aynı kaydı farklı hedefe otomatik yazmasın.
- **Append başladıktan sonra write/flush/fsync hatası:** yazılan byte miktarı kesin değilse `append_unknown` dön. Mesaj/outbox için stable `event_id` ile kilit altında readback/dedupe yapılır; doğrulanmış kayıt varsa başarılı sayılır. Yoksa ve tail temizse aynı event ID ile uzlaştırma denemesi yapılabilir. Kısmi/bozuk tail varsa append/rotation durur, dosya karantinaya alınır ve `#441` operatör kontrollü kurtarma akışı gerekir. Ekran satırlarında stable retry ID yoksa otomatik retry yapılmaz.
- **Rotation rename öncesi hata:** aktif segment değişmediyse `rotation_not_started`; append politikası eşik altı mevcut dosyaya güvenle yazabiliyorsa devam eder, aksi halde açık hata verir.
- **Rename sonrası, yeni aktif dosya/dizin `fsync` öncesi hata veya süreç kesilmesi:** `rotation_unknown`. Yeni arşiv adı, aktif dosya ve manifest/sequence durumu yeniden okunup tekilleştirilmeden ikinci rename, arşiv silme veya yeni kayıt yazımı yapılmaz. Eski segmenti otomatik geri taşımak veya üzerine yazmak yasaktır.
- **Disk dolu / retention temizliği yetişmiyor:** en eski veri sessizce ve sınırsız silinmez; yalnız tanımlı retention penceresindeki segmentler bütçe için silinebilir. Limit yine de açılamıyorsa yeni append reddedilir ve operatör uyarısı üretilir. Arşiv veya yedek silme sonucu belirsizse aynı silmeyi tekrar etmeden önce dizin ve dosya listesini uzlaştır.
- Hiçbir `append_unknown` veya `rotation_unknown`, panel/CLI tarafından kesin başarı ya da kesin başarısızlık olarak sunulmaz. Mesajlar için #437’deki operation/outbox ID’siyle aynı olay tekrar oynatılır; ekran için belirsiz kayıt kullanıcıya açıklanır ve otomatik duplicate üretmekten kaçınılır.

## Rollout sırası

1. Önce ölçüm ekleyip aktif dosya boyutları, satır boyutları, `/api/veri` cevabı ve kimlik sayısını yalnız sayaç olarak gözlemle; log içeriğini ölçümde tutma. Limit değerlerini gerçek hacme göre teyit et.
2. CLI ve panel bounded-tail okuyucularını, `truncated`/read-error metadata'sını birlikte yayınla; aynı `YUVA_DIR` ve `.kilit` inode'u kullanan sürüm koşulunu koru.
3. Yazıcıları tek JSON serializer, satır boyutu limiti, write-full/fsync sınıflandırması ve shared-lock rotation ile güncelle. Aktif ve arşiv izinlerini #434 ile eşzamanlı uygula.
4. İlk rotation öncesi KOK dışına doğrulanmış yedek al; rollback için eski binary ile yeni segment isimleri/manifest uyumluluğunu tanımla. Yeni writer'larla eski reader'ı karıştırma; tüm CLI/panel süreçlerini durdurup birlikte değiştir.
5. Retention temizliğini ilk aşamada dry-run raporuyla göster; yaş/boyut hesabı ve restore prosedürü onaylanınca etkinleştir. Arşiv ve backup expiry sayacı/uyarısı aç.
6. Kabulde çok büyük/uzun tek satır, dev dosya tail'i, çok sayıda ekran kimliği, iki writer + rotation yarışı, disk dolu, `fsync`/rename hatası, süreç kesintisi ve restore/rollback durumlarını sentetik ayrı `YUVA_DIR` üzerinde sınayın. Memory kullanımı `max_bytes` sınırında kalmalı; event kaybı/çift satır sessiz olmamalı.

## Kaynak eşlemesi

- Veri yolları ve env: `bin/yuva:28-34`; `panel/server.py:41-48`; `README.md:93-97`.
- Ortak kilit: `bin/yuva:73-99`; `panel/server.py:76-127`.
- Bugünkü append: `bin/yuva:170-175`; `panel/server.py:224-231`.
- CLI tam dosya okuma: `bin/yuva:337-390`, `1269-1295`.
- Panel tail sayıları ama unbounded read: `panel/server.py:51-53`, `414-474`, `484-500`, `828-861`.
- KOK dışı, doğrulamalı yedek örneği: `docs/linux-gecis.md:56-115`.

Bu belge bir politika taslağıdır; rotasyon/retention davranışının mevcut uygulamada bulunduğu veya limitlerin prod verisiyle doğrulandığı anlamına gelmez.
