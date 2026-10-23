# Release manifest pin'i için dış güven kökü kararı ve fixture akışı (#625)

**Tarih:** 2026-10-23
**Karar:** Yerel MVP'de verifier'a, release içeriğinden ve kurulum alanından bağımsız custody ile ulaştırılmış tam manifest SHA-256 pin'i sağlanır. Böyle bir kanal/custody gerçek operasyonda kurulup doğrulanana kadar release `verified` sayılamaz ve host rollout NO-GO kalır.
**Kapsam:** Bu karar mevcut unsigned manifest + caller-supplied pin sözleşmesini açıklar; imza sistemi, pin dağıtım servisi veya host root of trust kurmaz.

## Güven kökü ve karar

Manifest, payload dosyalarını ve source commit/tree bilgisini envanterler. Canonical manifest byte'larının SHA-256'sı manifesti ve içindeki inventory'yi bağlar. `release_manifest.py verify` pin'i manifestten, release dizininden veya yanındaki receipt'ten okumaz; caller'ın verdiği `--trusted-manifest-sha256` ile karşılaştırır. `release_installer.py` de aynı dış pini ister. Bu, **pin'i kimin ve hangi güvenilir süreçle sağladığı** sorusunu araçların dışında bırakır.

İlk tek-operatörlü, offline MVP için seçilen kök, release sorumlusunun bağımsız custody alanında tuttuğu digest kaydı ve onun kontrollü teslimidir. Kayıt release/payload/install alanı dışında ve aynı yazıcı süreçten bağımsız bir cihaz, medya ya da kimlik/yönetim alanında tutulmalıdır. Aynı hostta farklı path, owner-only mode, manifest yanındaki `.sha256`, installer'ın sakladığı manifest receipt'i veya fixture'ın ürettiği digest bağımsız güven kökü değildir. Bağımsız hedef/kanal yoksa verifier'ın içerik karşılaştırması yine yararlıdır; sonuç güvenilir release iddiasına yükseltilmez.

Bu model, verifier çağrısına ulaşan pin'in custody'si gerçekten sağlanmışsa manifest ve payload alanının tek başına değiştirilmesine karşı koruma verir. Aynı operatör hesabı/host ve pin kaydı birlikte ele geçirilirse saldırgan manifesti değiştirip yeni pin de sağlayabilir. Digest; yetkili kaynak seçimini, insan onayını, source tree'nin doğru olup olmadığını, çalışan process'in o release'i kullandığını, kurulum/cutover güvenliğini veya veri uyumluluğunu tek başına kanıtlamaz. Bunlar ayrı Go/No-Go kanıtlarıdır.

İmzalı manifest ya da harici immutable metadata store, çoklu operatör ve otomasyon ihtiyacı ortaya çıkınca yeniden değerlendirilebilir. İmzalı tasarımda private signing key ayrı custody/UID'de tutulmalı, verifier'ın public key'i bağımsız bir önceki güven kökünden provision edilmeli, key geçişi/rotation/revocation ve kayıp/compromise recovery tanımlanmalıdır. Aynı release hostunda üretilen ve doğrulanan imza yeni bir dış güven kökü yaratmaz. Immutable store seçeneğinde store administrator'ı, retention lock, recovery, silme ve veri konumu da tehdit modeline dahil edilir. Bu maliyetler ve kök dağıtım politikası kararlaştırılmadan imza/servis eklemek MVP için güven kanıtı değildir.

## Gerçek operasyonda pin akışı

1. Release sorumlusu kanonik repository ve tam commit'i seçer; temiz source, payload üretimi ve release manifesti oluşturma adımlarını kaydeder. Manifest byte'ları sabitlendikten sonra tam SHA-256 hesaplanır.
2. Release ID, commit, manifest byte digest'i ve gerekli kabul metadata'sı release içeriği/install root dışındaki operatör custody kaydına alınır. Kayıt ayrı hedefe kontrollü kanalla aktarılır; hedefin erişim sahibi ve teslim zamanı izlenebilir olmalıdır. Aynı host/UID üzerinde her iki kopyayı da değiştirebilen alan bu koşulu karşılamaz.
3. Kurulum operatörü digest'i bu dış kayıttan alır, hedef manifest/release ID ile eşleştirir ve `release_manifest.py verify` veya installer'a `--trusted-manifest-sha256` ile açıkça geçirir. Pin eksik, bozuk, yanlış release'e ait veya mismatch ise işlem fail-closed durur; manifest içinden/yanındaki dosyadan yeni pin türetilerek devam edilmez.
4. Manifest/source/payload sonucu `verified_release` olsa bile cutover kararı ayrı kanıt ister: install root ve immutable release, `current`/`previous`, etkin CLI/panel yolları ve süreç kimliği, veri kökü ayrımı, schema/backup/writer/canary kontrolleri. `verified_release` tek başına host rollout GO değildir.
5. Yeni release yeni tam release ID ve yeni manifest pin'i alır. Eski release pin'i üzerine yazılmaz; rollback için hedef sürümün kendi bağımsız pin'i ve tam kimliği geri çağrılır. Pin kaybında aynı manifestten yeniden hesaplama authenticity'yi geri getirmez.

## Sentetik fixture akışı

Fixture, byte/hash ve caller-pin sözleşmesini sınar; bağımsız operatör veya gerçek dış kanalın varlığını taklit ettiğini iddia etmez. Mevcut `release_acceptance.py fixture` ve `tests/test_release_acceptance.py` akışı şu sırayı izler:

1. `TemporaryDirectory` altında temiz sentetik Git kaynakları, payload'lar, manifestler, digest pin'leri, install root ve veri kökü kurulur. Gerçek repo/kurulum, kullanıcı verisi, servis veya port kullanılmaz.
2. Her fixture release'in manifest byte'larından expected digest hesaplanır; değer açıkça verifier/installer caller girdisi olarak verilir. Bu üretim ve tüketimin aynı fixture içindedir, dolayısıyla pin yalnızca **sentetik wiring testi**dir ve external trust anchor kanıtı değildir.
3. Positive case: temiz source commit/tree, canonical manifest, exact payload inventory ve fixture caller pin'i eşleşir; installer release'i scratch install root'a kurar. Kurulu dosyalar ve `current` tam release ID'ye göre tekrar incelenir.
4. Negatif kapılar ayrı test modüllerinde tamamlanır: `test_release_manifest.py` pin yok/yanlış, manifest tampering, payload drift ve dirty source durumlarını; `test_release_installer.py` wrong-pin install, duplicate release ID, root/path ve pointer hatalarını; acceptance fixture da payload path policy ile cutover/rollback wiring'ini sınar. Yanlış pin ile `verified_release` oluşmamalı ve geçersiz kurulum current'a geçmemelidir.
5. #609 birleşik fixture'ı v1/v2 cutover ve rollback zincirini sentetik olarak yürütür; sonuç `fixture_decision: GO` olabilir. Raporun `host_rollout_decision` **NO-GO** kalır; fixture pin'i bağımsız custody'den gelmez ve host process/writer/path gerçekliği incelenmez.
6. Geçici kök cleanup sonrası yokluğu doğrulanır. Fixture sonucunu veya fixture pin'ini release onayı, harici pin kaydı ya da canlı host kanıtı olarak dışarı aktarmayın.

İlgili mevcut testler: `tests/test_release_manifest.py`, `tests/test_release_installer.py` ve `tests/test_release_acceptance.py`. Bu belge için test çalıştırılmadı; yalnız mevcut fixture kodu ve kabul belgeleri incelendi.

## Release kararı için fail-closed kontrol

| Kontrol | PASS koşulu | Aksi durumda |
|---|---|---|
| Dış pin provenance | Operatör custody kaynağı ve teslimi release/install güven alanından bağımsız ve kayıtlı | `verified_release`/host rollout iddiası yok |
| Pin/release bağı | Backup değil, hedef canonical manifest byte digest'i; tam release ID/commit ile eşleşiyor | Kurulumu başlatma veya rollback yapma |
| Manifest/payload/source | Canonical şema, exact file set/hash/type/mode ve temiz source commit/tree doğrulandı | Fail-closed |
| Install/cutover | Install root, immutable release, pointer ve gerçek CLI/panel/process/data root kabulü ayrı doğrulandı | Host rollout NO-GO |
| Fixture yorumu | Fixture digest'i caller plumbing ve negatif davranışları kanıtlar; gerçek custody'yi kanıtlamaz | Fixture GO'yu host GO diye yorumlama |

## İlgili belgeler

- [#542 manifest aracı](release-manifest-tool-542.md) — canonical inventory, external pin parametresi ve doğrulama sınırı.
- [#543 explicit-root installer](release-installer-543.md) — install/rollback için caller-supplied external pin.
- [#550 acceptance harness](release-acceptance-harness-550.md) ve [#609 cutover fixture](release-cutover-acceptance-609.md) — sentetik pin'in neden host anchor olmadığını gösterir.
- [#565 backup trust anchor kararı](backup-authenticity-trust-anchor-565.md) — dış pin, imzalı metadata ve immutable store seçeneklerinin tehdit/maliyet karşılaştırması.
- [#624 backup pin custody prosedürü](backup-digest-pin-operator-custody-624.md) — tek-operatör custody akışının ayrıntılı örneği; release pin'i de kendi release ID ve manifesti için benzer bağımsız custody ister.
- [#617 operatör karar formu](release-operator-decision-form-617.md) — bağımsız pin ve rollout kanıtı için kabul kaydı.

Bu karar bir signer key, public-key trust store, dış pin servisi veya gerçek operator custody provision etmez. Bu bileşenler ve host acceptance sağlanana kadar mevcut kod `--trusted-manifest-sha256` değerinin provenance'ını kendi başına doğrulayamaz; gerçek release sonucu custody kanıtı yoksa `unverified`/NO-GO kalmalıdır.
