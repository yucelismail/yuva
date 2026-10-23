# Release installer'da kalan `.staging-*` için güvenli kurtarma kararı (#631)

**Tarih:** 2026-10-23
**Karar:** Staging artifact'ları otomatik kabul, publish, resume veya silme yapılmaz. Önce salt-okunur envanter ve işlem owner'ı uzlaştırması gerekir; belirsizlikte `HOLD`.
**Durum:** Kaynak/test incelemesi; gerçek install root, process veya staging dizini incelenmedi/değiştirilmedi, test çalıştırılmadı.

## Installer staging sözleşmesi

`release_installer.install_release()` doğrulanmış payload'ı `releases/.staging-<uuid>` altına `copytree()` ile kopyalar, staging ağacını tekrar source/manifest/pin'e karşı verify eder, release directory'lerini read-only moda dondurur ve `renameat2(RENAME_NOREPLACE)` ile final tam release ID adına atomik publish eder. Final dizin publish edilince `moved=True` olur. Normal Python exception'ında `moved=False` ise `shutil.rmtree(staging, ignore_errors=True)` denenir; ignore edilen cleanup hatası staging kalıntısını exception'la görünür kılmaz. Process kill/host crash cleanup bloğunu çalıştırmayabilir.

Final directory rename sonrası, `releases/` fsync, manifest receipt yazımı, `manifests/` fsync ve `previous`/`current` pointer adımları ayrı gelir. Bu nedenle `.staging-*` ile **final adı altında manifesti/receipt'i eksik kalmış release** farklı recovery sınıflarıdır. Pointer'lar yalnız `releases/<full-release-id>` canonical hedefini kabul eder; `.staging-*` normal current/previous target'ı olarak kabul edilmez.

## Salt-okunur sınıflandırma

İşlem için exact `INSTALL_ROOT`, expected source commit/release ID, pin kaynağı, çağrı zamanı, error/exit ve pointer state'i kaydedin. Bir installer hâlâ çalışıyor olabileceği veya açık file descriptor/cwd/mount kalabileceği durumda cleanup yoktur. Sırf `.installer.lock` dosyasının varlığı veya eski mtime, aktif transaction'ın var/yok kanıtı değildir. Yetkili host process/lock incelemesi mümkün değilse **HOLD**.

| Gözlenen artifact | Anlamı / sınırı | Karar |
|---|---|---|
| `releases/.staging-*` kısmi dosyalar veya kısmi directory içeriyor | Copy/verify/freeze/rename aşamalarından hangisinde kesildiği yalnız tree şekliyle kanıtlanmaz. Dış pin/source yoksa içeriği trusted release sayılmaz. | `STAGING_INCOMPLETE/HOLD`; verify edip current'a işaretleme, devam ettirme veya otomatik silme yok. |
| `.staging-*` tam payload gibi görünüyor ve verify geçiyor | Başarıyla staging doğrulanmış olması transaction'ın final rename ve directory fsync aşamalarını tamamladığını kanıtlamaz. | `STAGING_UNPUBLISHED/HOLD`; yeni install ID oluşturma veya staging'i final adına rename etme yok. Yeni resmi install akışı ayrı karar ve ID collision/readback sonrası kullanılabilir. |
| `.staging-*` ağacında directory mode `0555` | Directory freeze adımına ulaşmış olabilir; rename yapılmadığını/durability'yi kanıtlamaz. Permission değiştirerek “temizleme kolaylığı” sağlamayın. | Diğer staging durumlarıyla aynı `HOLD`; mode yalnız metadata kanıtıdır. |
| `releases/<id>` var, manifest receipt yok veya eksik | Final rename olmuş olabilir, sonra releases fsync/receipt aşamasında hata/crash yaşanmış olabilir. Pointers bu release'i kullanmıyor olabilir. Var olan ID yüzünden yeni install aynı ID'yi overwrite etmez. | `PUBLISHED_RECEIPT_INCOMPLETE/HOLD`; dosya attach/rename etme veya ID'yi tekrar install etme yok. External manifest/pin/source ile read-only verify ve ayrı owner kararı gerekir. |
| Final release ve receipt var, current/previous başka ID gösteriyor | Artifact başarılı yayımlanmış fakat pointer geçişi başlamamış/yarım kalmış veya candidate bilinçli olarak inactive bırakılmış olabilir. | `PUBLISHED_INACTIVE`; release'in amacı ve pointer operation sonucu doğrulanana kadar HOLD; silme veya current'a geçirme yok. |
| `current` veya `previous` final ID'ye gidiyor | Bu release aktif/rollback zincirine bağlıdır. `.staging-*` temizliğiyle ayrı görünse bile bağlı final directory/receipt korunmalıdır. | Pointer target'ı ve external pin/source ile verify; hiçbir bağlı dosyayı cleanup kapsamına alma. |
| Unknown files, symlink, dışarı çıkan yol, yanlış owner/mode, manifest/pin mismatch, iki installer/process olasılığı | Kapsam veya güven zinciri belirsizdir. | `HOLD/NO-GO`; hiçbir değişiklik yapma, data owner/release owner'a eskale et. |

## Read-only rapor akışı

1. Yeni install/rollback başlatmayın; pointer değiştirme, cleanup veya servis start/stop yapmayın. Incident/run ID ve operatör onayı referansını içeriksiz kaydedin.
2. Exact `INSTALL_ROOT` path'ini `lstat` ile doğrulayın; path component symlink'lerini takip etmeyin. Root/`releases`/`manifests` metadata'sını (type, owner, mode, size, timestamp) kaydedin.
3. `current` ve `previous` link metinlerini önce `readlink` ile okuyun; ID'leri exact kanonik biçimde doğrulayın. `releases/` altında yalnız bounded depth/name inventory yapın: `.staging-*`, full release ID'leri, ilgili manifest receipt varlığı ve geçici `.current.*.tmp`/`.previous.*.tmp` link'leri. İçerik dump'ı yapmayın.
4. Hangi install invocation'ın hangi ID/payload/manifest/pin'i hedeflediğini caller/release kaydından eşleştirin. Hash/pin'i install root receipt'inden türetmeyin; independent trust source ve temiz exact source checkout gereklidir.
5. Her aday için offline `release_manifest.py verify` ancak external manifest, external pin ve exact source ile çalıştırılabilir. Bu, tam staging/final payload byte'larının source/manifest'e uyduğunu denetler; staging'in installer transaction'ının hangi adımında kaldığını veya pointer durability'yi tek başına kanıtlamaz.
6. Sonucu `STAGING_INCOMPLETE`, `STAGING_UNPUBLISHED`, `PUBLISHED_RECEIPT_INCOMPLETE`, `PUBLISHED_INACTIVE`, `POINTER_REFERENCED` veya `HOLD_UNKNOWN` olarak raporla. Gerçek işlem aşaması kanıtlanamıyorsa kategoriye “possible” ekle ve `HOLD` tut.

Önerilen metadata rapor alanları: exact root, timestamp, incident ID, install invocation/release ID, pointer raw targets, path lstat/type/owner/mode/size, staging/final/receipt inventory, external manifest hash/pin custody reference, offline verification outcome, active process/lock inspection sonucu veya `unknown`, sınıflandırma/`HOLD`, karar sahibi ve sonraki onay. Manifest/payload/Yuva user data içeriği veya secret rapora eklenmez.

## Temizlik veya tekrar install için owner gate

Cleanup/restore/retry bu salt-read-only raporun otomatik sonucu değildir. Ayrı yazılı release-owner kararıyla yalnız exact artifact path için değerlendirin. Tüm koşullar karşılanmadan staging'e dokunmayın:

- Aktif install/rollback process'i, açık file descriptor/cwd referansı ve eşzamanlı operatör işi olmadığı host tarafında doğrulanmıştır.
- Exact path root'un `releases` doğrudan child'ıdır; gerçek directory'dir, symlink veya hardlink/special-file içermiyordur; manifest/payload dışına kaçan path yoktur.
- `current`/`previous` ve bağımsız release/cutover kaydı artifact'ın kullanılmadığını gösterir; pointer repair veya commit-unknown işiyle ilişkisi açıklanmıştır.
- Release owner silme/retention kararını ve audit referansını verir. İçeriği koruma ihtiyacı varsa artifact `HOLD` altında kalır; mtime yaşı tek başına silme sebebi değildir.
- Silme/yeniden deneme sonrası exact path inventory, pointer pair, final ID collision ve manifest/source/pin tekrar doğrulaması için ayrı işlem planı vardır. Belirsiz sonucu kör retry yok.

Gelecekte bir recovery aracı eklenecekse varsayılanı yalnız inventory/report olmalıdır. Silme ayrı bir explicit subcommand, exact UUID/ID path confirmation, private root validation, no-follow lstat walk, no active installer, owner approval ve before/after makbuzu gerektirir. Resume veya staging'i final release'e promotion, manifest receipt/pointer commit adımlarını transaction kaydı olmadan tekrar kurmak olacağından ayrıca tasarlanıp fixture'da sınanmadan desteklenmemelidir.

## Fixture kanıtı ve açık boşluk

`tests/test_release_installer.py::test_copy_and_staged_manifest_faults_preserve_current_and_data_hash` sentetik temp install root'ta copy interruption ve staged manifest verify hatası enjekte eder; normal exception handler staging'i temizlemeyi başarır, current/data değişmez. `test_release_directory_fsync_fault_keeps_old_pointer_and_data` final directory kalabildiğini, current'ın değişmediğini gösterir. Bu fixture'lar gerçek crash/kill, `shutil.rmtree` cleanup başarısızlığı, 0555 staging cleanup, receipt yazımı kesintisi, `manifests/` fsync failure, reboot recovery veya gerçek host permission davranışını kanıtlamaz. Testler bu görevde çalıştırılmadı.

`CommitUnknown` için pointer uzlaştırma sırası [#630 raporunda](release-installer-commit-unknown-reconciliation-630.md); install/rollback normal sözleşmesi [#543'te](release-installer-543.md); cleanup/hold ilkeleri [#530 restore-check retention kararında](restore-check-retention-policy-530.md) bulunur.

Bu karar gerçek staging/release artifact'ını bulmaz, silmez, chmod/chown yapmaz, manifest receipt yazmaz, pointer repair/rollback yapmaz ve user data root'a dokunmaz. Unknown artifact, owner kararı gelene kadar HOLD kalmalıdır.
