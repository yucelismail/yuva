# Eski CLI görev yazımı için fail-closed koruma (#568)

**Tarih:** 2026-10-23
**Kapsam:** PATH dışı Yuva CLI ve eski panel sunucusu kopyalarının görev yazımlarını reddetmesi.
**Sınır:** Kanonik kurulum işaretçisi, çalışan servis ve canlı görev verisi değiştirilmedi. Fixture testleri yalnız geçici `YUVA_DIR` kullandı. Eski panel sunucusu kaynak dosyası, bypass yolu kapatılacak şekilde değiştirildi.

## CLI envanteri

`which -a yuva` sırası:

1. `<HOME>/.local/bin/yuva` → `<REPO_ROOT>/bin/yuva` (PATH'teki desteklenen giriş noktası).
2. `<YUVA_DATA_ROOT>/bin/yuva` (PATH'te değil; eski kopya, görev mutasyonları fail-closed yapıldı).

PATH dışı dosya taramasında ayrıca `<YUVA_DATA_ROOT>-dev/bin/yuva`, `<YUVA_DATA_ROOT>-ui-dev/bin/yuva` ve iki `yuva-yedek/restore-check.*` kopyası bulundu. Dev kopyalarında ortak kilit yardımcısı mevcut; yedek/restore-check kopyaları kurtarma fixture'larıdır. Bunlar değiştirilmedi.

SHA-256 envanteri (değişiklik sonrası):

| Kopya | SHA-256 |
|---|---|
| `yuva/bin/yuva` (eski kopya) | `7ecfe14ce88abff09e424572f8e27fa2d7e06a8785419ec5541743ea9ccd82d1` |
| `yuva/panel/server.py` (eski panel sunucusu; koruma sonrası) | `f3c10cbad99f0b4318c1990733115a2f71f39cba77172476b1b3301f18ef08b4` |
| `yuva-dev/bin/yuva` | `11933ae13e8af951d6ab3aa9f0ccef1f8745df4120060a8ffc00ebb43db8fa5e` |
| `yuva-ui-dev/bin/yuva` | `6de3adda675aed0caf9e9cabde96fcd6c5ef44178dc3241bd203f5e55e00cddf` |
| `yuva-v2/bin/yuva` | `1023b3cc8c9cd997cc35be3b448f666e375366a40e27a9517f5c4faaa81f3a54` |
| Her iki `yuva-yedek/restore-check.*/yuva/bin/yuva` kopyası | `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` |

## Koruma ve doğrulama

Eski `<YUVA_DATA_ROOT>/bin/yuva`, `gorev ekle`, `ata`, `al`, `teslim`, `denetle` ve `iptal` alt komutlarını argüman çözümlemesinden sonra, veri okumadan/yazmadan reddeder. Salt okunur görev komutları bu korumadan etkilenmez. Kullanıcıya kanonik `~/.local/bin/yuva` giriş noktasını kullanması söylenir.

İkinci bypass, eski CLI üzerinden görev mutasyonunu subprocess ile çalıştıran `<YUVA_DATA_ROOT>/panel/server.py` idi. Bu eski sunucu kopyasında `POST /api/gorev` (query/trailing-slash normalizasyonu dahil) gövdeyi okumadan HTTP 410 `legacy_task_writes_disabled` döndürür; iç `gorev_calistir` köprüsü de doğrudan aynı şekilde kapalıdır. Böylece eski panel API'si kilit korumasının etrafından yazamaz. Bu, eski sunucu kaynak dosyasını değiştirdi; sunucu/servis yeniden başlatılmadı ve çalışan servisin bu kopyayı kullandığı iddia edilmiyor.

Geçici dizinde eski CLI ve panel kopyaları çalıştırıldı; `YUVA_DIR` fixture'a yöneltildi. Altı CLI mutasyonunun tümü ret koduyla ve `görev yazımı reddedildi` mesajıyla sonuçlandı. Aynı fixture'da eski panelin `/api/gorev?ignored=1` isteği 410 döndürdü; test gövde akışının hiç okunmadığını da doğruladı. İç köprü doğrudan çağrıldığında da 410 döndü. Fixture `gorevler.json` baytları her denemede aynı kaldı (SHA-256: `521e404647f77a9af362b6235acd26200ecc586478d3d50dcb2f4641132d1d6a`).

Doğrulama: `python3 -m unittest tests.test_legacy_task_write_guard -v` — 1 test geçti.

`~/.local/bin/yuva` symlink'i değiştirilmedi; hedefi `yuva-v2/bin/yuva` olarak kaldı. Servis durumu/ayarları ve fixture dışındaki canlı görev dosyası değiştirilmedi. Görev tahtasındaki #568 claim ve teslim kayıtları ayrı görev akışı işlemleridir.

Bu koruma belirtilen eski CLI ve eski panel API yazma girişlerini sınırlar; aynı kullanıcı hesabının Python modülünü doğrudan içe aktarması veya başka bir kopyayı düzenleyip çalıştırması için OS seviyesinde izolasyon iddiası taşımaz.
