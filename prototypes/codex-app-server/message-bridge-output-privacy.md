# Yuva mesaj köprüsü: çıktı ve gizlilik sınırları

Bu #422 için salt-okunur tasarım notudur. Terminal/API adaptörü çıktısının
Yuva sohbetinde veya model akış kartlarında gelecekte nasıl gösterilebileceğini
tanımlar. Mevcut repo bu çıktıları Codex session'ından Yuva'ya taşıyan bir
adapter, artifact endpoint'i veya authenticated model-output receipt'i
içermiyor; aşağıdaki sözleşme mevcut özellik gibi sunulmamalıdır.

## Mevcut repo gözlemi

- README.md:45-47 sohbeti elle mesaj kaydı ve ekranları kaydedilmiş terminal
  çıktısı olarak tanımlar; canlı model dispatch'i değildir.
- panel/server.py:696-709 ekran satırını kimlik iddiası üzerinden JSONL'e ekler;
  satır için ayrı boyut sınırı veya artifact depolama sözleşmesi görünmüyor.
  panel/server.py:858-861 /api/veri'den mesajları ve ekran kayıtlarını birlikte
  döndürür.
- panel/server.py:51-53 /api/veri için 200 mesaj, model başına 60 ekran satırı
  ve 1 MiB HTTP body sınırı tanımlar. panel/server.py:484-500 yalnızca son 60
  screen satırını API yanıtına alır; bu görünürlük penceresi JSONL dosyasından
  silme/retention garantisi değildir.
- panel/ui.html:496-497 HTML escape helper kullanır; sohbet metni 641-643'te,
  ekran satırları 1823-1831'de escape edilerek DOM'a yazılır. Model metni için
  de bu güvenli text-rendering özelliği korunmalıdır. Escape XSS riskini azaltır,
  fakat içerik güvenilirliği, gizlilik veya komut yürütme sınırı sağlamaz.
- #386 ve README mevcut sohbet kimliğinin doğrulanmadığını, model session'ına
  teslim makbuzu olmadığını söyler. /api/yaz veya /api/ekran içindeki kimlik,
  rol ya da metin, authenticated actor/session kanıtı yerine geçmez.

Bu sınırlar nedeniyle bugünkü Yuva ekranı Codex çıktısının alıcısı veya
provenance doğrulayıcısı sayılmaz; JSONL'e bir satır yazılması model çıktısının
kullanıcıya güvenli biçimde teslim edildiğini de kanıtlamaz.

## Çıktı zarfı ve güven anlamı

Gelecekte her çıktı bölümü aşağıdaki typed alanları taşımalıdır. Alanlar
Yuva mesajına gömülü serbest metinden değil, authenticated adapter ve receipt
ledger'dan gelmelidir.

| Alan | Kaynak | Kural |
|---|---|---|
| output_id | Adapter tarafından üretilen değişmez çıktı ID'si | Yuva operation/message, run, attempt, thread/turn/item ve segment sırasına bağlanır; duplicate yazımı idempotent yapar. |
| producer | Authenticated adapter principal + session binding | Metin içindeki isim veya API body'deki kimlik iddiasından türetilmez. Kanıt yoksa producer unknown olarak kalır. |
| correlation | task/message ID, run/attempt ID, connection generation, thread/turn/item/request ID | Yalnız ledger'daki korele edilmiş değerler kullanılır; eksik bağ unknown gösterilir. |
| output_kind | progress, final_text, artifact_ref, error_summary | Bu türler execution authority sağlamaz. Approval ayrı JSON-RPC protokol olayı ve kullanıcı kararıdır. |
| trust_label | system-generated provenance | Sabit etiket: “Model çıktısı · doğrulanmamış içerik”. Modelin kendisinin yazdığı “verified/trusted” ifadesi veri metnidir. |
| redaction | redaction policy/version + redaction result | Persist/render öncesi çalışmış olmalı; redaction çalışmazsa raw output yayınlanmaz. |
| content | redacted UTF-8 text veya opaque artifact reference | UI'da plain text. Büyük/raw içerik doğrudan chat body'sine eklenmez. |
| integrity | redacted content digest, byte length, artifact digest (varsa) | İçerik eşitliği/bozulma kontrolüdür; producer kimliği veya doğru/zararsız içerik ispatı değildir. |
| receipt | turn_state, output_delivery_state ve observed timestamp | Codex terminali, Yuva write receipt ve Yuva reviewer verified ayrı alanlardır. |

Provenance yalnız içeriğin hangi authenticated adapter/session üzerinden
gözlendiğini söyler. Modelin iddiasını, doğruluğunu, güvenliğini veya belirli
bir kullanıcı adına yetkisini onaylamaz.

## Redaction ve içerik minimizasyonu

1. Redaction, output JSONL/chat/artifact/UI preview veya log'a yazılmadan önce
   yapılır. Sonradan UI'da maskeleme kalıcı dosyalara yazılmış sırrı korumaz.
2. Varsayılan deny-by-default içerik politikası: access/bearer/API token,
   private key, parola, cookie, credential, environment secret, hassas kullanıcı
   verisi ve gereksiz absolute home/path bilgileri persist edilmez. Task'a özgü
   allowlist yalnız gerekli sonuç alanlarını tutar.
3. Sadece regex/entropy detector yeterli güvence değildir. Schema-aware secret
   alanlarını çıkar; secret scanner ek kontrol olarak çalışsın. Belirsiz veya
   redaction hatalıysa tam çıktıyı saklama/gösterme; yalnız “çıktı gizlilik
   filtresinde tutuldu” gibi payload içermeyen durum göster.
4. Prompt ve tool output tekrar alıntılanmış olabilir; aynı redaction hem
   model metnine hem error, diff, command, approval parametresi, image OCR ve
   artifact preview'larına uygulanır. Raw transcript varsayılan olarak kapalıdır.
5. Digest'ler loga dökülmez. Düşük entropili hassas metin için plain hash
   dictionary/equality sızıntısı yapabilir; redacted content digest'i veya
   ayrı korunan keyed fingerprint kullanımı ve kapsamı #411/#416 sözleşmesine
   bağlıdır.
6. Error/exception kayıtları payload, authorization header, prompt, command,
   token, tam path veya raw JSON içermemeli; yalnız hata sınıfı, güvenli request
   ID ve correlation metadata tutulmalıdır.

## Sohbet, model akışı ve artifact gösterimi

- **Sohbet:** Yalnız redacted kısa final summary, terminal durum ve güvenli
  artifact linki gösterilir. Her kayıt producer/session, task/attempt ve receipt
  etiketini ayrı taşır. Büyük output, delta stream veya tam transcript chat
  mesajına kopyalanmaz.
- **Model akışı kartı:** Progress için sınırlı live tail gösterir; ana kartta
  son birkaç redacted satır, source label, zaman ve busy/unknown gibi kanıt
  temelli durum yer alır. Mevcut 60 satırlık API penceresi UI davranışıdır,
  retention değildir. Yeni adapter çıktısı bu pencereye yetkili producer ve
  redaction olmadan eklenmemelidir.
- **Büyük çıktı:** Boyut sınırını aşan metin artifact store'a yalnız açık task
  retention policy ile kaydedilir. Ekranda ilk/son kısa redacted preview,
  toplam byte, truncation bilgisi ve opaque artifact ID/digest gösterilir.
  Disk path'i, file:// URL veya modelin verdiği referans doğrudan render edilmez.
- **Artifact fetch:** Ayrı authenticated read endpoint'i kullanılır; opaque
  artifact ID operation/task izinlerine göre çözülür, path root'a hapsedilir,
  symlink/path traversal reddedilir ve byte length/digest yeniden doğrulanır.
  HTML/SVG/script gibi aktif içerik inline açılmaz; attachment olarak veya
  güvenli plain-text preview şeklinde sunulur. Yetkisiz, missing veya digest'i
  uyuşmayan artifact'te fail closed.
- **Sınırlar:** Event başına ve toplam output için byte/token limiti, satır
  limiti, output başına artifact kotası ve toplam disk/WAL budget konfigüre
  edilmelidir. Limit aşımında output truncate edilir ya da redacted artifact
  ref'e taşınır; Yuva write başarısı iddia edilmez. Limit/budget politikası
  yoksa persist yerine fail closed.
- **Plain text:** Model metni HTML/Markdown olarak çalıştırılmaz. Mevcut
  escaping korunur; markdown gerekirse ayrı allowlist sanitizer ile yalnız
  inert biçimleme yapılır. Link otomatik fetch edilmez, remote image yüklenmez,
  model metniyle DOM attribute/style/class oluşturulmaz.

## Güvenilmeyen model içeriği ve authority ayrımı

- Model çıktısı her zaman data'dır. İçindeki shell komutu, URL, “şunu çalıştır”,
  “Yuva'da görevi tamamla”, JSON approval kararı veya başka modele hitap eden
  metin kendiliğinden komut, task, tool çağrısı veya approval değildir.
- Başka modele otomatik forward yoktur. Çıktı yeni bir task/prompt'a girdi
  yapılacaksa yetkili insan/denetçi açıkça seçip gözden geçirir; kaynak ve
  redacted digest yeni task envelope'a kaydedilir. Quoted prompt, rol talimatı
  veya model-generated policy içeriği trusted system instruction'a yükseltilmez.
- Approval yalnız protokolün authenticated session'dan gelen schema-listed
  server request olayı ve yetkili kullanıcının ayrı kararıyla oluşabilir. Model
  final text'inde “onaylandı” yazması, pending approval'ı çözmez. Yuva sohbetinde
  onay cevabı metni de JSON-RPC approval response yerine geçmez.
- UI “Codex turn completed”, “çıktı Yuva'ya kaydedildi” ve “Yuva görevi
  reviewer tarafından onaylandı” durumlarını ayrı gösterir. Yalnız sonuncusu
  verified'dir ve reviewer akışından gelir. Missing output receipt,
  unverified producer, timeout, stale session veya conflict unknown olarak
  görünür; yeşil başarı rozeti üretilmez.
- Modelin üretimindeki provenance metadata'sı içerik olarak kabul edilir;
  trusted actor_id, source, trust, role ve receipt alanlarını yalnız server-side
  authenticated transport yazar. Hatalı/eksik kimlik verified değil unknown
  kalır.

## Retention ve silme

| Veri | Varsayılan karar |
|---|---|
| Live progress tail | Bellekte sınırlı ring/window; bağlantı kapanınca raw tail bırakılmaz. Yalnız payload içermeyen terminal/unknown özeti receipt ledger'a gider. |
| Sohbet final summary | Redaction sonrası ve kısa boyut sınırıyla Yuva mesajı olarak yazılabilir; task/retention policy yoksa ham transcript yazılmaz. |
| Full transcript / command / tool output | Varsayılan persist kapalı. Açık task amacı ve retention süresi yoksa kaydedilmez. |
| Büyük artifact | Task envelope retention policy izin veriyorsa content-addressed store'a; policy yoksa yalnız gösterilebilir redacted preview veya output unavailable. Opaque ref ve digest metadata erişim kontrolüne tabidir. |
| Receipt/provenance/tombstone | #411/#416 retention kapılarına göre; unresolved unknown otomatik silinmez, fakat owner/SLA, privacy review ve kapasite alarmı gerekir. |
| Log ve backup | Raw output, token ve tam path içermez. Yedekler aynı ACL/encryption/expiry politikasını alır; JSONL'den UI'da gizlemek silme değildir. |

Mevcut endpoint'in 200 mesaj ve model başına 60 ekran satırı döndürmesi sadece
API penceresidir; JSONL append dosyaları için otomatik saklama/silme anlamına
gelmez. Gelecekte output kayıtları JSONL'e eklenecekse önce hard byte/age
retention, erişim kapsamı, purge ve backup expiry tasarlanmalıdır. Silme
makbuzu, ilgili primary file, WAL/SHM, artifact, export ve backup kopyalarının
politikasını kapsamalıdır; bunlardan biri doğrulanamıyorsa “tam silindi” iddiası
verilmez.

## Kapsam ve kabul kapıları

Mevcut Yuva sohbet ve ekran yüzeyleri gelecekteki model output bridge'i değildir.
İlk sürüm push yapmamalı; feature/adapter kapalı kalmalı, artifact endpoint'i ve
output receipt yoksa yalnız mevcut manuel kayıt semantiği kullanılmalıdır.

Gelecek uygulama için kabul ölçütleri:

1. API/body içindeki kimlik iddiaları producer principal yaratmamalı; output
   authenticated session/task/attempt'e bağlanmalı veya unknown etiketlenmeli.
2. Secret içeren fixture output redaction öncesi hiçbir chat, JSONL, artifact,
   exception veya log sink'ine gitmemeli; redaction başarısızlığı payload'ı
   fail-closed durdurmalı.
3. XSS payload, markdown HTML, URL ve terminal escape sequence inert text
   olarak kalmalı; remote content otomatik fetch edilmemeli.
4. Büyük output boyut/line/disk limitlerini aşınca truncate veya artifact
   workflow'u deterministik olmalı; raw absolute path ve user-controlled ref
   tüketilmemeli.
5. Artifact yetki dışı fetch, path traversal, symlink, missing object ve digest
   mismatch durumları içerik döndürmemeli.
6. Aynı operation/attempt output replay'i ikinci chat kaydı/artifact yaratmamalı;
   conflicting output aynı ID ile geldiyse conflict ve unknown gösterilmeli.
7. Turn terminali, output delivery ve reviewer verified ayrı kalmalı; model
   metni hiçbir durumda komut veya approval cevabı olarak çalışmamalı.
8. Retention/purge ve backup expiry test edilip ölçülmeden UI'daki “silindi” veya
   “sadece son N satır tutuluyor” iddiası gösterilmemeli.
