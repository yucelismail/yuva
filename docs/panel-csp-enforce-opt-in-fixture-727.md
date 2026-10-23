# Yuva #727 — CSP enforce opt-in fixture'ı

`tests/fixtures/panel-csp-transition/report_only_server.py` artık `enforce`
boolean parametresi kabul ediyor. Varsayılan `False` olduğunda mevcut
Report-Only davranışı sürüyor ve `Content-Security-Policy` enforce başlığı
gönderilmiyor. `enforce=True` yalnız `/` ve `/report-only.html` ana belge
yanıtlarında dar `ENFORCE_POLICY` değerini `Content-Security-Policy` başlığıyla
gönderiyor; Report-Only başlığı aynı yanıtta bulunmuyor. Aynı-origin JS/CSS
asset yanıtlarına CSP başlığı eklenmiyor. Rapor alıcısı opt-in enforce kipinde
de de aynı geçici endpoint olarak kalıyor.

Testler varsayılan kapalı davranışı, enforce opt-in header'ını, document/asset
kapsamını, boolean olmayan config reddini ve önceki Report-Only rapor
alıcılarını doğrular. Çalıştırma:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_csp_report_only_fixture -v
```

Sonuç: 4 test geçti. Sandbox ephemeral loopback socket'i engellediği için test
modülü sandbox dışında çalıştırıldı. Test gerçek tarayıcıda CSP ihlalini veya
script/style bloklanmasını doğrulamaz; üretim `panel/server.py` header'ı,
servis, panel UI ve canlı ayarlar değiştirilmedi.
