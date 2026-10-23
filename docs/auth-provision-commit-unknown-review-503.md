# Yuva #503 — Provisioning commit-belirsizliği düzeltmesine bağımsız inceleme

## Kapsam ve sonuç

`panel/auth_provision_draft.py` içindeki #502 düzeltmesi ve `docs/auth-provision-commit-unknown-502.md` notu statik olarak incelendi. Kod, test, runtime veya provisioning işlemi çalıştırılmadı.

#478'deki asenkron kesinti penceresi yerel dosya sistemi varsayımı altında kapatılmış: `os.link()` öncesi `link_attempting` işaretleniyor, başarı sonrası `installed` oluyor; bu aralıktaki `BaseException` `commit_unknown` dönüyor. Başarılı kurulum sonrasındaki unlink/fsync ve yakalanan cleanup kesintileri de bilinmeyen commit olarak korunuyor. Ancak dosya sistemi türü sınırlandırılmadığından genel `OSError` dalında kalan bir commit-belirsizliği var.

## Bulgu

### Orta — Uzak dosya sisteminde başarısız `link()` dönüşü kurulumun olmadığını kanıtlamıyor

`write_initial_state()` kök dizini `_secure_root_fd()` ile sahiplik, mod ve yol bileşenleri bakımından doğruluyor (`panel/auth_provision_draft.py:161-165`; `panel/auth_store_v2.py:265-305`). Bu kontroller dosya sistemi türünü doğrulamıyor. `os.link()` herhangi bir `OSError` döndürdüğünde kod fazı `not_started` yapıp `commit_not_started` üretiyor (`panel/auth_provision_draft.py:218-222`). Aynı kod yolu NFS üzerinde de çalışabilir.

Linux `link(2)` belgesi, NFS sunucusu linki oluşturduktan sonra yanıtı istemciye iletemeden kapanırsa `link()` dönüş kodunun yanlış olabileceğini ve linkin `stat()` ile kontrol edilmesi gerektiğini açıkça belirtiyor ([Linux man-pages: `link(2)`, BUGS](https://www.man7.org/linux/man-pages/man2/link.2.html#BUGS)). Bu senaryoda işlev `commit_not_started` diyerek hedef snapshot'ın kurulmuş olma ihtimalini gizler. Operatör bunu kesin başarısızlık sayıp prosedürü tekrar uygulamaya kalkabilir; hedef no-replace nedeniyle üzerine yazılmasa da gerçek sonuç raporlanmamış olur.

**Öneri:** Desteklenen auth kökünü yerel dosya sistemiyle açıkça sınırlandırıp bu koşulu uygulamada/kurulum sözleşmesinde doğrulayın veya `FileExistsError` dışındaki link hatalarını `commit_unknown` sayın. İkinci seçenek daha tutucudur; çevrimdışı inceleme gerektiren bazı kesin hata yollarını da belirsiz olarak raporlar. `commit_unknown` sonrasında otomatik readback/rollback/retry eklemeyin.

## Doğrulanan düzeltme noktaları

- `link_attempting` çağrıdan önce atanıyor; dönüş ile `installed` ataması arasındaki asenkron kesinti `commit_unknown` yoluna gidiyor.
- `FileExistsError`, no-replace hedef çakışması olarak ayrı ele alınıyor.
- Link kurulduktan sonraki geçici ad temizleme veya dizin fsync kesintisi `installed` fazında `commit_unknown` oluyor.
- Cleanup içindeki yakalanmış `BaseException`, commit fazı kurulmuş/belirsizse sonucu `commit_unknown` olarak koruyor.
- Modül hâlâ auth gate tarafından import edilmeyen, CLI'si olmayan ve canlı auth etkinleştirmeyen provisioning taslağı; rapor canlı ortam güvenliğini iddia etmiyor.
