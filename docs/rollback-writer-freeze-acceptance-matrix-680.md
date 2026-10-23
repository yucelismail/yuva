# #680 — Rollback öncesi writer-freeze kabul ve kanıt matrisi

**Tarih:** 2026-10-23
**Durum:** Runbook/ADR; canlı servis, süreç, kilit veya data root üzerinde işlem yapılmadı. Test çalıştırılmadı.
**Kaynaklar:** #645 actual-data gate, #663 writer eşzamanlılığı runbook'u, #552/#611 writer çağrı haritaları.

## Karar

#645'in bounded read-only şema taraması ve `INSTALL_ROOT/.install.lock` tek başına data root için ortak snapshot veya writer-free rollback sağlamaz. Kanonik CLI/panel writer'larının `.kilit` kullanması yalnız aynı lock protokolüne uyan çağrıları sıraya koyar. Tarihsel/dev/UI kopyaları, importer'lar ve keyfi aynı-UID writer'lar bu lock'a uymayabilir.

Bu yüzden rollback öncesinde **bütün writer girişleri belirlenip admission kapatılmadan, in-flight işlemler drain edilmeden ve lock/data/pointer sonucu kesinleştirilmeden GO verilmez**. Mevcut kaynakta tüm writer sınıflarını kapsayan global admission-freeze yoktur; belirsiz sınıf, stale süreç, timeout, gate sonucu veya `CommitUnknown` **HOLD** demektir. Bu belge bir host freeze'inin uygulandığını iddia etmez.

## Writer sınıfı ve kanıt matrisi

| Writer sınıfı | Data root etkisi ve mevcut eşzamanlılık | Freeze/admission kanıtı | Drain/stale kanıtı | Timeout veya belirsizlik sonucu |
|---|---|---|---|---|
| Kanonik CLI task geçişleri (`ekle`, `ata`, `al`, `teslim`, `ilk-kontrol`, `denetle`, `iptal`, `sonraki`) | `gorevler.json`; aynı `YUVA_DIR/.kilit` üzerinde `flock`. Normal geçişte kilit tam oku-değiştir-yazı kapsar; `sonraki` de seçme/atamayı aynı kilitte yapar. Varsayılan lock bekleme sınırı 10 sn. | Yeni CLI task invocation'larını hostça kapatan, sahibi belli maintenance/admission bariyeri; yalnız terminale “bakımda” yazmak yeterli değil. | Mevcut işlem normal tamamlandı veya hata sonucu uzlaştırıldı; bekleyen çağrı yok. Bariyer altında yeni çağrı kabul edilmediği kanıtlanmalı. | Lock alınamazsa, işlem sonucu bilinmiyorsa veya bariyer CLI girişini kapsamıyorsa **HOLD**. `flock -n` tek örneği drain kanıtı değildir. |
| Panel task API (`POST /api/gorev`) | Panel `gorev_calistir()` ile aynı CLI core'a dispatch eder ve aynı data lock'a girer. `_TASK_CORE_LOCK` yalnız panel sürecinde module/çıktı çağrılarını sıraya koyar; global data lock değildir. | Route'a yeni task POST kabulünü kapat; ingress değişikliği/maintenance kararı ve bütün panel instance'ları için etkin olduğuna dair kanıt. | Kabul edilmiş isteklerin handler ve CLI core işlemi tamamlanmalı; queued/in-flight request kalmamalı. | Panel durdurma veya health/offline göstergesi tek başına in-flight isteğin bittiğini kanıtlamaz. Drain belirsizse **HOLD**. |
| Kanonik CLI/panel state ve roster yazımları (`durum.json`) | `baglan/katil`, `ayril`, ad/rol/sorumlu/baş-denetçi ve kalp/presence gibi işlemler kullanıcı durumunu etkileyebilir. Desteklenen girişler data-root lock'ını paylaşabilir. | Bu CLI alt komutlarını, panel mutation route'larını ve otomatik heartbeat/daemon admission'ını ayrı ayrı kapat; sadece task route'unu kapatmak yeterli değil. | Heartbeat/daemon döngüsü durdurulup in-flight state yazımı tamamlandığı kanıtlanmalı; timer restart/retry kuyruğu kalmamalı. | Kaynağı belli olmayan roster/presence yazıcısı veya devam edebilen daemon **UNKNOWN → HOLD**. |
| Kanonik mesaj/audit yazımları (`mesaj.jsonl`) | CLI/panel mesaj yolları ve admin mutation audit append'leri. State değişimi ile audit append'i tek transaction değildir; handler/append tamamlanması ayrı izlenmelidir (#674). | `/api/yaz`, CLI mesaj/ekran bildirimi ve audit-producing admin route'ları dahil bütün girişleri kapat. | State commit ve ilişkili append'in tamamlanması/sonucunun uzlaştırılması beklenmeli; yalnız state lock'ın boş görünmesi işlem sonucunu açıklamaz. | State sonrası append hatası veya işlem sonucu belirsizse makbuz/ledger uzlaştırması olmadan **HOLD**. |
| Kanonik ekran JSONL yazımları (`ekran/**/*.jsonl`) | CLI ve panel `/api/ekran` yolları ekran kayıtlarını yazar; desteklenen panel uçları data-root lock'ı kullanır. Her ekran dosyası ayrı olsa da rollback gate tüm kökü tarar. | Screen append ve onu başlatan agent/worker admission'ını kapat. | Tüm kabul edilmiş append'ler bitmeli; gate sırasında herhangi bir ekran dosyasının değişmesi freeze ihlalidir. | Gate okumasında dosya/metadata değişirse veya screen writer kapsam dışı kalırsa **HOLD**. |
| Backup/restore ve installer işlemleri | #645 rollback `INSTALL_ROOT/.install.lock` alır; bu lock Yuva data writer'larını durdurmaz. Restore/backup aracı yanlışlıkla aktif `YUVA_DIR`'e yazabilir; scratch-only araçlar ayrı root'ta kalmalıdır. | Aynı install root'a erişen install/rollback/backup/restore admission'ını, aktif data root'a yazma ihtimaline göre koordine et. | Devam eden extraction, restore veya pointer işlemine ait tüm sonuç kesinleşmeli. Scratch işleminin hedefi aktif data root olmadığını kanıtla. | Install lock beklemesi, data writer freeze yerine geçmez. Root/target ayrımı belirsizse **HOLD**. |
| Legacy/dev/UI/restore CLI veya panel kopyaları | Bilinen kopyalar farklı schema/lock davranışı taşıyabilir; restore-check ve bazı eski kopyalar fail-open/lock'suz yazabilir. #552/#611 evrensel OS-level tek writer kanıtı vermiyor. | Her kopya/launcher/panel için host admission/erişim sınırı ya da açıkça doğrulanmış kullanım dışı durumu gerekir. PATH'ten kaldırma absolute path/import/panel çağrısını kapatmaz. | Process, caller ve seçtiği `YUVA_DIR` bilinmeli; yalnız `ps`, PID yokluğu veya panel offline durumu yeterli değildir. Aynı-UID/başka worktree bypass'ı ayrı ele alınmalı. | Tek bir kopya/launcher/importer veya aynı-UID writer UNKNOWN ise **HOLD**. Tarihsel restore-check kopyaları çalıştırılmamalıdır (#638/#659). |
| Keyfi aynı-UID dosya yazıcısı/importer/elle başlatılan süreç | Canonical `.kilit` kullanma zorunluluğu yok; doğrudan JSON yazımı, `SourceFileLoader` veya farklı CLI kopyası mümkün. | Tüm aynı-UID writer alanı kapatılmalı ya da yazma yetkisi OS/UID/ownership sınırıyla kaldırılmalı. Kod içi cooperative flock bu sınıfı zorlayamaz. | Sahip, executable/source, `YUVA_DIR` hedefi ve in-flight durumuna dair güvenilir host kanıtı gerekir. Bilinmeyen süreç stale writer sayılır; otomatik öldürme bu sözleşmede yoktur. | Evrensel caller envanteri veya OS admission sınırı yoksa **UNKNOWN → HOLD**. |

Tablodaki “mevcut eşzamanlılık” kaynak incelemesine dayalıdır; her kurulu kopya veya çalışan process'in aynı yolu kullandığı anlamına gelmez. Her satırın gerçek host kanıtı release owner tarafından tarih/saat ve kaynakla doldurulmalıdır.

## Freeze, drain ve rollback sırası

1. **Root ve writer envanteri:** `INSTALL_ROOT`, `current/previous` pointer'ları, hedef release ve gerçek `YUVA_DIR` operatörce sabitlenir. Yukarıdaki her writer sınıfı için executable/caller, UID/sahip, hedef root, admission kontrolü ve kanıt kaynağı kaydedilir. Bir sınıf veya root bilinmiyorsa ilerleme **HOLD**.
2. **Admission kapat:** Panel POST, CLI/wrapper, timer/daemon/worker, backup/restore ve bilinen legacy girişleri için ayrı bariyer uygula. Kapanışın yeni invocation'ları gerçekten reddettiği doğrulanır. Bu repo sürümünde global bariyer kanıtı yok; yalnız paneli durdurma veya PATH temizleme yeterli sayılamaz.
3. **Drain:** Bariyerden önce kabul edilen mutation'lar normal bitene veya açık sonuçla uzlaştırılana kadar bekle. Tek bir lock örneklemesi, process listesi, heartbeat yaşı veya panel offline rozeti drain kanıtı değildir. Çağrı/worker kuyruğu veya stale writer belirsizliği kalırsa **HOLD**.
4. **Lock kimliği ve sıra:** Teknik gate uygulandığında sıra `INSTALL_ROOT/.install.lock` → doğrulanmış `YUVA_DIR/.kilit` olmalı; ters lock sırası deadlock riski doğurur. Data lock tam olarak `YUVA_DIR/.kilit` path/inode'u olmalı; regular file, owner/mode/link/no-follow kontrolleri ve kilit sırasında inode recheck geçmeli. Eksik, symlink, değişen inode veya uyumsuz lock üzerinde dosya silme/yenileme yapma; **HOLD**.
5. **Sonlu deadline:** Admission close, drain ve lock acquisition için operatörce tanımlanmış tek bir sonlu toplam deadline ile faz limitleri kaydedilir. Bu belgede değer belirlenmemiştir; onaylı süre yoksa freeze işlemi başlatılamaz. Süre aşımında lock zorla açılmaz, otomatik retry/pointer mutasyonu yapılmaz; writer durumu UNKNOWN ise **HOLD**.
6. **Gate ve pointer commit:** Admission bariyeri ve data lock aktifken #645 manifest/data contract ve bounded data-root gate'i çalışır; gate tek başına writer-freeze yerine geçmez. Herhangi bir data/read metadata değişimi, schema FAIL/UNKNOWN, lock kaybı veya yeni writer gözlemi pointer değişikliğini durdurur.
7. **Sonucu doğrula ve freeze'i kaldır:** `previous`/`current` pointer işlemi kesin tamamlanıp read-only hedef doğrulaması PASS ederse veya kesin red/no-op uzlaştırılırsa release owner kararıyla bariyer kaldırılır. `CommitUnknown` durumunda bariyer tutulur; installer lock koordinasyonunda yalnız read-only pointer uzlaştırması yapılır ve operatör kararı alınır. Otomatik rollback/retry yok.

## Timeout ve HOLD karar tablosu

| Gözlem | Karar | Gerekli davranış |
|---|---|---|
| Writer envanteri eksik; host/process, UID, launcher veya `YUVA_DIR` hedefi UNKNOWN | **HOLD** | Freeze/rollback başlatma; eksik sınıfı envantere ekle. |
| Admission kontrolü herhangi bir CLI/API/timer/legacy girişini kapsamıyor | **HOLD** | Panel offline veya PATH'ten çıkarma ile GO üretme. |
| In-flight mutation/drain deadline aşıldı; çağrı sonucu bilinmiyor | **UNKNOWN → HOLD** | Writer'ı zorla öldürme, otomatik retry veya pointer değişimi yok; owner uzlaştırsın. |
| `.kilit` hemen alınamadı, timeout oldu, path/inode/owner/mode doğrulanmadı | **HOLD** | Lock dosyasını unlink/replace etme; bariyer korunur. |
| Yalnız `.install.lock` alındı veya `YUVA_DIR/.kilit` boş gözlendi | **HOLD** | Bu kanıt data-root freeze/snapshot değildir. |
| #645 gate FAIL/UNKNOWN, dosya read sırasında değişti ya da lock kaybedildi | **HOLD** | `current` ve `previous` pointer'larını değiştirme. |
| Pointer replace/fsync sonucu belirsiz (`CommitUnknown`) | **HOLD** | Writer admission kapalı kalır; salt-okunur pointer uzlaştırması ve release owner kararı gerekir. |
| Tüm writer sınıfları kapalı/drain kanıtlı, lock/data gate PASS, pointer sonucu kesin | **GO adayı** | Yalnız release owner'ın ayrıca onayıyla; freeze kaldırma sonucu kaydedilir. |

## Gelecek disposable-fixture kabul matrisi

Bu runbook'un host'ta uygulanması veya kod içi lock entegrasyonu ayrı görevdir. Gerçek host yerine geçici `INSTALL_ROOT` ve `YUVA_DIR` kullanan fixture en az şu dalları sınamalıdır:

| Fixture | Beklenen sonuç | Pointer/data beklentisi |
|---|---|---|
| Canonical CLI writer `.kilit` içinde mutation yaparken rollback gate başlar | Gate aynı data lock'ı almadan scan/pointer yapamaz; writer tamamlanınca sıra kontrollü sürer | Bekleme boyunca pointer/data tutarlı; lock timeout olursa değişiklik yok |
| Freeze sırasında yeni CLI ve panel task çağrısı | Admission reddi; işlem kuyruğa gizlice alınmaz | Task ledger değişmez |
| Heartbeat, message, screen ve state writer'ı in-flight iken freeze | Her sınıf drain tamamlanmadan rollback gate/pointer aşamasına geçmez | İlgili sentineller yalnız kendi tamamlanmış write'ıyla değişir; yarım/karışık scan yok |
| Timer/legacy/dev/restore veya keyfi same-UID writer envanter dışında kalır | Fixture/operatör sözleşmesi UNKNOWN üretir | Pointer değişmez; HOLD |
| Lock symlink, yanlış owner/mode, inode/path swap, lock busy veya toplam deadline | Fail-closed timeout/HOLD | Lock dosyası unlink edilmez; pointer ve data byte'ları değişmez |
| #645 schema gate malformed/unknown data veya scan-time mutation görür | Gate reject/UNKNOWN | Current/previous pointer ve sentinel data byte'ları değişmez |
| Pointer replace/fsync fault sonrası `CommitUnknown` | Freeze açık kalır; yeni retry başlamaz | Reconciliation receipt olmadan writer admission geri açılmaz |

Fixture aynı-UID keyfi process'i OS seviyesinde engellediğini iddia etmemeli. Uncooperative writer için yalnız “model testinde reddedildi” kanıtı yeterli değildir; gerçek host'ta gerekli sahiplik/UID/admission tasarımı ve ayrı owner kabulü gerekir.

## Mevcut NO-GO sınırı

Bugünkü kanıtlar kanonik task CLI/panel kilitli writer akışını ve #645 bounded data-schema gate'ini gösteriyor. Bunlar global admission freeze, bütün data root writer'larının durduğunu, tek transaction snapshot'ını veya stale same-UID writer bulunmadığını kanıtlamaz. Bu nedenle host prosedürü/lock entegrasyonu tamamlanıp yukarıdaki fixture ve owner kabulü sağlanana kadar rollback kararı **HOLD / NO-GO** kalır.

## Kaynaklar

- [#645 actual data contract gate](release-rollback-actual-data-gate-645.md)
- [#663 writer eşzamanlılığı runbook'u](rollback-data-root-writer-freeze-663.md)
- [#552 task ledger single-writer haritası](task-ledger-single-writer-552.md)
- [#611 panel/CLI task writer çağrı grafiği](task-writer-call-graph-611.md)
- `release_installer.py:131-145,580-620` — installer lock ve rollback gate sırası
- `bin/yuva:211-272,2274-2305,2390-2410` — canonical CLI kilidi ve task writers
- `panel/server.py:1342-1414,1450-1510,1683-1705,1985-1996` — panel mutation/snapshot paths

Bu görev yalnız karar matrisi ve fixture kabul şartlarını tanımlar. Canlı rollback, freeze, process/FD taraması, kilit alma, installer/data-root değişikliği veya test çalıştırması yapılmadı.
