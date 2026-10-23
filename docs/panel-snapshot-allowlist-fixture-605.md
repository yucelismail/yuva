# Panel snapshot alan allowlist'i ve byte bütçesi fixture'ı (#605)

**Tarih:** 2026-10-23
**Durum:** Yalnız sentetik fixture testleri; canlı servis veya snapshot kullanılmadı.

`tests/test_panel_snapshot_allowlist_fixture.py` üç sınırı geçici/sentetik verilerle doğrular:

1. `veri()` yalnız bilinen üst seviye alanları ve roster için açıkça seçilmiş alanları döndürür. `not_`, `katilma`, `bagli`, heartbeat placeholder'ları ve beklenmeyen kaynak alanları snapshot'a sızmaz.
2. JSONL okuyucusu verilen ham byte tavanını aşmaz ve tek kayıt byte tavanını aşan satırı atlar; sonraki küçük kayıt okunabilir kalır.
3. Ekran JSON map'i ayarlı çıktı byte bütçesini aşmaz; bütçeye sığmayan dosya atlanır ve `partial` / `output_byte_limit` ile görünür olur.

Çalıştırma: `python3 -m unittest tests.test_panel_snapshot_allowlist_fixture -v`.

Bu kontroller toplam `/api/veri` gövdesi için 8 MiB gibi bir global bütçe uygulamaz veya kanıtlamaz. Ekran map'inin kendi output tavanı ve JSONL kaynak/kayıt tavanlarıyla sınırlıdır; anonim GET erişim kontrolü değildir. Toplam snapshot bütçesi ayrı tasarım gerektirir: [#495 toplam bütçe tasarımı](panel-api-total-budget-design-495.md). Veri minimizasyonu kararı için [#574](panel-anonymous-snapshot-data-minimization-574.md) notuna bakın.
