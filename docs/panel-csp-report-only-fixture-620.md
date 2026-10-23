# Yuva #620 — CSP Report-Only HTTP fixture'ı

**Tarih:** 2026-10-23
**Kapsam:** Yalnız geçici loopback fixture/example server. `panel/server.py`, canlı service, production header ve CSP enforcement değiştirilmedi.

## Fixture neyi doğruluyor

`tests/fixtures/panel-csp-transition/report_only_server.py`, yalnız `127.0.0.1` üzerindeki ephemeral portta çalışan küçük bir örnek HTTP sunucusu kurar. Rapor yolu, HTML ve iki same-origin varlık için mapping dışında dosya yolu çözmez. Test, site dosyalarını her seferinde ayrı `TemporaryDirectory`'ye kopyalar; shutdown, socket close, thread join ve temp root temizliğini doğrular.

Ana document `/` ve `/report-only.html` yanıtında tek `Content-Security-Policy-Report-Only` başlığı gönderilir. `Content-Security-Policy` enforce başlığı ve meta policy gönderilmez. CSS ve JS same-origin dosyaları olarak sunulur; bu static asset yanıtlarında document policy tekrar edilmez. Mevcut ortak response başlıkları fixture'da korunur: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`.

Report sink, `report-uri` ve `report-to` directives ile aynı geçici server'ın `/__csp-report` yoluna sınırlıdır; `Reporting-Endpoints` ve legacy `Report-To` grubu aynı ephemeral endpoint'i gösterir. Alıcı yalnız report byte sayısı ve content-type bilgisini bellekte tutar; rapor gövdesi (document URL ve kullanıcı verisi içerebilir) saklanmaz. İçerik boyutu 16 KiB ile sınırlı, doğru JSON ve iki CSP report media type'ından biri gerekli; yabancı yol reddedilir.

Kullanılan dar Report-Only policy, #607'nin örnek geçiş hedefiyle aynıdır:

```text
default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none';
form-action 'self'; script-src 'self'; script-src-attr 'none'; style-src 'self';
style-src-attr 'none'; img-src 'self' data:; font-src 'self'; connect-src 'self';
report-uri /__csp-report; report-to yuva-csp-fixture
```

Fixture document kasıtlı inline `<style>`, `<script>`, `style=` ve `onclick=` ihlalleri içerir. Same-origin `allowed.css` ve `allowed.js` izinli örneklerdir. Test HTTP response header'ını, endpoint grubu/path kapsamını, iki report media type'ının bounded alıcıya ulaştığını ve rapor gövdesinin kalıcı/fixture sink kaydına alınmadığını doğrular. Rapor alıcısı dış ağ veya gerçek Yuva servisi kullanmaz.

## #607 envanteri ve mevcut enforce durumu

`panel/ui.html` #607 envanteriyle uyumlu olarak hâlâ şunları içerir:

- Bir inline `<style>` bloğu (`ui.html:5-446`) ve bir inline uygulama `<script>` bloğu (`ui.html:502-2438`). Strict `script-src 'self'` / `style-src 'self'` ile bu bloklar izinli olmaz.
- `ui.html:458`'de statik `style=`; ayrıca `ui.html:688, 818-820, 1143, 1253-1254, 1302, 2045, 2078-2089, 2118, 2128` civarında dinamik style attribute üretimleri. `style-src-attr 'none'` bunları raporlayıp enforce aşamasında engeller.
- Kaynak HTML'de inline event attribute bulunmadı; test fixture'ındaki `onclick` yalnız kasıtlı ihlal örneğidir. JavaScript event listener kullanımı same-origin `allowed.js` örneğine taşınabilir.
- `panel/ui.html` içinde çok sayıda `innerHTML` sink'i bulunur. `esc()` bazı metin interpolasyonlarında HTML karakterlerini escape eder; bu inceleme bütün sink'ler için context-aware XSS denetimi değildir. CSP report-only XSS'i düzeltmez veya sanitization/authorization garantisi vermez.

Bu envantere göre mevcut panel strict policy için **enforce'a hazır değildir**. Inline script/style dış dosyaya çıkarılmalı veya açıkça onaylı nonce/hash ile kapsanmalı; dinamik style üretimleri sınırlı CSS class/data varyantlarına taşınmalı; `innerHTML` interpolasyonları ayrı XSS incelemesinden geçmelidir. `unsafe-inline` eklemek kabul çözümü değildir. `img-src`, `font-src`, `connect-src` ve form davranışı da gerçek panel bağımlılıkları üzerinde gözden geçirilmelidir.

## Doğrulama

Çalıştırılan komut:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_csp_report_only_fixture -v
```

Sonuç: **2 test geçti.** Test, ephemeral loopback server response header'ını ve synthetic report POST alıcısını doğrular. Tarayıcı çalıştırmadı; gerçek Chromium/Firefox/WebKit console violation raporları veya production deployment raporlama davranışı ölçülmedi. Meta CSP fixture'ı olan `index.html` (#607 enforce örneği) değiştirilmeden bırakıldı.

## Kaynaklar

- `docs/panel-csp-transition-607.md` — inline envanter, enforcement engelleri ve geçiş kapıları.
- `docs/panel-security-response-headers-562.md` — production ortak response header'ları ve CSP'nin henüz uygulanmadığı bilgisi.
- `panel/server.py:H.end_headers()` — canlı panelin mevcut güvenlik/cache başlıkları; CSP burada yok.
- `tests/fixtures/panel-csp-transition/report-only.html`, `report_only_server.py`, `tests/test_panel_csp_report_only_fixture.py` — geçici örnek server ve acceptance testleri.

Fixture yalnız test içindir; CSP başlığı production panel yanıtına eklenmedi.
