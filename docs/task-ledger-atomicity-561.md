# Yuva #561 — Görev defteri atomikliği ve fixture kabul kaydı

**Durum:** Kod düzeltmesi ve geçici-fixture doğrulaması. Canlı `<YUVA_DATA_ROOT>`
verisi, panel servisi veya deployment kullanılmadı.

## Sonuç

Desteklenen v2 CLI/panel yazıcı yolu aynı süreçler-arası `.kilit` altında
görev snapshot'ını oku/değiştir/yazar; görev JSON'u aynı dizindeki benzersiz
geçici dosyaya yazılır, dosya `fsync` edilir, `os.replace` ile yayımlanır ve
üst dizin `fsync` edilir. Panel `/api/gorev` ayrı bir JSON yazarı değildir:
isteği canonical CLI task core'una yönlendirir; `_TASK_CORE_LOCK` panel
sürecinde çağrı/çıktı karışmasını engeller, ortak `.kilit` ise CLI ve panel
süreçlerinin görev snapshot'ı üzerindeki yarışını serileştirir.

Kaynak incelemesinde iki fail-closed boşluk kapatıldı:

1. Mevcut ama boş/whitespace-only `gorevler.json` CLI ve panel reader'ında
   boş defter sayılıyordu. Yeni bir defter yalnız dosya **yokken** varsayılan
   oluşturur; mevcut boş görev dosyası `VeriHatasi` / `DurumHatasi` verir ve
   mutation'a girmez. Kısmi/bozuk JSON zaten parse hatasıydı; dosya korunur.
2. Tekil pozitif tamsayı görev ID kontrolü `cmd_gorev_sonraki()` ile sınırlıydı.
   CLI `gorev_yukle()` ve panel `gorev_oku()` artık tüm görev kayıtlarında
   canonical pozitif tamsayı ve benzersizlik kontrolü yapar. `bool`, string,
   sıfır/negatif veya yinelenen ID taşıyan defter fail-closed okunur; ilk
   eşleşen kayıt sessizce mutate edilmez veya snapshot'ta normalleştirilmez.

Bu değişiklik mevcut görev semantiğini, snapshot şemasını veya task durumlarını
değiştirmez. `yukle()`/`oku()` için boş varsayılan davranışı diğer dosyalarda
korunur; görev defteri bu davranışı açıkça kapatır.

## İşlem sıralaması ve yarış sonucu

### CLI mutation

```text
principal/rol guard
  → kilit_tut() / aynı KOK/.kilit inode'u üzerinde flock
  → gorev_yukle() [JSON, şema, task ID tekilliği]
  → durum geçişi / geçmiş ekleme (RAM snapshot)
  → kaydet() [aynı dizinde temp → serialize → file fsync → os.replace → dir fsync]
  → kilidi bırak
  → JSONL bildirimi append
```

Panel `/api/gorev` önce kaynak, gövde ve etkinse HMAC/policy kontrolü yapar;
sonra CLI core'un `run_task_operation()` çağrılır. CLI'nin task mutation'ı
aynı süreçler-arası `.kilit` yoluna girer. `cmd_gorev_sonraki()` ayrı bir
`gorev_guncelle()` wrapper'ı kullanmaz ama seçim + assignee + `assigned`
snapshot'ı tek `.kilit` kapsamındadır. Aynı görevi iki worker claim ederse ilk
commit kazanır; ikinci güncel `assigned` durumunu görüp reddedilir. Farklı
görevlerde eşzamanlı CLI/panel yazımları eski snapshot'ı birbirinin üzerine
yazmaz.

Görev commit'i ile JSONL bildirimi atomik değildir. JSON commit başarılı olup
sonraki mesaj append'i başarısız olursa görev değişikliği korunur, bildirim
eksik kalabilir; bildirim yokluğu task mutation'ı tekrar etmek için kanıt
değildir.

### Hata/çökme semantiği

| Failure noktası | Canonical görev JSON'u | Güvenli yorum |
|---|---|---|
| JSON yazımı/serialize veya `os.replace` öncesi hata | Eski snapshot değişmeden kalır; temp dosya normal exception yolunda temizlenir. | Mutation yok; güvenli retry kararı yalnız bu eski snapshot doğrulanınca verilir. |
| Süreç temp write sonrası, replace öncesi çöker | Eski hedef dosya kalır; orphan temp kalabilir ama okuyucu onu task defteri saymaz. | Kısmi hedef JSON'a yayımlanmaz; orphan temizliği ayrı işletim kararıdır. |
| `os.replace` tamamlanır, üst dizin `fsync` hata verir | Yeni tam JSON görünür olabilir; crash sonrası dayanıklılık doğrulanamaz. `kaydet()` hata yükseltir. | `commit_unknown`: eskiye rollback veya kör tekrar yok; kanonik snapshot'ı okuyup uzlaştır. |
| Sonradan mevcut hedef boş/kısmi/bozuk bulunur | Reader varsayılana düşmez ve mevcut bytes'ı değiştirmez. | Hata/operatör kurtarması; yeni görev ekleyip bozuk defterin üstüne yazma yok. |
| Duplicate/noncanonical task ID | Reader hata verir; mutation callback'i/JSON rewrite çalışmaz. | Çakışmayı elle/kurtarma akışında çöz; “ilk ID kazanır” yapılmaz. |

`os.replace` öncesi ve directory fsync sonrası hata fixture'larda enjekte edildi;
bu gerçek power-loss/filesystem emulation değildir. “Tam exactly-once” mutation
makbuzu mevcut değildir: HTTP/CLI yanıtı kaybolduğunda görev snapshot'ı ile
bildirim ayrıdır ve commit sonrası belirsizlik yeni operation açmadan
uzlaştırılmalıdır (#437/#452).

## Fixture kanıtı

Yeni `tests/test_task_ledger_integrity.py` yalnız `TemporaryDirectory` altında:

- eksik task dosyasının boş defter olarak okunmasını; var olan boş, whitespace
  veya kısmi JSON'un CLI/panel tarafından reddedilmesini ve bytes'ın
  değişmemesini;
- yinelenen, `bool`, string ve pozitif olmayan ID'lerin iki reader'da da
  reddedilmesini ve mutation öncesi dosyanın korunmasını;
- `os.replace` öncesi hata halinde eski tam snapshot'ın ve temp temizliğinin
  korunmasını;
- directory `fsync` hatasında `commit_unknown` semantiğiyle uyumlu hata ve
  yeni, tam parse edilebilir snapshot görünmesini;
- farklı görevlerde panel API ve CLI claim'lerinin eşzamanlı yazıp ikisinin de
  sonucunu aynı defterde korumasını;
- aynı görevde iki ayrı CLI process claim'inden yalnız birinin kazanmasını
  sınar.

Çalıştırılan doğrulamalar:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_task_ledger_integrity -v
Ran 6 tests — OK

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_data_schema_compat tests.test_task_principal_gate tests.test_code_data_roots -v
Ran 15 tests — OK
```

Her iki komut da geçici fixture'ları kullanır. Servis, auth state veya canlı
Yuva veri kökü okunmadı/yazılmadı.

## Kalan sınır

Bu kanıt desteklenen güncel v2 CLI/panel kaynak yoluna aittir. #552'de
belgelendiği üzere eski `<YUVA_DATA_ROOT>/bin/yuva` kopyası aynı veri köküne
doğrudan çalıştırılırsa ortak lock protokolünü atlayabilir; fixture testi bu
legacy writer'ı ortadan kaldırmaz. Tek canonical release/writer ve
`YUVA_DIR` ayrımı host/release kabulünde ayrıca doğrulanmalıdır.

Dayanaklar: `bin/yuva` (`yukle`, `gorev_yukle`, `gorev_guncelle`, `kaydet`,
`cmd_gorev_sonraki`); `panel/server.py` (`oku`, `gorev_oku`, `gorev_calistir`,
`veri`); `docs/task-ledger-single-writer-552.md`;
`docs/task-mutation-failure-matrix-452.md`;
`docs/task-mutation-idempotency-outbox-design-437.md`.
