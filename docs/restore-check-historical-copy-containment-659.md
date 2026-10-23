# #659 — Tarihsel restore-check CLI kopyaları için güvenli kullanım kapısı

**Tarih:** 2026-10-23
**Durum:** Uygulanmamış containment tasarımı ve kabul ölçütü. Tarihsel ağaçlar,
backup/tar/sidecar, canlı `YUVA_DIR`, servis, shell ayarları veya permission'lar
değiştirilmedi; bu belgede fixture/test çalıştırılmadı.

## Karar ve geçici kullanım kuralı

`yuva-yedek/restore-check.T4hbP8/yuva/bin/yuva` ve
`yuva-yedek/restore-check.XOeUcj/yuva/bin/yuva` tarihsel inceleme girdisidir.
Önceki envanter her iki CLI için de aynı SHA-256'yı ve `0775` modu kaydetti;
bu kodun güvenli olduğunu veya iki yolun bugün aynı byte'larda bulunduğunu
kanıtlamaz. #638 revize notu tarihsel kopyalarda fail-closed guard olmadığını
ve bunların doğrudan çalıştırılmaması gerektiğini belirtir.

**Containment kurulup kabul edilene kadar iki kopyayı çalıştırmayın, import
etmeyin ve panellerini başlatmayın.** `gorev`, `yaz`, ilk-kontrol veya benzeri
mutasyon komutlarını bu yollara yönlendirmeyin. Restore-check ile yeni
oluşturulmuş scratch ağacında sabit stub varsa, o ağaçtaki CLI yalnız her
çağrıyı exit 2 ile reddeder; bu, tarihsel kaynak ağaçlarını veya backup'ın
kendisini güvenli/çalıştırılabilir yapmaz.

## Seçenekler ve gerçek sınırları

| Seçenek | Ne sağlar | Ne sağlamaz / kabul notu |
|---|---|---|
| PATH, shell alias ve launcher'dan tarihsel yolları çıkarmak | Yanlışlıkla kısa komutla çağırma olasılığını azaltır. Desteklenen tek launcher canonical, onaylı release ve ayrı `YUVA_DIR`'e sabitlenebilir. | Doğrudan absolute path, `python3 /path/bin/yuva`, `importlib`/`SourceFileLoader` veya kopya paneli çağrısını engellemez. Tek başına security boundary değildir. |
| Operatör prosedürü: “çalıştırma/import etme” ve yalnız statik inceleme | Hemen uygulanabilecek davranış kuralıdır; #638'in mevcut “kullanma” kararını açıklar. | İnsan hatası veya başka otomasyon çağrısını teknik olarak engellemez; işletim sistemi izolasyonu iddia edilemez. |
| Kopyaları mevcut konumda `chmod`/execute bit kaldırma | Basit yanlışlıkla shell yürütmesini azaltabilir. | `0775` ağaçta dosya sahibi/aynı yetkili actor modu geri verebilir; Python ile dosya okunup yorumlanabilir; directory write izinleri ve symlink/başka entrypoint'ler ayrıca kalır. Metadata değişikliği tarihsel delil niteliğini de etkiler. Operatör onayı ve öncesi/sonrası envanter olmadan uygulamayın. |
| Salt-okunur arşiv/mount veya root-owned, yazılamaz quarantine | Yetkisiz UID'lerin kaynak byte'larını değiştirmesini ve normal çalışma yolundan erişimi güçlü biçimde azaltır. Kaynak kopyalar korunup çalışma kopyasından ayrılabilir. | Aynı ayrıcalıklı/root aktör veya salt-okunur mount'u kaldırabilen yönetici sınırı aşabilir. Okuma ve Python import hâlâ mümkün olabilir. Arşiv/tar/sidecar'a dönüşüm ayrıca içerik değişikliğidir; açık custody kararı gerektirir. |
| Ayrı OS UID ile offline inceleme, boş/ayrı scratch data root | Yanlışlıkla gerçek `YUVA_DIR`'e yazma etkisini ayırır. Aynı UID varsayımını kaldırır. | Aynı UID altında çalıştırmayı güvenli yapmaz. Kopyalara erişim veya ayrı UID'nin canlı root'a yazma hakkı varsa yalıtım yoktur. Archive dosyalarını değiştirmeyi tek başına engellemez. |
| Path/hash-allowlist launcher veya invocation guard | Yalnız allowlist içindeki executable/release kimliğiyle başlatmayı reddedebilir; audit izi sağlayabilir. | Çalışan eski CLI'nin içinde kolayca bypass edilebilir guard veya sadece launcher kullanımı absolute path, import ve panel girişlerini kapatmaz. Gerçek enforcement için bütün çağrı yolları OS/owner sınırıyla kapatılmalı. |

### Önerilen containment hedefi

Önce tarihsel kopyaları aynı path'te değiştirmeden karantinada bırakın ve
launcher/alias/otomasyon girişlerini kullanımdan çıkarın. İnceleme gerekiyorsa
verified backup üzerinden **yeni** private scratch üretin; scratch içindeki
stub'lı restore-check ağacını çalıştırılabilir release olarak kullanmayın.
Görev/veri incelemesini canonical onaylı araçla veya ayrı, disposable UID ve
boş sentetik `YUVA_DIR` altında tasarlanmış read-only inceleme aracıyla yapın.

Teknik olarak çalıştırmayı engellemek istenirse, operatör ayrıca onayladıktan
sonra kopyaların üst dizinini sadece inceleme UID'sinin okuyabildiği,
çalıştırıcı/veri yazıcısı UID'sinin erişemediği root-owned/read-only alana
taşıma veya read-only mount seçeneğini değerlendirir. Bu adım kopya yolunu,
owner, mode ve custody kaydını değiştirir; **bu görevde uygulanmamıştır**.
Same-UID `chmod` tek başına containment kabul edilmez. Kopyaların hash, mode,
owner ve path kimliği değişirse yeni durum ayrıca kaydedilip onaylanmalıdır.

## Scratch stub'ın sınırı

`backup_verify.restore_check()` archive doğrulamasından sonra yalnız yeni
scratch destination içindeki `bin/yuva`'yı sabit exit-2 stub'a çevirir.
Bu koruma:

- archive içindeki byte'ları, sidecar'ı veya iki tarihsel restore-check
  ağacını değiştirmez;
- mevcut tarihsel path'lere uygulanmaz ve o kopyaların korunmuş olduğunu
  kanıtlamaz;
- panel kopyasını, `python3` ile kaynak dosyası çalıştırmayı veya başka
  kopyadaki helper/import girişlerini otomatik olarak kapatmaz;
- scratch'ı deploy edilebilir veya normal CLI komutlarını çalıştırabilir bir
  restore yapmaz; `--help` dahil CLI invocation'ları reddedilir;
- canlı ledger'ın veya çalışan process'in değişmezliğini tek başına
  kanıtlamaz.

Restore-check çıktısındaki `restore_cli_policy: task_mutations_disabled`
yalnız o scratch sonucuna aittir. `not_present`, scratch'ta CLI
bulunmadığını belirtir; tarihsel ağaç hakkında güvenlik sonucu değildir.

## Gerçek kopyalara yazmadan kabul ölçütü

Kabul, gerçek tarihsel executable'ı veya paneli çalıştırmayı gerektirmez.
Tasarım/containment adımı uygulandıktan sonra denetçi şu kanıtları yalnız
read-only toplar:

1. **Korunan kaynak kimliği:** iki tarihsel path, gerçek path çözümü,
   `lstat` türü, owner/mode, byte SHA-256 ve parent izinleri kayıt altına
   alınır. Herhangi bir quarantine/owner/mode değişimi açıkça işaretlenir;
   #627'deki tarihsel hash otomatik olarak güncel hash varsayılmaz.
2. **Tüm çağrı yüzeyleri:** PATH/alias/launcher, absolute path, doğrudan
   Python script/import, eş ağaçtaki panel ve bilinen otomasyon girişleri
   listelenir. Sadece PATH'ten kaldırma seçildiyse kabul raporu bunun
   kolaylık önlemi olduğunu ve direct-path bypass'ın açık kaldığını söyler.
3. **Mirror negative test:** orijinal byte'lardan yalnız geçici bir mirror
   oluşturulur; sentetik, bozuk task ledger ve ayrı temporary `YUVA_DIR`
   kullanılır. Test doğrudan CLI, Python/import veya launcher için tasarlanan
   containment'i mirror üzerinde dener. Mutasyon çağrısı reddedilmeli;
   sentinel ledger'ın byte hash'i öncesi/sonrası aynı kalmalı; bozuk JSON
   boş deftere dönüştürülmemeli. Test mirror silinince test sonrası gerçek
   path'lerin hash/mode/owner envanteri öncekiyle aynı kalmalıdır.
4. **OS boundary:** UID/parent mode/read-only mount seçildiyse authorised
   inspection UID'nin okuma izni ve writer/runtime UID'nin write/execute
   reddi sentetik mirror üzerinde sınanır. Aynı UID/root bypass'ı ve yönetici
   mount değiştirme yetkisi açıkça belgelenir; bunlar kontrol dışıysa OS-level
   garanti iddia edilmez.
5. **Canlı veri değişmezliği:** test argümanlarında aktif `YUVA_DIR`, backup,
   sidecar veya görev ledger path'i bulunmadığı doğrulanır. Üretim root'una
   dokunmama bu tasarımın kapsam şartıdır; test raporu yalnız mirror'daki
   sentinel hash'i ile gerçek historical kopyaların read-only pre/post
   hash'lerini karşılaştırır.
6. **İşletim kararı:** prosedür sahibi, izin/owner değişikliği ve quarantine
   konumunu onaylar; başarısız veya eksik kabul dalında tarihsel kopyalar
   “güvenli” ilan edilmez ve çalıştırma yasağı sürer.

Bu ölçütler executable davranışını gerçek kopyalarda kanıtlamaz. Güvence,
read-only kimlik envanteri + mirror testi + seçilen OS/launcher kontrolünün
kapsamını sınırlar. Tüm bypass yüzeyleri teknik olarak kapatılmadıysa sonuç
“contained” değil, “operatör kullanım yasağı uygulanıyor” olarak kaydedilir.

## İlgili kayıtlar

- [#638 kapsam/revizyon notu](restore-check-cli-guard-revision-638.md)
- [#638 scratch task-write guard raporu](restore-check-cli-task-write-guard-638.md)
- [#627 yerel görev writer envanteri](task-writer-local-copy-inventory-627.md)
- [#544 verify/restore-check sözleşmesi](backup-verify-restore-check-544.md)
- [#624 bağımsız backup pin custody prosedürü](backup-digest-pin-operator-custody-624.md)
