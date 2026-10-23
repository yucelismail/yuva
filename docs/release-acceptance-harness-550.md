# Yerel release acceptance harness (#550)

Çalıştırma:

```sh
python3 release_acceptance.py fixture
```

Harness, `TemporaryDirectory` altında iki temiz sentetik Git release'i ve
sentetik bir `YUVA_DIR` kurar. Harici kaynaktan dosya kopyalamaz, repo
çalışma ağacını release kabul etmez, kullanıcı verisi okumaz ve servis/port
başlatmaz. `INSTALL_ROOT`, `YUVA_DIR`, backup, restore scratch ve tüm release
fixture'ları geçici kökün altındadır; çıkışta temizlenir.

Fixture şu kapıları gerçek release/backup yardımcılarıyla yürütür:

- Temiz fixture Git commit'i, payload/manifest hash'i, dış pin kontrol akışı,
  kurulu dosya hashleri ve `current` release kimliği.
- CLI ve panel canary dosyalarının aynı kurulu release'e çözülmesi; ikisinin
  aynı geçici `YUVA_DIR`'den bir görev ve bir mesajı okuyabilmesi.
- Canary öncesi/sonrası veri kökü hash eşitliği.
- Geçici data root dışındaki backup'ın verify ve scratch restore-check'i;
  aktif data root içindeki backup yolunun reddi; aktif fixture hash'inin aynı
  kalması.
- `yuva-data-contract/v1` ile rollback uyumluluğu ve `current` işaretçisinin
  önceki tam release'e dönüşü. Bilinmeyen şema veya writer kanıtı NO-GO olur.
- Payload manifest kapısında kanonik olmayan yol, release kökü dışına çıkan
  symlink ve hedefi olmayan symlink reddi. Payload fixture kopyası symlink'i
  takip edip normal dosyaya çevirmek yerine link bilgisini korur; üç negatif
  kontrol de `payload_path_policy` gate'inin parçasıdır.

Çıktıdaki `fixture_decision: GO`, yalnız sentetik acceptance zincirinin
çalıştığını gösterir. `host_rollout_decision` kasıtlı olarak **NO-GO** kalır:
fixture pin'i bağımsız güven çapası değildir; hosttaki etkin CLI/panel süreçleri,
writer tekilliği, PATH/unit eşleşmesi, onaylı yedek ve gerçek şema uygunluğu
bu salt fixture koşusunda incelenmez. Bu nedenle çıktı kurulum veya canlı
canary onayı olarak kullanılamaz.

`evaluate_gates()` tüm gerekli kanıtları tam `True` ister; eksik, `unknown` veya
başka bir değer NO-GO üretir. `schema_rollback_compatible()` yalnız bilinen ve
iki release'te eşit olan data contract kimliğini kabul eder.

Fixture testi `tests/test_release_acceptance.py` içindedir. İlgili manifest,
installer, backup ve restore-check testleri ayrıca çalıştırılır.
