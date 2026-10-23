# Yuva #689 — Temiz kaynak ağacından release adayına provenance kabul planı

**Tarih:** 2026-10-23
**Durum:** Yalnız uygulama/acceptance planı; Git, release veya host değiştirilmedi.
**Karar:** Dirty/untracked geliştirme ağacı doğrudan release adayı değildir. Bütün kapılar geçilene kadar host rollout **NO-GO**.

## Amaç ve mevcut araç sözleşmesi

Bu plan, incelenmiş bir Yuva kaynak sürümünden immutable payload ve manifest'e, oradan bağımsız custody'deki manifest digest pin'ine kadar provenance zincirini tanımlar. Release manifest aracı `HEAD^{commit}` ve `HEAD^{tree}` kimliklerini kaydeder; `git status --porcelain=v1 --untracked-files=all --ignore-submodules=none` ile dirty/untracked durumunu ve recursive submodule durumunu kontrol eder; payload dosya seti/içeriğini seçilen commit'in Git tree'siyle karşılaştırır. Commit tree'de submodule gitlink varsa mevcut araç payload doğrulamasını desteklemez. Manifest imzasızdır; aynı payload/install alanında bulunan receipt veya fixture'dan hesaplanan digest dış trust anchor değildir.

Bu plan `release_manifest.py`, `release_installer.py` veya hostu çalıştırmaz. Bir sonraki gerçek release için ilgili owner ayrı değişiklik/rollout onayı ve güvenli çalışma ortamını sağlamalıdır.

## Kabul sahipleri

| Rol | Kanıt/sorumluluk |
|---|---|
| Kaynak/release sahibi | Canonical repository ID, exact full commit/tree, branch/PR/review kararını ve release kapsamını onaylar; çalışma ağacından yalnız incelenmiş içeriğin taşındığını kaydeder. |
| Build/payload sorumlusu | Temiz kaynak worktree'yi, asset/build araç zincirini ve payload üretim kaydını sağlar; toolchain/dependency girdilerini sabitler. |
| Güvenlik/independent reviewer | Kaynak diff, asset listesi, submodule/build/secret riskleri ve manifest inventory'yi release sahibinden bağımsız inceler. |
| Pin custodian | Canonical manifest byte digest'ini payload/release/install alanı dışındaki bağımsız custody kaydına alır ve kontrollü kanalla kurulum operatörüne verir. |
| Install/host operatörü | Yalnız external pin ve exact source/payload/manifest üçlüsüyle offline verify/install adımlarını, başka bir GO kararı varsa yürütür. Bu görev operatör değil, plan üretir. |

## Sıralı kaynak → payload → pin kabulü

### 1. Kaynak ve değişiklik kapsamını sabitle

1. Canonical repository adres/ID'sini ve incelenmiş branch/PR/review kaydını belirt. Branch adı taşınabilir mutable bir gösterge olduğundan release kimliği exact full commit hash'i olmalıdır.
2. Başlangıç ref'ini ve hedef commit'i kaydet. Commit'in ebeveynleri ve dahil edilen commit/diff kapsamını reviewer onaylar; force-push/branch hareketi sonradan aynı release kimliğini değiştirmez, yeni commit yeni adaydır.
3. Release işi için ayrı disposable source worktree/checkout aç; geliştirme worktree'sinden elle dosya kopyalama yapma. Seçilen `HEAD^{commit}` ve `HEAD^{tree}` kayıtları tam object ID olmalı.
4. Worktree status'u staged, unstaged, untracked (ignored dahil envanter), submodule initialize/dirty state olarak ayır. Manifest aracı untracked ve submodule state'ini kontrol eder; ignored dosyalar `git status`'ta normalde görünmez, bu yüzden ignored asset/config/cache/secret envanteri ayrıca yapılır.
5. `git diff --binary`, staged diff, untracked dosya envanteri ve reviewer onayı release kapsamına eklenir. Temiz worktree için status boş olmalı; “bilerek eklenmedi” diye untracked/dirty değişiklik payload'a alınmaz.

**Ret:** Exact commit/tree, repository identity, diff onayı veya worktree clean değil/unknown ise dur. Değişikliği bu görevde commit etme, stash etme, discard etme veya başka branch'e taşıma yok.

### 2. Assets, generated output ve submodule politikası

- UI/CSS/JS/font/image/template/static dosyaları payload'da gerçekten dağıtılıyorsa commit/diff ve manifest inventory içinde açıkça görünür olmalı. Runtime'da ihtiyaç olup manifestte olmayan dosya release eksikliğidir; payload'a sessizce kopyalama kabul edilmez.
- Üretilen asset/build çıktıları için üretici script, pinned dependency/lockfile, runtime/toolchain sürümü, platform/locale/environment girdileri ve artifact digest'leri kaydedilmeli. Build aynı pinned source/toolchain ile tekrarlanabilir olmalı; iki üretimin çıktısı byte/metadata olarak karşılaştırılmalı veya neden deterministik olmadığını owner onaylamalı.
- Generated output commit'e giriyorsa commit'teki exact bytes source tree'nin parçası olarak doğrulanır; commit dışı generated file release için kabul edilmez. Build sırasında dış ağdan gelen mutable dependency veya sır içeren config payload'a sızmamalıdır.
- Git ignore/export-ignore durumları kontrol edilmeli. `git archive` ignored/untracked dosyaları kopyalamaz ve `.gitattributes export-ignore` içerikleri çıkarabilir; payload tam tree match olmadan eligible olmaz.
- Submodule varsa her nested submodule commit/URL/init/clean state ve custody ayrıca sabitlenmelidir. Mevcut `release_manifest.py` commit tree'deki mode `160000` gitlink'i reddeder; araç açıkça destekleyecek şekilde revize edilip kabul edilmedikçe submodule içeriğini elle ekleyerek eşleşme iddiası kurulmaz.
- Credentials, local `.env`, test fixture secrets, caches, editor metadata, untracked logs, temp files veya kişisel data release'e girmez. Manifest içerik hash'i gizlilik kontrolü değildir; payload listesi reviewer tarafından dosya bazında gözden geçirilir.

**Ret:** Build tekrarlanamıyor/versiyonu belirsiz, gerekli asset ile manifest inventory uyuşmuyor, untracked/ignored/generated dosya açıklanamıyor, secret tarama kapsamı belirsiz veya araç submodule'ü desteklemiyorsa bu aday durur.

### 3. Temiz checkout/payload üretimi

1. Temiz ayrı worktree'yi exact approved full commit'te checkout et; source path'in gerçek Git worktree root olduğu doğrulanır. Manifest aracı dirty status, submodule state, commit ve tree'yi ayrıca okur.
2. Payload'ı aynı exact commit ve belgelenmiş build adımlarıyla ayrı scratch dizinine üret. Payload, source repo, manifest çıktısı, install root ve data root ayrı, non-nested hedefler olmalıdır.
3. Build sırasında input ref veya dependency değişirse scratch payload'ı at; eski manifest/pin'i sürdürme. Her yeni payload/manifest yeni candidate ID/digest alır.
4. Manifest payload dışına canonical byte serialization ile yazılır. Manifest kaydı full release ID'yi commit + payload digest ile bağlamalı; `release_eligible=false`, dirty source veya `payload_matches_source=false` varsa inceleme/kurulum için release onayı yoktur.

### 4. Payload/manifest doğrulama ve bağımsız pin

- Offline verifier exact source checkout, manifest, payload ve full IDs üzerinde kanonik manifest schema, file set, path/type/mode/hash, source commit/tree ve payload tree match'i kontrol eder.
- `manifest_sha256` canonical manifest **byte** dizisinin digest'idir. Release owner digest'i aldığı kaynak/cihazı, time, exact release ID/commit ve digest'i operatör custody kaydına yazar; pin release payload'ı, installer receipt'i veya yan yana `.sha256` dosyasından tekrar türetilmez.
- Pin custody'si release/install alanından bağımsız olmalı ve aynı write authority ile değiştirilememelidir. Aynı hostta farklı path/owner-only mode tek başına bağımsız trust anchor değildir. Pin custodian ve install operatörü teslimi doğrular.
- Kurulum/rollback ancak bütün exact kimlikler ve external pin eşleşirse ayrıca yetkilendirilebilir. Pin uyuşmazlığı, eksik pin, source tree drift, payload drift, uncertain output veya wrong release ID'de fail-closed dur.

`verified_release` manifest/payload/source/pin doğrulamasıdır. Çalışan panel/CLI'nin bunu kullandığını, host UID/paths/proxy/writer/backup/schema veya browser access sınırını doğrulamaz; host GO değildir.

### 5. Artefact ve provenance paketi

Release evidence index en az şunları taşımalı; secret veya local path içeriği gereksiz yere kopyalanmamalıdır:

- Repo canonical ID, approved branch/PR/change reference, exact commit/tree ve source worktree status/submodule sonucu.
- Reviewer diff kapsamı, dosya/asset inventory kararı, generated build toolchain/dependency/command/environment özetleri (secret'sız), reproducibility karşılaştırması.
- Payload file list/type/mode/size/digest özeti; payload overall digest; `release_id`; manifest canonical byte SHA-256.
- Pin custodian, bağımsız custody alanının türü (secret/path disclosure olmadan), pin release ID ile eşleşme kontrolü, aktarım zamanı ve install operatörü acknowledgment.
- Verifier sürümü/digest'i, sonucu, kullanılan exact source/payload/manifest ID'leri ve rejected/unknown gate'ler.
- Ayrı host/cutover/backup/rollback kanıtlarının referansları; fixture raporları yalnız fixture diye etiketlenmeli.

## Worktree farkı ve dirty tree değerlendirmesi

Bir worktree'de `HEAD` commit/tree temiz olsa bile başka worktree'deki untracked/diff dosyalar release'e eklenemez. Kaynak path, `git rev-parse --show-toplevel` ile manifest'teki source root arasında uyuşmalıdır. Candidate worktree disposable olsa da onun file content'i yalnız onaylı commit tree ve onaylı build output listesine göre seçilir.

Dirty build ağacındaki değişiklik önemliyse önce normal code review/değişiklik yönetimiyle committed source haline getirilip yeni full commit üretilir. Ardından fresh clean worktree, yeni payload, yeni manifest ve yeni dış pin baştan alınır. Mevcut dirty tree'yi manifestle “temiz” gösterme, önceki pin'i yeni bytes için tekrar kullanma veya yalnız `release_eligible` alanını değiştirme yasaktır.

## Stop/NO-GO matrisi

| Kontrol | PASS için kanıt | FAIL/UNKNOWN sonucu |
|---|---|---|
| Source identity | Canonical repo ID + full approved commit/tree + exact change review | Adayı dondurma yok; payload üretimini durdur |
| Worktree purity | Staged/unstaged/untracked/submodule status temiz; ignored/local inputs ayrı incelendi | Dirty/untracked/mismatch içeriği release'e alma yok |
| Build/assets | Pinned toolchain/deps; gerekli runtime asset listesi ve deterministic output/hash equality | Manifest/payload oluşturma veya pin alma yok |
| Submodules | Yok veya desteklenen, separately pinned/reviewed contract | Mevcut verifier gitlink reddinde NO-GO |
| Payload ↔ source tree | Exact file set, path/type/mode/content hash match | `payload_matches_source` false/unknown: release ineligible |
| Manifest/pin | Canonical manifest bytes, full release ID ve bağımsız custody digest match | Install/rollback yok; manifest yanındaki digest trust root olmaz |
| Host/runtime | PATH/unit/process/data-root/access/writer evidence separately accepted | `verified_release` olsa bile host rollout NO-GO |

## Bu görevde yapılmayanlar

Bu plan için Git worktree/branch/commit değiştirilmedi; dirty files stage/stash/clean edilmedi; payload veya manifest üretilmedi; build/test yapılmadı; pin alınmadı; release install/rollback, host taraması veya servis kontrolü yapılmadı. Plan bir release kararı veya commit/push/kurulum yetkisi değildir.

## Kaynaklar

- `release_manifest.py` — `_source_state()`, `_git_tree_files()`, `_compare_payload_to_tree()`, `verify_manifest()`.
- `docs/release-manifest-tool-542.md` — canonical manifest/inventory sözleşmesi.
- `docs/release-manifest-pin-trust-root-625.md` — dış pin custody'si ve trust-root sınırı.
- `docs/release-installer-543.md` — explicit-root install/rollback ve source/payload doğrulaması.
- `docs/local-mvp-clean-root-install-rehearsal-628.md` — disposable rehearsal'ın host NO-GO sınırı.
- `docs/local-mvp-release-go-no-go-matrix-576.md`, `docs/release-operator-decision-form-617.md` — host/cutover/owner kabul kapıları.
