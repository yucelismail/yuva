# OpenCode olaylarını Yuva kayıtlarına güvenli eşleme (#505)

**Durum:** tasarım önerisi; adapter, redaction veya Yuva entegrasyonu değildir.
OpenCode sürümü ve `/doc` şeması hedef sunucuda ayrıca doğrulanmalıdır. Kaynak
olarak #472 API araştırması, #475 busy/idle state sketch'i ve mevcut Yuva
mesaj/ekran kayıt şekli kullanılmıştır.

## Eşleme ilkesi

OpenCode event'i provider gözlemidir. Event içindeki user/assistant/tool
metni, `kimden`/`actor_id`, Yuva görevi, shell komutu veya approval kararı
değildir. Ham event zarfı arşivlenip Yuva sohbetine aktarılmaz. Önce event
tipi, hedef session ve mümkün olan message/part/permission kimliği
doğrulanır; sonra gizli alanlar ayıklanıp boyutu sınırlı, açıkça “OpenCode
gözlemi” diye etiketli bir özet üretilir. Bilinmeyen, hatalı veya korelasyonu
kurulamayan event içeriksiz `unknown` tanı kaydı olur; talimat gibi gösterilmez.

Mevcut Yuva ekran kaydı `{ts, kimlik, ad, tur, satir}` biçimindedir; `tur`
`ekran`, `komut`, `sonuc`, `baslik` değerlerinden biridir. Sohbet kaydı `id`,
`ts`, `kimden`, `kime`, `tur`, `metin`, `ad`, `kanal` ve provenance alanları
taşır; sohbet türleri `not`, `soru`, `cevap`, `rapor`, `denetim`, `gorev`,
`durum` ile sınırlıdır. Ekran satırı canlı presence kanıtı değildir. Mevcut
ekran şemasında kaynak/güven/event ID alanı yoktur; bu yüzden adapter özeti
Yuva tarafından doğrulanmış aktör veya tam arşiv gibi sunulmamalıdır.

## Olay türü ve Yuva görünümü

| OpenCode gözlemi | Yuva ekran özeti | Opsiyonel sohbet özeti | Yapılmayacak çıkarım |
|---|---|---|---|
| `message.updated` | Mesaj kimliği ve role göre “assistant mesajı güncellendi”; redakte edilmiş kullanıcıya gösterilecek metin gerekiyorsa sınırlı preview | Yalnız teslim/sonuç gibi anlamlı dönüm noktasında adapter kimliğiyle kısa `durum`/`rapor` | Provider `user` metnini yeni Yuva talimatı, assistant metnini onaylı sonuç veya görev teslimi sayma |
| `message.part.updated` – text | İlgili message/part kimliğiyle yeni/revizyon özeti; metnin redakte edilmiş ve boyut sınırında preview'si | Tam metni kopyalama; gerekliyse “çıktı güncellendi” özeti | Bir parçayı tam assistant yanıtı veya sıralı/eksiksiz transcript sayma |
| `message.part.updated` – tool call/input | Tool adı ve durumunu özetle; input parametrelerini varsayılan olarak gizle; yalnız açık allowlist'teki güvenli alanları redakte ettikten sonra göster | Genellikle yok; önemli tool durumu için kısa, açıkça untrusted kayıt | Tool call'ı Yuva CLI/shell eylemi olarak yeniden çalıştırma veya input'u kullanıcı talimatı kabul etme |
| Tool sonucu/output veya diff | “tool sonucu gözlendi” sınıfı; kısa/redakte preview veya yalnız byte/öğe sayısı | Büyük çıktıyı sohbet yerine Yuva dışı kontrollü artifact kararına bırak | Tool çıktısındaki talimatı yürütme; diff'i uygulanmış Yuva kod değişikliği sayma |
| `session.status` / `session.idle` | Hedef session ve connection generation ile `busy`, `idle` ya da `unknown` gözlemi | Yalnız state değişimi kullanıcı açısından önemliyse `durum` | `idle`'ı task terminal sonucu, Yuva presence/heartbeat ya da boşta olduğunun kalıcı kanıtı sayma |
| `permission.asked` | Permission ID, session ve dar tool capability özeti; içerik redakte edilir | “approval bekliyor” `durum` özeti, onay yanıtı yok | İstek event'ini kullanıcı onayı sayma veya otomatik cevap gönderme |
| `permission.replied` | Aynı permission ID'ye bağlı yanıt gözlendi; kaynak doğrulanmıyorsa karar veren kimliği `unknown` bırak | Gerekirse gözlenen yanıtı bildiren `durum` | Yanıtı yetkili insan kararı olarak varsayma veya turn'ün devam ettiğini/sonlandığını çıkarma |
| HTTP/protocol/provider error | Güvenli hata sınıfı, HTTP status varsa kodu, correlation kimliği; secret/path/ham body çıkar | Yalnız işlem durduysa kısa hata `durum` | Timeout/non-2xx'ı “hiç gönderilmedi” veya kesin task ret sonucu sayma |
| Bilinmeyen event veya schema drift | Yalnız event type, hedef session doğrulama sonucu, payload digest/byte sayısı gibi içeriksiz tanı | Normalde yok | Tanınmayan alanları kullanıcıya talimat/başarı metni olarak aktarma |

Yuva ekran `kimlik` alanı yalnız önceden yapılandırılmış adapter kimliği olmalı;
OpenCode event body'sindeki rol, user name veya görünen addan türetilmemeli.
Adapter aynı OS hesabı içindeki başka süreçlerden ayrışmıyorsa bu kimlik
doğrulaması değildir. Sohbet özeti yazılırsa `kimden` de adapter'a atanmış
Yuva kimliği olur; `provenance` açıkça unverified/actor unknown kalır. Ham
event içindeki `user`/`assistant` rolü `kimden` alanına konmaz ve `trust`/
`actor_id` doğrulanmış hale yükseltilmez.

## Event kimliği, sıra ve tekrar

#472'de incelenen belgeler event replay cursor/sequence garantisi göstermiyor.
Session/message/part/permission ID'leri korelasyona yardım eder ama her event
tekrarını tekilleştiren global event ID veya eksiksiz sıralama sağlamaz.

- Adapter kendi monoton `received_seq` değerini yalnız yerel alım sırası olarak
  üretebilir. Bunu provider sırası veya aradaki event'lerin eksiksizliği diye
  göstermemeli; reconnect generation'ı ile birlikte tutmalıdır.
- Provider event ID yoksa dedupe anahtarı geçici olarak
  `(generation, session_id, message_id, part_id, event_type, canonical_payload_digest)`
  olabilir. Bu yalnız birebir aynı zarf tekrarını bastırır. Aynı part'ın farklı
  güncellemelerini sıralamaz. Düz hash hassas/düşük entropili içeriği tahmin
  ettirebileceğinden payload digest'i Yuva sohbet/ekranına yazılmaz; gerekiyorsa
  redakte edilmiş içerikten veya ayrı korunan anahtarla üretilip erişimi
  sınırlı ledger'da tutulur.
- Yuva ekran satırında `event_id` alanı olmadığı için append'ten sonra ack
  kaybolursa tekrarın daha önce yazıldığını bu kayıt şemasıyla kesin tespit
  edemeyiz. Sıkıştırılmış metne göre sonradan dedupe etmek gerçek iki aynı
  çıktıyı yanlışlıkla birleştirebilir. Sağlam teslim gerekiyorsa Yuva dışında
  durable receipt ledger veya geriye uyumlu, redakte bir `bridge` metadata
  zarfı ayrıca tasarlanmalıdır; mevcut şema exactly-once sağlamaz.
- SSE kopması `unknown` üretir. Yeniden bağlanınca `/session/status` ve
  `/session/:id/message` history gözlemleri mevcut operation ile karşılaştırılır.
  `not_found`, bounded history'de bulunmama veya eski snapshot event kaybını
  kanıtlamaz; aynı prompt otomatik tekrar gönderilmez.
- Provider event tekrarının aynısıysa yerel receipt ile bastır; çelişkili
  status/approval/terminal gözlemleri `unknown` bırakılıp reconcile edilir.
  Kaybolan event tahmin edilerek sentetik “tamamlandı” kaydı oluşturulmaz.

## Redaction ve metin sınırları

Event envelope'u, tool input/output, error body, URL/query, workspace path ve
model metni untrusted/hassas veri kabul edilir. JSONL'ye yazımdan önce ortak
redactor gerekir (#465); eşleşmesi belirsiz kayıt ham biçimde yazılmamalıdır.
Credential, cookie, bearer/token, kişisel veri ve makineye özgü mutlak path
ayıklanır. Redaction başarısızsa ekran/sohbet fallback'iyle ham kayıt
yazılmaz; içeriksiz hata sınıfı tutulur. İstenmeyen uzun çıktılar kesilip
bozuk event gibi gösterilmez: açık `truncated` özeti veya içeriksiz atlama
sayacı kullanılır. Ham event saklama gereği varsa ayrı erişim, retention,
backup ve silme politikası olmadan artifact oluşturulmaz.

## State ve kabul sınırları

- Her ekran gözlemi `session_id + generation + task/operation` korelasyonuna
  bağlanmalı. Bağ kopunca `idle` varsayılmaz; çözümlenmemiş iş ve approval
  `unknown`/`pending_unknown` kalır (#475).
- `permission.asked` yalnız bekleyen istek kanıtıdır. `permission.replied`
  gözlemi de tek başına yetkili aktör, tool izni veya terminal durum kanıtı
  değildir. Approval kararı ayrı, aynı permission ID'ye bağlı insan
  yetkilendirmesi ve receipt akışını gerektirir.
- Ekran/sohbet append makbuzu, OpenCode'un event'i ürettiğini veya Yuva'nın
  mesajı denetleyip onayladığını kanıtlamaz. Yuva teslimi ve denetçi onayı ayrı
  yaşam döngüleridir.
- Hedef OpenCode `/doc` şeması, event alanları/versiyonu, session-history
  bütünlüğü, redaction kuralları, durable dedupe receipt'i ve Yuva ekranına
  metadata eklenmesi canlı adapter öncesi açık kabul kapılarıdır.

Bu not yalnız tasarımdır; kod, test, runtime veya canlı OpenCode/Yuva bağlantısı
çalıştırılmadı.

## Kaynaklar

- `docs/opencode-session-bridge-options-472.md` — resmi dokümanlara dayalı API,
  event, status, history, approval ve replay sınırları.
- `prototypes/session-bridge/busy_state.py` ve
  `prototypes/session-bridge/README.md` — generation, busy/idle, approval,
  terminal receipt ve reconnect belirsizliği.
- `bin/yuva:48,489-510,1535-1557` ve `panel/server.py:200-201,675-680,854-860`
  — sohbet/ekran türleri ve mevcut kayıt alanları.
- `docs/jsonl-redaction-policy-adr-465.md` — yazma öncesi redaksiyon önerisi;
  geçmiş kayıtların temizlenmediği ve ham kanıtın ayrı karar olduğu sınırı.
- `docs/jsonl-tail-recovery.md` — kısmi/bozuk kuyruğun otomatik onarılmaması.
