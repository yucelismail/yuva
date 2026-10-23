# JSONL son kayıt bozulması ve kurtarma sözleşmesi

## Amaç ve kapsam

Bu not, sohbet ve ekran JSONL dosyalarında bozuk satır veya tamamlanmamış son
append görüldüğünde okuyucu, yazıcı ve operatörün nasıl davranacağını tanımlar.
Salt-okunur tasarım kararıdır; kod veya mevcut arşiv değişikliği içermez.

Bugünkü yazıcılar JSON nesnesini `\n` ile sonlandırıp ortak `.kilit` flock'u
altında dosyaya ekler (`bin/yuva:170-175`, `panel/server.py:224-231`). Kilit
CLI ve panelin birlikte çalışmasını sağlar; kilidi kullanmayan yazıcıyı veya
append sırasında süreç/dosya sistemi kesintisini korumaz. Yazıcılar `write`
sonrasında açıkça `fsync` çağırmıyor. Bu nedenle normal dönüş de güç kesintisine
karşı diske kalıcılık kanıtı değildir.

CLI ve panel okuyucuları dosyanın tamamını okur, `splitlines()` uygular ve JSON
hatası olan satırları sessizce atlar (`bin/yuva:337-346,1279-1287`,
`panel/server.py:414-426,484-499`). `splitlines()` son newline bulunup
bulunmadığını kaybettirdiği için eksik sonlandırılmış kayıt ile tam satır
arasındaki fark mevcut akışta görünür değildir. Bu davranış sağlıklı arşiv
izlenimi verebilir ve hatalı son satırı gizleyebilir.

## Dosya sözleşmesi

- Dosya UTF-8 kodlu JSONL'dir. Her kayıt bir JSON nesnesidir; kayıt sonlandırıcısı
  tek LF (`0x0A`) baytıdır. CRLF kabul edilecekse `CR` yalnız LF'den hemen önceki
  satır sonu parçası olarak normalize edilir. Boş satır geçerli kayıt değildir.
- Yalnız LF ile biten ve JSON nesnesi olarak çözülen kayıt **tamamlanmış
  kayıt**tır. Satır LF ile bitiyor fakat UTF-8/JSON/şema doğrulamasından
  geçmiyorsa **tam satır bozukluğu** vardır. İlerideki kayıtlar okunabiliyor
  olsa da bu bir arşiv bütünlüğü alarmıdır.
- Dosyanın son baytları LF değilse **sonlandırılmamış kuyruk** vardır. Kuyruk
  JSON olarak çözülebilse bile, ayraç eksikliği yazıcının tamamlandığını ve
  kaydın commit edildiğini kanıtlamaz; otomatik olarak tamamlanmış sayılmaz.
  Çözülemiyorsa bu **kısmi/bozuk kuyruk** olarak sınıflanır. Aradaki newline
  eksikliğiyle iki JSON nesnesi birleşmişse bu da kuyruk bozukluğudur.
- Dosya sonu, newline ile biten geçerli kayıtların ardından geliyorsa kuyruk
  temizdir. Dosyanın boş olması da temiz başlangıçtır.
- JSON parse edilebilmesi tek başına uygulama kaydının geçerli olduğunu
  kanıtlamaz. Mesaj veya ekran okuyucusunun beklediği üst düzey tip ve asgari
  alanlar ayrıca doğrulanır; ileri sürüm/ek alanlar geriye uyum kurallarıyla
  ele alınır.

## Okuyucu ve yazıcı davranışı

| Durum | Okuyucu davranışı | Yazıcı davranışı |
|---|---|---|
| Tüm satırlar LF ile bitiyor ve kayıtlar geçerli | Normal sonucu ve `healthy` bütünlük durumunu döndür. | Append'e izin ver. |
| Son satır LF ile bitmiyor; JSON geçerli veya geçersiz | Kuyruğu tamamlanmış kayıt olarak sunma. Önceki doğrulanmış kayıtları gösterebilirsin; sonucu `degraded` işaretle ve kullanıcı/operatöre dosya, satır/bayt ofseti ve `unterminated_tail` alarmı ver. Ham kuyruk korunur. | Aynı dosyaya append'i reddet; yeni JSON'un kuyrukla birleşmesine izin verme. Kurtarma kararı gelene kadar başka sağlıklı dosya/yol varsa yalnız o yola yazma politikası açıkça tanımlanmalı. |
| LF ile biten tam satır UTF-8, JSON veya kayıt şema kontrolünden geçmiyor | Geçerli satırı sessizce yok sayıp dosyayı sağlıklı gösterme. Geçerli prefix'i gösterebilirsin, fakat `degraded` alarmı ve bozuk satır konumu döndür. Satırların geri kalanını otomatik birleştirme/silme. | Dosyanın sonundaki bozuklukta append'i durdur. İç satır bozukluğunda da arşiv bütünlüğü alarmı açık kalır; onarım olmadan dosyaya yazmak hatayı gizleyebilir, bu nedenle varsayılan politika yazmayı durdurmaktır. |
| Dosya okunamıyor veya bütünlük taraması tamamlanamıyor | Sağlıklı/boş sonucu gibi davranma; hata durumunu açıkça döndür. | Kilit veya kontrol mekanizması kurulamazsa yazma fail-closed reddedilir. |

Okuyucunun geçerli prefix'i sunması kolaylık içindir; bu sonuç **tam arşiv**
veya **eksiksiz sohbet geçmişi** olarak etiketlenemez. API/CLI çıktısında
bütünlük uyarısı görünür olmalı; yalnız terminal loguna yazılıp kaybolmamalıdır.
İşlem çağıran bileşen uyarıyı gösteremiyorsa bozuk veriyi normal başarı yanıtı
olarak sunmamalıdır.

## Eşzamanlı append ve dayanıklılık

- Tüm Yuva yazıcıları aynı kilit dosyasını kullanmalı ve kontrol, onarım ve
  append boyunca kilidi tutmalıdır. Kilit alınamazsa timeout/lock hatası görünür
  olmalı; kilitsiz append'e düşülmemelidir.
- Append öncesi dosyanın son baytının LF olduğu ve kuyruk bütünlük kontrolünün
  temiz geçtiği doğrulanmalıdır. Bu kontrol kilit alındıktan sonra yapılmalıdır;
  aksi halde başka bir append kontrol ile yazma arasına girebilir.
- Kayıt UTF-8 JSON artı LF olarak tek mantıksal payload hazırlanır. `write`
  hatası/istisnası veya beklenenden kısa yazma, sonucu belirsiz kılabilir:
  yazıcı dosyayı otomatik truncate ederek önceki boyuta döndürmemeli ve
  başarısız kaydı sessizce yeniden eklememelidir. Kuyruk tekrar taranır; durum
  `commit_unknown` olarak üst kata taşınır ve operatör alarmı korunur.
- Süreçler arası flock yalnızca katılımcı süreçleri sıraya koyar; dosya sistemi
  yazma atomikliği ya da güç kaybına karşı kalıcılık sağlamaz. Linux'ta
  `O_APPEND` offset seçimini korusa da yazma işlemi kesilebilir. Dayanıklılık
  isteniyorsa payload'ın tamamı yazılıp `flush` ve `fsync(file)` başarılı
  olmadan kayıt kalıcı kabul edilmemelidir. Yeni dosya oluşturma/atomik değişim
  varsa ilgili üst dizin de `fsync` edilmelidir. `fsync` hatası sonrası kayıt
  görünür olsa bile sonuç `commit_unknown` kalabilir.
- Yeni başlayan yazıcı, mevcut dosyada temiz LF kuyruğu ve beklenen dosya türü/
  izin kontrolleri doğrulanmadan otomatik onarım veya append yapmamalıdır.

## Operatör kontrollü kurtarma

Kurtarma geçmişi otomatik silmez, truncate etmez, satırları yeniden sıralamaz
ve özgün JSONL üzerinde yerinde düzeltme yapmaz. Önerilen işlem sırası:

1. İlgili sohbet/ekran dosyasına yazan paneli ve CLI/yardımcı süreçleri durdur.
   Ortak flock'u al; tüm yazıcıların bu kilide uyduğunu doğrula. Kurtarma
   boyunca yeni yazıcı açılmamalı.
2. Orijinal dosyanın ham baytlarını salt-okunur kopyala; boyut, sahiplik/izin,
   zaman damgası ve kriptografik özetini kaydet. Kopyayı korumalı konumda
   sakla. Bu adım başarısızsa kurtarmaya devam etme.
3. Bayt bazında tarayıcıyla doğrulanmış satırların son offset'ini ve ilk hata
   türünü raporla: bozuk tam satır, sonlandırılmamış geçerli JSON kuyruk,
   sonlandırılmamış geçersiz JSON kuyruğu, geçersiz UTF-8 veya boş satır.
   Hatalı baytları rapor/artifact olarak koru; mesaj/ekran metnini genel loga
   yazıp hassas veriyi sızdırma.
4. Operatör kaynak veya yedekten kaydın tamamlığını doğrular. Doğrulama yoksa
   kayıt kurtarıldı gibi kabul edilmez; geçerli prefix'ten yeni arşiv üretilecekse
   kayıp byte/record aralığı manifestte açıkça belirtilir. Orijinal dosya
   saklanmaya devam eder.
5. Düzeltme gerekiyorsa doğrulanmış kayıtları **yeni bir geçici dosyaya** yaz;
   her satırın UTF-8/JSON/şema kontrolünü yap, her satırı LF ile bitir, kayıt
   sayısını ve özeti manifestle karşılaştır. Eski dosyayı yerinde değiştirme.
6. Operatör yeni dosyayı onayladıktan sonra kontrollü atomik değişim yap ve
   üst dizin dayanıklılığını doğrula. Değişim sonrası tekrar tarama sağlıklı
   çıkmadan yazıcıları açma. Eski ham kopyayı saklama/retention politikasına
   göre muhafaza et.

Bir son kayıt JSON olarak geçerliyse operatör, dış kanıtla kaydın tamam olduğunu
doğruladığında yalnız LF ekleyerek yeni kopyada tamamlayabilir. JSON geçersizse
kısmi baytları otomatik kesmek yerine operatör onayıyla yeni kopyada dışarıda
bırakılabilir; manifestte bunun kısmi kayıt olduğu ve atılan aralık belirtilir.
LF ile biten bozuk tam satırın atılması veya yeniden oluşturulması da aynı
onay ve kanıtı gerektirir. Uygulama hiçbir seçimi kendi başına yapmaz.

## Kabul ölçütleri

- LF'siz geçerli JSON ve LF'siz geçersiz JSON farklı alarm ayrıntılarıyla
  sınıflanır; ikisi de otomatik tamamlanmış kayıt sayılmaz.
- LF ile biten bozuk satırın atlanması kullanıcıya/operatöre görünür ve dosya
  `degraded` olarak raporlanır.
- Okuma, yazma ve API yanıtları bozuk kuyrukta arşivi sağlıklı/eksiksiz
  göstermemeli; yeni append mevcut kuyruğu birleştirmemelidir.
- Kurtarma orijinali değiştirmez; yedek/özet, doğrulanmış prefix, operatör
  kararı, manifest ve son tarama kanıtı üretir.
- Kesinti sonrası yeniden deneme, önceki append sonucunu kesin başarısız varsayıp
  aynı kaydı otomatik çoğaltmaz; `commit_unknown` uzlaştırma gerektirir.

## Kaynaklar

- `bin/yuva:72-95` — ortak flock kilidi.
- `bin/yuva:170-175` ve `panel/server.py:224-231` — kilit altındaki JSONL
  append yazıcıları ve açık `fsync` bulunmaması.
- `bin/yuva:337-346,1279-1287` ve `panel/server.py:414-426,484-499` — tüm
  dosyayı okuyup satırları parse eden, hatalı satırı sessizce atlayan okuyucular.
- Yuva görevi #434 — son append/kısmi kayıt bulgusu; bu not kurtarma kararını
  tanımlamak için ondan bağımsız, kaynaklandırılmış bir tasarımdır.
