# Yuva JSONL redaksiyon sınırı

## Karar

`mesaj.jsonl` ve `ekran/<kimlik>.jsonl` hassas içerik taşıyabilir kabul edilsin. Yeni kayıtlar ortak JSONL'ye yazılmadan **önce**, kayıt üreten sınırda sınıflandırılsın ve yüksek güvenli secret redaksiyonu uygulansın. Redaksiyon başarısızsa veya bir credential'ın ham olarak yazılma ihtimali giderilemiyorsa kayıt reddedilsin; ham içerikle sessiz fallback yapılmasın.

Varsayılan paylaşılabilir kayıt, ham kanıt arşivi değildir. İnceleme için ham içerik gerçekten gerekliyse, JSONL dışında, ayrı yetkili erişim ve açık süre sınırı olan bir kanıt deposu kararı gerekir. Bu özellik şu anki JSONL akışının parçası değildir. Bu belge uygulamanın redaksiyon yaptığı veya geçmiş logların temizlendiği anlamına gelmez.

## Neden yazma sınırı

- README.md, sohbeti elle kaydedilip `yuva oku` ile okunan kayıt; ekranları ise terminal çıktısı kaydı olarak tanımlar. Bunlar canlı push veya kimlik kanıtı değildir (README.md, “Panel” ve “W0/W1a/W2”).
- Panelde `api_yaz()` mesajı `ekle()` ile `mesaj.jsonl`'ye, `api_ekran()` ise `ekran_yaz()` üzerinden kimlik başına JSONL'ye verir (`panel/server.py:225`, `:585-588`, `:771-825`). CLI de panel POST'u kesin gönderilmediyse yerel JSONL fallback'i kullanabilir (`bin/yuva:1350-1374`, `:1550-1565`). Dolayısıyla yalnız UI gösterimini temizlemek yeterli değildir; her kalıcı yazım yolu aynı redaksiyon kapısından geçmelidir.
- Panel `mesajlar()` ve `tum_ekranlar()` ile bu kayıtları okur ve `/api/veri` görünümüne dahil eder (`panel/server.py:522-555`, `:592-608`, `:936-963`). CLI mesaj/ekran okuma yolları da aynı dosyaları gösterir (`bin/yuva:445-470`, `:1377-1405`). Saklanan ham secret, bu tüketicilerden ve dosyaya erişebilen süreçlerden açığa çıkabilir.
- README.md, eski mesajların arşiv/görüntüleme verisi olduğunu ve mesaj gövdesinin kimlik/yetki kanıtı olmadığını söyler (README.md, “W0/W1a/W2”). `docs/sohbet-oturum-guven-siniri.md` de ham prompt/çıktıyı yalnız gerekliyse, açık retention ile saklamayı; provenance alanlarını doğrulanmış kimlik yerine koymamayı önerir.

## Veri sınıfı ve varsayılan işlem

| İçerik | Varsayılan işlem | Kayıtta kalabilecek denetim bilgisi |
|---|---|---|
| API anahtarı, bearer/session token, parola, private key, cookie, credential içeren URL veya secret store değeri | Yazmadan önce gizle; yüksek güvenli eşleşme çözümlenemiyorsa kaydı reddet. Secret'ın kendisini veya geri çevrilebilir kodlamasını yazma. | `redacted` işareti, kategori ve kural sürümü; güvenli değilse secret uzunluğu da saklanmasın. |
| Mutlak yerel path, home dizini, kullanıcı adı içeren path | Görev için gerekmiyorsa home/user/path öneklerini kararlı placeholder ile değiştir. Görev bağlamı için path gerekiyorsa yalnız gerekli en dar kök/relative path'i tut. | Path redaksiyonu kategorisi ve kural sürümü. |
| Model çıktısı, komut, traceback, ekran satırı ve kullanıcı mesajı | Güvenilmeyen ve potansiyel secret/kişisel veri kaynağı say; yazma öncesi aynı tarama ve sınıflandırma uygulanır. Büyük veya hassas kanıtı ortak akışa kopyalamak yerine kontrollü artifact tasarımına yönlendir. | Olay kimliği, zaman, kaynak/güven seviyesi ve redaksiyon metadata'sı. |
| Credential olmadığına karar verilen sıradan metin | Kaydet; kullanıcı/model kaynaklı talimatları veri olarak tut, hiçbir yetki/provenance alanına yükseltme. | Mevcut olay alanları; istemcinin verdiği actor id veya `kimden` doğrulanmış principal sayılmaz. |

Regex ve bilinen token biçimleri yararlı bir ilk katmandır, tam DLP garantisi değildir: özel credential biçimleri, parçalanmış secret, görüntü/encoded içerik ve yanlış negatifler kalabilir. Redaksiyon aracı bir içeriği güvenilir biçimde sınıflandıramıyorsa belirsiz içerik ham biçimde kaydedilmemelidir. Aşırı geniş eşleşme normal kodu veya tanı verisini bozabileceği için kategori/kural sürümü ve redaksiyon sonrası kontrol görünür olmalıdır.

## Kanıt ve denetlenebilirlik

1. JSONL'de orijinal metin yerine redakte edilmiş metin saklanır; marker hangi sınıfın hangi kural sürümüyle gizlendiğini belirtir. Olay ID'si, timestamp, kaynak, `trust=unverified` ve benzeri köken bilgileri korunabilir; bunlar kimlik doğrulaması değildir.
2. Ham değerin düz SHA-256 özeti de tutulmaz. Düşük entropili bir token/parola sözlük saldırısıyla tahmin edilebilir. Tekilleştirme zorunluysa yalnız ayrı korunan anahtarlı HMAC değerlendirilsin; varsayılan karar fingerprint saklamamaktır.
3. Redaksiyonun kendisi de hata üretebilir. Kaydetmeden önce çıktı UTF-8/JSON olarak doğrulanmalı; hata varsa ham satıra geri düşmeden kayıt reddedilmelidir. Redaksiyon logları yakalanan değeri veya çevresindeki hassas metni içermemeli.
4. Önceden yazılmış kayıtlar değişmeden kalır. Geçmiş JSONL'yi redakte etmek ayrı, yedekleri ve kopyaları kapsayan, onaylı migration/olay müdahalesi gerektirir; bu karar notu otomatik rewrite yetkisi vermez.
5. Erişim günlükleri içerik kopyalamamalı. Yalnız principal/OS UID, dosya veya artifact kimliği, eylem, zaman ve sonuç gibi asgari metadata tutulmalı.

## Erişim ve güven sınırı

| Aktör | JSONL'yi okuyabilir mi? | JSONL'ye yazabilir mi? | Sınır |
|---|---|---|---|
| Aynı OS UID altındaki yerel süreç | Genellikle evet; izinler aynı UID'yi birbirinden ayırmaz. | Panel/CLI yoluyla veya doğrudan kullanıcıya ait dosyalara yazabilir. | Loopback, `--from`, görünen ad ve dosya modu aynı UID'li süreçlere karşı actor doğrulaması değildir. Uygulama/proses izolasyonu gerekir. |
| Farklı yerel UID | Kök ve dosyalar `0700`/`0600`, doğru owner ile kurulmuşsa normalde hayır. | Aynı izinlerle normalde hayır. | Yanlış/eskimiş izin, ACL, yedek veya başka kopya bu varsayımı bozar; root ayrıcalığı bu sınırın dışındadır. |
| Yerel tarayıcı / loopback istemcisi | Panelin sunduğu görünümü okuyabilir. | Panelin açık yazma uçlarına ulaşmayı deneyebilir. | Loopback bind ve Host/Origin kontrolleri saldırı yüzeyini daraltır, kimlik doğrulamaz; aynı kullanıcıda çalışan zararlı süreçten koruma sağlamaz (`panel/server.py:990-1005`, `:1028-1075`; README.md W1a). |
| Model/ajan oturumu | Yalnız kendisine gösterilen Yuva ekranı, sohbet veya başka bağlamı görür. | Ancak eriştiği panel/CLI çağrısı ya da aynı UID dosya yetkisi varsa. | Model çıktısı ve gösterilen log, secret içerme ihtimali olan untrusted veridir; model kimliği veya onay kanıtı değildir. |
| Root / yedek veya host yöneticisi | İşletim sistemi/yedek erişimi varsa evet. | Evet. | Bu tasarım host yöneticisine karşı gizlilik sağlamaz; yedekler de aynı redaksiyon ve süre politikalarına bağlanmalıdır. |

Dosya modu yalnız farklı UID'ler arasındaki erişimi sınırlar; aynı UID izolasyonu sağlamaz. `#434` güvenli append çalışmasıyla yeni kök/ekran dizini `0700`, yeni JSONL `0600` olmalı ve mevcut izinler sessizce chmod edilmemelidir. Kurulum bu modları karşılamıyorsa yazıcı fail-closed davranmalı; operatör kontrollü izin düzeltmesi yapılana kadar kayıt alınmaması kabul edilmelidir. `docs/local-api-access-boundary.md` de Unix peer credential'ın OS sürecini/UID'yi doğruladığını, model veya ajan kimliğini doğrulamadığını belirtir.

## Saklama, erişim ve uygulama sırası

- Önce tek ortak redaksiyon fonksiyonunu panel ve CLI yerel fallback dahil tüm JSONL yazıcılarında çağır; redaksiyon sonrası serialization ve satır sınırlarını kontrol et. Logların okunma/gösterim katmanı ikinci savunma olabilir ama yazma öncesi redaksiyonun yerine geçmez.
- Mevcut `#438` append kontrolleri symlink/no-follow ve izin yarışını daraltır; hassas içerik sınıflandırması veya aynı-UID izolasyonu sağlamaz. Bu iki kontrol ayrı kabul edilmelidir.
- `#439` UID erişimi ve `#440` retention işleri kendi kapsamlarında kalır. Redaksiyon, dosya ACL/UID tasarımının veya saklama/silme süresinin tamamlandığı anlamına gelmez. Aktif log, arşiv, export, yedek ve geçici dosyanın tamamı için aynı hassasiyet sınıfı geçerlidir.
- Retention süresi dolunca ham kanıt dahil tüm kopyalar silinmeli veya yeniden yetkilendirilmiş ayrı saklama politikasına alınmalıdır. Bu belge süre belirlemez; `docs/jsonl-retention-design.md` yalnız tasarım önerisidir ve uygulanmış davranış değildir.
- Rollout öncesi redaksiyon false-positive/false-negative örnekleri sentetik veride doğrulanmalı; normal log ve hata çıktısında secret sızıntısı ayrıca gözden geçirilmeli. Test ve migration bu karar notunun kapsamı değildir.

## Açık kararlar

Üretim için secret sınıflandırma kural seti, path placeholder politikası, redaksiyon hata metriği, ham kanıt için ayrı depo gereksinimi, erişim principal'ı, artifact boyut/retention limitleri ve geçmiş log/backup migration prosedürü belirlenmelidir. Bunlar karara bağlanıp uygulanana kadar doğru beyan: **JSONL'de redaksiyon garantisi yoktur; loglar hassas ve host kullanıcısı erişimine açık kabul edilmelidir.**
