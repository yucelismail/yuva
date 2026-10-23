# Yuva #585 — Ekran, sohbet, log veya yedekte credential sızıntısı olayı

## Amaç ve güvenlik sınırı

Bu runbook, bir ekran kaydı, sohbet iletisi, log, export veya backup içinde gerçek bir credential bulunduğu **bildirildiğinde** izlenecek fail-closed olay akışıdır. İçeriği taramak veya doğrulamak için raw değeri istemeyin, ticket'a kopyalamayın ve raporda göstermeyin. Bilinen biçimlerle sınırlı redaction tam DLP değildir: #564'ün yazma sınırındaki filtresi bilinen bearer/authorization, credential ataması, credential URL ve bazı yaygın token biçimlerini maskeler; özel, parçalı veya kodlanmış biçimleri yakalayacağı garanti edilmez. Redactor'ın başarılı olması veya UI'da maskeli görünmesi eski kalıcı kopyaların temizlendiğini kanıtlamaz.

Bu belge prosedür tasarımıdır. Gerçek Yuva dosyaları, credential, log veya backup taranmadı/açılmadı; hiçbir credential iptal edilmedi/üretilmedi, servis durdurulmadı ve canlı tüketici doğrulanmadı. `auth-key-rotation-revoke-offline-501.md` mevcut auth store'da lifecycle/rotation/revoke aracı ve read-only auth probe olmadığını belirtiyor; dolayısıyla bu akış, bu yetenekler onaylı biçimde sağlanana kadar canlı sistemde kendi başına çalıştırılabilir komut değildir.

## Roller ve öncelik

- **Olay koordinatörü:** olay kimliğini ve zaman çizelgesini yönetir; karar/onay sahiplerini belirler; secret içermeyen kayıt tutar.
- **Credential/servis sahibi:** issuer ve etkilenen tüketicileri bulur, yetkili revoke/rotate işlemini yürütür ve güvenli doğrulamayı sağlar.
- **Veri/backup sahibi:** ilgili artifact/kopyaları içeriği açmadan erişime kapatır, hold ve retention/purge kapsamını yönetir.
- **Bağımsız kontrol eden:** revoke/readback ve tüketici doğrulama kanıtını onaylar.

Olay önceliği varsayılan olarak **yüksek** kabul edilir: credential'ın hâlâ geçerli olabileceği, birden fazla tüketicide kullanılmış olabileceği ve backup'larda bulunabileceği varsayılır. Bu varsayım raw değeri elde etmeyi gerektirmez.

## Akış

### 1. Bildirimi güvenli al

1. Bildirene raw değeri tekrar göndermemesini; ekran görüntüsü, terminal çıktısı veya credential içeren dosya eklememesini söyleyin. Değer zaten sohbet/ticket'a yazıldıysa onu alıntılamayın veya başka yere kopyalamayın.
2. Yalnız şu metadata'yı toplayın: olay ID'si, bildirim zamanı ve saat dilimi, artifact sınıfı (`screen`, `chat`, `log`, `backup`, `export`), içerik sahibinin/servis sahibinin iletişim referansı, ilgili artifact'ın güvenli içeriğe erişmeyen referansı, credential sınıfı (biliniyorsa), bilinen `issuer`/servis adı, `principal_id`/`key_id` (yalnız değer-secret değilse), yaklaşık maruziyet başlangıç/bitiş aralığı ve olası alıcı/erişim kitlesi.
3. Bildirim, “sır var mı?” diye içeriği açıp aramayla teyit edilmez. Bilgi yetersizse **credential maruz kalmış olabilir** statüsünde ilerleyin. Kaynağı veya scope'u bilmiyorsanız issuer/servis sahibiyle yetkili envanterden belirleyin; credential'ı denemeyin.

### 2. Karantinaya al ve yayılmayı durdur

1. Artifact'a erişimi sınırlayın: paylaşımı/indekslemeyi/indirmeyi durdurun, erişim listesini olay koordinatörü ve gerekli sahiplerle sınırlayın, normal silme/retention işini hold altına alın. Chat'te iletinin görünürlüğünü platformun yetkili moderasyon akışıyla kısıtlayın; e-posta/issue/log kopyalarının alıcılarını belirleyin. Bildirimdeki raw değeri yeni incident kaydına taşımayın.
2. Kaynağın türüne göre korunan kapsam:
   - **Ekran/sohbet:** ilgili kayıt veya iletiyi edit/silme mümkün olsa bile önce içerik kopyası üretmeden referansını ve erişim listesini kaydedin. İçeriği korumak zorunluysa erişimi kısıtlı karantina/hold alanında tutun; normal UI ve arama indeksinden çıkarma işlemini veri sahibinin onaylı süreciyle yürütün.
   - **Log:** ilgili log akışını daha fazla yayılmadan durdurun veya yeni, maskeli log akışına geçin. Dosyayı yerinde satır silerek yeniden yazmayın; append-only/forensic bütünlüğü ve eşzamanlı writer'lar etkilenebilir. Orijinal ve kopyalar için restricted hold/purge kararı alın.
   - **Backup/export:** içeriği açmadan dosya/artifact kimliği, sahip, hedef, oluşturulma zamanı ve retention/immutable durumu gibi dış metadata ile karantinaya alın. Restore, kopyalama ve dışa aktarma işlemlerini askıya alın veya credential revoke doğrulanana kadar bu kopyaları güvenilmeyen olarak etiketleyin. Backup'ı olay incelemesi için açmayın.
3. Kök kaynağa yeni yazımı durdurma gerekiyorsa servis/veri sahibi etkiyi değerlendirip onaylı çalışma prosedürüyle durdurur. Yalnız bir secret satırını `sed`/manuel edit ile JSONL'den çıkarmaya veya dosyayı truncate etmeye kalkışmayın. Birincil kaydı silmek arşiv, replica, log, export, restore-check ve backup kopyalarını silmez.
4. Karantina kanıtı yalnız içeriksiz referans ve metadata olmalıdır. Secret'ın plain hash'ini, HMAC'ini, prefix/suffix'ini, uzunluğunu veya eşleşen satırını bile genel incident kaydına koymayın; bunlar tahmin/bağlama saldırılarına veya yeni sızıntıya yol açabilir. İçerik zorunlu delilse ayrı erişim, şifreleme, audit, süre ve sorumlu sahibi onaylanmış kanalda belirleyin.

### 3. Credential'ı iptal et ve yenile

1. Credential ailesini ve gerçek issuer'ı yetkili envanterle belirleyin: Yuva HMAC/auth key'i, provider API key'i, session/cookie token'ı, private key veya başka token. Bildirilen değer görünmeden yalnız kimlik/scope/consumer ilişkisi üzerinden hedefi seçin. Bir key birden çok client'ta kullanılıyorsa hepsi etkilenmiş sayılır.
2. **Aktif sızıntı şüphesinde overlap beklemeyin.** Servis sahibi onaylı issuer/lifecycle aracıyla ilgili key'i veya session'ı revoke/disable eder; issuer key ise ona bağlı pending enrollment'ları da iptal eder. Revoke kanıtlanamıyorsa ilgili consumer'ı kapalı/izole tutun; güvenlik sınırını doğrulamadan auth flag veya servisi açıp deneme yapmayın.
3. Yeni credential yalnız yetkili offline provisioning/issuer süreciyle, yeni benzersiz ID ve gerekli en dar scope/validity ile oluşturulur. Secret, sohbet/ticket, shell argümanı, environment dump, terminal scrollback, log, audit veya genel backup'a konmaz. Önceden doğrulanmış alıcıya korumalı kanaldan teslim edilir; client sahibi saklama alanına aldığını secret'ı geri göndermeden teyit eder.
4. Yeni credential'ı yalnız önceden tanımlanmış, read-only ve zararsız doğrulama yolu ile teyit edin. Mevcut auth tasarımında bu probe yoksa key'in kullanılabilirliği kanıtlanmış sayılmaz; mutation endpoint'ini test için çağırmayın. Güvenli doğrulama yolu/işletim aracı yoksa **No-Go**: consumer kapalı kalır ve issuer/platform sahibine yükseltilir.
5. Tüketici envanterinde her client/worker/backup restore job için yeni credential'a geçiş teyidi alın. Secret değerini istemeden yalnız consumer ID, key ID, zaman ve sonuç kaydedin. Eski credential'ın hiçbir consumer'da kullanılmadığını yetkili telemetri/owner teyidiyle doğrulayın; credential değeri üzerinden arama yapmayın.
6. Eski credential'ı revoke edilmiş durumda tutun; un-revoke etmeyin. Auth store değişikliğinde `CommitUnknown`, crash veya kesinti olursa aynı mutation'ı körlemesine retry etmeyin ve backup'ı aktif store üzerine yazmayın. Consumer'ları kapalı tutun; sabit lock üzerinden onaylı offline readback'i değişiklik kaydı ve bağımsız anchor ile karşılaştırın. `generation` tek başına bağımsız kanıt değildir. Sonuç çelişkiliyse eskalasyon yapın.

### 4. Eski kopyaları gider ve restore'u güvenli kıl

1. Artifact envanterini içerik açmadan oluşturun: doğrudan kaynak, UI/cache/search index, chat export, log shipper/collector, replica, kullanıcı indirmeleri, CI/artifact store, backup zinciri, restore-check/scratch kopyaları ve dış export. Her satırda owner, erişim durumu, hold durumu, retention/immutability ve karar sahibi bulunsun.
2. Önce revoke'un etkili olduğu ve tüketicilerin geçişi doğrulansın. Sonra her kopya için platformun yetkili redaksiyon/silme/purge prosedürünü uygulayın; başarısız/immutability nedeniyle bekleyenleri açık exception ve sona erme tarihiyle takip edin. Backup purge yetkisi/retention kararı yoksa dosyayı açmak yerine erişimi kısıtlı hold'da tutun ve backup sahibinden karar isteyin. Otomatik retention yaşı veya bütçe adaylarını onaylanmış policy gibi kullanmayın.
3. Restore koruması: olay sonrası restore öncesi backup, olay sonrası revoke tombstone/bağımsız revoke kaydıyla karşılaştırılır. Eski aktif key'in yeniden canlanmadığı doğrulanmadan restored consumer başlatılmaz. Backup'ın auth store'u geriye sardığı/bağımsız anchor uyuşmadığı durumda tüm ilgili consumer'lar kapalı kalır; çevrimdışı state uzlaştırması ve yeni credential gerekir.
4. İçerik taşıyan delil yasal/operasyonel hold nedeniyle silinemiyorsa bunu “temizlendi” olarak işaretlemeyin. Kalan kopya, erişim listesi, sahibi, saklama gerekçesi, son tarih ve restore'da uygulanacak revoke kontrolü kaydedilir.

### 5. Olayı kapat

Olay yalnız şu koşullar sağlandığında kapatılabilir: eski credential revoke/readback ile etkisiz; yeni credential güvenli biçimde provision edilmiş ve tüketiciler secret'ı açığa çıkarmadan doğrulanmış; ilgili kopyalar karantinada/silinmiş/retention gerekçesiyle istisna olarak kayıtlı; restore koruması tanımlı; bağımsız kontrol eden kanıtı onaylamış; düzeltici aksiyonlar (writer redaction, logging policy, exposure scope, consumer inventory) sorumlu ve tarihle atanmış.

## Operatör kontrol listesi

- [ ] Raw değer istenmedi, kopyalanmadı veya olay kaydına eklenmedi.
- [ ] Olay koordinatörü, credential sahibi, veri/backup sahibi ve bağımsız kontrol eden belirlendi.
- [ ] Artifact türü/referansı ve erişim kitlesi içerik açmadan kaydedildi; paylaşım/indeks/restore yayılımı kısıtlandı.
- [ ] Şüpheli issuer, principal/key ID (secret olmayan), scope ve olası tüm consumer'lar yetkili envanterden belirlendi; belirsizlikte kapsam geniş tutuldu.
- [ ] Acil revoke/disable sonucu ve bağımsız readback doğrulandı; belirsiz commit'te kör retry yapılmadı.
- [ ] Yeni credential ayrı ve korumalı kanaldan hedefe ulaştı; secret geri istenmeden client storage teyidi alındı.
- [ ] Güvenli read-only probe/consumer doğrulaması başarılı; mutation endpoint'i kullanılmadı. Doğrulama yolu yoksa No-Go ve consumer kapalı.
- [ ] Eski key'e bağlı bütün consumer ve pending enrollment'lar kapatıldı/yenilendi; eski key un-revoke edilmedi.
- [ ] Screen/chat/log/export/backup/replica/restore-check kopyaları metadata ile envanterlendi; backup içeriği açılmadı.
- [ ] Her kopya için purge/redaction/hold/retention kararı, owner ve kalan kopya son tarihi kaydedildi.
- [ ] Restore öncesi revoke tombstone/bağımsız anchor kontrolü atanmış ve restore guard sahibi belirlenmiş.
- [ ] Audit kaydı secret, raw body, satır içeriği, secret hash/fingerprint veya imza içermiyor; bağımsız reviewer kapatmayı onayladı.

## Sentetik olay fixture'ı (içerik taşımaz)

Bu fixture yalnız prosedür/kayıt alanlarını gösterir. Hiçbir token veya gerçekçi secret biçimi içermez; `fixture://` referansları çalışır dosya yolu değildir.

```json
{
  "incident_id": "INC-SYN-0001",
  "reported_at": "2026-10-23T12:00:00Z",
  "status": "suspected_exposure",
  "source": {
    "kind": "screen",
    "artifact_ref": "fixture://screen-0001",
    "owner_ref": "synthetic-owner-01",
    "access_restricted_at": null,
    "content_opened": false
  },
  "credential": {
    "class": "provider_api_credential",
    "issuer_ref": "synthetic-provider",
    "principal_id": "synthetic-principal-01",
    "key_id": "synthetic-key-01",
    "scope_ref": "synthetic-scope-set-01",
    "raw_value": "OMITTED",
    "digest_or_fingerprint": "OMITTED"
  },
  "response": {
    "quarantine_ref": "fixture://restricted-hold-0001",
    "revoked": false,
    "revocation_readback": "pending",
    "replacement_key_id": null,
    "consumer_checks": [],
    "backup_content_opened": false,
    "reviewer_ref": null
  }
}
```

Sentetik akış örneği: `suspected_exposure` → kaynak erişimini kısıtla ve consumer envanteri çıkar → issuer yetkili aracı yoksa `no_go_consumer_disabled` → revoke/readback → ayrı key ID ile provision → read-only probe ve tüm consumer teyidi → kopya envanteri/purge veya hold → bağımsız review → kapat. Başarısız/unknown adımda durum `contained_open` kalır; otomatik retry veya kapatma yoktur.

## Secret içermeyen olay kaydı alanları

Incident ID; açılma/kapanma zamanı ve timezone; severity/durum; actor ve onay/reviewer referansları; source kind ve erişim kontrollü artifact referansı; yaklaşık maruziyet aralığı ve audience; issuer, principal, eski/yeni key ID, exact scope referansı ve validity aralığı; revoke request/result/readback zamanı ve bağımsız kanıt referansı; `CommitUnknown` uzlaştırma kararı; consumer listesi ve her birinin geçiş/zararsız doğrulama sonucu; karantina/purge/retention/hold kararı ve backup metadata; restore kontrolü; düzeltici aksiyon sahibi/tarihi; kalan risk/istisna. Secret, token, authorization header, ham ekran/chat/log satırı, raw request/response, imza, secret digest/hash/fingerprint veya regex eşleşme parçası kaydedilmez.

## Dayanak ve uygulanabilirlik kapısı

- `docs/screen-secret-redaction-564.md`: write-time maskeleme sınırlı ve geçmiş kopyalara uygulanmıyor.
- `docs/screen-secret-redaction-rotation-559.md`: screen/chat/log/backup veri yolları ve onaysız retention/rotation adayları.
- `docs/auth-key-rotation-revoke-offline-501.md`: auth store'da lifecycle aracı/probe yok; CommitUnknown ve backup rollback sınırı.
- `docs/local-data-retention-export-deletion-policy-546.md`: yedek/export kopyaları ayrı envanter ve purge kararı gerektirir.

Bu belge operatör onaylı lifecycle aracı, issuer runbook'u, güvenli read-only consumer probe'u ve backup hold/purge prosedürü sağlandığında kurulum bazında uyarlanmalıdır. Bu kapılardan biri yoksa gerçek olayda consumer'ı kapalı tutup ilgili servis/veri sahibine eskale edin; bu belgeyi canlı erişim veya rotasyon yetkisi olarak yorumlamayın.
