# Yuva #586 — Auth-off görev mutasyonu için yerel süreç sınırı

**Durum:** Tasarım kararı; canlı API, auth ayarı ve servis değiştirilmedi.
**Kapsam:** Auth kapalıyken loopback `POST /api/gorev` üzerinden gelen görev
mutasyonlarında yerel süreç kimliğinin ne ölçüde ayırt edilebildiği.

## Karar özeti

Auth-off `POST /api/gorev`, istekteki `kimden` alanını gerçek süreç kimliği
olarak doğrulamaz. Loopback, Host/Origin ve içerik türü kontrolleri uzak ağ ve
tarayıcı kaynaklı bazı istekleri daraltır; yerel çağıranı doğrulamaz. Aynı
UID'deki agent veya başka bir yerel süreç görev alabilir, atayabilir, teslim
edebilir ya da yetkili CLI akışlarının sunduğu diğer mutasyonları isteyebilir.
İşlem kaydındaki aktör auth-off durumda `local_unverified` sınıfındadır.

Bu nedenle mevcut davranış yalnız tüm aynı UID süreçlerinin güvenilir kabul
edildiği tek kullanıcılı yerel MVP sınırında **koşullu GO**'dur. Agent'ların
güvenilmeyen içerik işlediği veya agent'ların görev mutasyonu yapmaması gereken
çok-agent kurulumunda **NO-GO**'dur. Mevcut çok-agent/same-UID çalışma modeli
operatör-only görev mutasyonu olarak sunulamaz.

Tercih edilen hedef, veri ve görev defterini sahiplenen ayrı servis UID'si
altındaki broker'dır. Broker UDS peer credential (`SO_PEERCRED`) ile işletim
sistemi UID'sini doğrular, UID'yi operatör/agent principal'ına operator-owned
eşlemeyle bağlar ve işlem bazlı izin uygular. Ayrı UID veya UDS tek başına
yeterli değildir: doğrudan erişilebilir auth-off HTTP yazma yolu ve broker'ı
atlayan dosya yazıcıları kapatılmalıdır. HMAC, broker üzerinde doğrulanmış
istemci principal'ı için ek katman olabilir; aynı UID içindeki süreçleri
birbirinden ayırmaz ve custody/lifecycle olmadan operator kimliği kanıtı
oluşturmaz.

## Bugünkü sınır

- `panel/server.py` auth gate kurulmamışken `/api/gorev` payload'ını görev
  işlemesine geçirir. Gövde `kimden` alanı yerel, doğrulanmamış aktör
  beyanıdır; istemci process UID/PID'siyle bağlanmaz.
- Auth gate açıkken doğrulanmış principal ve route/işlem policy'si aranabilir;
  bu mod varsayılan değildir. Auth kapısını açmak tek başına anonim GET/HTML
  yollarını, browser oturumunu veya eski CLI kopyalarını korumaz.
- Loopback yalnız uzak ağ bind'ini daraltır. Aynı network namespace'teki
  farklı UID'ler de loopback HTTP'ye bağlanabilir. Aynı UID süreçleri dosya
  izinleri, aynı UID UDS kontrolü veya o UID'nin erişebildiği HMAC anahtarıyla
  birbirinden ayrılamaz.
- `Host`, `Origin`, CORS, JSON Content-Type ve CSRF kontrolleri gerekli kaynak
  kısıtları olabilir, ancak yerel programın kendini başka `kimden` değeriyle
  tanıtmasını engelleyen kimlik doğrulama değildir.
- Kanonik olmayan/eski CLI kopyaları ve doğrudan görev verisi yazıcıları ayrı
  geçiş/tek-yazıcı kabul kapısıdır. Panel broker'ı eklemek onları kendiliğinden
  ortadan kaldırmaz.

## Seçenekler

| Seçenek | Sağladığı gerçek sınır | Kalan açık / karar |
|---|---|---|
| **Auth-off loopback HTTP** | Uzak arayüzlerde dinlemeyi önler; tek UID'nin yerel kullanımını kolaylaştırır. | Süreç kimliği veya principal kanıtlamaz. Aynı UID ve aynı namespace'teki süreçler POST atabilir. Yalnız tüm bu süreçler güvenilir kabul edilirse koşullu GO. |
| **Farklı UID + mevcut loopback HTTP** | Dosya izinleriyle doğrudan veri dosyalarına erişim ayrılabilir. | Başka UID aynı namespace'te loopback'e erişebilir; auth-off POST açık kalır. Tek başına NO-GO. |
| **UDS + `SO_PEERCRED`** | Kernel bağlantıdaki UID/GID/PID'yi bildirir; sunucu izinli UID'leri ret edebilir. | Aynı UID'li agent'ları ayırmaz, uygulama/agent adını kanıtlamaz; browser doğrudan UDS kullanamaz. Broker'ın UID→principal ve işlem policy'si gerekir. |
| **Ayrı servis UID'si + özel UDS broker** | Servis UID'si veriyi sahiplenir; socket izinleri ve peer UID allowlist'i farklı UID'leri sınırlar. Tek mutasyon kapısı principal/policy uygulayabilir. | Önerilen yerel hedef. Agent başına ayrık UID, tüm writer geçişi, HTTP bypass'ının kapatılması ve browser için ayrı session/proxy yolu gerekir. Host kurulumu ve kabul kanıtı olmadan henüz GO değildir. |
| **HMAC imzalı HTTP** | Anahtarı tutan istemci için principal, audience, kapsam ve imzalı isteği doğrulayabilir. | Aynı UID'deki süreç anahtarı/store'u okuyabilir veya aynı güven alanındaki signer'ı kullanabilir. Browser'a sır verilemez; mevcut POST HMAC'i GET/session sağlamaz. Broker/OS izolasyonunun yerine geçmez. Yalnız ayrı custody ve yaşam döngüsüyle ek katman. |
| **UID + UDS/broker + HMAC** | Kernel peer UID ile cihazdaki bağlantı sınırı; HMAC ile broker dışında doğrulanmış istemci principal'ı birleştirilebilir. | İki kimlik kaynağının eşleşme ve scope kuralı açık olmalı. HMAC key'i agent UID'lerinden korunmalı; broker ele geçirilmesi hâlâ güven kökünü ihlal eder. |

## Önerilen hedef sözleşme

1. **Servis sahipliği:** Broker/API ve görev veri kökü ayrı, agent erişimi
   olmayan servis UID'sine aittir. Agent UID'leri ve insan operatör oturumu
   broker UID'sinden ayrıdır. Grup/ACL paylaşımı, aynı UID süreç izolasyonu
   yerine kullanılmaz.
2. **Taşıma:** Agent/CLI istemcileri yalnız broker'ın private Unix socket'ine
   bağlanır. Socket dizin/izinleri servis sahibindedir; broker her kabul edilen
   bağlantıda `SO_PEERCRED` alır, bilinmeyen UID'yi varsayılan ret eder.
   Backend'in auth-off loopback HTTP'si agent'ların erişimine açık bırakılmaz.
3. **Principal eşlemesi:** UID→principal ve UID→işlem kapsamı operator-owned,
   sürümlü konfigürasyondan gelir. `kimden`, `--from`, body role, roster veya
   görünen Yuva adı eşleme girdisi/kanıtı olamaz. Aynı UID'ye konmuş iki agent
   tek OS principal sayılır ve birbirinden ayrılamaz.
4. **İşlem yetkisi:** Broker her işlem için fail-closed policy uygular:
   görev claim/teslim yalnız atanmış worker; atama/iptal yalnız onaylı
   operator/admin; inceleme yalnız reviewer policy. Doğrulanmış bağlantı
   olması her işleme izin vermez. Aktör kaydı broker'ın belirlediği principal
   ve auth kaynağını taşır.
5. **Tek yazıcı:** Panel, CLI, agent ve bakım araçları aynı broker/kanonik
   writer sözleşmesine geçer. Eski CLI kopyaları ve doğrudan dosya yazımı
   servis verisine erişememelidir; geçişi tamamlanmamış her writer NO-GO
   sebebidir.
6. **Browser:** Browser UDS'ye bağlanamaz ve HMAC secret taşımaz. Gerekiyorsa
   doğrulanmış session broker/ters vekili kullanılır; backend'e doğrudan
   erişim kapatılır veya aynı session/policy kontrolünü uygular. Cookie
   mutation'ları CSRF kontrolü, session sona erme/iptal ve fail-closed hata
   davranışı ister. GET/HTML erişimi ayrı route policy'sidir.
7. **Arıza ve geri dönüş:** Socket peer bilgisi, UID map, policy, store veya
   broker durumu belirsizse mutasyon reddedilir/servis kapalı kalır. Anonim
   auth-off HTTP'ye otomatik geri dönüş yapılmaz.

HMAC ayrıca kullanılacaksa yalnız açıkça provision edilmiş anahtarlar,
operator-controlled principal/scope eşlemesi, revoke/rotation/recovery ve
server-side custody kanıtı sonrası açılır. HMAC'i imzalayan agent'ın aynı UID
altında verifier store'a erişmesi halinde bu ek katman ayrım sağlamaz.

## Go / No-Go matrisi

| Dağıtım / istek | Karar | Gerekçe ve gereken kanıt |
|---|---|---|
| Tek insan operatör, tüm aynı UID süreçleri güvenilir, bu kabul açıkça yapılmış | **Koşullu GO** | Yerel MVP kolaylığı kabul edilebilir; `kimden` alanları doğrulanmamış kalır ve operator-only audit iddiası yapılamaz. Panel portuna erişebilen tüm programlar mutasyon yetkisi paylaşır. |
| Aynı UID'de agent'lar var; agent'ların görev mutasyonu yapması istenmiyor | **NO-GO** | Mevcut OS kimliği bu agent'ları insandan veya birbirinden ayıramaz. Origin/Host, farklı body actor'ü veya HMAC key'i aynı UID altında çözüm değildir. |
| Agent'lar farklı UID'de, backend auth-off loopback HTTP hâlâ erişilebilir | **NO-GO** | Farklı UID loopback'e bağlanabilir; yalnız veri dosyası izinleri POST mutasyonunu durdurmaz. |
| Ayrı broker/service UID + private UDS; HTTP bypass kapalı, per-UID policy ve tüm writer'lar taşınmış | **GO adayı** | Hostta peer credential'ın gerçek UID'yi gösterdiği, reddedilen UID'nin bağlanamadığı, eşlemenin operator-controlled olduğu, veri kökü ve socket sahipliği, eski writer yokluğu ve işlem bazlı retler kanıtlanmalı. Browser yolu ayrıca kabul edilir. |
| HMAC açıldı ancak secret aynı UID'li agent'larla paylaşılabilir veya GET anonim | **NO-GO (operator kimliği için)** | HMAC key custody ve GET/browser kapsamı eksik. Yalnız POST gate'in aktif olması tam sistem kimlik sınırı değildir. |

### Host kabul kanıtı (hedef mimari için)

- Gerçek servis, operator ve her agent UID/PID eşlemesi; servis unit'i,
  executable/release ve etkin veri kökü sahipliği.
- Socket path, parent directory ve mode/owner; broker'ın `SO_PEERCRED`
  sonucunu kullandığı, izinli ve izinsiz UID ile pozitif/negatif bağlantı
  kanıtı.
- Agent UID'sinin broker auth store/key'i ve görev dosyalarını okuyamadığı;
  operator UID'sinin de backend dosyalarına doğrudan yazamadığı kanıt.
- API bind/route envanteri: auth-off HTTP'nin agent namespace'inden erişilemez
  olduğu; `/api/gorev` ve alias/bypass yollarının broker dışında mutasyon
  yapmadığı.
- Bütün CLI/panel/bakım writer envanteri ve eski kopyaların kapatıldığı veya
  veri köküne erişemediği doğrulaması.
- Görev işlemi başına UID→principal→scope eşleşmesi, gövde `kimden` sahteciliği,
  hatalı/bilinmeyen UID, politika/store arızası ve restart durumlarında
  fail-closed kabul sonuçları.
- Browser varsa session, CSRF, logout/revoke, GET/HTML kapsamı ve doğrudan
  backend bypass ret kanıtı.

Bu kayıt hostta bu koşulların sağlandığını iddia etmez. Burada servis/UID,
socket, auth store, environment veya canlı API incelenmedi/değiştirilmedi.

## Kaynaklar

- `docs/local-api-access-decision-451.md` — loopback, UDS, `SO_PEERCRED`, ayrı
  servis UID ve HMAC sınırları.
- `docs/task-principal-gate-539.md` — auth-off aktör etiketinin
  `local_unverified` niteliği ve doğrulanmış principal/policy.
- `docs/panel-local-security-snapshot-557.md` — mevcut panel GET/POST yüzeyi.
- `docs/panel-anonymous-snapshot-data-minimization-574.md` — same-UID ve
  multi-agent için anonim panelin NO-GO değerlendirmesi.
- `docs/operator-hmac-custody-decision-582.md` — HMAC custody ve ayrı UID
  broker hedefi.
- `docs/browser-session-read-scope-583.md` — browser session, GET kapsamı ve
  backend bypass gereksinimleri.
- `docs/shared-repo-data-ownership-533.md` — servis UID'siyle veri sahipliği
  ve broker gereksinimleri.
- `panel/server.py` — auth-off görev dispatch davranışının kaynak dayanağı.

Bu tasarım mevcut auth ayarını açmaz, kod/API/servis/UID/socket değişikliği
yapmaz ve host güvenliğini doğrulanmış saymaz.
