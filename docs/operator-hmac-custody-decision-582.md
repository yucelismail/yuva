# Operatör HMAC anahtarı için custody kararı (#582)

**Karar:** Hedef yerel mimari, agent'lardan ayrı OS UID'lerinde çalışan
operatör imzalayıcı ve verifier/broker'dır; agent süreçleri kendi UID'lerinde
kalır. HMAC anahtarı sadece operatör signer'ı ve güvenilir broker arasında
paylaşılır. Broker UID'si agent'lara verilmez ve broker'ın auth store'u agent
UID'lerinden okunamaz. Bu sınır kurulup hostta doğrulanana kadar `operator`
kaynak etiketi kapalı (`unknown/unverified`) kalır.

**Bugünkü durum:** Bu mimari kurulmuş değildir. İlk local MVP aynı OS UID
varsayımındadır; #578 yalnız boş auth store başlatıcısıdır, key oluşturmaz veya
enroll etmez. HMAC gate varsayılan kapalıdır. Bu belge key üretmez, auth
açmaz, servis/UID/izin değiştirmez ve canlı süreci incelemez.

## Karar ve gerekçe

Operatör imzalayıcıdaki HMAC secret'ı ve sunucudaki verifier secret'ı aynıdır.
İmza principal, audience, scope ve request bytes'ını doğrular; secret'a sahip
her süreç aynı imzayı üretebilir. `admin_principals` allowlist'i principal'a
yetki atar ama secret sahibini ayırmaz. Bu yüzden HMAC, OS/process custody
sınırı yerine geçmez.

Seçilen hedef, **ayrı UID broker + ayrı UID operator signer + agent başına ayrı
UID** modelidir. Signer key'i yalnız onaylı operatör oturumundan kullanır;
broker'ın verifier copy'si ayrı servis UID'sine ait owner-only store'da kalır.
Agent'lar anahtarı, signer sürecini veya broker store'unu okuyamamalı ve
operatör UID'sinde çalışmamalıdır. Broker, doğrulanmış HMAC principal'ını
operator-managed allowlist ve ayrıca provision edilmiş custody işaretiyle
eşleştirir. UI/browser doğrudan secret taşımaz; browser kaynaklı mesajlar için
ayrı session/signer köprüsü tasarlanana kadar auth-off panel yazımı
`unknown/unverified` kalır.

Bu tasarım aynı UID'de çalışan düşmanca süreçlere karşı güvence iddia etmez.
Agent ve signer aynı UID'deyse, server verifier veya signer o UID altında
çalışıyorsa, OS izinleri, ayrı dosya, kısa ömürlü FD, environment, browser
memory veya `0600` dosya bunu düzeltmez. Bu koşullarda `operator` etiketini
açma.

## Seçenekler

| Model | Gerçek sınır | Karar |
|---|---|---|
| **Ayrı UID broker + signer** | Broker/verifier key'i servis UID'sinde; signer key'i yalnız operatör UID'sinde; agent UID'leri ikisinden de farklı. Kernel dosya ve süreç erişimi bu UID'ler arasında sınır sağlar. HMAC yine iki trusted bileşende aynı secret'ı tutar; broker compromisel olursa operator principal taklit edilebilir. UDS varsa `SO_PEERCRED` gerçek peer UID'sini alır; request `kimden`/`--from` değerini principal saymaz. | **Seçildi.** Yerel hostta HMAC'le devam edecekse gerekli custody hedefi. Mevcut Yuva broker/auth deployment'ı değildir; ayrı kabul gerekir. |
| **External signer** | HSM/ayrı host/operatör kontrollü imzalayıcı secret'ı agent hostundan çıkarabilir. Ancak HMAC kullanılıyorsa verifier aynı secret'ı hâlâ tutar; yalnız signer'ı dışarı almak, agent'ların aynı UID'deki server auth store'una erişimini çözmez. Public-key imzalı protokolde server yalnız public key tutar ve private key'i bilmez; bu daha güçlüdür fakat mevcut `HMACAuthenticator` protokolüyle uyumlu değildir. | Ayrı signer UID'si kurulamıyorsa veya host içi agent'lara karşı daha güçlü sınır gerekiyorsa **gelecek alternatif**: public-key verifier'a ayrı mimari görev aç. Mevcut HMAC'i external signer varmış gibi yorumlama. |
| **Mevcut aynı-UID HMAC shared secret** | Auth store `0700/0600`, signer, verifier, browser ve agent aynı güven alanındadır. Aynı UID süreçleri key'i dosya/işlem belleği/FD/environment üzerinden elde edebilir veya signer/verifier kimliğini taklit edebilir. HMAC imzası bu süreçler arasında kimin kullandığını ayırmaz. | **Reddedildi.** Auth kapalı kalır; custody flag'i yok; admin allowlist tek başına `operator` üretemez. |

### Browser ve FD değerlendirmesi

- Browser belleğine HMAC key koymak XSS, extension, debugging/profile ve aynı
  UID'deki süreçlere karşı custody kanıtı değildir. Browser auth'suz mesaj
  gönderirse kaynak `unknown/unverified` olur. Auth açıkken imzasız UI isteği
  reddedilir; bu sınırı aşmak için key'i `panel/ui.html` içine gömme.
- Environment ve argv kullanılmaz: secret process listing, child inheritance,
  debug ve crash yüzeylerine girer. Ortak dosya kalıcı kopya ve backup/restore
  yüzeyidir. `0600` yalnız farklı UID'lere erişimi daraltır.
- FD/pipe `CLOEXEC`, dar `pass_fds` ve kısa ömürle kazara sızıntı/kopyaları
  azaltabilir; descriptor sahibiyle aynı UID'deki untrusted process arasında
  gerçek gizlilik sınırı kurmaz. `memfd` disk kalıntısını azaltır ama aynı UID
  memory/FD erişimini çözmez.
- Broker key'i aynı anda doğrular, scope uygular ve `operator` etiketini üretir;
  verifier UID ve kodu bu nedenle trusted root'tur. Bu UID'ye agent veya genel
  shell erişimi verilirse model başarısızdır. Signer ya da broker ihlalinde
  HMAC ile non-repudiation iddia edilmez.

## Enrollment kapısı

Key enrollment ayrı onaylı offline lifecycle aracı ve işletim makbuzu olmadan
yapılmaz. `yuva auth init` boş store ve stable lock kurar; key enrollment,
audience tüketici eşlemesi veya auth açma değildir.

1. Broker service UID, operator signer UID ve her agent UID'si ayrı olarak
   kurulup sahiplik/izinleri hostta doğrulanır. Kanonik release broker store'una
   ve operator UID'sine yazamaz; agent home/repo'su da bu alanları içermez.
2. Principal, `key_id`, instance/audience ve exact scope'lar önceden onaylanır.
   `operator` principal yalnız operatör sahibine aittir; `POST /api/yaz`
   yetkisi operator etiketi dışında görev/role/provider yetkisi doğurmaz.
3. CSPRNG key, onaylı korumalı kanalla sadece signer'a ve broker verifier
   store'una provision edilir. Secret argv, environment, ortak dosya, Yuva
   sohbeti, receipt, log, screen capture veya agent process'e girmez. Bu
   transferi sağlayan/denetleyen araç henüz mevcut kabul edilmez.
4. Broker allowlist'i ve custody işareti secret tesliminden ayrı, operator
   kontrollü konfigürasyon/revision ile açılır. Store/allowlist/custody
   revision'ları tutarlı değilse `operator` kapalı kalır. `YUVA_AUTH_ENABLED=1`
   ancak GET/browser, task scope, recovery ve host rollout kapıları ayrıca
   kabul edilirse değerlendirilir.
5. Enrollment kanıtı secret içermez: principal/key ID, audience, scope, store
   generation/revision, signer/broker UID sahipleri, teslim/onay zamanı ve
   doğrulama sonucu. Raw key, signature, token veya secret digest kaydedilmez.

## Revoke, kayıp ve recovery

- **Routine revoke/offboarding:** Signer kullanımı durdur; store'da key'i
  `revoked` yap ve onaylı readback ile doğrula; broker allowlist/custody
  revision'ını key kapsamıyla tutarlı güncelle; ilgili signer/agent süreçlerini
  sonlandırıp reopen öncesi yeni credentials/UID map'ini doğrula. Revoke
  uygulaması yoksa manuel JSON edit veya varsayılan deny list'i güvenilir
  lifecycle diye kullanma.
- **Compromise ya da secret'ın aynı UID agent'a sızması:** Key'i compromise
  kabul et. İlgili consumer'ı durdur, key'i revoke et, eski key'i un-revoke
  etme; yeni key/ID ile yeniden enrollment ve signer custody doğrulaması yap.
  Eski key'in reddedildiği kanıtlanana kadar operator etiketi kapalı kalır.
- **`CommitUnknown`, store bozulması ya da eski backup restore'u:** Consumer'ları
  kapalı tut, kör mutation retry/rollback yapma. Store generation tek başına
  anti-rollback anchor değildir; dış trusted kayıtla revoke durumunu
  doğrulayamıyorsan tüm etkilenen key'leri compromise sayıp yeni audience/
  instance ve credential'larla offline re-provision kararı al.
- **UID, broker veya signer değişimi:** Eski UID, socket, key ve cache
  eşlemesini devreden çıkar; eski UID'yi tekrar kullanmadan önce süreç, unit,
  store ve yedek bağlarını denetle. Broker restart/recovery belirsizse tüm
  operator istekleri `unknown/unverified` kalır.

## `operator` etiketi ne zaman kapalı kalır?

Aşağıdakilerden herhangi biri varsa sınıflandırıcı `operator` üretmez; auth-off
ve legacy kanallar `unknown/unverified` kalır:

- Operator signer, broker/verifier veya untrusted agent aynı UID/trust domain
  içinde ve aralarında host tarafından enforce edilen erişim sınırı yok.
- Custody işareti yok, doğrulanmıyor veya admin allowlist/principal/store
  revision'ıyla eşleşmiyor; `source_class`, `kimden`, `--from`, role, browser
  formu ya da imza gibi görünen body alanları tek kanıtsa.
- Principal HMAC doğrulaması başarısız, revoke edilmiş, yanlış audience/scope'ta
  veya `/api/yaz` request'i dışından geldi.
- Key signer'a/agent'a ortak dosya, argv, environment, browser memory veya
  sınırı olmayan FD yoluyla kopyalanmış; kayıp/compromise şüphesi var.
- Enrollment, allowlist güncellemesi, revoke/readback, broker UID eşlemesi,
  store recovery veya backup rollback sonucu belirsiz.
- Browser session/signer bağı henüz tasarlanmamış; HMAC POST gate'in GET, UI
  veya insan oturumunu doğruladığı varsayılmış.

## Mevcut rollout kararı

**NO-GO for `operator` HMAC label.** #578'deki init komutu yalnız boş store
hazırlar; key lifecycle ve ayrı UID custody uygulanmamıştır. #580'deki
`operator_custody_verified` test girdisi production custody kanıtı değildir.
#573 de client signer/token yolunun henüz bulunmadığını ve same-UID FD/env/file
izolasyon iddiası kurmayacağını belirtir. Bu yüzden güncel konfigürasyonda
allowlist tek başına operator kaynağı oluşturamaz.

`operator` ancak ayrı UID mimarisi uygulanıp host kabulü tamamlanır, key
enrollment/revoke/recovery işletimi doğrulanır, custody revision AuthGate'e
fail-closed bağlanır ve ayrı rollout onayı alınırsa açılabilir. Aynı UID MVP
korunursa bu sınıf kapalı kalır; güvenilir kullanıcı talimatı gereken akış
doğrulanmış Yuva operator kanalı yerine ürünün güvenilir oturumında alınmalıdır.

## Kaynaklar

- `docs/auth-init-578.md` — boş auth store ve aynı-UID operator custody sınırı.
- `docs/cli-session-key-storage-boundary-573.md` — CLI signer yokluğu; argv/file/env/FD riskleri.
- `docs/w1b-broker-principal-granularity-513.md`,
  `docs/agent-uid-host-operations-523.md`, `docs/shared-repo-data-ownership-533.md` —
  broker/UID/peer credential sınırları ve host kabulü.
- `docs/auth-state-v2-operations.md`, `docs/auth-key-lifecycle-api-design-462.md`,
  `docs/auth-key-rotation-revoke-offline-501.md` — store, enrollment, revoke,
  `CommitUnknown`, backup ve recovery.
- `docs/auth-state-external-anchor-decision-458.md` — restore/anti-rollback
  sınırı.
- `panel/auth.py`, `panel/auth_store_v2.py`,
  `panel/auth_integration_draft.py` — mevcut HMAC shared-secret doğrulaması,
  store ve feature-off route policy.

Bu karar key üretmez/enroll etmez, HMAC algorithm'i değiştirmez, auth flag'ini
açmaz, UID/broker/service kurmaz ve canlı host/store/process incelemez.
