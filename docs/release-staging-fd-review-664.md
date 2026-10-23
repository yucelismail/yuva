# #664 — Release staging inventory fd yaşam döngüsü bağımsız review

**Tarih:** 2026-10-23
**Önkoşul:** #647 artık `verified`; #664 review devam etti.
**Karar:** **NO-GO — child-directory `fstat` hatasında fd sızıntısı doğrulandı.**
**Kapsam:** `release_staging_inventory.py` kaynak akışı ve yalnız
`TemporaryDirectory` install-root fixture'ı. Gerçek host `INSTALL_ROOT`,
staging, pointer veya servis taranmadı/değiştirilmedi.

## Kaynak sahipliği incelemesi

| Fonksiyon/yol | FD akışı ve cleanup | Review sonucu |
|---|---|---|
| `_open_explicit_root()` component traversal | Anchor fd açılır; her component `O_DIRECTORY|O_NOFOLLOW` ve parent `dir_fd` ile açılır. Normal ilerlemede önceki fd kapanır; fonksiyonun hata çıkışında mevcut `fd` `except BaseException` içinde kapanır. Symlink component fixture'ı reddediyor. | Normal ve olağan open-failure akışı makul; aşağıdaki `close(old_fd)` hata penceresinde yeni açılmış `next_fd` henüz sahip olunan `fd`'ye atanmadığı için kaçabilir. Bu özel close-error kolu enjekte edilerek sınanmadı. |
| `_entries()` | Dizin fd'si `os.dup()` ile çoğaltılır; `os.scandir(scan_fd)` iterator'ı context manager ile kapanır; sağlanan duplicate fd `finally` içinde kapatılır. `dup`, scandir veya entry metadata hatası exception ürettiğinde de finally çalışır. | Statik kontrol olumlu. Mevcut tekrarlı fixture normal çağrılarda fd sayısının sabit kaldığını gösterir; scandir/entry-stat hata enjeksiyonu fixture'ı yok. |
| `_open_child_directory()` | Child önce `O_DIRECTORY|O_NOFOLLOW` ile açılır. Open hatası state'e çevrilir; inode/dev farklıysa fd kapatılıp `changed_during_scan` döner. | **Bulgu F1:** `os.open()` başarılı olduktan sonra `os.fstat(fd)` exception verirse bu descriptor için cleanup `try/finally` yok; fd sızıyor. |
| `_inventory_open_root()` | `releases_fd` ve `manifests_fd` açıldıktan sonra `_inventory_collect()` çağrısı `finally` ile child fd'leri kapatır. | Normal dönüş ve `_inventory_collect` hatası kapanır. Ancak iki child open helper çağrısı `try` başlamadan önce; ikinci çağrı beklenmeyen exception fırlatırsa ilk child fd'nin cleanup kapsamı henüz başlamamıştır. F1 bu riski görünür kılar. |
| `_pointer()`, `_manifest_metadata()` | `stat(..., follow_symlinks=False)` ve `readlink(dir_fd=...)` kullanır; manifest içeriği açılmaz/okunmaz, yeni fd alınmaz. | Ek child/file fd sahibi yok. Canonical olmayan pointer target rapora yazılmaz. |
| `inventory_install_root()` | Root fd elde edildikten sonra tüm `_inventory_open_root()` dönüş/hata yolları dış `finally` ile kapatılır. | Normal ve yukarı taşan exception yolunda root fd cleanup var; fakat leaked child fd dış root cleanup'tan etkilenmez. |

## Kabul / ret matrisi

| Kabul ölçütü | Kanıt | Sonuç |
|---|---|---|
| 40 ardışık çağrıda fd sayısı sabit | `tests/test_release_staging_inventory.py::test_repeated_inventory_keeps_process_descriptor_count_stable` — geçici root, 40 çağrı; görev kapsamında çalıştırıldı ve geçti. | PASS — yalnız normal çağrı yolu. |
| Root/release/pointer symlink no-follow | `test_symlink_component_in_explicit_root_is_rejected_without_following`, `test_symlinked_releases_directory_is_not_followed_for_pointer_lookup`, `test_never_echoes_unsafe_pointer_or_symlink_target`; görev kapsamında 7'li test dosyasının parçası olarak geçti. | PASS — test edilen symlink dalları. Manifest symlink için ayrı fixture yok; kaynak `lstat`/`follow_symlinks=False` yapıyor. |
| Hassas path/name/payload/pointer target output'a sızmıyor | Aynı fixture testleri rapor ve hata çıktısını kontrol ediyor; 7'li test dosyası geçti. | PASS — test edilen output sınıfları. |
| `dup`/`scandir` normal cleanup ve tekrar kullanılabilirlik | Kaynakta context-manager + `finally`; 40 çağrı fd sayısı sabit. | PASS — olağan akış; scandir/metadata hata enjeksiyonu kanıtı yok. |
| Child open sonrası erken `fstat` hatasında cleanup | Geçici install root'ta `os.fstat` ikinci çağrısında sentetik `OSError` enjekte edildi; `/proc/self/fd` sayısı 4'ten 5'e çıktı. | **FAIL — bir child descriptor açık kaldı.** |
| Gerçek host/install root etkisiz | Host yolu argüman edilmedi; fixture root `TemporaryDirectory` altındaydı. | PASS — bu review koşusunun sınırı. |

Komut sonucu: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
tests.test_release_staging_inventory -v` — **7 test geçti**. Ek sentetik
`fstat` hata deneyi `leaked_descriptors: 1` gösterdi. Deney subprocess'i
sonlandığında OS fd'yi kapattı; fixture geçici root dışına çıkmadı.

## Bulgu ve önerilen düzeltme

**F1 — child fd `fstat` exception'da sızıyor (yüksek, cleanup correctness).**
`_open_child_directory()` içinde `fd = os.open(...)` sonrasında `opened =
os.fstat(fd)` korumalı değil. `fstat` exception'ı `_inventory_open_root()`'a
taşar; parent root fd kapanır ama açılmış child fd kapanmaz. Tek çağrıda bir fd
kalır; yinelenen hata çağrıları descriptor limitine kadar biriktirebilir.

Öneri: child fd açıldıktan hemen sonra tek sahipli `try/except/finally` cleanup
kur; başarılı return'de ownership açıkça caller'a geçirilsin, tüm reject/error
çıkışlarında fd kapansın. `_inventory_open_root()` iki child open işlemini de
`try/finally` kapsamına alıp `releases_fd`/`manifests_fd` değerlerini baştan
`None` başlatmalı. Hata enjeksiyonlu regresyon fixture'ı şu şartı assert
etmeli: `fstat` fail olsa da işlem öncesi/sonrası `/proc/self/fd` sayısı aynı,
rapor `HOLD`/güvenli fixed error ve path-free kalır.

## Sonuç

Normal tekrar, test edilen symlink no-follow ve output privacy dalları geçiyor;
ancak F1 hata/early-return cleanup kabulini düşürüyor. Bu nedenle bağımsız
review **NO-GO**. #647'nin inventory kararı her durumda `HOLD`; bu bulgu
cleanup, staging repair veya pointer değişikliği izni vermez. Kaynak kod bu
review kapsamında değiştirilmedi.
