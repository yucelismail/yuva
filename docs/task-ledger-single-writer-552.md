# #552 — Görev defteri yazıcı yolu kaynak haritası

**Sonuç:** Repo içindeki desteklenen panel/CLI akışında görev defterine yazan
tek uygulama `bin/yuva` görev core'udur. Panel `/api/gorev` işlemlerini bu
modüle yönlendirir; `panel/server.py` içinde görev defterine doğrudan yazan
başka bir çağrı bulunmadı. Canlı YUVA verisi, servis veya deployment
değiştirilmedi.

## Yazma ve okuma çağrı haritası

| Yol | Kaynak çağrısı | Deftere etkisi |
|---|---|---|
| CLI durum geçişleri | `cmd_gorev_ekle`, `ata`, `al`, `teslim`, `ilk-kontrol`, `denetle`, `iptal` → `gorev_guncelle()` → `gorev_yukle()` → `kaydet(GOREV, gb)` | Kanonik kilitli oku/değiştir/yaz yolu (`bin/yuva:2107-2113`; çağrılar `2142`, `2183`, `2217`, `2350`, `2395`, `2434`, `2456`). |
| CLI FIFO claim | `cmd_gorev_sonraki()` → `kilit_tut()` → `gorev_yukle()` → seçim/atama → `kaydet(GOREV, gb)` | Aynı CLI modülünde özel atomik seç-ve-yaz işlemi (`bin/yuva:2223-2305`). Kilit seçim ve atamanın tamamını kapsar. |
| Panel görev POST'u | `/api/gorev` → `gorev_calistir()` → auth/policy kontrolü → `SourceFileLoader(CLI)` → `core.run_task_operation()` → ilgili CLI `cmd_gorev_*` | Ayrı panel yazıcısı yok; aynı CLI görev core'una yönlenir (`panel/server.py:1362-1444`, route `1467`). |
| Panel GET snapshot | `do_GET()` → `veri()` → `gorev_oku()` | Salt okunur. `veri()` durum ve görev snapshot'ını aynı `KILIT` + `dosya_kilidi()` kapsamında okur (`panel/server.py:563-577`, `1532-1539`). |
| Backup doğrulama/restore-check | `backup_verify.py` görev JSON'unu doğrular; restore-check yalnız yeni, özel scratch hedefe açar | Aktif `YUVA_DIR` yazıcısı değildir; scratch hedefin aktif kök dışında olması zorunludur (`backup_verify.py:400-455`). |
| Testler | Panel/CLI testleri görev fixture'larını geçici `YUVA_DIR` altında oluşturur | Üretim görev defteri yazılmaz. |

`bin/yuva:kaydet()` veri kökü JSON'ları için şema kontrolü uygular, aynı
dizinde geçici dosyaya yazar, `fsync` ve `os.replace` kullanır. Normal görev
geçişleri `gorev_guncelle()` içinden geçer. `sonraki` bunun tek özel
işlemidir; kendi içinde ayrı kilit veya dosya yordamı kullanmaz, yine aynı
`kilit_tut()` ve `kaydet()` primitiflerini kullanır. Kaynakta bağımsız bir
Panel JSON writer'ı veya ikinci bir repo içi görev saklama katmanı yoktur.

## Eşzamanlılık ve tutarlılık

- CLI işlemleri aynı `KOK/.kilit` üzerinde süreçler arası `flock` kullanır.
- Panel POST köprüsü aynı süreçte `_TASK_CORE_LOCK` ile çağrı/çıktı karışmasını
  önler; görev değişikliği yine canonical CLI'nin `.kilit` kilidine girer.
- Panel snapshot'ı aynı `.kilit` ile görev commit'i arasında yarışmaz.
- `cmd_gorev_sonraki()` seçim, assignee ve `assigned` geçişini tek kilitli
  bölümde yazar; paralel claim aynı görevi iki çalışana atayamaz.
- Görev JSON commit'i ile ardından gönderilen mesaj bildirimi tek transaction
  değildir. JSON commit başarılı olup bildirim append'i hata verirse görev
  geçmişi güncel kalır, ancak mesaj bildirimi eksik olabilir. Bu, görev
  defterinde lost-update yarışı değildir.

## Sınır ve kalan risk

Bu kanıt repo içindeki desteklenen kod yoluna aittir; aynı UID altındaki bütün
çalıştırılabilir kopyaları teknik olarak tek yazıcıya zorladığını göstermez.
`<YUVA_DATA_ROOT>/bin/yuva` eski kopyası kaynakta `gorev_kaydet()` ile
`kaydet(GOREV, ...)` çağırır ve görev JSON güncellemesinde ortak kilit
kullanmaz. #540 bu kopyayı desteklenen PATH/release kullanımından
decommission etmiş, ancak aynı UID ile doğrudan çalıştırılmasını engellememiştir.
`yuva-dev` ve `yuva-ui-dev` kopyaları kilitli `gorev_guncelle()` kullanır;
fakat ayrı kopyalar olmaları ve farklı sürümde bulunmaları onları desteklenen
giriş yapmaz. Eski kök kopya elle çalıştırılırsa canonical writer ile yarışıp
lost update üretebilir veya geçiş guard'larını atlayabilir.

Bu nedenle iddia **desteklenen panel/current CLI yolu için tek canonical
writer** ile sınırlıdır. Same-UID doğrudan eski kopya çalıştırmasını
engellemek host UID/izin veya dosyanın kaldırılması gibi ayrı bir operasyonel
sınır gerektirir; bu görev o sınırı değiştirmedi.

## Fixture doğrulaması

Çalıştırılan komut:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_task_principal_gate tests.test_code_data_roots tests.test_data_schema_compat -v
```

Sonuç: **15 test geçti.** Fixture kapsamı; Panel API'nin CLI core'a yazması,
principal/policy geçitleri, auth-off aktör etiketinin `local_unverified`
olması, auth-on doğrudan CLI reddi, kod/veri kökü ayrımı ve schema reader/writer
uyumudur. Testler geçici YUVA_DIR kullanır; canlı panel veya servis başlatılmaz.
