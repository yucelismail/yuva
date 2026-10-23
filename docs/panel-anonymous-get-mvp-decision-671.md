# #671 — Anonim GET snapshot: MVP karar taslağı ve kalan veri riski

**Tarih:** 2026-10-23
**Karar durumu:** Operatör/veri sahibi seçimi bekleniyor. Bu taslak erişim
modeli seçmez veya etkinleştirmez.
**Geçici güvenlik tutumu:** Tam anonim snapshot için **NO-GO**; owner kararı,
gerçek okuyucu topolojisi ve production route kabulü gelene kadar aynı kalır.

## Kanıtların birlikte okunması

| Kaynak / görev statüsü | Bulgu | Karar kapsamı |
|---|---|---|
| [#655 — verified operatör matrisi](panel-anonymous-get-operator-decision-655.md) | Tam snapshot, minimize anonim özet veya doğrulanmış GET/browser modellerini ve owner alanlarını sunuyor. Formda model/okuyucu/alan seçimi yok. | Owner kararı beklemede; formun kendisi erişim izni değildir. |
| [#656 — pending_verification fixture](panel-get-snapshot-acceptance-656.md) | Geçici `YUVA_DIR` ile gerçek Handler projection'ı `/api/veri` ve `/veri` üzerinde sınanıyor. Test Handler alt sınıfı 4096-byte selector'ı `_gonder()` öncesi uygular; response byte sayısı, `Content-Length`, partial metadata ve redaction sırası fixture'da kontrol edilir. | Selector yalnız test Handler'a bağlı; production `panel.server.H` global budget kullanmıyor. Bilinen pattern redaction da tam DLP değildir. Fixture anonimliğin güvenli olduğunu söylemez. |
| [#640 — verified real Handler session/CSRF fixture](panel-browser-session-handler-fixture-640.md) | Dört GET/HTML yolu session'sız anonim erişilebilir; auth gate kapalıyken 11 POST route sentetik callback'e dispatch edildi. Sentetik session/CSRF retleri sentetik ledger'ı değiştirmedi. | Handler sırası/fixture sonucu; production browser session veya gerçek callback side-effect kabulü değildir. Auth-off POST riski ayrı kalır. |
| [#669 — verified auth-off route risk incelemesi](panel-auth-off-mutation-route-review-669.md) | Auth gate `None` olduğunda POST body doğrudan callback'e gider. `kimlik`, `kimden`, rol ve loopback caller kimliği doğrulamaz; aynı UID dosya/HTTP bypass'ı mümkündür. | Statik kaynak davranışı. Gerçek çalışan servisin env/auth/bind durumu bu incelemeden bilinmiyor. |
| [#574 — verified veri minimizasyonu kararı](panel-anonymous-snapshot-data-minimization-574.md) | Mevcut çok-agent/same-UID varsayımında tam anonim snapshot varsayılan NO-GO. | Karar belgesi; hostta ilgili agent/UID/proxy topolojisini doğrulamaz. |

## Snapshot kapsamı ve okuyucu riski

Fixture'daki snapshot üst düzeyde şu alanları taşır: `ok`, `simdi`,
`online_sn`, `rev`, `kullanicilar`, `gorevler`, `mesajlar`, `ekranlar`,
`ekranlar_meta`; bütçe fixture'ı `snapshot_meta` ekler.

| Grup | Projection'daki alanlar | Veri riski |
|---|---|---|
| Roster | `kimlik`, `ad`, `arac`, `rol`, `bas_denetci`, `sorumlu_kimlik`, `son_okuma`, `online`, `presence_state`, `presence_verified` | Kimlik/ekip/rol metadata'sı; presence değerleri doğrulanmış liveness değildir. |
| Görevler | `id`, `baslik`, `detay`, `durum`, `kimden`, `assignee`, `gorevli_kimlik`, `inceleyen_kimlik`, `ust_gorev_id`, `gecmis` | Görev serbest metni, geçmiş ve actor iddiaları iş/kişisel bilgi taşıyabilir; `kimden` principal kanıtı değildir. |
| Mesajlar | `id`, `ts`, `kimden`, `ad`, `kime`, `metin`, `tur`, `source_class`, `source_class_trust`, `provenance` | Chat metni kullanıcı/agent girdisidir; sır veya hassas içerik içerebilir. Source/trust/provenance alanları doğrulanmış caller kimliği değildir. |
| Ekran | `ts`, `kimlik`, `ad`, `tur`, `satir`; ayrıca `ekranlar_meta` | Terminal/komut/çıktı, path veya credential içerebilir. Bilinen pattern redaction bilinmeyen sırları yakalamaz. |
| Limit/presence metadata | `snapshot_meta`, `ekranlar_meta`, online/presence state alanları | Partial/omitted ve kullanım bilgisi; eksik liste tam roster/task snapshot gibi gösterilmemeli. `unknown` çevrimiçi/offline kararı değildir. |

`#656` fixture'ında canary'ler redaction sonrası route projection'da ve HTTP
response'unda görünmüyor; kaynak JSONL dosyaları değiştirilmeden kalıyor.
`no-store`, `Host`/`Origin`, loopback veya redaction kimlik doğrulama değildir.
Anonim GET'e ulaşabilen same-UID process tam alanlara erişebilir; aynı network
namespace'teki başka UID/proxy erişimi de ayrıca araştırılmalı. Gerçek host
topolojisi bilinmiyor.

## Açık erişim seçenekleri

Operatör tek bir modeli seçmeli; bu taslak seçim yapmaz.

| Model | Getirdiği davranış | Kabul koşulu ve açık risk |
|---|---|---|
| **A — İnsan-only yerel istisna** | Mevcut tam anonim HTML/snapshot korunur. | Yalnız tek insanın kullandığı özel host/namespace ve tüm aynı-UID/loopback okuyucularının tam snapshot için güvenilir kabulü imzalanırsa düşünülebilir. Gerçek erişim topolojisi kanıtlanmadan NO-GO. |
| **B — Anonim minimize özet** | Server-side allowlist ile düşük hassasiyetli health/roster özeti; görev/chat/screen serbest metni çıkarılır. | Alan, amaçlanan okuyucu, partial davranışı ve consumer uyumu ayrıca kararlaştırılıp production route'da uygulanmalı. Bu model auth değildir ve auth-off POST mutasyonunu çözmez. |
| **C — Doğrulanmış GET/browser** | Hassas snapshot yalnız doğrulanmış session/scope veya onaylı broker üzerinden verilir; alias ve HTML yolları da aynı politika altında olur. | Cookie/session, CSRF/Origin, expiry/logout/revoke, route-by-route scope ve doğrudan backend anonymous erişimin kapanması fixture/production rollout ile kanıtlanmalı. HMAC POST gate'i browser session değildir. Same-UID ajanlarını ayırmak için OS sınırı gerekebilir. |

## Ayrı karar: auth-off POST mutation

GET için seçilen A/B/C modeli auth-off POST riskini kapatmaz. #669/#640
kanıtlarına göre auth gate kapalı olduğunda task/chat/roster/role/screen
mutation callback'lerine erişim vardır; `kimden`/`kimlik` body değerleri
caller principal'ı değildir. Operatör ayrıca auth-off mutation'ı reddetme veya
kabul etme kararını vermeli. Kabul etmiyorsa production'da auth-off write
yolu kapalı/fail-closed olmalı; bu belge hiçbir route'u değiştirmez.

## Owner karar kaydı — doldurulmayı bekliyor

| Alan | Karar / kayıt |
|---|---|
| Veri sahibi / kurulum owner'ı | ______________________________ |
| Canonical release ve gerçek `YUVA_DIR` kanıt referansı | ______________________________ |
| Amaçlanan okuyucu grupları: same UID, diğer UID, browser, proxy/tunnel | ______________________________ |
| Seçilen model | [ ] A — insan-only · [ ] B — minimize özet · [ ] C — doğrulanmış GET · [ ] ertelendi |
| Anonime açılabilecek alan allowlist'i ve sürümü | ______________________________ |
| Auth-off POST kararı ve owner'ı | [ ] kapat · [ ] açıkça kabul et · [ ] ertelendi; gerekçe: __________ |
| Production Handler/session/route kabul raporu | ______________________________ |
| Açık riskler, kapatma sorumlusu ve son tarih | ______________________________ |
| Operatör / bağımsız reviewer / tarih | ______________________________ |

Boş, çelişkili veya doğrulanmamış satır **NO-GO/HOLD** bırakır. Bu karar
taslağının mevcut güvenli ara sonucu tam anonim snapshot için **NO-GO**'dur;
owner imzası veya production kabulü varsayılmaz.

## Kalan üretim kanıtı

- Çalışan panel process'i, auth env/store, bind, network namespace, tunnel,
  proxy ve gerçek `YUVA_DIR` salt okunur deployment kaydıyla eşleştirilmedi.
- #656'nın global response bütçesi test Handler alt sınıfında; production
  Handler'a bağlanmış değil ve görev denetim bekliyor.
- Bilinen-pattern redaction privacy guarantee/DLP değil; legacy geçmişi,
  backup'ı veya export kopyasını temizlemiyor.
- Gerçek browser session/CSRF/logout/expiry/revoke ve direct backend bypass
  için production route kabulü yok.
- Auth-off POST üretim güvenlik kararı ayrı; GET gizliliği kararı bunu
  kapsamaz.

Bu belge yalnız #655/#656/#669/#574 karar ve kanıtlarını bir araya getirir.
Canlı GET/POST, `doctor`, servis, auth, proxy, data root, backup veya release
değişikliği yapılmadı.
