# Auth key rotation ve revoke: çevrimdışı operatör akışı (#501)

## Durum ve sınır

Bu belge, #462 lifecycle tasarımı ile #477 provisioning taslağına dayalı bir operatör prosedürü önerisidir. Key üretmez, store'u değiştirmez ve çalışan bir rotation/revoke aracı tarif etmez. `AuthStateStore` bugün yalnız `read()` ve genel `transact()` sunar; rotation, revoke, backup/restore ve lifecycle API'si yoktur. `yuva auth init` yalnız boş ilk snapshot ve stable lock kurar; credential üretmez/enroll etmez, bu prosedürü uygulanabilir kılmaz. Bu nedenle aşağıdaki akış, key custody/lifecycle için ayrı onaylı offline host aracı ve işletim kabulü hazırlanana kadar canlı sistemde uygulanabilir talimat değildir.

## Operatörün önceden karara bağlayacağı bilgiler

Değişiklik kaydında secret veya token olmadan şu bilgileri belirleyin:

- Store `instance_id`, `audience`, hedef `principal_id` ve eski `key_id`.
- Yeni key için ayrı `key_id`, gereken exact method/path scope'ları, `not_before` ve `expires_at`. Yeni scope'lar eskisini aşmamalı.
- Normal geçişte eski ve yeni credential'ın birlikte geçerli olacağı kısa overlap süresi. Bu süre için herkese uyan sabit bir değer yoktur; servis sahibinin client güncelleme/geri bildirim süresine göre önceden seçmesi gerekir. Süresiz overlap kabul edilmez.
- Yeni secret'ın hedef istemciye teslim edileceği korumalı kanal, alıcıyı doğrulama yöntemi ve istemcide saklama yeri.
- Değişiklik öncesi tutarlı backup ve bağımsız kayıt/anchor kaynağı. Store'un `generation` değeri tek başına eski backup restore'unu saptamaz.
- Uygun çevrimdışı doğrulama ve geri dönüş kararı. Mevcut sistemde read-only auth probe yoktur. Mutasyon endpoint'i doğrulama amacıyla çağrılmaz.

Kararlardan biri eksikse rutin rotation başlatılmaz. Acil compromise halinde overlap beklenmez; öncelik şüpheli credential'ı kapatmak ve etkilenen client'ı yeniden doğrulamaktır.

## Normal rotation sırası

1. **Kapsamı ve hedefi doğrulayın.** Servis sahibi, client sahibi ve değişiklik onayını doğrulayın. Mevcut snapshot'ı güvenli, tutarlı backup yöntemiyle alın; backup'ı owner-only, erişimi kısıtlı ve şifreli hedefte saklayın. Backup içinde aktif ve revoked secret'lar bulunabileceğini varsayın. Onaylı backup yöntemi yoksa ilerlemeyin.
2. **Yeni credential'ı hazır edin.** Güvenilir offline provisioning süreci yeni CSPRNG secret'ı ve benzersiz ID'yi hedef client için hazırlar. Store kaydı aynı `audience` ve principal'a, yalnız gerekli exact scope'lara, açık validity aralığına ve `revoked=false` değerine sahip olmalıdır. Secret shell argümanına, terminale, sohbet/issue'ya, audit'e veya genel backup'a yazılmaz. Aynı UID'deki süreçlerin dosya izinleriyle birbirinden ayrılamayacağını hesaba katın.
3. **Önce client'a teslim edin.** Alıcının kimliğini önceden kararlaştırılmış kanalla doğrulayın; secret'ı ayrı korumalı kanaldan verin. Client yeni credential'ı korumalı credential store'a yüklediğini secret'ı geri göndermeden teyit eder. Teyit kaydında yalnız key ID, zaman ve sonuç olur.
4. **Yeni key'i ekleyin, eskisini etkin tutun.** Onaylı lifecycle aracı aynı store transaction'ında yeni key'i eklemeli ve gerekli ilişki/denetim kaydını yazmalıdır. Eski key bu aşamada revoke edilmez. Issuer key etkileniyorsa, ona bağlı pending enrollment'lar da aynı transaction'da revoke edilmelidir; revoked issuer altında pending enrollment bırakılamaz.
5. **Yeni credential'ı zararsız yoldan doğrulayın.** Sadece önceden tasarlanmış, read-only auth probe ya da güvenli olmayan hiçbir yan etkisi bulunmayan açık doğrulama yolu kullanılabilir. Şu an böyle bir probe veya lifecycle endpoint'i mevcut değildir. Böyle bir yol yoksa key'in çalıştığı kanıtlanmış sayılmaz ve eski key revoke edilmez.
6. **Overlap boyunca teyit alın.** Client sahibi, gerçek kullanımın yeni key'e geçtiğini ve eski key'e ihtiyaç kalmadığını doğrular. Secret veya HMAC imzasını operatör kaydına eklemeyin. Süre bitince geçişi tekrar değerlendirin; teyit yoksa otomatik revoke yapmayın.
7. **Eski key'i revoke edin.** Önceden onaylanmış araç eski key kaydını `revoked=true` yapar; kaydı silmez. Key issuer ise bütün pending enrollment'ları aynı transaction'da revoked yapar. Yeni key'in durumu ve eski key'in revoke tombstone'u aşağıdaki readback adımlarıyla teyit edilmeden iş tamamlandı denmez.

## Revoke sonrası readback ve belirsiz commit

`transact()` atomik snapshot yer değiştirmesinden sonra dizin `fsync` hatası alırsa `CommitUnknown` döndürebilir. Bu sonuç commit'in olmadığını kanıtlamaz. Mevcut store'da create/revoke için genel operation receipt yoktur; bu yüzden yalnızca hata koduna veya generation artışına bakarak sonucu belirlemek mümkün değildir.

1. `CommitUnknown` veya işlemci kesintisi olursa aynı mutation'ı yeniden çalıştırmayın, yeni operation ID ile tekrarlamayın ve backup'ı aktif store üzerine otomatik kopyalamayın. Auth consumer'larını, ortamın onaylı işletim yöntemiyle kapalı/feature-off tutun; mevcut feature toggle'ı kullanmanın güvenli olduğu ayrıca doğrulanmalıdır.
2. Aynı sabit lock inode'u üzerinden yetkili offline `read()` ile snapshot'ı doğrulayın. `instance_id`, `audience`, başlangıç ve son `generation`, hedef eski key'in `revoked` değeri, yeni key'in gerekli alanları ve issuer altındaki bütün pending enrollment durumlarını kontrol edin. Secret, token, imza veya secret fingerprint'ini raporlamayın.
3. Readback'i değişiklik öncesi backup ve store dışı güvenilir değişiklik/audit kaydıyla karşılaştırın. `read()` şema ve dosya güvenliğini doğrular; commit receipt, bağımsız audit veya rollback anchor üretmez. Yalnızca snapshot içi generation yeterli değildir.
4. Hedef durum eksik, çelişkili veya bağımsız kayıtla uyuşmuyorsa consumer'ı kapalı tutun ve offline incelemeye yükseltin. Çelişki giderilene kadar hiçbir key'i un-revoke etmeyin, aynı değişikliği kör retry etmeyin ve store'u eski backup'a döndürmeyin.
5. Eski key revoked, yeni key aktif, enrollment bağları tutarlı ve bağımsız kayıt uyumluysa sonuç operatör tarafından kabul edilebilir. Bu kontrol mevcut sistemde otomatik/atomik lifecycle receipt sağlamaz; runbook'un kalıcı kabul ölçütü, bağımsız kontrol sorumlusu ve audit sink'i ayrıca karara bağlanmalıdır.

## Kayıp veya ele geçirilmiş istemci

- **Secret kayboldu, compromise bulgusu yok:** İstemciyi ve sahibini yeniden doğrulayın; kayıp secret geri getirilemez. Eski key'e erişimi kontrollü biçimde revoke edin, gerekiyorsa pending enrollment'larını iptal edin ve yeni key'i yeni secret ile provision edip doğrulayın. Yeniden yetki için eski kaydı un-revoke etmeyin.
- **Secret çalınmış/istemci kontrol dışı:** Overlap beklemeden ilgili key'i ve issuer ise pending enrollment'ları revoke edin. İşlemin `CommitUnknown` olması halinde yukarıdaki kapalı durumda kalma ve readback kuralını izleyin. Eski credential'ın geçersiz kaldığı doğrulanana kadar ilgili tüketiciyi yeniden açmayın.
- **Aynı key birden çok client'ta kullanılmış:** Key'i tek client'a özgü varsaymayın. Bütün bağlı client'ları envantere alın; her birini ayrı principal/key ile yeniden provision edin ve kapsamı daraltın. Bir client'ın başarılı geçişi diğerlerinin taşındığını kanıtlamaz.
- **Backup/restore veya anchor uyuşmazlığı:** Tüm consumer'ları kapalı tutun. Restore edilmiş snapshot eski revoked key'i geri getirebilir. Bağımsız kayıttan revoke durumu kanıtlanamıyorsa etkilenen credential'ları tehlikeye girmiş kabul edin; güvenilir yeni state ve yeni credential'larla çevrimdışı kurtarma kararı alın.

## İşlem kaydı

Secret içermeyen kayıt şu alanları taşımalıdır: değişiklik/operation kimliği, actor ve onay referansı, `instance_id`, `audience`, principal ve key ID'leri, scope fingerprint'i, planlanan validity/overlap zamanları, client teslim ve doğrulama teyitlerinin zaman/sonuçları, önce/sonra generation, readback sonucu, `CommitUnknown` uzlaştırma kararı ve bağımsız kontrol eden kişi. Raw request body, secret, enrollment token, HMAC imzası ve secret digest'i loglanmaz. Store ile ayrı JSONL kaydı atomik değildir; bu nedenle mevcut admin audit append'i lifecycle işleminin atomik kanıtı kabul edilmez.

## Uygulamadan önce zorunlu kapılar

- Güvenilir host-side rotation/revoke aracı; sabit lock ve atomik store işlemlerini kullandığına dair inceleme.
- Create/revoke için aynı transaction'da yazılan operation receipt/outbox ve belirsiz commit için desteklenen uzlaştırma davranışı.
- Tutarlı backup/restore, şifreleme/saklama ve bağımsız anti-rollback anchor prosedürü.
- Secret teslimi, client doğrulama yolu, overlap/expiry süreleri, emergency revoke ve shared-key politikasının servis sahibi tarafından seçilmesi.
- `YUVA_AUTH_ENABLED=1` öncesinde GET snapshot/HTML erişim kararı ve genel işletim kabulü. Rotation tasarımı tek başına auth'ı açma onayı değildir.

Kaynaklar: `docs/auth-key-lifecycle-api-design-462.md`, `docs/auth-state-v2-operations.md`, `panel/auth_store_v2.py`, `panel/auth_provision_draft.py`. Bu teslimde kod, key, store, test veya runtime değişikliği yapılmamıştır.
