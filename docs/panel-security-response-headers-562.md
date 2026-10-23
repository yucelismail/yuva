# #562 — Panel güvenlik yanıt başlıkları

Tarih: 2026-10-23
Durum: Kaynak değişikliği ve sentetik handler fixture'ları tamamlandı; görev
inceleme için teslim ediliyor.

## Uygulama

`panel/server.py` içindeki `H.end_headers()` her HTTP yanıtının sonlandırıldığı
ortak noktada aşağıdaki başlıkları ekliyor:

| Başlık | Değer | Amaç |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Tarayıcının MIME türünü tahmin etmesini engeller. |
| `Referrer-Policy` | `no-referrer` | İsteklerde referrer bilgisini göndermez. |
| `X-Frame-Options` | `DENY` | Panelin başka bir sayfada frame içine alınmasını engeller. |

Merkezileştirme `_gonder()` yanıtlarının yanında doğrudan `do_OPTIONS()` ve
`BaseHTTPRequestHandler.send_error()` tarafından üretilen yanıtları da kapsar.
Var olan MIME, `Cache-Control: no-store`, CORS ve kaynak denetimi davranışları
bu değişiklikte değiştirilmedi. Taşıma hatası nedeniyle HTTP yanıtı
üretilemeyen durumlarda yanıt başlığı bulunamaz.

## CSP uyumluluğu ve geçiş

Bu değişiklik CSP başlığı eklemiyor. `panel/ui.html` tek dosyada inline
`<style>` ve `<script>` içeriyor; arayüz ayrıca JavaScript ile dinamik
`style=` nitelikleri üretiyor. CSP'yi inline izinleri kapalı biçimde hemen
uygulamak mevcut arayüzün script veya görünüm davranışını bozabilir. Genel
`unsafe-inline` izni bu nedenle güvenli geçiş sayılmaz.

Önerilen dar geçiş sırası:

1. Sabit CSS ve JavaScript'i same-origin statik dosyalara çıkar.
2. Dinamik `style=` üretimlerini CSS sınıflarına ve sınırlı sınıf/tema
   eşlemelerine taşı; inline event handler bırakma.
3. Kalan sabit inline bloklar varsa sürümle eşleşen hash'leri kullan; içerik
   her istek için nonce ile işaretlenecekse nonce'u HTML ile CSP başlığında
   aynı yanıta özel üret ve HTML'deki tüm ilgili bloklara uygula.
4. Önce rapor-only `Content-Security-Policy-Report-Only` ile tarayıcı
   ihlallerini gözle; ardından `default-src 'self'`, `base-uri 'none'`,
   `object-src 'none'`, `frame-ancestors 'none'`, `form-action 'self'` ve
   `connect-src 'self'` tabanlı enforce politikasına geç. Script/style
   kaynaklarını temizleme tamamlanmadan gevşek inline izni ekleme.

Hash/nonce stratejisi `<style>` ve `<script>` bloklarını ele alır; dinamik
style niteliklerini tek başına çözmez. CSP tarayıcı katmanıdır ve anonim GET
erişimini, yetkilendirmeyi veya snapshot gizliliğini değiştirmez.

## Doğrulama ve kapsam

`tests/test_panel_security_response_headers.py` gerçek `H` metotlarını
sentetik handler ile çağırarak JSON başarı, `OPTIONS 405` ve standart HTTP
hata yanıtlarında üç başlığın tekil ve beklenen değerde olduğunu doğrular.
Çalıştırma: `python3 -m unittest tests.test_panel_security_response_headers -v`
— 3 test geçti.

Auth ayarı, route davranışı, canlı servis ve CSP uygulanmadı. Başlık testi
gerçek tarayıcı veya deployment doğrulaması değildir.
