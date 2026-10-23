# GET snapshot erişim sınırı — karar notu (#455)

- **Durum:** Öneri; ürün/operatör kararı ve canlı dağıtım denetimi gerektirir.
- **Kapsam:** `GET /api/veri`, `/veri`, panel HTML'i ve tarayıcının snapshot isteği.
- **Uygulama etkisi:** Yok. Bu belge auth açmaz ve çalışan bir kurulumun ayarlarını doğrulamaz.

## Kaynak incelemesinin gösterdiği sınır

`panel/server.py` içindeki `do_GET()` kaynak/Host denetiminden sonra `/api/veri`
ve `/veri` için snapshot, `/` ve `/index.html` için HTML döndürür. Bu GET
yollarında `AuthGate` çağrısı yoktur. Panel HTML'i `/api/veri` çağrısını yapar.
Kodda `YUVA_AUTH_ENABLED=1` ile yüklenen HMAC entegrasyonu `POST` route'ları
içindir; mevcut route politikası GET kapsamı tanımlamaz. Dolayısıyla HMAC POST
kapısı, etkinleştirildiği varsayılsa bile snapshot veya HTML erişimini kendi
başına kapatmaz. `Host`/`Origin` kontrolleri de istemci kimliği değildir.

Bu, kaynak kod incelemesinin sonucudur; canlı serviste env değerleri, proxy,
network namespace veya başka bir erişim katmanı incelenmedi. Belge, belirli bir
kurulumda GET'in gerçekten açık/kapalı olduğunu kanıtlamaz.

`/api/veri` kullanıcı/durum bilgisi, görevler, sohbet mesajları ve ekran
kayıtlarını bir arada taşır. Ekran ve mesaj kayıtları yanlışlıkla hassas
bilgi içerebilir. Loopback varsayılanı uzak ağdan doğrudan dinlemeyi azaltır;
aynı network namespace'te localhost'a erişebilen farklı UID süreçlerini
kimliksiz HTTP'den ayırmaz. KOK dosya izinleri HTTP yoluna uygulanmaz. Aynı UID
altındaki süreçler ise dosya izinleriyle de birbirinden yalıtılmaz.

## Önerilen varsayılan ve seçenekler

Varsayılan dağıtım olarak tek, güvenilen Unix UID'si altında **yerel-only,
kimliksiz GET** kabul edilebilir; bu karar ancak tüm bu UID ve localhost
erişimine sahip süreçler güven sınırında sayılıyorsa geçerlidir. Kullanıcıya
ve operatöre, loopback'in yalnız ağ erişimini daralttığı ve yerel UID
izolasyonu sağlamadığı açıkça söylenmelidir. Hassas snapshot verisi farklı
UID'lerden gizliymiş gibi tanıtılmamalıdır.

| Seçenek | Uygun olduğu ihtiyaç | Sınır ve karar kapısı |
|---|---|---|
| Yerel-only açık beyan | Tek güvenilen UID, yerel panel kullanımı | Bugünkü GET davranışını değiştirmez. Farklı UID'ler loopback'e erişebiliyorsa snapshot'ı görebilir; canlı ağ/servis düzeni ayrıca denetlenmelidir. |
| HMAC read scope | CLI/broker gibi anahtar saklayabilen yerel istemciler | GET için yeni imzalı route/scope ve yanıt erişim politikası gerekir. Şu anki POST entegrasyonunun bunu sağladığı iddia edilemez. Anahtar aynı UID süreçlerinden gizlenemez; tarayıcıya sır koymak uygun değildir. |
| Oturum doğrulamalı tarayıcı köprüsü/vekil | Tarayıcı UI'si farklı kullanıcıya açılacaksa | Oturum, cookie, CSRF/Origin ve logout/iptal kuralları gerekir. Backend'e doğrudan kimliksiz erişim kapatılmadıkça vekil tek başına yerel UID sınırı olmaz. |
| Ayrı servis UID'si + UDS `SO_PEERCRED` | Farklı OS UID'leri arasında gerçek yerel izolasyon | Özel servis UID'si ve allowlist uygulanırsa süreç UID'si doğrulanabilir; aynı UID'deki süreçler ayrılmaz. Tarayıcı UDS'ye doğrudan erişemez, bu yüzden ayrıca güvenli HTTP köprüsü gerekir. |
| Snapshot'ı daraltma/redaksiyon | Her istemciye dönmesi gerekmeyen hassas alanlar varsa | Veri azaltımı faydalıdır ama kimlik doğrulama veya yetkilendirme değildir; alan ve rol politikası ayrıca belirlenmelidir. |

## Geçiş kapıları

1. `/api/veri` içindeki alanları sınıflandır; her alan için amaçlanan okuyucu
   ve hassasiyet kararını kaydet. Özellikle sohbet/ekran metnini güvenilmeyen
   içerik ve olası sır olarak değerlendir.
2. Tek UID yerel-only model kabul ediliyorsa bunu README/operatör belgelerinde
   ve panelin erişim açıklamasında belirt; farklı UID'nin localhost erişimi
   olabileceğini varsay.
3. Snapshot farklı UID'lerden gizlenecekse önce dağıtım sınırını seç: özel
   servis UID'si ve UDS peer denetimi, ya da backend erişimi kapatılmış
   doğrulanmış HTTP köprüsü. Dosya izinlerinin HTTP'yi kapattığını varsayma.
4. HMAC read scope seçilirse route/scope, imzalanan istek, replay koruması,
   anahtar provision/iptal/rotasyon ve `GET /api/veri` yanıt yetkisini tasarla.
   Tarayıcı UI'si için HMAC sırrı dağıtma; oturum köprüsünü ayrı tasarla.
5. Değişiklikten sonra her GET yolunun (snapshot alias'ları ve HTML dahil),
   varsayılan auth-kapalı davranışın ve auth/peer hatasında fail-closed
   sonucunun dağıtım incelemesini yap. Bu not bu doğrulamayı yapmış sayılmaz.

Karar verilene kadar güvenli varsayım: localhost'a erişebilen yerel süreç,
snapshot verisini okuyabilecek yeteneğe sahip kabul edilir. Bu, her dağıtımın
fiilen bu şekilde yapılandırıldığının kanıtı değildir.

## Dayanak

- `panel/server.py`: `do_GET()`, `auth_gate_yukle()` ve loopback bind kontrolü.
- `panel/auth_integration_draft.py`: HMAC entegrasyonunun yalnız POST route
  politikası.
- `panel/ui.html`: `/api/veri` tarayıcı isteği.
- `docs/local-api-access-boundary.md` ve `docs/local-data-threat-model.md`:
  loopback, UID, snapshot kapsamı ve dosya izinleri.
- `docs/auth-state-v2-operations.md`: auth default-off ve GET'in auth dışı
  kaldığına ilişkin operasyon notu; canlı ayarların doğrulandığını ifade etmez.
