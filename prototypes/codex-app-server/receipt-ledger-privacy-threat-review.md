# Receipt ledger gizlilik, saklama ve artifact referans tehdidi incelemesi

Bu, Yuva görevi #416 için #408 ve #411 tasarım notlarının salt-okunur güvenlik
incelemesidir. Bulgular henüz uygulanmış bir ledger'a ait doğrulanmış
zafiyetler değildir; tasarım uygulanırken kapatılması gereken riskler ve
güvenlik varsayımlarıdır. Kod, test, runtime veya dosya sistemi işlemi yapılmadı.

## Kapsam ve varsayım

İncelenen yüzeyler: [receipt-ledger-design.md](receipt-ledger-design.md)
şemasındaki `payload_json`, digest alanları, `artifacts.immutable_ref`, SQLite
DB/WAL/SHM ve yedekler; [receipt-dedupe-retention.md](receipt-dedupe-retention.md)
içindeki ham payload temizliği, tombstone ve yetim artifact süpürme kararları.
Varsayılan tehdit sınırı aynı hostta güvenilen bir kullanıcı hesabı ve ona ait
tek bir yerel çalışma alanıdır. Aynı UID altında çalışan başka bir süreç
dosya izinleriyle yalıtılamaz; süreç/hesap ele geçirilmesine karşı gizlilik
garantisi verilmemelidir.

## Bulgular

### H1 — `immutable_ref` path olarak tüketilirse path traversal ve symlink kaçışı

**Koşul:** Uygulama `immutable_ref` değerini DB'den veya protokol/iş girdisinden
dosya yolu kabul ederek açar, siler ya da rename eder.

#408 şeması `immutable_ref TEXT` saklıyor ve artifact'i geçici dosyadan
immutable ada rename etmeyi öneriyor; referansın nasıl doğrulanacağını veya
filesystem çağrılarının nasıl root'a hapsedileceğini tanımlamıyor. Mutlak yol,
`..`, separator/encoding hileleri, symlink veya parent-directory değişimi
artifact okuma/silme işlemini artifact root dışına çıkarabilir. Content-addressed
isim tek başına bu sınırı sağlamaz.

**Gerekli kapılar:** Referansı dış girdiden doğrudan kabul etme. Saklanan anahtar
yalnızca biçimi doğrulanmış digest'ten türetilen tek bir dosya adı olsun;
root dizinini güvenli açıp işlemleri `dir_fd`/`openat` benzeri descriptor-relative
yollarla yap, symlink takip etmeyi reddet, mevcut nesnenin düzenli dosya ve
beklenen owner/type olduğunu doğrula. Cross-device veya harici URI referansı
kapalı kalsın. Okumada byte length ve SHA-256'yı doğrula; doğrulama tutmazsa
artifact'i kanıt olarak sunma ve otomatik üzerine yazma.

### H1 — Yetim artifact cleanup canlı/yedek referansı yarışta silebilir

**Koşul:** Süpürücü aynı anda dosya yazan worker'lar, ledger transaction'ı,
WAL checkpoint'i veya yedek alma ile çalışır.

#408'de artifact önce rename edilir, sonra DB satırı commit edilir. Bu sıra crash
sonrası yetim üretebilir; fakat dosyanın DB'de görünmemesi anlık olarak onun
yetim olduğunu kanıtlamaz. Süpürücü bu aralıkta dosyayı silerse DB transaction
başarılı olsa bile kayıt kırık ref'e döner. Benzer şekilde aktif DB dışındaki
backup snapshot'ları da dosyaya referans veriyor olabilir. DB erişilemiyor veya
backup envanteri eksik olduğunda silme kararı güvenli değildir.

**Gerekli kapılar:** Yazım için staging/lease kaydı veya yeterli yaş grace
period'u kullan; aktif writer lease'i olan dosyayı silme. Sweep öncesi tutarlı
SQLite snapshot'ı al ve tüm korunması gereken backup manifestlerini referans
kökü say. DB/backup okunamıyorsa cleanup'ı durdur. Önce candidate listesini
raporla, daha sonra kilitli ve tekrar doğrulamalı silme uygula. Silme öncesi
dosya türü, root üyeliği, digest ve referanssızlık yeniden kontrol edilsin.
Bu işlem DB transaction ve filesystem unlink arasında atomik değildir; retry
edilebilir bir bakım protokolü olarak tasarlanmalı.

### M1 — Hash alanları düşük entropili prompt/çıktı için dictionary ve korelasyon sızdırabilir

**Koşul:** Saldırgan ledger DB/log/backup'i okuyabilir veya digest'leri geniş
çevreye yayılan loglardan görebilir.

`params_sha256`, `payload_sha256` ve artifact SHA-256 hassas plaintext'i
saklamasa da tahmin edilebilir girdiler için bilinen adaylarla karşılaştırma
yapılmasına ve aynı içeriğin farklı görev/attempt'lerde korelasyonuna izin verir.
Örnek: bilinen komut/prompt, küçük olası cevap kümesi, standart veya herkese açık
artifact. #408 digest'i redaction sonrası üretmeyi söylese de hangi alanların
redakte edileceği ve digest'in loglanma sınırı normatif değil.

**Gerekli kapılar:** Varsayılan olarak sadece gerekli metadata'yı tut; raw prompt,
command, approval params, output/delta ve path'leri kalıcılaştırma. Redaction
şeması alan allowlist'iyle ve sürümlü olsun; redaction uygulanamadığında kayıt
fail-closed olsun. Düşük entropili/hassas payload fingerprint'i gerekiyorsa
DB'de olmayan, OS korumalı anahtarla HMAC kullan; anahtar yoksa hassas digest
üretmek yerine dedupe'u ilgili scope'ta kapat veya güvenli bellek içi karşılaştır.
HMAC anahtarı eşitlik korelasyonu sızdırmaya devam eder; trust domain/purpose
kapsamı daralt ve digest'i loglama. Artifact byte-integrity amacı için plain
SHA-256 artifact metadata'sında kalabilir, ancak onu sır/kimlik doğrulama kanıtı
sayma ve erişimini kısıtla.

### M1 — DB, WAL/SHM, temp dosyaları ve backup izinleri tek politika altında bağlanmamış

**Koşul:** Ledger gizli veya kişisel içerik saklar; dosyalar kullanıcı/servis
tarafından açılır, yedeklenir veya eşzamanlı kullanılır.

#408 kısıtlı izin öneriyor, ancak DB, `-wal`, `-shm`, staging/temporary artifact,
backup, export, lock ve parent directory oluşturma sırasını belirtmiyor. DB
dosyasını sonradan chmod etmek kısa bir umask/yarış penceresi bırakabilir.
SQLite backup'ını ham DB kopyası olarak almak WAL ile tutarsız snapshot veya
eksik/kalan hassas sayfa yaratabilir. Aynı UID altındaki süreçler dosyayı yine
okuyabilir; mode bit'leri bunu çözmez.

**Gerekli kapılar:** Önce owner-only (directory 0700, dosya 0600) güvenli state
root'u oluştur; dosyaları kısıtlı umask ve symlink-safe exclusive create ile
aç. WAL/SHM ve geçici dosyaların oluştuğu her bağlantıda gerçek izin/owner
kontrolü yap. Yedekleri SQLite'ın tutarlı backup API'siyle üret; backup/export
için aynı veya daha sıkı ACL, şifreleme, erişim kaydı ve retention uygula.
Aynı UID tehdidi varsa ayrı OS hesabı/servis veya uygulama katmanı şifreleme
gerekir; yerel mode bit'iyle izolasyon iddiası yapılmamalı.

### M1 — `unknown` tombstone'larını süresiz koruma veri minimizasyonu ve kapasiteyle çelişebilir

**Koşul:** İşlem uzun süre uzlaştırılmaz veya saldırgan/bozuk kaynak çok sayıda
belirsiz operation, büyük payload ya da artifact üretir.

#411 doğru olarak unresolved `unknown` kayıtlarına TTL uygulamıyor; bu duplicate
turn açmayı önler. Bununla birlikte `operation_id`, task/run/attempt, thread/turn,
request ID ve digest'leri süresiz tutmak hassas iş ilişkisini ve kullanıcı
aktivitesini açığa çıkarabilir. Aynı zamanda bu kayıtlar için sınırsız saklama
yerel disk doluluğuna ve ledger DoS'una dönüşür. Tasarım kapasite dolunca
gönderimi durduruyor, fakat unresolved state için insan inceleme SLA'sı, erişim
kontrolü ve silme/anonimleştirme kararı tanımlamıyor.

**Gerekli kapılar:** Raw content ve artifact'i minimal süreyle; tombstone'u ise
tanımlı replay/idempotency penceresi ve operasyonel/uyum gereğine göre sakla.
`unknown` durumuna bir owner, oluşturulma zamanı, son uzlaştırma denemesi ve
escalation/SLA bağla. Süresiz bekleyenleri otomatik silmek yerine yetkili
operatörün gerekçeli kapama, yasal hold veya içerik silip sınırlı pseudonymous
tombstone tutma kararı gerekir. Tombstone üzerinde hangi ID/digest'lerin kişisel
veri sayılabileceği için veri sorumlusu kararı ve silme kapsamı tanımlanmalı.
Per-operation/event/payload/artifact boyutları ve toplam disk/WAL bütçeleri
sınırlandırılmalı; bütçe aşımı yeni dış yan etkileri durdurmalı.

### M2 — Digest doğrulaması integrity sağlar; artifact kökenini veya DB bütünlüğünü kanıtlamaz

**Koşul:** Ledger DB ve artifact dizininden biri saldırgan tarafından
değiştirilebilir veya aynı hostta ayrıcalığı olan bir süreç dosyaları yazabilir.

SHA-256'yı tekrar hesaplamak bozulmayı fark eder, fakat saldırgan hem dosyayı hem
DB'deki `sha256`/`immutable_ref` alanlarını değiştirebiliyorsa güvenilir köken
kanıtı sağlamaz. `immutable_ref` adına göre içerik aynı digest'e sahip diye
artifact'in ilgili Codex item'inden veya Yuva mesajından geldiği doğrulanmış
olmaz.

**Gerekli kapılar:** DB ve artifact root aynı güven sınırında owner-only olsun;
artifact manifesti operation/task/run/attempt/item bağı ve digest ile tek
transaction'da saklansın. Daha güçlü yerel saldırgan modeli gerekiyorsa manifest
veya DB snapshot'ı ayrı korunan anahtarla MAC/imzalanmalı; bu tasarımın dışında
anahtar saklama/rotasyon ve doğrulama protokolü gerekir. Receipt'i her zaman
“gözlenen, yerel ledger tarafından kaydedilen” olarak etiketle; yalnız digest'e
dayanarak remote Codex veya reviewer attestation iddiası üretme.

### M2 — SQLite sayfaları, WAL ve backup'ta silinen payload fiziksel olarak kalabilir

**Koşul:** Retention, mevzuat veya kullanıcı silme talebi ham payload'ın
kurtarılamaz biçimde yok edilmesini gerektirir.

#411 ham payload temizliğini ve tombstone saklamayı ayırıyor; SQLite satırını
silmek eski sayfanın DB/WAL/SHM veya backup içinde kalmadığını garanti etmez.
`VACUUM`, WAL checkpoint, snapshot expiry, dosya sistemi snapshot'ı ve SSD
wear-leveling de güvenli fiziksel silmeyi tek başına kanıtlamaz.

**Gerekli kapılar:** Ürün gereksinimi fiziksel/crypto-erasure ise hassas payload'ı
ayrı şifreli blob katmanında, per-scope data encryption key ile sakla; silmede
anahtarı yok et ve tüm backup/replica key lifecycle'ını kapsa. Ledger'daki
tombstone kimliklerini de erasure kapsamı açısından değerlendir. Yalnız SQL
DELETE veya retention cron'u “geri getirilemez silme” olarak belgelenmemeli.

## Uygulama öncesi kabul kapıları

1. `immutable_ref` DB'ye yalnız içerik digest'inden türetilen, root'a hapsedilmiş
   opaque key olarak yazılmalı; mutlak path/URI/`..` reddedilmeli.
2. Artifact read/delete işlemleri symlink/path traversal testleriyle sınır
   altında kalmalı; içerik digest ve byte length her okumada doğrulanmalı.
3. Concurrent writer, crash aralığı, backup ve cleanup senaryolarında yetim
   süpürücü aktif/yedek referanslı artifact'i silememeli; DB erişilemezken
   cleanup çalışmamalı.
4. Hassas protokol alanlarının allowlist/redaction politikası, digest scope'u,
   log filtresi ve aynı UID tehdidi açıkça belgelenmeli.
5. DB/WAL/SHM/temp/artifact/backup izinleri, owner ve güvenli oluşturma sırası
   hedef Linux ortamında doğrulanmalı; tutarlı backup ve restore prosedürü
   tanımlanmalı.
6. Unknown tombstone için owner/SLA/escalation ve veri silme/pseudonymization
   kararı belirlenmeli; disk/WAL/payload/artifact limit aşımı dış gönderimi
   kapatmalı.
7. Hash'in gözlem bütünlüğüyle sınırlı olduğu; remote origin, exactly-once,
   Yuva `verified` veya Codex doğrulaması olmadığı her UI/raporda korunmalı.

## Sonuç

En önemli uygulama öncesi riskler artifact referansını root dışına çıkarabilecek
filesystem işlemleri, DB/WAL/backup ve cleanup arasındaki tutarsız saklama
sınırı, düşük entropili payload digest'lerinin sızıntısı ve süresiz unknown
tombstone'larının gizlilik/kapasite etkisidir. #408/#411 tasarımları fail-closed
ve içerik minimizasyonu yönünde doğru ilkeleri içeriyor; fakat yukarıdaki
uygulama kapıları netleşmeden production ledger güvenlik veya silme garantisi
veremez.
