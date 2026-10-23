# #696 — Production GET wire serialization regresyonları

`tests/test_panel_snapshot_budget_integration.py` ephemeral HTTP sunucusunda
production `panel.server.H` ve geçici `YUVA_DIR` kullanır. Yeni regresyon,
selector çağrısına verilen projected snapshot üzerinden beklenen `bytes` değerini
yeniden hesaplar ve HTTP body ile birebir karşılaştırır. `Content-Length` aynı
byte dizisinin UTF-8 byte uzunluğuna eşit olmalıdır.

Sentetik ledger'da küçük bir çok-byte'lı UTF-8 görev ve item bütçesini aşan büyük
bir Unicode görev bulunur. Beklenen yanıt `partial=true` ve bir atlanan görev
bildirir; küçük kayıt bütün olarak kalır, büyük kayıt kesilmeden atlanır. Ham
UTF-8 byte'ları korunur, büyük kaydın marker'ı yanıtta yer almaz.

Odaklı doğrulama:

`PYTHONPATH=. python3 -m unittest tests.test_panel_snapshot_budget_integration tests.test_panel_snapshot_budget -v`

Sonuç: **11 test geçti.** Yalnız `TemporaryDirectory` data root ve ephemeral
loopback Handler kullanıldı; canlı panel veya anonim erişim açılmadı.
