# Release installer CommitUnknown için salt-okunur uzlaştırma raporu (#630)

**Tarih:** 2026-10-23
**Durum:** Kaynak/test sözleşmesi incelemesi ve operatör read-only rapor akışı; canlı install root/process incelenmedi, dosya/pointer değiştirilmedi, test çalıştırılmadı.
**Önemli:** `CommitUnknown` sonrasında tekrar install/rollback, pointer düzeltme veya `.staging-*` cleanup bu raporun parçası değildir.

## Sonuç

`release_installer.py` pointer yazımını `os.replace` ile atomik adlandırır; ardından install root dizinini `fsync` eder. `os.replace` hata verirse veya replace sonrası directory `fsync` başarısız olursa `CommitUnknown` yükselir. Bu durumda pointer'ın son hedefi ya da power-loss sonrası dayanıklılığı yalnız exception kodundan belirlenemez. Kod otomatik rollback/tekrar yapmaz; mesaj da exact pointer target'ını incelemeyi ister.

Install ve rollback iki ayrı pointer çağrısı yapar: varsa önce `previous`, sonra `current`. Bu nedenle **tek genel “işlem tamam/olmadı” biti yoktur**. Her pointer ve yayınlanmış release artifact ayrı ayrı uzlaştırılmalıdır. `current` hedefini operatör gözleyebilse bile `fsync` sonrası hata crash dayanıklılığını kanıtlamaz; aynı process içindeki `readlink` yalnız o anda görünen namespace durumunu gösterir.

## Kaynak akışı ve mevcut kanıt

| Adım | Kalıcı işlem | Hata sınıfı / gözlenebilir etki |
|---|---|---|
| Payload staging, verify, directory freeze | `releases/.staging-*` kopyalanır ve doğrulanır | Bu aşamadaki exception'da `moved=False` ise staging temizliği denenir; temizliğin başarılı olduğu tek başına exception ile kanıtlanmaz. `current` henüz ele alınmaz. |
| Final release publish | `renameat2(RENAME_NOREPLACE)` ile staging → `releases/<release_id>`; `releases/` dizini fsync | Final directory yayımlanmış olabilir. `releases/` fsync hatası, pointer aşamasından önce OSError verir; mevcut testte current eski kalır, data hash'i aynı, final release dir mevcut. Manifest receipt henüz yazılmamış olabilir. |
| Manifest receipt | `manifests/<release_id>.manifest.json` exclusive-create + file fsync, sonra `manifests/` fsync | Receipt/final release mevcut olabilir ama current henüz değişmemiş olabilir. Tekrar install aynı release ID'yi overwrite etmez; eski artifact için önce salt-okunur uzlaştırma ve ayrı kurtarma kararı gerekir. |
| `previous` pointer | Install/rollback'da önceki `current` ID'ye symlink atomik replace + parent dir fsync | Kendi `CommitUnknown`'ı `current` denemesinden önce çıkabilir. `current` hedeflenmedi; `previous` için exact readback gerekir. Rollback/install'in bir önceki pointer çağrısı zaten başarılı olmuşsa onun etkisi durur. |
| `current` pointer | Yeni install release ID'si veya rollback target ID'si symlink atomik replace + parent dir fsync | Replace exception'ı “outcome uncertain”; replace sonrası fsync exception'ı hedefin değiştiğini söyler fakat dayanıklılık unknown'dur. `previous` adımı daha önce commit edilmiş olabilir. |

`_atomic_pointer()` çağrı öncesi root directory fsync hatasını “pointer was not switched” şeklinde normal `InstallError` olarak raporlar. Yine de daha önceki final release/manifest/`previous` işlemleri gerçekleşmiş olabilir; bu nedenle tüm komutun no-op olduğu anlamına gelmez. Replace sonrası hatalarda geçici symlink'i kaldırma girişimi yapılır; bu, hedef `current`/`previous` pointer'ını geri almaz.

Mevcut `tests/test_release_installer.py` sentetik temporary root'ta şunları sınar:

- `current` replace çağrısı hata verdiğinde `CommitUnknown`, current eski target'ta kalır ve fixture data değişmez;
- current replace'ten sonra root fsync hata verdiğinde `CommitUnknown`, aynı process readback'inde current yeni target'ı gösterir ve fixture data değişmez;
- final release directory fsync hatasında current eski kalır, final release dir kalır ve data değişmez.

Testler previous pointer replace/fsync failure dallarını, current/pre-sync exception sonrası iki pointer uzlaştırmasını, gerçek process kill/power loss veya filesystem reboot dayanıklılığını kanıtlamaz. Bu görev testleri tekrar çalıştırmadı.

## Olaydan sonra salt-okunur uzlaştırma sırası

### 1. Mutasyonları durdur ve kapsamı sabitle

- `INSTALL_ROOT`, komut (`install`/`rollback`), hedef full release ID, manifest digest kaydı ve hata zamanı/mesajını içerik-secret taşımadan olay notuna alın.
- Aynı root'a yeni install/rollback çağrısı, pointer rename, manual `ln -s`, `rm`, cleanup veya servis cutover başlatmayın. Installer lock yalnız canlı komut süresince tutulur; process sonlandıktan sonra sonraki komut eski işlemin sonucunu çözmez.
- User data root'unu değiştirmeyin. Installer kodu `YUVA_DIR` üzerine yazım yapmaz ve rapor için data içeriğine bakmak gerekmez.

### 2. Exact install root ve pointer namespace'ini oku

Canonical root path'in caller tarafından beklenen absolute path olduğunu, path bileşenlerinde symlink bulunmadığını ve root'un owner/mode'unu `lstat`/`stat` ile doğrulayın. Önce pointer'ları takip etmeden link metnini kaydedin:

```sh
stat -c '%F %a %u:%g %n' "$INSTALL_ROOT" \
  "$INSTALL_ROOT/current" "$INSTALL_ROOT/previous"
readlink -- "$INSTALL_ROOT/current"
readlink -- "$INSTALL_ROOT/previous"
```

Pointer eksikse veya regular file/symlink değilse, link hedefi tam `releases/<full-commit>-<full-payload-sha256>` kanonik biçiminde değilse, ya da hedef release dizini yoksa **STOP/HOLD**. Hedefi düzeltmeyin, fallback'e geçmeyin. Pointer yokluğu/bozukluğu teslim edilen güvenilir durumu belirlemez.

Her link için sonradan, exact target path'i türeterek `lstat` ile release directory'yi, `manifests/<id>.manifest.json` receipt'ini, mode/owner/size'ı ve `.staging-*`/geçici symlink adlarını envanterleyin. İçerik basmayın. `.staging-*` veya gizli geçici symlink görülürse süreç/işlem owner'ı ve relation'ı bilinmiyorsa **HOLD**; rapor sırasında cleanup yapılmaz.

### 3. Görünen pointer çiftini sınıflandır

Bu tablo crash sonrası durability'yi çözmez; yalnız gözlenen anlık adlandırma durumunu sınıflandırır.

| Gözlenen `current` / `previous` | Olası yorum | Karar |
|---|---|---|
| `current=old`, `previous=old`, yeni final release/manifest mevcut | Current switch görünür değil; install artifact yayımlanmış olabilir. Exception replace çağrısından geldiyse gerçek hata/FS davranışı sonucu uncertain sayılır. | `not committed` diye otomatik karar verme. Install root'u HOLD'da tut, her iki ID'yi offline verify et, operatör/release owner kararı iste. |
| `current=new`, `previous=old` | Install hedefi aynı process namespace'inde görünür; normal beklenen çift olabilir. Post-replace fsync hatasında kalıcılık kanıtlanmış değildir. | Başarı veya cutover GO deme; root/pin/source/artifact doğrula, reboot/host recovery sonrası kontrol gerekip gerekmediğini işletim sahibi kararlaştırsın. Blind rerun yok. |
| `current=old`, `previous` başka bir hedef | Önceki pointer adımı ilerlemiş ama current adımı başarısız/başlamamış olabilir; rollback/install sırasında olası ara state. | Her pointer ve artifact ayrı doğrulanana kadar HOLD; current'ı “eşleştirmek” için otomatik rollback yok. |
| `current=new`, `previous` beklenen eski ID değil/eksik | Pointer çifti beklenen geçişle uyuşmuyor veya daha önce başka işlem var. | Eşzamanlı installer/operatör geçmişi ve iki release/pin doğrulanana kadar HOLD. |
| Link bozuk, release/manifest yok, yanlış owner/mode ya da manifest/pin/source doğrulaması başarısız | Güvenilir release adayı kanıtlanamıyor. | NO-GO/HOLD; pointer'a dokunma, release'i çalıştırma veya silme. |

Install/rollback çağrısının hangi pointer aşamasında kaldığı log/exception'dan bilinmiyorsa olası tüm satırlar açık kalır; sadece beklenen bir çiftin görülmesi diğer olasılıkları veya geçmiş crash state'ini dışlamaz.

### 4. Release artifact'larını offline doğrula

Her mevcut pointer target ID ve işlem hedef ID için, yalnız owner'ın bağımsız kayıt/custody kaynağından alınmış **o manifest'e ait** tam pin, tam commit'teki temiz source checkout ve saklanan manifest receipt'iyle aşağıdaki salt-okunur komutu uygulayın:

```sh
python3 release_manifest.py verify \
  --payload "$INSTALL_ROOT/releases/<exact-release-id>" \
  --manifest "$INSTALL_ROOT/manifests/<exact-release-id>.manifest.json" \
  --source-repo "/absolute/path/to/clean-source-at-exact-commit" \
  --trusted-manifest-sha256 "<independently-custodied-manifest-pin>"
```

Pin'i receipt'ten veya release dizininden türetmeyin; aynı hesaplama yalnız internal consistency verir. Bir release'in geçmesi diğer pointer'ın release'ini geçirmez. `verified_release`, runtime process, PATH/unit alignment, `YUVA_DIR`, stopped writers veya cutover güvenliği değildir.

### 5. Raporla, sonra ayrı karar bekle

Uzlaştırma raporu yalnız şunları içersin: incident/run ID; root canonical path; hata class/step (bilinmiyorsa unknown); `current` ve `previous` raw link hedefi; her pointer için `lstat` tipi/owner/mode; release ID → final dir/manifest receipt varlık ve metadata'sı; offline verification sonucu ve kullanılan pin custody referansı; `.staging-*`/temporary link varlığı; başka installer/PID veya cutover bilgisinin durumu (unknown olabilir); data root'a dokunulmadığına dair kod kapsamı (canlı hash iddiası değil); karar sahibi ve next action. Manifest/payload içeriği, Yuva kullanıcı verisi, credential veya pin provenance'ı sağlayan private materyal rapora kopyalanmaz.

Sonuç `observed pointer state` ile sınırlı kalmalıdır. Eğer post-replace directory fsync hatası veya host reboot/power loss yaşandıysa tek process'te pointer'ı okumak durability'yi çözmez. Ayrı bir release/host owner recovery planı ve tam kanıt olmadan GO/rollback/install retry yapılmaz.

## Mevcut boşluk ve takip önerisi

- Installer `CommitUnknown` sınıfını ve fail-without-auto-rollback davranışını uygular; read-only reconciliation report CLI/API yoktur.
- Install, final release/manifest receipt'i current'dan önce yazar; başarısız geçişte yayımlanmış artifact'lar kalabilir. Bunların tutulması no-overwrite güvenliğine yardımcıdır; orphan cleanup ayrı onay/retention kararıdır.
- Pointer güncellemesi `previous` ve `current` için iki ayrı `os.replace` + directory `fsync` dizisidir; çift-pointer transaction yoktur. Aradaki failure kısmi pointer ilerlemesi doğurabilir.
- Mevcut testler current replace/post-replace fsync ve release directory fsync yollarını enjeksiyonla sınar; previous pointer failure, process crash, reboot ve durability recovery kapsamı ayrıca ele alınmalıdır.
- İleride rapor aracı yazılırsa sadece exact-root `lstat`/`readlink`, bounded metadata inventory ve explicit pin ile read-only manifest verify yapmalı; varsayılan davranış pointer'ı değiştirmemek, staging/release silmemek ve sonucu `commit_unknown` olarak korumak olmalıdır.

## Kaynaklar

- `release_installer.py::_atomic_pointer`, `install_release`, `rollback_release`: lock, publication order, pointer commit ambiguity ve exception cleanup.
- `tests/test_release_installer.py::test_release_directory_fsync_fault_keeps_old_pointer_and_data`, `test_current_pointer_replace_fault_is_commit_unknown_without_rollback`, `test_post_replace_pointer_fsync_fault_is_commit_unknown_no_auto_rollback`: temp fixture kanıtı.
- [#543 install/rollback sözleşmesi](release-installer-543.md): ambiguous pointer sonrası exact target inceleme ve blind retry yasağı.
- [#609 cutover fixture](release-cutover-acceptance-609.md): synthetic path/cutover; fixture GO host durability/identity kabulü değildir.
- [#604 operatör rollback checklist'i](operator-acceptance-rollback-checklist-604.md): writes freeze, exact release verification, data root korunumu ve unknown state'te durma.
- [#628 temporary-root rehearsal](local-mvp-clean-root-install-rehearsal-628.md): explicit-root rehearsal ve host rollout ayrımı.

Bu rapor statik davranış ve mevcut fixture kodunu açıklar. Gerçek INSTALL_ROOT/process/disk state okunmadı; install/rollback, pointer değişimi, cleanup, servis kontrolü veya test çalıştırması yapılmadı.
