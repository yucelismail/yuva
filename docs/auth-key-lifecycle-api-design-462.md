# Auth key provisioning ve lifecycle API tasarımı (#462)

- **Durum:** Uygulama öncesi tasarım önerisi; canlı auth/provisioning talimatı değildir.
- **Kapsam:** İlk key, enrollment, rotation, revocation, denetim, kurtarma ve olası yönetim API'si.
- **Mevcut kod:** `AuthStateStore.read()`/`transact()`, POST auth gate ve yalnız boş v2 store kuran `yuva auth init` vardır; key/enrollment lifecycle komutları veya endpoint'leri yoktur. `YUVA_AUTH_ENABLED` default-off kalır.

## Tasarım kararları

1. **Bootstrap ve kurtarma çevrimdışı kalır.** İlk store, ilk admin verifier key'i,
   `YUVA_AUTH_ADMIN_PRINCIPALS` güven kökü, dış generation anchor kurulumu ve
   rollback/backup sonrası yeniden provision işlemleri yalnız güvenilir host
   operatör aracı/runbook ile yapılır. `yuva auth init` boş store ve stable
   lock dışında credential/anchor kurmaz; ilk key ve allowlist için güvenilir
   custody aracı hâlâ yoktur. API kendi yetkisini veya ilk admin key'ini
   kendisi yaratamaz.
2. **Rutin işlemler için ileride sınırlı API düşünülebilir.** Admin key ile
   doğrulanan enrollment oluşturma/iptal ve verifier key iptali yönetim
   route'ları olabilir. İmtiyazsız tek kullanımlık enrollment token ile
   redeem ayrı bir route olur. Bu endpoint'lerin hiçbiri şu an mevcut değildir.
3. **Secret taşıma kapısı kapanmadan online enrollment yok.** Mevcut panel HTTP
   loopback'te ve kimliksiz GET'ler sunuyor; farklı UID'ler aynı network
   namespace'ten loopback'e erişebilir. HMAC secret'ı veya enrollment token'ı
   URL, browser, log ya da mesajda taşınmaz. Redeem yalnız açıkça kabul edilmiş
   güvenli istemci kanalı/dağıtım sınırı üzerinden tasarlanabilir; aksi halde
   bu işlem de offline provision olarak kalır.

## Önerilen yaşam döngüsü

### İlk verifier key

- Offline operatör aracı CSPRNG ile 32 byte secret üretir; key'e benzersiz ID,
  sabit audience, principal, exact `METHOD /path` scope listesi, `not_before`,
  kısa ve açık `expires_at`, `revoked=false` ve `enrollment_digest=null` verir.
- İlk admin principal allowlist'i operator config'inden gelir; payload, görünen
  rol veya enrollment isteği admin yetkisi oluşturamaz. İlk key ve allowlist
  bağımsız ikinci kişi/kanal incelemesiyle eşleştirilir.
- Secret yalnız hedef istemciye owner-only credential store veya eşdeğer
  korumalı teslim yöntemiyle verilir. Secret stdout, komut satırı, sohbet,
  JSONL, audit kaydı ya da genel yedeğe yazılmaz. Aynı servis UID'sindeki
  süreçlerden dosya izinleriyle gizlenemeyeceği kabul edilir.
- Tam şemalı snapshot ile sabit lock dosyası staging'de hazırlanır, izinleri
  doğrulanır ve atomik kurulumla devreye alınır. Çalışan store elle
  düzenlenmez; auth açma ayrı inceleme ve işletim kabulüne bağlıdır.

### Enrollment ve redeem

Gelecekteki, henüz kararlaştırılmamış route adları örneğin
`POST /api/auth/enrollments` (admin create),
`POST /api/auth/enrollments/redeem` (token holder redeem) ve
`POST /api/auth/enrollments/revoke` olabilir. Bunlar mevcut `POST_ROUTE_POLICY`
ve verifier scope'larında yoktur; eklenmiş gibi kabul edilmemelidir.

1. Admin create isteği için operator-admin principal, exact route scope ve
   payload doğrulaması gerekir. Oluşturucu `principal_id`, `audience`, izinli
   scope'lar, `issuer_key_id` ve kısa expiry seçer. Scope'lar issuer'ın
   yetkisini aşamaz; özellikle admin/role yönetim scope'u normal enrollment'a
   verilemez. Mevcut state validator scope biçimini kontrol eder, fakat
   issuer-scope alt kümesini tek başına garanti etmez; bu yetki kuralı yeni
   servis politikasında uygulanmalıdır.
2. Token CSPRNG ile üretilen yüksek entropili tek kullanımlık opaque değerdir.
   Store map anahtarı `SHA-256(token)` olur; ham token yalnız bir kez, kabul
   edilmiş korumalı kanaldan teslim edilir. URL, access log, exception veya
   audit event'e girmez. Kayıt `pending` olur ve tüketim alanları boş kalır.
3. Redeem sırasında token digest kaydı bulunur; tokenın kendisi kriptografik
   MAC doğrulama anahtarı değildir. İstek sahibi client-side 32 byte HMAC
   secret üretir; yalnız güvenli enrollment kanalı kabul edilirse secret body'de
   sunucuya gider ve yanıt secret'ı yeniden döndürmez. Client secret'ı
   kendisi bildiğinden kurulum teslimi idempotent olabilir.
4. Tek `transact()` içinde pending/expiry/issuer aktifliği ve scope kısıtları
   doğrulanır; key eklenir (`enrollment_digest` ile bağlanır) ve enrollment
   `consumed` yapılır. `consumed_at`, benzersiz `operation_id`, secret'ın
   SHA-256 fingerprint'i ve `key_id` aynı commit'te yazılır. Böylece aynı token
   ikinci key yaratamaz.
5. Pending enrollment iptali `status=revoked` ve boş tüketim alanlarını tek
   transaction'da yazar. Tüketilmiş enrollment iptali, bağlı key'in
   revocation'ıyla aynı transaction'da yapılır; kayıttaki tüketim ilişkisi
   saklanır.

Mevcut şema `pending`/`consumed`/`revoked`, issuer-key bağı, tüketim
`operation_id`'si ve key-enrollment bağını doğrular. Store token üretmez,
imzalamaz, endpoint çağırmaz veya lifecycle işlemi uygulamaz.

### Rotation ve revocation sırası

1. Eski key aktifken yeni key'i daha dar/aynı gerekli scope ile çıkar; expiry'yi
   belirle ve hedef client'a güvenli biçimde provision et.
2. Yeni key'in non-destructive bir doğrulama yolunda gerçekten çalıştığını
   teyit et. Mevcut yönetim API'si veya read-only auth probe yoktur; mutasyon
   endpoint'ini deneme amacıyla çağırma. Böyle bir probe tasarlanmadan rollout
   geçişi manuel ve offline kabul kapısıdır.
3. Yalnız doğrulanan client'lar için kısa ve önceden belirlenmiş overlap
   süresinden sonra eski key'i `revoked=true` yap. Kayıt silme yerine tombstone
   tut; enrollment/issuer referansları ve denetim bağı kopmasın.
4. Key issuer ise aynı transaction'da ona ait bütün `pending` enrollment'ları
   `revoked` yap. Validator, iptal issuer altında pending enrollment
   bırakılmasını reddeder. `consumed` enrollment ve bağlı key geçmişi korunur.
5. Acil compromise halinde overlap beklenmez: verifier key ve pending
   enrollment'lar birlikte iptal edilir; etkilenen client'lar yeni secret ile
   yeniden provision edilir. Eski key secret'ı rapora veya audit'e kopyalanmaz.

## CommitUnknown ve idempotency

`AuthStateStore.transact()` replace sonrası directory fsync hatasında
`CommitUnknown` döndürebilir. Bu, değişikliğin commit olmadığını göstermez.
İstek başarısız göründü diye kör retry yapmak ikinci key, farklı enrollment
sonucu veya yanlış audit bildirimi oluşturabilir.

- Her lifecycle isteği client tarafından önceden üretilmiş benzersiz
  `operation_id` taşımalı; ID principal ve operasyon türü kapsamında
  idempotency anahtarı olmalıdır. Mevcut enrollment redeem bunu state kaydında
  tutabilir; create/revoke için genel operation receipt henüz yoktur.
- **Önerilen şema eklentisi:** bounded `operations`/outbox map'i, domain
  değişikliği ve denetim event'inin özetiyle aynı v2+ snapshot transaction'ında
  yazılır. Sadece RAM cache veya ayrı dosyaya sonradan yazma yeterli değildir.
  Şema sürümü/limit ve retention kararı verilmeden bu alan eklenmiş sayılmaz.
- `CommitUnknown` sonrası aynı operation ID ile read/reconcile yapılır:
  receipt/domain state aynı payload fingerprint'i ve hedefi gösteriyorsa
  mevcut sonuç döndürülür; operation yok ve önkoşul hâlâ geçerliyse aynı ID
  ile kontrollü retry düşünülebilir; çelişkili/eksik durum varsa fail-closed
  durur ve offline incelemeye yükseltilir. Yeni operation ID ile tekrar
  başlatılmaz.
- Reconcile'da görülen generation yalnız aktif store snapshot'ına göredir.
  Eski backup restore'unu tek başına saptamaz; dış anchor ve restore policy
  ayrı karardır (bkz. #458 / auth-state v2 operasyon kılavuzu).

## Audit, sınırlar ve kapasite

Audit event en az UTC zamanı, `instance_id`, generation, `operation_id`,
actor principal/key ID, işlem türü, hedef key/enrollment ID, scope fingerprint,
sonuç ve `CommitUnknown` reconciliation durumunu taşır. Secret, token, imza,
raw request body veya token digest loglanmaz. Mevcut store'da audit event
koleksiyonu yoktur; ayrı JSONL append tek başına domain commit'iyle atomik
değildir. Öneri: transaction içinde bounded audit outbox/receipt yaz; dış
append-only audit sink'e event ID ile idempotent aktar, ardından teslim
durumunu kaydet. Outbox şema değişikliği, tam disk davranışı, retention,
erişim ve dış audit sink kaybı için kabul kapıları gerektirir. Aynı UID/root
ve host yöneticisi audit dosyasını değiştirebilir; tek başına bağımsız
non-repudiation değildir.

Mevcut format üst sınırları `MAX_STORE_BYTES=1 MiB`, `MAX_KEYS=4096`,
`MAX_ENROLLMENTS=100000`, `MAX_NONCES=100000`, `MAX_RATE_LIMITS=10000`,
`MAX_SCOPES=256` ve ID başına 128 byte'dır. Bunlar servis için önerilen hedef
kota değildir. Server POST gövde tavanı 1 MiB'dir; lifecycle route'ları bu
genel tavana yaslanmamalı, küçük endpoint-specific body/scope/token
limitleri uygulamalıdır.

Gelecek uygulama için kabul edilecek başlangıç politikası önerisi:

- Create/revoke yalnız doğrulanmış admin principal; redeem yalnız bir kez
  kullanılabilen geçerli enrollment token; bilinmeyen actor/route fail-closed.
- Request başına sınırlı scope sayısı (öneri: en çok 32), scope başına kısa
  exact method/path uzunluğu ve küçük lifecycle JSON body (öneri: 16 KiB).
- Enrollment expiry dakikalarla ölçülen kısa süreli olmalı; üst sınır ve
  overlap süresi ürün/operatör kararıyla sabitlenmeli, sınırsız istenemez.
- Admin mutation, redeem başarısızlığı ve token denemeleri principal ve
  enrollment/issuer bazında rate-limit edilir; anonim kaynak için de kaba
  global limit gerekir. 429/503 davranışı, Retry-After, bucket temizliği ve
  limit tablosu dolduğunda reddetme kuralı implementasyondan önce belirlenir.
- Expired enrollment ve nonce/rate bucket temizliği bounded batch ile yapılır.
  Key/enrollment tombstone'ları audit/restore gereksinimi karara bağlanmadan
  otomatik silinmez. 1 MiB store veya koleksiyon limiti yaklaşınca issuance
  yeni kayıt kabul etmez; mevcut key'leri sessizce prune etmez.

## Geri alma ve kurtarma

- Rutin key revoke transaction'ı geri çevrilmez; yeniden yetki gerekiyorsa
  yeni key çıkarılır, eski key'i un-revoke etmek yerine yeni credential
  provision edilir.
- Token kaybı veya expiration: pending enrollment revoke/expire edilir ve
  yeni operation ID ile yenisi oluşturulur. Önceki raw token geri getirilemez.
- Store bozulması, güvenilmeyen backup veya external generation anchor
  uyuşmazlığında consumer'ları kapalı tut; staging'de son güvenilir state ve
  audit/outbox zincirini karşılaştır. Eski snapshot'ın revoked key'i geri
  getirmediğini kanıtlayamıyorsan etkilenen tüm credential'ları compromise
  kabul edip yeni key'lerle yeniden provision et.
- Restore edilmiş store'u generation sayısı tek başına güvenli yapmaz. Anchor
  ile snapshot tutarsızsa otomatik eski state'e veya anonim auth'a düşme;
  offline yeni epoch/re-provisioning kararı ver.

## Uygulama öncesi karar kapıları

1. Bootstrap aracı, secret teslim kanalı ve hangi işlemlerin offline kalacağı
   onaylanmalı.
2. Hedef network/UID sınırı; farklı UID erişimi; browser enrollment olup
   olmayacağı; auth açık GET kapsamı ayrıca karara bağlanmalı.
3. Scope delegasyonu, enrollment expiry, rotation overlap, acil revoke,
   request/rate/storage kotaları ve audit retention için kesin politika
   değerleri seçilmeli.
4. Şema sürümü ve atomic outbox/idempotency kaydı; dış generation anchor,
   backup/restore ve `CommitUnknown` işletim runbook'u tasarlanmalı.
5. Bu kapılar ve ilgili auth/handler incelemeleri kabul edilmeden endpoint
   açılmamalı, canlı store değiştirilmemeli veya `YUVA_AUTH_ENABLED=1`
   yapılandırılmamalı.

Bu belge tasarımdır. Lifecycle kodu/endpoint'i, key provisioning aracı, rate
limiter, audit outbox veya canlı auth ayarı mevcutmuş gibi
değerlendirilmemelidir. `yuva auth init` yalnız boş store hazırlayıcısıdır.
