# #463 HMAC istemci sözleşmesi kaynak karşılaştırması

## Sonuç

`docs/hmac-client-signing-contract-448.md` içindeki canonical byte biçimi
`panel/auth.py` ile uyumlu: magic prefix/NUL sürümü, alan sırası, 4-byte
big-endian framing, ham body SHA-256 digest'i, method/path/timestamp/nonce
doğrulamaları ve padding'siz canonical Base64URL HMAC doğru eşleşiyor. Header
isimleri, duplicate reddi ve exact route hedefi de `panel/auth_integration_draft.py`
ile uyumlu. Kaynakta imza hesabını yanlış tarif eden bir bulgu yok.

İstemci uygulamasına etki edebilecek şu açıklıklar var:

1. **Nonce replay kapsamı fazla geniş ifade edilmiş — düşük.** Sözleşme, aynı
   nonce ile her tekrarın reddedileceğini söylüyor (`docs/hmac-client-signing-contract-448.md:48`).
   Kod replay anahtarını `(principal_id, key_id, audience, scope, nonce)`
   üzerinden türetiyor; `scope` ise `METHOD path` (`panel/auth.py:158-162,
   214-218`). Dolayısıyla aynı nonce farklı principal/key/audience/route
   kapsamlarında ayrı kayıt kabul edilebilir; kayıt süresi geçip temizlendikten
   sonra aynı kapsamda da tekrar kullanılabilir. Her istekte nonce yenileme
   tavsiyesi doğru; yalnız ret garantisi aynı kapsam ve nonce kaydı geçerli
   kaldığı pencereyle sınırlandırılmalı.

2. **HTTP body taşıma sınırları eksik — orta.** Sözleşme ham body byte'larını
   doğru anlatıyor ama gerçek handler'ın gerektirdiği `Content-Type:
   application/json` bilgisini, `Transfer-Encoding`/chunked body'sinin
   reddedildiğini, Content-Length yoksa body'nin boş kabul edildiğini ve POST
   body üst sınırının 1 MiB olduğunu belirtmiyor (`panel/server.py:59,
   1381-1415, 1442-1466`). Non-empty istemci body'si tek geçerli Content-Length
   ile gönderilmeli; duplicate Content-Length reddedilir (aynı revizyon #426
   kapsamında kabul edildi). Bunlar imzaya eklenen alan değil, HTTP katmanının
   kabul koşullarıdır.

3. **`/api/yaz` örnek body alanı yanlış — düşük.** Offline kod örneği
   `/api/yaz` ile `{"mesaj":"Merhaba"}` kullanıyor
   (`docs/hmac-client-signing-contract-448.md:148-151`). Handler `metin` alanını
   bekliyor ve `metin` yoksa 400 döndürüyor (`panel/server.py:1039-1047`). Örnek
   ağa istek göndermese de gövde gerçek route örneği gibi kopyalanırsa
   çalışmaz; `{"metin":"Merhaba"}` kullanılmalı veya body'nin yalnız imza
   hesabını göstermek için route payload'ı olmadığı açıkça yazılmalı.

4. **Route allowlist'i istemci belgesinde listelenmemiş — düşük.** Genel path
   grameri (`docs/hmac-client-signing-contract-448.md:45`) canonical biçime
   uyan pek çok yolu kapsar; server gate ise yalnız
   `POST_ROUTE_POLICY` içindeki 11 path'i kabul eder ve `/api/not` kapalıdır
   (`panel/auth_integration_draft.py:28-40, 91-94`). Belge unknown route'un
   reddedileceğini söylüyor, ancak hangi path'lerin kullanılabilir olduğunu
   tek yerde göstermiyor. İstemci ekibi route/scope seçerken entegrasyon route
   tablosuna başvurmalıdır.

## Kaynakta doğrulanan başlıklar

- Magic: `b"YUVA-HMAC-AUTH\x00v1"`; ardından her canonical field için
  `struct.pack(">I", len(field))` ve field byte'ları (`panel/auth.py:44,
  126-155`). Belgedeki sıralama ve framing doğru.
- Kimlik regex'i, uppercase method, path grammar, timestamp canonical biçimi,
  nonce alfabesi/uzunluğu ve 4096-byte field limiti belgeyle uyumlu
  (`panel/auth.py:44-49, 75-101, 126-149`).
- Body SHA-256'nın 32 raw digest byte'ı framing'e giriyor; body byte'larının
  kendisi canonical mesajda yer almıyor (`panel/auth.py:145-155`).
- Signature 32-byte HMAC-SHA256, canonical padding'siz Base64URL ve 43 karakter
  olarak doğrulanıyor (`panel/auth.py:105-123, 244-250`).
- Header adları ve `get_all()` ile tam bir değer kontrolü doğru eşleşiyor;
  değerler `strip()` ediliyor (`panel/auth_integration_draft.py:42-49, 96-101`).
- Gate yalnız POST ve policy allowlist'i doğruluyor; request-target tam route
  string'i olmalı (`panel/auth_integration_draft.py:28-40, 74-110`).

Salt-okunur incelemedir. `docs/hmac-client-signing-contract-448.md` ve kaynak
dosyaları değiştirilmedi; test, runtime veya panel çalıştırılmadı.
