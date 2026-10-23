# #655 — Panel anonim GET erişim sınırı: operatör karar matrisi

**Durum:** Doldurulacak operatör kararı; erişim modeli seçilmedi veya
etkinleştirilmedi.
**Tarih:** 2026-10-23
**Kapsam:** Panel HTML'i ve anonim olabilecek GET snapshot yollarının amaçlanan
okuyucu, veri kapsamı ve kabul kanıtı. Bu belge kaynak/deployment incelemesini
veya canlı erişim testini yapmış sayılmaz.

## Karar kaydı

| Alan | Operatör kararı |
|---|---|
| Panel/veri sahibi | ______________________________ |
| Kurulum ve canonical release referansı | ______________________________ |
| Etkin data root referansı | ______________________________ |
| Hedef kullanıcı/okuyucu grupları | ______________________________ |
| Karar sahibi ve reviewer | ______________________________ |
| Politika sürümü / onay tarihi | ______________________________ |
| Sonraki gözden geçirme tarihi | ______________________________ |

## Kaynakta görünen bugünkü sınır

Kaynak incelemesindeki GET dispatch şu yolları anonim olarak sunuyor:

| Yol | Kaynak davranışı | Kararda cevaplanacak soru |
|---|---|---|
| `GET /api/veri` | Birleşik snapshot: roster, görevler, sohbet ve ekran; GET auth gate bağlı değil. | Hangi okuyucular bu içerik gruplarını alabilir? |
| `GET /veri` | Snapshot için compatibility alias; ayrı bir gate yok. | `/api/veri` ile aynı auth/scope ve cache politikası mı? |
| `GET /` ve `/index.html` | Panel HTML'i anonim; browser sonra snapshot GET'i yapar. | HTML'yi kim açabilir ve backend'e doğrudan erişim nasıl kapanır? |
| Başka GET target | Route lookup dışında snapshot yetkisi tanımlı değil. | Bilinmeyen ve canonical olmayan target'lar nasıl reddedilecek? |

Bu, kaynak kod durumudur; çalışan service env'i, proxy, host network namespace,
başka UID erişimi veya gerçek GET yanıtı burada doğrulanmadı. `YUVA_AUTH_ENABLED`
POST gate'idir; GET veya browser session'ı açıp kapattığı varsayılamaz.

## 1. Amaçlanan okuyucu ve yerel güven sınırı

Her birini işaretleyin; bu kurulumda `localhost` ve panel HTML'ine erişebilen
her süreç/kişi için geçerli olduğunu doğrulayın.

| Okuyucu durumu | Seçim | Kanıt / sahibi |
|---|---|---|
| Tek insan operatör; aynı UID ve loopback namespace'teki tüm yerel süreçler güvenilen | [ ] evet · [ ] hayır | ______________________________ |
| Aynı UID altında güvenilmeyen agent/tool/browser extension çalışıyor | [ ] evet · [ ] hayır · [ ] bilinmiyor | ______________________________ |
| Aynı network namespace'te başka UID süreçleri localhost'a ulaşabiliyor | [ ] evet · [ ] hayır · [ ] bilinmiyor | ______________________________ |
| Tarayıcı başka kullanıcıya, paylaşılan profile veya uzaktan proxy'ye açılacak | [ ] evet · [ ] hayır | ______________________________ |
| Loopback dışı bind, tunnel, reverse proxy veya port-forward var | [ ] evet · [ ] hayır · [ ] bilinmiyor | ______________________________ |

`bilinmiyor` veya çelişen kanıt, tam anonim snapshot için **NO-GO** bırakır.
Loopback, `Host`/`Origin`, CORS, `no-store` ve file permissions HTTP caller
kimliği doğrulamaz. Aynı UID altındaki süreçleri UID/socket kontrolü ayırmaz.

## 2. Erişim modeli seçimi

Tam anonymous GET'i varsayılan kabul etmeyin. Bir model seçip koşullarını
kanıtlayın; A/B/C birbirinin yerine geçmez.

| Model | Operatör seçimi | Ne sunar | Asgari kabul şartı ve sınır |
|---|---|---|---|
| **A — İnsan-only yerel istisna** | [ ] seç · [ ] reddet | Mevcut tam anonim HTML ve snapshot akışını korur. | Yalnız ayrı, insan-only host/namespace'te değerlendirilebilir. Untrusted agent/tool veya başka UID localhost'a erişebiliyorsa reddedilir. Erişim topolojisi sahibi ve test kanıtı gerekir. |
| **B — Anonim, minimize özet** | [ ] seç · [ ] reddet | Anonimde sadece açıkça onaylanmış düşük hassasiyetli health/roster özeti; task serbest metni/history, chat metni ve screen satırları çıkarılır. | Alan allowlist'i, amaçlanan okuyucu, kısmi veri semantiği ve UI'nin eksik listeyi tam saymama kabulü gerekir. Bu model kimlik doğrulama değildir; auth-off POST write riskini ayrıca çözmez. |
| **C — Doğrulanmış GET ve browser erişimi** | [ ] seç · [ ] reddet | Hassas snapshot sadece onaylı CLI/broker veya browser session üzerinden erişilir. | Exact GET route/scope (iki snapshot path ve HTML dahil), browser session/cookie, CSRF/Origin, logout/expiry/revoke; backend'e direct anonymous erişimin kapatılması ve fail-closed hatalar. HMAC sırrı tarayıcıya konmaz. Same-UID ajanları ayırmak gerekiyorsa ayrı OS sınırı/proxy gerekir. |

**Seçilen model:** ______
**Seçimin kapsamı / istisna gerekçesi:** ____________________________________

Mevcut varsayılan çok-agent/same-UID kullanımında, agent/tool'lar loopback
GET'e erişebiliyorsa Model A tam snapshot için **NO-GO**'dur. Model B geçici
veri azaltımıdır; yetkilendirme veya POST koruması sayılmaz. Model C ancak
uygulanıp exact-route ve rollout kabulünden sonra GO adayı olur.

## 3. Snapshot alanı ve okuyucu matrisi

Anonim özet seçilirse her satır için karar verin. “UI'da gizli” kararı API
yanıtından çıkarıldığı anlamına gelmez; sunucu projection'ı değişmelidir.

| Grup | Hassasiyet / risk | Anonime dahil? | Amaçlanan okuyucu / asgari alan |
|---|---|---|---|
| Roster: kimlik, görünen ad, araç, rol, hiyerarşi | Çalışma kimliği/organizasyon metadata'sı | [ ] evet · [ ] hayır · [ ] azalt | ______________________________ |
| Profile `not_`, `son_okuma`, `bagli` | Serbest metin / davranış metadata'sı; bazıları UI'da tüketilmiyor | [ ] evet · [ ] hayır | ______________________________ |
| Görev başlığı/durumu/atama | İş akışı ve ekip bilgisi | [ ] evet · [ ] hayır · [ ] yalnız özet | ______________________________ |
| Görev detay/geçmiş/not/actor | Serbest metin, hassas iş bilgisi veya güvenilmeyen içerik | [ ] evet · [ ] hayır | ______________________________ |
| Chat metadata | Kimlik/hedef/zaman/tür ve provenance | [ ] evet · [ ] hayır · [ ] azalt | ______________________________ |
| Chat `metin` | Kullanıcı içeriği, kişisel bilgi veya yanlışlıkla yazılmış sır | [ ] evet · [ ] hayır | ______________________________ |
| Screen `satir` / terminal | Komut, path, serbest çıktı ve credential riski; redactor tam DLP değildir | [ ] evet · [ ] hayır | ______________________________ |
| Partial/limit metadata (`ekranlar_meta`, `snapshot_meta`) | Sistem kullanım/iş yükü hakkında bilgi | [ ] evet · [ ] hayır · [ ] azalt | ______________________________ |
| Sürüm/zaman/presence alanları | Operational metadata; kimlik veya liveness kanıtı değil | [ ] evet · [ ] hayır · [ ] azalt | ______________________________ |

**Alan allowlist sürümü ve owner:** ________________________________________

## 4. GET ve browser politika tablosu

Seçilen model için tüm yollar aynı kararın içinde bulunmalıdır.

| Kontrol | Karar / gereksinim |
|---|---|
| `/api/veri` route ve read scope | ______________________________ |
| `/veri` alias: aynı policy mi, kapalı mı? | ______________________________ |
| `/` ve `/index.html` HTML erişimi | ______________________________ |
| Query, body, duplicate/unknown header veya canonical olmayan target | ______________________________ |
| Hatalı/eksik auth, expired/revoked session, store/broker unavailable | [ ] 401/403/503 ve snapshot yok · [ ] başka (gerekçe): __________ |
| Cache/browser history/service worker davranışı | ______________________________ |
| Browser session: cookie flags, CSRF/Origin, expiry ve logout/revoke owner | ______________________________ |
| Proxy varsa backend'e direct erişim kapısı ve trusted proxy kaynağı | ______________________________ |
| GET HMAC seçilirse CLI/broker key custody, scope, replay/nonce lifecycle | ______________________________ |

`OPTIONS`, CORS, `Origin`/`Host` ve CSP kontrolleri erişim yetkisi değildir.
Unknown route/query/path davranışı, exact dispatch ve auth kararıyla birlikte
uygulama fixture'ında kanıtlanmalıdır.

## 5. Ayrı POST yazma kararı

Anonim GET kararı POST güvenliği yerine geçmez. GET kapısı açılsa bile auth-off
legacy POST davranışı ayrı değerlendirilmelidir.

| Mutasyon sınıfı | Auth kapalı kullanım kabul mü? | Owner / uygulanacak politika |
|---|---|---|
| Görev add/assign/take/review/complete | [ ] evet · [ ] hayır · [ ] bilinmiyor | ______________________________ |
| Chat ve screen write | [ ] evet · [ ] hayır · [ ] bilinmiyor | ______________________________ |
| Roster, role, responsible, supervisor değişiklikleri | [ ] evet · [ ] hayır · [ ] bilinmiyor | ______________________________ |
| Actor iddiası (`kimden`, `kimlik`, `--from`) güven seviyesi | [ ] `local_unverified` · [ ] doğrulanmış principal gerekli | ______________________________ |

İhtiyaç doğrulanmış actor/admin ise auth-on, key provisioning/revocation,
admin allowlist ve task operation scope'u ayrıca kabul edilmelidir. Auth flag
ya da rol politikası bu karar formuyla etkinleştirilmez.

## 6. GO / NO-GO karar kapısı

**NO-GO** kalır, eğer herhangi biri doğruysa:

- [ ] Okuyucu/UID/network namespace veya proxy topolojisi bilinmiyor.
- [ ] Untrusted agent/tool, aynı UID/loopback altında tam anonymous snapshot'a erişebiliyor ve bu kapsam açıkça kabul edilmedi.
- [ ] Seçilen model hassas alanı anonim GET'te tutuyor fakat veri sahibi bunu ve okuyucu kitlesini onaylamadı.
- [ ] Browser C için session/CSRF/logout/revoke veya backend'e direct erişim kapısı yok.
- [ ] `/api/veri` ile `/veri`, HTML ve diğer hassas GET yollarının policy eşlemesi eksik.
- [ ] Auth-on/off, release, data root, gerçek bind/proxy ve ayrı UID iddiaları dağıtım kanıtıyla doğrulanmadı.
- [ ] Snapshot partial/field minimization UI veya dış tüketiciler tarafından yanlışlıkla tam veri gibi yorumlanıyor.
- [ ] Auth-off POST mutasyonları hedef threat modelde kabul edilemez veya çözülmemiş.

GO adayı için gerekli kanıtlar:

- [ ] Veri sahibi ve intended-reader matrisi imzalı; alan minimizasyonu kararı sürümlü.
- [ ] Release, `YUVA_DIR`, bind/network namespace, proxy ve servis auth mode'u read-only deployment kanıtıyla eşleşiyor.
- [ ] Seçilen GET auth/session veya insan-only istisnası için exact route/alias/HTML kabul fixture'ı geçti.
- [ ] Auth/store/session/peer hata yolları fail-closed; başarısız durumda hassas snapshot body gönderilmiyor.
- [ ] Partial snapshot ve UI/harici consumer uyumu birlikte kabul edildi.
- [ ] POST task/chat/role write kapısı ayrı kabul edildi; `kimden`/`Origin`/loopback principal gibi sunulmuyor.
- [ ] Owner, reviewer, rollout, rollback ve yeniden değerlendirme tarihi kaydedildi.

**Operatör kararı:** [ ] NO-GO / bekle · [ ] koşullu (şartları aşağıda) · [ ] GO adayı
**Seçilen model (A/B/C):** ______
**Gerekçe ve kabul edilen okuyucu kitlesi:** _________________________________
**Açık şartlar / sorumlu / tarih:** _________________________________________
**Onaylayan ve tarih:** ____________________________________________________

Karar doldurulmamışsa veya gerekli kanıt yoksa mevcut dokümanlardan **GO
çıkarılmaz**. Bu matris anonim GET'i etkinleştirmez veya auth ayarını değiştirmez.

## Kaynaklar ve kapsam

- `docs/local-api-get-snapshot-decision-455.md` — GET ve HTML erişim seçenekleri.
- `docs/panel-api-route-scope-matrix-526.md` — GET/POST route ve auth
  kaynak davranışı; canlı deployment kanıtı değildir.
- `docs/panel-anonymous-snapshot-data-minimization-574.md` — alan riskleri ve
  A/B/C seçenekleri; çok-agent same-UID varsayımında tam anonim snapshot NO-GO.
- `docs/first-local-mvp-scope-go-no-go-536.md` — ilk MVP kullanıcı/ağ ve
  release varsayımları; operatör/release kararı yerine geçmez.
- `docs/panel-global-snapshot-budget-contract-606.md` — byte-budget/partial
  snapshot sözleşmesi; auth veya erişim kontrolü değildir.
- `docs/local-api-access-decision-451.md` — loopback, HMAC, UDS ve ayrı UID
  sınırlarının karşılaştırması.

Form statik kaynak ve önceki karar notlarını bir araya getirir. Gerçek servisi,
auth environment'ını, network namespace/proxy'yi veya kullanıcı/veri kökünü
incelemez; kod, panel, auth, route, deployment ya da runtime değiştirmez.
