# Yuva #607 — Panel CSP envanteri ve geçiş planı

## Mevcut inline kullanım envanteri

Kaynak incelemesi `panel/ui.html` ve `/` için `panel/server.py` içindeki
yerleşik minimal HTML yanıtını kapsar.

| Kaynak | Yer | CSP etkisi | Önerilen dönüşüm |
|---|---|---|---|
| Ana stylesheet | `panel/ui.html:5-446` arasındaki tek `<style>` bloğu | `style-src 'self'` ile engellenir | Aynı-origin `panel.css` dosyasına çıkar |
| Ana uygulama | `panel/ui.html:502-2438` arasındaki tek `<script>` bloğu | `script-src 'self'` ile engellenir | Aynı-origin `panel.js` dosyasına çıkar; geçici olarak nonce veya tam içerik hash'i düşünülebilir |
| Statik style attribute | `panel/ui.html:458` | `style-src-attr 'none'` ile engellenir | `.sohbet-durum` gibi sınıfa taşı |
| Dinamik style attribute üretimi | `panel/ui.html:688, 818-820, 1143, 1253-1254, 1302, 2045, 2078, 2089, 2118, 2128` | Inline style değerleri policy'yi aşmaya çalışmadan engellenir | Renk/yerleşimi sınıf veya sınırlı `data-*` varyantlarıyla eşle; `style=` ile gelen keyfi değerleri izin listesine taşı |
| Inline event attribute | HTML kaynak taramasında bulunmadı | Mevcut bulguda `onclick=` benzeri handler yok | Etkileşimler event listener'larında kalmalı; yenileri HTML attribute olarak eklenmemeli |
| JS event listener | `panel/ui.html` içindeki `addEventListener` çağrıları | Dış `panel.js` ile uyumlu | Dış dosyaya taşıma sırasında delegasyon ve listener davranışını koru |
| Sunucu minimal HTML yanıtı | `panel/server.py:1642-1646` | İç `style=` attribute'ları ve aynı-origin olmayan/inline kod yok; stil engellenirse görsel sadelik etkilenir | İstersen aynı-origin CSS'e taşı; CSP'nin temel onay kapısı olmamalı |

Dinamik style üretimleri birden fazla görünümde renk, grid konumu ve boyut
taşıyor. Bu değerler farklı kullanıcı/ekip/task verilerinden türediği için
yalnız sabit hash'lerle kapsanamaz. `style-src-attr` nonce kabul etmez. CSP3
`'unsafe-hashes'` + hash ile belirli statik handler/attribute değerleri
izinlenebilir; fakat keyfi veya değişken değerleri güvenle çözmez ve
genişleyen bir izin listesi oluşturur. Bu panel için tercih edilen son durum,
event listener kullanımı ve inline style attribute bulunmamasıdır.

## Politika seçenekleri

1. **Öncelik: dış dosyalara çıkarma.** Script ve stylesheet aynı-origin statik
   dosyalar olarak sunulur. Event handler attribute'ları listener'a, dinamik
   stil çıktıları sınıf/izinli varyantlara taşınır. Değişiklik takibi ve
   cache davranışı kolay kalır.
2. **Geçici sabit blok: hash.** Değişmeyen inline `<script>`/`<style>` içeriği
   için SHA-256 hash kaynakları kullanılabilir. Her byte değişikliği hash'in
   yeniden üretilmesini gerektirir; attribute handler/style için genel çözüm
   değildir.
3. **Geçici sunucu üretimli blok: nonce.** Her HTML yanıtı için CSPRNG ile
   üretilen tek kullanımlık nonce yalnız ilgili `<script nonce>` ve
   `<style nonce>` etiketlerine eklenir. Nonce cache'lenmiş HTML ile yeniden
   kullanılmamalı ve style/event attribute'larına uygulanmış gibi
   değerlendirilmemelidir. Panel `no-store` döndürse de nonce üretimi yanıt
   bazında açık olmalıdır.

Son hedef için örnek dar politika (bağımlılık envanteri doğrulandıktan sonra):

```text
default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none';
form-action 'self'; script-src 'self'; script-src-attr 'none'; style-src 'self';
style-src-attr 'none'; img-src 'self' data:; font-src 'self'; connect-src 'self'
```

`img-src`, `font-src`, `connect-src` ve form davranışı gerçek panel
bağımlılıklarıyla doğrulanmalı; raporlar incelenmeden bu taslak üretime
uygulanmamalıdır. `frame-ancestors` HTTP response header'da gönderilmelidir;
meta policy ile eşdeğer değildir.

## Report-Only → enforce kapıları

### Aşama 0 — Envanter ve baseline

- Her inline block, `style=`/event attribute ve harici bağlantı kayda alınır.
- Script/style dış dosyalara veya onaylı nonce/hash biçimine geçirilir;
  event/style attribute dönüşümü tamamlanır.
- Temsilî Chromium, Firefox ve WebKit sürümlerinde panelin giriş, refresh,
  task board, mesajlaşma, arama/filtre ve hata/boş durumları açılır.

### Aşama 1 — Staging Report-Only

- Politika yalnız staging veya sentetik fixture yanıtında
  `Content-Security-Policy-Report-Only` header'ı olarak çalışır. Meta etiketi
  Report-Only sağlamaz.
- Rapor alıcısı önceden hazır ve boyut/sıklık sınırlı olmalı; rapor gövdeleri
  kullanıcı verisi içerebileceğinden erişimi sınırlanmalı ve saklama süresi
  belirlenmelidir.
- Yeterli gözlem süresince tüm ihlaller kaynak, tarayıcı, route ve test
  senaryosuyla eşleştirilir. Meşru işlevden gelen ihlal kalmamalı; gürültü,
  extension kaynaklı raporlar uygulama ihlali gibi sayılmamalıdır.

### Aşama 2 — Staging enforce

- Aynı politika staging'de enforce edilir; yukarıdaki akışlar ve olumsuz
  durumlar tekrar edilir.
- CSP nedeniyle bloklanan meşru script/style, kaybolan panel etkileşimi veya
  API bağlantısı sıfır olmalı; Console ve raporlar kontrol edilir.
- Rollback header değişikliğiyle yapılabilir olmalı; CSP dışındaki auth,
  snapshot gizliliği veya XSS sanitizasyonu garantisi olarak sunulmamalıdır.

### Aşama 3 — Kademeli üretim

- Yalnız staging kapıları geçtikten sonra, ölçülebilir küçük kullanıcı/istek
  diliminde enforce açılır; işlev hataları, CSP ihlalleri ve panel hata oranı
  izlenir.
- İhlal veya işlev regresyonu varsa önceki header politikasına geri dönülür;
  etki temiz ve eşik altında kalmadan dilim büyütülmez.
- Tam enforce sonrası Report-Only duplicate policy kaldırılır; ihlal alıcısı
  ve inceleme sahibi belirli kalır.

## Sentetik engelleyici davranış fixture'ı

`tests/fixtures/panel-csp-transition/index.html` sadece kasıtlı ihlal örnekleri
içerir: inline script, inline `<style>`, inline event handler ve `style=`
attribute. Aynı-origin `allowed.js` ve `allowed.css` ise policy tarafından
izinlidir. Fixture'daki meta policy **enforce** modundadır; yerel web sunucusu
üzerinden açıldığında inline davranışların engellendiği, dış dosyaların
çalıştığı tarayıcı geliştirici konsolunda gözlemlenebilir. Bu fixture gerçek
paneli veya üretim header'larını değiştirmez ve tek başına tarayıcı matrisi
kanıtı sayılmaz.

Report-Only kontrolü için aynı policy staging fixture yanıtına HTTP header
olarak eklenmeli; ihlal rapor alıcısı yoksa `report-uri`/`report-to` eklenip
boşa POST üretilmemelidir. `Content-Security-Policy-Report-Only` bir meta
etiketiyle test edilemez.

Bu görevde `panel/server.py` CSP header'ı değiştirilmedi ve servis
başlatılmadı.
