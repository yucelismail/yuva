# #452 — Görev mutasyonu ve outbox hata matrisi

Bu not, `docs/task-mutation-idempotency-outbox-design-437.md` tasarımını
hata enjekte etmeden, adım adım teorik olarak inceler. Matris hedef tasarımı
anlatır; mevcut uygulamanın bu garantileri sağladığı anlamına gelmez.

## Durum ve yanıt sözlüğü

| Sınıf | Görev/operation durumu | Bildirim durumu | API sonucu | İstemcinin eylemi |
|---|---|---|---|---|
| `rejected` | Görev değişmez; operation makbuzu yazılmaz | Outbox yok | 4xx, validation/domain hata kodu | Payload/önkoşulu düzelt. Aynı key'in reddedilmiş işlem için tüketilip tüketilmediği aşağıdaki açık karardır. |
| `committed` | Görev + geçmiş + makbuz + outbox aynı atomik snapshot'ta | `pending` veya `delivered` | 200; bildirim bekliyorsa 202 ya da 200 + açık `notification=pending` | Aynı key ile sonucu sorgula/tekrar et; yeni key açma. |
| `idempotency_conflict` | Var olan görev/makbuz değişmez | Değişmez | 409 | Aynı key için payload değiştirme; yeni mantıksal işlemse yeni key kullan. |
| `commit_unknown` | Replace/child/yanıt sınırında kalıcılık belirsiz | Outbox yayımlanmaz; mevcutsa pending kalır | Ayrı belirsizlik sonucu (önerilen 503 veya yapılandırılmış 202; kesin başarı/ret değildir) | Kör retry veya yeni key yok; aynı key ile makbuz/status uzlaştır. |
| `delivery_unknown` | Görev commit'i kesin | JSONL append sonucu belirsiz | `committed`, bildirim `unknown`; mutation başarısız diye gösterilmez | Aynı event ID ile readback/recovery; bozuk veya kısmi tail incelenene kadar yeni append yok. |

`commit_unknown` ve `delivery_unknown` birbirinin yerine geçmez: ilki görev
snapshot'ını, ikincisi görev commit'i kesinleştikten sonraki JSONL bildirimi
anlatır. Bir HTTP yanıtının kaybolması da tek başına bunlardan hangisinin
olduğunu kanıtlamaz; aynı operation makbuzu sorgulanmalıdır.

## Hata matrisi

| Hata noktası / yarış | Kalıcı görev durumu | Outbox / JSONL | Makbuz ve yanıt | Tekrar davranışı |
|---|---|---|---|---|
| JSON/payload doğrulaması veya geçiş önkoşulu, snapshot yazımından önce reddedilir | Değişmez | Outbox ve JSONL yok | `rejected`, 4xx | Aynı payload yeniden reddedilir. Key reddedilen payload'a bağlandı mı kararı verilmelidir. |
| Geçici dosya yazımı/JSON serialize/replace öncesi hata | Eski snapshot geçerli kalır; görev değişmez | Bildirim yok | Kesin `rejected` yalnız eski snapshot'ın korunduğu biliniyorsa; aksi halde storage error | Yeni operation açma. Aynı key ile makbuz sorgula; geçici dosya temizliği ayrıca ele alınır. |
| `os.replace` tamamlanmadan hata | Eski snapshot görünür | Bildirim yok | Eski snapshot/operation kaydı doğrulanabiliyorsa `rejected` veya retryable storage error | Aynı key, aynı digest ile tekrar denenebilir; yalnız eski durum doğrulanınca. |
| `os.replace` tamamlandı, üst dizin `fsync` başarısız | Yeni snapshot şu an görünür olabilir, crash sonrası kalıcılığı kesin değil | Outbox kaydı snapshot'ta olabilir; worker bekletilir | `commit_unknown`; başarı veya ret diye sınıflandırılmaz | Aynı key okunur. Kayıt varsa directory durability retry edilir; durability teyit edilmeden `committed` denmez. Kayıt yoksa eski state doğrulandıktan sonra aynı key işlenebilir. |
| Aynı key + aynı digest eşzamanlı iki istek | Kilit altında yalnız biri geçişi yazar | Tek event ID/outbox kaydı | İkisi de aynı kayıtlı `committed` sonucunu görür; ikinci istek replay'dir | Mutation tekrar edilmez; notification worker tek event'i uzlaştırır. |
| Aynı key + farklı digest eşzamanlı istek | Kilit sırası kazananı belirler; yalnız kazanan değişiklik yapar | Yalnız kazananın outbox kaydı olabilir | Kaybeden `idempotency_conflict`, 409 | Çakışan payload için state değişmez; yeni mantıksal işlem ayrı key alır. |
| Görev + operation + outbox commit edildi, worker başlamadan süreç çöktü | Commit kesin; makbuz durur | Outbox `pending`, JSONL'ye yazılmamış | `committed`, notification pending (202 veya açık alan) | Worker restart sonrası pending event'i aynı ID ile teslim eder. İstemci mutation'ı yeniden açmaz. |
| JSONL append başarılı, outbox `delivered` commit edilmeden süreç çöktü | Görev ve operation commit'i durur | JSONL'de event ID var; outbox pending görünebilir | `committed`, geçici notification belirsiz | Worker önce event ID readback/dedupe yapar; yeniden satır append etmeden outbox'ı delivered yapar. |
| JSONL append kısmi, write hata verdi veya son satır bozuk olabilir | Görev commit'i kesin | JSONL tail belirsiz; outbox pending/unknown | `committed`, notification `delivery_unknown` | Aynı event ID otomatik tekrar append edilmez. Tail operatör kontrollü kurtarma/uzlaştırma görmeden worker durur. |
| JSONL append sonucu kesin, fakat `delivered` snapshot yazımı replace/fsync'te belirsiz | Görev commit'i kesin | Event JSONL'de bulunabilir; outbox durumu eski veya yeni snapshot'a bağlı | Mutation `committed`; notification durumu uzlaştırılana dek unknown | Aynı event ID'yi JSONL'de bul; varsa delivered işaretini dayanıklı kaydet, yoksa append'i güvenli biçimde sürdür. |
| Child CLI commit'ten önce doğrulama hatasıyla non-zero döndü | Mutasyon yok (ancak hata sınıfı yapılandırılmış olmalı) | Bildirim yok | `rejected` 4xx | Düzeltilmeden retry etme. |
| Child CLI commit sonrası bildirim veya durability hatasıyla non-zero döndü | Commit edilmiş veya belirsiz olabilir | Outbox yoksa tasarımla çelişir; outbox varsa pending/unknown | Serbest stderr/exit code ile `rejected` denmemeli; receipt'e göre `committed` veya `commit_unknown` | Aynı key ile makbuz uzlaştır; kör retry yok. |
| Panel `subprocess.run` timeout'u | Çocuk henüz commit etmemiş, commit ediyor veya bitirmiş olabilir | Herhangi bir noktada olabilir | `commit_unknown`, HTTP 500/400 gibi kesin failure değil | Aynı key ile status sorgula; yeni operation açma. |
| Mutation/outbox commit edildi, HTTP response yazımı veya ağ sırasında kayboldu | Commit kesin | Pending veya delivered | İstemci sonucu bilmiyor; sunucu kaydı `committed` | Aynı key tekrarında kayıtlı makbuz dön; ikinci mutation yok. |
| Makbuz retention süresi doldu, eski client daha sonra retry etti | Makbuz yoksa eski mutation ile yeni çağrı ayırt edilemeyebilir | Eski outbox teslim edilmiş olabilir | Belirsiz; 404 sonrası işlemi çalıştırmak duplicate üretme riski taşır | Tombstone/retention bitmeden retry penceresi kapatılmalı; süresi dolmuş key'i otomatik yeni mutation gibi kabul etme kararı açık olmalı. |

## Mevcut tasarımla çelişen veya netleştirilmesi gerekenler

1. **`rejected` operation key'i tüketiyor mu?** Yanıt tablosu doğrulama
   hatasını `rejected` makbuz diye adlandırıyor; uygulama adımları ise mevcut
   makbuz yoksa önce doğrula, sonra başarılı mutasyonla beraber makbuz yaz
   diyor. Ret kaydı kalıcı değilse aynı key farklı payload ile kullanılabilir.
   Retention/çakışma anlamı ve key'in ne zaman “harcanmış” sayıldığı
   belirlenmeli.

2. **Directory `fsync` sonrası operation kaydını bulmak, commit'in dayanıklı
   olduğunu tek başına kanıtlamaz.** Tasarım “operation varsa makbuzu döndür”
   cümlesini, “directory durability yeniden denenip makbuz döndürülür” şartıyla
   birlikte veriyor. Uygulama önce `fsync` başarıyla tamamlamadan `committed`
   raporlamamalı; yoksa crash sonrası kayıp mümkün.

3. **`commit_unknown` için HTTP kodu kesin değil.** Tasarım “ayrı semantik” ve
   başka yerde 202 veya açık alan öneriyor. 202, 503 veya 500 istemci
   kütüphanelerinde farklı retry davranışına yol açabilir. Tek status/body
   sözleşmesi, retry-after/poll kuralı ve operation-status sorgusu
   tanımlanmalı. İstemci her durumda aynı key'i saklamalı.

4. **Panelin CLI sonucu yapılandırılmış receipt olmalı.** Bugünkü
   `panel/server.py:936-1000` CLI non-zero sonucunu HTTP 400, subprocess
   exception/timeout'u HTTP 500'e çeviriyor. Bu ayrım commit öncesi ret ile
   commit sonrası belirsizliği taşıyamaz. CLI stdout/stderr metni tek başına
   API sınıflandırma protokolü olmamalı.

5. **JSONL `event_id` dedupe ile dosya bozulma/kısmi tail kuralı birlikte
   tanımlanmalı.** Readback tüm gerekli geçmişi kapsamalı; sadece bounded UI
   tail'iyle dedupe yapılmamalı. ID bulunamadı diye kısmi/bozuk son satırın
   üstüne append etmek güvenli değildir. Tasarım bu riski belirtse de worker'ın
   hangi durumda duracağı ve recovery'nin nasıl onaylanacağı normatif değil.

6. **Canonical digest ve scope kesin değil.** “Normalize edilmiş payload”
   için JSON key sırası, Unicode, sayı/boolean türleri, varsayılan alanlar,
   alias çözümü ve hedef kimliğin canonical biçimi belirtilmeli. `<scope>`'un
   operation adı, tenant/client veya doğrulanmış principal içeriği de
   tanımlanmalı. HMAC principal namespace'i gelene kadar `--from`/`kimden`
   namespace olarak kullanılamaz; bu tasarım bunu doğru biçimde not ediyor.

7. **Operation ID bir bearer receipt anahtarı gibi davranabilir.** Aynı
   key'e sahip çağıran önceki sonucu alabilir. Yüksek entropi ve güvenli
   saklama şartı, key'in URL/loglarda görünmemesi, key başına makbuz yanıtında
   hassas ayrıntıların sınırlandırılması ve gerekiyorsa actor authorization
   ayrıca çözülmeli. Idempotency tek başına yetki değildir.

8. **Tombstone ve retry penceresi sayısallaştırılmamış.** Saklama süresi
   belirsizken eski key'in ne zaman yeni mutation gibi ele alınacağı da
   belirsizdir. En uzun istemci retry/uzlaştırma süresi, tombstone TTL'i ve
   süre aşımı sonucu birlikte kararlaştırılmalı.

## Önerilen API sınıflandırma özeti

| HTTP sonucu | Makine kodu | Güvenli yorum |
|---|---|---|
| 400/422 | `validation_failed` / domain hata kodu | Doğrulama reddi; uygulama adımları state'e dokunmadıysa kesin mutation yok. |
| 409 | `idempotency_conflict` | Bu key başka digest'e bağlı; mevcut kayıt korunur. |
| 200 | `committed` | Operation receipt kalıcı; mutation ikinci kez uygulanmaz. Bildirim `pending` olabilir ve ayrı alanda görünmelidir. |
| 202 | `committed` + `notification=pending` | Görev commit'i kesin, bildirim işi sürüyor. Mutation'ı yeni key ile tekrar etme. |
| Tek belirlenmiş kod (önerilen 503) | `commit_unknown` | Kalıcılık belirsiz; kesin başarı/ret değil. Aynı key ile uzlaştır. |
| 200/202 | `committed` + `notification=delivery_unknown` | Görev commit'i kesin; yalnız mesaj teslimi belirsiz. Aynı event ID ile recovery. |
| 401/403 | auth code | Mutasyon aşamasına girilmeden ret; authorization ve idempotency receipt davranışı ayrı sözleşme olmalı. |

Mevcut panel köprüsü bugün bu sınıflandırmayı sağlamaz. Tasarımın uygulanması,
CLI, panel, JSONL writer/worker ve istemcinin operation key yaşam döngüsünü
birlikte güncellemesini gerektirir.
