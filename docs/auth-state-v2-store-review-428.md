# Yuva #428 — Auth-state v2 store fail-closed incelemesi

Kapsam: `panel/auth_store_v2.py` statik incelendi; mevcut auth çekirdeği ve taslak sözleşme yalnız store sınırlarını anlamak için okundu. Kod değiştirilmedi, test veya runtime çalıştırılmadı. İnceleme feature-off store modülüyle sınırlıdır.

## Bulgular

### Düşük — Yanlış türde store dosyası açılışta süresiz bloklanabilir

`panel/auth_store_v2.py:308-320` dosyayı `fstat` ile regular file olduğunu doğrulamadan önce `os.open` ediyor. `STORE_NAME` altında yanlışlıkla FIFO provision edilmişse, `_read_snapshot()` tarafından kullanılan salt-okunur açılışta FIFO yazıcısı gelene kadar bloklanabilir; `unsafe_store_file` hatasına ulaşılamaz. Store kökü euid'e ait `0700` olduğundan bu, başka bir yerel kullanıcıdan doğrudan saldırı yolu değildir; yanlış operator provisioning veya aynı UID süreci koşulunda kullanılabilirlik sorunudur. Açılışı non-blocking yapmak ve sonrasında file type doğrulamak bu durumu fail-closed, hızlı hataya çevirir.

### Düşük — `os.replace` sonrası asenkron kesinti `CommitUnknown` olarak dönmeyebilir

`panel/auth_store_v2.py:422-430` `replaced = True` atamasını başarılı `os.replace()` çağrısından sonra yapıyor ve yalnız `OSError` durumlarını sınıflandırıyor. `os.replace` kernel'de tamamlandıktan sonra bu atamadan önce `KeyboardInterrupt` gibi bir `BaseException` gelirse işlem diskte commit edilmiş olabilir, fakat çağıran `CommitUnknown` yerine kesinti alır. Çağıran bunu başarısız/pre-commit sanıp aynı mutasyonu yeniden deneyebilir. Belirsiz kesinti penceresinde konservatif olarak commit sonucu bilinmiyor durumunu koruyacak düzenleme düşünülebilir; sıradan süreç çökmesinde sonuç zaten çağırana bildirilemez.

## Doğrulanan fail-closed özellikler

- Snapshot şeması tam alan eşleşmesi, yinelenen JSON anahtarı reddi, tip/sınır doğrulaması ve key/enrollment bağlantı kontrolleri içeriyor (`134-253`, `361-388`).
- Root dizini ve her path bileşeni descriptor-relative, `O_NOFOLLOW` açılıyor; kök izinleri/owner kontrol ediliyor (`265-306`). Store/lock dosyaları regular, euid'e ait, başka kullanıcıya kapalı ve tek hardlink olarak doğrulanıyor (`308-325`).
- Tek sabit lock inode'u alınmadan okuma veya yazma yapılmıyor; lock inode'un path ile eşleşmesi kontrol ediliyor (`328-358`).
- Commit öncesi hata yazımı `commit_not_started` olarak reddediyor. Temp dosyası aynı dizinde oluşturuluyor, fsync ediliyor ve atomik replace ediliyor; replace sonrası dizin fsync hatası `CommitUnknown` oluyor (`391-443`).
- Nesil sayacı store içi tutarsızlığı yakalıyor, dışarıdan backup rollback koruması sağlamadığı modül dokümantasyonunda açıkça belirtilmiş (`1-17`, `453-455`). `generation_floor` yalnız üst katmanın sağladığı tabanı denetliyor; dış anchor oluşturma/güncelleme garantisi vermiyor.
- Modül `panel/auth.py` veya `panel/server.py` tarafından import edilmiyor; bu teslimle canlı auth etkinleşmiyor.

## İncelenen konumlar

- `panel/auth_store_v2.py:134-253` — snapshot doğrulama
- `panel/auth_store_v2.py:265-388` — root, lock ve snapshot açma/okuma
- `panel/auth_store_v2.py:391-443` — atomik yazım ve commit belirsizliği
- `panel/auth_store_v2.py:446-565` — store API ve transaction
