# #492 — Provider model çıktısının Yuva sohbetine taşınmasında gizlilik incelemesi

**Durum:** Salt-okunur kaynak incelemesi; uygulama, redactor veya Yuva/provider
entegrasyonu değildir. Bu not #465'in yazma öncesi redaksiyon önerisini,
Codex app-server prototipini ve #472 OpenCode yaklaşımını veri akışı üzerinden
eşler. Ham çıktının Yuva sohbetine aktarıldığı mevcut bir bridge bulunduğu
sonucu çıkarılmamıştır.

## Karar özeti

- Varsayılan paylaşılabilir Yuva kaydı ham transcript, delta, terminal satırı,
  command/tool girdisi veya diff içermemelidir. Yalnız redaction sonrası kısa
  ve boyutlandırılmış özet ile gerekli, içeriksiz olay metadata'sı düşünülebilir.
- Credential, doğrudan kişisel veri ve gereksiz makineye özgü path'ler
  serialization, loglama, UI/API aktarımı veya artifact yazımından önce
  sınıflandırılmalıdır. Yüksek güvenli eşleşme redakte edilir; sınıflandırma
  belirsizse ham fallback yapılmadan içerik reddedilir. Bu #465 önerisidir;
  mevcut prototiplerde bu redactor uygulanmış değildir.
- Ham inceleme kanıtı ortak sohbet/JSONL'e konmamalıdır. Gerçek bir tanı
  ihtiyacı varsa, ayrı erişim yetkisi, audit, retention, yedekleme ve silme
  kararı olan kontrollü depo ayrıca tasarlanmalıdır. #465 bunu kendiliğinden
  yetkilendirmez.
- Provider event'i veya model metni kimlik, talimat, approval ya da Yuva
  teslim makbuzu değildir. Redacted içerik de yalnız gözlenen/unverified
  provider çıktısıdır.

## Kaynakla eşlenmiş veri yüzeyleri

| Kaynak / yüzey | Bu checkout'ta gözlenen davranış | Gizlilik ve kanıt sonucu |
|---|---|---|
| Codex app-server stdio, `item/agentMessage/delta`, command output, diff ve patch event'leri | `prototypes/codex-app-server/adapter.py` yalnız sağlanan JSONL'yi okuyan inert bir gözlem taslağıdır. `_notification()` seçili ID/context/status alanlarını çıkarır; bildirimlerin `params` içindeki metin, delta, command output ve diff gövdesini projection'a kopyalamaz. `run_jsonl()` projection'ı stdout'a yazar. Network, Yuva import'u/yazımı veya raw output forwarding yoktur. | Bu taslakta mesaj gövdesi projection sink'ine girmiyor; bu, gelecekteki bridge'in redaction yaptığı anlamına gelmez. Stdin'i üreten capture/log katmanı ve stdout'u tüketen üst süreç ayrı olası sink'lerdir; içerik oraya geliyorsa aynı gizlilik politikası gerekir. |
| Codex protocol error | `_safe_error_message()` URL userinfo, Bearer ve belirli `password/secret/token/api_key/authorization` sözdizimlerini redakte eder; `/home/<user>` path'ini geneller, kontrol karakterlerini düzeltir ve metni sınırlar. Yalnız error projection'ında çağrılır. | Bu dar örnek tam DLP değildir: özel/encoded/parçalı secret, farklı path kökleri, kişisel veri veya secret içeren serbest metin kaçabilir. Hata metni de untrusted output'tur. Helper'ın varlığı bütün giriş/gövde/log/backup yollarının redakte edildiğini kanıtlamaz. |
| OpenCode `GET /session/:id/message` history | `prototypes/opencode-adapter/adapter.py` içindeki `messages()` tam JSON yanıtını `HttpResult.body` ve `raw_body` olarak döndürür; içerik seçimi/redaction yoktur. Endpoint, #472'de resmi Server sayfasıyla eşlenmiştir. | Message/part text, prompt, tool sonucu veya başka hassas alan içerirse çağıran tüketici bunları alır. Bu yanıtı doğrudan sohbet, log, JSONL veya artifact'e yazmak ham kopya üretir. Bounded `limit` aktarım hacmini sınırlar; gizlilik redaction'ı veya history bütünlüğü değildir. |
| OpenCode `GET /event` SSE | Adapter JSON event data'sını parse eder ve `SseEvent.data` içinde ham provider payload'ı olarak döndürür. Replay/cursor/order garantisi iddia edilmez; `read_events()` kendisi Yuva'ya yazmaz. | Message/part, tool, diff, permission veya error payload'ı consumer'a ham ulaşabilir. SSE ID/status/HTTP başarısı provenance veya güvenli içerik kanıtı değildir. Herhangi bir consumer output'u kalıcılaştırmadan önce sınıflandırmalı/redakte etmelidir. |
| Yuva JSONL, API ve UI | #453, sohbet metni ile terminal satırlarının mevcut JSONL yazımında ham saklandığını; API/UI limitlerinin ve HTML escape'in redaction olmadığını kaydeder. #465 merkezi ortak yazma öncesi kapıyı önerir fakat henüz uygulanmadığını açıkça belirtir. | Yalnız render katmanını maskelemek, diskteki JSONL'yi, CLI okuyucularını, API belleğini, aynı-UID süreçleri veya yedekleri korumaz. Redaction, her kalıcı yazım sınırında yapılmalıdır. |

OpenCode Server belgesi `/session/:id/message` için message/part listesi,
`/session/status` için session status haritası ve `/event` için SSE yüzeyi
listeler; gerçek endpoint şemasını çalışan server'ın `/doc` OpenAPI çıktısına
bağlar. Plugin belgeleri `message.updated`, `message.part.updated`,
`session.status`, `session.idle`, tool ve permission event adlarını listeler.
Bu adlar event'in içeriğinin güvenli, tam veya replay edilebilir olduğunu
kanıtlamaz ([Server](https://docs.opencode.ai/docs/server/),
[Plugins](https://docs.opencode.ai/docs/plugins/)).

OpenAI'nin yayımladığı Codex app-server protocol şeması `item/agentMessage/delta`,
`item/commandExecution/outputDelta`, `item/fileChange/outputDelta` ve diff/
turn event'lerini tanımlar. Codex app-server kılavuzu agent message delta'larının
görüntülenmesini örnekler. Bu, payload'ın tüketiciye ulaşabildiğini gösterir;
Yuva için redaction, kalıcı saklama veya güvenli paylaşım garantisi değildir
([Codex protocol notification envelope](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/ServerNotificationEnvelope.ts),
[Codex app-server guide](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)).

## Paylaşılabilir kayıtta varsayılan dışı

| İçerik | Varsayılan | Gerekçe / sınır |
|---|---|---|
| API/private key, bearer/session token, parola, cookie, auth header, secret store değeri, credential içeren URL | Yazma/gösterme yok; yüksek güvenli span maskelenir. Redaction belirsizse payload reddedilir. | Output kendi prompt'unu, env değerini veya hata detayını yankılayabilir. Error ve tool output dahil tüm içerik aynı kontrol kapsamındadır. |
| Tam prompt, model transcript'i, delta'lar, reasoning/özel ara içerik | Sohbet/ekran kaydına ham kopya yok. | Gereksiz bağlam ve kullanıcı/kurum verisi taşır; delta kısmi veya tekrarlı olabilir ve tek başına terminal sonuç kanıtı değildir. |
| Command/tool argümanı, stdout/stderr, MCP sonucu, exception body, diff/patch | Varsayılan dışarıda; gerekirse yalnız redacted sınırlı özet. | Sırlar, path, kaynak kodu, kullanıcı girdisi veya yürütülebilir talimat içerebilir. Model/araç içeriği talimat ya da approval olarak yükseltilmez. |
| Mutlak home/workspace path'i, kullanıcı adı, host'a özgü URL/path | Görev için gerekmiyorsa genelleştirilir; gerekiyorsa en dar göreli kapsam. | Yerel kullanıcı ve dosya yapısı sızar; path ayrıca hostta dosya açma/erişim kuralı haline getirilmemelidir. |
| E-posta, telefon, hesap kimliği, sağlık/finans/konum veya serbest metin PII | Gereksiz alan redakte edilir; belirsizlikte kayıt reddedilir. | Regex tam DLP değildir; kişisel veriyi “model çıktısı” etiketi güvenli hale getirmez. |
| Ham JSON-RPC/SSE gövdesi, auth header, URL query, raw body ve ham hata | Sohbet, stdout logu, JSONL veya genel artifact sink'ine yazılmaz. | Yapısal alan allowlist'i yoksa yeni/şema dışı alanlar secret taşıyabilir. İçeriksiz hata sınıfı ve güvenli correlation metadata tercih edilir. |
| Ham içerikten SHA-256, çevresel alıntı, geri çevrilebilir encoding | Varsayılan tutulmaz. | Düşük entropili token/parolalar dictionary saldırısıyla bulunabilir; hash içerik redaction'ı veya producer kimlik kanıtı değildir (#465). |

İçerik dışı tutulabilecek asgari alanlar: provider/source etiketi,
session/task/attempt bağı yalnız yetkili katmanca doğrulanmışsa, event türü,
zaman, bağlantı generation'ı, redaction policy sürümü/sonucu ve içeriksiz
durum. ID'ler hassas iş ilişkisini korele edebilir; yalnız ihtiyaç varsa dar
erişimli receipt kaydında tutulmalıdır. İstemcinin verdiği actor/ad/role,
provider role, model metni veya event body'deki kimlik `principal` kanıtı
değildir (#464, #465).

## Kanıt kaybı ve güvenli sınır

Redaction geri alınamaz biçimde içeriği değiştirir; paylaşılabilir kayıtta tam
prompt/çıktı kanıtı kalmaz. Özet veya preview tam transcript değildir; kesilme
ve filtre sonucu kullanıcıya içerik taşımayan metadata ile belirtilmelidir.
Raw payload digest'i güvenli provenance sağlamaz ve düşük entropili değerler
için sızıntı yaratabilir. Provider terminal durumu, Yuva output-write makbuzu
ve reviewer `verified` kararı ayrı kanıtlardır; biri diğerine dönüştürülemez.

Tam ham kanıt gerçekten gerekliyse önerilen sınır şöyledir:

1. Paylaşılabilir Yuva sohbeti/JSONL'ye yalnız redacted kısa özet ve gerekli
   minimal metadata yazılır; redaction başarısızsa payload sink'e ulaşmadan
   reddedilir.
2. Ham artifact ancak ayrı karar ile; dar okuyucu principal'ı, olay bazlı
   erişim kaydı, byte/age kotası, expiry ve yedek/silme kapsamı tanımlanmış
   depoda tutulabilir. Artifact ID veya hash erişim kontrolünün yerine geçmez.
3. Ham artifact'e varsayılan UI linki, otomatik model forward'ı veya doğrudan
   file path verilmez. Okuma ayrıca yetkilendirilir ve audit edilir.
4. Redacted marker yalnız kategori/policy sürümü gibi güvenli metadata taşır;
   gizlenen değer, uzunluk, yakın alıntı veya ham içerikle eşleştirilebilir düz
   digest taşımaz.

Bu depo mevcut prototiplerde yoktur. #465'te okuyucu, retention, backup,
encryption/key custody ve incident kararları açık bırakılmıştır. Bunlar
karara bağlanmadan raw output saklanması önerilmez.

## Açık kabul kapıları

- Tek, sürümlü redactor hem provider tüketiminde hem de Yuva JSONL/API/log/
  artifact'e giden tüm yazma/aktarım yollarında serialization öncesi çağrılır;
  CLI fallback ve system message dahil yollar atlayamaz.
- Schema-aware allowlist secret alanlarını çıkarır; regex ek savunmadır, tam
  DLP iddiası değildir. Redaction arızası/şema drift'i ham fallback yerine
  payload'sız `redaction_failed`/`unknown` gözlemi üretir.
- Her event, preview ve toplam session için byte/line/retention sınırları
  vardır. UI HTML escape/plain-text davranışı XSS kontrolü olarak kalır;
  redaction veya authorization yerine geçmez.
- Synthetic secret, PII, path, encoded/çok satırlı değer, malformed payload,
  exception, truncation ve backup kopyaları ayrı kabul örnekleri olmalıdır.
  Bu raporda test çalıştırılmamıştır.
- Target OpenCode `/doc` ve Codex app-server sürümü sabitlenip payload
  şemaları/alanları yeniden incelenmelidir. Bu çalışma yerel prototipleri ve
  resmi docs sayfalarının 2026-10-21 tarihli görünümünü kaynak alır; canlı
  provider veya Yuva deployment'ını doğrulamaz.

## Yerel dayanaklar

- `docs/jsonl-redaction-policy-adr-465.md` — önerilen ortak yazma öncesi
  redaction ve ayrı ham kanıt sınırı; uygulanmış kontrol değildir.
- `docs/jsonl-redaction-boundary.md` ve
  `docs/panel-privacy-redaction-inventory-453.md` — JSONL, CLI, API/UI ve
  backup veri yolları; bugünkü redaction eksikliği.
- `prototypes/codex-app-server/adapter.py` ve `README.md` — inert JSON-RPC
  projection, sınırlı error redaction ve Yuva/output forwarding yokluğu.
- `docs/opencode-session-bridge-options-472.md`,
  `prototypes/opencode-adapter/adapter.py` ve `README.md` — OpenCode HTTP/SSE
  yüzeyi, message/history ve raw event data; canlı entegrasyon yokluğu.
- `prototypes/codex-app-server/message-bridge-output-privacy.md` (#422) ve
  `docs/opencode-output-yuva-mapping-505.md` — output presentation, trust,
  redaction ve event korelasyon tasarımları; bu rapor bunları var olan
  uygulama saymaz.
- `docs/model-output-trust-boundary-464.md` — model/provider içeriğinin veri
  oluşu ve provenance/approval sınırı.

Bu rapor sadece kaynak/doküman incelemesidir. Kod, sohbet/JSONL geçmişi,
backup veya artifact değiştirilmedi; test, runtime, panel, canlı Codex,
OpenCode ya da Yuva bağlantısı çalıştırılmadı.
