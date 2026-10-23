# Oturum adaptörü çalışma dizini ve süreç sınırı (#498)

- **Durum:** Önerilen tasarım; uygulanmış sandbox veya çalışan provider launcher değildir.
- **Kapsam:** Codex/OpenCode oturumları için workspace seçimi, yol doğrulama, child process ve environment sınırı.
- **Güven varsayımı:** Görev metni, sohbet, model/worker çıktısı ve provider event'i path, kimlik veya izin yetkisi vermez. #480'in kaynak güven politikası geçerlidir.

## Mevcut kod ve araç yetenekleri

| Alan | Kaynakta görülen yetenek | Olmayan garanti |
| --- | --- | --- |
| OpenCode adapter | `OpenCodeAdapter` loopback HTTP(S) URL'si, bounded `session_id`, timeout, redirect reddi ve response/SSE byte sınırları uygular (`prototypes/opencode-adapter/adapter.py:28-48, 150-168`). `send_message()` mevcut session ID'ye prompt gönderir. | Çalışma dizini seçme/bağlama, session başlatma, subprocess, filesystem sandbox, Yuva task binding veya capability discovery yok (`prototypes/opencode-adapter/README.md`). Session ID tek başına workspace kanıtı değildir. |
| Codex app-server adapter | JSON-RPC trace'ini parse edip request/notification gözlemi üretir (`prototypes/codex-app-server/adapter.py:1-6`). | Codex'i başlatmaz/bağlanmaz, `thread/start` göndermez, cwd seçmez ve process/environment sınırı kurmaz (`prototypes/codex-app-server/README.md`). Metindeki `cwd` alanı bu yeteneği eklemez. |
| Mock adapter | Oturum kaydında `cwd` string'i saklar ve aynı Yuva identity'si için sonraki cwd değerinin eşleşmesini ister (`prototypes/mock-adapter/adapter.py:104-128`). | `cwd` yalnız boşluk kontrolünden geçer; canonical path, traversal, symlink, root containment, filesystem erişimi veya subprocess yok. Mock doğrulaması gerçek path güvenliği değildir. |
| Yuva panel görev köprüsü | `panel/server.py:gorev_calistir()` izinli görev altkomutları için sabit CLI yolunu argv listesiyle `subprocess.run()` çağırır; `timeout=15` verir (`:1299-1369`). | `cwd` atamaz; `env = dict(os.environ)` ile parent ortamını child'a kopyalar ve yalnız `YUVA_DIR` değerini değiştirir. Bu provider process sandbox'ı değildir; parent'ta bulunan sırlar/credential'lar child'a geçebilir. |
| Bu Codex oturumunun komut aracı | `exec_command` bir `workdir` kabul eder ve bu oturumda sandbox/writable-root politikasıyla çalışır. | Bu host sınırı Yuva'nın OpenCode/Codex prototiplerine veya onların başlatacağı süreçlere otomatik aktarılmaz. |

Sonuç: mevcut iki gerçek provider prototipi session transport/gözlemi seviyesindedir; proje çalışma dizini alanı veya child-process oluşturma sözleşmesi sunmaz. Yeni bir session runner ayrı bileşen ve ayrı güvenlik kapısı olmalıdır.

## Workspace bağlama sözleşmesi

1. **Path değil grant seç:** Yetkili operatör veya uygulama ayarı `workspace_id` değerini önceden onaylı kök dizin kaydına bağlar. Bu kayıt canonical kök, read/write modu, izinli provider/araçlar ve grant sahibini taşır. Worker, model, sohbet veya görev metninden gelen `cwd` kullanılmaz.
2. **Mevcut proje:** Kullanıcı açıkça başka türlü seçmedikçe session'ın cwd'si grant'in canonical proje köküdür. Adapter aynı session'ı resume ederken provider session'ın proje/workspace bağını salt-okunur doğrulayabilmelidir; doğrulayamıyorsa cwd'yi tahmin etmez ve session işlemini `unknown`/fail-closed tutar.
3. **Canonical doğrulama:** Dizin var olmalı, dizin türünde olmalı ve izin verilen workspace kökünün altında kalmalıdır. Karşılaştırma string prefix ile değil `realpath`/path-component tabanlı containment (`commonpath` eşitliği gibi) ile yapılır. Farklı filesystem/volume veya kullanıcı tarafından onaylanmamış dış kök reddedilir. Mutlak path, `..`, NUL, boş path ve belirsiz provider path formatı reddedilir.
4. **Symlink/TOCTOU:** Path'i bir kez `resolve()` edip sonra normal pathname ile spawn etmek yarış penceresini tamamen kapatmaz; bir dizin doğrulama ile child'ın `chdir` etmesi arasında symlink olarak değişebilir. Güvenlik gereksinimi varsa directory file descriptor üzerinden `openat2` (`RESOLVE_BENEATH`, `RESOLVE_NO_MAGICLINKS`, tercihen `RESOLVE_NO_SYMLINKS`) veya her path bileşenini `openat` + `O_NOFOLLOW` ile açan küçük bir güvenilir launcher kullan. Platform bu garantiyi sağlayamıyorsa launch reddedilsin ya da aynı-UID yerel yarışın tehdit modeli içinde olduğu açıkça kabul edilsin.
5. **CWD sandbox değildir:** `cwd=/project` yalnız başlangıç dizinini seçer; child `../`, mutlak path, symlink, `/tmp`, home veya başka dosyaları açabilir. Repo kökü dışına erişimi yasaklamak için OS seviyesinde filesystem allowlist/sandbox gerekir. Yalnız `cwd` kontrolü ile “repo içine hapsedildi” denemez.

## Süreç başlatma sınırı

- Yalnız ayrı ve güvenilir runner process başlatma yapar. Executable tam canonical mutlak path ve allowlist/versiyon kimliğiyle seçilir; model/worker/tool çıktısından executable, shell komutu veya CLI argüman listesi türetilmez.
- `shell=False` ve argv listesi kullanılır. `sh -c`, shell interpolation, PATH üzerinden belirsiz executable arama, provider metnini komut olarak çalıştırma ve onaysız script/extension yükleme yasaktır. Yuva CLI'ın sabit program/argv listesi kullanması shell injection yüzeyini azaltır; bu tek başına sandbox değildir.
- Child kendi düşük ayrıcalıklı UID'si veya OS sandbox'ı altında çalışır; filesystem erişimi seçilen grant ile sınırlandırılır. Varsayılan ağ erişimi kapalıdır. OpenCode loopback endpoint erişimi gerekiyorsa yalnız kayıtlı host/port için dar istisna verilir; loopback, process kimliği veya güven kanıtı değildir. Sandbox kurulamıyorsa runner fail-closed davranır.
- Her çağrı açık timeout, CPU/RSS/file-size/output limitlerine ve process-group cleanup politikasına sahip olur. `stdin` kapalı/borulu ve sınırlı; `stdout`/`stderr` ayrı, byte-limitli ve redakte edilmeden Yuva'ya aktarılmayan kanallardır. Child env ve açık file descriptor listesi ayrı ayrı allowlist edilir; varsayılan `pass_fds` boş, `close_fds=true` olmalıdır.

## Environment ve secret politikası

Child'a parent `os.environ` kopyası verilmez. Runner yeni minimal environment kurar: ihtiyaç varsa sabitlenmiş `PATH`, `LANG`, grant'e ait `HOME`, izole `TMPDIR` ve doğrulanmış `YUVA_DIR`. Aşağıdakiler varsayılan olarak çıkarılır: OpenCode Basic Auth/HMAC, Yuva auth key'leri, cloud/API credential'ları, `SSH_AUTH_SOCK`, GPG/socket değişkenleri, shell startup değişkenleri, proxy değişkenleri ve kullanıcıya ait diğer sırlar.

Bir provider credential'ı gerçekten gerekiyorsa yalnız o session/host kapsamına sahip ayrı secret broker veya dar ömürlü, yalnız ilgili FD'den okunan credential aktarımı kullanılmalı; secret komut satırına, ortam değişkenine, cwd'ye, prompt'a, exception'a veya log'a konmamalı. İlgili OS izolasyonu bunu desteklemiyorsa gerçek session launch yeteneği sunulmaz.

## Açık kullanıcı onayı eşiği

| Eylem | Karar |
| --- | --- |
| Önceden onaylanmış workspace grant'i içinde, açık görev kapsamına uyan çalışma | Grant kapsamı değişmiyor ve sandbox kısıtları geçerliyse ayrıca her dosya için onay gerekmez. Kayıt ve audit kapsamı yine korunur. |
| Yeni dizin/workspace, grant kökünü değiştirme, dış repo veya symlink'in hedeflediği dış kök | İlgili kullanıcı/operatörden hedefi ve read/write kapsamını belirten açık onay gerekir; grant kalıcılaştırılmadan önce canonical hedef gösterilir. |
| Shell/arbitrary executable, workspace dışı dosya yazma/okuma, network genişletme, credential geçişi, sandbox kapatma veya ayrıcalık yükseltme | Her biri ayrı, eylem ve hedefe özgü açık onay gerektirir; model/worker mesajı ya da Yuva sohbetindeki onay iddiası yeterli değildir. Desteklenmiyorsa reddedilir. |
| Path/grant/session eşleşmesi çözülemiyor, symlink yarışı önlenemiyor veya sandbox durumu bilinmiyor | Otomatik fallback yok; session `unknown`/blocked kalır ve dış eylem başlatılmaz. |

Bir görevin “repo'da çalış” demesi grant'in hangi repo olduğunu seçmez. Kullanıcı mesajındaki path açıkça seçilmiş olsa bile canonical containment ve sandbox şartları devam eder; workspace dışına çıkmak ayrıca izin ister.

## Uygulama kapıları

1. Workspace registry ve `workspace_id → canonical root + permissions` veri modelini, owner/expiry/değişiklik audit'ini tanımla.
2. Codex ve OpenCode için session oluşturma/resume API'sinin hangi workspace'i kanıtladığını resmi schema ve target-instance capability check ile belirle. Sağlayıcı workspace bağını kanıtlamıyorsa bu eksikliği açıkça taşı.
3. Platforma özgü sandbox/launcher seç; symlink/TOCTOU, UID ayrımı, read-only/read-write mount, ağ allowlist'i ve resource limitlerini bağımsız incele.
4. Child ortamı ve descriptor allowlist'ini oluştur; secret broker, redaction ve süreç sonlandırma davranışını ayrıca kararlaştır.
5. Bu kapılar kapanmadan provider adapter'a `cwd` parametresi ekleme, serbest path kabul etme veya gerçek process launch capability'sini ilan etme.

## Sınır

Bu çalışma kaynak ve prototip incelemesidir. Kod, servis, environment veya workspace değiştirilmedi; test/runtime çalıştırılmadı. Repo içi/aynı UID süreçlerinin birbiriyle güven sınırı oluşturmadığı; sandbox olmayan bir child'ın host filesystem'ine erişebileceği kabul edilmelidir.

## Dayanak

- `docs/session-adapter-contract-474.md` — workspace binding, provider capability ve opaque session sözleşmesi.
- `docs/session-bridge-trust-policy-480.md` — görev/sohbet/model çıktısının path veya dış eylem yetkisi vermemesi.
- `prototypes/opencode-adapter/README.md`, `prototypes/opencode-adapter/adapter.py:28-48, 150-168` — loopback HTTP/SSE, session ID ve process/workspace kapsamı olmayan prototip.
- `prototypes/codex-app-server/README.md`, `prototypes/codex-app-server/adapter.py:1-6` — bağlantı/başlatma yapmayan JSON-RPC gözlem prototipi.
- `prototypes/mock-adapter/adapter.py:104-128` — yalnız string cwd ve session eşleşmesi kullanan fake adapter.
- `panel/server.py:1299-1369` — Yuva görev CLI subprocess argv, timeout, varsayılan cwd ve parent environment kopyası.
- `functions.exec_command` araç sözleşmesi — bu Codex komut çağrısının `workdir` ve sandbox sınırı; gelecekteki provider child'larına aktarılmış yetki sayılmaz.
