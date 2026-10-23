# OpenCode oturum köprüsü seçenekleri

Bu #472 araştırma raporu Yuva sohbetinden OpenCode oturumuna mesaj iletme ve
çıktı/olayları geri alma yollarını karşılaştırır. Çalışma ağacında OpenCode
kurulum belgesi veya mevcut OpenCode prototipi bulunmadı; bu nedenle aşağıdaki
API bilgileri resmi çevrimiçi belgelere dayanır. Kurulu bir OpenCode sürümü,
canlı sunucu veya entegrasyon doğrulanmış değildir.

## Kaynaklar ve kapsam

Resmi belgeler 2026-10-21 tarihinde kontrol edildi:

- [Server](https://docs.opencode.ai/docs/server/) — `opencode serve`, API ve
  OpenAPI `/doc`.
- [CLI](https://docs.opencode.ai/docs/cli/) — TUI/server başlatma seçenekleri,
  headless `serve` ve attach.
- [Permissions](https://docs.opencode.ai/docs/permissions/) — `allow`, `ask`,
  `deny` ve approval davranışı.
- [Plugins](https://docs.opencode.ai/docs/plugins/) — tanımlı plugin event
  adları; server eventleriyle ilgili gözlem envanteri.
- [TUI](https://docs.opencode.ai/docs/tui/) — etkileşimli terminal akışı ve
  komut/keybind davranışı.

Server belgesi, gerçek endpoint şeması için çalışan instance'ın `/doc`
OpenAPI tanımını incelemeyi önerir. Burada belirli bir sürüm veya `/doc`
çıktısı sabitlenmedi. Belgelenmeyen bir özellik yoktur sonucuna değil,
**mevcut resmi sayfalarda doğrulanamadı** sonucuna varılmıştır.

## Resmi belgelerde doğrulanan API yüzeyi

`opencode serve` headless HTTP sunucusudur; belgelenen varsayılan adres
`127.0.0.1:4096`'dır. TUI de bir server ile çalışır ve belgeler TUI için sabit
hostname/port kullanılarak server'a bağlanılabildiğini; `/tui` uçlarının TUI
üzerinden prompt doldurma/çalıştırma amacıyla kullanılabildiğini belirtir.
`OPENCODE_SERVER_PASSWORD` ayarlanırsa HTTP Basic Auth etkinleşir; kullanıcı adı
varsayılanı `opencode`'dur, `OPENCODE_SERVER_USERNAME` ile değiştirilebilir.

| İş | Belgelenen API | Kanıtın anlamı ve sınırı |
|---|---|---|
| Sağlık/sürüm | `GET /global/health` | Sunucunun health ve version bilgisi; session veya model işi hazır demek değildir. |
| Session listele/oluştur | `GET /session`, `POST /session` | Session nesnesi döner. OpenCode session kimliği Yuva task/operation kimliği değildir. |
| Status | `GET /session/status` | Session başına sağlayıcı status görünümü. Bu bir anlık sorgudur; bağlantı kopmasında tek başına sonuç garantisi değildir. |
| Mesaj gönder | `POST /session/:id/message` | Senkron cevap ve mesaj/part içeriği; istek yanıtı kaybolursa sonuç belirsiz olabilir. |
| Asenkron mesaj | `POST /session/:id/prompt_async` | Belgelenen yanıt `204 No Content`; bu bir HTTP kabul yanıtıdır, Yuva teslim makbuzu veya idempotency garantisi değildir. |
| History | `GET /session/:id/message` | Session mesajlarını okuyup reconnect sonrası uzlaştırmaya girdi sağlar. Tek başına kayıp SSE sırasını kanıtlamaz. |
| Event stream | `GET /event` | İlk event `server.connected`, ardından server bus eventleri. Dokümanda replay cursor/sequence garantisi belirtilmiyor. |
| Global event stream | `GET /global/event` | Global event akışı; gerekenden geniş bir gözlem alanı olabilir. Session bağını event içindeki kimlikten doğrula. |
| Permission yanıtı | `POST /session/:id/permissions/:permissionID` | Permission isteğine cevap. Yalnız yetkili insan kararı sonrası kullanılmalı. |
| TUI kontrolü | `/tui/append-prompt`, `/tui/submit-prompt`, `/tui/execute-command` vb. | TUI arayüzünü sürer. Başarılı UI yanıtı modelin işi aldığına veya tamamladığına kanıt değildir. |

Plugin belgeleri `message.updated`, `message.part.updated`,
`permission.asked`/`permission.replied`, `session.status` ve `session.idle` gibi
event adlarını listeler. Bunlar olay türlerinin mevcut doküman yüzeyinde yer
aldığını doğrular; tüm sürümlerde tam payload şeması, event sırası, kalıcılık
ve reconnect replay garantisi vermez. Gerçek kurulum için `/doc` ve hedef sürüm
fixture'ları ayrıca kaydedilmelidir.

## API ve TUI tuş basma karşılaştırması

| Boyut | Oturum API'si | Terminale tuş basma | Resmi `/tui` kontrol uçları |
|---|---|---|---|
| Hedefleme | Session ID ile açık hedef | Aktif terminal/pencere ve odak durumuna bağlı | Belirli çalışan TUI server'ına bağlanır, yine UI state'i sürer |
| Gönderim sonucu | HTTP sonucu ve message/part veya async 204; uzaktaki işin terminal sonucu ayrı | Klavye girdisinin yazılması yalnız terminale girdi gittiğini gösterir | Boolean/UI kontrol yanıtı; model kabulü ya da tamamlanma değildir |
| Oturum/iş korelasyonu | Session ve message ID API alanlarıyla görünür | UI transcript/aktif session değişimine bağlı olarak belirsizleşebilir | TUI'nin o anki prompt ve session state'ine bağlı |
| Busy/idle ve output | Status endpoint + event + history sorgusu | Görsel ekranı okuyarak çıkarım gerekir | UI göstergesini sürme/gözleme; yapılandırılmış turn makbuzu değildir |
| Onay | Permission ID ve ayrı cevap endpointi; izin politikası yapılandırılabilir | Tuşla onay, yanlış/başka prompt'u kabul etme riski taşır | UI onayı başlatılabilir ama karar sahibi/receipt sınırı yine ayrıca gerekir |
| Reconnect | HTTP/SSE yeniden bağlanabilir; replay garantisi belgelenmemiş | Terminal/PID/TTY değişimi otomasyonu koparır; tekrar gönderim belirsiz | TUI server'ına yeniden bağlanabilir; UI işlemi sonucunu tek başına uzlaştıramaz |

**Değerlendirme (çıkarım):** Öncelikli seçenek session API'si olmalıdır; açık
session kimliği, yapılandırılmış mesajlar ve salt-okunur status/history uçları
sağlar. Ham tuş enjeksiyonu odak, prompt alanı, aktif session ve terminal
yaşam döngüsüne bağlı olduğundan gönderim receipt'i üretmez. `/tui` uçları
ham klavye enjeksiyonundan daha yapılandırılmıştır fakat gerçek session API'si
yerine geçmez; mevcut arayüzün prompt state'ini kullanır. UI'yi özellikle
sürmek gerekiyorsa `/tui` ayrı, düşük yetkili bir capability olarak ele
alınmalıdır.

## Busy/idle, output ve reconnect sözleşmesi

1. Başlangıçta `/session/status` ve hedef session history alınır; SSE bağlantısı
   açılır ve ardından aynı session için değişiklikler izlenir. Event ile
   snapshot arasında yarış olabileceğinden reducer iki kaynağı da tekrar
   uzlaştırabilmelidir.
2. `session.status` / `session.idle` eventleri canlı sinyaldir. Son gözlem
   zamanı, event'in session ID'si ve kaynak bağlantı nesliyle birlikte
   saklanır. Eski event veya farklı session event'i hedef state'i değiştirmez.
3. SSE kopunca `idle` varsayılmaz; activity `unknown` olur. Yeniden bağlantıdan
   sonra status ve message history okunup bilinen message/operation ile
   karşılaştırılır. Belgelenmiş replay cursor olmadığı için aradaki eventlerin
   eksiksiz alındığı varsayılmaz.
4. `prompt_async` sonrası kayıp yanıt veya bağlantı kopması `unknown`'dır.
   `messageID` alanı API gövdesinde bulunsa da resmi belgeler bunun uzak
   idempotency key olduğunu söylemez. Önce history/status ile reconcile et;
   aynı gönderimi körlemesine yeniden yapma. Yeni gönderim gerekiyorsa açık
   yeni attempt ve ayrı karar kaydı gerekir.
5. Message/part/tool/diff içeriği gözlenen provider output'udur. Yuva'ya
   kalıcı yazım makbuzu, operation bağı ve redaction kararı olmadan `teslim
   edildi` sayılmaz; model metni yeni görev/komut/approval değildir.

## Güvenlik ve approval

- Resmi belgelerde server loopback varsayılanıyla başlar; password auth
  yapılandırılabilir. Loopback, aynı makinede erişebilen süreçlere karşı
  kullanıcı kimliği kanıtı değildir (**çıkarım**). Basic Auth kimlik doğrular,
  fakat TLS sağlamaz; uzak erişimde güvenli tünel/TLS ve parola gerekir.
- CORS tarayıcı kaynak politikasıdır, API kimlik doğrulaması değildir. Server'ı
  parola olmadan dış ağda açmak uygun değildir.
- API'de `/session/:id/shell`, permission cevapları, session yönetimi ve TUI
  komutları gibi güçlü uçlar bulunur. Bağlantı yalnız izin verilen host,
  workspace ve session kapsamına sabitlenmeli; capability allowlist uygulanmalı.
- OpenCode permission kuralları `allow`, `ask`, `deny` davranışlarını
  belirler; varsayılanların geniş olabileceği resmi belgelerde belirtilir.
  Köprü auto-approve kullanmamalı. `permission.asked` gözlenirse request ID,
  session ve tool kapsamı kullanıcıya gösterilmeli; karar yalnız yetkili insan
  onayıyla ve aynı request'e bağlı açık cevap uçtan verilmelidir.
- Plugin belgelerinde event adının bulunması, canlı server API'de her sürümde
  approval response/replay yapılabildiğini kanıtlamaz. Bu ayrıntı hedef
  instance `/doc` şemasından doğrulanmalıdır.

## Önerilen, uygulanmamış köprü akışı

1. Feature kapalı başlasın; kurulu server version ve `/doc` şeması kaydedilsin.
   Host loopback olsun; password auth, CORS ve izin politikası ayrıca
   incelensin.
2. Dış orkestratör doğrulanmış Yuva source/message/task bağını oluşturup
   operation ID, attempt ID ve event ID'yi kalıcı kaydetsin. Bunlar
   authentication yerine geçmez.
3. Hedef OpenCode session'ı açıkça seçildikten sonra `prompt_async` veya
   senkron message API'si çağrılsın. Her HTTP/transport sonucu, provider
   accepted/turn lifecycle, output storage receipt ve Yuva reviewer kararı
   ayrı state olarak kalsın.
4. SSE olayları session kimliği ve connection generation ile korele edilsin.
   Çıkış/approval içeriği redaction ve güven politikalarından geçsin.
5. Bağlantı kaybında unknown + read-only reconcile; güvenilir kanıt yoksa
   otomatik resend yok. Approval pending ise pending/unknown korunup kullanıcı
   kararı beklenir.
6. Ayrı kabul kapıları olmadan canlı Yuva task state'i güncellenmesin; bu
   araştırma raporu entegrasyon, authorization veya güvenlik kontrolü
   uygulandığını iddia etmez.

## Doğrulanmayan noktalar

- Çalışma ortamında kurulu OpenCode sürümü ve server process'i doğrulanmadı.
- `/doc` OpenAPI çıktısı canlı instance'dan alınmadı; endpoint schema/version
  farkı bulunup bulunmadığı bilinmiyor.
- SSE reconnect sırasında replay, cursor, event durability ve duplicate
  semantiği resmi Server sayfasında tarif edilmemiştir; bunun protokolde hiçbir
  zaman olmadığı sonucu çıkarılamaz.
- `messageID` değerinin idempotency veya dedupe garantisi olduğu
  doğrulanmamıştır.
- Gerçek TUI focus/keypress hataları runtime deneyimiyle ölçülmemiştir; tablo
  protokol ve arayüz özelliklerinden çıkarımdır.
- Approval response yetkisinin Yuva principal/actor ile nasıl bağlanacağı,
  event/output retention ve aynı UID güven sınırı entegrasyon öncesi ayrıca
  tasarlanmalıdır.

Bu rapor yalnız belge araştırmasıdır; kod, test, runtime, panel veya OpenCode
oturumu çalıştırılmamıştır.
