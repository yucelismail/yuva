# Yuva #622 — Dev/UI CLI görev yazımı uyumluluk kapısı

**Tarih:** 2026-10-23
**Durum:** Dev ve UI geliştirme CLI kopyalarında görev mutasyonları fail-closed kapatıldı; sentetik `YUVA_DIR` fixture'ı geçti.
**Sınır:** Yalnız `<YUVA_DATA_ROOT>-dev/bin/yuva` ve `<YUVA_DATA_ROOT>-ui-dev/bin/yuva` kaynakları değiştirildi. Canlı görev defteri, eski root kopyası ve restore-check kopyaları değiştirilmedi.

## Değişiklik

Her iki geliştirme CLI'ında `parse_args()` hemen sonrasına görev yazımı kapısı eklendi. `gorev ekle|ata|al|sonraki|teslim|ilk-kontrol|denetle|iptal` işlemleri, kimlik çözümleme veya herhangi bir veri okuma/yazma başlamadan `görev yazımı reddedildi: kanonik writer kullanın` hatasıyla çıkar. Salt-okunur `tahta` ve `liste` akışları bu kapının kapsamı dışındadır.

Kopyalar desteklenen writer/schema sürümüne sabitlenmediğinden kapı görev yazımını bu kaynaklardan tümüyle reddeder; fixture/ayrı veri kökü üzerinden de yazma açmaz. Görev mutasyonu için canonical `yuva-v2/bin/yuva` kullanılmalıdır.

## Sentetik fixture kanıtı

`tests/test_cli_copy_compatibility_fixture.py` güncellendi. Test, dev ve UI CLI kaynaklarını geçici dizine kopyalar; schema v99 içeren sentetik `gorevler.json` üzerinde `gorev al` çalıştırır ve her iki kopyanın kanonik-writer ret mesajıyla çıktığını, defterin başlangıç bayt hash'inin aynı kaldığını doğrular. Gerçek kopyalar fixture içinde çalıştırılmaz; `YUVA_DIR` her zaman geçicidir.

Canonical yol ayrı olarak sınandı:

- schema v1 ve sentetik worker kaydıyla `gorev al` başarılı oldu; kayıt `assigned` durumuna geçti ve schema v1 korundu.
- schema v99 defterde canonical CLI reddetti; görev defteri baytları değişmedi.

Eski root CLI guard'ı regresyonu ve restore-check kopyalarının tarihsel bozuk JSON fail-open bulgusu da fixture'da tekrar çalıştı. Komut: `python3 -m unittest tests.test_cli_copy_compatibility_fixture -v` — **5 test geçti**. `py_compile` ve her değişen CLI ağacında `git diff --check` de başarılı oldu.

## Kopya envanteri / kapsam

| Kopya | #622 durumu |
|---|---|
| `<YUVA_DATA_ROOT>/bin/yuva` (eski root) | #568 fail-closed task guard mevcut; bu görevde değişmedi. Fixture regresyonu geçti. |
| `<YUVA_DATA_ROOT>-dev/bin/yuva` | Bu görevde görev mutasyonları canonical writer uyumluluğu yokken fail-closed reddediliyor. |
| `<YUVA_DATA_ROOT>-ui-dev/bin/yuva` | Bu görevde görev mutasyonları canonical writer uyumluluğu yokken fail-closed reddediliyor. |
| `<REPO_ROOT>/bin/yuva` | Desteklenen canonical writer; v1 mutasyon başarılı, v99 reddi fixture ile ayrı doğrulandı. |
| `<YUVA_DATA_ROOT>-yedek/restore-check.T4hbP8/yuva/bin/yuva` | Kurtarma girdisi olarak bırakıldı; fixture kopyası bozuk JSON'da fail-open davranıyor. Ortak/live ledger writer'ı olarak kullanılmamalı. |
| `<YUVA_DATA_ROOT>-yedek/restore-check.XOeUcj/yuva/bin/yuva` | T4hbP8 ile aynı CLI kaynak hash'i; kurtarma girdisi olarak bırakıldı. Fixture kopyası bozuk JSON'da fail-open davranıyor. |

Restore-check yolları yedek inceleme materyalidir; bu görev onları yamamadı veya canlı veriye bağlamadı. Bu rapor yalnız görev defteri CLI mutasyon sınırını kapsar; aynı OS kullanıcısı altında keyfi modül importu, `kaydet()` doğrudan çağrısı veya diğer durum dosyası yazıcıları için genel OS writer izolasyonu iddiası değildir.
