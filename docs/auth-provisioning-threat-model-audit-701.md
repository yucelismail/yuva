# #701 — Auth provisioning CLI bağımsız threat-model denetimi

**Tarih:** 2026-10-23
**Önkoşul:** #700 `verified` olarak kontrol edildi.
**Karar:** Temporary-only CLI kabul yüzeyi incelendi; gerçek credential provisioning ve `YUVA_AUTH_ENABLED=1` için **NO-GO** sürüyor.

## Kapsam ve sonuç

`bin/yuva auth provision`, `panel/auth_provision_draft.py`,
`panel/auth_store_v2.py` ve #700 temporary-root fixture’ı kaynak üzerinden
incelendi. Yeni negatif kontroller yalnız `TemporaryDirectory` kullandı. Gerçek
key, enrollment, auth store, kullanıcı hesabı, servis veya host kullanılmadı.

İncelenen CLI key/secret kabul etmiyor; yalnız store yolu ve instance, audience,
operation ID gibi ID değerlerini alıyor. Girdi secret’ları ortamdan okumuyor ve
key üretmiyor. ID değerleri `argv` içinde süreç listesinde görülebilir, ayrıca
receipt’te saklanıp başarılı CLI çağrısında stdout’a yazılır. ID sözdizimi
secret içermediğini kanıtlayamaz; bu alanlara token/key koyulmamalıdır. CLI,
verilen ID’lerin semantik olarak sır olmadığını denetlemez.

## Kontrol matrisi

| Saldırı yüzeyi | Kaynak/fixture kanıtı | Sonuç ve sınır |
|---|---|---|
| Argv, environment, stdout/stderr | `cmd_auth_provision` yalnız `--store-root`, `--instance-id`, `--audience`, `--operation-id` alır; secret argümanı yoktur. Provisioner env’i okumaz. Geçici CLI fixture’ında secret sentinel environment değişkeni stdout/stderr’e çıkmadı. Hata kodları sabit allowlist biçimindedir. | Secret-bearing input yüzeyi yok; ancak argv ve receipt’teki ID/path değerleri görünür. Çağıranlar secret-free ID vermelidir. Süreç listesi başka UID’lere karşı gizlilik garantisi değildir. |
| Geçici kök, symlink ve traversal | CLI mutlak/`..` içermeyen yolu, lexical ve resolved path eşitliğini, seçili temp root altında olmayı ve temp root’un kendisi olmamasını denetler. Store açılışı path bileşenlerini `O_NOFOLLOW` ile gezer; root euid sahibi ve tam `0700` olmalıdır. Symlink root, seçili temp root dışı ve mevcut pre-store negatif fixture’ları yazım olmadan reddedildi. | CLI girişi için path sınırı fixture kapsamıyla tutarlı. `TMPDIR` seçili geçici-root sınırıdır; bu test workflow’u production root veya key provisioning aracı sayılmaz. |
| Owner ve mode | `auth_store_v2._secure_root_fd()` root owner/mode kontrolü yapar; dosya kontrolleri euid, regular-file türü, `0600`, tek link şartı arar. `0755` root CLI fixture’ında reddedildi. Euid farkı fixture’ı, yanlış sahipliği gerçek `chown` yerine `geteuid` enjeksiyonuyla sınadı. | Owner/mode gate kaynakta fail-closed. Yanlış owner testi gerçek farklı UID/host kanıtı değildir. |
| Replay ve operation conflict | Receipt `operation_id`, kind, instance, audience, initial wall time ve store digest’e bağlıdır. #700 fixture’ı eşleşen committed replay’de state/receipt byte’larının aynı kaldığını; aynı operation ID farklı audience ile kullanıldığında ret ve no-write olduğunu gösterdi. | Exact receipt + empty-store digest eşleşmesi dışında replay başarı sayılmaz. Receipt veya store bozuk/unknown ise otomatik retry yapılmamalı. |
| Kısmi snapshot write | Yeni disposable fixture, prepared receipt’ten sonra snapshot temp dosyasına kısmi yazım enjekte etti. Çağrı `snapshot_write_failed` döndü; store hedefi kurulmadı, temp snapshot temizlendi ve receipt `not_committed` oldu. | Bilinen pre-commit hata sonucu korunuyor. Kısmi receipt yazımı ve her filesystem fault kombinasyonu bu fixture’da kapsanmadı. |
| `commit_unknown` ve retry | #700 fixture’ı store directory-fsync hata enjeksiyonunda `commit_unknown` receipt’ini doğruladı; tekrar çağrı da `commit_unknown` verdi ve store/receipt byte’ları değişmedi. Kaynakta `link_attempting` syscall öncesi işaretleniyor; link hata/kesinti ve sonrasındaki cleanup/durability belirsizliği `commit_unknown` olarak sınıflanıyor. | Kör retry, otomatik rollback veya otomatik readback yok. Belirsiz sonuç çevrimdışı operator uzlaştırması gerektirir. Fixture tüm asenkron kesinti noktalarını veya gerçek uzak filesystem davranışını kanıtlamaz. |
| Aynı UID / root | Mod ve dizin kontrolleri izin kazara genişlemesini ve başka kullanıcıları sınırlar. | Aynı UID veya root süreçlerini birbirinden izole etmez; bu açık trust boundary’dir. |

## Bulgular ve işletim kapısı

### Düşük — provision lock unlock hatası root FD’sini sızdırıp sonucu gölgeler

`provision_empty_store_with_receipt()` cleanup bloğunda (`panel/auth_provision_draft.py:566-572`)
`flock(LOCK_UN)` hata verirse `os.close(lock_fd)` `finally` içinde çalışır,
ancak exception `os.close(root_fd)` satırına ulaşmayı engeller. Yalnız
`auth-provision-v1.lock` unlock hatasını enjekte eden disposable denemede
provision başarıyla store ve `committed` receipt yazdı, sonra `OSError` fırlattı
ve süreç içi FD farkı `+1` oldu. CLI bu `OSError`’ı “offline araç kullanılamıyor”
olarak raporlar; receipt ise `committed` durumundadır.

CLI her çağrıda kısa ömürlü ayrı süreç olduğu için süreç sonu leaked FD’yi
kapatır; aynı Python prosesinde provisioner’ı tekrar çağıran bir consumer varsa
FD birikir. Aynı operation ID ile tekrar çağrı committed receipt/store digest
eşleşmesini kontrol edip `replayed` döndürdüğünden bu yol kör snapshot yeniden
yazımı yapmaz. Yine de cleanup tüm descriptor’ları bağımsız kapatmalı ve unlock
hatası tamamlanmış receipt sonucunu gölgelememelidir. Bu bulgu yalnız cleanup
hata dalını ilgilendirir; credential sızıntısı veya store bütünlüğü ihlali
gösterilmedi.

### #730 düzeltme eki

Bu bulgu için #730 kapsamında cleanup sırası düzeltildi: unlock, lock-FD close
ve root-FD close artık birbirinden bağımsız deneniyor; aktif işlem hatası cleanup
hatasıyla değiştirilmiyor. Yeni fault-injection fixture’ı hem committed-receipt
replay durumunda hem de eşzamanlı `commit_unknown` yolunda `fd_delta=0`, byte
değişmezliği ve aynı retry sonucunu doğruladı. #730 kod/fixture teslimi board’da
ayrıca denetim bekliyor; bu ek yeni bir host veya gerçek UID kabulü değildir.

Diğer incelenen dallar #700 kapsamıyla tutarlı bulundu. Fixture’lar CLI’nin
temp-root sınırını, ID replay davranışını, known partial snapshot failure’ını
ve bir `commit_unknown`/no-blind-retry yolunu destekliyor. Daha geniş syscall
hata enjeksiyonu ve gerçek farklı UID çalıştırması yapılmadı.

Bu sonuç production provisioning onayı değildir. #672’deki NO-GO kapıları devam
eder: güvenilir araç zinciri/sürüm ve host owner kabulü, key custody, gerçek
principal/enrollment yaşam döngüsü, backup/restore/anti-rollback, browser GET
erişim kararı ve bağımsız rollout imzaları yoktur. `yuva auth provision`
yalnız mevcut özel geçici root içinde boş store fixture’ıdır; gerçek key
oluşturmaz ve auth’ı etkinleştirmez.

## Doğrulama

`PYTHONPATH=panel:. PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_auth_provision_threat_model tests.test_auth_provision_cli -v`

Sonuç: ilk denetim sırasında **10 test geçti** ve unlock fault injection
`fd_delta=1` bulgusunu üretti. #730 revizyonuyla aynı odaklı komut **12 test
geçti**; iki unlock-failure fixture’ında `fd_delta=0` oldu ve committed/replay
ile `commit_unknown` semantiği korundu. Testler yalnız geçici dizinler kullandı.
