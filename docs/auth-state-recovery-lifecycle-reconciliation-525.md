# #525 — Auth-state kurtarma ve lifecycle kaynak uzlaştırması

## Kapsam ve sonuç

`#447`, `#458`, `#461`, `#477/#478`, `#501`, `#502` ve `#503` belgeleri mevcut
`panel/auth_store_v2.py`, `panel/auth_provision_draft.py`, `panel/auth.py` ve
`panel/server.py` kaynaklarıyla statik karşılaştırıldı. Kod, secret, store,
test, runtime veya deployment değiştirilmedi/çalıştırılmadı.

Temel durum: store doğrulama ve genel tek-snapshot transaction altyapısıdır.
Boş ilk state kuran ayrı bir provisioning taslağı vardır; yedekleme, restore,
key üretme/rotation/revoke ve harici anti-rollback anchor için işletilebilir
araç/API yoktur. Belgelerdeki çoğu güvenlik sınırı bu gerçekle uyumludur.
Başlıca uzlaştırma işi #503 incelemesinin eski commit sınıflandırmasını ve
#447'deki “provisioning aracı yok” ifadesinin kapsamını netleştirmektir.

## Uzlaştırma matrisi

| Alan / belge | Belgelerdeki iddia veya öneri | Güncel kaynak davranışı | Uzlaştırma / açık nokta |
|---|---|---|---|
| İlk provisioning — #447, #477, #501 | #447, store'un kendiliğinden bootstrap etmediğini ve onaylı host provisioning akışı bulunmadığını söyler. #501, #477 taslağının yalnız boş ilk snapshot kurduğunu belirtir. | `AuthStateStore` mevcut root, state ve sabit lock dosyasını ister; kendi başına dosya oluşturmaz (`auth_store_v2.py`, `_secure_root_fd`, `_open_private_file`, `AuthStateStore`). Ayrı `auth_provision_draft.py` `empty_initial_state()` ile keys/enrollments/nonces/rate_limits boş v2 state hazırlar; `write_initial_state()` owner-only mevcut root'u kullanır, stabil lock'u oluşturabilir/yeniden kullanır ve snapshot'ı mevcut hedefin üstüne yazmadan hard-link ile kurar. Key veya secret üretmez. | “Store bootstrap etmez” doğru. “Provisioning aracı yok” ifadesi bugün kod taslağı bulunduğu için fazla geniş: CLI/servis entegrasyonu ve onaylı host prosedürü hâlâ yok; yalnız callable, offline taslak mevcut. Belge bu ayrımı açık söylemeli. Provisioning taslağının kendi modül docstring'indeki “auth.py/server.py tarafından import edilmiyor” iddiası kaynak aramasıyla uyumlu. |
| Stable lock ve ilk kurulum sonucu — #447, #502 | #447 state ve lock'un birlikte, private izinlerle hazırlanmasını ister. #502, hard-link öncesi/sonrası commit fazını tarif eder. | `_open_stable_lock()` boş `0600` lock inode'u `O_EXCL` ile oluşturur veya var olanı doğrular; oluşturulan lock ve root directory fsync hatasını `lock_durability_unknown` verir. Snapshot temp dosyasına yazılıp fsync edilir, sonra no-replace `os.link()` ile kurulur. | #447'nin sabit lock inode'u ve private dosya gereksinimi geçerli. İlk lock'un dayanıklılık belirsizliği ayrı `lock_durability_unknown` sonucudur; bu, state snapshot commit'iyle aynı olay değildir ve mevcut kılavuzlarda ayrıntılı ele alınmıyor. Çağıran bu sonucu kesin “lock yok” saymamalı; root'u offline incelemelidir. |
| Backup — #447, #458, #501 | Backup için consumer'ları durdurma veya aynı lock inode'unu kullanan tutarlı yöntem, snapshot+lock'u ayrı ve erişimi kısıtlı yerde saklama; aktif/revoked secret içerdiğini varsayma önerilir. | `auth_store_v2.py` ve `auth_provision_draft.py` backup/export aracı sunmuyor. `read()` yalnız doğrulanmış state döndürür; backup metadata, şifreleme, retention veya audit sağlamaz. Lock dosyası sabit inode koordinasyonunun parçasıdır. | Belgelerdeki “backup aracı yok” ve gizli materyali koruma uyarıları doğru. Backup/restore mevcut kaynakta uygulanmış kabiliyet değildir. Canlı süreçler eski lock inode'unu açık tutarken restore edilmiş/yeni lock inode'una geçmek kilit sahipliğini bölebilir; restore öncesi tüm consumer'ları durdurma şartı korunmalı. |
| Restore ve rollback — #447, #458, #501 | Snapshot içi generation/high-water'ın eski geçerli backup'ı tespit edemediği; eski revoked key ve nonce durumunun dönebileceği; bugünkü güvenli yolun offline inceleme ve re-provision/credential rotation olduğu yazılı. #458 harici anchor seçeneklerini tasarım olarak kıyaslar. | `generation` ve `last_wall_time` aynı state snapshot'ında ilerler. `generation_floor` opsiyoneldir, yalnız state değeri floor'dan küçükse reddeder; store anchor üretmez/güncellemez. `server.py` store'u `AuthStateStore(kok)` ile, floor vermeden kurar. Restore API/prosedürü yoktur. | #447/#458/#501'in ana güvenlik sonucu geçerli ve #458'in CAS/TPM/log seçenekleri tasarım önerisi olarak kalıyor. Bir eski snapshot kendi içinde geçerli olabilir; floor kullanılsa bile son floor üstündeki rollback veya aynı generation'daki farklı snapshot'ı tek başına ayırt etmez. Aynı host/UID'de korunan sidecar, o UID tehdidine karşı bağımsız anchor değildir. |
| Key/enrollment rotation ve revoke — #447, #501 | #447 lifecycle şemasını ve elle JSON düzenlememe sınırını anlatır. #501 overlap, client'a secret teslimi, revoke sırası, issuer altındaki pending enrollment'lar, readback, kayıp istemci ve acil revoke için önerilen offline prosedürdür; bunu çalışan araç gibi sunmaz. | `AuthStateStore` yalnız `read()` ve genel `transact()` sağlar. Validator key/enrollment ilişkilerini doğrular; `auth.py` verifier `revoked`, scope, audience ve validity okur. Rotation/revoke/enrollment yönetim helper'ı, API endpoint'i, client delivery veya operation receipt yoktur. `write_initial_state()` sadece boş ilk state kurar. | #447 ve #501'in “tasarım/prosedür, uygulanmış lifecycle değil” sınırı doğru. `transact()` düşük seviyeli genel mutasyon sağlar; bu, onaylı revoke/rotation işlemi, audit veya idempotent receipt olduğu anlamına gelmez. Store dışı audit append'i state değişikliğiyle atomik değildir. |
| Normal store transaction `CommitUnknown` — #447, #458, #501 | Replace/directory-fsync sonrası belirsiz sonucu kör retry etmemek; backup'a otomatik dönmemek ve readback'i bağımsız kayıtla uzlaştırmak önerilir. | `_atomic_replace()` temp file'ı fsync eder; `os.replace()` öncesinde `replace_attempt` fazına geçer. `os.replace()` dönerse root directory fsync yapılır. Directory fsync veya syscall çevresindeki `BaseException` `CommitUnknown` olur. Kaynak, `os.replace()` tarafından döndürülen `OSError`'ı `commit_not_started` olarak sınıflandırır. | Başarıdan sonra directory fsync belirsizliği belgelerle uyumlu. Ancak root'un yerel filesystem olduğu doğrulanmıyor/sınırlandırılmıyor; kaynak `OSError` dönüşünün kesin pre-commit olduğu varsayımını koda yansıtmış. Desteklenen filesystem sözleşmesi açıkça yerel POSIX ile sınırlandırılmalı veya bu hata sınıfı için belirsiz commit davranışı ayrıca değerlendirilmelidir. Bu statik uzlaştırma remote filesystem semantiğini test etmez. |
| Initial hard-link `CommitUnknown` — #478, #502, #503 | #478, `os.link()` sonrası `installed` bayrağına ulaşmadan kesinti olursa belirsizliğin kaybolabileceğini buldu. #502 bunu syscall öncesi `link_attempting` fazıyla düzeltti. #503 daha sonra genel `OSError` dönüşünün remote filesystem'de kurulumun olmadığını kanıtlamayabileceğini belirtti. | Mevcut `write_initial_state()` çağrıdan önce `link_attempting`, başarılı dönüşten sonra `installed` yapar. `FileExistsError` `store_already_exists`; diğer `os.link()` `OSError` sonuçları `commit_unknown` olur. Link-attempt penceresindeki `BaseException`, kurulum sonrası temp unlink/fsync ve commit aşamasındaki cleanup kesintileri de `commit_unknown` olarak korunur. Kod otomatik readback, rollback veya retry yapmaz. | #478'in asenkron kesinti bulgusu #502 ile kapanmış. #503'ün genel OSError önerisi mevcut kaynakta uygulanmış; #503 raporundaki “link OSError → commit_not_started” tespiti artık güncel kaynakla uyuşmuyor ve superseded olarak işaretlenmeli. #502 notu mevcut sınıflandırmayla uyumlu. |
| Operasyon kılavuzu doğrulaması — #461 | #461; default-off, store/audience şartı, GET'in auth dışı kalması ve restore sınırını doğru buldu; o andaki kılavuzda Content-Length kabul durumu ve `server.py` satır referanslarını eski saydı. | Güncel `auth-state-v2-operations.md` duplicate Content-Length düzeltmesini #426/#429 kabulü olarak anlatıyor; GET auth sınırı ve fail-closed config'i koruyor. | #461'in tarihsel Content-Length bulgusu mevcut kılavuzda düzeltilmiş. Satır numarası yerine fonksiyon adlarına dayalı referanslar tercih edilmeli; #461'in tarihsel bulgusu güncel açık kusur gibi aktarılmamalı. |

## Kaynakta görülen belge uyumsuzlukları

- `panel/auth_store_v2.py` modül docstring'i (satır 1–3) store'un `auth.py` ve
  `server.py` tarafından import edilmediğini söylüyor; iki dosya da store'u
  import ediyor (`auth.py:38-40`, `server.py:1438-1444`). #447 kılavuzu bu
  docstring'i eski olarak doğru biçimde işaretliyor; kaynak docstring'i hâlâ
  güncel değil.
- #503 raporunun genel `os.link()` `OSError` dalına ilişkin P2 bulgusu #502'den
  sonraki kaynakla çelişiyor. Güncel kodda `FileExistsError` dışında kalan
  `OSError` `commit_unknown`; #503 raporu bu nedenle çözülmüş/superseded olarak
  not edilmeli, tarihsel inceleme kaydı olarak kalabilir.
- #447 kılavuzundaki “provision aracı yok” ifadesi `auth_store_v2.py` için
  doğru, fakat repository'de `auth_provision_draft.py` taslağı bulunduğunu da
  belirtmeli. Taslak onaylı işletim aracı veya auth etkinleştirme yetkisi
  değildir.
- Store transaction'ındaki `os.replace()` OSError sınıflandırması ile ilk
  provisioning hard-link'inin remote-filesystem için tutucu sınıflandırması
  farklıdır. Store root filesystem türü doğrulanmadığından bu iki sınır, host
  desteği seçilmeden tek bir “commit kesin değildi/değildi” garantisi altında
  sunulmamalı.

## Sonuç

Backup/restore, rotation/revoke ve external anchor belgeleri güncel kaynakta
olmayan kabiliyetler için tasarım/operatör kararı olarak kalmalı. En net belge
revizyonları: #447'de provisioning taslağı ile onaylı araç ayrımını açıklamak;
#503'te remote hard-link `OSError` bulgusunun #502 sonrası kapandığını kaydetmek;
auth-store `os.replace()` filesystem varsayımını ayrıca karara bağlamak. Bu not
mevcut auth belgelerini, kodu veya auth ayarını değiştirmez.

## Kaynaklar

- `docs/auth-state-v2-operations.md` (#447), `docs/auth-state-external-anchor-decision-458.md`, `docs/auth-state-operations-review-461.md`
- `docs/auth-provision-draft-review-478.md`, `docs/auth-key-rotation-revoke-offline-501.md`, `docs/auth-provision-commit-unknown-502.md`, `docs/auth-provision-commit-unknown-review-503.md`
- `panel/auth_store_v2.py`: `CommitUnknown`, `_atomic_replace`, `AuthStateStore`, `read`, `transact`, `encode_initial_state`
- `panel/auth_provision_draft.py`: `empty_initial_state`, `_open_stable_lock`, `write_initial_state`
- `panel/auth.py`: `HMACAuthenticator.verify_request`; `panel/server.py`: auth store construction
- `<YUVA_DATA_ROOT>/gorevler.json`: referenced task status/context
