# README hızlı başlangıç çapraz kontrolü (#723)

**Tarih:** 2026-10-23
**Kapsam:** README komutları ve release anlatımı parser, service template ve mevcut release belgeleriyle karşılaştırıldı. Host, servis, GitHub veya release işlemi yapılmadı.

## Bulgu ve düzeltme

README hızlı başlangıcı release klasörünü `<INSTALL_ROOT>/releases/<commit>`
olarak gösteriyordu. Bu eksik tanımdı: installer pointer hedefinde ve manifestte
`<full-commit>-<full-payload-sha256>` kullanır. README ifadesi bu tam release ID
biçimini gösterecek şekilde düzeltildi.

Kaynak kanıtı:

- `release_manifest.py:293,382-384` — release ID commit'i payload SHA-256 ile bağlar.
- `docs/release-installer-543.md:30-33` — `current`/`previous` hedefini `releases/<full-commit>-<full-payload-sha256>` olarak belgeler.
- `release_installer.py:27,193-196,615-648` — aynı ID formatını regex, pointer doğrulama ve publish sırasında kullanır.
- `README.md:121-132` — hızlı başlangıç artık tam biçimi gösterir ve verified manifest installer belgesine yönlendirir.

## Tutarlılık kontrolü

- README'deki `yuva baglan`, `kalp`, `ayril`, `durum`, `kimler`, `sorumlu`,
  `bas-denetci`, `yaz`, `oku`, `gelen`, `wait`, `tahta`, `gorev` ve `panel`
  örneklerinin isimleri/temel seçenekleri `bin/yuva` argparse tanımlarıyla
  uyumludur (`bin/yuva:3513-3705`). `yuva ekran oku` parser'da ayrı subcommand
  değil, `cmd_ekran()` tarafından `satir[0] == "oku"` ile yönlendirilen özel
  kullanım biçimidir (`bin/yuva:1701-1703`); README/protokol örneği buna uygundur.
- Panel varsayılan portu README ve unit template'te `8686`, statik preview portu
  `8687`'dir (`bin/yuva:83,3697`; `contrib/systemd/yuva-panel.service:8`;
  `preview/server.py`). Kalıcı unit `yuva-panel.service` yalnız
  `panel/server.py` UI/API sunucusudur.
- README W1a/W1b açıklamaları mevcut kaynakla uyumludur: `/api/kalp` broker
  principal yokken `503`; `baglan --kalp-yok` roster kaydı olup doğrulanmış
  online/presence üretmez. Host-supervised heartbeat başlatma kapalıdır.
- README'nin loopback panelinin kimlik doğrulaması olmadığını ve aynı network
  namespace içindeki yerel süreçlerin erişebileceğini belirten uyarısı korunuyor.
  `YUVA_AUTH_ENABLED=1` için HMAC principal/policy gereği de doğru belirtilmiş.
- `docs/release-installer-543.md` dışarıdan pinlenmiş manifest digest'i, ayrı
  clean source/payload/install/data root'larını, tam release ID'yi ve rollback'in
  data root'u geri yüklemediğini doğruluyor. `docs/linux-gecis.md` panel ve
  heartbeat unit ayrımını, 8686 loopback kullanımını ve writer/backup kapılarını
  ayrıca koruyor.

Kaynak başlıklarının/portlarının statik kontrolüdür; örnek kurulum, `systemd`,
`doctor`, canlı `YUVA_DIR`, release install/rollback veya browser auth testi
çalıştırılmadı. README'deki systemd komutları operatörün açık kurulum adımlarıdır;
burada çalıştırılmadı.
