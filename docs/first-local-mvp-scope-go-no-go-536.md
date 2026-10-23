# İlk özel yerel MVP: kapsam, Go/No-Go ve geri alma (#536)

**Durum:** ürün/release planı önerisi; hizmetin kurulduğu, canlı kaynağın
doğrulandığı veya launch kararı verildiği anlamına gelmez. Kod, host hesabı,
auth, servis, test, runtime, deployment ve canlı veri değiştirilmedi.

## Önerilen hizmet kapsamı

| Konu | İlk MVP kapsamı | Açıkça kapsam dışı |
|---|---|---|
| Kullanıcı | Tek, güvenilir yerel operatör ve tek sahipli Yuva veri kökü. Aynı OS hesabındaki yerel süreçlere karşı güvenlik/actor doğrulaması iddia edilmez. | Çok kullanıcılı/çok operatör, ajan başına UID, uzak kullanıcı veya doğrulanmış reviewer kimliği. |
| Ağ | Panel yalnız loopback `127.0.0.1:8686` adresinde. README ve `panel/server.py` loopback dışı bind'i reddeder. | LAN, internet, tunnel, reverse proxy, ağdan API kullanımı. Loopback bir authentication mekanizması değildir. |
| Görev akışı | Tek yerel OS hesabındaki güvenilir operatör/ajanlar açık CLI/API çağrılarıyla görev oluşturur, atar, alır ve teslim eder; v2 CLI tek kanonik görev yazarıdır. `--from`/`kimden` aktör etiketi doğrulanmış kimlik değildir ve geçmişte `local_unverified` işaretlenir. | Mesajdan otomatik task çıkarımı, otomatik scheduler/worker başlatma, arka plan dispatch veya doğrulanmış agent adına teslim/review. |
| Presence | Tüm kullanıcılar `unknown`; verified online/offline ya da yeşil model göstergesi yok. Kayıtlı `bagli`, ekran satırı ve `son_okuma` presence/delivery kanıtı değildir. | Broker heartbeat, ajan başına online, verified offline veya presence lease. |
| Provider | Codex/OpenCode dispatch kapalı; provider oturumu, auth/credential, turn, tool veya approval çağrısı yok. | Canlı model dispatch'i, provider credential saklama, approval yanıtı, otomatik retry. |
| Veri ve release | Kod değiştirilmeyen doğrulanmış release, ortak `current` pointer ve release dışında tek `YUVA_DIR`; tek writer ve geri dönüş uyumu kanıtlanır. | Geliştirme ağacından kalıcı hizmet, eski/yedek CLI'lerin ortak veriye yazması, release ile veri kökünü birleştirme. |

Bu MVP “kişisel tek operatör aracı”dır, kimliği doğrulanmış audit hizmeti
değildir. Kaynakta HMAC kapısı opsiyonel ve varsayılan kapalıdır; auth kapalıyken
panel task aktörünü request gövdesinden, CLI ise `--from` argümanından alabilir.
Bu alanlar gerçek çağıranı kanıtlamaz. Tek operatör/host hesabı varsayımı kabul
edilemiyorsa veya task geçmişindeki actor/reviewer kararı denetlenebilir kimlik
gerektiriyorsa launch **No-Go** olur; auth taslağını sessizce açmak bu planın
parçası değildir.

## Girdilerin durumu ve güven düzeyi

Bu tablo Yuva görev tahtasının 2026-10-23 16:46 statik görünümüdür. `verified`
olanlar kabul edilmiş tasarım/incelemedir; implementasyon veya host kurulumu
kanıtı değildir. `pending_verification` teslimleri rapor içerikleri olarak
kullanılır, ancak reviewer kabulü tamamlanana kadar ilgili release kapısı açık
kalır.

| Girdi | Tahta durumu | MVP planında kullanımı |
|---|---|---|
| #508 CLI kopya cutover kabul listesi | `verified` | Kaynak/release hash'i, tek CLI ve panel hedefi, tek `YUVA_DIR`, eski writer yokluğu, backup ve rollback uyumu launch kanıtıdır. |
| #514 feature-off broker/presence planı | `verified` | Broker/presence açık değildir; `unknown` korunur. #514 onayı implementasyon/host kurulum onayı değildir. |
| #520 repo systemd unit şablonu | `verified` | Unit şablonu `current` release kodu ve ayrı `%h/yuva` veri köküne işaret eder; kurulu unit veya çalışan process kanıtı değildir. |
| #530 restore-check retention notu | `verified` | 30 gün, restore sonucunun operator kabulünden başlar; manifest/archive/hash bağı ve aktif kullanım olmadan temizleme yok. İki mevcut kontrol ağacı `HOLD/unknown`; arşiv saklama kararı ayrıdır. Politika uygulandığı/silme yapıldığı anlamına gelmez. |
| #531 presence UI copy notu | `verified` | UI metin gap'i analizi kabul edildi, UI değişmedi: ekran boş durumu presence ile karışıyor; ekip sekmesi offline/unknown breakdown vermiyor. Düzeltme veya açıkça kabul edilmiş release metni gerekir. |
| #532 task actor/role statik incelemesi | `verified` | Auth-off body `kimden`, CLI `--from`, kısmi rol denetimi ve provenance eksikliği doğrulandı. Reviewer notu P0 actor/writer sınırını ilk hizmet kapısı sayıyor; rapor uygulama değildir. |
| #533 ortak repo/veri sahipliği | `pending_verification` | `docs/shared-repo-data-ownership-533.md` tek owner'lı 0700 KOK, euid/mode doğrulaması, read-only release ve ortak grup/ACL modelini reddediyor. Farklı UID'ler aynı Yuva KOK'unu doğrudan paylaşamaz; gerekiyorsa tek sahipli broker sonraki fazdır. Host izinleri incelenmedi. |
| #534 HTTP header/cache incelemesi | `pending_verification` | `docs/panel-http-security-headers-cache-policy-534.md`: `_gonder` no-store ve MIME, CORS kapalı/OPTIONS 405 iyi başlangıç; `nosniff`, CSP, Referrer-Policy eksik, bazı `send_error` yolları ortak header set'ini atlayabilir. Anonymous GET ve aynı namespace'te farklı UID erişimi sürüyor; önerilen header değişikliği uygulanmış değil. |
| #535 legacy CLI geçiş denetimi | `verified` | Eski `~/yuva/bin/yuva` ortak görev verisine kilitsiz ve terminal durum guard'ları olmadan yazabilir. Mutasyonlar sadece doğrulanmış current release CLI ile yapılmalı; eski writer varsa No-Go. |

Kaynak gerçekleri: README paneli manuel sohbet/tahta ve kaydedilmiş ekranlar
olarak tanımlar; mesaj kaydı canlı push değildir. `/api/veri` bugün `online=false`,
`presence_state=unknown`, `presence_verified=false` sunar. `panel/server.py`
varsayılan host'u `127.0.0.1` yapar ve loopback dışı bind'i reddeder; README
loopback ve Host/Origin kontrollerinin authentication olmadığını açıklar.
Bunlar statik kaynak davranışıdır; etkin host süreci/configuration kanıtı
değildir.

## Launch blocker'ları

| Kapı | Go için gereken kanıt | No-Go koşulu |
|---|---|---|
| Özel erişim sınırı | Host tek güvenilir OS hesabına ayrılmış olmalı; `--host 127.0.0.1` etkin süreç ve browser erişiminde doğrulanmalı; LAN/tunnel/reverse proxy yok. #533 sahiplik kapısı: tek UID KOK owner ve aynı UID içindeki süreçler trusted boundary'dedir. | Host çok kullanıcılı/güven sınırı belirsiz; auth'sız API'ye başka local UID/browser-origin erişimi olabilir; loopback dışı/proxy erişim var. Loopback/Host/Origin kontrolleri auth değildir; ortak KOK'u farklı UID'lerle ACL üzerinden açmak kabul edilmez. |
| Tek kanonik release | Commit/tree, immutable release path ve CLI/panel manifest hash'leri kaydedilmiş; `current` beklenen release'e gidiyor; PATH CLI ve panel unit aynı current pointer'ı kullanıyor. #520 örnek şablondur; kurulu unit ve çalışan process ayrı kanıtla kontrol edilir. | Kod development tree/legacy copy'den çalışıyor; etkin CLI/panel hedefi bilinmiyor; manifest/hash uyuşmuyor veya unit/CLI farklı release seçiyor. |
| Tek veri sahibi ve writer | CLI/panel aynı absolute `YUVA_DIR` kullanıyor ve release dizini dışında; eski panel/CLI writer'ları durmuş/engellenmiş; görev writer'ı ortak lock kullanan kanonik release. | Birden çok release aynı veri köküne eşzamanlı yazabilir; eski `~/yuva` CLI erişilebilir ve mutation yapabilir; kod/veri kökü karışmış. |
| Backup ve geri dönüş | Release öncesi veri kökü dışında korumalı backup; archive adı/hash, kaynak kök, restore-check sonucu ve operator kabul kaydı bağlı. Restore doğrulaması izole alanda tamamlanmış; rollback hedefi ve şema uyumu bilinmiş. #530 retention kararı kabul edilmiş; mevcut kontrol ağaçları provenance/aktif kullanım kararı olmadan HOLD kalır. | Restore başarısız/eksik/unknown; backup provenance yok; kontrol ağacı active/hold/unknown; geri dönüşte yeni şema eski release ile uyumsuz. |
| Manuel task/actor sınırı | Tek operatör threat model'i ve actor provenance sınırlaması açıkça kabul edilir; `kimden`/`--from` verified actor/audit kanıtı değildir. Mutasyon yalnız current release, tek KOK owner ve kanonik writer üzerinden yapılır; #532/#535 şartları geçerlidir. | Ayrı operator/reviewer yetkisi, kriptografik actor attribution veya audit trail ürün gereksinimidir; fakat auth/authorization/provenance kapısı yoktur. Eski/başka CLI writer aynı KOK'a erişebilir. |
| Presence ve UI dili | #514 feature-off durumu korunur: unknown; #531 copy gap'i uygulanmış veya release UI metniyle açıkça giderilmiş; UI verified online/offline iddiası üretmez; boş ekran kaydı presence ile karıştırılmaz. | Eski heartbeat/`bagli`/ekran/sohbet activity yeşil veya offline kanıtı olur; copy API'nin kanıtını aşar. |
| Provider kapalı | İlk release'te provider transport/credential/dispatch/approval writer yolu devre dışı olduğuna dair release/source konfigürasyon incelemesi; manuel Yuva mesajı yalnız kayda alınır. | Provider request otomatik veya kullanıcı mesajıyla tetiklenebilir; credential mevcut hizmette gerekir; dispatch durumunun unknown/off olduğu kanıtlanamaz. |
| Veri içeriği/cache | `_gonder` no-store ve açık MIME davranışı korunur; tüm hata cevapları dahil `nosniff`, `no-referrer` ve inline UI'ye uyumlu CSP kararı uygulanıp gözden geçirilir. CORS kapalı kalır; anonymous GET bilinen erişim sınırı olarak kabul edilir. | CSP/header boşlukları veya handler dışı hata yolu açık; hassas snapshot cache edilir; anonymous GET'i auth'lı sanma; başka local UID'den gizlilik bekleme. |

## Sıralı Go/No-Go

Her adım önceki adımlar Go olmadan ilerletilmez. Bu belge kabul kanıtı üretmez;
işaretli maddeler gelecekteki kontrollü release/host geçişinde doldurulmalıdır.

1. **G0 — kapsam dondur:** Tek operatör/tek OS hesabı, loopback, açık CLI/API görev çağrıları,
   presence unknown ve provider dispatch off sınırını release kaydında onayla.
   `kimden`/`--from` actor attribution değildir; aynı UID içindeki süreçler
   trusted boundary'dedir. Bu varsayım kabul edilmiyorsa No-Go.
2. **G1 — review kararlarını kapat:** #530–#532 `verified`; #533/#534 raporları
   teslim edilmiş olsa da `pending_verification`. Son iki review ve uygulama
   kararları tamamlanmadan KOK multi-UID sınırı veya browser header/cache
   hazırlığı Go sayılamaz. #531 UI gap'i uygulanmadıysa açık kalır.
3. **G2 — release'i sabitle:** Temiz/kanıtlı commit'ten immutable release
   üret; manifest ve CLI/panel hash'lerini kaydet; `current` ve PATH hedeflerini
   statik olarak karşılaştır. Eski/dev kopyalar mutasyon yolundan çıkarılsın.
4. **G3 — veri ve backup:** Tek absolute `YUVA_DIR`, owner/permissions/backup
   retention ve izole restore-check makbuzunu doğrula. Restore-check geçici
   dizinlerini archive/hash bağı ve aktif kullanım netleşene kadar `HOLD` tut;
   yaş/mtime ile otomatik cleanup yok.
5. **G4 — servis ve web yüzeyi:** `contrib/systemd/yuva-panel.service` yalnız
   örnek şablondur. Kurulu unit'in current path + ayrı data path kullandığını,
   etkin process'in bu release'ten başladığını ve eski writer olmadığını
   hostta doğrula. Loopback dışı erişim, #534 `send_error`/security-header
   gap'leri ve anonymous GET riskinin operator boundary'si kapanmadan browser
   Go yok.
6. **G5 — ürün semantiği:** Manuel task kayıt/atama akışının provider dispatch
   yapmadığını; API/UI presence'ın unknown kaldığını; UI copy'nin #531 önerisiyle
   tutarlı olduğunu; Yuva message kaydının agent delivery receipt olmadığını
   gözden geçir. Bu aşama actor kimliğini doğrulamış sayılmaz.
7. **G6 — tek-operatör Go:** Yalnız G0–G5 kanıtları tamamlandığında operator
   sınırlı açılışı kabul eder. Herhangi bir release/data/process/actor/presence
   kanıtı eksikse No-Go ve erişim/dispatch kapalı kalır. G6 için canlı canary
   bu görev kapsamında yapılmamıştır.

## Rollback checklist'i

Rollback kod işaretçisini geri alır; ortak Yuva verisini otomatik geri yüklemez.
Herhangi bir commit/restore sonucu belirsizse yazımları dondur ve kanıtı koru;
kör rollback/backup restore yapma.

1. Yeni manuel task/message yazımlarını durdur; panel ve CLI writer çağrılarının
   tamamlanmasını bekle. Aynı `YUVA_DIR` üzerinde başka bir writer kalmadığını
   kanıtlamadan eski sürümü başlatma.
2. Panel unit/prosesini durdur ve 8686 portunun boş olduğunu doğrula. Symlink
   değişimi önceden açılmış process image'ını değiştirmez; eski proses kendi
   başına veri yazmaya devam edebilir.
3. Önceki release'in immutable dizin, commit/tree ve manifest/hash kanıtını
   doğrula. `current` yalnız uyumlu olduğu kanıtlanmış release'e alınır; CLI ve
   panel aynı pointer'ı izlemelidir.
4. `YUVA_DIR` değerini olduğu gibi koru ve ayrı veri kökü olarak doğrula. Kod
   rollback'i backup restore değildir. Yeni sürümün yazdığı şema eski release
   tarafından okunamıyorsa aynı veri köküne bağlanma; No-Go/izole kurtarma
   kararı ver.
5. Servis yeniden açılmadan önce auth/loopback ve provider dispatch-off
   kapsamını tekrar doğrula. Presence `unknown` kalır; eski snapshot/heartbeat
   yeşile yükseltilmez.
6. Rollback sonrası release target, CLI/panel path, `YUVA_DIR`, backup
   referansı ve bilinen hata/unknown durumlarını operatör makbuzuna yaz. Bu
   maddeler tamamlanana kadar yeni kullanıcı/ajan veya provider ekleme.

## Sonraki fazlar — ilk MVP'de kapalı

- Broker principal, ajan başına UID/HOME/user manager, güvenli IPC ve
  doğrulanmış provider-session presence (#514/#533 ve yeni host kabulü).
- Çok operatör, doğrulanmış task actor/role/reviewer authorization, audit
  provenance ve API auth policy (#532 gap'leri kapatılmadan yok).
- Codex/OpenCode provider dispatch, kalıcı receipt/unknown reconciliation,
  credential lifecycle, approval writer ve otomatik görev kuyruğu.
- Remote/reverse-proxy erişimi; ayrı authentication, authorization, CSRF,
  security-header/cache review ve deployment planı olmadan açılmaz.

Bu fazlar first-MVP launch blocker'ı değildir; first MVP bunları kullanmaz ve
aktif hale getirmez. İlk MVP'nin kendi blocker'ları olan tek release/tek writer,
backup/restore, loopback/web güvenliği ve private-operatör varsayımı ise faz
ertelenerek geçilemez.

## Dayanaklar

- `README.md` ve `panel/server.py` — manuel sohbet/tahta sınırı, loopback-only
  host kontrolü, auth varsayılanı ve veri kökü/release pointer tarifi.
- `docs/yuva-cli-copy-cutover-acceptance-508.md` — tek kaynak, manifest, tek
  CLI/panel target, data root, writer tekilliği, backup, rollback ve şema uyumu.
- `docs/w1b-broker-presence-implementation-plan-514.md` ve
  `contrib/systemd/yuva-panel.service` — presence feature-off/unknown ve
  current-release unit örneği; kurulu service/process kanıtı değil.
- `docs/restore-check-retention-policy-530.md` — restore-check provenance,
  HOLD/ACTIVE/ACCEPTED ve temizleme kapısı önerisi (Yuva #530 verified; politika
  uygulama veya silme değildir).
- `docs/panel-presence-copy-contract-531.md` — presence copy ve ekran boş durum
  boşluğu (Yuva #531 verified; UI değişikliği yapılmadı).
- `docs/task-actor-role-trust-boundary-532.md` — auth kapalı actor iddiası,
  CLI `--from` ve provenance sınırı (Yuva #532 verified; P0 actor/writer gate
  uygulamada hâlâ açık).
- `docs/shared-repo-data-ownership-533.md` — tek-owner KOK/euid/mode sınırı ve
  çok UID paylaşımı için broker gereği (Yuva #533 pending_verification).
- `docs/panel-http-security-headers-cache-policy-534.md` — no-store/CORS
  başlangıçları, eksik response header'ları ve anonymous GET sınırı (Yuva #534
  pending_verification).
- `docs/legacy-cli-task-transition-audit-535.md` — eski `~/yuva` CLI'nin
  kilitsiz görev yazımı/guard boşluğu ve kanonik writer kabul koşulu.
- `docs/linux-gecis.md` — host cutover ve rollback prosedürü; canlı rollout
  kanıtı değildir.
