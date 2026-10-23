# Yerel MVP hizmete çıkışı: kanıt temelli Go/No-Go matrisi (#576)

**Durum:** Kaynak ve kabul belgelerinden derlenmiş release kararı/işletim
kontrolü. Host, servis, çalışan süreç, canlı YUVA verisi veya backup bu görevde
incelenmedi ya da değiştirilmedi. Panel servisi başlatılmadı; auth açılmadı.
**Görev tahtası eşlemesi:** `<YUVA_DATA_ROOT>/gorevler.json` salt-okunur
snapshot'ı 2026-10-23 22:35:02 Europe/Istanbul (19:35:02 UTC). Bu snapshot'ta
#567, #569, #574 ve #656 `verified`; #638–#669 aralığındaki release/panel
teslimleri de ilgili görevlerde `verified` görünüyordu. Bu statüler artifact
kabulidir; host/runtime veya release GO kanıtı değildir.

## Mevcut karar

**NO-GO — host kabulü ve anonim snapshot kararı bekleniyor.** #536, #550 ve
#552 `verified`; bunlar tasarım, fixture zinciri ve repo içi yazıcı haritasını
kabul eder. Gerçek hostun bu koşullara uyduğunu kanıtlamaz. Ayrıca kaynak
çalışma ağacında çok sayıda yerel değişiklik/untracked dosya var; bu ağaç
release adayı veya sabitlenmiş provenance değildir. #574 `verified` karar
belgesi tam anonim snapshot için varsayılan **NO-GO** verir; #655 operatör
seçim formu henüz doldurulmamıştır. #557 aynı loopback namespace içindeki
başka UID'lerin HTTP snapshot'a erişebildiğini ve kaynakta peer-UID kontrolü
olmadığını belgeliyor.

`GO`, aşağıdaki bütün zorunlu kapılar için gözlenebilir kanıt bulunduğunda,
tek operatörlü ve loopback ile sınırlı yerel MVP anlamına gelir. Herhangi bir
`unknown`, eksik kanıt veya kabul edilmemiş risk **NO-GO** üretir. GO; çoklu UID,
uzak erişim, doğrulanmış aktör/audit, agent presence, otomatik dispatch veya
provider entegrasyonu anlamına gelmez.

## Release kapıları

| Kapı ve durum | Kabul edilmiş kanıtın sınırı | GO için eksik host/runtime kanıtı | Sorumlu | Dar sonraki adım |
|---|---|---|---|---|
| **1. Ürün ve erişim sınırı — AÇIK / NO-GO** | #536 tek güvenilir yerel operatör, loopback, manuel görev akışı, `presence=unknown`, provider dispatch kapalı kapsamını tanımlar. #557 anonim GET ve auth-kapalı POST'un HTTP peer UID'sini sınamadığını gösterir. #574 karar belgesi `verified` ve tam anonim snapshot için varsayılan **NO-GO** önerir; bu artifact kabulü operatör deployment seçimi değildir. | Operatörün görev ayrıntısı, son 200 sohbet mesajı ve ekran kayıtlarını okuyabilen bütün loopback süreçlerini güvenilir sayıp saymadığı; hostta farklı UID/namespace, tunnel, proxy veya browser erişim yolu olup olmadığı. | Ürün sahibi/operatör | #655 erişim-modeli formunda owner kararını kaydet veya anonim özet/gerçek GET erişim sınırı için ayrı tasarım ve uygulama aç. Kabul edilmeyen erişim ihtimali varsa hizmete çıkma. |
| **2. Kaynak ve release kimliği — AÇIK** | #542 manifest aracı kaynak commit/tree ve payload hash'lerini kaydeder; imzasız manifest ancak dışarıdan sağlanan tam SHA-256 pin'iyle doğrulanmış release olur. #543 atomik ayrı release kurulumunu ve `current` işaretçisini tanımlar. #550 sentetik fixture'da bu zinciri çalıştırır. | Temiz kanonik commit/tree, tam payload/CLI/panel hash eşleşmesi, release dizininin değiştirilemez tutulduğu, `current` ve PATH girdilerinin aynı adaya çözüldüğü ve manifest pin'inin payload dışındaki bağımsız yerden geldiği. Şu anki dirty çalışma ağacı bunların kanıtı değil. | Release sorumlusu | Değişiklikleri gözden geçirip ayrı bir temiz commit/release adayı dondur; manifest üret; tam hash'i bağımsız kabul kaydına al; adayı ayrı install root'a kurup doğrula. |
| **3. Tek CLI/panel hedefi ve tek writer — AÇIK** | #552 desteklenen repo yolunda panelin görev yazımını aynı `bin/yuva` core'una yönlendirdiğini ve kilitli oku/değiştir/yaz kullandığını doğrular. #540/#535 eski `~/yuva/bin/yuva` kopyasının kilitsiz/guard'sız yazabildiğini ve doğrudan çalıştırılmasının yalnız kaynak kararıyla engellenmediğini gösterir. #550 `writer_singleton=true` yalnız ardışık sentetik fixture süreçleri içindir. | PATH `yuva`, kurulu unit `ExecStart`, etkin panel process executable/cwd ve etkin `YUVA_DIR` aynı release/veri kökünü kullanıyor mu; eski panel/CLI/heartbeat writer süreçleri var mı; eski CLI doğrudan çağrılabiliyor mu. | Host işletim sahibi | Salt okunur host envanteri tut: CLI çözümlemesi/hash'i, unit ve etkin PID kod yolu, port/bind, `YUVA_DIR` mutlak gerçek yolu, eski writer yokluğu. Belirsizlikte geçişi durdur. |
| **4. Veri kökü, sahiplik ve snapshot — AÇIK / NO-GO** | #533 özel tek-owner KOK modelini doğrular; farklı UID'lerle ortak dosya/ACL paylaşımını reddeder. #550 ortak veri kökü ve değişmeden kalan hash'i yalnız geçici fixture'da kanıtlar. #557 `GET /api/veri`, `/veri`, `/` ve `/index.html` yollarının anonim olduğunu; snapshot'ın roster, görev, sohbet ve ekran içeriği taşıdığını saptar. | Etkin CLI/unit aynı, release dışında kalan mutlak `YUVA_DIR`'i mi kullanıyor; gerçek owner/mode doğru mu; başka UID dosyaya ve loopback HTTP'ye erişebiliyor mu; hassas snapshot içeriğinin bu okuyuculara açılması kabul mü. | Veri sahibi + operatör | Veri yolunu ve izinlerini salt okunur doğrula; network namespace/HTTP okuyucu sınırını kaydet; #574 kararı olmadan anonim tam snapshot'ı hizmete açma. `YUVA_AUTH_ENABLED=1` mevcut GET/HTML yollarını kapatmaz. |
| **5. Backup, restore ve rollback — AÇIK** | #544 verifier arşiv yapısı, yan yana checksum ve etkin KOK dışında scratch restore-check sağlar. #530 retention/hold politikasını tanımlar; aktif restore-check artıkları mtime ile temizlenmez. #565 adjacent `.sha256` için authenticity değerinin `unverified` kalmasını seçer. #550 geçici backup, scratch restore ve rollback pointer'ını sentetik veride dener; host rollout'u açıkça `NO-GO` döndürür. | Etkin KOK dışında, izinleri koruyan gerçek pre-release yedeği; archive/list/hash bağlantısı; izole scratch restore-check makbuzu; gerçek snapshot şeması/rollback uyumu; operatörün yerel tek-operatör tehdidinde `unverified` backup authenticity'yi kabulü. Bağımsız pin yoksa yedeği `authentic/verified` diye sunma. | Backup sorumlusu/operatör | Canlı backup işlemi ayrı onay ve bakım penceresinde yapılmalı; bu matris bunu yapmaz. Önce salt okunur verify, sonra yeni özel scratch'e restore-check ve operatör gözden geçirmesi; etkin KOK üzerine açma/restore etme yok. |
| **6. HTTP, browser ve auth — AÇIK** | #538 Host/Origin/Content-Type kontrolleri CSRF/kaynak filtresidir, kimlik kanıtı değildir. #562 `nosniff`, `no-referrer`, `X-Frame-Options: DENY` başlıklarını ortak yanıtlara ekler; CSP bilerek ertelenmiştir. #557 anonime açık snapshot/HTML ve CSP boşluğunu kaydeder. HMAC varsayılan kapalıdır; açık olsa bile HMAC POST gate'i GET/HTML'yi kapsamıyor. | Etkin bind gerçekten `127.0.0.1`; tunnel/proxy/LAN yok; etkin auth modu biliniyor; browser erişim kapsamı ve CSP residual riski kabul edilmiş mi. Eksik servis unit'ini bu kabul için başlatma. | Host işletim sahibi + güvenlik kabul sahibi | Mevcut unit/process/port ve environment kaynağını salt okunur doğrula. Auth açmak çözüm diye varsayma; gerekiyorsa GET/session/peer sınırı için ayrı tasarım ve rollout kararı al. |
| **7. Görev, actor, presence ve provider sınırı — AÇIK** | #536 ve #514 ilk MVP'de açık manuel çağrı, `--from`/`kimden` için `local_unverified`, presence `unknown` ve provider dispatch kapalı sınırını belirler. #566 sohbet kaydının agent receipt/teslim olmadığını söyler. #532 actor/rol raporu kimlik doğrulaması açığını belgeler. #567 ve #569 `verified`: source-class protokolü ve doğrulanmış kanalda server-side üretim kabul edildi; bu, auth-off kimliği doğrulamaz. #569 notuna göre custody gate varsayılan kapalı olduğundan doğrulanmış `operator` sınıfı üretilemiyor. | Kurulu release'in mesajı otomatik göreve/dispatch'e dönüştürmediği, provider/approval/retry yolu açmadığı; görev actor'ının ve UI presence'ının doğrulanmış kimlik gibi gösterilmediği; bu sürümde ilgili auth/presence çevre ayarlarının hangi değerde olduğu. | Release sorumlusu | Aday release kaynak/ayar incelemesinde bu davranışları kanıtla. Bunlardan biri açılmış veya bilinmiyorsa NO-GO; mesajı canlı ajana gönderme canary'si yapma. |
| **8. Acceptance/canary kanıtı — FIXTURE VAR, HOST YOK** | #550 gerekli sekiz fixture kapısını (release hash, CLI/panel hedefi, ortak data root, read-only canary, backup guard, şema uyumu, rollback pointer, writer singleton) `True`/unknown semantiğiyle değerlendirir. Fixture-generated pin bağımsız anchor değildir; test servis başlatmaz ve geçici kökleri temizler. | Aynı kontrollerin exact release adayı, gerçek host yolları, etkin süreçler ve gerçek veri kökü için makbuzu. Fixture GO'su host GO'su değildir. | Release ve host işletim sahipleri | Önce #550 fixture raporunu release makbuzuna iliştir; sonra statik host kabul listesini doldur. Bütün zorunlu gerçek kanıtlar gelmeden kullanıcı trafiği veya servis başlatma yok. |

## #567, #569 ve #638–#657 güncel kanıt durumu

Bu tablo yukarıdaki board snapshot'ı ve ilgili teslim/artifact kapsamını eşler.
`verified`, iş/artifact kabul statüsüdür; **host veya release GO kanıtı
değildir**.

| Görev / durum | Kabul edilen artifact ve kanıt kapsamı | Release kapılarına etkisi |
|---|---|---|
| #567 — verified; kaynak sınıfı protokolü | Task ledger kabul notu: source-class şeması ve protokol iddiası/yetki ayrımı tamamlandı. Eski mesajlar ve CLI wait `unverified/data_only` kalıyor; canlı operator kimliği veya dispatch sağlamıyor. | Kapı 7 açık: protokol etiketi yetkilendirme değildir; auth-off caller `local_unverified` kalır. |
| #569 — verified; server-side source class | Task ledger kabul notu: panel payload'ından `source_class` kaldırıldı; auth-off yazım `unknown/unverified`, auth-on sınıflama principal/scope/allowlist/custody gate'ine bağlı. Custody varsayılan kapalı olduğundan canlı operator etiketi üretilmiyor. | Kapı 7 açık: fixture/code kabulü gerçek auth config, custody veya operator kimliği kabulü değildir. |
| [#638 — verified](restore-check-cli-guard-revision-638.md), [scratch guard raporu](restore-check-cli-task-write-guard-638.md) | Yeni restore-check scratch ağacındaki CLI sabit exit-2 stub ile task mutation yapamaz. Gerçek tarihsel restore-check kopyaları guard içermez; bu kabul onları güvenli yapmaz. | Kapı 3 açık: tarihsel/dev writer ve çalışan süreç envanteri/containment hostta ayrıca doğrulanmalı. |
| #639 — verified; snapshot cursor fixture | Global seçim ve ekran cursor commit sınırı sentetik akışta; dahil edilmeyen dosya cursor'ı ilerletmiyor. Production endpoint veya erişim kontrolü değişmedi. | Kapı 4/8 için dar response-selection fixture'ı; anonim erişimi veya host verisini kabul etmez. |
| [#640 — verified](panel-browser-session-handler-fixture-640.md) ve #642 — verified ephemeral HTTP error fixture | Gerçek Handler dispatch'i fixture server'ında denendi. Dört GET alias session'sız anonim 200; auth gate kapalıyken 11 POST callback'i dispatch edildi. Auth/session açık senaryolarındaki retler sentetik ledger'ı değiştirmedi. | Kapı 6 açık/NO-GO: production GET anonim; auth-off POST dispatch yolu açık. Hata header/redaction fixture'ı runtime policy yerine geçmez. |
| #641 — verified anonymous summary fixture | Summary projection'ın partial/unavailable semantiği ve UI action kilidi sentetik girdilerle sınandı; endpoint/auth/cache değişmedi. | Kapı 4/8 için prototip kanıtı; production GET'e bağlanmış değil. |
| [#643 — verified audit](panel-innerhtml-context-audit-643.md), #653 ve #654 — verified takip düzeltmeleri | R1 rol fallback ve R2 revision HTML sink riskleri dar UI escape/validation değişiklikleri ve sentetik fixture'larla kapatıldı. Gerçek browser/CSP enforce veya tüm UI akışının deployment kabulü değil. | Bilinen iki XSS bulgusunun kapsamı daraldı; kapı 6 ve release/browser kabulü açık kalır. |
| [#644 — verified geçiş sözleşmesi](task-outbox-canonical-writer-transition-644.md), [#657 — verified compatibility fixture](task-outbox-canonical-writer-compat-657.md) | Canonical writer'ın additive root alanlarını koruması, lock/save ve no-write fixture dalları sınandı. Nested outbox semantiği, receipt atomikliği, worker/dispatch ve production entegrasyonu yok. | Kapı 3/7 açık: tek writer tüm kopyalar/process'ler için kanıtlanmadı; outbox production feature-off. |
| [#645 — verified actual-data gate](release-rollback-actual-data-gate-645.md), [#646 — verified doctor projection](release-data-schema-rollback-matrix-632.md), [#647 — verified staging inventory](release-staging-readonly-inventory-647.md) | #645 temporary root'ta manifest/data uyumunu pointer öncesi denetler; #646 source metadata ile actual schema PASS/FAIL/UNKNOWN'ı ayırıp yalnız `candidate` verir; #647 bounded inventory raporu belirsiz staging için `HOLD` tutar. Hiçbiri canlı root/pointer taraması veya cleanup yapmadı. | Kapı 2/5/8 açık: external pin, exact release, çalışan writer durumu, target reader, screen/auxiliary schema, gerçek `YUVA_DIR` ve operator rollback kararı eksik. `candidate`/inventory PASS release GO değildir. |
| #648 — verified local decision-form validator | Sentetik formun completeness/syntax kararıdır; `host_acceptance=not-verified`; release, gerçek kanıt içeriği veya signer kimliği doğrulanmaz. | Operatör checklist'ini destekler, host/owner kabulünün yerini tutmaz. |
| [#649 — verified two-UID runner](operator-broker-two-uid-fixture-649.md), [#650 — verified presence projection](panel-presence-broker-principal-projection-650.md) | #649 disposable Linux fixture koşucusu; host koşusu/uid provisioning yapılmadı. #650 feature-off saf projection; sentetik evidence dışında trusted provenance üretmez. | Kapı 7 açık: production broker/session/UID separation yok; `presence=unknown`, host acceptance `not-verified`. |
| #651 — verified retention decision form; #652 — verified history scanner prototype | Retention/export/delete için owner kararı boş; scanner yalnız marked temp fixture ve bilinen credential pattern'leri. | Kapı 5/7 açık: retention politikası seçilmedi; scanner temiz garanti, gerçek geçmiş taraması, revoke veya purge kanıtı değildir. |
| [#655 — verified operator matrix](panel-anonymous-get-operator-decision-655.md), [#656 — verified snapshot fixture](panel-get-snapshot-acceptance-656.md) | #655 erişim modeli/alan/POST formu operatör seçimini bekliyor. #656 verified fixture selector'ı test-only Handler alt sınıfında `_gonder()` wire serialization öncesi çağırır; `/api/veri` ve `/veri` fixture response body byte bütçesi/`Content-Length`, partial metadata, allowlist ve bilinen-pattern redaction sırasını doğrular. Production `panel.server.H` değiştirilmemiştir; bu yüzden production GET global bütçe/anonim erişim veya tam DLP kanıtı değildir. | Kapı 1/4/6 NO-GO: owner kararı yok, production anonim GET sürüyor; fixture route-wire sınırını test eder ama canlı production Handler'a bağlanmamıştır. Bilinen-pattern redaction tam DLP değildir. |

## Güncel açık kapılar ve owner kararları

- **Kapı 1/4/6 — anonim GET/browser:** #574 kararı tam anonim snapshot'ı
  reddeder ve `verified` statüsündedir; #640 bunu Handler fixture'ında
  doğrular, #655 owner erişim-modeli seçimini bekler. #656 fixture teslimi de
  `verified`: test Handler'da route response wire bütçesi ve redaction sırası
  kapsanır, ancak production Handler'a bağlanmaz. Production anonymous GET ve
  auth-kapalı POST dispatch'i #640'ta açık gözlenmiştir. Operatör kararı ve
  production session/route bypass kabulü yok: **NO-GO**.
- **Kapı 2/5 — release/backup/rollback:** #645/#646 yalnız prototype/doctor
  projeksiyonu; #632 checklist'indeki source pin, gerçek data root, target
  reader/writer ve eşzamanlı writer koşulları bekliyor. #565'e göre adjacent
  checksum authenticity `unverified`; backup sahibi bu sınırlamayı açıkça
  kabul etmeli. **NO-GO/HOLD**.
- **Kapı 3/7 — writer/actor/presence:** #638'in scratch stub'ı tarihsel
  restore-check kopyalarını güvenli yapmıyor; #657 yalnız canonical writer
  additive-field fixture'ı; #649/#650 gerçek broker/UID presence sağlamıyor.
  Eski writer/process envanteri ve broker/presence runtime'ı belirsiz:
  **NO-GO/UNKNOWN**.
- **Kapı 8 — acceptance:** #638–#657 verified fixture/raporları yalnız kendi
  sentetik veya statik kapsamlarına aittir. #656 verified Handler-fixture
  wire-budget sonucu da production handler/host kabuline yükseltilmez.
- **Veri politikası:** #651 retention/export/delete owner formu ve #655
  anonim erişim matrisi doldurulmamış; #574'nin varsayılan NO-GO kararı
  yürürlükte kalır. Politika/rollout sahibi seçilmeden cleanup veya erişim
  modeli etkinleştirilmez.

Bu güncelleme mevcut **NO-GO** kararını değiştirmez. Board statüleri ve ilgili
artifact'lar salt okunur karşılaştırılmıştır; canlı doctor, host, backup,
servis, auth veya veri taraması yapılmadı.

## Kullanıcıya dönük GO/NO-GO koşulları

**GO** ancak operatör aşağıdakilerin tümünü kabul edip release makbuzunda
kanıtlayınca verilebilir:

1. Tek yerel operatör/tek sahipli veri kökü varsayımı kabul edilmiştir; loopback
   HTTP'ye ulaşabilen süreçlerin erişim kapsamı bilinir ve snapshot verisine
   erişmeleri kabul edilmiştir ya da ayrı bir OS/HTTP erişim sınırı kanıtlanmıştır.
2. Temiz ve sabit release manifesti/payload hash'leri bağımsız pin ile eşleşir;
   kurulu `current`, PATH CLI ve panel unit'i aynı release'i kullanır.
3. Etkin CLI, panel ve veri kökü yolları doğrulanmış; eski/ikinci writer
   olmadığı ve görev yazımının kanonik kilitli writer'dan geçtiği kanıtlanmıştır.
4. KOK'un gerçek yolu/sahipliği/izinleri doğrulanmış; pre-release yedek ve
   scratch restore-check gözden geçirilmiştir. Yerel backup authenticity
   `unverified` ise bu sınırlama açıkça kabul edilmiştir.
5. Loopback/browser erişim, auth modu, anonim snapshot ve CSP kalıntı riski
   açıkça kabul edilmiş; `Host`/`Origin`, CORS, no-store veya dosya izinleri
   kullanıcı kimlik doğrulaması diye sunulmamıştır.
6. Presence `unknown`, actor beyanları doğrulanmamış, provider dispatch,
   otomatik görev çıkarımı ve approval yolu kapalıdır.
7. Herhangi bir kapıdaki bilinmeyen sonuç yoktur; test/fixture sonucu host
   kanıtı yerine kullanılmamıştır.

**NO-GO**: Bu koşullardan biri bilinmiyor/sağlanmıyor; farklı UID ya da proxy
erişimi kabul edilmiyor; hassas task/chat/screen snapshot'ı okuyabilecek
istemciler kapsam dışı; eski writer çalışıyor; release/hash/data root farklı;
restore uyumu veya yedek belirsiz; ya da actor/presence/provider davranışı
beklenen sınırın dışında. Mevcut kanıt durumu bu kurallara göre **NO-GO**.

## En kısa güvenli canary sırası

Bu sıra bir yürütme kaydı değildir; bu görevde adımlar çalıştırılmadı.

1. Operatör erişim/snapshot ve tek-operatör threat model'ini kabul etsin (#574
   kararı dahil). Kabul yoksa burada dur.
2. Temiz commit'ten immutable release/payload üret; manifest'i ve bağımsız
   hash pin'ini kaydet. Dirty geliştirme ağacını kurma.
3. Release'i ayrı, henüz etkin olmayan install root'a stage et; manifest/payload
   doğrulaması, `current` hedefi, CLI/panel hash'leri ve data path ayrımını
   doğrula. Bu adım var olan pointer'ı veya servisi değiştirmez.
4. #550 fixture acceptance'ı yalnız sentetik kanıt olarak release makbuzuna
   ekle. Gerçek host için read-only preflight'te PATH/unit/etkin process/port/
   bind/`YUVA_DIR`/eski writer durumunu doğrula; eksik panel servisini başlatma.
5. Ayrı onaylı bakım penceresinde, etkin KOK dışında korumalı backup al; verify
   ve scratch restore-check yap; şema/rollback uyumu ve `HOLD` artıkları
   gözden geçir. Bu matris backup alma veya restore işlemi yapmaz.
6. Bütün kapılar GO olsa bile, gerçek servisi kurma/başlatma veya canlı veriyle
   canary ayrı açık rollout onayı ve işletim planı gerektirir. İlk canary
   manuel ve read-only kapsamda kalmalı; görev/mesaj/provider yazımı ve gerçek
   dispatch yapılmamalıdır. Belirsiz sonuçta trafik açılmaz ve kör rollback/
   restore yapılmaz.

## Dayanak ve kapsam

- `docs/first-local-mvp-scope-go-no-go-536.md` — ürün kapsamı, host kapıları,
  rollback ve açık kalan kanıtlar.
- `docs/release-acceptance-harness-550.md`, `release_acceptance.py` — sentetik
  acceptance kapıları; kasıtlı host `NO-GO`.
- `docs/task-ledger-single-writer-552.md`, `docs/legacy-cli-decommission-540.md`,
  `docs/legacy-cli-task-transition-audit-535.md` — desteklenen writer ve eski
  kopya riski.
- `docs/shared-repo-data-ownership-533.md`, `docs/panel-local-security-snapshot-557.md`,
  `docs/panel-anonymous-snapshot-data-minimization-574.md` — UID, HTTP snapshot
  sınırı ve henüz kabul bekleyen veri kararı.
- `docs/panel-origin-csrf-538.md`, `docs/panel-security-response-headers-562.md` —
  browser filtreleri, ortak response başlıkları ve CSP durumu.
- `docs/backup-verify-restore-check-544.md`, `docs/restore-check-retention-policy-530.md`,
  `docs/backup-authenticity-trust-anchor-565.md` — backup doğrulama,
  scratch/retention ve bağımsız authenticity anchor sınırı.
- `docs/w1b-broker-presence-implementation-plan-514.md`,
  `docs/task-actor-role-trust-boundary-532.md`,
  `docs/chat-command-receipt-contract-566.md` — presence, actor ve dispatch
  sınırları.

Bu belge bir karar matrisi ve sonraki adım tarifidir; kaynak, host, deployment,
servis, backup, auth veya canlı veri üzerinde kabul işlemi değildir.
