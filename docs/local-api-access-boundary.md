# Yerel panel API erişim sınırı

## Amaç ve mevcut durum

Bu not, panel API'sinin aynı makinedeki farklı işletim sistemi kullanıcılarına
(UID) açık olmasından doğan erişim sınırını ve olası geçiş yollarını değerlendirir.
Bu bir tasarım değerlendirmesidir; sunucu davranışını değiştirmez.

Panel varsayılan olarak `127.0.0.1:8686` üzerinde dinler ve loopback dışı bind'i
reddeder (`panel/server.py:1095-1113`). Bu, uzaktan erişimi kapatır; aynı
network namespace içindeki yerel süreçlerden kimlik istemez. `Host` ve `Origin`
denetimleri tarayıcı kaynaklı CSRF/DNS-rebinding riskini daraltır, ancak
kimlik doğrulamaz. Sunucu kodu da aynı UID'deki süreçlerin istemci kimliğini
taklit edebildiğini ve veri dosyalarını doğrudan değiştirebildiğini açıkça
belirtir (`panel/server.py:886-893`). README ayrıca farklı UID'lerdeki yerel
süreçlerin localhost API'sine erişip model adını taklit edebildiğini kaydeder
(`README.md:170-182`).

`GET /api/veri` tüm panel anlık görüntüsünü döndürür (`panel/server.py:1035-1047`);
bu nedenle sınır yalnızca yazma işlemleriyle ilgili değildir. POST yolları
istek kaynağı, gövde boyutu ve JSON biçimini denetler; bu denetimler de çağıran
yerel sürecin kimliğini kanıtlamaz (`panel/server.py:1059-1075`).

Kullanıcı systemd servisi ve ortak kullanıcı veri kökü mevcut dağıtımın
varsayımlarındandır (`README.md:105-140`). API'ye erişim denetimi eklemek,
aynı UID'nin dosyalara doğrudan erişebildiği durumda o UID'ye karşı dosya
gizliliği veya bütünlüğü sağlamaz. Hedef tehdit aktörü ve ayrıcalık seviyesi
bu nedenle açıkça seçilmelidir.

## Tehdit modeli

| Aktör | Bugünkü sınır | Tasarım sonucu |
|---|---|---|
| Uzak ağ istemcisi | Sunucu loopback dışı bind'i reddeder. Dışarı açılan vekil/tünel kendi erişim denetimini uygulamalıdır. | Loopback kısıtını koru; dış erişim ayrıca tasarlanıp doğrulanmadıkça desteklenmiş sayılmamalı. |
| Başka UID'deki yerel süreç | Aynı network namespace'ten loopback HTTP API'yi çağırabilir; Host/Origin kimlik kanıtı değildir. | Yerel UID izolasyonu gerekiyorsa API'nin kendi dinleme yüzeyinde OS kimliği doğrulanmalı veya güvenilir bir aracıya kapatılmalı. |
| Aynı UID'deki süreç/model | HTTP çağrısı yapabilir, model adı taklit edebilir ve UID'nin dosya izinleri elveriyorsa veri dosyalarına doğrudan erişebilir. | Aynı UID altındaki süreçleri birbirinden ayırma hedefi bu tasarımlarla tek başına karşılanamaz. |
| Root/host yöneticisi veya ele geçirilmiş servis UID'si | İşletim sistemi izinlerini ve süreçleri denetleyebilir. | Bu tasarımın dışında, makine güven köküdür. |
| Başka origin'deki web sayfası | Kaynak denetimleri ve CORS ön-uçuşunun reddi bazı tarayıcı vektörlerini sınırlar. | Tarayıcı korumalarını sürdür; bunları yerel uygulama kimliği yerine kullanma. |

Özellikle, model adı, `--from`, mesajdaki `kimden`, rol veya `durum.json`
içindeki iddialar OS kimliği değildir. Kimlik kararı yalnızca güvenilir
taşıma/kimlik doğrulama katmanından gelen ve endpoint'e ayrı geçirilen
principal üzerinden verilmelidir.

## Seçeneklerin değerlendirmesi

| Seçenek | Güvenlik sınırı | Tarayıcı ve uyumluluk | Sınır / maliyet |
|---|---|---|---|
| Mevcut loopback HTTP | Uzak bind kapalı; yerel UID'ler arasında izolasyon yok. | Mevcut UI ve CLI kullanımıyla uyumlu. | Kimlik doğrulama değildir. Aynı namespace'teki farklı UID'ler API'yi çağırabilir. |
| HTTP istek HMAC'i | Doğru uygulandığında imzalı istemciye ve route'a bağlı istekleri doğrulayabilir. | CLI/broker için uygundur. Tarayıcıda sır saklamak uygun değildir. Mevcut taslak yalnız POST yollarını kapsar; anonim GET'i ve browser session'ını çözmez. | Anahtar dağıtımı, iptal/rotasyon, nonce kalıcılığı ve tekrar denemelerde idempotency gerekir. Aynı UID'deki yetkili süreçten gizli tutulabilen anahtar varsayımı ayrıca incelenmelidir. |
| Unix domain socket ve `SO_PEERCRED` | Linux'ta bağlantıdaki sürecin kernel tarafından bildirilen UID/GID/PID'sini doğrular; izinli UID listesi uygulanabilir. Socket dosyası izinleri ek katmandır. | CLI ve yerel yardımcı süreçler kullanabilir. Tarayıcı JavaScript'i doğrudan UDS'ye bağlanamaz; UI için HTTP köprüsü/vekil veya ayrı tarayıcı oturumu gerekir. | Peer credentials model/ajan kimliğini değil OS sürecinin UID'sini kanıtlar. Sunucu aynı kullanıcı UID'sinde kalırsa diğer aynı-UID süreçleri ayırt etmez. |
| Ayrı servis UID'si + UDS | Paneli özel UID altında çalıştırıp socket'i seçilmiş kullanıcı/gruba açmak, diğer UID'leri panel API'sinden ayırabilir. Dosya erişimi de bu yeni sahiplik modeline göre düzenlenmelidir. | CLI için grup/ACL veya küçük bir istemci aracısı gerekebilir. Tarayıcı UDS kullanamaz; loopback'te yalnız kontrollü proxy ya da oturum doğrulamalı HTTP köprüsü gerekir. | Kurulum, systemd unit'i, veri kökü izinleri, yedekleme ve mevcut CLI yazıcıları için geçiş gerektirir. Doğrudan ortak dosyalara erişen kullanıcıları API'den bağımsız olarak engellemez. |
| Kimlik doğrulamalı ters vekil | Vekil tarayıcı/uzak erişim politikasını uygulayabilir. Backend yalnız vekile erişilebilir ise API için de bir kapı olur. | Web UI ile uyumludur; vekil oturumu, cookie ve CSRF politikası tasarlanmalıdır. | Şu anki doğrudan loopback backend'i başka yerel süreçlere açık kalırsa vekil tek başına izolasyon sağlamaz. Backend erişimi ayrıca kapatılmalı. |

### HMAC taslağıyla ilişki

`panel/AUTH_INTEGRATION_DRAFT.md` bir öneridir; `server.py` tarafından
yüklenmez ve geçerli varsayılan davranışı değiştirmez. Taslak, imzalı POST
route'ları, doğrulanmış principal ve endpoint bazlı yetki eşlemesini ele alır;
`GET /api/veri` için auth sözleşmesi veya tarayıcı oturum akışı tanımlamaz
(`panel/AUTH_INTEGRATION_DRAFT.md:1-6, 8-31`). Bu nedenle taslak, yerel UID
izolasyonu kararının yerine geçmez. Gelecekte HMAC benimsenirse, CLI/broker
kimlik doğrulaması için UDS/servis UID'siyle birlikte kullanılabilir; browser
GET ve POST trafiği için ayrıca bir oturum tasarımı gerekir. Tarayıcıya HMAC
anahtarı koymak güvenli bir seçenek değildir.

## Önerilen karar ve aşamalı geçiş

İlk karar, koruma hedefini seçmektir:

1. **Yalnız ağdan uzaktaki erişimi engellemek yeterliyse:** loopback varsayılanı,
   Host/Origin ve gövde kontrolleri korunur; bunlar açıkça ağ/CSRF kontrolleri
   olarak belgelenir. Yerel UID izolasyonu sağlandığı iddia edilmez.
2. **Farklı yerel UID'leri engellemek gerekiyorsa:** panel API'si özel servis
   UID'sine taşınır ve yazma/CLI erişimi kontrollü bir Unix socket'ten verilir;
   `SO_PEERCRED` UID allowlist'iyle doğrulanır. UI gerekiyorsa loopback HTTP
   yalnız kontrollü yerel proxy/bridge arkasında açılır ve backend'e doğrudan
   erişim engellenir. Tarayıcı oturumu cookie/CSRF ve Origin kontrollerini ayrı
   tanımlar.
3. **İmzalı ajan/broker çağrıları da gerekiyorsa:** HMAC taslağı yalnız ilgili
   POST route'larına principal doğrulama katmanı olarak entegre edilir. GET
   verisinin yetkisi ayrıca tanımlanır. HMAC, OS UID sınırını veya veri
   dosyalarının doğrudan erişim politikasını ikame etmez.

Uygulamaya geçmeden önce şu kapılar kapatılmalıdır:

- Korunacak veriler ve her GET/POST route'unun yetkili principal/rolü
  envanterlenmeli; özellikle `/api/veri` içeriği ve hassasiyeti açıkça
  sınıflandırılmalı.
- Hedef UID'ler, servis UID'si, veri kökü sahibi/grubu, JSONL ve ekran dosyası
  izinleri belirlenmeli. Mevcut CLI'nin doğrudan yazma yolları ve ortak kullanıcı
  varsayımıyla uyum planı çıkarılmalı.
- UDS kabul edilecekse socket yolu, dizin izinleri, izinli UID/GID listesi,
  bağlantı başına credential kontrolü ve hata davranışı tanımlanmalı. PID
  tek başına kalıcı model kimliği sayılmamalı.
- Browser bridge/proxy kullanılacaksa backend'in yalnız bu bileşenden
  erişilebilirliği, dinleme adresi, cookie niteliği, CSRF/Origin koruması,
  loglarda sırların maskelenmesi ve oturum iptali belirlenmeli.
- HMAC kullanılacaksa verifier/nonce saklama izinleri, provision/rotation/
  revocation, canonical route, body boyutu ve imza doğrulaması sırası ile
  tekrar denemelerde domain işlemi idempotency'si belgelenmeli.
- Önce opt-in kurulumla uyumluluk gözlemlenmeli. Geçişte bilinçsizce anonim
  mutasyon erişimine geri düşülmemeli; auth/peer-check yapılamıyorsa istek
  kapalı şekilde reddedilmeli. Geri dönüş planı salt-okunur/servisi durdurma
  seçeneğini içermeli.

## Kaynaklar

- `panel/server.py:886-893` — Host/Origin denetimi ve aynı UID sınırı hakkındaki
  sunucu açıklaması.
- `panel/server.py:1035-1047` — API snapshot GET route'u.
- `panel/server.py:1059-1075` — POST kaynağı ve gövde işleme başlangıcı.
- `panel/server.py:1095-1113` — loopback varsayılanı ve loopback dışı bind reddi.
- `panel/AUTH_INTEGRATION_DRAFT.md:1-6, 8-31` — devre dışı HMAC entegrasyon
  taslağı ve route kapsamı.
- `README.md:105-140, 170-182` — kullanıcı servisi, ters vekil ve yerel UID
  güvenlik sınırı.
