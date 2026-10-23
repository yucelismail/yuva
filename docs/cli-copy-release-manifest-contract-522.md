# Yuva #522 — CLI kopyaları için sürüm ve manifest sözleşmesi

**Durum:** Önerilen sözleşme; uygulama veya release seçimi değildir.
**Kapsam:** #485/#486/#508 ve #515 bulgularına göre CLI kopyalarının kaynağını, tam payload'ını ve release uygunluğunu ayırt etme. Bu not dışında dosya, CLI kopyası, symlink, servis veya veri değiştirilmedi; test/runtime/deployment yapılmadı.

## Karar özeti

Bir CLI kopyasının kimliği üç ayrı bilgiyi birlikte taşımalıdır:

1. **Kaynak kimliği:** kanonik Git deposunun kimliği, tam commit ve tree hash'i.
2. **Çalışma ağacı durumu:** kaynak, tam seçilmiş commit'ten mi üretildi; staged, unstaged, untracked ve submodule değişiklikleri var mı?
3. **Kurulu payload kimliği:** release içindeki CLI, panel ve diğer dağıtılan dosyaların SHA-256 listesi ile bu listenin özeti.

Sadece commit hash'i, branch/tag adı, dosya adı veya sürüm metni çalışan kopyanın baytlarını kanıtlamaz. Sadece SHA-256 da dosyanın hangi kaynaktan ve hangi release sürecinden geldiğini kanıtlamaz. Release kabulü, temiz kaynak commit'i ile kurulu payload manifesti ve güvenilir manifest imzası ya da harici digest bağını doğrular.

**Kirli veya kaynağı belirlenemeyen ağaç release değildir.** Böyle bir ağaç envanter için development/unknown olarak hashlenebilir; release_eligible=false kalır. Yerel değişiklikleri sessizce bırakıp commit kimliğini release kimliği gibi göstermeyiz.

## Bulgular ve sınırlar

- #515 dört bağımsız CLI kopyası ve SHA-256 değerlerini raporladı: ~/yuva/bin/yuva, ~/yuva-v2/bin/yuva, ~/yuva-dev/bin/yuva ve ~/yuva-ui-dev/bin/yuva. ~/.local/bin/yuva, rapordaki statik PATH çözümünde v2 dosyasına symlink'tir; ayrı beşinci kopya değildir. #515/#517 etkin çalışan panel sürecini doğrulanmış kabul etmedi.
- #515 dört kopyada --version arayüzü görmedi; eski/dev ile v2/ui-dev arasında CLI özellik ve presence davranış farkları var. Bu nedenle kopya eşitliği dosya adına ya da komutun çalışmasına göre çıkarılamaz.
- #515 v2 çalışma ağacının kirli ve çok sayıda untracked dosyalı olduğunu, yuva-dev çalışma ağacında da yerel değişiklik bulunduğunu kaydetti. Bunlardan release çıkarılmamalı; çalışma kopyasının hash'i, ilgili Git commit'in temiz artifact'ı sayılmaz.
- #486 tek kanonik kaynak, seçilmiş commit, değiştirilmeyen sürümlü release, current işaretçisi ve koddan ayrı YUVA_DIR önerir. #508 kaynak temizliği, commit/tree, kurulu CLI/panel hashleri ve rollback hedefi için kabul kapıları koyar. Bu sözleşme henüz uygulanmış değildir; kanonik repo ve kurulu release sahibi operatörce belirlenmelidir.
- CLI ve panel veri kökünü kod kökünden ayrı seçer: YUVA_DIR yoksa süreç kendi $HOME/yuva yolunu varsayar. Manifest, veri kökünü release payload'ının parçası yapmaz ve symlink/rollback'in veriyi taşıdığı iddiasını üretmez.

#515'in dosya hash snapshot'ı:

| Kopya | SHA-256 (bin/yuva) | Manifest sözleşmesinin ayırt etmesi gereken durum |
| --- | --- | --- |
| ~/yuva/bin/yuva | 90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05 | Eski kopya; #515'te bu ağaç Git deposu değildi, commit provenance yok. |
| ~/yuva-v2/bin/yuva | 812e7fc4862a894c9edbe9a0d612c8733012823740605b527947a4a8df678b5a | Çalışma ağacı kirliydi; bu dosya hash'i tek başına release kimliği değildir. |
| ~/yuva-dev/bin/yuva | 11933ae13e8af951d6ab3aa9f0ccef1f8745df4120060a8ffc00ebb43db8fa5e | Geliştirme kopyası ve yerel değişikliği vardı; release uygunluğu yok. |
| ~/yuva-ui-dev/bin/yuva | 6de3adda675aed0caf9e9cabde96fcd6c5ef44178dc3241bd203f5e55e00cddf | Linked worktree; CLI commit tabanıyla eşleşse de preview untracked dosyaları çalışma ağacını kirli bırakıyordu. |

Bu değerler #515'in 2026-10-23 tarihli statik envanteridir; yeni hash ölçümü değildir. Hash'lerin farklı olması sürüm/provenance kanıtı, aynı olması da tam release eşitliği kanıtı sayılmaz. #515'in raporladığı ~/.local/bin/yuva → yuva-v2/bin/yuva bağlantısı aynı dosya hash'ini seçer; manifest kopyası oluşturmaz.

## Manifest biçimi

Önerilen format sürümlü, makinece okunabilir JSON'dur. Aşağıdaki örnekteki yer tutucular gerçek digest değildir:

    {
      "manifest_schema": "yuva-release-manifest/v1",
      "product": "yuva",
      "release_id": "<full-commit>-<payload-digest-prefix>",
      "release_eligible": true,
      "source": {
        "repository_id": "<canonical-repository-identity>",
        "commit": "<full-git-commit-id>",
        "tree": "<full-git-tree-id>",
        "ref": "<tag-or-branch-for-information>",
        "worktree_state": "clean",
        "submodules": []
      },
      "artifact": {
        "format": "directory-tree/v1",
        "payload_digest": "sha256:<digest>",
        "files": [
          {
            "path": "bin/yuva",
            "type": "regular",
            "mode": "0755",
            "size": 12345,
            "sha256": "<file-digest>"
          },
          {
            "path": "panel/server.py",
            "type": "regular",
            "mode": "0644",
            "size": 67890,
            "sha256": "<file-digest>"
          }
        ]
      },
      "data_contract": {
        "data_root_in_artifact": false,
        "yuva_dir": "configured-separately",
        "schema_compatibility": "<declared-read-write-compatibility-id>"
      },
      "created_at": "<UTC timestamp>",
      "builder": "<release-process-id>"
    }

Alanların anlamları:

- repository_id makineye özgü mutlak yol değil, operatörün belirlediği kanonik depo kimliğidir. commit ve tree tam Git nesne kimliği olmalıdır; kısa hash ve hareketli branch tek başına yeterli değildir. ref yalnız açıklayıcı metadadır.
- worktree_state=clean, release girdisinin seçilmiş commit ağacıyla birebir olduğunu belirtir. Git status porcelain çıktısında staged/unstaged/untracked/deleted değişikliği, çözülmemiş merge veya pinned olmayan/değişmiş submodule varsa release_eligible=true olamaz. Ignore edilmiş yerel dosyalar payload girdisi olamaz; her payload path'i seçilmiş commit veya açıkça pinlenmiş bağımlılık ağacına ait olmalıdır. Seçilmiş kanonik checkout kirliyse commit nesnesinden paket üretmek bu kapıyı atlamaz.
- artifact.files payload'a dahil her regular file, symlink, executable ve dağıtım girdisini listeler. Regular file için hash ve boyut; symlink için literal hedef ve tür kaydı kullanılır. Dizin dışına kaçan, mutlak veya release dışına bağlanan symlink kabul edilmez. Sıra kanonik path sırasıdır; duplicate path ve manifestte olmayan payload dosyası ret sebebidir.
- payload_digest, manifest.json ve imza dosyası hariç dosya kayıtlarının kanonik serileştirmesi üzerinden hesaplanır; böylece manifestin kendisiyle döngü oluşmaz. Girdi yolları release köküne göre POSIX relative path'tir; "."/".." bileşenleri, NUL, absolute path, duplicate path ve UTF-8 NFC'ye normalize edilince çakışan adlar reddedilir. Kayıtlar normalize path'in UTF-8 byte sırasına göre dizilir. Her kayıt beş sütunlu olur: path, type, mode, size, sha256. Sütunlar arasında 0x00 byte, kayıt sonunda LF kullanılır. Regular file için mode dört haneli octal, size decimal byte sayısı ve sha256 küçük harf hex dosya digest'idir. Symlink için mode sütunu boş, size literal target byte sayısı, sha256 literal target byte'larının digest'idir. Kayıtların birleştirilmiş byte dizisinin SHA-256 değeri payload_digest olur. Manifestin kendisi ayrıca hashlenip imzalanır. Aynı girdiler aynı digest üretmelidir.
- data_contract yalnız veri uyumluluk sözleşmesini tanımlar. Gerçek YUVA_DIR, kullanıcı dizini, görev/mesaj verisi, secret, credential veya auth store içeriği release manifestine yazılmaz.
- Release bütünlüğü manifest imzası veya release deposu dışında pinlenen trusted manifest digest'iyle doğrulanır. İmza anahtarı/dağıtımı için henüz işletim kararı yoktur; imzasız hash listesi yalnız accidental drift tespitidir, provenance/authenticity kanıtı değildir.

Manifestte bin/yuva, panel/server.py, panel/ui.html, örnek unit dosyası ve dağıtılan tüm bağımlılık/doküman dosyaları bulunur. Zorunlu dosya listesi release policy ile sabitlenir; dosya atlama veya fazladan executable sessizce kabul edilmez. Manifestin içine kendi hash'i konmaz.

## Sürüm ve kopya sınıflandırması

| Tür | Asgari kayıt | release_eligible | Kullanım |
| --- | --- | --- | --- |
| **Verified release** | Kanonik repo + tam commit/tree, temiz çalışma ağacı, pinned submodule, payload dosya listesi/digest, doğrulanmış imza veya dış digest | true | releases/<release_id> altında değiştirilmeyen kurulu artifact; current bunun birine işaret eder. |
| **Dirty development tree** | Bulunabilen commit/tree; staged/unstaged/untracked durumu; seçilen dosyaların hash'i; dirty=true | false | Yalnız geliştirme/inceleme envanteri. Release veya rollback hedefi diye adlandırılamaz. |
| **Commit'i bilinmeyen kopya** | Tam dosya hashleri; source.commit=null, source.tree=null, worktree_state=unknown | false | Eski/backup/restore-check kopyasını ayırt etme. Hash benzerliği Git provenance oluşturmaz. |
| **Manifesti eksik/değişmiş kurulum** | Kurulu dosya hashleri ile manifest farkları | false | current hedefi veya rollback hedefi olarak kabul edilmez; incelemeye alınır. |

Seçilmiş kanonik kaynak çalışma ağacı kirliyse release pipeline kapanır; commit nesnesinden artifact üretmek bu kirli-kaynak kapısını atlamaz (#486). Önce operatörün belirlediği kanonik kaynak temiz ve sabit commit ile eşleşir hale gelmelidir. Release girdisi yalnız bu commit ağacından üretilir; başka kopyadan dosya seçmek, dirty tree içeriğini commit hash'ine mal etmek veya ignored/untracked girdiyi pakete eklemek yasaktır.

İleriye dönük yuva --version --json arayüzü önerilir; mevcut kopyalarda böyle bir seçenek yoktur ve bu görevde eklenmemiştir. Uygulanırsa manifest_schema, release_id, commit/tree, worktree_state, payload_digest ve release_eligible döndürür. Çıktı kendini tanıtır; tek başına güven kanıtı değildir. Kurulu dosyaların imza/hash doğrulaması ayrı verifier veya deployment acceptance tarafından yapılır.

## Kurulum ve geçiş kabulü

1. **Kanonik girdiyi seç:** repository identity, tam commit/tree, temiz status, pinned submodule ve release owner kayda geçer. Hangi mevcut checkout'un kanonik kaynak olduğu doğrulanmadığından bu not bir repo seçmez.
2. **Staging'i ayrı tut:** commit artifact'ı <INSTALL_ROOT>/releases/.staging-<id> içine açılır. Kaynak checkout veya mevcut release üzerine yazılmaz. Hash listesi staging payload'ından üretilir; manifest imzalanır veya digest'i dışarıda pinlenir.
3. **Doğrula:** source commit/tree ve worktree temizliği; dosya listesinin tamlığı, mode/type/literal symlink, SHA-256, payload digest ve manifest imzası doğrulanır. Release manifesti yanında uygulanacak CLI ve panel dosyalarının hashleri bağımsızca kayda geçer.
4. **Dondur ve kimlik ver:** başarılı aday aynı dosya sisteminde releases/<release_id> olarak atomik rename ile sabitlenir. Dizin mevcutsa üzerine yazılmaz; release ID/payload çakışması reddedilir. release_id tam commit ve payload digest'i bağlar, böylece aynı commit'ten farklı artifact'lar aynı sürüm gibi görünmez.
5. **Ayrı etkin işaretçi:** current yalnız doğrulanmış release dizinine işaret eder. <USER_BIN>/yuva → <INSTALL_ROOT>/current/bin/yuva; panel unit'i de aynı current/panel/server.py kullanır. CLI ve panel için YUVA_DIR ayrıca, aynı mutlak veri köküne ayarlanır. Bu aşamaların hiçbiri veri kökünü taşımaz veya kod ağacına dahil etmez.
6. **Geçiş öncesi kabul:** PATH'in seçtiği gerçek hedef, panel unit ExecStart hedefi ve etkin panel süreci birbirinden ayrı kaydedilir. Etkin sürece dair runtime kanıt yoksa unknown kalır. Eski yazarların yokluğu, ortak YUVA_DIR, şema uyumu ve doğrulanmış yedek ayrıca kabul edilir (#508); manifest tek başına bunları kanıtlamaz.
7. **Geçiş sonrası kabul:** current hedefinin manifestteki tam release ID'ye ve payload digest'e çözülmesi; CLI/panel ana dosya hashleri; data-root config uyumu; eski release'in korunması; canary read kabulü; writer tekilliği kaydedilir. Yalnız komutun başarıyla başlaması sürüm kanıtı değildir.

## Geri alma sözleşmesi

- Önceki release dizini, manifesti, imzası/dış digest'i ve file hashleri korunur. Rollback hedefi isim/tag ile değil tam release_id ile seçilir.
- Eski ve yeni kodun aynı veri köküne eşzamanlı yazması engellenmeden işaretçi çevrilmez. Önceden açılmış CLI/panel süreçleri symlink değişiminde kod değiştirmez; writer quiescence ve etkin kod doğrulaması ayrı kapıdır.
- Rollback yalnız current işaretçisini önceki doğrulanmış release'e alır. Release dosyalarını kopyalayıp değiştirmez ve veriyi otomatik restore etmez.
- Önceki manifest/hash doğrulanamıyor, eski kod yeni yazım şemasını okuyamıyor veya ortak data root belirsizse aynı veri köküne rollback kabul edilmez. İleri düzeltme ya da ayrı, doğrulanmış backup restore kararı gerekir. Backup restore'u kod rollback'inden bağımsızdır.
- Başarısız/yarım staging release current yapılmaz; release dizinleri release_id çakışmasında overwrite edilmez. Belirsiz atomik işaretçi değişiminde önce gerçek hedef ve manifest okunur, kör tekrar yapılmaz.

## Kabul ölçütleri

| # | Kabul ölçütü | Kanıt |
|---|---|---|
| M1 | Tek kanonik repository identity ve tam commit/tree seçili; commit kaynağı çalışma ağacından ayrıştırılmış | Git source inventory ve release kaydı; kanonik repo kararı ayrıca onaylı |
| M2 | Seçilmiş kanonik source worktree dirty/staged/untracked/deleted/unresolved ise release üretimi kapanıyor; submodule pinned/clean ve payload yalnız seçilmiş commit'ten geliyor | Release pipeline kontrolü ve gelecek test: her dirty sınıfı release_eligible=false; kanonik kaynak temiz checkout'ta ayrı case |
| M3 | Manifest her payload path/type/mode/size/hash'i, required file set'i ve symlink literal target'larını kapsıyor | Staging dosya envanteri ile manifest birebir karşılaştırma; eksik/extra/duplicate/escape negatifi |
| M4 | Manifest payload digest'i döngüsüz, kanonik ve deterministik; imza/dış digest manifest bütünlüğünü doğruluyor | Aynı payload için aynı digest; tek byte/mode/path farkında digest değişimi; imza yok/yanlış anahtar reddi |
| M5 | release_id source commit/tree ile payload digest'i ayırt ediyor; aynı commit farklı payload ise farklı ID veya red | Aynı commit farklı artifact senaryosu ve ID çakışma reddi; kısa digest prefix çakışırsa prefix uzatılır, var olan dizinin üstüne yazılmaz |
| M6 | --version çıktısı varsa manifestteki iddiaları gösteriyor fakat integrity/provenance kanıtı diye sunulmuyor; henüz uygulanmış varsayılmıyor | CLI contract test; ayrı verifier hash/signature doğrulama kanıtı |
| M7 | Installed current CLI ve panel aynı release ID'ye çözümleniyor; file hashler manifestle uyuyor | Salt-okunur symlink/manifest/hash acceptance; etkin süreç için ayrıca süreç kanıtı, yoksa unknown |
| M8 | Manifest ve kod release ağacında; YUVA_DIR ayrı ve CLI/panel aynı veri kökünü kullanıyor; data root dışarıda | Config/realpath incelemesi; manifestte gerçek kullanıcı veri yolu/secret yok |
| M9 | Rollback hedefi önceki imzalı/tam hashli release; writerlar durmuş, veri şeması uyumlu, veri restore otomatik değil | Geri dönüş checklist'i; şema uyumsuzluğu ve eksik manifest negatif kapısı |
| M10 | Eski/unknown kopya, kirli çalışma ağacı, eksik manifest veya hash drift current/rollback hedefi kabul edilmiyor | Eski dört CLI ve backup/unknown kopya fixture envanteri; eksik/yanlış manifest/hash negatifleri |

Bu kabul testleri ve verifier uygulaması bu görev kapsamında çalıştırılmaz. #508'deki canlı writer, etkin panel süreci, veri uyumu ve backup kontrolleri release manifestinin dışındaki ayrı kurulum kapıları olarak kalır.

## Açık kararlar ve sınırlamalar

1. Kanonik Git deposu, release maintainer ve güvenilir kaynak seçimi operatör tarafından belirlenmeli; #515'in PATH'te görülen v2 kopyası otomatik kanonik kaynak sayılmaz.
2. Manifest imza anahtarı, güvenilir verifier ve imza dağıtım kanalı belirlenmeli. Bunlar olmadan hash listesi provenance değil, yalnız içerik karşılaştırmasıdır.
3. Çözüldü: `yuva-data-contract/v1` tanımı ve rollback sınırı `docs/data-schema-compatibility-549.md` içindedir. Manifest bu kimliği taşır; acceptance harness bilinmeyen/eksik kimliği NO-GO sayar.
4. Makinece okunur --version arayüzü istenip istenmediği ve uyumluluk sözleşmesi ayrıca uygulanmalıdır; mevcut CLI'da yoktur.
5. Build sistemi, zorunlu payload file list'i, supported platform/Python sürümü ve deterministic artifact beklentisi seçilmelidir.
6. current işaretçisinin release ID'si ile panel unit/CLI başlangıç doğrulama raporunun nereye yazılacağı kararlaştırılmalı; bunu runtime'a bağlamak ayrı uygulama/deployment görevidir.

## Kaynaklar

- docs/local-cli-copy-version-map-485.md: PATH, dört CLI kopyası, kod/data root ayrımı ve davranış farkları.
- docs/yuva-cli-update-single-source-plan-486.md: kanonik kaynak, temiz commit, sürümlü release, manifest/hash, current, ortak YUVA_DIR ve rollback akışı.
- docs/yuva-cli-copy-cutover-acceptance-508.md: source/release/hash kabulü, panel/CLI/data-root eşleşmesi, writer tekilliği ve rollback şartları.
- Yuva #515/#517 görev teslim kayıtları (<YUVA_DATA_ROOT>/gorevler.json): dört CLI hashleri, kirli worktree, --version yokluğu, etkin süreç belirsizliği ve unit/sample farkları. #517'nin ilk runtime sorgularına dair sonuçları revizyonda geri çekilmiştir; bu not yalnız statik bulgularını kullanır.
- README.md hızlı başlangıç, güncel tek current CLI symlink sözleşmesini örnekler; release manifest ve sürüm arayüzü henüz uygulanmış anlamına gelmez.
