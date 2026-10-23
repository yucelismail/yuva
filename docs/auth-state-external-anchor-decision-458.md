# #458 — Auth-state dış generation/high-water anchor kararı

## Karar özeti

`AuthStateStore` içindeki generation ve duvar saati high-water değerleri tek
snapshot transaction'ında tutarlı ilerliyor; fakat aynı snapshot'ın eski bir
yedeğini geri yüklemek bu iki değeri de geriye alır. Bu nedenle dış anchor
olmayan mod için eski yedeğe otomatik dönmek güvenli kabul edilemez.

Önerilen geçiş kararı:

1. **Bugün:** Auth store restore'u yalnız operatör kontrollü offline
   re-provision/credential rotation prosedürüyle yap; restore edilen snapshot'ı
   otomatik kullanma. Bu mevcut feature-off işletim modeline uygundur.
2. **Üretimde otomatik rollback algılama gerekiyorsa:** ayrı trust domain'de
   compare-and-swap destekli anchor ve `prepared → snapshot durable → committed`
   recovery protokolü seç. Anchor her auth-state değişikliğini, özellikle key
   revoke ve nonce tüketimini, generation + snapshot digest'iyle bağlamalı.
3. Sadece sabit `generation_floor` veya aynı backup kapsamındaki sidecar'ı
   sürekli anti-rollback garantisi diye sunma. Bunlar en son state'i güvenilir
   biçimde sabitlemez.

Bu bir ürün/işletim kararı notudur; kod veya dış servis uygulanmadı.

## Mevcut durum ve güvenlik sonucu

- `panel/auth_store_v2.py:476-503` dış `generation_floor` değerini opsiyonel
  alır; store kendisi anchor oluşturmaz veya ilerletmez. `_with_lock()` yalnız
  sağlanan tabandan küçük snapshot generation'ını reddeder (`514-516`).
- `transact()` clock rollback kontrolü, `last_wall_time` artışı, generation
  artışı ve state commit'ini aynı snapshot değişikliğinde yapar (`540-580`).
  Bu normal çalışma içindeki stale clock'u yakalar.
- `_atomic_replace()` temp file fsync, `os.replace` ve root directory fsync
  kullanır; replace denemesinden/sonrasından belirsizlikte `CommitUnknown`
  üretir (`399-469`). Çağıran, sonucu kesin başarısız varsayıp aynı mutasyonu
  farklı bir anahtarla tekrarlamamalı.
- Eski ve kendi içinde geçerli snapshot restore edilirse onun generation,
  `last_wall_time`, key revoke durumu ve nonce kümesi birlikte geri döner.
  Snapshot içi generation/high-water bu rollback'i dışarıdan göremez.
  #430 incelemesi de varsayılan `generation_floor=None` için bunu orta bulgu
  olarak kaydetti.
- `generation_floor` yalnız alt sınırdır: floor 20 iken generation 27'den
  23'e restore edilmesi hâlâ kabul edilir. Floor her commit'te güncel,
  güvenilir dış kaynaktan okunmazsa son commit'leri korumaz. Generation
  floor'a ek olarak exact snapshot hash/instance bağlanmıyorsa aynı generation
  numaralı farklı/yanlış state'i ayırt edemez.
- Anchor aynı UID'nin yazabildiği sıradan bir dosyaysa aynı UID tehdidine
  karşı bağımsız değildir. Anchor ve store birlikte yedeklenip birlikte geri
  alınırsa rollback tespiti yine kaybolur.

## Seçeneklerin karşılaştırması

| Seçenek | Rollback algılama | Crash / `CommitUnknown` | Backup restore | İşletim ve maliyet | Karar |
|---|---|---|---|---|---|
| Snapshot içi generation/high-water (mevcut) | Snapshot'ın kendi iç tutarlılığını korur; eski geçerli snapshot'ı yakalayamaz. | Mevcut dosya atomik replace/fsync sınırı `CommitUnknown` verir; dış kayıtla uzlaştırma yok. | Eski snapshot yeniden geçerli olur; iptal/replay durumu geri alınabilir. | En düşük karmaşıklık; yalnız crash/bütünlük hataları, rollback saldırısına değil. | Mevcut default olarak kalsın, anti-rollback iddiası verilmesin. |
| Başlangıçta okunan statik `generation_floor` | Yalnız floor altındaki restore'u yakalar. Güncellenmeyen floor'dan büyük eski snapshot'lar geçer. | Güncel floor değerinin commit başına yazıldığı bir protokol yok. | Floor'a kadar eski yedek kabul edilir. | Basit deploy config; per-commit yönetilmezse yanıltıcı güvence. | Tek başına yeterli değil. |
| Aynı host'ta ayrı sidecar/manifest | Sidecar store snapshot'ından bağımsız güncellenir ve yedek dışında kalırsa kazaî restore'u yakalayabilir. Aynı UID sidecar'ı da yazabiliyorsa UID saldırısını yakalamaz. | İki dosyanın atomik commit'i yok; sidecar-first ile availability kesintisi, store-first ile anchor geride kalması doğar. Pending intent/recovery gerekir. | Store ile sidecar birlikte restore edilirse algılama yok. Ayrı restore politikası ve yedek dışı koruma şart. | Kolay kurulum; sağlam owner/ACL/backup işletimi ve iki-faz recovery gerekir. | Yalnız tehdit modeli same-UID/root'u dışlıyor ve sidecar backup'tan ayrı korunuyorsa değerlendirilir. |
| TPM/secure element monotonic counter | Counter eski snapshot generation'ından ilerideyse rollback'i algılar; snapshot digest ile bağlanırsa aynı generation farklı içeriği de ayırt eder. | Counter ve dosya transaction'ı atomik değildir. Counter önce artırılırsa crash sonrası state geride kalır ve auth fail-closed olur; kurtarma gerekir. Counter sonra artırılırsa aradaki crash rollback açığı bırakır. | Counter geri alınamıyorsa eski snapshot reddedilir; yalnız counter'dan daha yeni matching backup restore edilebilir. | Donanım/firmware, NV yazma ömrü/hız limiti, provisioning ve cihaz değişimi planı gerekir. | Tek host/offline deployment ve donanım desteği varsa güçlü seçenek; counter-first + recovery kabul edilmeli. |
| Uzak, güçlü tutarlı CAS/anchor servisi | Her commit'te `instance_id`, generation, `last_wall_time`, snapshot digest ve transaction ID eşleşirse eski/different snapshot reddedilir. | 2-resource transaction gerekir; `prepared` kayıt, local durable snapshot ve `committed` anchor adımlarına recovery tanımlanmalı. Servis yoksa auth durur. | Eski snapshot anchor'ın son committed hash'iyle eşleşmez; restore matching snapshot veya yeni epoch/re-provision gerektirir. | Servis availability, mTLS/service identity, CAS, anchor audit ve disaster recovery gerekir. | Sürekli online üretim servisi için önerilen seçenek. Anchor'da sır/credential değil yalnız bütünlük metadatası tutulmalı. |
| Append-only/audit log | Güvenilir, eksiksiz ve dışarıdan korunmuş son kayıt aranırsa rollback görünür. Yalnız hash chain dosyası yine eski prefix'e döndürülebilir. | Log append sonucu da belirsiz olabilir; operation ID ile idempotent append ve readback gerekir. Anchor log head dışarıda pin edilmelidir. | Dış log head mevcut snapshot digest'iyle karşılaştırılır; snapshot restore reddedilir. | Log bütünlüğü, retention, checkpoint/başlık yönetimi ve per-commit erişim maliyeti vardır. | Remote CAS yerine kullanılabilir ancak commit/recovery semantiği açıkça tanımlanmalı. |
| Tam offline restore + anahtarları yeniden provision et | Restore anında otomatik algılama sağlamaz; prosedür eski kimlikleri kullanım dışı bırakır. | `CommitUnknown` için online anchor yok; snapshot okunup operatör kararıyla restore/yeniden kurulum yapılır. | Restore edilen state güvenilmez kabul edilir; yeni epoch/audience veya tüm anahtarların rotate/revoke edilmesi gerekir. | Operatör müdahalesi ve outage; acil revoke/restore runbook'u gerekir. | Bugün için önerilen kontrollü prosedür; otomatik rollback garantisi değildir. |

## Dış anchor seçilirse önerilen transaction sözleşmesi

Anchor tek bir “minimum generation” integer'ı değil, şunları korumalı:

- `instance_id` / auth-state epoch;
- son committed `generation`;
- son state'in canonical digest'i veya güçlü bütünlük commitment'ı;
- `last_wall_time` high-water;
- `transaction_id` ve `pending/committed` durumu.

Olası crash-consistent protokol:

1. Store stable lock altında güncel committed anchor tuple ile snapshot'ı
   karşılaştırır. Fark varsa mutasyon/auth fail-closed olur.
2. Anchor CAS ile `prepared(txid, old_generation, new_generation,
   snapshot_digest)` yazar. Anchor erişilemiyorsa store değiştirilmez.
3. Store snapshot'ı `new_generation` ve yeni `last_wall_time` ile atomik
   yazar. Temp file fsync, replace ve directory fsync tamamlanmalı.
4. Anchor aynı `txid` için committed tuple'ı CAS ile finalize eder. Ancak bu
   onaydan sonra transaction kesin tamamlandı sayılır.
5. `prepared` varken restart olursa auth/mutations askıya alınır. Recovery
   anchor kaydı ve store digest'ini okur: dayanıklı snapshot eşleşiyorsa finalize
   eder; eski snapshot görünüyorsa yalnız anchor protokolünün izin verdiği
   explicit abort/retry yolunu kullanır. Farklı/bozuk snapshot veya anchor
   erişim sorunu varsa otomatik eski state'e/anonim moda düşmez.

İki sistem arasında gerçek atomik commit yoktur; bu nedenle `prepared` kaydı
ve recovery protokolü zorunludur. Anchor önce yalnız `floor = g+1` yazıp sonra
store'u değiştirmek güvenlidir ama crash'te availability kaybı doğurur. Store
önce yazıp anchor'ı sonradan güncellemek, anchor ilerleyene kadar eski snapshot
restore'una açık pencere bırakır; dış anchor'ın tam koruma sağlaması için bu
pencere kabul edilemez veya pending intent tarafından kapatılmalıdır.

`CommitUnknown` durumunda signature verifier başarılı principal döndürmemeli.
Retry aynı transaction ID ile önce `prepared/committed` anchor ve snapshot
digest'ini uzlaştırmalı; farklı key/nonce ile ikinci mutasyon başlatılmamalı.
Anchor servisi veya donanım counter'ı kullanılamıyorsa auth protected request
503/closed kalmalı; legacy anonymous mutation fallback'i olmamalı.

## Restore ve anchor kaybı kararları

| Olay | Güvenli varsayılan | Operatör kararı gereken nokta |
|---|---|---|
| Store generation/hash anchor'dan eski veya eşit generation hash'i farklı | Auth kapalı; restore edilmiş state'i kabul etme. | Anchor'ın en son commit'ine ait matching backup mı, yoksa yeni epoch ve tam key re-provision mı? |
| Anchor `prepared`, store yeni digest'e eşit | Normal request'leri açmadan directory durability/reconciliation yap, sonra finalize et. | Retry/commit recovery işlemini hangi yetkili servis/CLI yapar ve nasıl audit edilir? |
| Anchor `prepared`, store eski digest'te | Auth kapalı; kayıp/yarım transaction'ı uzlaştır. | Anchor intent güvenle abort edilip aynı transaction yeniden denenebilir mi? CAS bunu kayıt altına almalı. |
| Anchor kayıp/bozuk/erişilemez | Dış anchor kullanan modda auth fail-closed. | Anchor restore edilip imza/epoch doğrulaması mı yapılır, yoksa yeni epoch ve bütün credential'lar mı provision edilir? Eski store'u tek başına kabul etme. |
| Yedekten geri dönüş | Yalnız son anchor tuple ile digest'i eşleşen snapshot'ı restore et; diğer yedekler doğrudan açılmaz. | Eski credential revocation ve nonce geçmişi kaybolduysa key rotate/re-enrollment kapsamı. |
| TPM cihazı değişti veya counter sıfırlandı | Auth kapalı. | Cihaz değişimi, secure enrollment ve tüm key'lerin yeniden provision edilmesi. |

## Ürün/operasyon kararları

Üretim seçimi yapılmadan önce şu sorular yanıtlanmalı:

1. Tehdit yalnız kazara eski backup restore'u mu, yoksa aynı UID/host
   yöneticisinin store'u geri alması da mı? Aynı UID attacker hedefleniyorsa
   aynı host sidecar yeterli değildir.
2. Auth servisi anchor ağına/TPM'e erişemediğinde protected mutation için ne
   kadar kesinti kabul edilir? Güvenli varsayılan fail-closed'tur.
3. Her `transact` için anchor güncellemesi gerekir mi? Daha seyrek checkpoint
   nonce tüketimi ve revoke rollback'ini checkpoint aralığı boyunca korumaz.
4. Restore'da RPO sıfır mı, yoksa son yedekten sonra tüketilen nonce ve
   revoke'ların kaybı kabul edilir mi? Key revoke için bu kayıp kritik olabilir.
5. Anchor yedeği, key rotation, instance/epoch değişimi, servis değişikliği ve
   anchor kaybında recovery sorumlusu kimdir; hangi kanıt/audit tutulur?
6. Canonical snapshot digest formatı ve schema version değişiminde anchor
   migration/dual-version protokolü nasıl işleyecek?

## Kapsam ve kaynaklar

Karar notudur; kod, auth store, yedek veya runtime durumu değiştirilmedi.
Test çalıştırılmadı.

- `panel/auth_store_v2.py:399-469` — replace, fsync ve `CommitUnknown`.
- `panel/auth_store_v2.py:476-583` — opsiyonel generation floor, locked
  snapshot, persisted clock high-water ve generation transaction'ı.
- `docs/auth-core-v2-review-430.md` — mevcut orta seviye rollback bulgusu ve
  feature-off/restore sınırı.
