# #535 — Legacy CLI görev geçişleri denetimi

**Tarih:** 2026-10-23
**Kapsam:** Dört `bin/yuva` kopyasının statik kaynak karşılaştırması ve #524 görev geçmişinin okunması.
**Sınır:** Çalışma verisi, CLI kopyaları ve servisler değiştirilmedi; görev geçişi, test, runtime, HTTP veya deployment çalıştırılmadı. #524 notları yalnızca inceleme girdisidir.

## Kaynak anlık görüntüsü

| Kopya | SHA-256 |
|---|---|
| `<YUVA_DATA_ROOT>/bin/yuva` | `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` |
| `<YUVA_DATA_ROOT>-dev/bin/yuva` | `11933ae13e8af951d6ab3aa9f0ccef1f8745df4120060a8ffc00ebb43db8fa5e` |
| `<YUVA_DATA_ROOT>-ui-dev/bin/yuva` | `6de3adda675aed0caf9e9cabde96fcd6c5ef44178dc3241bd203f5e55e00cddf` |
| `<REPO_ROOT>/bin/yuva` | `824a8d4379e45b9e40e7316d418fa3fad918388b11164dc11aab1c7c07ea0510` |

Her dört kopya da `YUVA_DIR` yoksa `Path.home()/yuva` kullanıp `gorevler.json` ve `.kilit` yollarını aynı veri kökünden türetiyor. Dolayısıyla aynı HOME/YUVA_DIR ile farklı kod kopyaları aynı görev dosyasına yazar.

## Kanıtlanan davranış farkları

### Eski `~/yuva/bin/yuva`

`gorev_kaydet` görev geçmişini ekleyip `kaydet(GOREV, gb)` çağırıyor; bu görev güncellemesi ortak `kilit()` kapsamına alınmıyor (`yuva/bin/yuva:640-646`). Kilit mesaj JSONL ekleme yolunda kullanılıyor (`:43-54`), görev JSON’u için değil.

- `ata` her kaydı doğrudan `assigned` yapıyor; önceki durum veya aktör/rol denetimi yok (`:664-675`).
- `al` önceki duruma veya mevcut assignee’ye bakmadan `assigned` yapıyor; assignee doluysa onu koruyor (`:678-689`).
- `teslim` önceki durumu ve assignee’yi kontrol etmeden `pending_verification` yazıyor (`:692-702`). Bu, `dropped` ve `verified` kayıtlarını tekrar açabilir.
- `iptal` her kaydı `dropped` yapıyor; terminal durum denetimi yok (`:725-732`).
- Komutlar `--from` metnini olay aktörü olarak kaydediyor; kimlik doğrulaması ya da rol denetimi bu görev geçişlerinde yok (`:858-874`).

### `yuva-dev` ve `yuva-ui-dev`

İkisi de görev okuma-değiştirme-yazma adımını `gorev_guncelle` içinde ortak `kilit_tut()` kapsamına alıyor (`yuva-dev/bin/yuva:1536-1542`; `yuva-ui-dev/bin/yuva:1746-1752`). `ata` yalnız `pending`, `assigned`, `pending_revision`; `al` yalnız `pending`/`pending_revision` ve boş ya da aynı assignee; `teslim` yalnız `assigned` ve mevcut assignee; `iptal` terminal olmayan durumlarla sınırlı (`yuva-dev:1566-1698`; `yuva-ui-dev:1786-2003`).

`yuva-ui-dev` ayrıca ilk kontrol kuyruğu ve reviewer rolü denetimlerini içeriyor (`:1886-1914`, `:1948-1979`). `yuva-dev` teslimi doğrudan denetim kuyruğuna alıyor; denetleme için v2’deki rol/inceleyen kontrolü bu kopyadaki `cmd_gorev_denetle` akışında yok (`:1651-1679`).

Bu iki kopyada da `ata` ve `iptal` için çağıranın rolü doğrulanmıyor. `--from` kullanıcı tarafından verilen bir kimlik iddiası olarak kalıyor; kilit ve geçiş kontrolleri çağıranı kriptografik olarak doğrulamıyor.

### `yuva-v2/bin/yuva`

Görev geçişleri de ortak kilit altında okunup yazılıyor (`yuva-v2/bin/yuva:1987-1993`). Atama, alma, teslim ve iptal kontrolleri `yuva-ui-dev` ile aynı fail-closed geçiş sınırlarını koruyor (`:2028-2096`, `:2186-2228`, `:2311-2326`). `denetle` denetçi rolünü ve yönlendirilmiş reviewer’ı kontrol ediyor (`:2273-2285`); ilk kontrol de görevli rolünü ve kimlik eşleşmesini kontrol ediyor (`:2243-2255`).

Ancak v2’de de `ata` ve `iptal` için rol/yetki kontrolü yok (`:2028-2061`, `:2311-2326`). `--from` CLI argümanıdır; bu kaynak tek başına gerçek çağıranı kanıtlamaz. Bu nedenle geçiş guard’ları eski kopyalara karşı koruma sağlar, fakat `--from` değerini taklit edebilen bir istemciye karşı kimlik doğrulaması sağlamaz.

## #524 olay dizisi

`yuva/gorevler.json`, #524 kaydı şu sıralamayı gösteriyor:

1. `yuva-basdenetcisi` görevi üstlendi.
2. `codex`, görevi `codex-kole1` kimliğine yeniden atadı.
3. `codex`, görevi iptal etti (`dropped`).
4. Eski assignee `yuva-basdenetcisi`, iptalden sonra teslim etti.
5. `codex-kole1` de teslim kaydı ekledi; ardından `codex` görevi yeniden iptal etti.

Adım 4, iptal edilmiş görevin yeniden açılabildiğini ve eski assignee’nin hâlâ işlem yapabildiğini gösteriyor. Adım 5, mevcut assignee ile teslimin dahi iptal terminal durumunu korumadığını gösteriyor. Bu olay sırası, eski `~/yuva/bin/yuva` içindeki koşulsuz `teslim` ve `iptal` davranışıyla tutarlıdır. JSON geçmişi, hangi fiziksel CLI kopyasının her komutu çalıştırdığını kaydetmediğinden, kopya atfı kaynak davranışıyla uyumluluk çıkarımıdır; olay kaydı tek başına çalıştırılabilir dosya hash’ini kanıtlamaz.

## Güvenli uyumluluk ve kullanım dışı bırakma kabul planı

1. **Tek kanonik görev yazıcısı belirle.** Dağıtımda kullanılan CLI yolu ve SHA-256 envanteri kaydedilsin; kabul edilen kopyanın kodu ve görev geçişleri aynı release kaynağından gelsin. Bugünkü kaynak karşılaştırmasında eski `~/yuva/bin/yuva` görev mutasyonları için uyumlu değildir.
2. **Eski kopyaları görev yazımından çıkar.** Kopyalar güncellenene kadar `gorev ekle/ata/al/teslim/denetle/iptal` mutasyonları reddedilsin veya doğrulanmış kanonik CLI’ye yönlendirilsin. Salt okunur `tahta`/liste kullanımı görev yazımıyla karıştırılmasın. Yalnız bir README uyarısı bu sınırı sağlamaz.
3. **Geçiş kabul senaryoları tanımla.** Kanonik CLI; iptal edilmiş/verified görevi teslim veya yeniden atamayla açmayı, başka assignee’nin görevi almasını/teslimini ve geçersiz durum geçişlerini reddetmeli; normal `pending → assigned → teslim` ve `pending_revision → al → teslim` akışlarını korumalı. Eski kopya mutasyonları ortak veride hiçbir değişiklik üretmemeli.
4. **Eşzamanlılık kabulü yap.** Kilitli kanonik yazıcı ile her uyumluluk yolu aynı `YUVA_DIR` üzerinde eşzamanlı tetiklendiğinde, durum ve geçmiş kaydı tek bir tutarlı geçiş göstermeli. Kilitsiz eski kopya bu kabulü geçemez; dosya hash’i değiştiyse inceleme tekrarlanmalı.
5. **Aktör/rol sınırını ayrı kapı olarak ele al.** `--from` değerinin sahte kimlik olarak kullanılmasını engelleyen doğrulanmış principal gereksinimi tanımlanmalı. Özellikle `ata` ve `iptal` için yetkili rol/policy açıkça belirlenip uygulanmadan, yalnız mevcut CLI argümanına dayanarak “actor/role güvenliği” kabul edilmemeli. Denetçi ve görevli kontrollerinin v2’deki olumlu örnekleri, `--from` kimlik doğrulaması yerine geçmez.
6. **Değişiklik öncesi/sonrası kanıtı tut.** Her kopyanın SHA-256’sı, gerçek çağırma yolu, etkin `YUVA_DIR`, eski kopya devre dışı bırakma sonucu ve yukarıdaki kabul senaryolarının kanıtı release kaydına eklenmeli. Bu belge hiçbir kopyayı güncellemez veya runtime durumunu doğruladığını iddia etmez.

## Sonuç

Legacy kök kopyası iptal/yeniden atama sonrasında stale assignee teslimini ve terminal görevin açılmasını engellemiyor; ayrıca görev yazımını ortak kilit dışında yapıyor. Dev, UI-dev ve v2 kaynaklarında durum/assignee guard’ları ile kilitli oku-değiştir-yaz var, ancak hepsi aynı veri köküne yazabildiği için eski kopya devre dışı bırakılmadan bu korumalar ortak veri için yeterli değil. Rol kontrolleri de kısmi; `--from` tek başına doğrulanmış aktör değildir. Bu rapor kaynak ve görev geçmişi incelemesidir; canlı çağrı/servis, dosya izinleri, test veya geçiş davranışı üzerinde doğrulama yapılmadı.
