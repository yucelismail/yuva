# #499 — Yerel provider endpoint ve credential güvenliği

**Durum:** Salt-okunur tasarım notu; credential oluşturma, servis başlatma,
provider bağlantısı veya Yuva auth açma işlemi yapılmadı. Karşılaştırma
çalışma ağacındaki OpenCode HTTP/SSE ve Codex stdio prototiplerine dayanır.
Upstream doküman/şema ile yerel prototype arasında sürüm farkı olabilir.

## Karar özeti

- Mevcut OpenCode adapter HTTP sunucusuna bağlanır; host'u loopback ile
  sınırlar, redirect'i reddeder ve isteğe bağlı Basic Auth bilgisini yalnız
  adapter belleğinde tutar. Loopback aynı UID süreçlerine karşı kimlik doğrulama
  değildir; `http://` üzerindeki Basic Auth şifreleme sağlamaz.
- Mevcut Codex adapter'ı yalnız stdio JSON-RPC trace gözlemidir; dinleyen
  endpoint'i, loopback host'u veya auth katmanı yoktur. Gerçek Codex çalıştırma
  kılavuzu OAuth access token'ı child process ortamına verip provider API'ye
  Bearer olarak gönderir. Bu token Yuva HMAC anahtarı değildir.
- Provider endpoint'i, host ve port güvenilir operator config'inden sabit
  gelmeli; model/task metni, event veya repo içeriğinden URL/credential
  seçilmemelidir. OpenCode için varsayılan `127.0.0.1`, Codex için mevcut
  prototipte `stdio://` dış taşıma yoktur. Wildcard bind, mDNS, port forward,
  public reverse proxy ve auth'suz remote websocket kapalı kalmalıdır.
- Yuva HMAC key'i yalnız Yuva panel API client↔server yetkisi içindir. OpenCode
  Basic Auth, Codex OAuth/API token'ı veya başka bir provider credential'ı
  olarak yeniden kullanılmamalı ve provider'a gönderilmemelidir. Yuva auth
  varsayılan kapalıdır; onaylı key lifecycle/provision aracı henüz yoktur.

## Taşıma ve endpoint karşılaştırması

| Özellik | OpenCode Server | Codex app-server |
|---|---|---|
| Bu checkout'taki taşıma | HTTP JSON ve SSE (`prototypes/opencode-adapter/adapter.py`) | Captured newline-delimited JSON-RPC stdio trace (`prototypes/codex-app-server/adapter.py`) |
| Endpoint | `base_url` ile seçilir; prototype yalnız `http(s)` ve `localhost`/loopback IP kabul eder. URL userinfo/query/fragment reddedilir, redirect izlenmez. | Mevcut prototype'da URL/port/listener yoktur. Gerçek app-server guide stdio giriş/çıkışı gösterir. Upstream ayrıca doğrudan WebSocket seçenekleri yayımlamıştır; bunlar mevcut prototype davranışı değildir. |
| Listener sınırı | Resmi varsayılan hostname `127.0.0.1`; `--hostname`, `--port`, `--mdns` opsiyonları vardır. | stdio'da TCP listener yok. WebSocket/remote taşımaya geçiş ayrı endpoint/auth/TLS incelemesi gerektirir. |
| Endpoint auth | `OPENCODE_SERVER_PASSWORD` HTTP Basic Auth açar; kullanıcı adı varsayılanı `opencode`, `OPENCODE_SERVER_USERNAME` ile değişebilir. | Stdio client/server arasında local pipe'dır; provider inference access token'ı bu transport auth'u değildir. Upstream direkt websocket dokümanı `--ws-auth` auth modlarını listeler; bu auth stdio/remote registration/forwarding için geçerli değildir. |
| Uzak erişim | Basic Auth tek başına TLS değildir. Uzak kullanıma açılacaksa TLS/WSS veya iyi tanımlı korumalı tünel ve ayrı threat review gerekir. | Bu raporda remote/forwarding etkinleştirilmez. Uzak doğrudan WebSocket gerekiyorsa kullanılan sürümün auth davranışı ve endpoint'i doğrulanmadan açılmamalıdır. |
| Reconnect | SSE replay/cursor garantisi belgelenmemiştir; kopma `unknown`, ardından status/history ile salt-okunur uzlaştırma gerekir. | Stdio kopması child/connection neslini kapatır; unresolved RPC sonucu `unknown` kalır. Token refresh için app-server restart + thread resume belgelenir; bu, eski turn'ü tekrar göndermek değildir. |

OpenCode resmi Server sayfası varsayılan `127.0.0.1:4096`, mDNS kapalı ve
Basic Auth için `OPENCODE_SERVER_PASSWORD` bilgilerini verir. CLI `--hostname`
ile başka bind değerlerine izin verir. Bu yüzden `0.0.0.0`, `::`, LAN adresi,
mDNS discovery, SSH/Dev Container port forwarding veya auth'suz reverse proxy
bilinçli olarak kapalı tutulmalıdır. CORS tarayıcı origin politikasıdır; API
kimlik doğrulaması değildir ([OpenCode Server](https://docs.opencode.ai/docs/server/),
[OpenCode CLI](https://docs.opencode.ai/docs/cli/)).

Upstream Codex exec-server README doğrudan WebSocket listener'larında app-server
auth bayraklarının bulunduğunu (`capability-token` veya `signed-bearer-token`),
ve bu bayrakların stdio, remote registration ve forwarding'e uygulanmadığını
belirtir. Bu, #391/#487 yerel stdio prototipine auth özelliği eklenmiş olduğu
anlamına gelmez; sürümlü build ve seçilen transport ayrıca doğrulanmalıdır
([upstream Codex exec-server transport/auth notu](https://github.com/openai/codex/blob/main/codex-rs/exec-server/README.md#authentication)).

## Credential sınırları ve saklama

| Credential | Kullanıldığı sınır | Yerel kaynakta gözlenen / güvenli varsayılan |
|---|---|---|
| OpenCode server Basic Auth password | Adapter → OpenCode local HTTP server | Resmi server env var ile yapılandırmayı tarif eder. Prototype username/password'u kurucudan alıp bellekte tutar ve yalnız o base URL'ye header ekler. Gerçek secret'ı shell satırına literal yazma, repo/config örneğine koyma veya loglama. Aynı UID/root ve process belleği içindeki saldırgana karşı gizlilik iddiası yoktur. |
| Codex OAuth access token / provider API key | Codex child → seçili inference API | Resmi app-server guide app token dosyasını okuyup `ACCESS_TOKEN` olarak child environment'ına vermeyi ve provider isteğinde `Authorization: Bearer` kullanmayı söyler. Parent mümkünse tokenı kendi güvenli credential kaynağından okuyup yalnız ilgili child'a minimal env ile aktarmalı; shell history/`set -x`/diagnostic/stdout/stderr'e düşürmemeli. Tokenı app-server restart/refresh prosedürüne göre yenile; Yuva HMAC key'iyle karıştırma. |
| Yuva HMAC client secret | Yuva client → Yuva panel auth gate | `docs/hmac-client-signing-contract-448.md` 32-byte HMAC secret ve header formatını tanımlar; `docs/auth-state-v2-operations.md` feature-off v2 store, owner-only `0700` root/`0600` dosyalar ve aynı UID sınırını açıklar. Store'daki `secret_b64` uygulama anahtarıdır, şifreli kasa olduğu iddia edilmez. Canlı provisioning, client secret dağıtımı, rotate/revoke aracı yoktur; `YUVA_AUTH_ENABLED` default-off kalır. |
| App-server WebSocket capability/shared secret | Yalnız ayrıca seçilmiş direkt Codex websocket transportu | Upstream README token file/hash ya da shared-secret file seçenekleri tarif eder. Bu repo prototipinde kullanılmıyor. Seçilecekse dosya ACL/owner, token dağıtımı, `wss://`, endpoint auth ve rotasyon ayrı onaylanıp sürümde doğrulanmalıdır. |

Linux'ta `/proc/<pid>/environ`, program `execve()` ile başlatılırken verilen
ilk environment'ı içerir ve erişimi ptrace permission kontrolüne tabidir.
Dolayısıyla environment değişkeni komut argümanına kıyasla process listesine
literal yazmamak için işe yarasa da, aynı güven sınırındaki yetkili süreçlere
karşı secret vault değildir ([`proc_pid_environ(5)`](https://www.man7.org/linux/man-pages/man5/proc_pid_environ.5.html)).
`docs/session-adapter-workdir-process-boundary-498.md` child ortamını
allowlist ile kurmayı; credential gerekirse ayrı broker veya dar ömürlü FD
kanalını değerlendirmeyi, secret'ı argv/env/cwd/prompt/log'a koymamayı önerir.
İşletim sistemi/secret broker bu izolasyonu sunamıyorsa otomatik provider
dispatch açılmamalıdır.

Yuva HMAC imzası `Authorization` değil `X-Yuva-*` header'larında taşınır ve
HMAC yalnız Yuva isteğine kapsam verir. Header logları key'in kendisini
içermeseler de replay denemesinde işe yarayabilecek imza setini, principal,
nonce, timestamp ve scope'u açığa çıkarabilir; HTTP access/debug trace'lerinde
bu başlıklar redakte edilmelidir. OpenCode `Authorization: Basic ...`, Codex `Bearer`
token'ı ve provider URL query parametreleri de her log/error/telemetry/backup
yolundan çıkarılmalıdır. Ham request/response body, prompt, tool output,
exception body ve tam URL gereksiz yere tutulmamalıdır.

## Güvenli varsayılanlar

1. **Endpoint kaynağı güvenilir olsun:** Origin/scheme/host/port config'ten
   gelir, tek değer olarak sabitlenir; prompt/model/task/event kaynağı URL veya
   auth seçemez. URL userinfo/query/fragment reddedilir. Sadece açık route ve
   capability allowlist'i çağrılır. Session/workspace binding ayrıca kontrol
   edilir.
2. **OpenCode local-only:** `127.0.0.1` bind ve yalnız loopback client. Gerekli
   ise password auth açılır; HTTP loopback'te Basic Auth'ın TLS olmadığını ve
   aynı makine süreçlerine karşı yetki sınırı oluşturmadığını kabul et. Redirect
   izlemesini kapalı tut; HTTPS kullanılıyorsa certificate doğrulamasını
   gevşetme. `localhost` DNS çözümlemesini ve her yeni deployment sürümünü
   doğrula; aynı allowlist dışına çözülüyorsa bağlantıyı kes.
3. **Codex stdio-only:** Yalnız app-server child'ını açık executable/config ile
   başlat; shell string interpolation yapma. Child fd'leri, cwd ve env
   sınırlandırılır. Inbound provider URL/config yazılabilir ise yalnız izinli
   HTTPS host listesini kabul et; auth header başka origin'e yönlenmemelidir.
4. **Secret minimizasyonu:** Secret komut satırı literal'i, Yuva mesajı, task
   notu, source, exception, shell history, stdout/stderr, debug log veya genel
   artifact'e konmaz. Env zorunluysa yalnız ilgili child'a minimum env aktarılır;
   same-UID/process-memory tehdidi ayrı OS hesabı veya broker gerektirir.
5. **Ağ erişimi kapalı:** OpenCode `0.0.0.0`/`::` bind, mDNS, dış port publish,
   auth'suz proxy ve CORS'u auth yerine kullanma kapalıdır. Codex stdio dışı
   listener bu prototip için kapalıdır; özellikle auth/TLS kesinleştirilmeden
   wildcard WebSocket, port-forward ve public listener açılmaz.
6. **Güvenli log:** Yalnız güvenli hata sınıfı, status code, opaque correlation
   ID ve sonuç kaydedilir. `Authorization`, `X-Yuva-*`, password/token,
   request body, prompt, tool output, raw SSE, exception repr ve URL query
   redakte edilir. Redactor hata verirse raw fallback yoktur.

## Reconnect ve credential rotation

| Olay | OpenCode | Codex app-server |
|---|---|---|
| Stream/process kopması | SSE `complete=false` veya hata: `unknown`; yeni bağlantı generation'ı, status + message history readback; replay garantisi yok, otomatik resend yok. | Child EOF/timeout: unresolved request/approval `unknown`/`pending_unknown`; yeni process generation'ı; eski JSON-RPC ID yanıtını yenide eşleştirme. |
| Credential yenileme | Basic Auth password değişimi için yeni credential güvenli kaynaktan alınmalı; eski bellekteki adapter kapatılıp yeni client oluşturulmalı. Bu prototipte dynamic reload/rotation yok. | Resmi guide yeni access token alınmasını, app-server'ı yeni `ACCESS_TOKEN` ile restart etmeyi ve mevcut thread'i resume etmeyi söyler. Eski unresolved turn idempotent sayılmaz ve tekrar gönderilmez. |
| Credential reddi | 401/403'ü anonim fallback, alternatif host denemesi veya prompt retry olarak ele alma; operatörce endpoint/audience/key state doğrulansın. | Auth/provider error'ı token/endpoint hatasıdır; yeni token veya host config'i ancak kontrollü operatör akışından alınır. Pending inference sonucu kesin değilse `unknown`. |
| Audit | Yalnız rotation eylemi, key id (secret değil), zaman, sonuç ve etkilenen client/session scope'u; payload yok. | Token değeri yok. Child restart zamanı ve thread ID ancak gerekli/sınırlı receipt metadata'sında; access token veya Authorization header asla yok. |

## Açık kapılar

- OpenCode için hedef instance `/doc` schema/version, hostname çözümü, bind
  adresi, TLS, Basic Auth config'i, capability allowlist, process UID ve
  secret kaynağı deployment bazında doğrulanmalıdır. Bu rapor canlı ayar
  okumadı.
- Codex stdio dışında WebSocket/remote/exec-server kullanımı seçilirse
  transport'a özgü auth/TLS/reconnect modeli, upstream source sürümü, endpoint
  allowlist ve network exposure yeni inceleme ister. `--ws-auth` bayraklarının
  stdio'yu koruduğu veya remote forwarding'e yayıldığı varsayılmamalıdır.
- Yuva auth state/key lifecycle için approved provisioning, client delivery,
  rotation/revoke, backup/restore ve incident prosedürü gerekir. V2 dosya
  izinleri aynı UID süreçlerini birbirinden ayırmaz; HMAC feature-off olması
  canlı deployment konfigürasyonunu kanıtlamaz.
- Yuva'daki ayrı #507 işi provider başına secret kaynağı/işletim prosedürünü
  netleştirmelidir; bu not credential üretmez, depolamaz veya teslim etmez.

## Kaynaklar

- [OpenCode Server](https://docs.opencode.ai/docs/server/) — bind varsayılanı,
  host/port, mDNS, CORS ve Basic Auth.
- [OpenCode CLI](https://docs.opencode.ai/docs/cli/) — `serve` ve auth env
  değişkenleri.
- [Codex app-server / Sign in with ChatGPT](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
  — child process `ACCESS_TOKEN`, Bearer inference, stdio ve token refresh.
- [Codex exec-server authentication](https://github.com/openai/codex/blob/main/codex-rs/exec-server/README.md#authentication)
  — upstream doğrudan WebSocket auth sınırları; yerel prototype ile aynı
  feature olduğu iddia edilmez.
- [`proc_pid_environ(5)`](https://www.man7.org/linux/man-pages/man5/proc_pid_environ.5.html)
  — Linux initial process environment erişim kontrolü.
- Yerel: `prototypes/opencode-adapter/adapter.py`,
  `prototypes/opencode-adapter/README.md`,
  `prototypes/codex-app-server/README.md`,
  `docs/opencode-session-bridge-options-472.md`,
  `docs/hmac-client-signing-contract-448.md`,
  `docs/auth-state-v2-operations.md`,
  `docs/session-adapter-workdir-process-boundary-498.md`.

Salt-okunur kaynak/doküman incelemesi yapıldı. Kod, auth state, credential veya
servis değiştirilmedi; test, runtime ve canlı OpenCode/Codex/Yuva bağlantısı
çalıştırılmadı.
