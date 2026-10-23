# #559 — Ekran kayıtlarında sır maskeleme ve rotasyon incelemesi

**Kapsam:** Kaynak ve mevcut karar notlarının statik incelemesi. Canlı ekran
kayıtları, backup'lar, auth sırları veya servis durumu açılmadı. Kod ve gerçek
veri değiştirilmedi.

## Mevcut akış

| Yol | Bugünkü davranış | Mahremiyet etkisi |
|---|---|---|
| Panel yazımı | `api_ekran()` body'deki `satir` değerinin yalnız sağ boşluğunu siler, sonra `ekran_yaz()` kaydı `ekle()` JSONL append yoluna verir (`panel/server.py:1296-1310, 878-885, 377+`). | `satir` ve görünen ad ham biçimde serialize edilir; credential sınıflandırması veya maskeleme yoktur. |
| CLI yazımı | `yuva ekran` satır argümanlarını birleştirip `/api/ekran` çağırır. POST'un kesinlikle gönderilmediği kanıtlanırsa yerel `ekle_jsonl()` fallback'i kullanılır; belirsiz POST sonucu ikinci yazım üretmemek için reddedilir (`bin/yuva:1631-1655, 825-870`). | Panel ve yerel fallback iki ayrı JSONL writer'ıdır; ikisi de aynı ham satırı saklar. Fallback mevcut ortak redactor'dan geçmez; böyle bir redactor henüz yoktur. |
| Panel snapshot | `/api/veri` `tum_ekranlar()` üzerinden dosyaların sınırlı tail'lerini yanıta alır (`panel/server.py:938-1068, 1540-1544`). | 128 dosya, okunan/parse edilen/serileştirilen byte ve satır bütçeleri yalnız seçimi sınırlar. Snapshot için HMAC POST kapısı uygulanmaz; yanıt no-store olsa da veri tarayıcı belleğine gider. |
| Gösterim ve CLI okuma | UI son satır özetini ve tail'i HTML escape ederek gösterir (`panel/ui.html:2011-2024`). `yuva ekran oku` satırları terminale ham metin olarak basar (`bin/yuva:1658-1703`). | HTML escape script enjeksiyonunu önlemeye yöneliktir, secret redaksiyonu değildir. UI'dan gizlemek API/JS belleği, terminal, dosya veya same-UID erişimini temizlemez. |
| Backup ve restore | Tam KOK arşivi `ekran/` dahil tüm veriyi kopyalar; restore-check aracı da seçilen backup'ı scratch alana açar. | Bir satırın ana JSONL'den silinmesi tek başına backup ve restore kopyalarını silmez. Bu inceleme hiçbir backup'ı açmadı. |

Panel ve CLI JSONL writer'ları kilit, izin ve symlink kontrolleri yapar; içerik
sınıflandırması yapmaz. Ekran başına tail/byte sınırı dosyada saklanan toplamı
sınırlamaz. Writer'da segment rotasyonu, yaşa bağlı temizleme veya ekran başına
girdi boyutu kuralı görünmüyor. Okuyucuda 16 KiB satır bütçesi bulunması, daha
büyük satırların yazım anında reddedildiği anlamına gelmez.

## Önerilen maskeleme sınırı ve veri akışı

1. **Bir ortak write-boundary redactor kullanın.** Panel `ekran_yaz()` ve CLI
   `ekle_jsonl()` fallback'i aynı modüle yönelsin. Sadece `api_ekran()` içine
   filtre eklemek, yerel fallback'i ve doğrudan writer çağrılarını açık bırakır.
2. **Nesne şekli doğrulandıktan sonra bütün metin alanlarını tarayın.** Ekran
   kaydında en az `satir` ve `ad` alanları; varsa metin taşıyan ek metadata da
   sınıflandırılmalı. `kimlik` ve `tur` değerleri ayrı biçim allowlist'leriyle
   doğrulanmalı. Bilinen yüksek güvenli sınıflar arasında bearer/session
   token'ları, API/private key biçimleri, cookie/authorization değerleri ve
   credential içeren URL bölümleri bulunmalı. Marker kategori adı taşıyabilir;
   eşleşen değer, çevresindeki hassas metin ve düz hash kayda konmamalı.
3. **Serialize etmeden önce maskelenmiş kayıt üretin.** Akış: boyut ve şekil
   kontrolü → alan sınıflandırması/redaksiyon → maskeleme sonrası şema ve
   encoded-record boyutu kontrolü → UTF-8/JSON serialization → kilitli append.
   Böylece panel cevabı ve yerel fallback aynı redakte edilmiş içeriği yazar.
4. **Redactor yoksa, hata verirse veya sınıflandırma kararsızsa yazmayı
   reddedin.** Ham metne fallback, sessiz satır atlama veya exception'a içerik
   ekleme olmamalı. CLI kullanıcıya içerik içermeyen hata kodu versin; panel
   hata loguna satır, token, header veya regex eşleşme parçası yazmasın.
5. **UI/API masking'i ikincil kontrol sayın.** Önceden yazılmış satırlar,
   JSONL/CLI, browser memory, backup ve same-UID süreçler ancak ayrı işlemle
   ele alınabilir. Yeni writer redaksiyonu geçmiş kayıtları geriye dönük
   temizlemez. Ham kanıt gerçekten gerekiyorsa JSONL dışındaki ayrı depo için
   erişim, encryption, audit, TTL ve backup kararları alınmadan açılmamalı.

Bu öneri #465'in write-time redaction/fail-closed taslağıyla uyumludur; ancak
#465 henüz uygulama kararı değildir. Regex/heuristic tam DLP garantisi vermez:
parçalı veya kodlanmış sırlar, özel provider biçimleri ve bilinmeyen kullanıcı
değerleri kaçabilir. Kullanıcıya credential'ı ekrana yazmama talimatı sürmeli;
maskeleme “ekran çıktısında hiçbir sır bulunamaz” garantisi olarak sunulmamalı.

## Rotasyon ve saklama

Bugün her kimlik için tek `ekran/<kimlik>.jsonl` append dosyası vardır. Otomatik
rotasyon/silme yoktur. #449/#546'daki **aday** değerler ekran kimliği başına
8 MiB veya 24 saat segment, 7 gün saklama ve toplam 256 MiB'dir; hacimle
doğrulanmamış ve operatörce onaylanmamıştır. Bunları mevcut davranış gibi
sunmayın veya uygulamada etkinleştirmeyin.

Önerilen rotasyon sözleşmesi, bu eşikler operatörce kabul edildikten sonra:

- Tek aktif segment append almaya devam eder; segment boyu veya yaşı eşik
  sınırına gelince ortak Yuva yazma kilidi altında kapatılıp yeni aktif segment
  açılır. İçerik kesilmez; aktif dosya truncate edilmez.
- Dosya adı kimlik + UTC başlangıç zamanı + sıra numarası içersin. Rename,
  directory `fsync` ve küçük bir manifest güncellemesi sıralı ve crash sonrası
  uzlaştırılabilir olsun. `rotation_unknown`/fsync belirsizliğinde yeni
  segment açma, eski segment silme veya otomatik retry yapılmasın.
- Yaş ve toplam byte bütçesi birlikte uygulanacaksa minimum yaş korunmalı.
  Bütçe dolduğunda henüz yaşı dolmamış eski segmentleri sessizce erken silmek
  yerine yeni ekran yazımını görünür hata ile durdurup operatör kararı isteyin.
  Eski kapalı segmentlerin silinmesi yalnız kabul edilmiş retention kuralı,
  hold kontrolü ve içerik taşımayan audit kaydıyla yapılmalı.
- Backup/restore segmentleri, manifesti, redaction-policy sürümünü ve
  retention metadata'sını aynı hassasiyet sınıfında taşımalı; birincil dosya
  silme backup kopyasını temizlemiş sayılmamalı.

7 gün/256 MiB ve 8 MiB/24 saat adayları onaylanmadan, aktif dosyanın rota
adlandırması, kilitli rename sırası, retention/bütçe önceliği ve silme audit
hedefi karara bağlanmış değildir. Ölçümsüz adayları uygulamak kapsam dışıdır.

## Öncelikli kabul maddeleri

- Tek redactor'ın panel ve CLI fallback için ortak kullanıldığını; redactor
  hatasında hiçbir yolun ham yazmadığını sentetik fixture ile doğrula.
- Fixture seti en az bearer/API key/cookie örnekleri, credential URL, metin
  olmayan/bozuk alan, uzun kayıt, false positive benign metin ve redactor
  exception senaryolarını içersin. Gerçek credential veya ekran satırı
  fixture'a ya da rapora alınmasın.
- Başarı fixture'ı yalnız marker ve redacted metadata'nın kalıcı forma ulaştığını;
  ret fixture'ı JSONL'nin değişmediğini göstersin. Test, backup veya UI
  snapshot'ında ham satır sızıntısı olmadığını sentetik veriyle sınasın.
- Rotation fixture'ları eşikte yeni segment, eşzamanlı append, crash/rename/
  fsync belirsizliği, yaş dolmadan global bütçe dolması ve backup'ta segment
  kümesinin korunmasını sınasın.

## Dayanaklar ve sınır

- `docs/panel-privacy-redaction-inventory-453.md`: panel/CLI writer ve reader
  yolları, raw satır saklama, read-time bütçelerinin saklama/redaksiyon olmadığı.
- `docs/jsonl-redaction-policy-adr-465.md`: ortak write boundary, seçenek B
  önerisi, fail-closed redaction ve açık kalan DLP/ham kanıt kararları.
- `docs/local-data-retention-export-deletion-policy-546.md` ve
  `docs/jsonl-retention-operator-decisions-449.md`: saklama/rotation sayıları
  aday; ölçüm ve operatör kararı olmadan cleanup açılmaması.
- `docs/panel-error-redaction-548.md`: panel hata logu redaksiyonu. Bu, ekran
  içeriğinin write-time masking'i değildir ve #559'un yerine geçmez.

Bu görevde canlı ekran/backup içeriği, secret, log veya servise erişilmedi;
maskeleme ya da rotasyon kodu eklenmedi. Bu not kaynak gözlemi ve uygulama
önerisidir; redactor'ın veya retention'ın mevcutta çalıştığı iddiası değildir.
