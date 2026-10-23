# İlk yerel MVP için temiz geçici kurulum provası (#628)

**Tarih:** 2026-10-23
**Amaç:** Release hazırlama, explicit-root install, pointer doğrulama ve rollback akışını gerçek Yuva kullanıcı verisi/servisi olmadan prova etmek.
**Karar sınırı:** Bu belge bir host rollout izni değildir. Fixture GO yalnız sentetik kök için geçerlidir; host kararı mevcut kapılarda NO-GO'dur.

## Önce iki çalışma kipini ayırın

Tam sentetik kabul zinciri için repo kökünden:

```sh
python3 release_acceptance.py fixture
```

Harness kendi geçici Git source/payload'larını, fixture `YUVA_DIR`'ini, install root'u, backup/scratch ve PATH/unit kopyalarını kurar; iki release'i install edip canary/rollback zincirini yürütür ve temporary root'u sonunda yoklar. Gerçek repo dosyaları, home kurulumu, systemd, servis, port, canlı veri veya gerçek backup kullanılmaz. Beklenen rapor `scope=temporary-fixture-only`, `fixture_decision=GO` olabilir; `host_rollout_decision=NO-GO` kasıtlıdır. Fixture pin'i harness tarafından üretildiği için bağımsız trust anchor değildir.

Alttaki elle adımlar, release manifesti ve explicit-root installer sözleşmesini bir başka **izole prova kökünde** yürütme şablonudur. Placeholder yolları gerçek kullanıcı/servis dizinlerine çevirmeyin; komutlar `systemctl`, PATH symlink'i veya canlı `YUVA_DIR` değiştirmez. Gerçek data/host için #576/#604 kabulü ve ayrıca rollout kararı gerekir.

## Elle, temiz temporary root'ta install provası

### 1. Girdileri ve kökleri hazırla

- Kanonik Git repository'yi ve incelenmiş tam commit'i seçin. Worktree temiz olmalı; dirty geliştirme kopyasından release üretmeyin.
- Üçüncü taraf/bağımsız operatör kanalından gelen manifest pin'i gerçek kullanımda ayrı custody'den sağlanmalıdır. Aynı geçici kökte oluşturup hemen verifier'a verilen pin yalnız sentetik plumbing provasıdır.
- Yeni bir private temporary root oluşturun. Source repo bu root'un dışında olmalı; `payload`, manifest, install root, data root ve scratch root birbirinden ayrı, kardeş hedefler olmalı. Installer source/payload/install/data yollarının birbirinin içine girmesini kabul etmez.

```sh
MVP_TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/yuva-mvp-rehearsal.XXXXXX")"
chmod 700 "$MVP_TMP_ROOT"
PAYLOAD="$MVP_TMP_ROOT/payload-v1"
MANIFEST="$MVP_TMP_ROOT/release-v1.manifest.json"
INSTALL_ROOT="$MVP_TMP_ROOT/install-root"
DATA_ROOT="$MVP_TMP_ROOT/data-root"
SCRATCH_ROOT="$MVP_TMP_ROOT/restore-scratch"
mkdir -m 700 "$PAYLOAD" "$DATA_ROOT" "$SCRATCH_ROOT"
```

`INSTALL_ROOT` ilk install'da henüz oluşturulmamış kalmalıdır. `DATA_ROOT` boş da olsa gerçek, owner-only dizin olmalıdır. Bu provada canlı `~/yuva` yerine mutlaka `$DATA_ROOT` kullanın. Temporary root oluşturulamadıysa, path symlink/önceden var olan hedefe çözülüyorsa veya root'ların ayrılığı belirsizse durun.

### 2. Temiz source commit'inden payload ve manifest üret

```sh
SOURCE_REPO="/absolute/path/to/reviewed-clean-source"
RELEASE_COMMIT="<reviewed-full-commit>"
git -C "$SOURCE_REPO" status --porcelain
test "$(git -C "$SOURCE_REPO" rev-parse HEAD)" = "$RELEASE_COMMIT"
git -C "$SOURCE_REPO" archive --format=tar "$RELEASE_COMMIT" \
  | tar -xf - -C "$PAYLOAD"
python3 release_manifest.py create \
  --repo "$SOURCE_REPO" \
  --payload "$PAYLOAD" \
  --repository-id "<operator-approved-canonical-repository-id>" \
  --output "$MANIFEST"
```

İlk komut boş çıktı vermeli; commit tam ve incelenmiş olmalı. `create` sonucu tek başına release eligible veya trusted demek değildir. Manifest canonical inventory, commit/tree ve payload dosyalarını bağlar; dirty/unknown source uygunluk kazanmaz. Manifest payload ağacının dışında tutulur ve `O_EXCL` ile var olan dosyanın üstüne yazılmaz.

### 3. Manifest pin'ini ayrı kökten al ve offline verify et

Gerçek release akışında pin'i bağımsız kabul kaydından alın. Aşağıdaki placeholder'ı custody kanalından alınan 64 küçük harfli hex değerle doldurun:

```sh
TRUSTED_MANIFEST_SHA256="<independently-custodied-64-lowercase-hex-pin>"
python3 release_manifest.py verify \
  --payload "$PAYLOAD" \
  --manifest "$MANIFEST" \
  --source-repo "$SOURCE_REPO" \
  --trusted-manifest-sha256 "$TRUSTED_MANIFEST_SHA256"
```

Pin yok, bozuk, yanlış release'e ait veya eşleşmiyorsa install'a geçmeyin. Pin'i manifestin içinden/yanından yeniden üretip trusted diye adlandırmayın. Salt temp rehearsal için pin'i aynı temp manifestten hesaplamak yalnız test girdisi üretir ve dış güven kanıtı değildir.

### 4. Explicit-root install yap ve pointer'ları incele

```sh
python3 release_installer.py install \
  --install-root "$INSTALL_ROOT" \
  --data-root "$DATA_ROOT" \
  --payload "$PAYLOAD" \
  --manifest "$MANIFEST" \
  --source-repo "$SOURCE_REPO" \
  --trusted-manifest-sha256 "$TRUSTED_MANIFEST_SHA256"
readlink "$INSTALL_ROOT/current"
readlink -f "$INSTALL_ROOT/current"
```

Installer pin/source/payload'ı kurulumdan önce ve kopyalanmış staging ağacında yeniden doğrular; immutable release'i no-replace rename ile yayımlar ve `current` pointer'ını atomik günceller. `DATA_ROOT`'a yazmaz. Kurulu `current` tam beklenen release ID'ye gitmeli; `releases/` ağacı read-only olmalı. Belirsiz durability/commit sonucu, yanlış target veya yarım `.staging-*` durumunda kör tekrar/pointer değişimi yapmayın; önce exact path ve receipt'i salt okunur inceleyip ayrı kurtarma kararını izleyin.

Kurulu payload/manifest/source/pin'i offline tekrar kontrol etmek için:

```sh
python3 release_manifest.py verify \
  --payload "$INSTALL_ROOT/current" \
  --manifest "$MANIFEST" \
  --source-repo "$SOURCE_REPO" \
  --trusted-manifest-sha256 "$TRUSTED_MANIFEST_SHA256"
```

Bu çıktı, çalışan panel process'inin bu dosyalardan geldiğini, `PATH`'in/current unit'in aynı release'e baktığını veya gerçek data root'unu kanıtlamaz. Release acceptance fixture'daki `--canary-readonly` yalnız üretilmiş sentetik fixture programlarının argümanıdır; kurulu gerçek `bin/yuva` için canary komutu varsaymayın. Gerçek runtime doğrulaması ayrı salt-okunur host/process envanteridir.

### 5. İkinci sürüm ve rollback provası

İkinci seçilmiş release için yeni payload/manifest/pin ve aynı izole install/data root'u hazırlayın; var olan manifesti veya release ID'yi overwrite etmeyin. İkinci install `current`'ı v2'ye, `previous`'ı önceki release'e yönlendirir. Rollback hedefi v1 ise temiz v1 source checkout'u ve v1 pin'i kullanın:

```sh
SOURCE_V1="/absolute/path/to/clean-source-at-v1-commit"
PIN_V1="<independently-custodied-v1-manifest-pin>"
python3 release_installer.py rollback \
  --install-root "$INSTALL_ROOT" \
  --data-root "$DATA_ROOT" \
  --source-repo "$SOURCE_V1" \
  --trusted-manifest-sha256 "$PIN_V1"
readlink "$INSTALL_ROOT/current"
readlink "$INSTALL_ROOT/previous"
```

Rollback yalnız kod pointer'ını değiştirir; veri restore etmez, PATH/unit güncellemez, servisi durdurup başlatmaz ve açık process'leri yeni koda geçirmez. Eski/yeni schema uyumu ve writer'ların durması ayrı kapıdır. Sonuç belirsizse #604 sırasını izleyin; kör retry veya backup restore yapmayın.

### 6. Backup/restore ve temizlik sınırı

Bu repository'de `backup_verify.py` verify ve yeni private scratch'e `restore-check` sağlar; genel amaçlı backup üretim komutu bu görev kapsamındaki araçlarda yoktur. Gerçek backup'ı yalnız onaylı ayrı backup prosedürü ve bakım penceresinde üretin. Arşivi etkin data root dışında doğrulayın; gerekiyorsa aynı temporary rehearsal içindeki yeni `$SCRATCH_ROOT`'a scratch restore-check yapın. Scratch restore-check live data'ya terfi veya active root üzerine restore izni değildir. Retention/`HOLD` artıkları mtime ile otomatik silinmez.

`release_acceptance.py fixture` temporary root'u kendi context'iyle temizleyip yokluğunu doğrular. Elle açtığınız `$MVP_TMP_ROOT` için sadece onu yarattığınızdan ve hiçbir path'in dışarı symlink olmadığından emin olduktan sonra o exact disposable root'u temizleyin; host install root, home data root, backup veya çalışan release dizinine genel cleanup uygulamayın. Temizlik/cleanup sonucu da rehearsal notuna yazılmalıdır.

## Canlı hosta geçmeden önce NO-GO kapıları

Temiz temporary install başarılı olsa bile gerçek yerel MVP kurulumu için aşağıdakilerin tümü bağımsız kanıt ister:

- Temiz canonical source + manifest/payload hash'leri ve release dışından sağlanmış pin custody'si.
- Install root, `current`, PATH CLI, kurulu user unit, çalışan process executable/cwd ve panel kaynaklarının aynı immutable release'e eşleşmesi.
- Tek kanonik writer; eski/dev/restore CLI, panel, automation ve elle çağrı girişlerinin yokluğu veya yazamayacağının kabulü.
- Release dışında gerçek `YUVA_DIR`; owner/mode, schema, backup authenticity sınırlaması, scratch restore-check ve rollback schema uyumu.
- GET/HTML snapshot erişim kararı (#574 varsayılan NO-GO), auth/bind/proxy/namespace ve loopback'e ulaşabilen istemci kapsamı.
- Actor/presence semantiği, provider/approval/dispatch'in kapalı olduğuna dair release/host kanıtı.

Bunlardan biri unknown/eksikse servis başlatmayın ve kullanıcı/worker trafiği açmayın. `fixture_decision: GO`, `host_rollout_decision: NO-GO` sonucunu değiştirmez.

## İlgili belgeler

- [#550 sentetik acceptance harness](release-acceptance-harness-550.md) ve [#609 cutover/rollback fixture](release-cutover-acceptance-609.md).
- [#542 manifest aracı](release-manifest-tool-542.md), [#543 installer/rollback sözleşmesi](release-installer-543.md), [#625 dış trust root kararı](release-manifest-pin-trust-root-625.md).
- [#576 Go/No-Go matrisi](local-mvp-release-go-no-go-matrix-576.md), [#604 operatör checklist'i](operator-acceptance-rollback-checklist-604.md), [#598 runtime envanteri](runtime-roots-inventory-598.md).
- [#544 backup verify/restore-check](backup-verify-restore-check-544.md), [#530 restore retention/`HOLD`](restore-check-retention-policy-530.md), [#574 snapshot veri minimizasyonu](panel-anonymous-snapshot-data-minimization-574.md).

Bu teslim bir runbook taslağıdır. Hiçbir komut bu görev kapsamında çalıştırılmadı; gerçek source/release/data root, backup, PATH/unit, servis, auth, process veya canlı Yuva verisi değiştirilmedi.
