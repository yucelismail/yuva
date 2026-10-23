# Yuva #663 — Rollback data-root writer eşzamanlılığı runbook'u

**Karar:** #645 actual-data gate'in mevcut hali tek başına eşzamanlı snapshot veya
writer-free rollback garantisi vermez. Kontrollü ve kanıtlanabilir bir
writer-freeze yoksa rollback **HOLD / NO-GO**. Manifest eşitliği, başarılı
bounded scan veya boş kilit örneklemesi bu kararı değiştirmez.

Bu belge karar sözleşmesidir. Servis durdurmadım, süreç/FD sorgulamadım, canlı
`YUVA_DIR` taramadım ve herhangi bir kilit almadım.

## Kaynakta görülen kilit sınırları

| Yol | Kilit / kapsam | Rollback açısından anlamı |
|---|---|---|
| Kanonik CLI task mutation (`gorev_guncelle`, `sonraki`) | `YUVA_DIR/.kilit` üzerinde güvenli `flock`; CLI bekleme sınırı varsayılan 10 saniye. Panel task dispatch'i de aynı CLI core'u çağırır. | Yalnız bu kilidi alan, aynı data root'a yöneltilmiş writer'ları serileştirir. Panelin `_TASK_CORE_LOCK`'u bunun yerine geçmez. |
| Installer `rollback_release()` | `INSTALL_ROOT/.install.lock` üzerinde blocking `flock`; actual data root doğrulaması ve `current`/`previous` pointer yazımları bu lock kapsamındadır. | Installer eşzamanlılıklarını/pointer işlemlerini sıralar; YUVA writer'larını durdurmaz. |
| #645 `_validate_actual_data_root()` | Bounded read-only dosya okumaları; her dosyanın kendi okuma sırasında değişmediği kontrol edilir. | Dosyalar arası tek snapshot sağlamaz ve `.kilit` almaz. Writer scan sırasında farklı dosyalara yazabilir. |
| Tarihsel/dev/UI/restore kopyaları, importer, keyfi aynı-UID writer | Tümünün aynı lock protokolüne uyduğuna dair kanıt yok. Bazı kopyalar aynı data root'a doğrudan yazabilir. | Kanonik `.kilit` örneklemesi bu writer'ları dışlamaz. Evrensel writer exclusivity kanıtlanmış değildir. |

Kaynak dayanakları: [#645 gate](release-rollback-actual-data-gate-645.md),
[#611 writer çağrı grafiği](task-writer-call-graph-611.md),
[#552 tek writer envanteri](task-ledger-single-writer-552.md),
`release_installer.py::_install_lock`, `rollback_release`,
`_validate_actual_data_root`; `bin/yuva::kilit_tut`, `gorev_guncelle`.

## Operatör karar akışı

1. **Freeze kapsamını belirle.** Rollback penceresinde data root'a yazabilecek
   bütün girişleri say: panel/API, kanonik CLI, timer/daemon/worker, backup veya
   restore araçları, legacy/dev/UI/restore-check kopyaları ve elle başlatılmış
   aynı-UID süreçler. Bu envanter eksikse veya bir writer'ın kullanacağı yol
   bilinmiyorsa **HOLD**.
2. **Writer admission'ı kapat ve drain et.** Uygulanmış, owner tarafından
   onaylanmış host prosedürü her writer'ın yeni mutation başlatmasını
   engellemeli; aktif mutation'lar normal tamamlanmalı. Sadece `ps`, heartbeat,
   panel offline göstergesi veya `flock -n` anlık başarısı drain/freeze kanıtı
   değildir. Stale writer yalnız PID listesiyle dışlanamaz; writer kaynağı,
   data-root hedefi ve sahiplik sınırı bilinmiyorsa **UNKNOWN → HOLD**.
3. **Kilit kimliğini doğrula.** Kanonik writer kullanan ortamda `.kilit`, tam
   olarak `YUVA_DIR/.kilit` inode'u olmalı; güvenli normal dosya/owner/mode/link
   koşulları CLI ile aynı olmalı. Kilit yoksa veya symlink/başka inode/izin
   uyumsuzluğu varsa **HOLD**. Kilit dosyasını unlink/replace ederek stale
   kilit “temizleme”; `flock` kernel tarafından FD kapanınca bırakılır ve path'i
   değiştirmek farklı inode üzerinde eşzamanlı kilitler doğurabilir.
4. **Timeout'u fail-closed ele al.** Writer drain veya kilit koordinasyonu
   onaylı timeout içinde tamamlanmazsa rollback komutunu başlatma. CLI'nin
   10 saniyelik kilit timeout'u rollback gate için snapshot garantisi değildir.
   Timeout sonrası writer'ın devam edip etmediği belirsizse **UNKNOWN → HOLD**;
   otomatik retry, pointer değişimi veya force-unlock yok.
5. **Gate ve pointer işlemini freeze penceresinde çalıştır.** #645'in bounded
   data scan'i manifest/data acceptance kapısı olarak kalır; freeze süresince
   YUVA writer admission kapalı tutulur. Gate reject/UNKNOWN, okuma değişikliği,
   kilit kaybı veya herhangi bir writer aktivitesi görülürse `current` ve
   `previous`'ı değiştirme. Pointer replace/fsync sonucu belirsizse installer'ın
   commit-unknown kararını koru; yeni rollback denemesi yapmadan önce current ve
   previous pointer'larını aynı INSTALL lock koordinasyonuyla read-only
   uzlaştır ve operatör kararı al.
6. **Freeze'i ancak sonuç belli olunca kaldır.** Gate/pointer makbuzu kesin
   başarılı ve hedef pointer doğrulanmışsa, ya da kesin no-op/red sonucu kayıt
   altına alındıysa writer'ları yeniden aç. UNKNOWN/CommitUnknown durumunda
   writer'ları açma; önce pointer ve data-root writer durumu uzlaştırılsın.

## Uygulama kararı / gerekli kod kapısı

Bugünkü rollback kodu yalnız installer lock'ını alıyor. Bu yüzden prosedürün
tercih edilen teknik çözümü, release gate'e data-root writer kilidini kod içinde
eklemektir:

1. **Tek kilit sırası:** `INSTALL_ROOT/.install.lock` → doğrulanmış
   `YUVA_DIR/.kilit`; aynı süreç iki kilidi tutarken scan ve iki pointer sonucu
   kesinleşene kadar kilitleri bırakmaz. Gelecekteki hiçbir writer ters sırada
   (data lock → install lock) beklememelidir.
2. **Ortak protokol:** Gate, `kilit_tut()` ile aynı path, no-follow, owner/mode,
   inode recheck ve kernel `flock` sözleşmesini kullanır. Symlink, path/inode
   değişimi veya desteklenmeyen lock biçimi fail-closed reddedilir.
3. **Sınırlı bekleme:** İki kilit için tanımlı toplam deadline uygulanır. Timeout
   pointer/data değişikliği olmadan `HOLD/LOCK_BUSY` sonucu verir; bekleme
   süresini sınırsız uzatma veya lock dosyasını silme yoktur.
4. **Writer evreni:** Bu kilit yalnız protokole uyan writer'ları sıralar. Eski,
   restore veya keyfi aynı-UID writer'ları aynı `YUVA_DIR`'e erişebilir durumda
   ise kod içi flock da tek başına yeterli değildir; admission freeze veya OS
   sahiplik sınırı gerekir. Release/restore kopyaları desteklenen writer olarak
   pinlenip uyumluluk fixture'ı geçmeden GO verilmez.
5. **Acceptance:** Test, gerçek host yerine temporary INSTALL_ROOT/YUVA_DIR'de
   bir canonical writer'ın lock-held mutation'ı ile rollback scan yarışını
   kontrollü sırada kurmalı; gate lock'ı tutarken mutation'ın beklediğini,
   timeout'un pointer'ları/data'yı değiştirmediğini, lock release sonrası
   retry'ın yalnız yeni operatör kararıyla başladığını kanıtlamalıdır. Bu görevde
   kod veya fixture eklenmedi.

## Karar tablosu

| Gözlem | Karar |
|---|---|
| Bütün writer girişleri envanterli, admission kapalı, in-flight işler drain edilmiş, hedef release/data acceptance PASS ve pointer commit kesin | **GO adayı**; release owner ayrıca onaylar |
| Writer envanteri eksik; eski/dev/restore writer ihtimali var; stale process veya aynı-UID erişimi belirsiz | **UNKNOWN / HOLD** |
| Yalnız installer lock alınmış veya `.kilit` bir anda boş gözlenmiş | **HOLD**; shared snapshot kanıtı değil |
| `.kilit` timeout, malformed/symlink/inode değişimi veya writer freeze doğrulaması başarısız | **HOLD**; lock temizleme/force yok |
| Gate FAIL/UNKNOWN, dosya read sırasında değişmiş veya pointer `CommitUnknown` | **HOLD**; pointer/data değişikliği ve yeni mutation yok, salt-okunur uzlaştırma + owner kararı |
| Data schema PASS ama panel/legacy writer davranışı, screen producer veya backup/restore uyumu belirsiz | **HOLD**; schema PASS tek başına rollback GO değildir |

Bu runbook şu anki gate için otomatik GO üretmez. Kod içi ortak data-root lock
ve tam writer admission sınırı eklenip disposable acceptance fixture'ı
geçilene kadar güvenli varsayılan **HOLD** kalır.
