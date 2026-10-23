# #546 — Yerel MVP veri saklama, dışa aktarma ve silme politikası

Tarih: 2026-10-23
Durum: Kaynaklı politika önerisi; operatörce onaylanmadı ve uygulanmadı. Canlı
veri okunmadı/silinmedi; kod, test veya runtime değişikliği yapılmadı.

## Karar özeti

Yuva'nın görev, mesaj, ekran ve tasarlanan receipt verileri aynı hassasiyet
sınıfında ele alınmalıdır. `/api/veri` görevleri, sohbet mesajlarını ve ekran
kayıtlarını aynı snapshot'ta birleştirir; mesaj ve ekran metinleri yazma öncesi
redakte edilmez. Loopback ve owner-only dosya izinleri tek güvenilen Unix UID
sınırını destekler; farklı UID'nin localhost GET erişimini veya aynı UID'deki
süreçleri birbirinden ayırmaz.

İlk yerel MVP için öneri:

1. Kullanıcıya yerel dosya içeriklerinin hassas olabileceğini açıkça söyleyin;
   secret, token ve gereksiz kişisel veriyi mesaj/ekranlara yazmayın. Yazma
   öncesi redactor ortak CLI/panel yazıcılarına bağlanıp fail-closed davranışı
   kabul edilmeden geçmiş içeriğin güvenle redakte edildiğini iddia etmeyin.
2. **Süreler operatörce seçilene kadar otomatik saklama/silme açmayın.** #449'daki
   90 gün mesaj, 7 gün ekran ve 30 gün/1 GiB yedek değerleri adaydır; #496 bunların
   onaylanmış ürün politikası olmadığını açıkça belirtir. MVP lansmanından önce
   aşağıdaki aday değerler kabul edilmeli veya değiştirilmelidir. Onay yoksa
   kullanıcıya verinin kendiliğinden silinmediği, saklama sonunun belirsiz
   olduğu söylenmelidir.
3. Mevcut arayüz/CLI'de dışa aktarma veya kullanıcıya yönelik silme özelliği
   yoktur. Ürün “dışa aktar” veya “silindi” taahhüdü vermemelidir. Tam veri kökü
   silme/backup temizleme ayrı, operatör kontrollü bir işlem olarak kalır.
4. Provider receipt entegrasyonu henüz tasarımdır. Provider gönderimi kapalı
   kalmalı; çözümsüz receipt/`unknown` veya dedupe tombstone silinmemelidir.

## Veri sınıfları ve bugün görülen yüzey

| Veri | Kalıcı kaynak ve mevcut okuma yüzeyi | Saklama/mahremiyet gözlemi |
|---|---|---|
| Görev ve görev geçmişi | `gorevler.json`; panel snapshot/tahta ve CLI görev komutları | Görev durumu ve `gecmis` birlikte güncellenir. Terminal `verified`/`dropped` kayıtları da dosyada kalır; kullanıcıya yönelik saklama veya silme API'si görülmedi. |
| Sohbet ve bildirim mesajları | `mesaj.jsonl`; CLI `yuva oku`, panel `/api/veri` | Ham metin saklanır. Panel/API tail'i 200 mesaja ve CLI okumaları sınırlı sayıya düşebilir; bu kalıcı dosyadan silme veya tam dışa aktarma değildir. |
| Ekran/terminal çıktısı | `ekran/<kimlik>.jsonl`; CLI `yuva ekran oku`, panel `/api/veri` | Ham `satir` metni saklanır. Panel/CLI seçimi ve tail/byte limitleri yalnız gösterilen çıktıyı sınırlar. |
| Provider/session receipt | #504/#527 kalıcı store tasarımı; izole prototipler | Canlı durable store/retention uygulaması değildir. `pending`, `sending`, `unknown/conflict` ve çözülmemiş approval'lar kaybolma veya duplicate riski nedeniyle süre doldu diye silinmemeli. |
| Backup ve restore-check kopyası | `docs/linux-gecis.md` tam KOK yedeğini KOK dışına alır; restore-check geçici extraction üretir | Tam backup görev, sohbet ve ekran verisini de kopyalar. Birincil kaydı silmek backup'ı silmez. Backup ve restore-check aynı erişim sınıfında korunmalıdır. |

`panel/server.py:1466-1500` birleşik snapshot içeriğini; `panel/server.py`
mesaj/ekran writer ve reader yollarını gösterir. #453'e göre JSONL metni ham
kalır. `/api/veri` ve dosya temelli okumalar, `no-store` veya UI'da saklama
kararıyla veriyi diskten kaldırmaz.

## MVP için önerilen saklama değerleri

Aşağıdaki süreler **öneridir**, mevcut uygulama davranışı veya onaylanmış
retention değildir. Operatör bunları kabul etmeden retention cleanup
etkinleştirilmemelidir.

| Sınıf | Önerilen MVP ömrü | Süre sonunda davranış | Dayanak ve açık karar |
|---|---|---|---|
| Görev kaydı/geçmişi | Çalışma alanı ömrü boyunca; terminal kayıtları otomatik budanmaz | Ayrı bir workspace kapatma/arsivleme kararı gerekir; görev bazında silme audit ve parent/child bağlarını etkileyebilir | Mevcut dosya tek task ledger; kaynaklarda görev TTL'si yok. Terminal durumlar değişmez, kayıtlar geçmişi taşır. |
| Sohbet JSONL | 90 gün aday | Yaşı dolan kapalı segmentler temizlenebilir; aktif dosya doğrudan truncate edilmez. Minimum yaş ve disk bütçesi çatışırsa sessiz erken silme yerine yazmayı durdur/operatör kararı | #449 aday değeri; #496 süre/bütçenin onay beklediğini söylüyor. |
| Ekran JSONL | 7 gün aday | 7 günden eski kapalı segmentler temizlenebilir; aktif dosya doğrudan silinmez. Bütçe dolması kayıtları daha erken silmemeli | #449 aday değeri; ekranlar ham ve hassas içerik kabul edilir. |
| Durable receipt payload | Çözümsüz işlem boyunca; terminalde yalnız ihtiyaç kanıtlı payload | Terminal payload temizlense bile kompakt tombstone/operation bağları kalır | #504/#527 önerisi. Payload TTL'si, tombstone ve retry/reconcile süresi henüz seçilmedi. |
| Tombstone ve terminal receipt metadata | En uzun kaynak-message tekrar ingest, provider reconcile/history ve insan retry karar penceresinden uzun | Bu pencereler belirlenmeden temizlenmez; kapasite dolarsa dispatch fail-closed ve operatör uyarısı | #527 bu süreleri açık bırakır; ID yeniden kullanımı ve sessiz eviction yok. |
| Backup | 30 gün ve 1 GiB aday | Tüm içindeki data sınıflarıyla beraber sona erer; erken temizleme minimum yaş kararına tabidir | #449 aday değeri; tam KOK backup'ı sohbet/ekranı da kopyalar; #496 açık kapsam/şifreleme/silme kararı ister. |
| Restore-check çalışma kopyası | Kontrol kabulünden itibaren 30 gün önerisi | Yalnız başarı, provenance, aktif kullanım ve açık hold kontrollerinden sonra ayrı temizlik | `docs/restore-check-retention-policy-530.md` önerisidir; bağımsız onay ve uygulama bekler. |

Mesaj/ekran için #449 ayrıca segment ve byte bütçesi adayları verir (mesaj
32 MiB/24 saat, ekran kimliği başına 8 MiB/24 saat; arşiv toplam bütçeleri
512/256 MiB). Bunlar hacim ölçümüyle doğrulanmamıştır. Tüm yaş/bütçe sınırları
aynı anda uygulanacaksa hangisinin öncelikli olduğu kabul edilmelidir. Bu notun
önerisi, minimum yaşı korumak ve bütçe yetmezse eski kayıtları sessizce erken
silmemektir; bunun bedeli yeni yazıların durmasıdır.

## Dışa aktarma

### Mevcut durum

- Panel `/api/veri` görev/durum, sınırlı sohbet tail'i ve seçilmiş ekran
  kayıtlarını döndürür; bunun tamamı veya tutarlı arşiv export'u olduğu
  söylenemez.
- `yuva oku` ve `yuva ekran oku` görüntüleme/okuma komutlarıdır; tarih aralığı,
  tutarlı tam snapshot, export manifest'i veya yedek checksum'u sağlayan
  kullanıcıya dönük export akışı kaynaklarda görünmüyor.
- Dosya kökünü doğrudan kopyalamak teknik olarak başka bir yedek oluşturur;
  erişim, içerik kapsamı, doğrulanmış bütünlük veya silme sonrası purging
  taahhüdü değildir.

### Sonraki faz için gereksinim

Kullanıcı başlatmalı export; seçilmiş sınıf ve tarih aralığını önizlemeli,
görev/mesaj/ekran/receipt ayrımını açık göstermeli ve kısmi veriyi `complete`
gibi sunmamalıdır. Export için tek bir lock/snapshot veya kesinti metadata'sı,
şema sürümü, kayıt sayıları, zaman aralığı, redaction sürümü ve içerik bütünlüğü
manifest'i tanımlanmalıdır. Hedef yol kullanıcıca seçilmeli; varsayılan dosya
owner-only izinle oluşturulmalı, KOK içine yazımın büyüme/backup etkisi açık
olmalıdır. Dış hedefe kopyalanmış export da yeni bir hassas backup'tır ve aynı
retention/silme planına girmelidir.

Gereksiz credential, auth secret, raw provider output ve hassas tool içeriği
export'a eklenmemelidir. Digest/fingerprint de düşük entropili içerikle
eşleştirilebilir; genel loga yazılmamalı, içerik kadar sıkı korunmalıdır.

## Silme ve redaksiyon

### MVP sınırı

Kaynakta sohbet, ekran ve görev için self-service per-record delete/erase API'si
görülmüyor. JSONL append-only kullanılır; görev defteri ise görev durum/geçmişi
ve ilişkileri tek kayıt içinde tutar. Kullanıcı isteğine karşı mevcut JSONL'yi
elle satır silerek yeniden yazma veya görev history'sini kısmi budama güvenli
ürün işlemi sayılmamalıdır: dedupe/receipt/audit referansları kopabilir ve
backup'larda eski içerik kalabilir.

İlk MVP'de ürün kullanıcı silme isteği karşılayamıyorsa bunu açıkça belirtmeli.
Veri kökünün tamamını kaldırmak gerekirse ayrı, açık operatör işlemi; tüm
yazıcıların durduğunun doğrulanması; export/backup saklama kararının alınması;
silinen kapsam ve kalan kopyalar için makbuz gerekir. Bu not böyle bir silmeyi
yetkilendirmez veya komut/uygulama tanımlamaz.

### Sonraki faz için gereksinim

- **Mantıksal silme:** kullanıcı talebi, actor ve kapsamı kaydedilir; bağlı
  görev/mesaj/ekran/receipt ilişkileri bulunur; UI'da gizleme fiziksel silme
  diye sunulmaz.
- **Fiziksel silme:** hangi veri ve kopyaların silineceği, JSONL re-write ya da
  segment/record key tasarımı, lock altında eşzamanlı writer'lar, fsync/rename
  belirsizliği, doğrulama ve başarısızlıkta fail-closed davranış önceden
  tasarlanır. Append-only audit ve dedupe tombstone ihtiyacı korunur.
- **Receipt payload:** hassas payload mümkün olduğunca kısa tutulur; terminal
  payload ayrıştırılabilir şekilde temizlenebilir, ancak unresolved/unknown,
  idempotency anahtarı, digest sürümü, terminal outcome ve tombstone
  uzlaştırma penceresi bitmeden kaybolamaz. #504/#527 değerleri için bir süre
  belirlenmediğinden şimdilik otomatik tombstone silme yoktur.
- **Backup purge:** silme isteğine dahil kopyalar (tar, arşiv, restore-check,
  export ve başka hedefler) envanterden bulunur. Backup zincirinden fiziksel
  silme retention/immutable snapshot nedeniyle gecikebilir; kullanıcıya hangi
  tarihte hangi kopyanın sona ereceği açıklanmalıdır. Restore sonrası silinen
  kaydın yeniden ortaya çıkmaması için delete tombstone/migration planı gerekir.
- **Audit:** silme olayında içerik değil; operation ID, kapsam/count/byte,
  actor, politika sürümü, zaman, yedek/export durumu ve sonuç tutulur. Audit
  yeni bir hassas içerik kopyası oluşturmamalıdır.

### Yazma öncesi redaksiyon

#465 ortak write-boundary redactor'ı, belirsiz içerikte fail-closed reddi ve
CLI/panel writer'larının aynı kurala bağlanmasını önerir. Bu öneri şu anda
tamamlanmış/uygulanmış garanti değildir. Redactor devreye girse dahi önceki
JSONL, mevcut backup ve export kopyalarını geriye dönük temizlemez; bunlar için
ayrı migration, retention ve purge kararı gerekir. Tam DLP varsayımı yapılmamalı;
belirsiz tespit kullanıcıya güvenli uyarı vermeli ve raw fallback yazmamalıdır.

## Güvenlik ve operasyon ilkeleri

- Tek güvenilen yerel UID varsayımını ve loopback sınırını kullanıcıya bildirin.
  `/api/veri` anonymous GET olduğu için farklı UID aynı network namespace'ten
  snapshot okuyabilir; HMAC POST kapısı bunu değiştirmez (#451/#455/#526).
- KOK, mesaj/ekran dosyaları, export ve backup aynı hassasiyet sınıfında
  owner-only korunmalıdır. `0700/0600` farklı UID'yi sınırlar, aynı UID'deki
  süreçleri değil (#465/#496).
- Okuma tail/byte/API bütçeleri bir görüntüleme sınırıdır; retention, redaction,
  export bütünlüğü veya tam veri silme kanıtı değildir.
- JSONL bozuk/kısmi kuyruğu, `append_unknown`/`rotation_unknown` veya receipt
  `commit_unknown` görülürse temizleme/yeniden yazma durur; önce kanıt salt
  okunur uzlaştırılır (#441/#450/#504).
- Saklama temizliği dry-run ve içeriksiz audit ile başlamalıdır. Minimum yaş,
  yedek dönüşü ve sorumlu kabul edilmeden otomatik silme etkinleştirilmemelidir.

## Açık operatör kararları

1. #449 mesaj/ekran/backup süre ve bütçelerini kabul et/değiştir; disk dolunca
   erken silme mi yazmayı durdurma mı olacağını seç.
2. Tam KOK backup'ında mesaj/ekran verisine izin verilip verilmeyeceğini, hedef
   izinlerini/şifrelemeyi ve backup expiry audit sahibini seç.
3. Task history retention'ı, workspace kapatma ve tam workspace silme
   sorumlusunu belirle.
4. Export kapsamı, formatı, hedef izinleri, redaction, hash manifesti ve
   backup/retention davranışını belirle.
5. Kullanıcı silme talebinin kapsamını, tombstone ve dedupe penceresini, backup
   zincirindeki silme zamanını ve silme audit deposunu belirle.
6. Receipt backend'i, payload TTL'si, unresolved/unknown saklama süresi ve
   terminal tombstone ömrünü provider retry/reconcile sözleşmeleriyle eşle.

Bu seçimler kabul edilene kadar otomatik retention cleanup, backup purge,
self-service erase ve provider receipt eviction kapalı kalmalıdır.

## Kaynaklar

- `docs/jsonl-retention-design.md` (#449) — önerilen mesaj/ekran/backup
  süreleri, segment/bütçe tasarımı; bunların ölçüm ve kabul gerektirdiği notu.
- `docs/jsonl-retention-operator-decisions-449.md` ve
  `docs/jsonl-storage-operator-decisions-496.md` — süre, bütçe, yedek,
  redaction ve silme kararlarının henüz onaylanmadığı sınırlar.
- `docs/jsonl-redaction-policy-adr-465.md` ve
  `docs/panel-privacy-redaction-inventory-453.md` — ham içerik, write-time
  redaction, API/UI ve eski kopyalar.
- `docs/local-api-access-decision-451.md`,
  `docs/local-api-get-snapshot-decision-455.md`,
  `docs/panel-api-route-scope-matrix-526.md` — UID ve anonymous GET sınırı.
- `docs/session-bridge-persistent-receipt-store-504.md` ve
  `docs/persistent-session-receipt-contract-527.md` — payload/tombstone
  saklama, unknown ve kapasitede fail-closed.
- `docs/linux-gecis.md` — tam KOK backup'ının `gorevler.json`, `mesaj.jsonl`
  ve `ekran/` kopyalarını içermesi.
- `panel/server.py`, `bin/yuva` — mevcut statik data path, writer, reader ve
  görev/panel yüzeyleri; canlı kullanıcı verisi bu işte açılmadı.
