# Yuva #681 — Release staging inventory için #664 sonrası bulgu haritası

**Tarih:** 2026-10-23
**Karar:** **HOLD / NO-GO for operational action.**
**Önkoşul:** #647 `verified`; #664 bağımsız fd review revizyonu teslim edilmiş (`pending_verification`).
**Kapsam:** Yalnız mevcut kaynak ve rapor/fixture kanıtı. Gerçek `INSTALL_ROOT` taranmadı; kaynak düzeltilmedi, test/runtime/host işlemi çalıştırılmadı.

## Karar özeti

#647 envanter aracı bounded ve read-only bir gözlem raporu üretir; her durumda `HOLD` döndürür. Staging/release cleanup, publish, resume veya pointer repair yetkisi vermez. #664 teslimi normal tekrar çağrısı, test edilen symlink/output dalları ve özellikle hata cleanup'ı için ek kanıt sağlar; fakat child descriptor leak bulgusu **F1 FAIL** olarak kalmıştır. Güncel `release_staging_inventory.py` içinde `_open_child_directory()` başarılı `os.open()` sonrasındaki `os.fstat()` çağrısını cleanup kapsamına almıyor; `_inventory_open_root()` iki child açılışını da `try/finally` öncesinde yapıyor. Dolayısıyla rapor #664 bulgusunu düzeltmiş değildir.

Bu nedenle herhangi bir host/install root için araçla operasyonel karar verme, cleanup veya release/pointer işlemi için kabul yoktur. Gözlem geçici/izole fixture'da dahi kullanılacaksa F1 için düzeltme ve hata enjeksiyonlu regresyon kanıtı ayrı bir revizyonda gerekir. Düzeltme sonrası da inventory tek başına GO üretmeyecektir.

## Kanıt ve güven sınırı eşlemesi

| Bulgu / sınır | Kaynak veya fixture kanıtı | Değerlendirme | Operasyon etkisi |
|---|---|---|---|
| Root ve child path no-follow | `release_staging_inventory.py`: açık absolute root, component traversal `O_NOFOLLOW`; `releases`/`manifests` fd-relative açılır ve inode/dev karşılaştırılır. #647/#664 fixture symlink root, symlink releases ve unsafe pointer hedefini sınar. | Test edilen path'lerde dış target taranmaz; bu, eşzamanlı installer durumunu kanıtlamaz. | **Dar kapsamlı PASS**; path güvenliği dışında işlem izni vermez. |
| Bounded/secret-free envanter | `_entries()` en çok `limit+1` okur; canonical olmayan adlar aggregate sayılır; manifest içeriği açılmaz; root redacted; pointer target doğrulanmazsa atılır. #647 fixture byte/mode/symlink snapshot'ı karşılaştırıp içerik/path sızıntısını denetler. | Kanıt yalnız fixture'daki örnek ad/target/content sınıfları içindir. `truncated=true` eksiksiz envanter değildir. | Truncated/metadata error/unknown entry varsa gözlem eksik; **HOLD**. |
| Installer ve transaction state'i | `.installer.lock` yalnız lstat metadata'sıyla `present_uninspected`; `active_installer_process` ve her release `process_state` `unknown`. | Lock varlığı/yokluğu, yaşı veya fd inventory'si aktif installer, açık cwd/fd/mount ya da owner uzlaştırması değildir. | Host process/transaction sahibi bağımsız ve yetkili yöntemle çözülmeden **HOLD**. |
| Staging sınıflandırması | `.staging-<id>` `STAGING_STATE_UNKNOWN`; yanlış tür/owner/mode veya metadata sorunu `HOLD_UNKNOWN`. Ağaç recursive gezilmez, transaction phase bilinmez. | İçerik bütünlüğü, staging'in terk edilmiş olup olmadığı veya güvenle silinebilirliği çıkarılamaz. | Cleanup/resume/publish yok. |
| Release/receipt/pointer sınıflandırması | Pointer `readlink` ile ayrı gözlenir; canonical target metadata'ya bakılır. Manifest receipt yalnız regular-file/owner/mode/link/size metadata'sı olarak `present_unverified`; içerik/digest/signature doğrulanmaz. Bütün item kararları `HOLD`. | Farklı dosyalar aynı atomik snapshot'tan okunmaz. Pointer, receipt ve directory listing arasındaki yarışlar karışık gözlem üretebilir. | External manifest/payload pin ve exact release doğrulaması olmadan active/inactive etiketi güvenilir yayın/cleanup kararı değildir. |
| Normal fd lifecycle | #647 testinde `/proc/self/fd` sayısı 40 ardışık normal inventory çağrısı öncesi/sonrası sabit; `_entries()` duplicate descriptor'ı `finally`, scandir iterator'ını context manager ile kapatır. | PASS yalnız olağan dönüş ve tekrarlı normal çağrılar için. | Hata/erken çıkış cleanup'ı ayrıca kanıtlanmalı. |
| **F1: child `fstat()` exception fd leak** | #664 temporary-root deneyinde enjekte edilen `os.fstat` hatasında descriptor sayısı `4 → 5`, `leaked_descriptors=1`. Güncel `_open_child_directory()` hâlâ `fd=os.open(...)` ardından korunmasız `opened=os.fstat(fd)` yapıyor. | **FAIL — kaynakta hâlâ mevcut.** Dış `root_fd` finally'si child descriptor'ı kapatmaz. Tekrarlı hata fd limitini tüketebilir. | Operational use **NO-GO**; F1 düzeltmesi ve injected-fstat regresyonu beklenir. |
| İkinci child açılışında sahiplik penceresi | `_inventory_open_root()` önce `releases_fd`, sonra `manifests_fd` açıyor; `try` daha sonra başlıyor. `_open_child_directory()` beklenmeyen exception fırlatırsa önce açılan fd cleanup'a ulaşmayabilir. | **Residual cleanup risk.** F1'in gösterdiği hata modeli bu akışı da kritik kılıyor; exception enjeksiyonlu ikinci-open fixture yok. | İki fd de baştan `None` initialize edilip her acquisition korumalı cleanup kapsamına alınmalı; hata fixture'ı gerekir. |
| Root traversal `close(old_fd)` aralığı | `_open_explicit_root()` `next_fd` açtıktan sonra eski `fd`'yi kapatıyor, sonra `fd=next_fd` atıyor. `close(old_fd)` beklenmedik hata verirse yeni `next_fd` sahipliği kaybolabilir. #664 bunu enjekte etmedi. | **Test edilmemiş dar hata penceresi**; rapor/fixture kanıtı yok. | FD error-injection matrisi tamamlanmadan cleanup kabulü tam değildir. |

## #664 kabul tablosunun yorumu

- **PASS:** Geçici fixture'da 40 ardışık normal çağrıda descriptor sayısı sabit.
- **PASS (tested branches only):** root/release/pointer symlink no-follow ve test edilen output privacy dalları.
- **STATİK/PASS (normal path only):** scandir iterator + duplicate fd cleanup düzeni.
- **FAIL:** Child `fstat` hata enjeksiyonunda bir fd leak.
- **NOT TESTED:** `_open_child_directory` ikinci açılış istisnası, `_open_explicit_root` old-fd close exception, `scandir`/entry metadata hatalarının tümü, eşzamanlı pointer/manifest/release değişimleri.
- **SCOPE PASS:** #664 review koşusu gerçek host `INSTALL_ROOT`'a erişmedi; bu kapsam sınırıdır, host kabul kanıtı değildir.

#664'ün 7 testin geçtiği notu F1'i geçersiz kılmaz: hata enjeksiyonlu deney ayrıca bir descriptor leak göstermiştir. Normal fixture testleri F1 senaryosunu test etmiyor.

## Residual race ve anlam sınırları

1. **Zamansal tutarsızlık:** root/release listing, `current`/`previous`, manifest metadata ve lock farklı anlarda okunur; shared transaction lock alınmaz. Installer inventory sırasında ilerleyebilir. Rapor snapshot consistency veya quiescence sağlamaz.
2. **Process sahipliği bilinmiyor:** `.installer.lock` metadata'sı lock holder veya çalışan installer kanıtı değildir. Installer sürecinin fd/cwd/mount ilişkileri envanterde yoktur.
3. **İçerik doğrulanmıyor:** staging payload, release payload, manifest içeriği, imza ve external digest pin okunmaz. Metadata eşleşmesi artifact authenticity/integrity değildir.
4. **Bounded tarama eksik kalabilir:** root ve releases ayrı ayrı `max_entries` ile sınırlıdır; truncation, hata ve unknown entry açıklığa kavuşmadan yokluk/eksiksizlik sonucu çıkarılamaz.
5. **Metadata/path yarışları:** `lstat`/`readlink`/directory enumeration birbirinden bağımsızdır. No-follow dış symlink traversal riskini düşürür, fakat tarama sırasında rename/replace altında aynı generation'a ait tutarlı envanter garantilemez.
6. **Sınıflandırma eylem değildir:** `PUBLISHED_INACTIVE`, `PUBLISHED_RECEIPT_INCOMPLETE`, `POINTER_REFERENCED` ve `STAGING_STATE_UNKNOWN` release owner'lığı, işlem sahibi veya silme yetkisi vermez. Root item ve pointer temporary adlarında da karar HOLD'dur.

## Üretim kullanımına geçiş kapıları

Operasyonel değerlendirme için aşağıdakilerin tümü ayrı kanıtlanmalıdır:

1. **F1 düzeltmesi:** child fd açıldıktan itibaren tek ve açık ownership/cleanup; child fd'ler `try/finally` öncesi sızabilecek şekilde edinilmemeli.
2. **Hata enjeksiyonlu fixture:** `fstat`, ikinci child open, old-fd close, `dup`, `scandir` iterator/entry metadata ve collection early-return hata yollarında fd sayısı sabit; rapor fixed/path-free ve karar HOLD.
3. **FD ve symlink kabul matrisi:** normal/repeated, fail-before/after acquisition, root/release/manifest/pointer swaps, symlink/no-follow ve private output dalları sonuçları ayrı kaydedilir. Testler geçici install root ile sınırlı olur.
4. **Installer owner/quiescence:** exact host root ve o root üzerinde installer/process/lock/cwd/fd/mount durumu yetkili owner tarafından bağımsız uzlaştırılır. Inventory bunu kendisi kanıtlamaz.
5. **Artifact trust:** exact release ID, externally pinned manifest/payload digest veya imza, receipt politikası, hedef reader/data schema ve rollback kararı bağımsız kanıtlanır.
6. **Eylem izni ayrı:** cleanup/publish/pointer repair ancak açık owner kararı, exact target ve ayrı onaylı mutation prosedürüyle yapılır; inventory raporu tek başına eylem kapısı değildir.

Bu kapılar geçilse bile envanterin karar sözleşmesi **HOLD** olarak kalır; rapor yalnız kanıt paketinin bir girdisidir.

## Bu teslimde yapılanlar

`release_staging_inventory.py`, #647 raporu, #664 review raporu ve ilişkili test kaynağı statik karşılaştırıldı. Kaynak/test/host state değiştirilmedi; test çalıştırılmadı. Canlı `INSTALL_ROOT` kullanılmadı. Mevcut kaynak #664 F1'i hâlâ içerdiğinden sonuç **HOLD / NO-GO** olarak verildi.

## Kaynaklar

- `docs/release-staging-readonly-inventory-647.md` — #647 sınıflandırma, bounded envanter ve fixture kapsamı.
- `docs/release-staging-fd-review-664.md` — fd yaşam döngüsü kabul matrisi, F1 ve sentetik `fstat` failure kanıtı.
- `release_staging_inventory.py` — güncel descriptor ownership ve metadata akışı.
- `tests/test_release_staging_inventory.py` — TemporaryDirectory fixture ve normal repeated-fd testi.
- `docs/release-installer-staging-recovery-631.md` — staging recovery için owner/process HOLD karar ağacı.
- `docs/release-installer-commit-unknown-reconciliation-630.md` — commit-unknown uzlaştırma sınırları.
