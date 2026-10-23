# #692 — Legacy CLI kopyaları için single-writer containment kabul kapıları

**Tarih:** 2026-10-23
**Durum:** Tasarım/acceptance planı; containment uygulanmadı, tarihsel kopyalar çalıştırılmadı, test veya host taraması yapılmadı.
**Kaynaklar:** #552/#627/#638/#659; #679 çağrı yüzeyi envanter planı (teslim edildi, denetim bekliyor).

## Amaç ve sınır

Bu plan, yerel CLI kopyalarının ve bunları çağırabilecek panel/import/launcher/automation yollarının aynı `YUVA_DIR`'e birden fazla görev yazıcısı olarak erişmesini önlemek için kanıt ve kabul kapıları tanımlar. #552/#611 kanonik repo panel/CLI yolunda ortak CLI task core'u ve `YUVA_DIR/.kilit` olduğunu gösterir; bu sonuç tüm yerel binary'lere veya aynı-UID süreçlere genellenemez.

Özellikle şu tarihsel restore-check hedefleri inceleme girdisi olarak kalır:

- `<YUVA_DATA_ROOT>-yedek/restore-check.T4hbP8/yuva/bin/yuva`
- `<YUVA_DATA_ROOT>-yedek/restore-check.XOeUcj/yuva/bin/yuva`

#638'in kabul edilmiş kapsamı yalnız yeni scratch restore-check çıktısındaki sabit CLI stub'ıdır. Bu stub arşiv içindeki, mevcut tarihsel ağaçlardaki veya panel/import çağrılarındaki CLI'yi kapatmaz. #659, bu iki ağacın doğrudan çalıştırılmaması gerektiğini ve aynı-UID/absolute-path bypass'larının ayrı kaldığını belirtir. Bu belge operatör prosedürü, OS izolasyonu veya teknik enforcement kurulduğunu iddia etmez.

## Tehdit ve iddia sınırları

- **Kanonik writer:** Desteklenen `yuva-v2/bin/yuva` task işlemleri ortak `gorev_guncelle()`/`cmd_gorev_sonraki()` yolundan `YUVA_DIR/.kilit` alır. Panel `/api/gorev` desteklenen panel içinde aynı CLI core'una dispatch eder (#552/#611).
- **Kopya writer:** `yuva-dev`, `yuva-ui-dev`, eski root ve restore-check kopyaları ayrı dosyalardır. Schema, lock ve fail-closed davranışları aynı olmayabilir. #627/#596 envanterindeki hash'ler tarihsel snapshot'tır; güncel path kimliğini yeniden ölçmeden varsayma.
- **Call surface:** PATH'ten kaldırmak kısa `yuva` komutunu etkileyebilir; doğrudan absolute path, `python3 /path/bin/yuva`, `SourceFileLoader`/`importlib`, kopya paneli, script, cron veya systemd çağrısını tek başına kapatmaz.
- **Same UID:** `chmod` ve cooperative `.kilit`, aynı UID'li keyfi Python/import/direct-file writer'a karşı sınır değildir. Hash eşitliği davranış veya provenance eşitliğini kanıtlamaz.
- **Üretim iddiası:** Yalnız listelenmiş köklerde `no-match` bulunması sistem genelinde erişim yolu yok demek değildir. Bütün bypass'lar OS/owner/admission sınırıyla kapatılmamışsa sonuç “operasyonel kullanma yasağı” veya “kısmi containment” olarak kalır.

## Çağrı yüzeyi ve containment matrisi

Her satır ayrı araştırılır ve kabul edilir; bir giriş türünün kapatılması diğerlerine kanıt sayılmaz.

| Yüzey | Envanter kanıtı | Mirror/fixture kabul denemesi | Kalıcı containment iddiası için gereken kontrol |
|---|---|---|---|
| **PATH ve shell** (`PATH`, alias, function, hash cache) | İnceleme shell'inde `type -a`/`command -v -a`; bilinen startup dosyalarında literal ve değişkenle kurulan path; zaman damgası ve kapsam | Desteklenen kısa komutun yalnız canonical, onaylı CLI'ye çözüldüğünü doğrula; `yuva` komut adını taklit eden fixture PATH girdisini test et | PATH/alias temizliği kolaylık kontrolüdür. Mutlak path ve import bypass'ı ayrıca kapatılmadıkça “contained” deme. |
| **Symlink ve launcher** (`~/.local/bin`, desktop `Exec=`, wrapper) | Her symlink bileşeninin link text/resolved target'ı, launcher caller/argv, executable identity/hash | Geçici launcher üzerinden mirror CLI çağrısını dene; wrong target veya legacy hash için fail-closed reddi bekle | Launcher tek giriş olarak zorlanmalı; kullanıcı doğrudan target path'e erişebiliyorsa güvenlik sınırı değildir. |
| **Mutlak path / Python script yürütme** | Shell, script, repo ve bilinen config'lerde exact path, restore-check directory marker'ı ve `python[3] <path>` eşleşmeleri | Mirror üzerinde doğrudan script çalıştırma ve task mutation denemesi; sentinel ledger değişmemeli | Gerçek dosyaya erişim/execute/write ayrı OS policy ile kısıtlanmalı veya teknik olarak yalnız allowlist edilmiş giriş mümkün olmalı. Gerçek tarihsel binary çalıştırılmaz. |
| **Python import / source loader / helper çağrısı** | `SourceFileLoader`, `spec_from_file_location`, `runpy`, `exec`, import path manipulation ve `gorev_kaydet`/`kaydet` gibi doğrudan writer referansları | Geçici mirror modülünü yükleyip export edilen writer entrypoint'lerine sentetik data root ile deneme; loading tek başına mutation yapmamalı, helper çağrısı varsa containment onu reddetmeli | CLI parser guard'ı import edilen writer helper'ını kapatmaz. Kodu çağrılabilir kılan kullanıcıdan execution/import/write yetkisi kaldırılmalı veya bütün write'lar broker/UID sınırından geçmeli. |
| **Panel/server bridge** | Her panel kopyasının `CODE_ROOT`/CLI path'i, `SourceFileLoader`/subprocess bridge'i, task route'u, unit/launcher bağı | Disposable panel fixture'ında task API'nin canonical core'a gittiğini; legacy panel/bridge'in reddedildiğini ve sentinel data root'un değişmediğini doğrula | Panel panel-process/route düzeyinde kapatılmalı; sadece kanonik paneldeki HMAC/policy kontrolü başka eski paneli veya CLI kopyasını sınırlamaz. |
| **Automation** (cron, systemd service/timer, scripts, desktop jobs) | Bilinen user/system unit ve timer'ların `ExecStart`/`OnCalendar`, crontab satırları, backup/restore wrapper zincirleri; okunamayan kaynak `unknown` | Her bilinen launcher'ın disposable mirror hedefini kullandığını ve legacy path çağrısını reddettiğini doğrula; job body'sini gerçek host'ta tetikleme | Timer stop veya unit offline tek başına in-flight/stale process'i dışlamaz. Admission kapalı ve iş drain edilmiş olmalı; her restart/enable path'i de hesaba katılmalı. |
| **Aynı-UID doğrudan data-root writer** | `YUVA_DIR` seçimi, aynı UID altındaki bilinen source/process/cgroup/launcher; keyfi/unknown caller'lar ayrıca işaretlenir | Farklı UID/OS fixture'ında unauthorized writer'ın synthetic root'a erişemediğini; same UID testinde chmod'un yetersizliğini göster | Root-owned/read-only quarantine, ayrı writer UID, izinli broker veya eşdeğer OS sınırı gerekir. Erişim sahibi aynı UID ise permission-only çözüm “containment” sayılmaz. |
| **Restore/archive kopyası** | Kopya exact path, güncel lstat/hash/owner/mode/parent perms; panel ve sibling entrypoint varlığı statik olarak kaydedilir | Yalnız temp mirror'da path-aware guard/stub davranışı; sentinel `YUVA_DIR` byte/mode öncesi/sonrası eşit | #638 scratch stub gerçek historical path'i değiştirmez. Kopyayı immutable tutma seçimi korunur; kullanma yasağı tek başına teknik engel değildir. |

## Aşamalı kabul ve karar kapıları

### A. Read-only kaynak kimliği

1. Her hedefin `lstat` türünü, tam path ve varsa symlink çözümünü, owner/mode/hash'ini ve üst dizin izinlerini aynı zaman damgasında kaydet. #627/#596 tarihsel değerlerini güncel değer gibi kullanma.
2. `PATH`/shell, launcher, absolute path, import/helper, her panel kopyası ve automation alanları için #679'daki kök kayıt formunu doldur. Aranamayan alan `unknown` kalır; geniş disk taramasına çevrilmez.
3. Hedef dosyanın çalıştırıldığı, import edildiği, açılıp yazıldığı; mode/owner/path'in değiştirildiği veya archive/live ledger'a erişildiği bir adım olmamalıdır.

### B. Seçilen politika

Operatör kontrol türünü ve sahibini seçer; onaysız varsayılan **HOLD + çalıştırma/import etmeme talimatı**dır.

| Kontrol seçimi | Kabul seviyesi | Açık kalan bypass |
|---|---|---|
| Operatör “çalıştırma/import etme” kuralı | Kullanım prosedürü kaydedildi | İnsan hatası ve otomasyon bunu teknik olarak aşabilir; containment iddiası yok. |
| PATH/alias/launcher temizliği | Kısa komut ve bilinen launcher için kolaylık kontrolü | Absolute path, Python import, diğer shell/user, panel ve same-UID writer. |
| CLI içi `gorev` guard/stub | Yalnız o dosya içinden parser/main çağrısı | Import edilen helper, başka writer, değiştirilmemiş kopya veya guard'ın öncesinden yapılan kod yan etkisi. #638 scratch stub'ı yalnız yeni scratch çıktısı içindir. |
| Ayrı UID + owner-controlled quarantine/read-only alan veya writer broker | Kabul edilen OS threat modelindeki execution/write bypass'larını kapatabilir | Root/ayrıcalıklı yönetici, yanlış mount/ACL, import/read hakkı ve eksik process/caller envanteri ayrıca değerlendirilir. |

Same-UID `chmod` tek başına containment kabul edilmez. Karantina, owner/mode, UID, ACL, mount veya path değişimi ayrı operatör onayı ve öncesi/sonrası metadata kaydı gerektirir.

### C. Disposable negative fixture

Gerçek kaynak byte'larından TemporaryDirectory altında bir mirror üret; gerçek historical path'i veya paneli testte çalıştırma. Fixture sentetik `YUVA_DIR` ve sentinel `gorevler.json` kullansın. Seçilen kontrolün bütün ilgili invocation'larını ayrı dene:

1. Desteklenen PATH/launcher üzerinden görev yazma çağrısı legacy target'a ulaşmamalı.
2. Mirror CLI'ı direct `python`/absolute-path formuyla çağırma reddedilmeli veya OS policy tarafından engellenmeli.
3. Python source loader/import üzerinden modül ve doğrudan writer helper yolu denenmeli; parser dışı writer bypass'ı açık kalmamalı.
4. Kopya panel task mutation route'u canonical dışı CLI'ı çağıramamalı; test yalnız temporary panel/source/data root kullanmalı.
5. Bilinen automation wrapper'ları mirror ile sınanmalı veya static evidence + disabled admission sonucu kaydedilmeli.
6. `gorev ekle`/durum değiştiren fixture işlemi sonrası sentinel hash, mode ve directory entry set'i önce/sonra aynı olmalı; `.kilit`/mesaj dosyası gibi beklenmeyen artifaktlar oluşmamalı.
7. Fixture sonunda mirror temizlenmeli. Gerçek iki historical path'in pre/post hash, mode, owner ve parent metadata'sı değişmemiş olmalı.

Bir surface test edilmediyse overall sonuç PASS olamaz. PATH-only test direct/import/panel/automation bypass'larını kapatmaz. Testte fail-closed davranış üretmek, gerçek kopyanın bugünkü davranışı hakkında runtime kanıt değildir.

### D. Karar

| Kanıt durumu | Karar |
|---|---|
| Tüm bilinen caller surfaces listeli; her surface seçilen policy ile kapalı; OS/UID sınırı ve disposable negative fixture PASS; gerçek source/archive/live data metadata değişmez | Yalnız rapor kapsamındaki threat model için **CONTAINED**; owner onayı kaydedilir. |
| PATH/launcher kısıtlı, fakat absolute/import/panel/automation/same-UID yolları teknik olarak açık | **PARTIAL / OPERATIONAL USE BAN**; security containment veya single-writer ispatı yok. |
| Herhangi bir surface unknown/erişilemez; stale process veya data-root hedefi belli değil; fixture/live hash karşılaştırması eksik | **HOLD / UNKNOWN**; “bulunmadı” diye kapatma yok. |
| Historical path/owner/mode/archive/live data değişmiş veya target testte çalıştırılmış | **HOLD / INCIDENT REVIEW**; custody ve operatör kararı olmadan test/rollback yok. |

## Rapor şablonu

### Kapsam ve kimlik

- İnceleme tarihi/timezone, owner ve onay:
- Aranan kökler, araç/komut, dosya türü ve erişilemeyen kökler:
- İki historical hedef için `lstat`, resolved path, SHA-256, owner/mode, parent mode:
- Gerçek historical CLI/panel çalıştırıldı mı veya import edildi mi: **Hayır** / açıklama:
- Archive, sidecar, task ledger, service, mode, owner, symlink değişti mi: **Hayır** / incident:

### Surface bulguları

| Surface | Confirmed/candidate/no-match-in-scope/unknown | Caller + source/line | Target ve `YUVA_DIR` çözümü | Policy | Fixture/evidence ref | Bypass/sınır |
|---|---|---|---|---|---|---|
| PATH/shell |  |  |  |  |  |  |
| Symlink/launcher |  |  |  |  |  |  |
| Absolute path |  |  |  |  |  |  |
| Python import/helper |  |  |  |  |  |  |
| Panel/server bridge |  |  |  |  |  |  |
| Cron/systemd/automation |  |  |  |  |  |  |
| Same-UID/direct data writer |  |  |  |  |  |  |

### Negative fixture ve karar

- Temporary mirror identity ve data-root konumu:
- Direct/launcher/import/panel/automation denemeleri:
- Sentinel ledger pre/post SHA-256, mode ve directory entries:
- Temporary artifact cleanup:
- Historical source identity pre/post değişmezliği:
- Karar: `CONTAINED` / `PARTIAL — OPERATIONAL USE BAN` / `HOLD — UNKNOWN` / `HOLD — INCIDENT REVIEW`:
- Karar sahibi, onay tarihi ve yeniden gözden geçirme koşulu:
- Kalan bypass'lar ve takip görevi:

## Kaynaklar

- [#552 single-writer çağrı haritası](task-ledger-single-writer-552.md)
- [#627 yerel kopya envanteri](task-writer-local-copy-inventory-627.md)
- [#638 restore-check scratch guard ve residual risk](restore-check-cli-guard-revision-638.md)
- [#659 historical copy containment seçenekleri](restore-check-historical-copy-containment-659.md)
- [#679 çağrı yüzeyi envanter planı](restore-check-call-surface-inventory-plan-679.md)
- [#611 panel/CLI task dispatch grafiği](task-writer-call-graph-611.md)

Bu belge yalnız acceptance planıdır. Envanter, fixture, OS isolation, launcher/permission değişikliği, gerçek CLI/panel çalıştırması veya canlı data-root işlemi bu görevde yapılmadı.
