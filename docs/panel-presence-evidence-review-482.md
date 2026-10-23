# Panel çevrimiçi göstergesinin kanıt kaynağı incelemesi (#482)

- **Kapsam:** CLI `kimler`/`durum`, `/api/veri` ve panel model/ekran kartları.
- **Yöntem:** Salt-okunur kaynak incelemesi. Test, runtime veya panel davranışı çalıştırılmadı.
- **İncelenen ağaç:** Aday kaynak ağacı; presence yolu ayrıca Yuva'nın yerel kurulu kaynak kopyasıyla karşılaştırıldı.

## Akış ve kanıt

### `yuva-v2` çalışma ağacı

- `bin/yuva:1608-1650,1659-1699`: `durum` ve `kimler`, kimlik listesini yerel `durum.json`'dan alıyor; çevrimiçi kararını `/api/veri` snapshot'ından veriyor. Yeşil için `online is True`, `presence_verified is True`, `presence_state == "online"` ve `son_kalp` değerinin `online_sn` içinde (varsayılan 30 saniye) olması birlikte gerekiyor. Panel verisi yoksa `kimler` açıkça durumu bilinmiyor yazıyor; yerel `bagli` alanını yeşile çevirmek için kullanmıyor. `durum` da bilinmiyor gösteriyor.
- `panel/server.py:987-1029,1400-1434`: `POST /api/katil` yalnızca `bagli` kayıt alanını güncelliyor; kod yorumu bunun heartbeat kanıtı olmadığını belirtiyor. `api_kalp` doğrulanmış broker principal olmadığı için 503 döndürüyor. Snapshot, `bagli` değerini yalnızca kayıt bilgisi olarak taşıyor; `son_gorulme` ve `son_kalp` alanlarını `null`, `online` değerini `false`, presence durumunu `unknown` ve `presence_verified` değerini `false` veriyor. `online_sn` API'de tamsayı olarak sunuluyor.
- `panel/ui.html:515-530,533-553`: Tarayıcı aynı doğrulanmış presence alanlarını ve taze heartbeat'i kontrol ediyor. Süre aşımı, gelecekte tarih, hatalı TTL, doğrulanmamış kayıt ve panel fetch hatası çevrimiçi sonucunu engelliyor. Çevrimdışı etiketi için de `presence_verified === true` ve açık `presence_state === "offline"` gerekiyor; diğer durumlar bilinmiyor.
- `panel/ui.html:745-771,1844-1930,1935-1953`: Ekip ve ekran kartları renk/etiketi `onlineMi` ve `onlineEtiketi` üzerinden alıyor. Panel hatasında eski snapshot bellekte kalsa da çevrimiçi işareti bastırılıyor ve bağlantı doğrulanamıyor etiketi gösteriliyor. Ekran JSONL satırları geçmiş çıktı olarak gösterilebilir; tek başına presence kanıtı sayılmıyor.

Bu ağaçta heartbeat kabul eden doğrulanmış bir kaynak bulunmadığından panel/API şu an hiçbir kullanıcıyı doğrulanmış çevrimiçi yapamaz. Bu, `G1/W1b` kaynağı eklenene dek kapalı tutulan fail-closed davranışla tutarlıdır; `bagli: true` veya yeni ekran satırı yeşil durum üretmez.

## Bulgu: yerel kullanılan kopya panel hatasında eski `bagli` değerini çevrimiçi sayabiliyor

Yuva'nın yerel kurulu kaynak kopyasındaki `bin/yuva:478-500,507-522` içindeki `durum` ve `kimler`, panel verisi alınamadığında yerel `bagli` değerine düşüyor. `kimler` bunu yeşil ışığa, `durum` ise “bağlı” etiketine dönüştürüyor; `son_gorulme` tazeliğini bu fallback'te kontrol etmiyor. Bu kayıt `yuva ayril` gelene kadar true kalabildiği için panel kapalıyken stale oturum çevrimiçi görünebilir.

Aynı yerel kurulu kopyanın `panel/server.py:187-190,227-236,405-427` yolu kalp isteğinde `son_gorulme`'yi tazeliyor ve snapshot `bagli && taze(son_gorulme)` ile `online` hesaplıyor. Ancak bu, aday kaynak ağacındaki doğrulanmış presence sözleşmesiyle aynı kanıt değildir: `bagli` kullanıcı kaydıdır, heartbeat isteğinde doğrulanmış principal yoktur ve API'de `presence_verified` ayrımı bulunmaz. Dolayısıyla aday ağaçtaki “panel yoksa bilinmiyor” düzeltmesi bu yerel kaynak kopyasında mevcut değil. Hangi `panel/server.py` sürümünün çalışan serviste yüklü olduğu runtime incelemesi yapılmadığından burada dağıtım hakkında hüküm verilmiyor.

## Sınırlama: doğrulanmış çevrimdışı durumun yaşı tanımlı değil

CLI ve UI, açıkça doğrulanmış `offline` durumunu heartbeat TTL'iyle sınamıyor; yalnızca `presence_verified` ve `presence_state` alanlarına bakıyor (`bin/yuva:1636-1644,1682-1695`; `panel/ui.html:525-530`). Snapshot bugün bu alanları her kullanıcı için `unknown/false` yaptığı için mevcut kaynakta yanlış çevrimdışı etiketi oluşmuyor. İleride `offline` kanıtı sunulursa snapshot'a kanıtın zamanı/kaynağı ve tazelik kuralı eklenmeli; yoksa eski bir doğrulanmış offline kaydı süresiz güncel durum gibi gösterilebilir.

## Sonuç

Aday çalışma ağacında panel erişim hatası ve stale online heartbeat, çevrimiçi/çevrimdışı yerine bilinmiyor sonucuna gider; ekran çıktısı presence yerine geçmez. Yuva'nın yerel kurulu CLI kopyası panel hatasında bu kurala uymuyor ve `bagli` alanından çevrimiçi sonucu çıkarabiliyor. Çalışan servis ve CLI kopyalarının hangileri olduğu ayrıca runtime/deployment denetimi gerektirir; bu görev kapsamında yapılmadı.
