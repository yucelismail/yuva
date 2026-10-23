# #695 — Production Handler snapshot byte budget entegrasyonu

`panel/server.py` artık `/api/veri` ve `/veri` yanıtlarını isteğe bağlı olarak
production selector üzerinden gönderebilir. Selector uygulaması
`panel/snapshot_budget.py` içindedir; önceki `prototypes.panel_snapshot_budget`
yolu uyumluluk importu olarak korunur.

## Etkinleştirme sözleşmesi

- `YUVA_SNAPSHOT_BUDGET_ENABLED` tanımsız veya `0` ise mevcut GET yanıt yolu
  korunur; `snapshot_meta` eklenmez.
- Yalnız tam `1` değeri selector'ı açar. Sabit JSON UTF-8 yanıtı 8 MiB varsayılan
  global bütçeyle üretilir; aynı `bytes` nesnesi gönderilir ve
  `Content-Length`, gönderilen byte sayısından hesaplanır.
- Tanımsız/`0` dışındaki geçersiz değer sabit `503` üretir; limitsiz yanıt
  fallback'i yapmaz.
- Flag GET erişim veya auth policy'sini değiştirmez ve anonim erişim kararı
  sağlamaz. #574 tam anonim snapshot kararı **NO-GO** olarak kalır.
- Bütçe açıkken ekran round-robin cursor'ı snapshot alınırken ertelenir ve
  yalnız selector başarılı final response ürettikten sonra ilerletilir.
  Selector hatası cursor'ı tüketmez.

Bu entegrasyon kaynak/response memory sınırının bütünü için kanıt değildir;
özellikle parse öncesi kaynak byte sınırı ve ölçümlü peak RSS kapıları #685’te
tanımlandığı şekilde ayrı kalır. Handler testi yalnız `TemporaryDirectory` ve
ephemeral loopback HTTP kullanır; gerçek panel, host veya auth provisioning
kullanmaz.

## Odaklı doğrulama

`PYTHONPATH=. python3 -m unittest tests.test_panel_snapshot_budget_integration tests.test_panel_snapshot_budget -v`

Sonuç: 9 test geçti. Testler unset flag davranışını, enabled production Handler
wire body/`Content-Length` ve metadata'yı, bozuk flag'in fail-closed `503`
sonucunu, selector başarı/hata dallarında ekran cursor commit'ini ve selector'ın
UTF-8/bütçe davranışını kapsar.
