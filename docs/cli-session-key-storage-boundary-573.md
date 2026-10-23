# Aynı UID altında CLI oturum anahtarı saklama sınırı (#573)

**Tarih:** 2026-10-23
**Durum:** Kaynak ve işletim belgesi temelli karar notu; secret/token üretilmedi, provision edilmedi veya okunmadı.
**Sınır:** Auth flag'i, store, CLI, servis ve process ortamı değiştirilmedi; `/proc` veya canlı süreçler incelenmedi.

## Karar özeti

Bugünkü uygulamada kayıtlı CLI principal için taşınabilir bir “session token” yoktur. `panel/auth_store_v2.py` sunucu tarafı key kaydında 32 bayt HMAC secret'ını `secret_b64` olarak tutar; `panel/auth.py` bu anahtarla imzalanmış her bir HTTP isteğini doğrular ve nonce tüketir. `canonical_request_bytes()` gelecekteki imzalayıcının üretmesi gereken byte sözleşmesini sağlar, ancak CLI imzalayıcı, client key store, token çıkarma endpoint'i veya session binding/expiry akışı bu kaynakta yoktur. İstek timestamp penceresi, anahtarın oturum ömrü değildir.

Karar: Uygulama yapılacaksa raw anahtarı argv, ortak dosya, environment variable, sohbet, receipt veya log ile taşımayın. Aynı UID içindeki işçi süreçler birbirinden güvenlik sınırı oluşturmadığı için, **FD/session pipe yalnız kazara sızıntıyı ve kalıcı kopyaları azaltan aktarım tercihidir; aynı UID'ye karşı gizlilik garantisi değildir.** Aynı UID'deki untrusted worker'dan anahtarı gerçekten gizlemek gerekiyorsa anahtar işçiye hiç verilmemeli; ayrı servis UID'sinde çalışan broker kendi adına imzalamalı ve dar işlem politikasını uygulamalıdır. Mevcut tek UID MVP bunu sağlamaz; hostile same-UID süreç tehdit modelinde token tabanlı CLI oturumu **NO-GO**'dur.

## Mevcut protokolün sınırı

- Store `keys` map'inde `principal_id`, `audience`, exact scope'lar, `secret_b64`, validity ve `revoked` alanları vardır. Store ve lock owner-only (`0700` dizin, private dosyalar) tasarlanmıştır; store modül docstring'i aynı UID/root süreçleri açıkça yerel güven sınırında sayar.
- İstek imzası audience, principal, key ID, HTTP method/path, body digest, timestamp ve nonce'u kapsar. Sunucu kaydı bulur, scope/validity/revocation kontrolü yapar, HMAC-SHA-256'yı karşılaştırır ve nonce'u tüketir. `VerifiedPrincipal` bu başarılı **isteği** temsil eder; kalıcı browser/agent session'ı ya da bearer token değildir.
- Kodda client signing key'in nasıl alınacağı ve CLI prosese nasıl ulaştırılacağı henüz tasarlanmamıştır. Provision, enrollment, rotation ve revoke araçları da yoktur. Mevcut operasyon notları bu yaşam döngüsünü offline host-side kabul kapısı sayar.
- Oturum köprüsü / child-process belgeleri provider credential'larının parent env'inden child'a kopyalanmaması, environment ve FD allowlist'lerinin ayrılması, `close_fds=true` ve gerekli değilse `pass_fds` boş tutulması gerektiğini söyler. Bunlar gelecekteki runner sözleşmeleridir; mevcut provider/session runner varmış gibi yorumlanmamalıdır.

## Aktarım seçenekleri

| Yöntem | Sızıntı yüzeyi ve aynı UID değerlendirmesi | Karar |
|---|---|---|
| Komut satırı argümanı | `/proc/<pid>/cmdline` çalışan süreç argümanlarını gösterir; shell history, process listesi ve hata/telemetri de ek kopya yaratabilir. | **Reddet.** Secret veya token hiçbir zaman argv'ye konmamalı. |
| Ortak dosya (`0600`) | Kalıcı kopya, yedek ve crash/snapshot kapsamına girer. `0600` başka UID'leri sınırlar; dosya sahibiyle aynı UID'deki süreçleri ayırmaz. | **Reddet.** Session başına dosya, repo/KOK/shared temp veya genel credential cache oluşturma. |
| Environment variable | Secret process başlangıç environment'ına girer, child'lara kopyalanabilir ve hata ayıklama/ortam dökümlerine sızabilir. Linux `/proc/<pid>/environ` başlangıç environment'ını gösterir ve erişimi ptrace erişim denetimine bağlıdır. `unsetenv`/parent ortamını temizlemek önceki kopyaların silindiği kanıtı değildir. | **Secret taşıma kanalı olarak kullanma.** İzinli minimal environment içinde yalnız secret olmayan selector/FD numarası gibi metadata taşınabilir. |
| İzinli session FD / pipe | Path veya argv/env kopyası gerektirmez, ömrü launcher/child'e bağlanabilir ve tek hedef child'a `pass_fds` allowlist'i uygulanabilir. FD `CLOEXEC` varsayılanında kapalı kalmalı; yalnız seçilen child'a kasıtlı geçirilmelidir. | **Aynı UID sınırında tercih edilen taşıma, ama gizlilik izolasyonu değildir.** Raw key yerine brokered imza veya dar ömürlü credential mümkünse onu taşı. Kısa aktarımda tek kullanımlık pipe; tekrar okuma gerekiyorsa private memfd tasarlanabilir. |
| Ayrı UID broker + dar IPC | Secret broker UID'sinde kalır; worker yalnız imza/izinli işlem isteği yollar. Socket peer UID gerçek OS tarafından alınmalı ve UID→principal/policy bağı operatörce yönetilmelidir. | **Aynı UID saldırganına karşı gizlilik gerekiyorsa hedef model.** Mevcut sistemde kurulmuş değildir; işçi/operatör anahtarı custody'si ve route-scope ayrı tasarlanmalıdır. |

### `/proc` nüansı

Linux'ta `/proc/<pid>/environ` ve `/proc/<pid>/fd` erişimi ptrace access mode kontrollerine tabidir. Kontrol gerçek/effective/saved UID/GID uyumu, hedef sürecin dumpable durumu, capability ve LSM/Yama gibi host politikalarına bağlıdır. Bu yüzden “aynı UID her koşulda her `/proc` içeriğini okuyabilir” demek doğru değildir; ancak ürün tasarımı da `/proc`'ün kapalı olacağını varsayıp raw secret'ı env/FD'ye koymamalıdır. `/proc/<pid>/fd` bağlantısının görünmesi ile bağlı inode'u tekrar açma izni ayrı kontrollerdir.

`memfd_create()` anonim, volatile backing'li bir file descriptor üretir; descriptor `fork` ile miras alınabilir ve `MFD_CLOEXEC` yoksa `execve` üzerinden açık kalır. Descriptor adının `/proc/self/fd` görünümünde gösterilmesi de mümkündür. Dolayısıyla memfd disk dosyası riskini azaltır; process memory/FD incelemesini veya aynı UID'deki çalıştırıcı/child'ın secret'ı kopyalamasını çözmez. SCM_RIGHTS de descriptor referansını başka sürece kopyalar, gizlilik sınırı oluşturmaz.

## Uygulanırsa session sözleşmesi

1. **Uzun ömürlü key ile session bilgisini ayır.** Auth store'daki kayıtlı key bir HMAC shared secret'tır. Mevcut server ayrı session token kabul etmiyor. Gelecekte gerçek session credential istenirse issuance, audience/principal/session bağlama, kısa `expires_at`, revoke ve server doğrulaması ayrıca tasarlanıp uygulanmadan mevcut key'i “session token” diye adlandırma.
2. **İşçi sürece anahtar verme.** Güvenilir runner veya ayrı broker imzayı kendisi üretir. Ham secret yalnız onaylı signer/broker bileşeninin belleğinde açılır; untrusted model/provider child'a parent env'i veya dosya erişimiyle sızmaz. Aynı UID altında bu bileşenler arasında güven sınırı kurulamadığı kabul edilir.
3. **FD kullanımı gerekiyorsa daralt.** `shell=False`, sabit executable, minimal environment, `close_fds=true`; descriptor'ı önce close-on-exec aç, yalnız hedef child için açık `pass_fds` kullan. Secret'ı argv/env'e koyma. FD'yi mümkün olan en kısa süre açık tut, okuma/yazma kapsamını belirle, çocuğun türettiği alt süreçlere geçmesine izin verme ve bütün süreç ağacını kontrollü kapat.
4. **Kalıcı receipt'ten çıkar.** Receipt/outbox yalnız session/key ID, scope, validity, girişim/generation ve içeriksiz güvenli sonuç sınıfı gibi secret olmayan metadata tutar. Raw key, token, signature, auth header, environment dump veya geri üretilebilir secret materyali kaydedilmez. ID/digest de hassas işlem korelasyonu olabileceğinden erişim/retention'a tabidir.
5. **Uygulama temizliği best-effort'tür.** Session bitince parent ve child descriptor'larını kapat, child process group'u sonlandırıp reap et, temporary buffer'ları mümkünse temizle ve env değişkenlerini kaldır. Python string kopyaları, runtime allocator, core dump, swap, tracing veya crash artifact'lerinden kriptografik silinme iddiası verme. Anahtar sızıntısı şüphesinde yalnız memory cleanup'a güvenme; revoke gerekir.

## Temizleme, expiry ve revoke ölçütleri

| Olay | Gereken davranış |
|---|---|
| Normal session kapanışı | İşçi/adapter sürecini kapatıp reap et; açık FD'leri kapat; session state'ini süresi dolmuş yap; receipt/log'da secret bırakma. Uzun ömürlü principal key, başka kabul edilmiş client'lar da kullanıyorsa otomatik revoke edilmez. |
| Session timeout veya disconnect sonucu belirsiz | Yeni token/nonce ile sessizce tekrar deneme yok. Bağlı isteğin sonucu `unknown` kalır ve mevcut receipt sözleşmesiyle uzlaştırılır. Session credential expiry yeni işlem yetkisini kapatmalı; eski imzalı istek timestamp penceresi bunun yerine geçmez. |
| Raw secret argv/env/shared file/log/screen/core dump'ta bulundu, beklenmeyen child'a geçti veya consumer sahibi bilinmiyor | İlgili key'i compromise say; consumer/oturumları durdur; key'i onaylı lifecycle yordamıyla `revoked` yap; yeni key'i ayrı güvenli provisioning ile ver; eski key'in reddedildiğini bağımsız readback ile doğrula. |
| Client kaybı/offboarding, scope gereksizleşmesi veya `expires_at` dolması | Kayıtlı key'i kullanım dışı bırak/revoke et; sırf key artık kullanılmıyor diye kaydı silme. Gereksiz uzun overlap bırakma. |
| Auth store eski backup'tan döndü veya revoke durumu kanıtlanamıyor | Eski key yeniden aktif olmuş olabilir. Consumer'ları kapalı tut; etkilenen key'leri compromise say ve offline recovery/re-provision kararı olmadan auth'ı açma. |

Bugünkü store doğrulayıcısı `revoked`, validity, scope ve key bağını kontrol eder; ancak onaylı bir CLI key lifecycle aracı veya session revoke endpoint'i yoktur. Bu nedenle tablo gelecek işletim kabul ölçütüdür, uygulanabilir komut dizisi değildir. `AuthStateStore.transact()`'i canlı state üzerinde elle çağırmak bu görevin kapsamında değildir.

## Go / No-Go ölçütleri

**Go** ancak credential consumer ve süreç yaşam döngüsü sabitlendiğinde; key tek bir onaylı signer/broker'a scope ve expiry ile bağlandığında; argv/env/shared file/receipt/log testlerinde secret görünmediği; FD pass listesi tek hedefle sınırlı ve child bitince kapandığı; stop/revoke/readback ve backup/restore prosedürü kabul edildiğinde düşünülebilir. Testler secret değerini çıktılamadan yalnız bulgu sayısı/kanal adı kaydetmelidir.

**No-Go**: untrusted CLI/provider child raw key'i alacaksa; aynı UID'deki başka süreçlerden key'i gizlemek bir gereksinimken ayrı UID/broker yoksa; key environment, argv veya ortak dosyada tutuluyorsa; session expiry/revoke/readback belirsizse; ya da auth lifecycle aracı/operatör kabulü bulunmuyorsa. Mevcut kaynakta client signer ve provisioning lifecycle olmadığı için bugünkü durum **NO-GO for authenticated CLI sessions**; auth kapalı kullanımın mevcut olması bu tasarımı uygulamaz.

## Kaynaklar

### Yuva kaynakları ve kararları

- `panel/auth.py`: `canonical_request_bytes()`, `HMACAuthenticator.verify_request()`, `VerifiedPrincipal`.
- `panel/auth_store_v2.py`: key alanları, owner-only store ve aynı UID/root süreçleri için trust-boundary açıklaması.
- `docs/auth-state-v2-operations.md`, `docs/auth-key-lifecycle-api-design-462.md`, `docs/auth-key-rotation-revoke-offline-501.md`: provisioning, expiry, revocation, backup ve `CommitUnknown` sınırları.
- `docs/session-adapter-workdir-process-boundary-498.md`: secret'sız minimal child environment, `close_fds`, dar `pass_fds`, aynı UID tehdidi.
- `docs/persistent-session-receipt-contract-527.md`, `docs/session-bridge-persistent-receipt-store-504.md`: receipt/outbox'a credential kopyalamama ve belirsiz gönderim sonucu.
- `docs/agent-uid-host-operations-523.md`, `docs/local-data-threat-model.md`: UID izolasyonu ve ortak dosya/credential riskleri.

### Linux process/FD kaynakları

- [`proc_pid_cmdline(5)`](https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html) — process command line görünümü.
- [`proc_pid_environ(5)`](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html) — başlangıç environment görünümü ve ptrace erişim kontrolü.
- [`proc_pid_fd(5)`](https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html) ve [`ptrace(2)`](https://man7.org/linux/man-pages/man2/ptrace.2.html) — FD bağlantılarına erişim ve host'a bağlı ptrace access-mode kuralları.
- [`memfd_create(2)`](https://man7.org/linux/man-pages/man2/memfd_create.2.html), [`execve(2)`](https://man7.org/linux/man-pages/man2/execve.2.html), [`unix(7)`](https://man7.org/linux/man-pages/man7/unix.7.html) — anonymous FD, CLOEXEC/inheritance ve SCM_RIGHTS descriptor aktarımı.

Bu not Linux man-pages ve yerel kaynak/karar belgelerine dayanır; makinenin `/proc` mount'u, Yama/LSM ayarları, dumpability, çalışan süreçleri veya canlı auth state'i incelenmedi. Host'a özgü erişim sonucu çıkarılmaz.
