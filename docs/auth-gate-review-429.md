# #429 — Auth gate route ve actor incelemesi

## Sonuç

İncelenen entegrasyonda kimlik doğrulamayı atlayıp mutasyon handler'ına veya
görev subprocess'ine ulaşan bir route yolu bulmadım. HMAC açıkken request
target exact canonical allowlist'e bağlanıyor; aynı route dispatch ediliyor.
`/api/not`, bilinmeyen route ve kimlik/rol bağlama hataları handler çağrısından
önce terminal olarak reddediliyor. `/api/kalp` doğrulanmış çağrıda da mevcut
503 cevabını veriyor ve mutasyon yapmıyor.

İnceleme salt kaynak okumasıydı. Panel başlatılmadı, HTTP çağrısı yapılmadı,
auth flag açılmadı ve Yuva uygulama durumunda mutasyon yapılmadı.

## Doğrulanan akış

- `panel/server.py:1025-1069`: auth yalnız `YUVA_AUTH_ENABLED=1` ile
  etkinleşiyor. Eksik config, import, store veya audience uyuşmazlığı
  `main` içinde startup'ı durduruyor (`server.py:1397-1407`); anonim moda
  düşüş yok.
- `server.py:1315-1335`: kaynak ve boyut kontrolleri, ham gövde okuması,
  ardından `authenticate_post(self.path, headers, raw_body)` sırası var.
  JSON parse, handler ve subprocess bu aşamadan sonra.
- `auth_integration_draft.py:74-110`: query, fragment, trailing slash,
  alias ve allowlist dışı path reddediliyor. İmzalama ve dispatch için
  `AuthenticatedRequest.route` aynı canonical path.
- `server.py:1337-1365`: JSON parse sonrasında payload authorization yapılır;
  auth başarısızsa dönüş terminaldir. Auth açıkken dispatch `authn.route`
  ile yapılır ve handler'a `principal=authn.principal` ayrı argüman geçer.
- `auth_integration_draft.py:28-40,112-149`: `UCLAR` içindeki 11 POST
  mutasyon yolunun tamamı policy tablosunda var. `/api/not` `closed`,
  `/api/gorev` admin, actor rotaları self/self-or-admin veya admin
  politikasıyla korunuyor. `/api/katil` self kaydı admin dışı için `isci`
  rolüyle sınırlı (`140-145`).
- `server.py:688-746,857-906,936-1000`: katıl/ayrıl/ekran kimlikleri
  doğrulanmış principal'dan belirleniyor; `/api/yaz` body `kimden` alanını
  authenticated actor yapmıyor; görev köprüsü CLI `--from` değerini
  principal'dan alıyor.
- `auth.py:52-55,197-257` ve `server.py:1072-1081,1325-1349`: auth/store
  hataları açık status ile sonlanıyor; bilinmeyen veya güvensiz hata
  biçimleri güvenli 503'e indirgeniyor. Auth hatası handler/fallback
  çalıştırmıyor.

## Bulgular ve kalan sınırlar

1. **Düşük — yinelenen `Content-Length` başlıkları reddedilmiyor.**
   `server.py:1270-1288` `self.headers.get("Content-Length")` ile tek bir
   değer okuyor; birden fazla değer için `get_all` kontrolü yok. Auth imzası
   ile JSON parser aynı okunan prefix'i görür, bu nedenle incelemede auth
   bypass yolu bulmadım. Ancak HTTP/1.1 çerçevelemesi belirsizleşebilir ve
   artan baytlar sonraki istek gibi işlenebilir. Tek CL başlığını şart koşmak
   daha güvenli olur.

2. **Düşük — bazı mutation actor bilgileri kalıcı audit'e yazılmıyor.**
   `/api/sorumlu` ve `/api/bas-denetci` doğrulanmış principal argümanını alır
   ancak kullanmaz veya olay kaydetmez (`server.py:810-854`). Ayrıca mesaj
   yazarı principal ile seçilse de `mesaj_ekle` kalıcı kayıtta
   `actor_id=None`, `auth_method="none"`, `trust="unverified"` bırakıyor
   (`server.py:522-548`). Bu davranış sahte doğrulama iddiası üretmiyor,
   ancak başarılı HMAC kimliğinin sonradan audit edilmesini sağlamıyor.

3. **Kapsam sınırı — GET ve aynı UID süreçleri bu kapıda değil.**
   `H` sınıfı yorumunda belirtildiği gibi (`server.py:1145-1150`),
   `/api/veri` GET'i HMAC'e bağlı değil; aynı UID'deki süreçler doğrudan
   dosyalara erişebilir. Auth gate mutasyon POST'larını koruyor, yerel
   süreç izolasyonu veya snapshot gizliliği sağlamıyor.

4. **Önceki store incelemesinden kalan — generation dış anchor yok.**
   Geçerli eski auth snapshot'ını geri yüklemek iptal ve nonce geçmişini
   geri alabilir. Bu route wiring incelemesinin dışında; #430 raporundaki
   orta düzey sınıra atıftır.

## Kapsam

Kod değiştirilmedi. Test, runtime veya panel çalıştırılmadı. Kaynaklar:
`panel/server.py`, `panel/auth_integration_draft.py`, `panel/auth.py` ve
`panel/auth_store_v2.py`.
