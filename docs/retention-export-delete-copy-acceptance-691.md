# Yuva #691 — Retention, export ve delete kopya kabul formu

**Tarih:** 2026-10-23
**Durum:** Operatör karar formu; politika seçilmedi veya etkinleştirilmedi.
**Varsayılan:** Her belirsiz/owner'sız kopya `HOLD`; bu form tarama, export, retention, cleanup veya silme yapmaz.

## Karar sahipleri ve uygulama kapsamı

| Alan | Doldurulacak karar |
|---|---|
| Workspace / Yuva instance | ______________________________________________ |
| Data owner ve karar yetkilisi | ______________________________________________ |
| Backup/restore owner | ______________________________________________ |
| Security/privacy/incident hold owner | ______________________________________________ |
| Operasyon/purge sorumlusu | ______________________________________________ |
| Politika sürümü ve change/request ID | ______________________________________________ |
| Onay tarihi/saat dilimi, yürürlük ve review tarihi | ______________________________________________ |
| Kapsamdaki data root ve sistem/ortamlar | ______________________________________________ |

Kararlar workspace, user, tarih aralığı ve copy class ile sınırlanır. Owner, kopyanın kapsamını ve yasal/incident hold durumunu doğrulamadan TTL/“sil” sonucu uygulanmış sayılmaz. Boş/çelişkili alanlar `HOLD` demektir.

## Tek kopya envanteri ve karar matrisi

Her satır her fiziksel/lojik kopya için tekrarlanmalıdır. Önerilen süreler #651/#629/#546 adaylarıdır; bu formda onaylanmaz. Birincil dosya, segment, backup archive, restore-check, export, cache/index ve başka hedefler ayrı kopyalardır.

| Copy class / örnek | İçerik ve bugün bilinen durum | Policy / TTL seçimi | Copy owner | Hold/incident durumu | Export durumu | Delete/purge kanıtı ve restore suppression |
|---|---|---|---|---|---|---|
| Chat primary/closed segments (`mesaj.jsonl`) | Ham serbest metin/provenance; user-facing full export veya delete aracı yok. | ☐ 90 gün aday ☐ Değiştir: ____ gün ☐ Süre kararı bekle | ______ | ☐ Yok (kanıt ref: ___) ☐ ACTIVE ☐ HOLD ☐ UNKNOWN | ☐ Yok ☐ İzinli scope: ___ ☐ Kapalı | ☐ Bulunmadı ☐ Purge verified ref: ___ ☐ Tombstone/suppression: ___ |
| Screen primary/closed segments (`ekran/<id>.jsonl`) | Hassas terminal satırları; #564 yalnız belirli yeni write pattern'lerini maskeler. Eski satır/kopyalar geriye dönük temizlenmedi; tam DLP yok. | ☐ 7 gün aday ☐ Değiştir: ____ gün ☐ Süre kararı bekle | ______ | ☐ Yok (kanıt ref: ___) ☐ ACTIVE ☐ HOLD ☐ UNKNOWN | ☐ Yok ☐ İzinli identity/date scope: ___ ☐ Kapalı | ☐ Bulunmadı ☐ Purge verified ref: ___ ☐ Tombstone/suppression: ___ |
| Task ledger/history (`gorevler.json`) | Görev detail/geçmiş notu ve actor alanları; ayrı task history TTL veya self-service delete yok. | ☐ Workspace ömrü ☐ Süre: ___ ☐ Karar bekle | ______ | ☐ Yok ☐ ACTIVE ☐ HOLD ☐ UNKNOWN | ☐ Yok ☐ Yetki/scope: ___ ☐ Kapalı | ☐ Bulunmadı ☐ Retention/purge ref: ___ ☐ Parent/child/audit etkisi: ___ |
| Full backup/archive (`yuva-*.tar`, replicas) | Durum/görev/chat/screen kopyalayabilir; checksum authentic provenance kanıtı değildir. | ☐ 30g/1GiB aday ☐ Değiştir: ___ ☐ Karar bekle | ______ | ☐ Yok ☐ ACTIVE ☐ HOLD ☐ UNKNOWN | Backup user export değildir; ☐ başka onay: ___ | ☐ Expiry/purge ref: ___ ☐ Immutable expiry: ___ ☐ Restore suppression: ___ |
| Restore-check tree (`restore-check.*`) | Extract edilmiş kopya; `ACTIVE/HOLD` ve bilinmeyen owner/process varsa TTL dolması silme izni değildir. #530 30 gün önerisi kabul edilmemiştir. | ☐ Kabul sonrası 30g aday ☐ Değiştir: ___ ☐ Karar bekle | ______ | ☐ ACTIVE ☐ HOLD ☐ UNKNOWN ☐ ACCEPTED (ref: ___) | Kullanıcı export sayılmaz | ☐ Inventory + purge ref: ___ ☐ Backup source binding: ___ |
| User export artifact / downloaded copy | Bugün user-facing full/tarih aralıklı export yok; her dışa aktarım yeni hassas kopya olur. | Per-artifact TTL: ___ gün/byte: ___ ☐ Kapalı ☐ Karar bekle | ______ | ☐ ACTIVE ☐ HOLD ☐ UNKNOWN | ☐ İzinli format/scope: ___ ☐ Kapalı | ☐ Hedef envanteri: ___ ☐ Purge receipt: ___ |
| Cache/search/index/temp/agent-side copy | Kapsam/retention mekanizması bu kaynaklarda complete envanter değil. | TTL: ___ ☐ Yok ☐ Karar bekle | ______ | ☐ ACTIVE ☐ HOLD ☐ UNKNOWN | ☐ Kapalı ☐ İzinli scope: ___ | ☐ Kaynak ve kopya listesi: ___ ☐ Purge/expiry ref: ___ |
| Incident/legal/eDiscovery hold copy | Hold, normal TTL/cleanup üzerinde veto taşır. | Hold review date: ___; hold kaldırma yetkisi: ___ | ______ | ☐ ACTIVE ☐ HOLD ☐ UNKNOWN | Yalnız ayrı yetkiyle | ☐ Hold kapanış ref: ___ ☐ Sonraki purge kararı: ___ |

**Ek kopya sınıfları/path owner (content okumadan envanter ref'i):**

___________________________________________________________________________

## Saklama, rotation ve expiry kararı

Birincil kayıt TTL'si ile backup/export/restore-check ömrü ayrı seçilir. Süre başlangıcını her class için işaretleyin: ☐ record create ☐ segment close ☐ restore-check accepted ☐ export created ☐ başka: __________.

| Veri sınıfı | Seçilen TTL / limit | Rotation/segment gereksinimi | Minimum yaş–bütçe çatışması | Yetkili onay |
|---|---|---|---|---|
| Chat | __________ | __________ | ☐ yaş korunur, yazma durur ☐ başka: ____ ☐ karar bekle | __________ |
| Screen | __________ | __________ | ☐ yaş korunur, yazma durur ☐ başka: ____ ☐ karar bekle | __________ |
| Task/history | __________ | __________ | ______________________________ | __________ |
| Backup | __________ | immutable/replica expiry: __________ | ______________________________ | __________ |
| Restore-check | __________ | accepted-at: __________ | ______________________________ | __________ |
| Export/other copy | __________ | owner/location: __________ | ______________________________ | __________ |

TTL dolması ancak ilgili kopyanın kaynağı, owner'ı, hold ve restore ilişkisi biliniyor ve onaylı mekanizma varsa `ELIGIBLE` anlamına gelebilir; otomatik silme izni değildir. Bozuk/yarım JSONL, append/rotation/commit belirsizliği, read error, `ACTIVE`, `HOLD`, unknown copy path veya owner/process belirsizliğinde cleanup başlamaz. Asgari saklama yaşı ile bütçe çatışınca erken silme ancak owner'ın açık kararını ister; sessiz erken purge yok.

## User export kabul kapısı

**Bugünkü durum:** Panel GET tail'i veya `yuva oku`/`yuva ekran oku` tam/tarih aralıklı, tutarlı, kullanıcıya sunulabilir export contract'ı değildir. Bu form tek başına export özelliği yaratmaz.

Export geliştirme/istek açılmadan önce doldurun:

- Yetkili requester ve veri sahibi: ______________________________
- Dahil edilen class/person/date range ve dışlanan kopyalar: ______________________________
- Snapshot consistency: ☐ ortak lock/snapshot ☐ açıkça partial ☐ karar bekle
- Schema/version, record/byte count, time span, redaction sürümü ve integrity manifest: ______________________________
- Legacy raw screen/chat içeriği: ☐ içerme ☐ dışla ☐ ayrıca açık uyarı ☐ karar bekle
- Target/destination ve owner-only mode/access custody: ______________________________
- Export TTL, hold, backup kopyaları ve expiry: ______________________________
- Partial, permission, source read ve size limit hatasında: ☐ reddet ☐ partial işaretle ☐ karar bekle

Export “complete” denmesi ancak seçilen kapsam, kaynak okuma sınırı, kısmi kayıt ve bütün export kopyaları kanıtlandıysa mümkündür. Backup arşivi veya API tail'i kullanıcı export'u diye sunulmaz.

## Delete/purge ve talep sonucu

Per-record/workspace self-service delete bugün mevcut değildir. JSONL satırı yerinde elle düzenlenmez. **Mantıksal gizleme**, **birincil dosyadan removal** ve **bütün kopyalarda fiziksel purge** ayrı sonuçlardır; kanıt yokken “silindi” sözü verilmez.

| Delete talep alanı | Karar/kanıt |
|---|---|
| Request ID, requester authority, received time | ______________________________ |
| Hedef class/identity/date/message scope ve kapsam dışı alan | ______________________________ |
| Data owner karar/onayı | ______________________________ |
| Hold/incident check, owner ve kaldırma şartı | ______________________________ |
| Primary/segment/archive/backup/export/cache/index/restore-check copy inventory ref | ______________________________ |
| Mutation/rotation procedure, stopped writer/lock/drain proof (ayrı uygulama görevi) | ______________________________ |
| Post-delete readback/manifest/count/bytes sonucu | ______________________________ |
| Backup immutable expiry veya purge/tombstone suppression kararı | ______________________________ |
| Her kopya sonucu: `ACTIVE` / `HOLD` / `ACCEPTED` / `ELIGIBLE` / `DELETED` / `UNKNOWN` | ______________________________ |
| User-facing sonuç ve kalan kopyalar/son kullanma tarihi | ______________________________ |

Backup restore silinmiş veriyi yeniden getirebiliyorsa tombstone/suppression veya restore sonrası purge planı olmadan restore online açılamaz. Immutable backup henüz süresi dolmadı/erişilemiyorsa onu `DELETED` olarak işaretlemeyin; kullanıcıya kopya bazlı kalan durum ve expiry açıklanmalıdır.

Purge kanıtı content dump içermemelidir; copy ID/path için restricted inventory reference, policy version, operation/time/owner, önce/sonra metadata/count/byte result ve error/unknown sonucu yeterli olacak şekilde ayrı kabul edilmelidir. Bilinmeyen kopya, başarısız purge veya belirsiz commit tüm talebi `UNKNOWN/HOLD` tutar.

## Hold ve durum makinesi

Her kopya için ayrı status kaydedin:

`UNKNOWN → ACTIVE → HOLD | ACCEPTED → ELIGIBLE → DELETED`

- `UNKNOWN`: yer, owner, provenance veya işlem sonucu belirsiz; default HOLD.
- `ACTIVE`: çalışan primary, current export/backup, işlemdeki staging/restore-check; retention cleanup yok.
- `HOLD`: incident/legal/security/user dispute veya unresolved commit; normal TTL silme adayı değildir.
- `ACCEPTED`: restore-check sonucu ve owner acceptance mevcut; yalnız ilgili policy şartları sağlanırsa retention clock başlayabilir.
- `ELIGIBLE`: imzalı TTL dolmuş, hold yok, kopya envanteri doğrulanmış; purge için ayrıca açık operation approval gerekir.
- `DELETED`: yalnız bu belirli kopya için purge/expiry receipt doğrulanmış; başka kopyalara genellenmez.

Hold kaldırma yetkisi hold owner'ına aittir; cleanup implementatörü hold'u kendi başına kaldıramaz. `UNKNOWN` hiçbir zaman TTL veya `mtime` ile otomatik `ELIGIBLE` olmaz. #530 restore-check için 30 gün, ancak successful accepted check'ten itibaren öneridir; `mtime` ve klasör yaşı başlangıç zamanı değildir.

## İmzalar ve uygulama kapısı

- Veri sahibi policy/class/TTL ve user promise kapsamını onaylar: __________________ Date: ______
- Backup/restore owner tüm backup/replica/restore-check kopyalarını ve expiry'yi onaylar: __________________ Date: ______
- Security/privacy/incident owner hold ve release kriterini onaylar: __________________ Date: ______
- Export/delete operation owner purge evidence ve unresolved davranışını onaylar: __________________ Date: ______
- Bağımsız reviewer copy inventory ve kapsamın tamamını gözden geçirir: __________________ Date: ______
- Son karar: ☐ politika kabulü ☐ ayrı implementation/fixture aç ☐ ertele / NO-GO

İmzalar politika tercihi içindir; retention/export/delete kodunun uygulandığını veya bir talebin tamamlandığını kanıtlamaz. Uygulama rollout'u, dry-run, source/backup inventory ve purge verification ayrı teslim/izin gerektirir. Bu belgede tüm alanlar boş olduğundan mevcut karar **HOLD; otomatik retention/export/purge kapalı**.

## Kaynaklar ve sınır

- `docs/data-retention-operator-decision-form-651.md` — owner formu, aday TTL/bütçeler ve export/delete kapısı.
- `docs/chat-screen-retention-export-delete-matrix-629.md` — chat/screen/backup/export kopya etkileşimi ve mevcut feature yokluğu.
- `docs/local-data-retention-export-deletion-policy-546.md` — yerel MVP aday politikası ve belirsizlikte otomasyon kapalı.
- `docs/restore-check-retention-policy-530.md` — `ACTIVE/HOLD/ACCEPTED/ELIGIBLE/DELETED`, 30 günlük post-acceptance önerisi ve mtime sınırı.
- `docs/credential-exposure-incident-runbook-585.md` — incident karantina/hold.

Gerçek geçmiş/backup listesi veya içeriği okunmadı; export, delete, restore, purge, retention, code veya service üzerinde işlem yapılmadı.
