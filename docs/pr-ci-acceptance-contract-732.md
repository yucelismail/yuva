# Yuva #732 — Pull request CI kabul sözleşmesi ve güven sınırı

**Tarih:** 2026-10-23
**Durum:** Workflow uygulaması ve repo ayarı değildir; #733 için kabul sözleşmesidir.

## CI neyi kanıtlar?

Pull request CI, runner'da checkout edilen kaynak ağacının seçilmiş unittest
keşif komutunu ve ayrı kaynak syntax kontrolünü tamamladığını gösterir. Bu,
yalnız o commit/runner girdileri için otomatik regresyon sinyalidir. CI sonucu
tek başına kodun güvenli olduğunu, gözden geçirildiğini, doğru sürümün
yayımlandığını, canlı servisin çalıştığını, Yuva data root'unun güvenli
olduğunu veya release/host kabul kapılarının geçtiğini kanıtlamaz.

Test envanteri [#731](test-inventory-before-actions-731.md) 64 `unittest`
modülü, Linux/POSIX bağımlılıkları ve geçici loopback/AF_UNIX socket kullanan
fixture'lar kaydeder. README Linux ve Python 3.8+ bildirir; gerçek destek
matrisi için #738 çapraz kontrolü gereklidir.

## Kabul maddeleri

| Alan | Kabul koşulu |
|---|---|
| Tetikleyici | Pull request açma, güncelleme ve yeniden açma olaylarında aynı gerekli CI check çalışmalı. İlgili workflow/script değişiklikleri check'i atlatamamalı. Varsayılan branch hedefi repo ayarıyla eşleşmeli. |
| Güvenli PR bağlamı | Fork PR'ları dahil kaynak kodu güvenilmeyen girdi sayılmalı. Workflow `pull_request` benzeri sınırlı bağlamı kullanmalı; PR kodunu sır veya yazma yetkili token ile çalıştıran ayrıcalıklı `pull_request_target` akışı olmamalı. |
| Token ve sırlar | Job için yalnız checkout/teste gereken read-only erişim verilmeli. Repo secrets, ortam secrets, deploy credentials, OIDC yazma yetkisi ve production verisi test job'una açılmamalı. |
| Runner | README'de desteklenen Linux ortamı kullanılmalı. `fcntl`, `/proc`, AF_UNIX/SO_PEERCRED ve geçici localhost listener kullanan testler ayrıcalıksız runner'da çalışmalı; gerçek Yuva servisi, UID, key veya data root kurulumu yapılmamalı. |
| Python matrisi | Matris yalnız #738'in kaynak ve test uyumluluk sonucunda doğruladığı desteklenen sürümleri içermeli. README iddiası ile test sonucu çelişiyorsa sessizce bir sürümü düşürmek yerine destek aralığı ayrıca karara bağlanmalı. |
| Bağımlılıklar/ağ | #731 envanterinde test bağımlılık dosyası veya üçüncü taraf test paketi bulunmadı. Test adımı dış ağdan paket indirmeden çalışmalı; yeni bağımlılık gerekirse pin/tedarik ve ağ kararı ayrı değerlendirilmelidir. |
| Test discovery | Sabit unittest discovery komutu tüm `tests/test_*.py` modüllerini bulmalı. Sıfır test keşfi başarı olmamalı (#737); modül import veya test başarısızlığı job'u başarısız yapmalı (#748). `continue-on-error`, `|| true` veya sonucu maskeleyen wrapper kabul edilmez. |
| İzolasyon | Gerçek `YUVA_DIR` ve host state'ine erişim CI içinde engellenmeli (#739). Yazabilen testler işaretli `TemporaryDirectory`/fixture root kullanmalı (#740). Gerçek UID provisioning, servis başlatma, kullanıcı HOME, production path veya host policy mutasyonu olmamalı. |
| Socket ve süreç ömrü | Loopback testleri yalnız ephemeral port ve geçici listener kullanmalı (#742); server thread/socket her durumda kapanmalı (#743). Subprocess testlerinde timeout, terminate/kill ve çocuk temizliği bulunmalı (#744). |
| Determinizm | Locale ve timezone CI girdileri sabit olmalı (#746). Testler dış servise/host adına bağlı olmamalı (#745). Makineye özel mutlak path'ler log/çıktıda sızmamalı (#741). |
| Kaynak kontrolü | Python syntax/compile adımı unittest adımından ayrı, görünür check olmalı (#747). |
| Rapor/artifact | Başarısızlık logları sentetik secret'ı dışarı vermemeli (#749). Test sonucu dışında artifact/cache üretimi gerekçelendirilmedikçe kapalı tutulmalı (#750); çalışma ağacından test verisi yüklenmemeli. |
| Check kimliği | Branch protection'ın bağlayacağı job/check adı sabit ve dokümante olmalı (#756). Branch protection ayarı ayrıca operatör işi ve gözlemlenebilir repo konfigürasyonudur (#735). |

## Asgari beklenen komut davranışı

Envanterdeki discovery örneği:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Workflow uygulaması öncesi/sonrası kabulte şunlar gözlenmeli:

1. Temiz checkout'ta discovery en az bir test çalıştırır ve tüm testler geçince
   sıfır exit code verir.
2. Sentetik olarak başarısız bir test veya import hatası non-zero sonuç üretir;
   CI check kırmızı kalır.
3. `tests/test_*.py` dışında repo'da hedeflenmeyen bir dosyaya test glob'u
   genişlemez.
4. İzolasyon guard'ı gerçek data root path'ini testin kullanmasına izin vermez;
   socket kullanan fixture yalnız loopback/AF_UNIX temporary endpoint açar.
5. Syntax kontrolü ve unittest sonucu ayrı, gerekli check'ler olarak raporlanır.

## Güven sınırı ve yanlış yorumlanmaması gerekenler

PR içindeki test ve workflow dosyaları kod çalıştırabilir; read-only token ve
sır yokluğu bu nedenle temel koşuldur. GitHub-hosted runner'ın geçici olması
run sırasında açılan test socket'ini veya temp fixture'ı sınırlar, fakat
workflow'a gereksiz credential vermeyi güvenli hale getirmez. CI'da başarılı
test sonucu code review, release imzası, bağımsız artifact pin'i, browser
uyumluluk testi, gerçek host multi-UID kabulü veya live service readiness
yerine geçmez.

PR başlığı/gövdesi, test output'u ve artifact isimleri güvenilmeyen metin
olabilir; workflow bunları shell komutu, path veya credential seçimi olarak
kullanmamalıdır. Üçüncü taraf action kullanılırsa action kaynağı ve pinleme
politikası #734 güvenlik incelemesinde belirlenmelidir.

## İlişkili takip görevleri

- #731 test envanteri — bu sözleşmenin kaynak girdisi.
- #733 workflow uygulaması; #734 workflow güvenlik incelemesi.
- #735 branch protection runbook'u; #756 kararlı check adı.
- #737–#750 discovery, destek matrisi, isolation, fixture cleanup, path,
  socket, subprocess, ağ/determinism ve rapor/artifact kabul işleri.
- #757 tüm değişikliklerde PR workflow tetiklenmesini doğrular; #758–#759
  operatör checklist'i ve yönerge bağlantısını ele alır.

Bu belge workflow, repo permission, secret, branch protection, deployment,
servis veya test ortamı ayarını değiştirmedi; test çalıştırmadı.
