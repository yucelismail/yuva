# Yuva #497 — Auth ve provider oturum köprüsü yayın kapıları

Kapsam: Auth default-off sınırı, GET read scope, offline provisioning, doğrulanmış presence ve Codex/OpenCode session bridge için kabul edilmiş teslimleri, güncel görev durumlarını ve kalan yayın blokajlarını tek haritada toplamak. Bu harita statik bir durum kesitidir; `verified` görev kaydı çalışan deployment veya canlı readiness kanıtı değildir.

## Durum okuma kuralı

**Görev tahtası snapshot'ı: 2026-10-23 16:10:23 Europe/Istanbul** (`<YUVA_DATA_ROOT>/gorevler.json`). `verified`, Yuva'da teslimin kabul edildiğini; `pending_verification` teslimin inceleme beklediğini; `pending_revision` revizyon istendiğini; `assigned` görevin üstlenildiğini gösterir. Hiçbiri tek başına canlı sistemin hazır olduğunu göstermez. Bu snapshot'ta #512, #513, #515 ve #517 `verified`; #514 `pending_verification`; #516 ve #518 `assigned`. Kullanıcının 15:58:44 tarihli operatör kararı (Yuva ortak mesajı) hedefi model/ajan başına doğrulanmış yeşil presence olarak seçti; ajan başına ayrı OS UID tercih edilen güven sınırı, same-UID ajanlar güvenilir sayılmıyor ve güvenilir launcher varsayılmıyor. Bu karar kurulum, auth açma veya deployment onayı değildir.

## Kabul edilen teslimler ve açık sınırlar

| Hat | Güncel kabul edilmiş durum | Kalan yayın sınırı |
| --- | --- | --- |
| **POST auth ve auth state** | #426, #429, #456, #458, #462, #477–#478 ve #501–#503 `verified`. Offline rotation/revoke akışı belgelendi; #502 commit-unknown düzeltmesi ve #503 bağımsız incelemesi kabul edildi. Kaynaklar: `docs/auth-key-rotation-revoke-offline-501.md`, `docs/auth-provision-commit-unknown-502.md`, `docs/auth-provision-commit-unknown-review-503.md`, `docs/auth-state-v2-operations.md`, `docs/auth-state-external-anchor-decision-458.md`. | `YUVA_AUTH_ENABLED` kapalı varsayılır. Provisioning/rotation/revoke taslak ve operatör belgeleri canlı yönetim aracı değildir; credential üretimi/teslimi, hedef host kabulü, backup/restore ve rollback işlemleri uygulanıp doğrulanmış değil. #458 bir anchor kararıdır, uygulanmış anti-rollback kanıtı değildir. #502 belirsiz sonucu sınıflandırır; otomatik readback, rollback veya retry yapmaz. Aynı UID sınırı sürer. |
| **GET read scope** | #455 ve #471 tasarımları ile #506 feature-off GET policy prototipi `verified`. Kaynaklar: `docs/local-api-get-snapshot-decision-455.md`, `docs/hmac-get-read-scope-design-471.md`, `panel/auth_integration_draft.py`, `panel/AUTH_INTEGRATION_DRAFT.md`. | #506 server GET dispatch'e bağlı değildir; `read_enabled=False` varsayılanı korunur. Gerçek kurulumda GET framing, nonce/replay, cache/limit, hata halinde snapshot sızıntısı ve startup flag ayrıca bütünleştirilip kabul edilmeli. HTML/browser oturumu veya proxy auth sağlanmış değildir. |
| **Presence** | #435, #482, #494 ve #513 `verified`. #513 aynı UID + `SO_PEERCRED`'i yalnız host göstergesi için dürüst sayıyor; model/ajan başına presence hedefi için kullanıcı B seçeneğini (ajan başına ayrı OS UID) tercih etti. Kaynaklar: `docs/panel-presence-evidence-review-482.md`, `docs/panel-presence-source-options-494.md`, `docs/w1b-broker-principal-granularity-513.md`, `<YUVA_DATA_ROOT>/mesaj.jsonl` (2026-10-23 15:58:44). | #514 feature-off planı `pending_verification`. Rev3 ilk teslimdeki live GET, `ps` süreç sorgusu ve saat okumasını kapsam sapması olarak kaydediyor; bunların sonuçlarını bilgi veya kabul kanıtı olarak kullanmıyor. Süreç modu/kodu `unknown`; rev2/rev3'te ek runtime sorgusu yapılmadı. Operatör kararı planı yönlendiriyor ama hostta UID/servis kurulumu veya auth açma yetkisi vermiyor. Broker/principal uygulaması ve attestasyonlu heartbeat yok; model presence `unknown` kalmalı. |
| **CLI ve release kopyaları** | #485, #486, #508, #515 ve #517 `verified`. Kaynaklar: `docs/local-cli-copy-version-map-485.md`, `docs/yuva-cli-update-single-source-plan-486.md`, `docs/yuva-cli-copy-cutover-acceptance-508.md`, #515/#517 için Yuva tahta geçmişi (`<YUVA_DATA_ROOT>/gorevler.json`). | #515 dört kopya denetimini kabul ettirdi. #517'nin kabul edilen statik inceleme revizyonu ilk rapordaki `ps`, `/proc`, `systemctl` ve `curl` kullanımını kapsam sapması diye açıkladı; önceki canlı süreç/HTTP sonuçlarını geri çekti. Onay yalnız statik rapor teslimidir. Statik bulguları repo `contrib` unit'i ile user-unit dosyasının farklı kod kökleri göstermesi, README symlink tarifinin eski kalması ve kontrol edilen yedek kopya dosyalarıdır; bunlar etkin sürecin kodunu kanıtlamaz. v2 çalışma ağacı kirli, buradan release çıkarılmamalı. |
| **Provider session bridge** | #472–#476, #480–#481 ve #487–#493 `verified`; #498–#511 de `verified`. Kabul edilenler arasında izole adapter/reconcile/trust prototipleri ve privacy, approval, retry, credential, startup capability, receipt, output mapping, process boundary ve scheduler belgeleri bulunuyor. Kaynaklar: `prototypes/opencode-adapter/`, `prototypes/session-bridge/`, `prototypes/codex-app-server/`, `prototypes/task-scheduler/README.md`, `docs/model-output-privacy-review-492.md`, `docs/opencode-messageid-retry-risk-493.md`, `docs/provider-approval-bridge-decision-490.md`, `docs/session-adapter-workdir-process-boundary-498.md`, `docs/provider-local-credential-endpoint-security-499.md`, `docs/opencode-capability-startup-check-500.md`, `docs/session-bridge-persistent-receipt-store-504.md`, `docs/opencode-output-yuva-mapping-505.md`, `docs/provider-api-credential-operations-507.md`, `docs/yuva-cli-copy-cutover-acceptance-508.md`, `docs/opencode-http-adapter-security-review-509.md`, `docs/session-bridge-trust-policy-review-510.md`. | Kabul edilmiş prototip ve kararlar canlı Codex/OpenCode/Yuva entegrasyonu değildir. Hedef OpenCode `/doc` şeması/sürümü ve capability'leri deployment için pinlenip doğrulanmadı; credential yönetimi, kalıcı receipt/outbox, trust/binding, output redaction/delivery ve insan approval yolu entegre değil. #493'e göre `messageID` idempotency garantisi belgelenmedi; gönderim belirsizliğinde otomatik retry yok. #492, ham provider çıktısının güvenle Yuva'ya taşındığını kanıtlamaz. |

## Güncel görev envanteri

### Auth ve GET

| ID | Tahta durumu | Teslim / kanıt |
| --- | --- | --- |
| #426, #429, #456 | `verified` | POST auth gate, route/actor incelemesi, principal provenance ve yönetim audit izi. |
| #455, #471 | `verified` | GET snapshot erişim kararı ve HMAC read-scope sözleşmesi. |
| #458, #462 | `verified` | Dış generation anchor kararı ve auth lifecycle tasarımı. |
| #477, #478 | `verified` | Offline provisioning taslağı ve kaynak incelemesi; incelemede commit-unknown aralığı bulunmuştu. |
| #501–#503 | `verified` | Offline rotation/revoke operatör akışı; #502 commit-unknown düzeltmesi ve #503 bağımsız review kabul edildi. |
| #506 | `verified` | GET read-scope prototipi kabul edildi; feature-off ve server dispatch dışında. |

### Presence

| ID | Tahta durumu | Teslim / kanıt |
| --- | --- | --- |
| #435, #482 | `verified` | Yalnız doğrulanmış/taze online gösterimi ilkesi ve mevcut presence kaynağı incelemesi. |
| #494 | `verified` | Broker, adapter ping ve local process/socket kanıtı seçenekleri; uygulama değil karar belgesi. |
| #513 | `verified` | `docs/w1b-broker-principal-granularity-513.md` karar notu kabul edildi; same-UID `SO_PEERCRED` yalnız host principal'ı kanıtlar ve ajan presence'ı ayırmaz. |
| Kullanıcı kararı (2026-10-23 15:58:44) | kaydedildi | Hedef model/ajan başına yeşil presence; aynı UID ajanlar güvenilir sayılmıyor; ajan başına ayrı OS UID uygulanabilir ve tercih edilen sınır; trusted launcher varsayılmıyor. Bu, #514 planını yönlendirir, host kurulumu veya auth açılışını onaylamaz. |
| #514 | `pending_verification` | Minimax'in feature-off B0–B9 planı ve K1–K19 matrisi rev3 olarak teslim edildi. İlk teslimdeki live GET, `ps` ve saat sorguları kapsam sapması olarak kaydedildi; sonuçları rapordan çıkarıldı, çalışan panel/süreç modu/kodu `unknown`. Rev2/rev3'te ek HTTP, süreç veya runtime sorgusu yapılmadı. Denetçi incelemesi bekleniyor. |
| #518 | `assigned` | #514 W1b planı için bağımsız güvenlik ve kapsam incelemesi. |

### CLI ve release kopyaları

| ID | Tahta durumu | Teslim / kanıt |
| --- | --- | --- |
| #485, #486, #508 | `verified` | CLI kopya envanteri, tek kaynak/release planı ve geçiş kabul listesi; geçiş uygulanmış değil. |
| #515 | `verified` | Dört CLI kopya/hash denetimi kabul edildi. `~/.local/bin/yuva` v2'ye symlink'tir; UI-dev ayrı preview worktree'sidir. Kontrol edilen PATH/servis yapılandırmalarında UI-dev referansı yoktur; etkin panel süreci ve elle çağırma/otomasyon belirsizliği notta korunur. |
| #517 | `verified` | Rev2 bağımsız inceleme kabul edildi. İlk rapordaki runtime/süreç/HTTP sorguları kapsam sapması olarak açıklandı; bunlardan çıkan iddialar geri çekildi. Onay yalnız statik rapor teslimine ilişkindir; etkin panel süreci unknown. |

### Harita ve takip işleri

| ID | Tahta durumu | Not |
| --- | --- | --- |
| #516 | `assigned` | Bu snapshot'ta revizyon üstlenilmiş; yalnız milestone haritası güncelleniyor. |
| #518 | `assigned` | #514 planının bağımsız güvenlik/kapsam incelemesi. |

### Provider ve session bridge

| ID | Tahta durumu | Teslim / kanıt |
| --- | --- | --- |
| #472–#476, #480–#481 | `verified` | Provider API araştırması, adapter/outbox ve trust/task-switching sözleşmeleri; izole taslaklar. |
| #487–#491 | `verified` | HTTP/SSE ve trust prototipleri; approval karar notu. #491 için #510 review da kabul edildi. |
| #492–#493 | `verified` | Output privacy incelemesi ve messageID/unknown retry kararı. |
| #498–#511 | `verified` | Process boundary, credential/capability, auth lifecycle, receipt/output mapping, CLI geçişi, bağımsız review ve scheduler teslimleri. Bunlar kod prototipi veya tasarım belgeleri olarak belirtilen kapsamda kabul edildi. |

## Bugünkü blokajlar ve güvenli ilerleme sırası

1. **Auth kapalı kalsın.** #501–#503 kabulü doküman ve prototip düzeyindedir; güvenilir bootstrap/provisioning aracı, secret teslimi, hedef host üzerinde readback, backup/restore ve rollback kabulü olmadan auth flag açılışına dayanak değildir. Aynı UID, audit atomikliği ve GET/HTML sınırları ayrıca çözülmeli.
2. **GET'i ayrı feature kapısı olarak tamamla.** #506 prototipi server dispatch'e bağlı değil. Entegrasyon ve hedef deployment doğrulaması yapılmadan API snapshot veya browser erişiminin korunduğu iddia edilmemeli.
3. **Presence uygulamasını seçilen güven sınırıyla planla.** Kullanıcı model/ajan başına yeşili ve same-UID ajanlar arası düşmanca threat modelini seçti; ajan başına ayrı OS UID tercih edilen sınır, trusted launcher ise varsayılmamalı. #514 rev3 planı B0–B9 dilimlerini ve K1–K19 ölçütlerini tarif ediyor; `pending_verification`. İlk teslimdeki live GET, süreç ve saat sorguları kapsam sapmasıdır ve raporun kabul kanıtı değildir; süreç modu/kodu `unknown`. Karar host UID/servis kurulumunu, auth açmayı veya deployment'ı onaylamaz; broker yokken hiçbir model yeşil sayılamaz.
4. **CLI kopya geçişini doğrula.** #515 dört kopya denetimi ve #517 statik bağımsız incelemesi `verified`; #517'nin runtime sorguları açık kapsam sapması olarak kaydedildi ve sonuçları geri çekildi. Statik inceleme README symlink'i, repo `contrib` unit'i ile user-unit dosyası farkını ve kontrol edilen yedek kopyaları gösteriyor. Etkin panel süreci hâlâ unknown; v2 çalışma ağacı kirli. Sabitlenmiş temiz kaynak, ortak veri kökü ve yazıcı tekilliği kanıtlanmadan release veya symlink geçişi yapılmamalı.
5. **Provider bridge'i kapalı tut.** Kabul edilen adapter/prototipler için gerçek hedef sürüm `/doc` ve capability doğrulaması, ayrı credential işletimi, kalıcı operation/attempt receipt, güvenilir session/workspace/assignee binding'i, redacted output delivery ve insan approval yazarı hâlâ gerekir. Kopma veya timeout sonrası `unknown` salt-okunur uzlaştırılmalı; sağlayıcı garantisi olmadan resend yapılmamalı.
6. **Canlı release kararını ayrı kanıtla.** Hedef host, kurulu CLI/panel sürümleri, feature flag'ler, auth store, provider credential'ları ve rollback/canary davranışı bu görev kapsamında okunmadı veya çalıştırılmadı. Yetkili release sahibi deployment'a özgü doğrulamayı ayrıca yürütmeli.

Bu güncelleme yalnız görev tahtası, operatörün Yuva mesajı ve mevcut teslim dosyalarıyla statik eşlemedir. Bu güncellemede kod, Yuva görev verisi, auth/provider entegrasyonu veya runtime değiştirilmedi; test, HTTP, süreç veya servis sorgusu yapılmadı. #514/#517 geçmiş teslimlerindeki kapsam dışı sorgular haritada kapsam sapması olarak işaretlendi, kanıt olarak kullanılmadı. Kullanıcı principal tercihini belirlemiştir ancak hostta UID/servis kurulumu, auth açılışı veya canlı presence doğrulanmış değildir.
