# GET snapshot ve HTML için veri minimizasyonu seçenekleri (#479)

- **Durum:** Karar eki; uygulama veya canlı dağıtım kararı değildir.
- **Kapsam:** `GET /api/veri`, `/veri`, panel HTML'i ve tarayıcı snapshot tüketimi.
- **Yöntem:** Salt-okunur kaynak incelemesi. Kod, test, runtime ve panel çalıştırılmadı. `docs/local-api-get-snapshot-decision-455.md` değiştirilmedi.

## Kaynakta dönen veri

`panel/server.py:1610-1621` `GET /api/veri` ve `/veri` yollarında aynı snapshot'ı döndürür; `/` ve `/index.html` panel HTML'ini verir. Bu GET yollarında `AuthGate` çağrısı yoktur. Opsiyonel `YUVA_AUTH_ENABLED` kapısı yalnızca `do_POST()` içindeki mutasyon yolunda (`server.py:1634-1677`) çalışır. Host/Origin ve loopback kontrolleri istemci UID'sini doğrulamaz; sunucu varsayılan olarak `127.0.0.1`'e bağlanır ve loopback dışı bind'i reddeder (`server.py:1513-1544,1695-1725`). README bu sınırı aynı network namespace'teki başka UID süreçlerinin de HTTP API'ye erişebilmesi olarak açıklar (`README.md:170-182`).

`panel/ui.html:533-553` tarayıcı açılırken ve periyodik yenilemede `/api/veri`'nin tamamını alır; `S.veri` içinde saklar. İstemci tarafında bir alanı gizlemek, JSON yanıtı veya tarayıcı belleğinden o veriyi kaldırmaz.

| Snapshot bölümü | Kaynak ve kapsam | Veri minimizasyonu açısından not |
|---|---|---|
| Kullanıcı kayıtları | `server.py:1408-1427`: kimlik, görünen ad, araç, rol, baş denetçi/üst sorumlu ilişkisi, katılma zamanı, son okuma, `bagli`, kullanıcı notu ve presence alanları. Presence şu an `unknown/false` ve kalp zamanı `null` döner. | Kimlik, ekip/rol ilişkileri ve okuma zamanı davranış/metaveri açığa çıkarır. `not_` serbest metin olabilir. `bagli` alanı tek başına presence kanıtı değildir. |
| Görevler | `server.py:522-535,1405-1407,1431-1434`: `gorev_oku()` tüm görev listesini yükler; snapshot filtreleme veya sayfalama olmadan `gorevler` olarak döndürür. | Başlık/detay, atama, geçmiş olaylar ve notlar görev içeriği taşıyabilir. Bu bölüm için snapshot byte bütçesi yoktur. |
| Sohbet | `server.py:777-849,1433`: en çok 200 son kayıt; son-tail okuması en çok 2 MiB, tek JSONL kaydı 64 KiB, taramada en çok 600 satır. Mesaj gövdesi, hedef, kimden iddiası, zaman ve provenance döner. | İçerik yanlışlıkla sır, kişisel veri veya kullanıcı/model talimatı içerebilir. Provenance güven seviyesi, mesaj metnini gizlilik bakımından temizlemez. |
| Ekran kayıtları | `server.py:862-982,1434`: ada göre ilk 128 dosya, model başına en çok 60 satır; toplam ham tarama 8 MiB, JSON parse girdisi 2 MiB ve `ekranlar` map çıktısı 2 MiB. Kısmi durum `ekranlar_meta` ile bildirilir. | Terminal/araç çıktısı sır veya yerel yol içerebilir. Bütçeler aktarımı sınırlar; redaksiyon veya geçmişi silme sağlamaz. |
| Panel HTML | `server.py:1446-1450,1620-1621`: statik `ui.html` (okunamazsa sabit yedek sayfa); HTML, JSON snapshot'ı kendisi gömmez, aynı origin'den alır. | HTML GET'i de kimlik doğrulamasızdır. Tek başına snapshot içeriğini taşımasa da arayüz/route yapısını açar; asıl veri `/api/veri` ve `/veri` yolundadır. |

Ekran bölümü için açık bütçeler vardır; bu, tüm `/api/veri` yanıtının sınırlı olduğu anlamına gelmez. Özellikle görev listesi ve kullanıcı notları için alan/byte/pagination sınırı bu akışta görünmüyor. Snapshot'taki anahtarların tümü her istemciye gider; görev/mesaj hedefi veya UI rolüne göre sunucu tarafı filtre yoktur.

## Seçeneklerin etkisi

| Seçenek | Faydası | Sınırı / uyumluluk etkisi |
|---|---|---|
| **Tek güvenilen UID, loopback** | Mevcut CLI ve tarayıcı akışı çalışmaya devam eder; en az değişiklik. | Yalnız yerel ağ bind'ini sınırlar. Aynı network namespace'te localhost'a erişen başka UID süreçlerini durdurmaz. Aynı UID'deki süreçler dosyalara da erişebilir. Bu model ancak o süreçlerin tamamı aynı güven alanında kabul edilirse uygundur. |
| **Snapshot alanlarını azaltma** | Hassas içerik yanıt gövdesine hiç konmayabilir. Mesaj/ekran içeriğini, serbest notları ve kullanılmayan zaman/metaverileri özet görünümden çıkarmak en düşük veri aktarımı sağlar. | Kimlik doğrulama değildir; endpoint'e erişen kişi kalan alanları yine okuyabilir. Mevcut panel ekip, sohbet, görev ve ekran görünümlerinin tümünü tek snapshot'tan üretir. Sessizce alan kaldırmak UI/istemci uyumluluğunu bozar. |
| **Özet ve içerik uçlarını ayırma** | Ekip/presence özeti düşük hassasiyetli kalabilir; mesaj, görev ayrıntısı ve ekran akışına ayrı izin ve sayfalama uygulanabilir. | Eski tam snapshot alias'ları açık kalırsa ayrım etkisiz olur. UI ve CLI tüketicileri taşınmalı; cursor/retention ve tutarlı snapshot sözleşmesi tanımlanmalıdır. |
| **Ayrı HMAC read scope** | Anahtar taşıyabilen CLI/broker istemcileri için GET erişimi POST yazma yetkisinden ayrılır; route bazında asgari izin verilebilir. #471 ayrı GET sözleşmesi tasarımıdır, çalışan bir kapı değildir. | `YUVA_AUTH_ENABLED` mevcut haliyle GET'i kapatmaz. HMAC sırrı tarayıcı JavaScript'ine gömülemez; sırrı bilen istemciler arasında veri erişimini de aynı scope/paylaşım sınırlarıyla sınırlamak gerekir. `Host`/`Origin` bunun yerini tutmaz. |
| **Oturum doğrulamalı tarayıcı vekili** | Kullanıcı tarayıcısına backend sırrı vermeden cookie/session üzerinden UI erişimi sağlayabilir. | Session, logout/iptal, CSRF/Origin ve cache kuralları gerekir. Ham backend GET yolları doğrudan erişilebilir kalırsa vekil tek başına sınır oluşturmaz; tüm alias ve HTML/API yolları korunmalıdır. |
| **Ayrı servis UID'si + UDS peer kimliği** | Farklı OS UID'leri arasında yerel peer kimliğine dayalı erişim politikası kurabilir. | Tarayıcı UDS'ye doğrudan bağlanamaz; yine dar kapsamlı bir HTTP vekili gerekir. Veri kökü sahipliği, servis yetkileri ve mevcut dosya izinleri yeniden tasarlanmalıdır. Aynı UID süreçlerini birbirinden ayırmaz. |
| **Yazma öncesi redaksiyon/retention** | JSONL'ye yazılan sır ve PII riskini kaynağında azaltır; API'den önce ve CLI geçmişinde de etkili olabilir. | Geçmişi geri dönülmez değiştirebilir; kayıpsız kanıt, yedek ve ayrı ham artifact politikası gerekir. Mevcut saklı veriyi geriye dönük temizlemez. API yanıtını daraltmanın yerine değil, yanında kullanılan ayrı kontroldür. |

## Önerilen karar yolu

1. Tek kullanıcı hesabı altındaki tüm yerel süreçler güvenilir kabul ediliyorsa #455'teki yerel-only modeli açıkça belgeleyin. Dosya izinlerinin HTTP erişimini de koruduğunu veya loopback'in UID yalıttığını söylemeyin.
2. Daha az veri taşımak isteniyorsa mevcut `/api/veri` biçimini sessizce daraltmak yerine yeni, sürümlü bir özet görünümü tanımlayın. Varsayılan özette serbest metin (`metin`, görev `detay`/geçmiş notları, `not_`, ekran `satir`) olmasın; kullanılmayan kişisel zaman ve ilişki alanları da dahil edilmesin. Her alan için UI amacı ve okuyucu kaydedilsin.
3. Tam içerik gerekiyorsa mesaj, görev ayrıntısı ve ekran kayıtlarını ayrı, sayfalı/boyut sınırlı çağrılara taşıyın. Her çağrının auth/scope politikası ayrı olsun. Eski `/api/veri` ve `/veri` tam snapshot'ı koruyacaksa aynı erişim kontrolüne bağlanmalı; açık bir bypass olarak bırakılmamalıdır.
4. Tarayıcı kullanıcıları farklı güven alanlarına ayrılacaksa HMAC anahtarını JS'e koymayın; oturum doğrulamalı vekil kullanın veya tarayıcı dağıtımını tek güvenilen UID yerel paneliyle sınırlayın. HMAC read scope'u CLI/broker gibi secret saklayabilen istemciler için ayrı bir seçenek olarak ele alın.
5. Herhangi bir seçenekten önce görev içeriklerinin, sohbet/ekran JSONL'sinin ve yedeklerin saklama/redaksiyon politikasını belirleyin. UI kartında gizleme, network yanıtı veya yerel dosyayı azaltmaz.

Bu seçenekler kaynak değerlendirmesidir; veri sınıflarına ilişkin ürün/operatör onayı, canlı ağ/proxy ayarı veya bir özelliğin etkin olduğu iddiası değildir. #455'in açık erişim/dağıtım sınırları ve #453'ün redaksiyon envanteriyle birlikte okunmalıdır.

## Dayanak

- `panel/server.py`: `do_GET()`, `veri()`, `gorev_oku()`, `mesajlar()`, `tum_ekranlar()`, loopback ve POST auth yolları.
- `panel/ui.html`: `cek()` ve `fetch("/api/veri")`.
- `README.md`: güvenlik sınırı ve aynı UID/localhost açıklaması.
- `docs/local-api-get-snapshot-decision-455.md`: GET erişim seçeneği ve geçiş kapıları.
- `docs/panel-privacy-redaction-inventory-453.md`: ham sohbet/ekran içeriği, redaksiyon ve saklama sınırları.
