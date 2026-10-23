# Yuva #597 — Lease epoch geçişi ve eski teslim fixture sonucu

## Sonuç

Mevcut `tests/test_lease_completion.py::LeaseCompletionTests.test_stale_epoch_is_audited_without_task_snapshot_change_then_current_completes` fixture'ı çalıştırıldı: **1 test geçti**.

Fixture geçici `TemporaryDirectory` altında synthetic task ledger kuruyor. Eski sahibin epoch N claim'i sonrasında, expiry'nin operatörce uzlaştırılmış hâlini modelleyerek eski lease'i `closed`, görevi `pending` yapıyor. Yeni sahibin claim'i epoch'u N+1'e çıkarıyor. Eski sahibin epoch N ile geç gelen `complete/teslim` çağrısı `lease_epoch_mismatch` alıyor; task snapshot baytları değişmiyor ve reddedilen deneme ayrı attempt log'a yazılıyor. Yeni sahibin epoch N+1 teslimi kabul edilip görev `pending_verification` durumuna geçiyor.

## Kapsam ve sınır

Fixture zaten vardı; bu görevde üretim kodu veya test kaynağı değiştirilmedi. Yalnız hedefli fixture test komutu çalıştırıldı: `python3 -m unittest tests.test_lease_completion -v`. Canlı `gorevler.json`, servis veya panel kullanılmadı.

Test, gerçek saatle lease expiry'yi ya da otomatik recovery/reassignment'ı uygulamaz. Expiry sonrası eski lease'in kapatılıp yeniden claim'e açılması, açık reconciliation sonrası fixture setup'ıdır. Prototipte fencing davranışını sınar; production lease deployment'ı veya gerçek zamanlı sonlandırma kanıtı değildir.
