# ADR 451: Yerel API erişim sınırı

- **Durum:** Karar kaydı; uygulama veya dağıtım değişikliği değildir.
- **Tarih:** 2026-10-21
- **Kapsam:** Panelin yerel HTTP API'si, CLI/broker istemcileri ve farklı Unix UID'leri.

## Karar

Desteklenen varsayılan dağıtım tek, güvenilen Unix UID'sidir. Panel loopback
(`127.0.0.1`) üzerinde kalır; veri kökü ve kayıtlar yalnız bu UID'ye açık
tutulur. Loopback uzak ağdan doğrudan erişimi daraltır, fakat aynı network
namespace'teki başka UID'leri engellemez ve çağıranın kimliğini kanıtlamaz.
`Host`, `Origin` ve içerik biçimi kontrolleri de kimlik doğrulama değildir.

Aynı UID altındaki süreçler dosya izinleri ve UID tabanlı socket kontrolleriyle
birbirinden ayrılamaz. Bu süreçler aynı API ve veri kökü güvenini paylaşır.
Farklı UID'nin API erişiminin engellenmesi bir gereksinimse, mevcut loopback
HTTP tek başına uygun sınır değildir.

## Taşıma ve token seçenekleri

| Seçenek | Sağladığı sınır | Sağlamadığı / koşulu |
|---|---|---|
| Loopback HTTP | Uzak arayüzlerde dinlemeyi önler. | Yerel UID'leri ayırmaz; localhost erişimi kimlik kanıtlamaz. |
| HTTP HMAC token | Anahtarı olan istemcinin imzalı isteğini ve principal'ını doğrulayabilir; CLI/broker için uygundur. | Anahtar dağıtımı/iptali gerekir; aynı UID'deki süreçlerden gizli değildir. Tarayıcıya sır konmamalı. GET ve browser oturumunu kapsamaz. |
| UDS + `SO_PEERCRED` | Kernel'in bağlantı UID/GID/PID bilgisini alıp izinli UID'leri sınırlayabilir. | UID aynıysa süreçleri ayıramaz; model/ajan kimliğini kanıtlamaz. Tarayıcı UDS'ye doğrudan bağlanamaz. |
| Ayrı servis UID'si + UDS | API'yi özel UID altında tutup socket izinleri ve peer UID allowlist'iyle farklı yerel UID'leri ayırabilir. | CLI/broker geçişi ve veri sahipliği düzeni gerektirir. Tarayıcı için ayrıca kontrollü HTTP köprüsü/vekil ve oturum/CSRF politikası gerekir. |

HMAC, gerektiğinde UDS/servis UID'sine ek bir istemci principal katmanı olabilir;
işletim sistemi izolasyonunun veya dosya erişim sınırının yerine geçmez.
Mevcut kodda HMAC kapısı `YUVA_AUTH_ENABLED=1` ile açıkça yapılandırılmadıkça
kapalıdır; açıkken POST isteklerine uygulanır. `GET /api/veri` ve tarayıcı
oturumu için auth sağlamaz. Bu ADR auth'ı etkinleştirmez.

## Geçiş yolu ve kapılar

1. Farklı UID izolasyonunun gerekip gerekmediğini ve korunacak GET/POST
   verilerini, özellikle birleşik `/api/veri` snapshot'ını, sınıflandır.
2. Gerekliyse hedef servis/istemci UID'lerini, veri kökü sahipliğini ve mevcut
   doğrudan dosya yazıcılarının geçişini belirle. Socket dizini/yolu,
   izinleri, peer UID allowlist'i ve reddetme davranışını tanımla.
3. Paneli ayrı servis UID'sine taşı; CLI/broker erişimini UDS üzerinden geçir.
   Tarayıcı gerekiyorsa loopback köprüsünü/vekilini ayrı oturum, cookie ve
   CSRF/Origin kurallarıyla tasarla; backend'e doğrudan yerel erişimi kapat.
4. İmzalı ajan/broker principal'ı gerekiyorsa HMAC'i ayrıca devreye al; GET
   yetkilendirmesini ve anahtar provision/rotation/revocation sürecini de
   tanımla. Auth veya peer denetimi hatasında anonim erişime düşme.
5. Geri dönüşte kimliksiz backend'i farklı UID'lere açma; gerekirse servisi
   durdur veya tek güvenilen UID dağıtımına dön.

Bu geçiş kapıları kapanmadan farklı UID'lerle ortak API kullanımı desteklenen
güvenli dağıtım sayılmaz. Yeni auth etkinleştirme, kod değişikliği ve test bu
görevin kapsamı dışındadır.

## Dayanak

- [Yerel API erişim sınırı](local-api-access-boundary.md)
- [Yerel veri tehdit modeli](local-data-threat-model.md)
- `panel/server.py`: loopback dışı bind reddi, isteğe bağlı HMAC yapılandırması,
  POST doğrulama akışı ve auth kapalıyken mevcut uyumluluk davranışı.
