# #465 — JSONL redaksiyon politikası ve kayıpsız kanıt kararı

- Durum: öneri; uygulama kararı değil
- Kapsam: `mesaj.jsonl` ve `ekran/<kimlik>.jsonl` için yeni kayıtların
  sınıflandırılması, redaksiyonu ve ham kanıtın ele alınması
- Dayanak: `docs/jsonl-redaction-boundary.md` ve
  `docs/panel-privacy-redaction-inventory-453.md`

## Karar özeti

Paylaşılabilir JSONL akışına yalnız redaksiyondan geçmiş kayıt yazılması
önerilir. Aynı ortak redaction/write kapısı panel, CLI fallback'i ve sistem
mesajları dahil her kalıcı JSONL yazma yolunda serialization'dan önce
çalışmalıdır. Yüksek güvenli eşleşmeler maskelenmeli; belirsiz, hatalı veya
redactor'ın işleyemediği kayıt ham biçimde yazılmamalı ve sessizce atlanmamalı,
açık hata ile reddedilmelidir. Ham inceleme kanıtı ortak JSONL'den ayrı,
erişimi ve yaşam döngüsü ayrıca kararlaştırılmış bir depoda tutulabilir; böyle
bir depo mevcut davranış değildir ve bu ADR tek başına açılmasına yetki vermez.

Bu öneri eşleşme kurallarının tam listesini, saklama sürelerini, boyut
limitlerini veya erişim rollerini belirlemiyor. Bu değerler kaynaklarda
kararlaştırılmış değil; uygulama öncesinde sahipleri tarafından ayrıca
seçilmelidir.

## Karar bağlamı

Panel ve CLI, kullanıcı/model mesajı ile terminal satırlarını ortak JSONL
dosyalarına yazabilir. Bu içerikler credential, kullanıcı tanımlayıcıları,
yerel yollar veya başka kişisel veriler içerebilir. Ekran başına okuma limiti,
API yanıt bütçesi, HTML escape ve dosya izinleri yazılan içeriği redakte etmez.
Mevcut akışta JSONL yazma öncesi redaksiyon garantisi yoktur. Önceden yazılmış
kayıtlar ve yedekler bu yeni politikayla geriye dönük temizlenmiş sayılmaz.

Temel çatışma: ortak kayıt kolay aranabilir ve kayıpsız yerel geçmiş sağlar;
ancak secret/PII'nin tüm kopyalarını aynı geniş erişimli akışta tutmak
paylaşılabilir kayıt amacıyla çelişir. Ham içeriği sonradan kurtarmak için
JSONL'de düz değer veya geri çevrilebilir temsil bırakmak bu çatışmayı çözmez.

## Sınıflar ve önerilen varsayılan işlem

| Sınıf | Önerilen paylaşılabilir JSONL işlemi | Ham kanıt ihtiyacı |
|---|---|---|
| Yüksek güvenli credential: API/private key, parola, bearer/session token, cookie, secret store değeri ve credential içeren URL bölümü | Credential değeri serialization öncesi geri çevrilemez marker ile değiştirilsin. Tanıma ya da redaksiyon güvenilir biçimde tamamlanamazsa kayıt reddedilsin; ham fallback olmasın. | Gerekliyse ayrı kanıt deposunda, ayrı yetki ve yaşam döngüsü kararıyla tutulabilir. |
| Yerel kimlik ve path: home dizini, kullanıcı adı içeren mutlak path, makineye özel dizin | Görev için gerekmiyorsa kararlı genel placeholder kullanılsın. Görev için gerekliyse mutlak kök yerine gerekli en dar göreli/path bileşeni tutulsun. | Makineye özel tam path ancak açıkça gerekliyse ayrı kanıta alınsın. |
| Doğrudan kişisel tanımlayıcı: e-posta, telefon, hesap/kimlik numarası veya kişiyle doğrudan ilişkilendirilebilen benzer değer | Varsayılan olarak redakte edilsin. Tekil görevin gerektirdiği tanımlayıcı varsa açıkça kapsamlandırılmış, en az veri içeren biçim kararı verilsin. | Ham tanımlayıcı paylaşılabilir akışta tutulmasın; kanıt deposu gerekiyorsa aynı ayrı kontrol geçerli olsun. |
| Hassas kişisel nitelik veya bağlam: sağlık, finans, konum, özel hayat ve kişiyi tanımlayan serbest metin | Gereksiz ayrıntı redakte edilsin veya kayıt reddedilsin. Sadece görev için gereken asgari ve mümkünse kişisizleştirilmiş bilgi kalsın. | Ham bağlamın tutulması ayrıca gerekçelendirilip erişimi sınırlandırılsın. |
| Teknik metin: komut, kod, traceback, model çıktısı, ekran satırı ve sıradan mesaj | Untrusted veri olarak aynı taramadan geçsin. Yüksek güvenli secret/PII eşleşmeleri redakte edilsin; yalnız sınıflandırma eşiğini geçen sıradan içerik saklansın. | Büyük veya hassas tanı çıktısı ortak JSONL yerine ayrı kanıt gereksinimi olarak ele alınsın. |
| Redaksiyon sonucu ve olay metadata'sı | Yalnız redakte metin; kural/kategori sürümü gibi asgari metadata tutulabilir. Secret'ın kendisi, çevresindeki hassas alıntı veya düz hash yazılmasın. | Ham içeriğe bağ kuran HMAC/fingerprint varsayılan olmasın; ihtiyaç varsa ayrı güvenlik kararı gerekir. |

Bu sınıflar ilk politika taslağıdır, eksiksiz DLP iddiası değildir. Özel
credential biçimleri, kodlama/obfuscation, parçalı değerler, görsel/binary
içerik ve dilsel kişisel veriler regex ile tam yakalanamaz. Herhangi bir
sınıflandırma sistemi bu sınırı kullanıcıya ve operatöre açıkça bildirmelidir.

## Seçenekler

### A. Ham JSONL'yi koru, yalnız UI/API'de maskele

Operasyonel olarak en az müdahaleli seçenektir ve kayıpsız yerel geçmişi
korur. Ancak dosyaya, CLI okuyucularına, yedeklere ve aynı UID süreçlerine ham
değerleri açık bırakır. Gizleme veri diske ve API belleğine ulaştıktan sonra
uygulanır; paylaşılabilir kayıt hedefini sağlamaz. Önerilmez.

### B. Tek ortak akışta yazma öncesi redakte et, belirsiz kaydı reddet

JSONL paylaşılabilir kopya olur; panel ve CLI aynı redaction/write sınırını
kullanır. Yüksek güvenli eşleşmeler maskelenir. Bir kaydın güvenli biçimde
sınıflandırılması mümkün değilse yalnız o kayıt reddedilir, neden içerik
sızdırmayan bir hata koduyla bildirilir ve ham fallback yapılmaz. Bu yol
redakte edilmiş kaybı kalıcı hale getirir; geçmiş/kanıt gereksinimi olan
işlerde tanı ayrıntısı azalabilir. Ayrı ham kanıt deposu gerektirmeyen
kurulumlar için en küçük kapsamlı öneridir.

### C. Paylaşılabilir JSONL ve ayrı kontrollü ham kanıt deposu

Ortak JSONL redakte kalır; yalnız açıkça gerekli ham çıktı ayrı artifact olarak
alınır. Denetlenebilirliği ve hata ayıklamayı koruyabilir; fakat yeni bir
hassas veri yüzeyi, erişim denetimi, audit, backup ve silme/retention yükü
oluşturur. Kimlerin okuyacağı, hangi olaylarda açılacağı, bağlantı referansının
nasıl korunacağı, süre/kapasite sınırları ve tüm kopyaların nasıl silineceği
belirlenmeden devreye alınmamalıdır. Hash veya artifact ID tek başına erişim
kontrolü değildir.

## Yanlış pozitif ve belirsizlik politikası

1. **Kesin eşleşme:** Tanımlı credential biçimi veya kişisel veri kuralı
   yüksek güvenle eşleşirse yalnız hassas span redakte edilir; kalan kayıt
   korunur. Marker kategori bilgisini verebilir, gizlenen değeri veya uzunluğu
   vermez.
2. **Olası eşleşme, çözülemeyen belirsizlik:** Normal kodu/traceback'i bozma
   ihtimali olan ama güvenle ayırt edilemeyen değer sessizce ham bırakılmaz.
   Varsayılan öneri ilgili kaydı reddetmek ve kullanıcıya içerik göstermeyen
   kategori/genel hata bildirmektir. Tüm sohbeti veya ekran oturumunu durdurma
   yerine kayıt sınırında fail-closed davranılır.
3. **Bilinen zararsız biçim:** Dosya yolu veya token benzeri sözdiziminin
   zararsız olduğu biliniyorsa allowlist yalnız dar, belgelenmiş yapıya
   uygulanır; genel `ignore` kalıbı veya kullanıcı tarafından serbestçe
   değiştirilen bypass kuralı olmaz.
4. **Doğrulama:** Kurallar sentetik pozitif, negatif ve sınır örnekleriyle
   değerlendirilir. False positive düzeltmesi ham veriyi loglamakla yapılmaz;
   test fixture'ları sentetik tutulur ve kural değişikliği sürümlenir.
5. **İçerik sızıntısız hata:** Redaction logu yakalanan değeri, yakın metni,
   düz hash'i veya geri çevrilebilir kodlamayı içermez. Reddin nedeni yalnız
   kategori/kural kodu seviyesinde olabilir.

Bu eşiklerle sıradan metni korumak ve belirsiz secret'ı sızdırmamak arasında
tercih yapılır. Kaynaklarda onaylanmış bir kabul oranı, regex listesi veya
yanlış pozitif metriği yoktur; nicel eşik uydurulmamalıdır.

## Ham kanıt kararı

Önerilen varsayılan: ham değer ortak JSONL'ye yazılmaz ve bu ADR ham kanıt
deposunu otomatik olarak etkinleştirmez. Önce her kullanım için “hangi tanı
sorusu redakte kayıttan cevaplanamıyor?” gerekçesi gösterilsin. Depo
onaylanacaksa ayrı karar en az şu konuları belirlemelidir:

- okuyucu principal'ları ve yetki verme/geri alma yolu;
- olay bazlı erişim kaydı ve loglarda içerik tutmama;
- saklama süresi, boyut sınırı ve süresi dolan kopyaların/backup'ların
  silinmesi;
- JSONL ile artifact bağının gizli erişim kabiliyetine dönüşmemesi;
- encryption/key custody, backup/restore ve incident süreci;
- redaksiyon servisi veya artifact deposu kullanılamadığında fail-closed
  davranışı.

Bu kararlar mevcut taslak kaynaklarda verilmediği için süre, byte limiti,
rol adı veya onay mercii burada sayısallaştırılmıyor.

## Sonuç ve uygulama önkoşulları

**Öneri: B varsayılanı; C yalnız ayrıca onaylanmış ve tasarlanmış kullanım
için.** Ortak JSONL'ye yazmadan önce panel, CLI fallback ve sistem kayıtları
aynı redactor'dan geçmeli. Serialization/UTF-8/JSON doğrulaması redaksiyondan
sonra yapılmalı; hata veya belirsizlikte yazım reddedilmeli. UI/API masking,
retention ve dosya izinleri tamamlayıcı kontrollerdir, redactor yerine geçmez.

Uygulama öncesi karara bağlanması gerekenler: kural seti ve sürümleme, yerel
path placeholder biçimi, PII alanlarının görev istisnası, içerik sızıntısı
yapmayan ret hata sözleşmesi, redactor'ın her yazıcıya zorunlu bağlanması,
synthetic test kapsamı, ham artifact gereksinimi ve kabul edilirse erişim/
retention/backup politikası. Geçmiş JSONL/backup taraması, rewrite ve
incident müdahalesi ayrı kapsamdır.

Bugünkü durum hakkında beyan değişmez: mevcut JSONL akışı redaksiyon garantisi
sağlamaz; bu ADR politika önerisidir, uygulanmış kontrol veya geçmiş temizliği
değildir.
