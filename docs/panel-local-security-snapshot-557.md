# Yuva #557 — Panel yerel güvenlik yüzeyi ve snapshot sınırı

**Durum:** Güncel kaynaklar ve önceki #534/#538/#562 kararları arasında statik
fark analizi. Auth ayarı, credential, görev/veri, servis veya canlı HTTP
değiştirilmedi; çalışan deployment ve gerçek erişim topolojisi doğrulanmadı.

## Sonuç: açık kalan karar

Panelin `127.0.0.1` bind'i ağdan doğrudan dinlemeyi sınırlar; Host/Origin
kontrolleri istek hedefi ve tarayıcı kaynak filtresidir. Kaynakta HTTP istemci
UID'sini (`SO_PEERCRED` benzeri) doğrulayan bir kapı yok. Dolayısıyla tek
güvenilir OS UID'li MVP varsayımı, HTTP snapshot yolunda teknik olarak aynı UID
ile sınırlandırılmış değildir: aynı network namespace'ten localhost'a
ulaşabilen başka bir UID de anonim GET'e erişebilir.

Bu kalan fark, önceki bulguların tekrarından ziyade karar etkisidir:

- #538'deki kaynak filtresi POST için çapraz-origin browser/CSRF ve
  DNS-rebinding yollarını daraltır; caller kimliği ya da GET yetkilendirmesi
  sağlamaz.
- #562, tüm yanıt yollarına `nosniff`, `no-referrer` ve `X-Frame-Options:
  DENY` eklemiştir. CSP uygulanmamıştır; bu tarayıcı katmanı konusu da anonime
  açık snapshot kararını değiştirmez.
- #455/#526'da bırakılan anonim snapshot kararı hâlâ açıktır: `GET /api/veri`
  ve compatibility alias `/veri`, ayrıca UI `GET /` ve `/index.html`, HMAC
  POST kapısından geçmez. `YUVA_AUTH_ENABLED=1` olması bunları korumaz.
- Auth kapalıyken POST handler'ları legacy/güvenilmeyen client actor alanlarıyla
  çalışır. Bu, yalnız “aynı kullanıcıya ait CLI” demek değildir; localhost'a
  HTTP kurabilen istek sahibi kaynak filtresini geçip yazma yüzeyine gelebilir.
  Gerçek etkin auth modu bu incelemede okunmadı.

Bu nedenle operatör, ilk MVP'nin tehdit modelini şu iki seçenekten biriyle
karara bağlamalıdır: (A) snapshot ve auth-off yerel HTTP yazımlarına erişebilen
tüm yerel loopback süreçlerini güvenilir saymak; veya (B) erişimi tek UID / dar
browser oturumuyla sınırlayan OS peer-credential/broker ya da oturumlu proxy
gibi ayrı bir sınır tasarlayıp kanıtlamak. Mevcut kaynak tek başına (B)'yi
sağlamaz. Bu karar verilmeden paneli çok kullanıcılı ya da ajan UID'leri arasında
güvenli ortak veri yüzeyi gibi sunmak doğru değildir.

## Tarayıcıdan erişilebilir veri

`panel/server.py:do_GET()` kaynak/Host denetiminden sonra `veri()` çağırır.
`veri()` durum ve görev snapshot'ını kilit altında tutarlı okur; `no-store`
cache politikasıdır, erişim kontrolü değildir. Snapshot alanları:

| Alan | Kaynakta dönen içerik | Browser güvenlik anlamı |
|---|---|---|
| `kullanicilar` | Kimlik/görünen ad, araç, kayıtlı rol, baş-denetçi/sorumlu bağları, katılma/son okuma ve not alanları. Presence alanları sabit `online=false`, `presence_state=unknown`, `presence_verified=false`; `son_gorulme`/`son_kalp` null. | Roster/iş ilişkileri ve notlar anonim okunur; presence doğrulaması/agent oturumu göstermez. |
| `gorevler` | Görev nesneleri `gorev_oku()` çıktısı olarak bütün halinde verilir; başlık/detay, atama, durum ve geçmiş gibi iş içeriği bulunabilir. | Sadece UI'da görünür kartların gizlenmesi veri erişim sınırı değildir. Snapshot alanı API yanıtında kalır. |
| `mesajlar` | `MESAJ_SN=200` ile son 200 sohbet kaydı. | Serbest metin olası sır/kişisel içerik barındırabilir; UI hedef filtresi veya okundu eşiği anonim API erişimini daraltmaz. |
| `ekranlar` ve `ekranlar_meta` | Kaydedilmiş ekran satırları; model başına seçilmiş sayfa, dosya tarama/çıktı byte sınırları ve redaksiyon yordamı bulunur. | Redaksiyon ile sayfa/bütçe hassas verinin tamamının çıkarıldığını veya okuyucunun yetkili olduğunu kanıtlamaz. Kayıtlı terminal içeriği hâlâ hassas olabilir. |
| `rev`, `simdi`, `online_sn` | Snapshot sürüm/zaman ve presence TTL bilgisi. | Sistem işleyişi hakkında metadata; kimlik veya çevrimiçi kanıtı değildir. |

Tarayıcı paneli aynı origin'den `/api/veri` çağırıp snapshot'ı render eder. `GET
/`, `/index.html`, `/api/veri` ve `/veri` için kaynak kodda principal/session
kontrolü yoktur. CORS izni üretmemek çapraz-origin JavaScript'in yanıtı
okumasını sınırlar; localhost'a erişebilen süreçleri, kullanıcı navigasyonunu
ve aynı-origin paneli yetkilendirmez.

## Rota bazında yetki iddiaları

| Yüzey | Auth kapalı / kaynakta varsayılan yol | HMAC POST açıkken kaynak davranışı | Gerçek sınır ve açık nokta |
|---|---|---|---|
| `GET /api/veri`, `/veri` | Anonim snapshot okuma. | Değişmiyor; GET gate'e bağlı değil. | KOK izinleri bu HTTP yanıtını korumaz; istemci UID'si denetlenmiyor. |
| `GET /`, `/index.html` | Anonim UI HTML'i; UI snapshot'ı ayrıca anonim GET eder. | Değişmiyor; HTML/browser session yok. | HTML auth gate değildir. HMAC sırrı tarayıcıya konmamalı; oturum/proxy ayrıca tasarlanmalı. |
| `POST /api/gorev` | Request body'deki `kimden` aktör etiketi ile CLI task operation çalışır. Başlık/Origin/JSON kontrolleri caller'ı doğrulamaz. | HMAC principal + operation policy gerekir; ekle/ata/iptal admin, al/sonraki/teslim worker, ilk-kontrol/denetle reviewer scope'u. | Auth-off durumda body actor güvenilir kimlik değildir. Auth-on davranışının canlıda açık olduğu bilinmiyor; mevcut auth kullanımı/görev geçmişi tek başına tam audit trail değildir. |
| `POST /api/rol`, `/api/bas-denetci`, `/api/sorumlu` | Legacy yol rol/yetki/iş yönlendirme durumunu değiştirebilir. | Provision edilmiş principal ve admin policy kapısı. | Auth kapalı çalışma kritik yetki değişikliğini anonymous loopback HTTP'ye bırakır; production etkinliğini doğrulamadık. |
| `POST /api/yaz`, `/api/ekran`, `/api/ad`, `/api/katil`, `/api/ayril`, `/api/not` | Handler'a göre mesaj/ekran, roster veya profile durumunu değiştirebilir; istemci kimlik alanları auth kanıtı değildir. | Route policy ve principal bağları devreye girer; `/api/not` gate-on modda kapalıdır. | Auth kapalı modda bu da ayrı UID/yerel çağıran ayrımı yapmaz. Ekran ve mesaj yazımı redaction/retention sınırlarından ayrıca geçmelidir. |
| `OPTIONS`, hatalı origin/Host ve form POST | `OPTIONS 405`, CORS allow header yok; `Origin` mevcutsa loopback Host authority ile eşleşmeli, POST JSON olmalı. | Aynı kaynak kontrolleri. | Bunlar browser isteğini filtreler; bearer principal, izin veya server peer UID'si üretmez. `Origin` bulunmayan CLI çağrıları kabul edilir. |

Auth kapısı kaynakta açıkça yapılandırılınca yanlış/eksik config ile anonim
fallback yerine startup hatası verir; bu fail-closed davranış canlı env'in doğru
kurulduğunu göstermez. Auth store ve KOK tek UID sahibine aittir. Aynı UID'deki
başka süreçlere karşı store secret'ı veya yerel dosya/API erişimi ayrıcalık
sınırı değildir.

## Önceki incelemelere göre yalnız kalan riskler

1. **MVP varsayımı ile HTTP peer sınırı uyuşmuyor.** #536 tek güvenilir UID'yi
   ürün varsayımı yapar; HTTP GET ve auth-off POST kaynakta peer UID'yi
   denetlemez. Farklı UID aynı loopback namespace'e erişebiliyorsa bu erişim
   sınırının dışında kalır. Dağıtım namespace'i/başka UID erişimi kanıtlanmadı.
2. **Snapshot en az yetkiyle daraltılmıyor.** Birleşik endpoint roster, tüm
   task nesneleri, sohbet ve ekran verisini ortak cevapta döndürür. Ekran
   redaksiyonu ve byte cap tek başına alan bazlı yetkilendirme veya hassas
   içerik sınıflandırması değildir.
3. **Auth-off mutation yüzeyi ürün kararına bağlı.** Kaynakta gate default-off;
   bu modda POST işlemleri `kimden`/`kimlik` iddialarını kullanabilir. Aynı
   makinedeki yerel istemcilerin tümüne bu yetki verilmesi, tek operatör
   threat-model'inin açık kabulüdür; rol/actor doğrulaması değildir.
4. **Auth-on kapsam GET/browser session'ı çözmez.** HMAC POST policy'si bile
   anonim snapshot/HTML'yi kapatmaz. Tarayıcı session'ı, GET scope, backend'e
   doğrudan erişimi kapatma, key rotation/revoke ve multi-UID broker kararı
   ayrı mimaridir.
5. **CSP geçişi açık.** #562 ortak güvenlik response başlıklarını ekler; CSP
   inline script/style ve dinamik style attribute'lar temizlenmeden uygulanmış
   değildir. CSP kalan tarayıcı savunmasıdır; kimlik doğrulamaya alternatif
   değildir.
6. **Deployment doğrulaması yok.** `YUVA_AUTH_ENABLED`, servis `Environment`,
   gerçek bind/network namespace, proxy/tunnel, browser profile/extensions,
   snapshot içerik sınıflandırması ve KOK erişimi canlı sistemde kontrol
   edilmedi. Kaynak raporu canlı erişim ya da güvenli dağıtım sonucu çıkaramaz.

## Karar gerektiren kapılar — uygulamadan ayrı

| Karar | Mevcut kaynakta otomatik varsayılan | Operatörün kabul etmesi gereken nokta |
|---|---|---|
| Tek kullanıcı panelini hangi süreçler okuyabilir? | Loopback GET erişen UID için principal şartı yok. | Aynı host/network namespace'teki tüm loopback erişebilen süreçlere snapshot açmak kabul mü? Hayırsa broker/peer UID/proxy tasarım ve host kabulü gerekir. |
| Snapshot'ın alanları/hassasiyeti | Tüm gruplar tek anonymous snapshot'a girer. | Chat/screen/task detail, actor/reviewer alanı ve profile notes için veri minimizasyonu/redaction kapsamı onaylanmalı. |
| Auth-off POST yazımı | Gate yoksa legacy handler çağrılır. | Auth-off altında görev/rol/profile mutasyonlarının tüm localhost istemcilerine açık olması kabul mü? Çok kullanıcılı ya da güvenilir actor gereksiniminde auth/policy açılmadan Go verilmemeli. |
| HMAC/browser modeli | HMAC kapısı POST odaklıdır; HTML secret saklamaz. | Auth etkinleştirilecekse provision edilmiş store/audience/admin listesi ve browser için ayrı session/proxy tasarımı gerekir; bu kaynak incelemesi bunları etkinleştirmez. |
| Yayın koşulu | README/#536 tek-operatör private MVP sınırı önerir; gerçek çalışan servis doğrulanmış değil. | Kaynak, release, tek writer, YUVA_DIR, network namespace ve auth mode operatör kanıtlarıyla eşleşmeli; aksi halde paneli güvenli hizmet olarak tanıtma. |

Bu görev kapsamında bu seçeneklerden hiçbiri seçilmedi veya uygulanmadı. “Tek
güvenilir UID” varsayımı dışında bir güvenlik gereksinimi varsa, ürün/release
kararı gelmeden auth bayrağı, snapshot alanları veya servis erişimi değiştirilmez.

## Kaynaklar

- `panel/server.py`: `H.end_headers`, `_kaynak_denetimi`, `do_GET`, `do_POST`,
  `gorev_calistir`, `veri`, `mesajlar`, `tum_ekranlar`, `auth_gate_yukle`.
- `panel/ui.html`: `/api/veri` fetch'i ve snapshot render akışı.
- `docs/panel-origin-csrf-538.md`: uygulanmış Host/Origin/Content-Type
  kontrolleri ile kimlik doğrulama sınırı.
- `docs/panel-http-security-headers-cache-policy-534.md` ve
  `docs/panel-security-response-headers-562.md`: başlık durumu ve CSP'nin
  halen uygulanmamış olması.
- `docs/local-api-get-snapshot-decision-455.md`,
  `docs/panel-api-route-scope-matrix-526.md`: GET/auth route kapsamı ve
  operatör kararları.
- `docs/first-local-mvp-scope-go-no-go-536.md` ve
  `docs/shared-repo-data-ownership-533.md`: tek UID varsayımı, KOK sahipliği ve
  panelin UID sınırı olmadığı.

İnceleme statik kaynakla sınırlıdır; gerçek GET yanıtı, auth flag, browser
erişimi veya servis/deployment durumu ölçülmedi.
