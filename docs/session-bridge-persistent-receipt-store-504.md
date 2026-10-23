# Kalıcı receipt store geçiş mimarisi (#504)

**Durum:** mimari öneri; uygulama, kalıcılık veya exactly-once garantisi değildir.
`prototypes/session-bridge/outbox.py` bellek içidir. Bu not onu restart sonrası
uzlaştırılabilir bir store'a taşımayı ve Yuva görev bildirimi sınırını ayrı
tanımlar. Dayanaklar: #476 prototipi, #452 hata matrisi ve #437 Yuva görev
mutasyonu/outbox tasarımı.

## Önerilen store ve kayıt modeli

Provider/session outbox için uygulamanın tek yazıcılı süreç varsayımına bağlı
kalmayan, yerel diskte tek bir transactional store önerilir (ör. ayrı SQLite
veritabanı). İşlem makbuzu ve gönderilecek payload aynı transaction içinde
yazılmalı; `event_id` benzersiz anahtar, `payload_digest` aynı anahtarın içerik
bağını, `operation_id` üst seviye mantıksal işi, `attempt_id` tek gönderme
girişimini tanımlamalıdır. Kayıt en az şunları taşır:

- `event_id`, `operation_id`, canonical payload ve digest;
- `pending | sending | accepted | delivered | not_sent_proven | unknown | rejected` durumu;
- attempt sayısı/kimliği, zamanlar, güvenli hata sınıfı ve varsa dış receipt;
- son reconcile sonucu ve karar/evidence referansı.

Payload yalnız `pending`/çözümlenmemiş durum gerekirken saklanır. Terminal
receipt ve dedupe tombstone payload silindikten sonra da key/digest/terminal
sonucu tutabilir. Secret, auth bilgisi ve gereksiz provider çıktısı receipt'e
kopyalanmamalı; payload hassas sayılıp store erişimi, yedek ve silme politikasına
bağlanmalıdır. Store açılmazsa, şema tanınmazsa veya kapasite dolarsa gönderim
kapalı kalır; kayıtlar yer açmak için sessizce atılmaz.

Bu örnek bir tercih olarak verilmiştir, zorunlu teknoloji kararı değildir.
SQLite seçilirse transaction/senkronizasyon ayarı, dosya ve dizin izinleri,
aynı anda çalışan writer sayısı, yedek ve restore davranışı platform üzerinde
ayrıca karara bağlanıp doğrulanmalıdır. `outbox.py`'nin varsayılan bellek
sınırları kalıcı store için saklama politikası sayılmaz.

## Provider/session gönderim sınırı

| Adım | Kalıcı sınır ve durum | Hata / restart davranışı |
|---|---|---|
| Kaydet | Tek transaction: yeni `event_id` + digest + payload + `pending`. Aynı key/aynı digest eski makbuzu döndürür; farklı digest conflict olur. | Transaction kesin commit olmadıysa gönderim çağrılmaz. Commit sonucu belirsizse key ile store okunur; yeni ID üretilmez. |
| Göndermeye hazırla | Aynı transaction içinde `pending → sending`, yeni `attempt_id` ve başlangıç bilgisi commit edilir; ancak sonra dış write başlar. | Restart'taki `sending` **unknown** yapılır; yeni deneme başlatılmaz. Yalnız `pending` daha önce hiç write başlamadığı store tarafından kanıtlanıyorsa dispatch edilebilir. |
| Dış sonuç | Callback sonucu ayrı transaction ile kaydedilir. `accepted` teslim değildir. `delivered`/`rejected` yalnız tanımlı dış receipt kanıtıyla terminal olur. | Tam write/flush veya provider cevabı kaybolduysa unknown. Açık sıfır-byte kanıtı aynı işlem için `not_sent_proven` olabilir; partial/exception/timeout kör retry yetkisi vermez. |
| Uzlaştır | Read-only lookup aynı `event_id`/provider idempotency key üzerinden yapılır; kanıt ve sonuç birlikte kaydedilir. | `not_found` tek başına negatif commit kanıtı değildir; lookup stale veya iş hâlâ sürüyor olabilir. Sonuç unknown kalır. |

Store state geçişleri tek transaction ve compare-and-set benzeri beklenen eski
durum kontrolüyle yapılmalı; farklı worker aynı `pending` olayı eşzamanlı
claim edememelidir. Ağ çağrısı transaction açıkken yapılmaz. Worker lease'i
kullanılırsa lease kaybı/süresi dolması `sending` kaydını yeniden `pending`
yapmaz; önce unknown olarak uzlaştırılır. Dış sistem stable idempotency key
desteklemiyorsa, operatörce onaylanmış yeni girişimin uzak etkileri çoğaltma
riski açık kalır. Yerel receipt store uzak sisteme exactly-once sağlamaz.

## Yuva görev değişikliği ve bildirim

Yuva task mutasyonu, provider/session receipt store'a ayrı transaction ile
yazılıp görev değişikliğiyle eşzamanlıymış gibi gösterilmemelidir. #437/#452
uyumlu en küçük yol: tek Yuva task snapshot commit'inde görev alanı + geçmiş
olayı + operation makbuzu + JSONL outbox olayı birlikte kalıcılaşır. Mevcut
JSON snapshot yaklaşımı korunursa tüm CLI/panel writer'ları ortak kilidi
kullanmalı; temp dosya yazımı/flush, atomik replace ve üst dizin `fsync`
sırası tanımlanmalıdır. Herhangi bir dayanıklılık sonucu belirsizse operation
`commit_unknown` olur, outbox dispatch edilmez ve aynı operation key ile
uzlaştırılır. Görev `committed` sonucu bildirim teslim durumundan ayrı sunulur.

JSONL ayrı dosya olduğundan bildirim gönderimi task commit'inin parçası olamaz:

1. Worker yalnız kalıcı task snapshot'ındaki `pending` event'i alır.
2. Ortak JSONL yazma kilidinde event ID'nin gereken tam aralıkta varlığını ve
   dosya kuyruğunun sağlığını kontrol eder. UI için bounded tail, tüm arşivde
   dedupe kanıtı yerine kullanılamaz.
3. Yoksa LF ile sonlanan payload'ı append eder; write/flush/fsync/readback
   sözleşmesi başarıyı kanıtlamadan outbox `delivered` yapılmaz.
4. Append'ten sonra `delivered` snapshot commit edilmeden çökülürse worker
   aynı event ID ile readback yapar; kayıt zaten varsa tekrar append etmeyip
   outbox durumunu dayanıklı günceller.
5. Partial/bozuk tail, okunamayan geçmiş veya append/fsync sonucu belirsizse
   `delivery_unknown` olarak durur. #450 kurtarma onayı olmadan truncate,
   düzeltme, otomatik tekrar veya arşiv silme yoktur.

Bu model task commit'i için tek kalıcı sınır; JSONL teslimi için idempotent
uzlaştırma sunar. İki dosyada tek atomic transaction veya koşulsuz exactly-once
teslim sağlamaz. Ayrı SQLite store Yuva task snapshot'ını da kapsayacak şekilde
kullanılacaksa dosya + veritabanı arasında transactional outbox/rehabilitasyon
mekanizması tasarlanmalı; iki tarafta bağımsız commit yeterli değildir.

## Restart, unknown ve tekrar politikası

- Açılışta schema/owner/izin ve bütünlük denetimi yapılır. Store okunamıyorsa
  yeni dispatch yapılmaz; ham store ve yedek salt okunur korunur.
- `pending` yalnız gönderme başlangıcının hiç kaydedilmediği durumda hazırdır.
  `sending` → `unknown`; `accepted` busy/çözümlenmemiş kalır; terminal durumlar
  terminal receipt ile korunur. `unknown` event otomatik `pending` olmaz.
- Yalnız taşıma katmanı aynı event'in dışarı sıfır byte gönderildiğini açıkça
  kanıtlarsa `not_sent_proven` kalıcılaştırılır ve aynı event ID/operation için
  yeni attempt açılabilir. Kanıt yoksa yeni attempt ayrıca insan kararıdır ve
  olası duplicate etkisi receipt'e kaydedilmelidir.
- Reconcile sonucu yalnız açıkça tanımlı ve aynı event'e bağlı kanıtsa
  terminal state'i çözer. Yokluk veya tek bir arama cevabının gelmemesi
  `not_sent_proven` değildir.
- Aynı `event_id` + aynı digest replay'dir; aynı ID + farklı payload
  `idempotency_conflict` verir. Operation makbuzu ile dış event receipt ayrı
  kimlik ve durum alanlarıdır; biri diğerinin teslimini kanıtlamaz.
- Payload kaldırıldıktan sonra bile tombstone'un ne kadar tutulacağı, maksimum
  retry/reconcile penceresi ve süresi dolmuş key'in davranışı seçilmelidir.
  Bu değerler kararlaştırılana kadar tombstone temizliği/ID yeniden kullanımı
  kapalı kalmalı. Süresi geçmiş receipt'i yok sayıp mutation/send'i yeni kabul
  etmek duplicate riskidir.
- Boyut/record limiti dolarsa açık hata ve operatör müdahalesi gerekir. Çözümsüz
  receipt, tombstone veya `unknown` kaydı yer açmak için silinemez.

## Uygulama öncesi açık kararlar

1. Kalıcı backend seçimi; SQLite ise senkronizasyon modu, tek/çok yazıcı
   protokolü, upgrade/backup/restore ve store kilidi.
2. Provider başına idempotency key desteği, `accepted`/`delivered` kanıtı ve
   readback'in tutarlılık/otorite sınırı.
3. Operation/event ID namespace'i, canonical payload digest sözleşmesi ve
   unknown sonrası insan onaylı yeni attempt kaydı.
4. Payload, receipt, terminal tombstone ve yedek saklama süresi/boyutu;
   kapasite dolunca işletim ve alarm sorumluluğu.
5. Yuva JSON snapshot'ı ile JSONL outbox'ın tek ortak writer/lock/fsync
   sözleşmesi ve legacy writer rollout/kapama planı.

Bu kararlar ölçülüp kabul edilmeden üretime geçiş, otomatik retry, tombstone
silme veya gerçek provider dispatch'i açılmamalıdır.

## Kaynaklar

- `prototypes/session-bridge/outbox.py` ve aynı dizindeki `README.md` — mevcut
  bellek içi state'ler, kapasite davranışı, retry ve reconcile sınırları (#476).
- `docs/task-mutation-failure-matrix-452.md` — `commit_unknown` ile
  `delivery_unknown` ayrımı, failure noktaları ve çözülmemiş kararlar.
- `docs/task-mutation-idempotency-outbox-design-437.md` — görev + operation +
  outbox'ın tek snapshot commit'i ve JSONL event ID ile dedupe önerisi.
- `docs/jsonl-tail-recovery.md` — bozuk/yarım JSONL kuyruğunda ham veriyi
  koruma ve operatör kontrollü kurtarma.
