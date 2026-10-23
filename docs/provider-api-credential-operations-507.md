# Yuva ve yerel provider credential'ları: işletim notu (#507)

**Durum:** çevrimdışı işletim önerisi; secret oluşturulmadı, okunmadı veya
servise verilmedi. Çalışma ağacında #499 için kalıcı tasarım raporu
bulunamadığından bu ek, #499 görev kapsamı, #472 OpenCode araştırması,
`prototypes/opencode-adapter/README.md` ve güncel resmi OpenAI app-server/
authentication belgelerine dayanır. Dağıtılmış bir kurulumda gerçek endpoint,
versiyon ve auth seçimi ayrıca doğrulanmalıdır.

## Birbirinden ayrı tutulacak sırlar

| Sır | Kimlik doğruladığı | Yerel saklama/başlatma önerisi |
|---|---|---|
| OpenCode provider API key'i veya `opencode serve` Basic Auth parolası | İlki model/provider hesabını; ikincisi yerel OpenCode HTTP server'ına istemci erişimini | Provider key'i OpenCode'un hedef sürümde sunduğu yerel auth mekanizmasında tut; sürüm/OS keyring desteği doğrulanmıyorsa owner-only OS secret store'dan yalnız server başlarken çöz. `OPENCODE_SERVER_PASSWORD` ve isteğe bağlı username'i kaynak/config dosyası, CLI argümanı veya Yuva mesajı yerine servis credential kaynağından runtime ortamına ver. |
| Codex'in upstream hesabı/API credential'ı | Codex'in OpenAI inference istekleri; ChatGPT sign-in ile Platform API key farklı hesap/billing bağlamıdır | Codex yerel auth cache'i için kullanılabilir ve zorunluysa `cli_auth_credentials_store="keyring"`; `auto` keyring yoksa `CODEX_HOME/auth.json` dosyasına düşebilir. `file` seçeneğinde `auth.json` token içerir ve parola gibi korunur. Geçici işte process-only `ephemeral` veya güvenilen automation için secret manager'dan kısa ömürlü env kullan. |
| Codex app-server client→server WebSocket tokenı/shared secret | App-server WebSocket bağlantısının kendisi; upstream inference credential'ı değildir | Server tarafında ayrı, yüksek entropili token için `--ws-token-file` veya signed-bearer shared-secret file kullan; yalnız server credential dosyasının mutlak yolunu alsın. İstemci raw token'ı OS secret store'da tutsun, gerekiyorsa env değişken adıyla versin. `--ws-token-sha256` yalnız server verifier'ıdır; client'ın raw token'ını saklama ihtiyacını kaldırmaz. |
| Yuva HMAC anahtarı | Yuva API principal/scope imzası | Provider credential'larından ayrı Yuva auth store/provisioning sözleşmesini kullan. HMAC key'i provider adapter'a, OpenCode Basic Auth'a veya Codex app-server bearer alanına koyma. |

Bu sırlar birbirinin yerine geçmez. Özellikle Codex WebSocket auth tokenı ile
Codex'in OpenAI/ChatGPT upstream credential'ı, ayrıca Yuva HMAC key'i farklı
amaçlar içindir. Codex app-server için resmi doküman `stdio`/Unix socket'i
yerel taşıma seçenekleri olarak; uzak WebSocket için auth ve TLS'i belirtir.
Mevcut dokümanda WebSocket taşıması deneysel/desteklenmeyen olarak nitelenir;
uzak dinleyiciyi auth/TLS olmadan açmak uygun değildir.

## Kaynağa göre işletim

### OpenCode local server ve provider key'i

- #472'de incelenen resmi OpenCode Server belgesine göre `opencode serve`
  loopback varsayılanıyla çalışır; `OPENCODE_SERVER_PASSWORD` Basic Auth'ı
  etkinleştirir ve username ayrıca yapılandırılabilir. Bunlar startup
  credential'larıdır; parola URL'ye veya `--password ...` gibi argümana
  eklenmemeli.
- Interactive terminal yerine servis yöneticisi kullanılacaksa parolayı servis
  yöneticisinin korumalı credential kaynağında tut; servis başlarken yalnız
  OpenCode process'inin ihtiyacı olan env/file descriptor/file olarak aç. Unit
  dosyasında literal `Environment=...SECRET...`, repo `.env`, project config,
  shell script içine gömülü değer veya genel erişilebilir config kullanma.
- OpenCode model provider key'i ile server Basic Auth ayrı saklanmalı ve ayrı
  döndürülebilmeli. Hedef OpenCode sürümünün provider login/key store davranışı
  doğrulanmadan kimlik bilgisinin nerede persist edildiğini varsayma. Store
  seçeneği yoksa service başlatıcısı secret manager'dan çözmeli ve değeri
  command-line argümanına koymamalı.
- Tek makinede loopback, farklı süreçleri kimliklendirmez; aynı OS UID'li süreç
  localhost'a istek atabilir. Basic Auth da aynı UID altındaki zararlı süreçten
  tek başına koruma değildir. Ayrı güven sınırı gerekiyorsa provider'ı ayrı OS
  UID/service account altında çalıştır, secret dosyalarını yalnız o UID'ye aç
  ve listener'ı yalnız gereken loopback/socket yoluyla sınırla. LAN/tünel
  erişimi gerekiyorsa TLS veya güvenli tünel + auth gerekir.

### Codex CLI/app-server

- Kişisel Codex CLI auth cache'i `CODEX_HOME` altındadır. Resmi doküman store
  seçeneklerini `file`, `keyring`, `auto`, `ephemeral` olarak tanımlar:
  `keyring` OS credential store yoksa hata verir; `auto` file fallback yapar;
  `ephemeral` credential'ı yalnız process belleğinde tutar. Persist gerekli ve
  OS keyring çalışıyorsa `keyring` seç; fallback kabul edilmiyorsa `auto`
  seçme. File auth kullanılıyorsa `CODEX_HOME` erişimini owner ile sınırla ve
  `auth.json`'ı secret kabul et.
- OpenAI API key ile Codex'e giriş yapmak Platform API kullanımını/faturalamasını
  seçer; ChatGPT sign-in ise workspace izin/entitlement bağlamını kullanır.
  Güvenilir headless işlerde uygun credential türünü operatör seçmeli. ChatGPT
  access token yalnız ilgili trusted local automation kullanımına ve erişim
  koşullarına göre değerlendirilmeli; genel API key yerine geçtiği varsayılmamalı.
- App-server `--listen stdio://` veya desteklenen yerel Unix socket kullanıyorsa
  stdio pipe/Unix socket dosya sahibi ve süreç sınırı korunmalı. TCP/WebSocket
  dışarı açılacaksa auth flag'i ve TLS/proxy güvenlik sınırı önceden
  etkinleştirilmeli; listener'ın aynı host içindeki yetkisiz süreçlere de
  erişebileceği hesaba katılmalı.
- WebSocket sunucu token dosyası veya shared-secret dosyası mutlak yolda,
  servise özel owner-only dizinde ve dosyada tutulmalı; yedek/ACL ve rotation
  kapsamına alınmalı. Token'ı argüman, URL, QR, Yuva mesajı veya başlangıç
  banner'ına koyma. `--ws-token-sha256` raw tokenın client tarafında saklanma
  gereğini ortadan kaldırmaz. Client token'ı gerekiyorsa OS secret store'dan
  process'e ver; komut satırındaki literal değer yerine env variable name
  kullan.

## Dosya, environment ve gözlem kuralları

- Unix file fallback için secret dizini yalnız owner erişimli (`0700`), secret
  dosyası yalnız owner read/write (`0600`) olmalı; owner, regular-file ve
  symlink/ACL kontrolleri yapılmalı. Mode farklı UID'leri sınırlar, aynı UID'li
  süreçleri birbirinden ayırmaz. Dosya yedekleri ve geçici kopyalar da aynı
  hassasiyet ve silme politikasına tabidir.
- `Environment=KEY=literal` içine credential yazma. Shell'de `export
  KEY=literal`, komut argümanı veya URL içine gömmek shell history, process
  metadata/inspection, service tanımları ve teşhis çıktısına taşıyabilir.
  Environment değeri çalışan process'e gerekli olabilir; aynı UID veya root'un
  process environment/crash diagnostic erişimi varsayıma göre mümkün olduğundan
  env, secret vault veya OS kimlik doğrulamasının yerine geçen güçlü izolasyon
  değildir. `set -x`, `env`/`printenv`, debug dumps ve service environment
  dökümlerini secret içerebilecek süreçte kullanma.
- Secret'ı Yuva görev açıklaması/teslimi/mesajı, `mesaj.jsonl`, `ekran/*.jsonl`,
  exception, HTTP header dump, request/response log veya ekran görüntüsüne
  koyma. Hata raporuna yalnız provider, host alias'ı, credential key ID'si,
  işlem aşaması ve içeriksiz hata sınıfı yaz; token, password, auth header,
  raw response ve hassas mutlak path yazma.
- Rotation/revoke için eski ve yeni credential overlap süresi, bağlı servisleri
  yeniden başlatma, readback, eski credential'ı kapatma ve kayıp client
  prosedürü ayrı operatör planı ister. Bu not secret üretmez, value paylaşmaz,
  credential store'u değiştirmez veya servis başlatmaz.

## Kaynak durumu ve doğrulama sınırı

- OpenCode: #472 araştırması Server dokümanında loopback varsayılanı ve
  `OPENCODE_SERVER_PASSWORD`/username ayarlarını kaydetmiştir; kurulu provider
  sürümü ve provider-key kalıcılık yeri bu çalışma kapsamında doğrulanmadı.
- Codex: resmi [Authentication](https://learn.chatgpt.com/docs/auth)
  belgesi auth.json/keyring/auto/ephemeral credential store seçeneklerini,
  auth.json'ın token taşıdığını ve korunmasını açıklar. Resmi
  [Codex App Server](https://learn.chatgpt.com/docs/app-server) sayfası remote
  WebSocket auth/TLS, token-file/hash-file ve command-line yerine env name
  kullanımını açıklar. Resmi [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)
  store davranışını listeler.
- Bu yerel not endpoint'e bağlanmadı, secret store sorgulamadı veya herhangi
  bir secret okumadı. OpenCode kurulum seçenekleri hedef sürüm `/doc` ve
  kurulum dokümanı ile; Codex seçenekleri de gerçek CLI sürümü/OS credential
  store ile operatör tarafından doğrulanmalı. Yuva HMAC özellik bayrağı veya
  provider server auth durumu bu belgeden çıkarılamaz.
