# Yuva #446 — JSONL append güvenlik incelemesi

## Kapsam ve sonuç

Salt-okunur inceleme: `bin/yuva` ve `panel/server.py` içindeki ortak JSONL append, güvenli dirfd traversal, dosya doğrulama, descriptor kapanışı, umask ve kilit kullanımı. Kod/test/runtime/panel değişikliği veya çalıştırması yapılmadı.

JSONL hedefi için dirfd tabanlı traversal, `O_NOFOLLOW | O_APPEND`, `0600` oluşturma, exact owner/mode/nlink/type doğrulaması ve kısa fd yaşam döngüsü yerinde. CLI ve panel aynı `KOK/.kilit` yolunu kullanıyor. Tek gerçek bulgu, lock dosyasının kendisinin bu JSONL hedefi kadar güvenli açılıp doğrulanmaması; bu nedenle lock pathname/inode değişikliğinde iki writer farklı inode'ları kilitleyebilir. Etki, güvenli `0700` KOK içindeki aynı UID veya root işlemlerle sınırlıdır; farklı UID'nin normal koşullarda lock'ı değiştirmesi beklenmez.

## Bulgu

### Düşük — `.kilit` inode'u doğrulanmıyor ve değiştirilmeye karşı sabitlenmiyor

CLI `kilit_tut()` `.kilit` dosyasını standart `open(KILIT, "a+")` ile açıyor, sonra açılan file object üzerinde `flock` alıyor (`bin/yuva:72-99`). Panel `dosya_kilidi.__enter__()` de aynı yolu standart `open(KILIT_DOSYA, "a+")` ile açıp fd üzerinde `flock` alıyor (`panel/server.py:85-128`). Bu açılışlar symlink'i takip eder; lock fd'si regular file, euid sahibi, `0600`, `nlink=1` mi veya kilit alındıktan sonra `.kilit` pathname'i hâlâ aynı inode'u mu gösteriyor denetlenmiyor.

Çalışan writer'lar arasında `.kilit` unlink edilip yeniden oluşturulursa eski süreçler eski inode'u, yeniler yeni inode'u kilitleyebilir. Aynı `O_APPEND` dosyasına yazsalar bile çoklu `os.write()` döngüleri ayrı syscall'lardır; writer'lar farklı lock inode'larında kalırsa kısa/yarım yazımlarda JSON kayıtlarının byte aralıkları araya girebilir (`bin/yuva:194-212`, `panel/server.py:250-268`). Symlink ile mevcut private KOK içindeki lock adı beklenmeyen hedefi kilitleyebilir. KOK `0700` olduğundan bu, normalde farklı UID'den uzaktan bir yerel saldırı yolu değildir; aynı UID zaten KOK verisini doğrudan okuyup yazabilir. Pratik risk, aynı UID bakım/temizlik/deployment adımının lock dosyasını canlı süreçler varken değiştirmesi ve koordinasyonun fark edilmeden kaybolmasıdır.

**Öneri:** Her iki writer'ın da ortak helper ile, zaten güvenli açılmış KOK dirfd'sine göre `O_NOFOLLOW | O_CLOEXEC` ile lock dosyasını açması; eksikse yalnız `0600` ve `O_EXCL` ile oluşturması; `fstat` ile regular/euid/mode/nlink doğrulaması; `flock` aldıktan sonra dirfd-relative `stat(..., follow_symlinks=False)` ile fd/path `(st_dev, st_ino)` eşitliğini doğrulaması. Lock inode'u canlı süreçler varken unlink/replace edilmemeli. Bu değişiklik mevcut append incelemesinin bulgusudur; bu görevde uygulanmadı.

## Kontroller

- **Hedef traversal/symlink:** `yol.relative_to(KOK)` sonrası yalnız `mesaj.jsonl` veya `ekran/<dosya>.jsonl` biçimi kabul edilir; dosya adı parent dirfd-relative `os.open()` ile açılır. KOK ve `ekran/` dirfd'leri `O_DIRECTORY | O_NOFOLLOW` ile bileşen bileşen açılır, root/alt dizin `0700` ve euid sahipliği kontrol edilir (`bin/yuva:170-203, 221-299`; `panel/server.py:225-259, 277-350`). Final dosyada da `O_NOFOLLOW` vardır.
- **Append semantiği:** Hedef `O_APPEND` ile açılır; yeni dosya `O_CREAT | O_EXCL`, `0600` ile oluşturulur. Tam payload yazılana kadar `InterruptedError` tekrar edilir ve kısa `write()` ilerlemesi tamamlanır; sıfır ilerleme hata verir (`bin/yuva:194-212`; `panel/server.py:250-268`). Hedefin regular file, euid sahibi, tam `0600` ve tek hardlink olduğu descriptor üzerinden doğrulanır (`bin/yuva:302-306`; `panel/server.py:335-340`).
- **Descriptor yaşam döngüsü:** KOK fd, parent dirfd ve dosya fd'si iç içe `try/finally` kapsamlarında kapatılır (`bin/yuva:186-218`; `panel/server.py:242-274`).
- **Umask:** Her iki doğrudan giriş noktası `umask(0o077)` ayarlar (`bin/yuva:2126`; `panel/server.py:1382`); JSONL yaratımı ayrıca açık `0600` mode ister. Mevcut yazıcılar, izin/owner/type doğrulaması geçmezse otomatik izin gevşetmesi yapmadan hata verir. Daha kısıtlayıcı harici umask yeni dosyayı 0600'den dar oluşturursa doğrulama reddeder; bu fail-closed kullanılabilirlik etkisidir, izin genişletme değildir.
- **Ortak kilit kapsamı:** Her iki append, JSON satırını hazırladıktan sonra `.kilit` alır ve dosya append'i tamamlanıp fd'ler kapandıktan sonra bırakır (`bin/yuva:185-218`; `panel/server.py:241-274`). Panelde süreç içi `RLock`/reentrant derinlik de vardır (`panel/server.py:70, 85-128`). Kilit kapsamı uygundur; yukarıdaki pathname/inode doğrulama açığı devam eder.

## Kaynak sınırı

Bu inceleme yalnız JSONL append ve koordinasyon kodunu kapsar. Yuva'nın daha geniş auth/API güven sınırını veya aynı UID'deki süreçlere karşı izolasyonu değerlendirmez. Bu nedenle bulgu farklı UID'lere yetki yükseltme olarak sunulmamıştır. Davranış testi ya da runtime kanıtı üretilmemiştir.
