# Yuva #669 — Auth-off görev/chat yazma yüzeyi statik incelemesi

**Sonuç:** Auth gate kapalıysa (`YUVA_AUTH_ENABLED` yok veya `0`) `H.do_POST()`
HMAC principal oluşturmadan JSON body'yi `UCLAR` callback'ine doğrudan verir.
Bu kipte loopback + Host/Origin + JSON Content-Type kontrolleri erişim yüzeyini
sınırlar; kullanıcı/principal kimliği doğrulamaz. Aynı OS UID altında çalışan
yerel süreçler bu panel API'sini çağırabilir; aynı UID'deki CLI/dev/restore
kopyaları da dosya yazma iznine sahipse HTTP katmanını atlayabilir. Bu nedenle
`kimden`, `kimlik`, rol veya loopback erişimi doğrulanmış principal değildir.

İnceleme yalnız `panel/server.py`, `panel/auth_integration_draft.py`,
`bin/yuva` ve mevcut #640/#611 kanıtlarının statik okunmasıdır. Canlı HTTP
isteği, servis/runtime/env sorgusu, gerçek ledger veya yeni test çalıştırması
yapılmadı. Çalışan panelin etkin auth ayarı bu incelemeden çıkarılamaz.

## Auth-off kaynak → route → writer

`auth_gate_yukle()` gate'i yalnız `YUVA_AUTH_ENABLED=1` iken kurar; yok/`0`
`None` üretir. `do_POST()` gate `None` olduğunda `fn(g)` dispatch eder. Bütün
route'lar kaynak denetiminden yine geçer: loopback istemci, doğrulanmış loopback
Host/port, varsa Host ile eşleşen Origin ve POST'ta JSON Content-Type. Origin
yokluğu desteklenir. Bu kontroller browser session veya kullanıcı yetkisi
değildir.

| POST route | Body'deki iddia / politika | Auth-off yazım yolu | Actor/provenance sonucu |
|---|---|---|---|
| `/api/katil` | `kimlik`, opsiyonel `rol`, `arac`, `ad` | `durum.json` roster kaydı/bağlı bayrağı; yeni kimlik yaratabilir, join duyurusu `mesaj.jsonl`'e eklenebilir | Principal yok; body kimliği kişi kanıtı değil. Rol geçişi yalnız ekip tutarlılığı kurallarına tabi. Heartbeat kanıtı sayılmaz. |
| `/api/kalp` | İstemci kimliği kullanılmaz | Her zaman `503`, `online:false`; writer çağrısı yok | Heartbeat kapalı; auth-off istisnası olarak mutate etmez. |
| `/api/ayril` | Hedef `kimlik` | `durum.json` içinde hedefin `bagli=false`/`duyuruldu=false`; ayrılma mesajı | Body hedefi caller kimliğine bağlanmaz; başka bir roster kaydını çevrimdışı işaretleme riski. |
| `/api/ad` | Hedef `kimlik`, yeni `ad` | `durum.json`; değişiklikte `mesaj.jsonl` durum satırı | Caller doğrulanmaz; başka kimliğin görünen adını değiştirebilir. |
| `/api/rol` | Hedef `kimlik`, `rol`, `bas_denetci` | `durum.json`; rol mesajı `mesaj.jsonl` | Geçiş helper'ı ekip bağlarını korur fakat caller/admin doğrulaması auth-off'ta yok; rol yetkisi atanabilir. |
| `/api/sorumlu` | Hedef `kimlik`, `sorumlu_kimlik` | `durum.json`, ardından audit `mesaj.jsonl` | Bağlantı şekli doğrulanır; actor doğrulanmaz. Audit append başarısızsa state mutasyonu kalmış olabilir ve API `503` belirsizliği bildirir. |
| `/api/bas-denetci` | Hedef `kimlik`, JSON boolean `etkin` | `durum.json`, ardından audit `mesaj.jsonl` | Tek baş denetçi tutarlılığı uygulanır; caller/admin doğrulaması auth-off'ta yok; audit ayrı yazımdır. |
| `/api/yaz` | `kimden`, `metin`, `kime`, `tur` | `mesaj.jsonl` ortak kilitli append | Bilinmeyen/insan claim'i authoritative actor olmaz; `actor_id=null`, `trust=unverified`, auth method `none`. `operator` claim'i reddedilir. Bu, doğru bir provenance sınırıdır; route yine içerik yazabilir. |
| `/api/ekran` | `kimlik`, `satir`, `tur` | `ekran/<güvenli-kimlik>.jsonl` ortak kilitli append ve redaction | Auth-off body kimliği filename/kayıt kimliği olur; kimlik doğrulaması/roster üyeliği kanıtı yok. |
| `/api/not` | Hedef `kimlik`, `not_` | `durum.json` kullanıcı notu | Auth-off callback erişilebilir; actor doğrulaması yok. HMAC gate açıkken route policy `closed` ve reddedilir. |
| `/api/gorev` | `islem`, `kimden`, görev alanları | `gorev_calistir()` → aynı süreçte canonical `bin/yuva` core → `YUVA_DIR/.kilit` → task ledger atomik writer | `kimden` body değeri `actor`/`--from` olur; principal değildir. History `actor_trust=local_unverified` olarak işaretlenir. Bazı işlemlerde kayıtlı rol/task-state kontrolleri vardır; bunlar caller'ın o kişi olduğunu kanıtlamaz. |

State ve JSONL yazımlarının çoğu panelin `KILIT`/`.kilit` koordinasyonunu
kullanır. Bu, aynı veri kökündeki canonical writer'ları serileştirir; kimlik
doğrulaması veya aynı-UID süreçlerine karşı erişim kontrolü değildir. Yönetim
state'iyle audit event'i tek atomik işlem değildir.

## Task actor güven sınırı

`gorev_calistir()` auth-off'ta non-empty `g.kimden` alanını actor olarak
seçer. `bin/yuva::run_task_operation()` bu kipte `principal=None` kabul eder;
task history kaydı da doğru şekilde `local_unverified` yazar. Worker/reviewer
handlers bazı durumlarda body'de seçilen aktörün `durum.json` rolünü ve görev
durumunu kontrol eder. Bu kontrol **rol etiketini** doğrular, HTTP caller'ın o
kimlik olduğunu doğrulamaz. Auth-off `/api/rol` ve `/api/katil` yolları da bu
roster/rol verisini değiştirebildiğinden, role check tek başına actor policy
değildir.

`api_yaz()` daha güvenli ayrım yapar: body'deki `kimden` yalnız gösterim/iddaa
alanı olur ve provenance actor'ı üretmez. Aynı yaklaşım task API için uygulanmış
değildir; görev tarafında yalnız `local_unverified` audit kaydıyla sınırlama
vardır. Görev/rol/admin kararlarında `kimden` principal gibi sunulmamalıdır.

## Auth açık kip ile fark

`YUVA_AUTH_ENABLED=1` ise eksik store/audience/config ile panel başlamaz; sessiz
auth-off fallback yoktur. `do_POST()` ham request'i authenticate eder, sonra
route ve payload policy uygular. `auth_integration_draft.py` politikasında
`/api/rol`, `/api/sorumlu`, `/api/bas-denetci` admin; `/api/ad` self/admin;
`/api/katil`, `/api/ayril`, `/api/ekran`, `/api/kalp` self; `/api/not` kapalı;
task operation'ları policy'ye bağlıdır. Bu HMAC protokolü browser session/CSRF
mekanizması değildir. #640 gerçek Handler fixture'ında sentetik callback'lerle
auth-off dalın 11 POST'un tamamını dispatch ettiği raporlanmış; gerçek
production callback yan etkilerinin o fixture'da sınanmadığı da belirtilmiştir.

## Risk ve karar

1. **Yüksek — auth-off POST'lar dispatch edilir.** Gate kapalı local-MVP kipinde
   bütün mutation route'ları (kalp hariç) API callback'ine ulaşabilir. Güven
   sınırı yerel/aynı OS hesabıdır; loopback ve Origin bu hesabı tanımlamaz.
2. **Yüksek — yönetim hedefi ve caller ayrışmıyor.** Rol, sorumlu, baş denetçi,
   not, ad ve ayrılma route'larında body hedefi korunur ama auth-off caller
   principal'ı yoktur. Alan doğrulamaları state tutarlılığı sağlar, yetki
   sağlamaz.
3. **Yüksek — task `kimden` self-asserted.** Kayıtlı rol/state checks actor
   iddiasını caller'a bağlamaz. History `local_unverified` bu farkı korur;
   downstream consumer bu etiketi doğrulanmış aktör saymamalıdır.
4. **Orta — state/audit ayrık commit.** `sorumlu` ve `bas-denetci` önce
   `durum.json` yazar, sonra audit JSONL append eder. Audit hatası sonrası
   mutation commit edilmiş, denetim kanıtı eksik olabilir.
5. **Sınırlı koruma — mesaj provenance.** `/api/yaz` kullanıcı/operatör
   iddialarını doğrulanmamış tutar ve operator claim'ini reddeder; bu koruma
   diğer kimlik/yönetim/task route'larına genellenmemelidir.

Auth-off davranış local MVP'nin açıkça seçilmiş kipidir; bu statik rapor tek
başına o kipin runtime'da etkin olduğunu söylemez. Servis same-UID dışı aktörlere
açılacaksa auth gate, route-specific policy ve task principal binding
zorunludur. Browser istemcisi için ayrıca gerçek session/CSRF gate gerekir.
Bu görev auth açmaz, route kapatmaz, UI veya servis değiştirmez; live access
veya production acceptance kararı vermez. Mevcut route davranışı için risk
kararı: **auth-off kullanımında tüm POST mutation yüzeyi aynı OS UID güven
sınırında; body actor/target değerleri doğrulanmış kimlik değildir.**

## Kaynaklar

- `panel/server.py`: `auth_gate_yukle`, `H.do_POST`, `_kaynak_denetimi`, `UCLAR`,
  `api_*`, `gorev_calistir`, `mesaj_ekle`, `admin_mutasyon_audit_ekle`.
- `panel/auth_integration_draft.py`: `POST_ROUTE_POLICY`, `authorize_payload`.
- `bin/yuva`: `_gorev_principal_dogrula`, `_gorev_rol_dogrula`,
  `run_task_operation`, `gorev_olay_ekle`, kilitli task handlers.
- [#640 Handler fixture raporu](panel-browser-session-handler-fixture-640.md)
  — gerçek handler auth gate sırası, sentetik callbacks, auth-off dispatch.
- [#611 task writer çağrı grafiği](task-writer-call-graph-611.md) — panel/CLI
  canonical task writer ve local-unverified actor sınırı.
