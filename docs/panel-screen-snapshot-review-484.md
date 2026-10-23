# #484 — ekran snapshot düzeltmelerinin statik incelemesi

İnceleme tarihi: 2026-10-21
Kapsam: Salt okunur kaynak ve doküman incelemesi. Test, panel veya runtime
çalıştırılmadı.

## İnceleme durumu

#483, 2026-10-21 01:02:52 +03:00 tarihinde ajan4 tarafından teslim edildi
ve inceleme anında pending_verification durumundaydı. Bu rapor teslim edilmiş
diff'i salt okunur değerlendirdi; kabul kararı vermez.

## Bulgular

### Yüksek — sayfa içindeki bütçe nedeniyle atlanan dosyalar yine kalıcı aç kalabilir

panel/server.py:864-903 her çağrıda alfabetik cursor'dan sonraki en fazla 128
dosyayı seçip gerektiğinde başa sarıyor; seçim kilidi cursor güncellemesini
eşzamanlı çağrılara karşı koruyor. Ancak cursor, dosyalar işlenmeden önce
seçilen sayfanın son adına taşınıyor (:901-903). Sayfa işleme sırasında ham
bayt bütçesi tükenirse döngü :1011-1013'te, parse bütçesi tükenirse
:1009-1010'da erken kesiliyor. Erken kesilen dosyalar, sonraki çağrının
başlangıç noktası seçilmiş sayfanın sonu olduğu için aynı sayfa içinde
işlenmiş dosyaların arkasında kalıyor.

Örnek: ilk iki dosyanın parse edilebilir tail'leri 2 MiB toplam parse bütçesini
dolduruyorsa, aynı 128'lik sayfadaki kalan dosyalar her turda atlanır. Sonraki
istek bir sonraki sayfaya gider; tam tur sonunda aynı sayfaya dönünce yine aynı
iki dosya bütçeyi tüketir. Böylece #483'ün sabit ilk 128 dosyanın açlığını
önleme amacı yalnız sayfa dışında kalan adlar için sağlanır; sayfa içi bütçe
açlığı sürer. Raw-byte tavanı da benzer erken kesme üretebilir.

Öneri: cursor'ı seçilen son dosyaya değil, gerçekten tamamlanan/denenen son
dosyaya ilerletmek veya bütçe nedeniyle kalan dosyaların başlayacağı sayfa
offset'ini de döndürmek. Kısmi/boş sonuçların yine ilerleme sağlayacağı ve
eşzamanlı isteklerde cursor güncellemesinin atomik kalacağı sözleşme açıkça
tanımlanmalı.

### Orta — eşzamanlı yanıtların dönüş sırası cursor sırasını garanti etmiyor

Kilit yalnız _ekran_dosya_sayfasi içindeki seçimi ve cursor güncellemesini
kapsıyor. Her HTTP işleyicisi dosyaları kilitten çıktıktan sonra okuyor ve
serileştiriyor. Yavaş kalan önceki isteğin yanıtı, daha sonra seçilmiş sayfanın
yanıtından sonra dönebilir. Bu dosya seçimini bozmaz ve tek başına kalıcı
açlık kanıtı değildir; ancak sözleşme yanıtların geliş sırasına dayalı istemci
rotasyonu bekliyorsa bu garanti mevcut değildir.

### Unicode/JSON serialization — incelenen hata yolu kapatılmış

panel/server.py:997-1002 dosya anahtarını ve kayıt listesini
ensure_ascii=False ile JSON'a çevirip UTF-8'e kodluyor. JSON metnindeki
escaped lone surrogate ("\\ud800") json.loads tarafından Python string'ine
dönüşebilir. jsonl_tail_satirlari bozuk ham UTF-8'i replacement karakterine
çeviriyor (panel/server.py:771-775), ancak escaped surrogate Python string'inde
kalır. #483'ün dosya başına try bloğu UnicodeError, ValueError, TypeError ve
RecursionError'ı yakalayıp dosyayı atlıyor ve serialization_error ekliyor.
Böyle kayıt out içine eklenmediğinden _gonder'a ulaşmıyor. Statik incelemede
bu hata yoluna dair bulgu yok.

### Bilgi — 2 MiB tavan ekran map'ine ait; tam HTTP yanıtına değil

EKRAN_CIKTI_TOPLAM_BAYT, ekranlar map'inin serialized boyutunu sınırlar.
Sayaç anahtar, kolon ayıracı, map elemanları arası virgül ve dış süslü
parantez baytlarını hesaplıyor; mevcut json.dumps(..., ensure_ascii=False)
biçimiyle uyumlu. Dosyanın tüm satır listesi sığmazsa dosya atlanıyor,
output_byte_limit metadata'ya giriyor ve sonraki dosya deneniyor.

#459 belgesi tüm /api/veri yanıtının kullanıcı, görev ve mesaj alanlarıyla
birlikte sınırlanmadığını açıkça söylüyor. _gonder (panel/server.py:1600-1607)
tüm yanıtı bellekte serileştirip kodluyor; genel HTTP yanıtı için ayrı bayt
tavanı yok. Bu ekran-map sözleşmesine göre regresyon değil; tam response byte
cap beklentisi varsa açık kapsam boşluğudur.

## Sonuç

Unicode/JSON serialization düzeltmesi mevcut akışta doğru şekilde dosyayı
atlayıp partial metadata'ya işaretliyor; ekran map'inin 2 MiB tavanı da
serileştirilmiş map biçimine uygun hesaplanıyor. Rotasyon cursor'ı process
local, kilit altında güncelleniyor ve restartta başa dönmesi belgelenmiş.
Ancak cursor'ın bütün seçili sayfayı işlenmeden önce tüketmesi, parse/raw
bütçesiyle kesilen sayfalarda sabit sayfa içi açlığa neden olabilir. Tam HTTP
yanıt tavanı yok; bu sınır #459 dokümanında açıklanmış durumda. Bu inceleme
salt okunurdur; test veya runtime çalıştırılmadı.
