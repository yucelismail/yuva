# #453 — Panel gizlilik/redaksiyon uygulama envanteri

Bu envanter `docs/jsonl-redaction-boundary.md` kararını mevcut panel, CLI ve
UI akışıyla eşleştirir. **Bugünkü kodda JSONL yazma öncesi secret/path
redaksiyon garantisi yoktur.** Tail boyutu, dosya modu ve HTML escaping bu
garantinin yerine geçmez.

## Veri akışı

| Veri | Kaynak ve yazma yolu | Kalıcı hedef | API / gösterim |
|---|---|---|---|
| Sohbet metni | UI `gonder()` `/api/yaz` POST eder (`panel/ui.html:2155-2165`). CLI `yuva yaz` önce aynı uca gider; yalnız POST kesin gönderilmediyse yerel `mesaj_ekle()` fallback'i yazar (`bin/yuva:1617-1631`). Panel handler `api_yaz()` ardından `mesaj_ekle()` çağırır (`panel/server.py:857-889`). | `mesaj.jsonl`; içerik `metin` alanında ham biçimde saklanır. CLI ve panel ayrı `mesaj_ekle`/JSONL writer yolları kullanır (`bin/yuva:454-465`; `server.py:522-548`). | `/api/veri` `mesajlar()` sonucunu döndürür (`server.py:1115-1119`). UI son 80 kaydı sohbet DOM'una koyar (`ui.html:623-655`); CLI `yuva oku` da JSONL geçmişini basar (`bin/yuva:1634-1640`). |
| Ekran/terminal satırı | `yuva ekran` `/api/ekran` çağırır; yalnız POST kesin gönderilmediyse yerel JSONL fallback'i kullanır (`bin/yuva:1414-1438`). Panel `api_ekran()` -> `ekran_yaz()` zincirini kullanır (`server.py`, `api_ekran` ve `ekran_yaz`). | `ekran/<guvenli kimlik>.jsonl`; `satir` ham saklanır. | `/api/veri` `tum_ekranlar()` ile deterministik ada göre en fazla 128 dosyanın sınırlı tail'lerini aktarır (`server.py`, `EKRAN_DOSYA_AZAMI` ve `tum_ekranlar`). Toplam ham okuma 8 MiB, parse girdisi 2 MiB, `ekranlar` map çıktısı 2 MiB ile sınırlıdır; kesinti `ekranlar_meta.partial` ve `partial_reasons` ile bildirilir. UI grid/birleşik/tek model/modal görünümlerinde gösterir (`ui.html`, `ekranCiz`); CLI `yuva ekran oku` ise dosyaları doğrudan okur (`bin/yuva:1441-1470`). |
| Sistem mesajı | Katılma, ayrılma, ad ve rol değişimi mesajları aynı panel `mesaj_ekle()` yolundan üretilir (`server.py:688-805`). | `mesaj.jsonl`, yine redaksiyonsuz. Görünen adlar ve sistem metni de arşivlenir. | Sohbetle aynı `/api/veri` ve UI akışı. |

Panel JSONL append'leri merkezi `ekle()` fonksiyonunda, CLI append'leri `ekle_jsonl()` içinde JSON serialize edilir (`server.py:225-260`; `bin/yuva:170-210`). Her iki yol da dosya/lock/symlink güvenliği uygulasa bile içerik sınıflandırması yapmıyor. Bu kontroller saklama erişimini daraltır; secret'ı dosyaya yazılmadan engellemez.

## Mevcut saklama ve aktarım sınırı

- Panel sohbet okuması en fazla 200 kayıt döndürür; bounded tail taraması 2 MiB, satır başına 64 KiB ile sınırlıdır. `/api/veri` ekran okuması dosya başına en fazla 60 kayıt, en fazla 1 MiB tarama rezervasyonu ve satır başına 16 KiB uygular; ayrıca toplamda en fazla 128 ada göre ilk dosyayı seçer, 8 MiB toplam ham okuma, 2 MiB toplam JSON parse girdisi ve 2 MiB serileştirilmiş `ekranlar` map'i sınırlarını uygular. Bir sınır veri dışarıda bıraktığında `ekranlar_meta.partial=true` ve `partial_reasons` dönülür. Bu sınırlar dosya başı limitlerin toplam sınır yerine geçmediğini açıkça ayırır. Bunlar okuma/yanıt bütçeleridir; eski kayıtları silmez ve geçmişteki hassas içeriği redakte etmez.
- JSONL yazıcılarında bu akış için yaş/boyut retention veya rotation görünmüyor. `docs/jsonl-retention-design.md` bir tasarım önerisidir; bounded tail, dosyanın disk üzerindeki boyutunu ve ömrünü sınırlamaz.
- `/api/veri` yanıtı tarayıcıya en fazla son 200 sohbet kaydını ve ekran bütçeleri içinde seçilmiş dosyaların en fazla 60 satırını taşır. Ekran verisi 128 dosya, 8 MiB toplam ham tarama, 2 MiB parse girdisi ve 2 MiB map çıktısı bütçelerine tabidir; seçilmeyen/çıktıya sığmayan ekranlar `ekranlar_meta` kısmi durumuyla açıklanır. Sohbet panelinin 80 satır göstermesi veya kullanıcının tek ekran seçmesi API yanıtındaki diğer kaydı daraltmaz; istemci belleğindeki `S.veri` API'nin döndürdüğü veri kümesini içerir. GET yolu HMAC POST kapısının kapsamı dışındadır (`server.py`, API route tanımları).
- Aynı OS UID süreçleri, CLI ve panel kullanıcı hesabı dosyalarına erişebilir. JSONL metnini UI'dan gizlemek veya panel rolüne göre kart saklamak, doğrudan dosya/CLI erişimini engellemez (`docs/jsonl-redaction-boundary.md`, Erişim ve güven sınırı).
- Mevcut kod `mesaj_ekle()` ve `ekran_yaz()` içinde ham içerik için redaction metadata üretmiyor. Sohbet provenance alanlarının `unverified` olması aktör iddiasını sınırlar; mesaj gövdesini gizlilik açısından temizlemez (`server.py:522-548,655-662`).

## Redaksiyon hangi katmanda uygulanabilir?

| Katman | Uygun rol | Sınır / kayıpsız geçmiş etkisi |
|---|---|---|
| Üretici/write boundary | Zorunlu birincil kontrol. Ortak redactor, serialization'dan önce metin ve metadata'yı sınıflandırıp sonucu ya redakte ederek döndürmeli ya da yazımı reddetmeli. Panel sohbeti, sistem mesajı, ekran satırı ve CLI yerel fallback'leri aynı kurala bağlanmalı. | Redaksiyon kalıcı ve geri döndürülemez; `mesaj.jsonl` / ekran JSONL artık ham orijinali içermez. Görev kanıtı veya hata ayıklama için bu kayda güvenen akışlar etkilenir. Redactor yoksa/error verirse ham fallback yasak olmalı. |
| JSONL writer / serializer | Ortak son koruma noktası; doğrudan writer kullanan yeni producer'ların redactor'ı atlamasını önler. Birden fazla entry-point kalmaması için panel `ekle()` ve CLI `ekle_jsonl()` aynı paylaşılan yazma API'sini kullanmalı. | Writer'a gelen nesne şema doğrulamasından sonra redakte edilmeli; mesaj/ekran formatı ve UTF-8/JSON satır bütünlüğü korunmalı. Sadece writer'da tarama, `metin`/`satir` dışındaki hassas alanları ve başka dosya/artifact kopyalarını kaçırmamalı. |
| API/taşıma | Redakte edilmiş gövdeyi dönmek veya okuma kapsamını yetkiye göre azaltmak ikincil kontrol olabilir. `/api/veri` için field-level redaction ve gerekirse pagination/access policy uygulanabilir. | Yalnız response redaksiyonu diskteki ham içeriği, CLI okuyucularını, backup'ları veya başka same-UID süreçleri korumaz. Server'da API öncesi redaction yapıp diskte ham bırakmak paylaşılabilir log politikasına uymaz. |
| DOM/gösterim | UI'da hassas alanı role/tercihe göre maskeleme, kopyalama/ekran görüntüsü riskini azaltan UX kontrolüdür. İçeriği untrusted metin olarak escape etmek de HTML enjeksiyonuna karşı ayrı kontroldür. | Gizleme redaksiyon değildir: veri zaten JSON yanıtı ve JS belleğine ulaşmıştır. Aynı kişinin başka ekranda veya DevTools'ta ham cevabı görmesini engellemez; CLI/JSONL geçmişini değiştirmez. |
| Retention/migration | Süre sonu silme veya eski log/backup temizliği ayrı storage lifecycle kontrolüdür. Önceden yazılmış veriyi dönüştürmek kontrollü migration ve backup kapsamı ister. | Mevcut JSONL'yi yerinde sessiz rewrite etmek kayıpsız yerel arşivi bozar ve kanıt zincirini değiştirebilir. Önceki secret'ları yeni writer temizleyemez. Ayrı onaylı migration, backup/exports, temp dosyaları ve doğrulama planı gerekir. |
| Ham kanıt deposu | Ham çıktının gerçekten gerektiği durumlarda ayrı, dar yetkili, süreli ve erişim kaydı tutan artifact deposu düşünülebilir. JSONL'ye yalnız redakte özet ve artifact referansı konabilir. | Bu depo şu anki akışta yok. Artifact ID de hassas içeriğe erişim kabiliyeti taşıyabileceğinden yetki kontrolü ve retention gerekir; hash tek başına redaksiyon değildir. |

Kayıpsız yerel arşiv ile redaksiyonsuz kayıt aynı dosyada bir arada sağlanamaz.
Paylaşılabilir sohbet/ekran JSONL'si yazma öncesi redakte edilecekse, gerekli
ham inceleme kanıtı ayrı kontrollü depoda tutulmalıdır. Ham JSONL'yi tutup yalnız
UI'da gizlemek gizlilik kararını uygulamaz.

## DOM gösterimi ve kaçış

- Sohbet gövdesi, ad, hedef ve zaman `innerHTML` oluşturulmadan `esc()` ile
  HTML metni/attribute bağlamına kaçırılıyor (`ui.html:496-497,644-655`). Ekran
  satırları, kimlik ve adlar da `satirlarHtml()` içinde escape ediliyor
  (`ui.html:1832-1840`); modal metaverisinin bir bölümü `textContent` kullanır
  (`ui.html:1937-1942`). Bu, gösterim enjeksiyonuna yönelik bir kontroldür,
  secret redaksiyonu değildir.
- Sohbet kartının CSS `class` değeri `m.tur` metnini doğrudan içermez: yalnızca
  `m.tur === "durum"` ve `m.tur === "soru"` kontrolleri sabit `sistem`/`soru`
  class token'larını ekler (`ui.html:638-650`). Türün görünen metin olarak
  yazıldığı `kime` span'inde ise `esc(m.tur)` kullanılır. Bu nedenle mevcut
  render yolunda `m.tur` kaynaklı class injection bulgusu yoktur; HTML escaping
  yine gizlilik redaksiyonu anlamına gelmez.
- Ekran satırı JSONL'de ve API yanıtında durmaya devam eder; grid görünümünde
  son satır hem kart özetinde hem akışta gösterilebilir (`ui.html:1900-1913`).
  Özet/line clamp görsel sunumdur, veri redaksiyonu değildir.

## Uygulama envanteri ve çatışmalar

1. `panel/server.py:522-548` ve `:655-662` en dar panel writer sınırlarıdır;
   fakat CLI `bin/yuva:454-465,1433-1437` aynı dosyalara doğrudan fallback
   yazıyor. Yalnız panel handler'ına redactor eklemek CLI fallback'i açık
   bırakır. Paylaşılan bir redaction/write modülü veya her iki writer'ın aynı
   kütüphaneye bağlanması gerekir.
2. Yeni sohbet mesajı `mesaj.jsonl` ile CLI `yuva oku` için arşiv niteliği
   taşır; ekran satırı da `yuva ekran oku` ve panel debug görünümüne kaynak
   olur. Redaksiyon, dosyadaki ham kanıtı geri alınamaz biçimde değiştirir.
   Önce hangi credential/path/PII değerlerinin görev bağlamında tutulacağı ve
   ham kanıtın ayrı depoya ihtiyaç duyup duymadığı belirlenmelidir.
3. `api_yaz()` mevcut metin için yalnız boşluk trim'i yapar; `api_ekran()`
   yalnız sağdaki whitespace'i temizler (`server.py:863-865,895-900`). Bu
   normalizasyon secret temizliği değildir. Path/credential eşleşmesi ve
   redactor başarısızlığında reject politikası bu noktadan önce/ortak writer'da
   uygulanmalıdır.
4. Secret regex'i eksiksiz DLP değildir. Parçalı token, özel credential
   biçimi, URL encoding, görüntü/binary içerik ve çok uzun satırlar false
   negative doğurabilir; API/UI redaction bu riskleri saklayıp diskte tutar.
   Belirsiz sınıflandırmada fail-closed ve redaction sonrası serialized satır
   boyutu kontrolü gerekir.
5. Bu inceleme hiçbir JSONL, backup, export, yedek veya UI kaydını taramadı ve
   değiştirmedi. Önceden yazılmış olası secret'ların varlığı/yokluğu hakkında
   sonuç çıkarılamaz; migration/incident işi ayrı kapsamdır.

## Kapsam

Salt kaynak envanteri yapıldı. Kod, UI, JSONL geçmişi ve backup'lar
değiştirilmedi; test veya runtime/panel çalıştırılmadı.
