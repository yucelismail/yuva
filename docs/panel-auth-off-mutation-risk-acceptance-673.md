# Yuva #673 — Panel auth-off mutation risk kabul formu

**Tarih:** 2026-10-23
**İlişkili inceleme:** [#669 auth-off route incelemesi](panel-auth-off-mutation-route-review-669.md)
**Durum:** Operatör kararı bekliyor; bu belge tek başına risk kabulü veya canlı ortam beyanı değildir.

## Karar kaydı

Bu form, `YUVA_AUTH_ENABLED` yok/`0` iken panel POST yüzeyinin aynı OS UID güven sınırı içinde değerlendirilmesi için hazırlanmıştır. #669 statik kaynak incelemesinde `/api/kalp` dışındaki 10 yazabilir POST'un auth gate yokken callback'e dispatch edildiği görülmüştür. Servis ortamındaki gerçek auth ayarı bu incelemeden bilinmez. Loopback, Host/Origin ve JSON kontrolleri ağ/kaynak kısıtlarıdır; kullanıcı veya principal doğrulaması değildir.

**Değerlendirilen ortam/instance:** ______________________________
**Karar sahibi (veri/servis sahibi):** ______________________________
**Güvenlik gözden geçireni:** ______________________________
**Karar tarihi ve değişiklik kaydı:** ______________________________
**Karar:** ☐ Kabul et, sınırlı auth-off local MVP  ☐ Azaltım gerekli  ☐ Reddet / NO-GO
**Geçerlilik ve yeniden inceleme tarihi:** ______________________________

Karar yalnız aşağıda işaretlenen ortam, route, actor ve süre için geçerlidir. Boş alanlar kabul edilmiş sayılmaz. Ortam, bind, UID, route davranışı veya kullanıcı kitlesi değişirse karar yeniden alınmalıdır.

## Güven sınırı — açıkça kabul edilmesi gerekenler

- **Same-UID varsayımı:** Panel, CLI/dev/restore kopyaları ve yetkili aynı-UID yerel süreçler ortak dosya erişim sınırında kabul edilir. Bu süreçlerden herhangi biri HTTP API'yi çağırabilir veya uygun yazma izni varsa HTTP'yi atlayarak canonical writer'a ulaşabilir. Loopback erişimi bu süreçleri birbirinden ayırmaz.
- **Kimlik/provenance:** Auth-off request body içindeki `kimden`, `kimlik`, rol ve hedef değerleri self-asserted girdidir. `/api/gorev` history'sindeki `actor_trust=local_unverified` doğrulanmış kullanıcı demek değildir. `durum.json` rol/state kontrolleri actor'ın gerçekten o kimlik olduğunu kanıtlamaz.
- **Ağ/istemci:** Auth-off kontrolleri uzak erişim veya browser session/CSRF kimlik doğrulaması sağlamaz. Kullanıcı kitlesi aynı yerel UID sınırının dışına çıkıyorsa bu form olumlu kabul vermek için kullanılamaz.
- **Audit bütünlüğü:** `/api/sorumlu` ve `/api/bas-denetci` state mutasyonu ile JSONL audit append ayrı yazımlardır; append hatası/crash halinde state commit edilmiş ama audit eksik kalmış olabilir.
- **Canlılık kanıtı:** #669 statik kaynak incelemesidir; servis/env/runtime ya da gerçek ledger gözlemi değildir. Bu formun hazırlanması auth-off'un şu anda açık olduğunu veya riskin sahibi tarafından kabul edildiğini göstermez.

Bu maddelerden biri gerçek işletim varsayımına uymuyorsa karar **NO-GO** olmalı veya risk azaltımı tamamlanana dek askıda kalmalıdır.

## Route bazında kapsam ve risk kararı

Her satırda ortamda route'un gerekli olup olmadığı, kabul edilen çağıran kümesi, veri/iş etkisi ve karar belirtilmelidir. “Gerekli” seçimi çağıranı doğrulamaz; yalnız işlev gereksinimidir.

| Yazabilir POST | Auth-off etkisi (#669) | Ortamda gerekli? | Kabul edilen çağıran/UID sınırı | Karar / gerekçe |
|---|---|---|---|---|
| `/api/katil` | Roster kaydı/bağlı bayrağı; yeni kimlik ve join mesajı oluşabilir. Body kimliği kişi kanıtı değildir. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/ayril` | Body hedefini `bagli=false`/`duyuruldu=false` yapar ve mesaj yazabilir; hedef caller'a bağlanmaz. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/ad` | Hedef roster kaydının görünen adını ve mesaj kaydını değiştirebilir. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/rol` | Hedefin rolünü değiştirebilir; ekip tutarlılığı caller/admin yetkisi sağlamaz. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/sorumlu` | Sorumlu ilişkisini değiştirir; audit ayrı append edilir ve sonuç belirsiz kalabilir. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/bas-denetci` | Baş denetçi atamasını değiştirir; tekil atama kuralı caller yetkisi sağlamaz, audit ayrıdır. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/yaz` | Ortak mesaj JSONL'ına içerik yazar. Body kimden/id iddiası unverified kalır; `operator` iddiası reddedilir. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/ekran` | Body kimliğiyle ekran JSONL kaydı yazar; kimlik doğrulaması/roster üyeliği kanıtı değildir. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/not` | Hedefin durum kaydındaki kullanıcı notunu değiştirir. Auth açık route policy'sinde kapalıdır. | ☐ Evet ☐ Hayır | __________________ | __________________ |
| `/api/gorev` | Mesaj/görev API işlemlerini canonical task writer'a iletebilir. `kimden` self-asserted actor olur; history `local_unverified` olarak işaretlenir. | ☐ Evet ☐ Hayır | __________________ | __________________ |

`/api/kalp` listeye dahil değildir: #669 incelemesinde `503 online:false` döndürdüğü ve writer çağırmadığı belirtilmiştir. Değişiklik olursa bu karar formunun route envanteri yenilenmelidir.

## Kapsam sınırları

Karar sahibi aşağıdakileri doldurup onaylamalıdır:

- **Bind/erişim yeri:** ______________________________
- **OS servis UID ve aynı UID'de çalışan yerel araçlar:** ______________________________
- **Kullanıcı kümesi:** ☐ yalnız güvenilen aynı-UID süreçleri ☐ başka yerel kullanıcılar ☐ browser kullanıcıları ☐ başka: __________
- **Kapsamdaki route'lar:** ______________________________
- **Kapsam dışı route/işlemler ve kapalı tutulma kanıtı:** ______________________________
- **İzin verilen değişiklikler/veri sınıfları:** ______________________________
- **Azami kabul süresi ve kapanış tetikleri:** ______________________________
- **İzleme ve olay müdahalesi sahibi:** ______________________________

Başka OS UID, paylaşılan hesap, browser kullanıcısı veya aynı makinede güvenilmeyen süreç varsa auth-off local-only kabul varsayımı karşılanmaz. Bu durumda route'ları açık bırakmak için bu form yeterli değildir; bağımsız kimlik/policy ve uygun session/CSRF tasarımı gibi azaltımlar ve yeni kabul gerekir.

## Seçilen karar ve azaltımlar

**Mevcut risk için karar:** ☐ Kabul (yalnız tanımlı sınırlı local MVP) ☐ Azaltım sonrası yeniden değerlendir ☐ Reddet
**Kararın gerekçesi:**

____________________________________________________________________

**Gerekli azaltımlar, sorumlusu ve tamamlanma kanıtı:**

| Azaltım | Sorumlu | Son tarih | Kanıt / durum |
|---|---|---|---|
| Same-UID sınırını doğrula veya ayrı UID/custody kur | __________ | __________ | __________ |
| Gerekli route'ları daralt/kapat ya da route-specific auth/policy kabul et | __________ | __________ | __________ |
| Task actor'ını doğrulanmış principal'a bağla veya local_unverified sonucunu tüketicilerde koru | __________ | __________ | __________ |
| State + audit ayrık commit ve belirsiz sonuç için işletim prosedürü belirle | __________ | __________ | __________ |
| Browser erişimi varsa session/CSRF güven sınırını kabul et | __________ | __________ | __________ |

Azaltım seçimi bu görevde uygulanmaz. Route, servis, kod ve canlı veri değişikliği ayrı yetki/iş kapsamıdır.

## Operatör onayı

İmza, yalnız yazılı ortam/kapsam/süreyi ve yukarıdaki `local_unverified` same-UID riskini kabul eder. Boş checkbox veya imza, bilinmeyen runtime durumunu doğrulamaz.

- **Karar sahibi adı/rolü:** ______________________________
- **İmza veya değişiklik kaydı referansı:** ______________________________
- **Tarih:** ______________________________
- **Bağımsız gözden geçiren:** ______________________________
- **Gözden geçirme sonucu/tarihi:** ______________________________

## Bu teslimin sınırı

Form #669 statik raporundaki 10 yazabilir POST'u ve `local_unverified` actor sınırını operatör kararına taşır. Kaynak incelemesi dışında kod/route/servis/gerçek veri değiştirilmedi; canlı auth ayarı sorgulanmadı; form adına bir risk kabul kararı verilmedi.

## Kaynaklar

- `docs/panel-auth-off-mutation-route-review-669.md` — route etkileri, auth-off caller/provenance sınırı ve statik inceleme kapsamı.
- `docs/panel-browser-session-handler-fixture-640.md` — sentetik callback'li Handler fixture'ı; gerçek production callback yan etkileri kapsamı değildir.
- `docs/task-writer-call-graph-611.md` — task writer çağrı grafiği ve local-unverified actor sınırı.
