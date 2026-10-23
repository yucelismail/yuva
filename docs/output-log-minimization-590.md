# Yuva #590 — Komut ve ortam çıktısı için dar loglama kuralı

## Karar

Paylaşılabilir rapor, sohbet veya `yuva ekran` kaydı ham subprocess/provider içeriğini varsayılan olarak taşımaz. Çıktı **allowlist'ten üretilmiş, sabit anlamlı metadata özeti** olmalıdır: şema sürümü, yerel operation ID (gerekliyse), izinli kaba işlem sınıfı, enum sonuç (`success`/`failed`/`unknown`), kaba süre kovası ve `stdout_stderr_omitted` gibi sabit politika etiketi. Hata için yalnız içeriksiz hata sınıfı/kodu ve güvenli correlation ID tutulabilir.

Tam argv/komut satırı, shell expansion, tüm environment dump veya env değişkeni değerleri, request/response header'ları (özellikle Authorization/Cookie), URL query, raw JSON-RPC/SSE gövdesi, sınırsız stdout/stderr, exception/traceback metni, diff/patch ve prompt/transcript default dışıdır. Output byte sayısı, ilk/son satır veya kırpılmış ham snippet de içerik sızdırabilir; ürün için gerekçe ve sınıflandırma politikası yoksa paylaşılmaz. Ekrana verilecek sonuç, serbest metin çıktıdan değil, yetkili caller'ın enum/şema alanlarından türetilen sabit metinden oluşturulur.

Bu görev yalnız tasarım ve fixture prototipidir; `bin/yuva`, panel, agent adapter, servis veya mevcut JSONL davranışı değiştirilmedi. Mevcut kaynak şu an aşağıdaki kuralları tam uyguluyor varsayılamaz.

## Bugünkü kaynak ve sınırlar

- `bin/yuva cmd_ekran()` kullanıcı/model tarafından verilen `satir` metnini panel'e gönderir; yalnız panel POST'un gönderilmediği kesinleşirse CLI yerel JSONL fallback'ine gider. Panel ve CLI kalıcı ekran yazıcısı #564'te ortak `redact_screen_record()` kullanır. Ancak bu redactor bilinen Bearer/Basic, credential assignment, credential URL ve yaygın token biçimlerine dayalıdır; eşleşmeyen serbest metni aynen bırakır.
- `cmd_ekran_oku()` eski JSONL içindeki `satir` alanlarını terminale doğrudan basar. Yazma anındaki redactor geçmiş JSONL/backup'ları temizlemez; read-time path de ayrıca projeksiyon/redaction ister. API/UI limitleri içerik minimizasyonu veya silme kanıtı değildir.
- `prototypes/codex-app-server/adapter.py` app-server'a bağlanmaz; sağlanan JSONL protokolünü gözlemler. Mevcut output-delta notification projection'ı gövde/delta metnini almıyor, yalnız bazı method/ID/status alanlarını çıkarıyor. `_safe_error_message()` URL userinfo, Bearer ve belirli key=value sınıflarını sınırlar/redakte eder; tam DLP değildir. Üstteki stdin recorder veya sink ayrıca ham içeriği tutabilir.
- Bu adapter OS environment'ını dökmez veya subprocess başlatmaz; gelecekteki agent runner'ın env/argv/stdout/stderr kopyalarını aynı şekilde maskelediği sonucu çıkmaz. Protocol `params` veya error alanı yeni şema/serbest metin taşıyabilir.
- HTML escape, record/byte limit, JSONL file permission ve no-store kontrolleri içerik gizliliği/credential sınıflandırması değildir. Aynı OS UID süreçleri dosya modu ile birbirinden ayrılmaz.

## Allowlist sözleşmesi

| Kaynak | Paylaşılabilir özet için izinli biçim | Varsayılan dışı |
|---|---|---|
| Komut | Sabit `operation_class` enum'u (örn. `local_tool`, `test_runner`) ve güvenilir yerel operation ID | Tam komut, argv, shell metakarakterleri/expansion, çalışma dizini, serbest command label |
| Sonuç | Tam sayı exit status'tan türetilmiş `success`/`failed`/`unknown`; gerekirse sabit hata kodu enum'u | Ham stdout/stderr, exit sonrası exception/traceback veya modelin yazdığı başarı iddiası |
| Süre | Önceden belirlenmiş kaba bucket | Milisaniye hassas zamanlama veya host benchmark ayrıntısı; gerekiyorsa ayrıca gerekçelendir |
| Environment | `values_not_recorded` gibi sabit politika etiketi | Environment key/value dökümü; allowlist'e giren env **değerleri** de yok. Runtime için gereken env yalnız subprocess'e dar ve geçici biçimde verilir, rapora kopyalanmaz. |
| HTTP | Gerekliyse status code aralığı ve sabit transport error class | Header'lar, Authorization/Cookie, URL query, request/response body, raw exception |
| Agent protocol | Bilinen event type/method enum'u, gerekli ve yetkili ID/correlation metadata'sı, `observed_unverified` kanıt etiketi | Ham JSON-RPC, arbitrary `params`, delta/output/diff/patch, bilinmeyen event gövdesi |
| Ekran/sohbet | Sabit durum cümlesi veya ayrıca redakte edilmiş, amacı belirli sınırlı özet | Raw tool output, tam transcript, terminal control sequence, otomatik alıntı |

Her allowlist alanı typed ve boyutlandırılmış olmalı. Bilinmeyen enum, şema sürümü veya alan sessizce pass-through yapılmaz: ilgili content projeksiyondan çıkarılır ve `output_omitted`/`schema_unknown` gibi sabit içeriksiz durum raporlanır. Caller'ın verdiği `kimden`, rol, task veya event içeriği authenticated principal/approval kanıtı değildir.

## Redaction sonrası kalan risk ve fail-closed davranış

Redactor ek savunmadır; output paylaşma izni değildir. Regex, yaygın token kalıplarını bulabilir ama özel provider credential'ı, kısa parola, parçalı/kodlanmış değer, Base64/escape edilmiş data, görüntü/OCR, unknown header, başka dil/anahtar adı veya output'un farklı biçimde yankılanmasını yakalamayı garanti etmez. Bir redaction marker'ı görülmesi de metnin kalan kısmında sır olmadığını kanıtlamaz. Redacted output'ta dahi kişisel veri, kaynak kodu, host path'i veya başka müşteri verisi kalabilir.

Önerilen akış:

1. Runner raw output'u gerekiyorsa yalnız geçici bellekte/bounded pipe içinde tutar; varsayılan kalıcı transcript/log/artifact kopyası oluşturmaz. Environment minimal allowlist'ten hazırlanır; parent environment dump edilmez. Komut argv'si rapor ve ekran sink'ine aktarılmaz.
2. Önce typed schema ve content alan allowlist'i uygulanır. Default özet content-free metadata'dır. Bir kullanım serbest içerik istiyorsa alan/amaç/byte sınırı ve redaction policy sürümü ayrıca tanımlanır.
3. Bu dar içerik adayı secret redactor'dan geçer; çıktı encoding/size ve yasaklı alan kontrolü yapılır. Redactor yoksa, hata verirse, belirsizlik kalırsa veya schema değişmişse raw fallback yerine bütün içerik payload'ı reddedilir; yalnız sabit hata kodu/status kalır.
4. Rapor, JSONL, API, screen, adapter stdout ve log sink'lerinin her biri ayrı çıkış yüzeyi sayılır. Hiçbiri raw veya pre-redaction nesneyi loglamaz. Ekran metni enum sonucundan sabit şablonla üretilir; `yuva ekran oku` için tarihsel kayıtların ayrı redacted read projection'ı gerekir.
5. Çıktı/metadata'nın retention ve erişim politikası ayrıca belirlenir. Raw debug kanıtı ortak Yuva ekranına veya genel loga taşınmaz; gerçek tanı ihtiyacı varsa ayrı onaylı, dar ACL/audit/TTL/backup alanı gerekir.

## Agent protokolü için özel kural

- Bilinen JSON-RPC output/delta event'lerinde yalnız şema allowlist'li event/method, gerekli ID ve status alanları tutulabilir. `item/commandExecution/outputDelta`, agent message delta, file change/diff ve patch metni default olarak project edilmez.
- Error response `message` alanı da untrusted content'tir. Regex + length cap tek başına yeterli değildir; rapora yalnız numeric code ve enum error class almak önerilir. İnsan tarafından okunur serbest hata metni gösterilecekse ayrıca sınıflandırılır ve fail-closed redakte edilir.
- JSON parsing/serialization/protocol exception loglarında input satırı, `repr`, raw headers veya exception text yoktur. Malformed/unknown message için line number veya opaque event ID ve sabit `invalid_json`/`unknown_method` code yeterlidir.
- Adapter stdout'unu tüketen üst süreç de allowlist uygular; observer projection'ı veya “known event” etiketi trusted source, secret-free payload, komut tamamlanması ya da Yuva task teslimi anlamına gelmez.

## Sentetik fixture prototipi

`prototypes/output-log-minimization/fixture.py` yalnız bellek içi sentetik environment, argv, header, stdout/stderr ve `item/commandExecution/outputDelta` mesajı kullanır. Rapor allowlist ile oluşturulur; screen kaydı sabit bir durum cümlesi olarak üretilip mevcut redactor'a verilir; app-server adapter'ı output delta metnini almayan metadata projection'ı üretir. Fixture sentetik değerlerin report, screen ve protocol sink'lerine ulaşmadığını kontrol eder.

Fixture ayrıca bir bilinen synthetic Bearer örneğinin redakte edildiğini ve regex'in unknown synthetic secret biçimini değiştirmeden bırakabildiğini gösterir. Dolayısıyla sızıntısız sink sonucu redactor'ın tamlığına değil, free-form argv/env/header/stdout/stderr/delta içeriğinin allowlist'ten dışlanmasına dayanır. Bu fixture gerçek `yuva ekran`, panel/API veya canlı agent session'ı çağırmaz; üretim kontrolü değildir.

Çalıştırma: `python3 prototypes/output-log-minimization/fixture.py`.

## Kaynaklar ve kapsam

- `bin/yuva`: `cmd_ekran()`, `cmd_ekran_oku()`, `ekle_jsonl()`.
- `yuva_screen_redaction.py`: bilinen şekiller için ortak write-time redaction ve fail-closed schema/size kuralları.
- `prototypes/codex-app-server/adapter.py`: outputDelta metadata projection'ı ve dar `_safe_error_message()` helper'ı.
- `docs/screen-secret-redaction-564.md`, `docs/jsonl-redaction-boundary.md`, `docs/model-output-privacy-review-492.md`, `prototypes/codex-app-server/message-bridge-output-privacy.md`.

Bu teslimde canlı Yuva verisi/provider/servis okunmadı; prod komut, environment, header veya subprocess output'u toplanmadı. Yeni production sink/policy entegrasyonu yapılmadı.
