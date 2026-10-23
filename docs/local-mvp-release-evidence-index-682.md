# Yuva #682 — Yerel MVP release kanıt indeksi ve operatör imza sırası

**Tarih:** 2026-10-23
**Karar:** **NO-GO — host/runtime ve owner kanıtları yok; operatör imzaları boş.**
**Board snapshot:** `<YUVA_DATA_ROOT>/gorevler.json`, salt-okunur, 2026-10-23 22:35:56 Europe/Istanbul (19:35:56 UTC). #638–#669 görevlerinin tamamı bu snapshot'ta `verified`; #670 son revize teslimi `pending_verification`.

Bu indeks #576 hizmete çıkış kapıları, #617 karar/imza formu, #632 rollback/data-schema matrisi ve #638–#669 artifact kabul kapsamını tek kanıt görünümünde toplar. `verified` burada görev/artifact inceleme statüsüdür; gerçek release, servis, host veya canlı veri onayı değildir. Canlı `doctor`, host/backup taraması, release işlemi ve operatör kararı bu çalışmada yapılmadı.

## Kaynak kararların ilişkisi

| Kaynak | Bu indeksteki rolü | Kalan sınır |
|---|---|---|
| [#576 MVP Go/No-Go matrisi](local-mvp-release-go-no-go-matrix-576.md) | Ürün/erişim, release kimliği, writer, veri kökü, backup/rollback, browser/auth, actor/presence ve acceptance kapıları | Board/artifact eşlemesi ve statik/fixture kapsamı; canlı host kanıtı değildir. |
| [#617 operatör karar formu](release-operator-decision-form-617.md) | Zorunlu PASS/FAIL/UNKNOWN, risk kaydı, release/veri/güvenlik sahipleri ve son imza alanları | Form doldurulmamış ve imzalanmamıştır; boş/UNKNOWN kapı NO-GO'dur. |
| [#632 rollback data-schema matrisi](release-data-schema-rollback-matrix-632.md) | Current/target contract, actual data, reader/writer, screen/auxiliary state ve rollback ayrımı | Manifest eşitliği, doctor `candidate` veya fixture gerçek data-root compatibility ve writer freeze değildir. |
| [#670 son revizyon](local-mvp-release-go-no-go-matrix-576.md) | #576 içindeki 2026-10-23 22:35:02 board eşlemesi ve #567/#569/#574/#656 kapsam düzeltmesi | Bu snapshot'ta #670 yeniden teslim edilmiş ama `pending_verification`; artifact onayı bekliyor. Release GO değildir. |

## #638–#669 kabul edilmiş artifact envanteri

Board snapshot'ında aşağıdaki görevler `verified` durumundadır. “Sınır” sütunu kabulün release kararında hangi UNKNOWN/NO-GO kapısını açık bıraktığını gösterir.

| Görev(ler) | Kabul edilen kanıt | Release kararında kalan sınır |
|---|---|---|
| #638 | Yeni scratch restore-check CLI stub'ı görev ledger yazımını fail-closed durdurur. | Tarihsel CLI kopyaları bu guard'ı taşımıyor; #659 containment tasarımı uygulanmış değildir, çalıştırılmamalıdır. |
| #639 | Sentetik global snapshot bütçesi/ekran cursor commit fixture'ı. | Production endpoint veya erişim kontrolü kanıtı değildir. |
| #640, #642 | Gerçek Handler/ephemeral HTTP fixture'ları: anonim GET alias'ları ve auth-off POST dispatch/error davranışları. | Production erişim modu hostta bilinmiyor; anonim GET ve auth-off POST riski açık kalır. |
| #641 | Anonymous summary read-model için sentetik partial/unavailable ve UI kilidi davranışı. | Production endpoint/auth/cache entegrasyonu yok. |
| #643, #653, #654 | Salt-okunur innerHTML sink denetimi ve rol/revision için dar escape/validation düzeltmeleri. | Browser/CSP/deployment kabulü değildir; yalnız raporlanan sink ve fixture kapsamıdır. |
| #644, #657 | Canonical writer geçiş sözleşmesi ve temporary-root additive-field/lock/no-write fixture'ı. | Nested outbox, receipt atomikliği, worker/dispatch ve tüm eski writer/process'ler için production tek-writer kanıtı yok. |
| #645, #646 | Rollback actual-data gate ve doctor projeksiyon fixture'ları; `candidate`/`PASS|FAIL|UNKNOWN` ayrımı. | Canlı `YUVA_DIR`, eşzamanlı writer-free snapshot, target reader, dış pin ve runtime kanıtı değildir. |
| #647, #664 | Read-only staging inventory fixture'ı ve bağımsız fd review. #664 kabulü review teslimine aittir; F1 child `fstat` exception'da bir fd leak olarak bulundu. | #664 `verified` olsa da F1 kaynakta açık; #681 residual haritası da HOLD verdi. Inventory her durumda HOLD, cleanup/publish/pointer repair izni yok. |
| #648, #665 | Release decision form validator ve sentetik PASS/FAIL/UNKNOWN semantik fixture'ları. | Form biçimini doğrular; kanıt içeriği, host, signer veya digest provenance doğrulamaz; host acceptance `not-verified`. |
| #649, #666 | İki UID broker koşucusu/fixture sözleşmesi ve host readiness checklist'i. | Gerçek iki-UID host koşusu, UID/ACL/service/key provisioning ve host acceptance yapılmadı. |
| #650, #667 | Sentetik broker-principal projection ve provenance denetimi. | Production peer/map/session/heartbeat adapter yok; replay high-water ve gerçek provenance kanıtı yok; presence `unknown`. |
| #651, #652, #668 | Retention karar formu, bilinen secret pattern'leri tarayan fixture prototipi ve canary regression fixture'ı. | Owner retention kararı boş; gerçek geçmiş/backup taranmadı; scanner tam DLP veya purge/revoke garantisi değildir. |
| #655, #656 | Anonymous GET karar matrisi ve verified test-only Handler snapshot fixture'ı. #656 wire response byte budget/`Content-Length`, partial, allowlist ve redaction sırasını test alt sınıfında sınar. | #655 operator seçimi boş. #656 production `panel.server.H` değişikliği/entegrasyonu değildir; production GET global byte bütçesi, auth/session veya anonim veri kabulü kanıtı değildir. |
| #660 | Temporary ledger üzerinde live-board claim/assigned/delivery tutarlılık fixture'ı. | Deployment HTTP/UI davranışı veya gerçek concurrent host writer kabulü değildir. |
| #661, #662 | Nested outbox schema/budget ve exact-ID append belirsizliği sentetik prototipleri. | Production canonical writer/outbox entegrasyonu ve genel delivery idempotency yok. |
| #663 | Rollback öncesi writer-freeze/lock/timeout HOLD sözleşmesi. | Canlı admission close, drain veya host writer yokluğu kanıtı değildir. |
| #664, #665, #666, #667, #668, #669 | Yukarıdaki ilgili review/fixture ve auth-off route risk incelemesi kapsamları. #669 on POST writer route'u ile `local_unverified` caller sınırını statik eşler. | Host auth modu ve runtime erişimi bilinmiyor; body actor claim'i principal değildir. #664 F1, #669 riskleri host GO'yu engelleyen açık konulardır. |

Not: Son satır görevlerin önceki satırlardaki kapsama ek kabul sağlamadığını belirtir. #638–#669 artifact statüleri yalnız kendi görev kapsamındaki teslim kabulünü gösterir.

## Operatör/owner imza sırası ve kanıt gereksinimi

Bu sıra, #617 formu üzerinde gereken bağımsız sorumlulukları gösterir. Hiçbir owner başka bir rol adına UNKNOWN'ı varsayımla PASS yapamaz. Önceki aşamada FAIL/UNKNOWN varsa sonraki imza GO oluşturmaz.

| Sıra / owner | İmzalaması gereken kanıt | Şu anki durum |
|---|---|---|
| 1. Release sahibi | Temiz kaynak commit/tree, payload/CLI/panel hash'i, exact release ID, dışarıdan alınan bağımsız manifest pin'i, immutable ayrı install root ve `current`/PATH/unit hedef eşleşmesi | **UNKNOWN** — mevcut çalışma ağacı release adayı/pin kabulü değildir. |
| 2. Host işletim sahibi | Etkin executable/cwd/PID ve unit, bind/port, environment kaynağı (secret dökmeden), `YUVA_DIR`, namespace/proxy/tunnel ve UID erişim yolu; eski/legacy/dev writer envanteri ve uygulanmış admission sınırı | **UNKNOWN** — canlı host/runtime incelenmedi. `ps`/lock varlığı tek başına yeterli kanıt değildir. |
| 3. Ürün/veri sahibi + güvenlik kabul sahibi | Browser erişim kitlesi; GET `/`, `/index.html`, `/api/veri`, `/veri` için session/authorization veya açık insan-only istisna kanıtı; chat/task/screen veri sınıfı ve auth-off POST risk kabulü | **AÇIK / NO-GO** — #574 verified karar artifact'ı tam anonim snapshot için NO-GO der; #655 formunda seçim/imza yok. #640 auth-off GET/POST riskini fixture'da gösterir. |
| 4. Browser/API güvenlik sahibi | 4 GET/HTML alias ve bütün POST route'ları için exact session, route policy, CSRF, auth-off fail-closed ve proxy/backend bypass negatif/pozitif kabul makbuzu; browser ile HMAC/agent protokol ayrımı | **UNKNOWN / NO-GO** — #656 test-only Handler fixture'ı; production gate/session/CSP/CSRF deployment kanıtı ve gerçek endpoint access kabulü yok. |
| 5. Backup sahibi + veri sahibi | Aktif `YUVA_DIR` dışında izinleri koruyan backup, verify/scratch restore-check, bağımsız digest kaynağı/custody, saklama/hold ve restore owner kaydı | **UNKNOWN / NO-GO** — #565 authenticity `unverified`; #616 fixture digest'i kaynağını doğrulamaz; gerçek backup/restore yapılmadı. |
| 6. Release/data owner + host writer-freeze sahibi | Exact current/target contract ve actual data shape/readers; screen/auxiliary stores; tüm canonical, legacy, panel, timer/heartbeat, importer, backup/restore ve same-UID writer sınıfları için admission close/drain/deadline kanıtı; data-root unchanged readback | **UNKNOWN / HOLD** — #632 actual root/race ve target-reader boşluklarını açık bırakır; #663/#680 karar belgeleri host freeze uygulaması değildir. #664 inventory F1 de düzeltme/tekrar kanıtı bekler. |
| 7. Bağımsız gözden geçiren | Bütün imzaların exact release/host/time/pin'e bağlandığı, fixture'ın host kanıtı olarak kullanılmadığı, hiçbir UNKNOWN/FAIL/HOLD kalmadığı ve rollback kararının data restore'dan ayrıldığı çapraz kontrol | **Yapılmadı** — kanıt paketi imzalanmamış. |
| 8. Son karar sahibi (release + veri + güvenlik sahiplerinin required approvals'ı) | #617 formunda final scope, kalan açık riskler, GO/NO-GO, tarih ve kanıt paketi referansı | **Boş / NO-GO** — bu indekste karar verilmiyor ve GO verilmiyor. |

## Açık UNKNOWN/HOLD kayıtları

| UNKNOWN / risk | Etki | Kapatma kanıtı | Sorumlu owner |
|---|---|---|---|
| Exact release ve independent pin | Çalışma ağacı/provenance sabitlenmedi; artifact'ın hangi host binary'si olduğu bilinmiyor. | Temiz commit/tree + manifest/payload digest'leri; payload dışından alınmış bağımsız pin custody/readback'i; `current`, PATH ve unit eşleşmesi. | Release sahibi + bağımsız reviewer |
| Host/runtime/UID/network path | Etkin panel/CLI, auth modu, bind, service, UID/namespace, tunnel/proxy ve gerçek data root bilinmiyor. | Yetkili salt-okunur host acceptance makbuzu; secret'sız config kanıtı, exact process/unit/executable ve path/owner/mode; proxy/netns envanteri. | Host işletim sahibi |
| Browser GET/POST erişimi | Tam snapshot anonymous; auth-off mutation route'ları dispatch edebilir; session/CSRF veya peer boundary deployment'ta kanıtlanmadı. | GET/HTML tüm alias ve POST route'ları için production release'e bağlı access-control/CSRF/bypass acceptance; owner'ın veri kapsamı ve erişim kitlesi imzası. | Ürün/veri sahibi + security/browser owner |
| Backup authenticity/custody | Adjacent checksum tek başına güvenilir kaynak değildir; restore eski/zararlı state'i geri getirebilir. | Bağımsız güven alanındaki pin kaynağı ve custody; izinli backup verify, ayrı scratch restore-check, retention/hold ve recovery imzası. | Backup sahibi + veri sahibi |
| Actual rollback/schema/readers | Manifest contract metadata gerçek data'yı veya eski target'ın okuyabildiğini kanıtlamaz; screen/auxiliary data sürümsüz olabilir. | Exact current/target release; gerçek `YUVA_DIR` schema/data read-only gate; hedef CLI/panel/backup reader fixture'ı; screen/auxiliary kararları ve owner onayı. | Release/data owner |
| Writer freeze ve eşzamanlılık | Canonical lock bütün eski/dev/importer/aynı-UID writer'ları durdurmaz; scan sırasında karışık snapshot oluşabilir. | Admission close + in-flight drain için sonlu ve onaylı deadline; tüm process/caller/UID/target sınıfları; data lock ve unchanged readback; bilinmeyen writer yokluğu. | Host writer-freeze sahibi + veri sahibi |
| Staging inventory F1 | Child `fstat` error descriptor leak'i #664 verified review'de bulundu; inventory operasyonel olarak güvenilir kabul edilemez. | Kaynak düzeltmesi ve fstat/ikinci-open/close hata fixture'larıyla fd sayım regressions; inventory yine HOLD kaldığı gösterilsin. | Release tool owner; bağımsız review |
| Presence/actor/provider | Same-UID principal ve local-unverified body claims gerçek actor/session/provider presence değildir. | Production broker/UID/session custody ve replay high-water kabulü; provider dispatch kapalı konfigürasyon/release kanıtı; panel unknown kalma kanıtı. | Security/broker owner + release sahibi |
| Retention/secret geçmişi | Retention formu doldurulmadı; sentetik scanner geçmişi temiz olduğunu kanıtlamaz. | Veri owner retention/export/delete imzası; kapsamlı, onaylı offline scan ve ayrı purge/hold prosedürü gerekiyorsa kanıtı. | Veri sahibi + security owner |

## GO/NO-GO eşiği ve mevcut sonuç

Bu indeks **GO vermiyor**. #617'ye göre herhangi bir boş, `UNKNOWN`, `FAIL`, açık HOLD veya imzasız risk NO-GO'dur. Şu an host/runtime, browser erişimi, backup custody, writer freeze ve actual rollback kanıtları açık; #574/#655 kararı anonim GET için kapalı değil; #664 F1 kaynak düzeltmesi yok. Bu yüzden yalnız **NO-GO** kaydedilebilir.

Fixture/verified task kabulü kendi dar kapsamındaki kod/artifact kalitesine kanıttır. Release candidate'ın tam hash'i, canlı host config'i, gerçek browser okuyucuları, backup authenticity, yazarların durmuş olması veya rollback güvenliği anlamına gelmez.

## Kaynaklar

- `docs/local-mvp-release-go-no-go-matrix-576.md` — ürün/release sekiz kapısı ve #638–#669 eşlemesi.
- `docs/release-operator-decision-form-617.md` — zorunlu kapılar, risk ve imza alanları.
- `docs/release-data-schema-rollback-matrix-632.md` — actual data, contract, reader/writer ve rollback sınırı.
- `docs/rollback-writer-freeze-acceptance-matrix-680.md` — writer sınıfları, freeze/drain ve HOLD.
- `docs/release-staging-fd-review-664.md` — F1 child-fd bulgusu; #664 review kabulü bug fix değildir.
- `docs/panel-anonymous-get-operator-decision-655.md`, `docs/panel-get-snapshot-acceptance-656.md`, `docs/panel-auth-off-mutation-route-review-669.md` — GET/POST ve actor trust sınırları.
- `<YUVA_DATA_ROOT>/gorevler.json` — board durum snapshot'ı; statüler snapshot zamanına aittir.

Bu belge bir indeks/karar hazırlığıdır; imzalı release makbuzu değildir. Host, servis, auth, backup, data root, release pointer veya browser session üzerinde işlem yapılmadı.
