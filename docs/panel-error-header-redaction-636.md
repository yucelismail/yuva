# Yuva #636 — Panel hata yanıtlarında header ve redaction fixture'ı

**Tarih:** 2026-10-23
**Kapsam:** #599 ortak yanıt başlıkları ve #548 hata redaction kuralları sentetik handler fixture'ında birleştirildi. Servis başlatılmadı.

## Bulgular ve değişiklik

Mevcut `H.end_headers()` bütün tamamlanan HTTP yanıtlarına `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` ve `X-Frame-Options: DENY` ekliyordu. Fixture kapsamı GET/POST kaynak reddi, OPTIONS, auth gate, parse/size, uygulama handler hatası ve framework `send_error()` yollarının tamamını birlikte doğrulamıyordu.

Sentetik secret ile yapılan sınama, Python `BaseHTTPRequestHandler.send_error()` varsayılanının çağıranın verdiği `message` ve `explain` metinlerini HTML hata gövdesine yansıttığını gösterdi. `H.send_error()` artık yalnızca HTTP status kodunun sabit standart reason phrase'ini ve sabit `The request could not be processed.` açıklamasını geçiriyor. Böylece istekten türeyen veya çağıranın verdiği path/secret metni standart protokol hatası gövdesine çıkmıyor; yanıt yine ortak `end_headers()` policy'sinden geçiyor.

## Sentetik fixture kapsamı ve sonuç

`tests/test_panel_security_response_headers.py` gerçek `H` metotlarını sahte handler nesnesinde çağırıyor; soket veya servis başlatmıyor. Dört güvenlik başlığının her yanıt için tam bir kere, beklenen değerle bulunduğunu; hata gövdelerinde sentetik secret, traceback veya `/home/` path'i olmadığını kontrol ediyor.

Kapsanan yollar:

- JSON başarı yanıtı, OPTIONS 405, GET/POST kaynak reddi ve GET 404
- POST kaynak, Content-Type, JSON parse ve aşırı boyut hataları
- Auth gate reddi
- Beklenmeyen route handler exception'ı; body ve stderr redaction
- Secret/path içeren message ve explain verilen framework `send_error()`

Çalıştırılan komutlar:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_security_response_headers tests.test_error_redaction -v
python3 -m py_compile panel/server.py tests/test_panel_security_response_headers.py
git diff --check -- panel/server.py tests/test_panel_security_response_headers.py
```

Sonuç: **10 test geçti**; derleme ve diff kontrolü başarılı. Servis başlatılmadı, canlı isteğe veya veriye erişilmedi.

## Sınırlar

Bu fixture doğrudan Python handler metotlarının yanıt buffer'ını inceler; gerçek TCP/browser entegrasyonunu veya taşıma hatası yüzünden hiç tamamlanmayan yanıtı test etmez. `end_headers()` çağrılmayan ve HTTP yanıtı üretmeyen bağlantı kopuşlarında HTTP response header beklentisi yoktur. CSP politikası bu görevin kapsamında değildir.
