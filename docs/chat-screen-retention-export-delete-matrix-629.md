# Sohbet ve ekran verisi: saklama, export ve silme karar matrisi (#629)

**Tarih:** 2026-10-23
**Durum:** Operatör karar taslağı; otomatik retention, kullanıcı export'u veya silme işlemi uygulanmadı.
**Güncel fark:** #564 ekran yazıcılarına sınırlı fail-closed credential redaksiyonu ekledi. Sohbet yazıcılarında aynı redaction yok; önceki ekran kayıtları, backup'lar ve export kopyaları da geriye dönük değişmedi. Her iki veri sınıfının retention süreleri hâlâ operatör onayı bekleyen adaylardır.

## Karar özeti

- İlk yerel MVP'de açık operatör onayı ve kabul edilmiş mekanizma olmadan otomatik retention cleanup, per-record delete veya kullanıcıya “silindi/export edildi” taahhüdü açılmamalıdır.
- Öneri olarak sohbette **90 gün**, ekran kayıtlarında **7 gün** saklama adayı korunur; bunlar etkin politika değildir. Tam KOK backup'ı ikisini de kopyalayabildiğinden backup/export/restore kopyalarının ömrü ayrıca kararlaştırılmalıdır.
- Sohbet ve ekran aktif JSONL dosyaları append-only kabul edilir. Yaş/bütçe temizliği uygulanacaksa önce aktif segment rotation, ortak writer lock ve bozuk/unknown kuyrukta fail-closed davranış gerekir. Minimum yaş korunacaksa disk bütçesi dolduğunda eski veriyi sessizce erken silmek yerine yazma durdurulup operatör uyarılmalıdır.
- `GET /api/veri` tail'i export değildir; tam, tarih aralıklı veya tutarlı arşiv olduğuna dair contract yoktur. Mevcut CLI `oku`/`ekran oku` görüntüleme yolları da user-facing export sunmaz.
- Kullanıcı silme isteğinde bugün güvenli per-record delete aracı yoktur. Aktif JSONL'yi elle düzenlemeyin; kapsam, backup/export kopyaları ve restore ile yeniden ortaya çıkma riski için veri sahibinin kontrollü purge kararı gerekir.

## Sınıf bazlı matris

| Sınıf ve kalıcı kaynak | Hassasiyet / mevcut redaksiyon | Saklama kararı | Export kararı | Silme / backup / hold kararı |
|---|---|---|---|---|
| **Sohbet ve sistem mesajları** — `mesaj.jsonl` | Serbest `metin`, kimlik/hedef/timestamp ve provenance metadata'sı; ham mesaj metni yazılır. #564 ekran writer'larını kapsar, chat writer'larını değil. Panel `/api/veri` son en fazla 200 kaydı, UI daha azını gösterse de API/disk kapsamını daraltmaz. | **90 gün aday**, henüz ölçülmemiş/onaysız. Önerilen hedef aktif dosya değil, ortak kilitle döndürülen kapalı segmentlerdir. Segment/yaş/byte cleanup uygulanmıyor; disk limitleri mevcut dosyayı kendiliğinden silmez. | Bugün tam/tarih filtresi olan user export yok. Panel tail'i kısmi; `yuva oku` da kullanıcıya yönelik arşiv/manifest veya tutarlı snapshot sağlamaz. Gelecek export kullanıcı tarafından başlatılmalı, tarih aralığı, kapsam, redaction sürümü, kayıt sayısı ve `complete/partial` durumunu göstermeli. | JSONL satırını yerinde silme/rewrite yapmayın. Per-record delete sözleşmesi yok. Tam KOK backup'ı mesajları içerebilir; birincil kaydın kaldırılması backup kopyasını kaldırmaz. Incident/unknown durumunda ilgili kopyalar `HOLD` ve erişim kısıtlı kalır. |
| **Ekran/terminal kayıtları** — `ekran/<kimlik>.jsonl` | Komut/terminal satırı, yol ve serbest içerik yüksek hassasiyetlidir. #564 panel ve CLI kalıcı screen writer'larında bilinen bearer/basic, credential assignment, credential URL ve bazı token kalıplarını maskeler; tip/alan/encoding/size/redactor hatasında yazımı reddeder. Bu tam DLP, PII/path redaction veya kodlanmış/parçalı secret garantisi değildir. #564 öncesi satırlar ve kopyalar ham kalır. | **7 gün aday**, henüz ölçülmemiş/onaysız. Ekran tail'inin 60 kayıt/reader byte limitleri yalnız aktarımı sınırlar, disk retention değildir. Önerilen rotation kimlik başına ortak lock altında olmalı; retention yalnız kapalı segmentte çalışmalıdır. | `yuva ekran oku` ve panelin seçilmiş screen map'i export contract'ı değildir. Gelecek export kimlik ve tarih kapsamını önizlemeli; ekran satırlarını ayrı ve yüksek hassasiyetli sınıf olarak göstermeli. Redaction sürümü/legacy raw içerik durumu açıklanmalıdır. | Eski/hatalı/şüpheli satırları yerinde editlemeyin. Tek kimlik dosyasını silmek backup, export, restore-check ve başka kopyaları silmez. Credential incident'inde içerik taraması/kopyalama yerine #585 karantina ve credential lifecycle akışı gerekir; purge öncesi hold sahibi karar vermelidir. |
| **Export artifact'ı** — bugün user-facing mekanizma yok | Export, içerik seçilmiş olsa da yeni kalıcı hassas kopyadır. Mesaj ve ekran için redaction/retention kaynaklarıyla birlikte sınıflandırılmalıdır. | Her artifact için ayrı expiry ve sahip belirlenmeli; varsayılan süresiz saklama kabul edilmemelidir. Önerilen 90/7 günlük kaynak politikaları export ömrünü otomatik olarak belirlemez. | Gelecek format tek snapshot/lock veya kesinti metadata'sı, schema sürümü, zaman aralığı, içerik sınıfı, redaction sürümü ve bütünlük manifest'i taşımalı; eksik kaynak/sınır aşımını `complete` gibi sunmamalıdır. Hedef path kullanıcı seçmeli, default mode owner-only olmalıdır. | Delete request export'ları da envantere alır. Yetkili purge veya hold kararı ayrı tutulur; index/cache/indirilen dosya kopyaları kapsam dışı bırakılmamalıdır. |
| **Backup ve restore-check kopyası** — full KOK arşivi ve scratch restore | Full KOK backup'ı sohbet ve ekran içeriğini, ayrıca eski ham satırları taşıyabilir. Scratch restore-check bağımsız yeni içerik kopyasıdır. | #449'un **30 gün / 1 GiB** backup değeri ve #530'un **30 gün** restore-check önerisi adaydır, onaylı değildir. Backup expiry uygulanacaksa içerik sınıflarının tamamına ve restore/hold istisnasına bağlanmalıdır. | Operatör backup'ı user export yerine kullanmamalı; arşiv bütünlüğü/format doğrulaması user export kapsam/tarih filtresi anlamına gelmez. | Silme talebi backup zincirinde fiziksel silmenin ne zaman gerçekleşeceğini kullanıcıya söylemelidir. Backup restore, silinmiş mesajı/screen satırını geri getirebilir; restore öncesi purge/delete tombstone veya post-restore suppression planı olmadan canlıya açılmamalıdır. Restore-check `ACTIVE/HOLD/ACCEPTED/ELIGIBLE/DELETED` envanterini ve owner onayını gerektirir. |

## Ortak yaşam döngüsü akışı

1. **Veri sahibi ve kapsam:** İstek sohbet mi, screen mi, tarih/kimlik aralığı mı, tek kayıt mı, tam workspace mi; requester yetkisi ve saklama gerekçesi owner tarafından doğrulanır. İçerik incident incelemesi için açılmaz; gerekirse #585'teki gibi artifact reference ile ilerlenir.
2. **Retention seçimi:** Owner chat/screen TTL'lerini, active segment boyut/rotasyonunu, archive byte limitini ve bütçe dolduğunda önceliği onaylar. Minimum yaş ile disk bütçesi çatışırsa “erken sil” veya “yazmayı durdur” kararı açıkça verilir; öneri minimum yaşı koruyup yazmayı durdurma yönündedir.
3. **Export:** Kullanıcı kapsamı preview eder; export'un partial olup olmadığı, screen legacy raw riski ve hedef izni gösterilir. Tam veriye erişim yetkisi export'u otomatik yetkilendirmez. Export artifact'ı owner, access, TTL/hold ve purge kaydı alır.
4. **Delete:** Onaylı silme mekanizması yoksa işlem kabul edilmiş tamamlanma olarak işaretlenmez. Gelecek uygulama için stable operation ID, lock altında segment/record migration, write/fsync/rename belirsizliği, tombstone, backup/export inventory ve post-restore suppression gerekir. UI'da gizleme mantıksal silmedir; fiziksel purge kanıtı değildir.
5. **Kopya kapanışı:** Birincil JSONL, arşiv segmentleri, full backup, export, cache/search, restore-check ve incident hold her biri envanterde ayrı satır olur. Yalnız tamamı için sonucu belli olan kopyalar temizlendiğinde talep “tamamlandı” denebilir; kalan immutable/hold kopyalarının owner ve sona erme zamanı açıklanır.

## Etkinleştirme ve fail-closed kararları

| Konu | Mevcut durum | Gerekli owner kararı/kanıtı | Karar yoksa |
|---|---|---|---|
| Chat 90g / screen 7g | Adaylar; otomatik retention yok | Veri sahibi TTL, sınıf gerekçesi ve revizyon tarihini onaylar | Veri kendiliğinden silinmiyor; kullanıcıya süre garantisi verilmez |
| Segment rotation ve disk bütçesi | #449 tasarımında; kaynakta retention/rotation uygulanmış değil | Writer'lar, lock inode'u, fsync/restart ve bounded reader uyumu fixture'da kabul edilir | Auto cleanup/rotation kapalı; disk dolarsa owner kararı olmadan eski kayıt sessiz silinmez |
| Yazma öncesi redaction | Screen için sınırlı #564 uygulaması; chat için bu kapsamda ortak filtresi yok | Chat kapsamı ve screen redactor sınırları, legacy migration planıyla seçilir | Chat raw hassas kabul edilir; screen de tam temiz sayılmaz |
| User export | Mevcut değil | Scope, consistency/partial, manifest, hedef mode, retention/expiry ve redaction sürümü belirlenir | Panel tail'i/export diye sunulmaz |
| Per-record veya workspace delete | Mevcut self-service API/CLI yok | Operation/audit, writer stop/lock, backup/index/export inventory, tombstone ve restore suppression tasarlanıp test edilir | Manuel JSONL edit/silme önerilmez; talep `pending_owner_decision` kalır |
| Backup/restore purge | #530/#546 öneri ve envanter sözleşmesi; genel auto purge yok | Backup owner TTL/HOLD/immutability ve purge makbuzunu kabul eder | Restore-check klasörü mtime'a göre toplu silinmez; backup içerik scope'u unknown kalır |

Kabul edilen politika, sahibi, politika sürümü ve tarih kayıt altına alınmadan otomatik cleanup açılmamalıdır. Cleanup ilk olarak içeriksiz dry-run envanteri üretmeli; bozuk JSONL, son LF'siz kuyruk, `append_unknown`, `rotation_unknown`, `ACTIVE`/`HOLD` artifact veya belirsiz silme sonucu görülünce işlem durmalıdır. Silme retry'si önce salt-okunur path/list uzlaştırması gerektirir.

## Dayanak ve sınırlar

- [#546 genel retention/export/delete politikası](local-data-retention-export-deletion-policy-546.md) — 90g/7g/30g adayları ve onaysızlık; kullanıcı export/silme sınırı.
- [#564 screen writer redaction](screen-secret-redaction-564.md) — yeni screen yazımlarında dar credential filtresi; eski kayıtların ve backup'ların değişmediği sınır.
- [#449 JSONL retention tasarımı](jsonl-retention-design.md) ve [#496 operatör kararları](jsonl-storage-operator-decisions-496.md) — aday segment/bütçe ve açık owner tercihleri.
- [#530 restore-check retention](restore-check-retention-policy-530.md) — `ACTIVE/HOLD/ACCEPTED/ELIGIBLE/DELETED`, purge kapısı.
- [#585 credential incident runbook](credential-exposure-incident-runbook-585.md) — içeriği açmadan karantina/consumer/revoke/kopya envanteri.
- [#453 panel redaction envanteri](panel-privacy-redaction-inventory-453.md) — sohbet ham içeriği, API tail'i ve read/write yüzeyleri.

Bu belge karar matrisi önerir; TTL onayı, export/delete kodu, JSONL rotation/cleanup, gerçek içerik incelemesi, backup açma, purge veya host/servis değişikliği yapmaz. #564'ün bilinen screen-secret pattern'leri dışında tam DLP varsayımı yoktur.
