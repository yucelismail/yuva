# #445 JSONL bounded-tail bağımsız incelemesi

## Sonuç

Statik incelemede CLI ve panel tail helper'larının aynı byte/satır algoritmasını
kullandığı görüldü. Okuma maliyeti sabit 8 KiB bloklarla geriye doğru taranarak
dosya başına tarama-byte ve LF ile tamamlanmış satır sayısıyla sınırlandırılıyor.
Ekran okumalarında ayrıca dosya sayısı ve aggregate ham tarama bütçesi; panel
ekran map'inde de JSON çıktı bütçesi var. Bütçeler aşıldığında helper kısmi veya
boş sonuç verebilir; kullanıcıya arşiv eksikliği/bozulma uyarısı üretilmez.

Kaynakta bu limitlerin aşılacağı bir yol görülmedi. Ancak “8 MiB” ham okuma
bütçesi, tepe RAM kullanımının 8 MiB olduğu anlamına gelmez: chunk listesi,
birleştirilmiş bytes, satır kopyaları, decoded string'ler ve parse edilmiş JSON
aynı anda bellekte bulunabilir. Ayrıca ada göre ilk 128 dosyayı seçmek için
`heapq.nsmallest()` dizindeki bütün adları dolaşır; dosya içeriği okunan dosya
sayısı 128 ile sınırlıdır ama dizin girdisi taraması sayısal bir üst sınıra
bağlı değildir.

Bu yalnız kaynak incelemesidir. Test, runtime veya panel çalıştırılmadı.
Yuva'da #445 kabul edilmiş durumdadır.

## Limit matrisi

| Akış | Dosya adedi | Dosya başı / toplam ham tarama | Satır sınırı | Dış sonuç bütçesi |
|---|---:|---:|---:|---:|
| Sohbet CLI `mesajlar()` | 1 (`mesaj.jsonl`) | 2 MiB toplam | Aday `3*n`, `n≤400`; kayıt ≤64 KiB | En çok 400 message objesi; ayrı serialized-byte bütçesi yok |
| Sohbet panel `mesajlar()` | 1 (`mesaj.jsonl`) | 2 MiB toplam | Aday `3*n`, `n≤200`; kayıt ≤64 KiB | En çok 200 message objesi; ayrı serialized-byte bütçesi yok |
| CLI ekran, kimlik filtresi | 1 | `min(1 MiB, 8 MiB, dosya boyutu)`; dolayısıyla en çok 1 MiB | İstenen `n≤60`; kayıt ≤16 KiB | Ayrı encoded-output byte tavanı yok |
| CLI ekran, filtresiz | Ada göre ilk 128 dosya okunabilir | Dosya başı en çok 1 MiB, aggregate en çok 8 MiB | Dosya başı istenen `n≤60`; kayıt ≤16 KiB | Ayrı encoded-output byte tavanı yok |
| Panel ekran `/api/veri` | Ada göre ilk 128 dosya okunabilir | Dosya başı en çok 1 MiB, aggregate en çok 8 MiB | Dosya başı en çok 60 satır; kayıt ≤16 KiB | `ekranlar` map'inin JSON kodlu temsili en çok 2 MiB; sığmayan dosyanın satır listesi bütünüyle atlanır |

Mesaj isteklerinde okuyucu önce `3*n` adayı en fazla 2 MiB'den toplar, sonra
JSON hatalı veya nesne olmayan mesajları eler ve son `n` geçerli mesajı verir.
Dolayısıyla `n` kadar geçerli kayıt bulunması garanti değildir. Ekran
okuyucuları da JSON parse hatalı satırları atlar. Panel ekran map'inde hiç
kabul edilmiş satır kalmazsa mevcut API şekli korunur ve `ekranlar: {}` olur;
CLI ekran okuyucu çıktı vermezse `(gösterilecek ekran satırı yok)` yazar.

## Tail sınırı, kısmi kayıt ve uzun satır

İki helper da aynı akışı uygular (`bin/yuva:471-507`,
`panel/server.py:555-591`):

1. Dosya sonundan başlayarak en çok 8 KiB'lık parçalar okur. Okuma toplamı
   çağıranın `en_cok_bayt` bütçesini aşmaz; LF sınırı her chunk sonrasında
   denetlendiğinden son chunk `en_cok_satir + 1` hedefini aşabilir (en fazla
   o chunk içindeki ek LF'ler kadar). Sonuç listesi yine en çok istenen satır
   sayısına dilimlenir.
2. Bütçe dosyanın tamamını kapsamıyorsa, eldeki en eski olası satırın başı
   kesilmiş olabilir. İlk LF öncesindeki parça atılır; pencere içinde LF yoksa
   hiç satır dönmez.
3. EOF LF ile bitmiyorsa, son LF'den sonraki eksik kuyruk atılır. Dosyanın
   tamamı LF'siz tek geçerli JSON içerse bile kayıt tamamlanmış sayılmaz ve
   dönmez. Okunan pencere içinde tamamlanmış önceki satırlar varsa onlar
   dönebilir.
4. Sonra yalnız son `en_cok_satir` satır seçilir; boş kayıtlar ve satır byte
   uzunluğu `en_cok_kayit_bayt` üstünde olan kayıtlar atlanır. Oversized satır
   önce satır sayısı seçiminde yer kaplayabildiğinden, daha eski satırlarla
   geriye doğru doldurma yapılmaz.
5. UTF-8 `errors="replace"` ile çözülür. Böylece hatalı UTF-8 her zaman
   görünür okuma hatası oluşturmaz; değiştirilmiş metin JSON parse edilebilir
   veya sonradan atılabilir.

Kısmi kuyruk, limit üstü satır, boş satır ve JSON parse hatası CLI/panelde
   ayrı bütünlük alarmı oluşturmaz. Bu davranış `docs/jsonl-tail-recovery.md`
içindeki hedeflenen `degraded` sözleşmesini uygulamaz; bu review'un kapsamı
limit ve bounded-tail uyumudur.

## Eşzamanlı değişiklik ve hata davranışı

- Helper dosya boyutunu açılmış fd üzerinde `fstat()` ile alır. Append aynı
  inode'un sonuna olursa, helper başlangıç boyutuyla snapshot alır ve daha yeni
  eklenen byte'ları içermeyebilir. Normal append mevcut prefix'i değiştirmez;
  okuyucular `.kilit` almıyor, dolayısıyla en yeni kayıtların aynı yanıtta
  görünmesi garanti değildir.
- Dosya okuma sırasında küçülürse beklenen chunk'tan az byte okuması
  `OSError("JSONL boyutu okunurken değişti")` üretir. Büyüme başlangıç
  boyutunun ötesindeki byte'ları bu çağrıya katmaz.
- Mesaj CLI'sinde okuma hatası çağrı zincirinden çıkar ve ana CLI'da dosya
  hatası olarak nonzero çıkışa dönüşür (`bin/yuva:479-487`, `bin/yuva:2301-2308`).
  Panel `mesajlar()` tüm okuma hatalarını yakalayıp `[]` döndürür
  (`panel/server.py:594-603`); bu hata ile gerçekten boş dosya API görünümünde
  ayrışmaz.
- Ekran CLI'si her dosya için `OSError`'ı yakalayıp geçer; panel ekran map'i
  her dosyadaki her türlü exception'ı yakalayıp o dosyayı atlar
  (`bin/yuva:1466-1479`, `panel/server.py:687-700`). Kalan dosyalar işlenmeye
  devam eder. Bütçe okuma öncesinde ayrıldığı için atlanan/hata veren dosyanın
  ayrılmış byte'ları sonraki dosyaya geri verilmez; bu hata durumunda da toplam
  okuma tavanını korur.
- Klasör/dosya yokluğu ile boş veya filtrelenmiş sonuç, ekran CLI'de açık
  mesajla; panelde `{}`/boş listeyle temsil edilir. Bir panel mesaj dosyası
  okuma hatası da boş listeye indirgenir. Boş sonuç “bütün kayıtlar temiz”
  anlamına gelmez.

## CLI/panel uyumu ve açık farklar

- Tail helper'ın temel algoritması ve varsayılan return şekli aynıdır. Panel
  ekran bütçelemesi için opsiyonel `(satırlar, taranan_byte)` dönüşünü kullanır;
  CLI de aynı seçeneği aggregate tarama hesabında kullanır.
- Sohbet path'inde ikisi de aynı 2 MiB ve 64 KiB/record sınırını kullanır,
  ancak üst mesaj sayısı farklıdır: CLI 400, panel 200. İstenen mesaj sayısına
  ulaşmak için aday sayısı üç katıyla sınırlıdır.
- Ekranlarda temel per-file ve aggregate tarama değerleri eşleşir: ilk 128
  ada göre sıralı dosya, dosya başı en çok 1 MiB, toplam 8 MiB. Panelde ayrıca
  2 MiB `ekranlar` JSON bütçesi vardır; CLI terminal çıktısında eş değer bir
  serialized-byte tavanı yoktur.
- File discovery deterministik seçim için bütün glob sonuçlarını dolaşır.
  İçerik okuma 128 dosyada sınırlandırılmış olsa da çok büyük `ekran/` dizini
  için isim enumerasyonu CPU/I/O maliyeti ayrı bir sınıra bağlı değildir.
- JSONL satırlarının sözdizimsel JSON olması dışında ekran okuyucuları şema
  kontrolü yapmaz. CLI, JSON olarak çözülen bir listenin/skalarning `.get()`
  çağrısında hata verebilir; panel map'i de dict olmayan JSON değerlerini
  geçerli satır listesi gibi döndürebilir. Mevcut writer'lar nesne üretir;
  bozuk/tahrif edilmiş dosyada bu ayrıca şema-kabul sınırı olarak incelenmeli.

## İnceleme kapsamı ve kaynaklar

- CLI tail helper: `bin/yuva:471-507`; sohbet kullanımı: `bin/yuva:510-516`;
  ekran seçimi/bütçesi: `bin/yuva:1445-1490`.
- Panel tail helper: `panel/server.py:555-591`; sohbet kullanımı ve hata yolu:
  `panel/server.py:594-610`; ekran toplam bütçesi: `panel/server.py:675-711`.
- Ekran bütçe sabitleri: `bin/yuva:36-37`, `panel/server.py:52-57`.
- İnceleme salt-okunurdur. Kod değiştirilmedi; test, runtime ve panel
  çalıştırılmadı.
