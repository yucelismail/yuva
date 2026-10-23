# #540 — Legacy CLI ortak tahta yazımından kullanım dışı kabulü

**Tarih:** 2026-10-23
**Kapsam:** Repo içindeki kurulum sözleşmesi ve salt-okunur `yuva doctor` PATH kabulü.
**Sınır:** `<YUVA_DATA_ROOT>` CLI/verisi, `~/.local/bin/yuva` symlink'i, servis ve dosya izinleri değiştirilmedi.

## Karar

#535'in bulduğu eski `~/yuva/bin/yuva`, ayrı bir Git checkout/release dışında duruyor ve mevcut repo kodunu çalıştırmıyor. Aynı OS UID ile çalıştığı ve ortak `YUVA_DIR` dosyalarına doğrudan eriştiği sürece, repo içindeki yeni bir kontrol onun yazmasını teknik olarak durduramaz. Legacy dosyaya guard eklemek, izin/UID sınırı kurmak veya kurulu symlink'i çevirmek bu görevin izin verilen sınırını aşardı.

Bu değişiklik **desteklenen kullanımın decommission kabulünü** kanıtlanabilir yapıyor: README'de tek desteklenen CLI giriş noktası `~/.local/bin/yuva` → `<INSTALL_ROOT>/current/bin/yuva` olarak tanımlandı. `yuva doctor` artık bu PATH symlink'inin release kökü içindeki `current/bin/yuva` dosyasına çözüldüğünü salt okunur doğruluyor. Legacy `~/yuva/bin/yuva`, rastgele kopya ve regular file giriş `supported_cli_entry=fail` / NO-GO üretir.

Bu kabul, legacy binary'nin elle mutasyona çağrılmasını engellediği iddiası değildir. Kullanım dışı bırakma kanıtı yalnız standart PATH/kurulum yoluna aittir; same-UID doğrudan çalıştırma ve dosya yazımı için host düzeyinde ayrı UID/izin veya kopyayı kaldırma kararı gerekir.

## Uygulama ve kanıt

- `bin/yuva` doctor'ına `supported_cli_entry` kontrolü eklendi: eksik/bozuk `current`, releases dışındaki current, release dışı CLI hedefi ve regular-file kopyası reddedilir. Kontrol symlink'i değiştirmez, süreç çalıştırmaz ve Yuva payload dosyalarını okumaz.
- README, `current` tek kaynak sözleşmesini açıkça belirtiyor ve doctor `PASS` sonucunu kurulum kabul koşulu yapıyor. Eski veri-kökü CLI hedefinin aynı UID içindeki manuel çağrıya karşı korunmadığı açıklanıyor.
- `tests/test_doctor.py` fixture'ında canonical `current` symlink geçer; `~/yuva/bin/yuva` legacy hedefi ile bağımsız regular-file kopya reddedilir.

Bu görev canlı symlink/kurulum durumunu doğrulamadı. Gerçek kurulum kabulü `yuva doctor --install-root <INSTALL_ROOT>` çıktısında `supported_cli_entry=PASS`, `current=PASS` ve unit eşleşmelerini gerektirir; bu repo çalışma ağacı için verified release iddiası üretmez.
