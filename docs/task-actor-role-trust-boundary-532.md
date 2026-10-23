# #532 — Görev mutasyonlarında aktör ve rol güven sınırı

**Tarih:** 2026-10-23
**İnceleme:** Güncel `yuva-v2` CLI/panel kaynakları ile #60, #433, #437 ve #452 kararlarının salt statik karşılaştırması.
**Sınır:** Kod, veri, auth ayarı veya servis değiştirilmedi; test, HTTP ya da runtime çalıştırılmadı. Auth kapısının canlı kurulumda açık olup olmadığı incelenmedi.

## Kaynak anlık görüntüsü

| Kaynak | SHA-256 |
|---|---|
| `bin/yuva` | `824a8d4379e45b9e40e7316d418fa3fad918388b11164dc11aab1c7c07ea0510` |
| `panel/server.py` | `683f1b94847a999eea149b2d33fb918c2eca8151aef389c6f9e4adc2c5615245` |
| `panel/auth.py` | `ae22be353db0306c86a51c8c86f5be987f20947c038f30778952bf77fee55b99` |

## Yönetici özeti

1. Görev geçişlerinin dosya tutarlılığı v2 CLI’de ortak `.kilit` altında korunuyor; bu, aktör kimliğini doğrulamıyor. Doğrudan CLI çağrıları `--from` değerini çağıran olarak kabul ediyor.
2. Paneldeki HMAC kapısı kaynakta **varsayılan kapalı**. Kapalıyken `/api/gorev` aktörünü JSON gövdesindeki `kimden` alanından seçiyor. Açıkken HMAC principal’ı aktör olarak geçiriyor ve bütün görev API işlemlerini yalnız yapılandırılmış admin principal’larına açıyor.
3. CLI rol politikası kısmi: ilk kontrol `goreci`, son denetim `denetci` ve yönlendirilmiş reviewer kontrolleri içeriyor. Görev ekleme/atama/iptal etme rol/yetki denetimi yapmıyor; alma/teslim ise yalnız `--from` ile assignee eşitliğine dayanıyor.
4. Görev geçmişi aktör metnini kaydediyor, fakat bu aktörün CLI argümanı mı, gövde iddiası mı yoksa doğrulanmış HMAC principal’ı mı olduğunu ve hangi auth key/scope ile geldiğini görev olayına yazmıyor.
5. #60’ın yerel güven sınırı sonucu hâlâ geçerli: aynı OS kullanıcısındaki süreç CLI’yi çağırabilir ve ortak dosyaları doğrudan değiştirebilir. Loopback, `.kilit`, `--from` ve aynı UID altında tutulan token tek başına güvenilir principal oluşturmaz.

## Kaynak ve karar bağlamı

- **#60 — “Panel kimlik/rol ve görev API yetki sınırları”:** Tarihsel `yuva-dev` kaynak incelemesi, istemcinin `kimden`/`kimlik`/rol iddialarının API’de yetkisiz kabul edildiğini ve `/api/gorev` geçişlerinde sahiplik/rol denetimi olmadığını bulmuştu. Aynı UID, loopback ve istemci kontrollü token/Origin değerlerinin gerçek kimlik doğrulaması sayılamayacağı; gerçek sınır için ayrı UID ve doğrulanmış broker/peer ya da ayrı güven kökü gerektiği belirtilmişti. Bu eski kaynak bulguları güncel v2 durumunun yerine kullanılmadı.
- **#433:** Görev kaydı `.kilit` altında commit edilir, bildirim JSONL’si sonradan ayrı yazılır; iptal bildirimi yoktur. Durum değişmişken bildirim veya fsync hatası istemciye kesin başarısızlık gibi yansıyabilir.
- **#437:** Operation ID ve outbox tekrarları/idempotency sorunlarını azaltabilir; `kimden`/`--from` için kimlik doğrulaması ya da yetki sağlamaz.
- **#452:** `rejected`, `committed`, `commit_unknown` ve `delivery_unknown` sonuçlarını ayırmayı; auth sonucu ile mutation receipt’ini ayrı sözleşmeler olarak ele almayı önerir. Mevcut köprünün HTTP 400/500 sınıfları bu garantileri vermez.

## Katmanlara göre davranış matrisi

| İşlem | CLI (`bin/yuva`) aktör/rol ve geçiş | Panel API aktörü/rolü | Provenance ve hata sınırı |
|---|---|---|---|
| `ekle` | `--from` zorunlu, fakat kimlik doğrulaması yok. `--ata` hedefi için işçi rolü kontrol edilmiyor; isteğe bağlı `--gorevli` hedefi `goreci` rolüne göre doğrulanıyor (`bin/yuva:1996-2025`). | Auth kapalıysa gövde `kimden` aktör olur. Auth açıksa `/api/gorev` yalnız configured admin principal’larına açık; principal ID CLI’ye `--from` olarak aktarılır (`server.py:1316-1379`; `auth_integration_draft.py:28-42,190-210`). | Görev geçmişi yalnız aktör string’ini içerir (`bin/yuva:1971-1976`); doğrulama kaynağı/key ID kaydedilmez. Görev commit’i ile JSONL mesajı ayrı yazılır.
| `ata` / yeniden ata | Durum yalnız `pending`, `assigned`, `pending_revision` olabilir. `--from` rolü/atanan hedef için işçi rolü doğrulanmaz. İlk kontrol kuyruğunda assignee sabit kalır; yalnız `goreci` seçimi doğrulanır (`:2028-2069`). | Auth kapalıyken `kimden` gövde iddiasıdır; açıkken admin principal gerekir. API hedefi CLI’ye iletir. | CLI guard retleri `SystemExit` ile non-zero olur. API bunu 400’e çevirir; commit sonrası başka hata olursa sonuç kesin ret olmayabilir.
| `al` / `sonraki` | Yalnız pending/revision, başka assignee varsa ret; boş assignee’yi `--from` iddiasına atar. Claim eden kimliğin kayıtlı/işçi rolünde olduğu kontrol edilmez (`:2072-2184`). | Panel `al` işlemini de aynı genel `/api/gorev` admin politikasından geçirir. Auth kapalıyken aktör gövde iddiasıdır. | Claim olayı aktör string’i ile kaydedilir; gerçek oturumla bağı yoktur. Claim commit’inden sonra bildirim yazılır.
| `teslim` | Durum `assigned`, assignee boş değil ve assignee `--from` ile aynı olmalı. `--from` taklit edilebilir. Görevli/reviewer hedefleri için bazı güncel rol kontrolleri yapılır (`:2186-2228`). | Auth kapalıyken body `kimden`; açıkken admin principal. Gated API, kayıtlı işçi assignee’sinin doğrudan teslimine izin veren ayrı bir self/worker policy sunmuyor. | Yalnız “teslim edildi” aktör metni tutulur. JSONL raporu commit sonrasında yazılır; #433/#452’deki belirsizlik sürer.
| `ilk-kontrol` | Görev `pending_gorevli_review` olmalı; `--from` hem kayıtlı `goreci` rolüne hem `gorevli_kimlik` değerine uymalı (`:2243-2270`). Argüman hâlâ doğrulanmış süreç kimliği değildir. | Auth kapalıyken gövde iddiası; açıkken yalnız admin. `AuthGate` endpoint rolü ile CLI’deki `goreci` rol denetimi farklı kontrollerdir. | Sonuç görev geçmişinde aktör string’i; auth key/scope/request ID yok.
| `denetle` | Rol `denetci`, reviewer yönlendirmesi (baş denetçi istisnası), tek karar bayrağı ve `pending_verification` durumu aranır (`:2273-2308`). `--from` kimlik iddiası olduğu için rol verisiyle eşleşme tek başına caller doğrulamaz. | Auth açıkken sadece configured admin principal’ı `/api/gorev` çağırabilir; `denetci` rolü ayrıca CLI’nin `durum.json` kaydında aranır. Admin ve Yuva denetçi listeleri eşleşmezse geçerli HMAC çağrısı da CLI’de reddedilebilir. | JSON boolean `revize` doğrulaması yoksa API 400 döner (`server.py:1330-1339`). Non-zero CLI sonucu 400; timeout/exception 500.
| `iptal` | Yalnız terminal olmayan durumdan `dropped` yapar; görev açanı, assignee’yi veya görevli/denetçi rolünü kontrol etmez (`bin/yuva:2311-2326`). Herhangi bir doğrudan CLI çağrısı `--from` iddiasını seçebilir. | Auth kapalıysa aktör body `kimden`; açıkken configured admin gerekir. | CLI iptal için inbox mesajı üretmez (#433). Panel başarı/ret sınıfları commit belirsizliğini ayırt etmiyor.

## Auth, actor ve rol ayrımı

- Panel `do_POST`, source/body boyutu kontrolünden sonra HMAC doğrulamasını JSON parse ve handler dispatch’inden önce çalıştırıyor (`panel/server.py:1700-1750`). Bu olumlu sıralama yalnız `AUTH_GATE` kuruluysa geçerli.
- `auth_gate_yukle()` `YUVA_AUTH_ENABLED` yok veya `0` ise `None` döndürüyor; `1` için açık store/audience gerekir (`server.py:1405-1449`). Bu rapor env veya canlı panel durumunu okumadı; yalnız kodun varsayılanını bildiriyor.
- Auth entegrasyonunda `/api/gorev` policy’si tüm workflow işlemleri için `admin` (`panel/auth_integration_draft.py:28-42`). Bu route-scope yetkisidir; CLI’deki işçi/görevli/denetçi iş kurallarını kaldırmaz veya güncel CLI çağrısını HMAC’siz güvenilir yapmaz.
- Auth açıkken `gorev_calistir()` aktör metnini request body’den değil `principal.principal_id` değerinden kuruyor; auth kapalıyken `g.kimden` kullanılıyor (`server.py:1370-1387`). Böylece bu tek API köprüsünde body actor’ı devre dışı kalıyor. Doğrudan CLI yine `--from` alıyor; auth gate CLI’yi veya dosya yazımını korumuyor.
- `gorev_guncelle()` ortak `.kilit` altında görev JSON’unu güncelliyor (`bin/yuva:1987-1993`). Kilit yarış ve kaza kaynaklı çakışmayı azaltır; aktör kimliğini, işletim sistemi sınırını veya kötü niyetli aynı-UID yazarı doğrulamaz.
- `gorev_olay_ekle()` geçmişe `kimden`, olay ve not yazıyor; `principal_id`, auth yöntemi/scope’u, key ID, istemci request/operation ID veya `verified/unverified` kanıtı eklemiyor (`bin/yuva:1971-1976`). Görev geçmişi bu nedenle denetlenebilir bir iş akışı günlüğü olsa da kriptografik audit trail değildir.

## Hata ve retry davranışı

1. CLI her geçişte görev snapshot’ını kilit altında kaydeder; uygun komutlarda JSONL bildirimi bu işlemden sonra yapılır. İşlem durumu commit edildikten sonra bildirim yazımı başarısız olabilir (#433, #437).
2. Panel CLI’yi 15 saniye timeout ile çalıştırıyor; CLI non-zero olursa HTTP 400, subprocess exception/timeout olursa HTTP 500 üretir (`panel/server.py:1381-1387`). Bu yanıtlar “mutation kesin olmadı” demek değildir. `commit_unknown` ve `delivery_unknown` makbuzu mevcut akışta yoktur (#452).
3. Auth reddi (401/403) handler dispatch’inden önce gelir; bu, auth açık çağrılarda mutation öncesi ret sağlar. Ancak mevcut auth integration bir “görev API’si yalnız admin” politikası uygularken operasyon bazlı worker/reviewer/coordinator ayrımı yapmıyor.
4. `operation_id`/outbox önerisi (#437) duplicate ve retry sorununu hedefler; actor authorization’ın yerine geçmemeli. Ret, auth ve mutation makbuzu ayrı sonuç sınıfları olarak tutulmalı (#452).

## Gap matrisi ve önem

| Öncelik | Gap | Etki / kanıt |
|---|---|---|
| **P0** | API auth kapısı opsiyonel ve varsayılan kapalı; kapalı modda aktör body’den geliyor. Doğrudan CLI `--from` kabul ediyor. | Taklit aktörle görev oluşturma/atama/iptal veya sahte geçmiş girdisi. `server.py:1370-1379,1412-1421`; `bin/yuva:2521-2529`. Aynı-UID doğrudan dosya/CLI erişimi ayrı güven sınırı olmaya devam eder (#60). |
| **P1** | CLI’de `ekle`, `ata`, `iptal` için çağıran rol/nesne yetkisi yok; `al`/`teslim` assignee kontrolü istemci `--from` değerine bağlı. | İzin verilen geçişler başka aktör adına yürütülebilir; `iptal` herhangi bir non-terminal işi kapatabilir. `bin/yuva:1996-2061,2072-2096,2186-2228,2311-2326`. |
| **P1** | Auth açık API yalnız admin scope kullanıyor; bütün task işlemlerini tek kaba role topluyor. Admin principal ile `durum.json` denetçi rolü/inceleyen kaydı ayrı ve tutarsız olabilir. | Worker kendi task’ını teslim etmek için API kullanamaz; admin-only atama/iptal ve denetim dar görev politikasını yansıtmaz. `auth_integration_draft.py:28-42`; `server.py:1370-1387`; `bin/yuva:2273-2308`. |
| **P1** | Geçmiş olayı aktörün kaynağını kanıtlamıyor. | `gecmis[].kimden` aynı biçimde body iddiasını, CLI `--from` değerini veya doğrulanmış principal’ı gösterebilir. `bin/yuva:1971-1976`; #437’nin `kimden` uyarısı. |
| **P2** | Görev commit’i, JSONL notification ve HTTP yanıtı tek işlem/receipt değil. | İstemci 400/500/timeout sonrası kör retry ile duplicate veya görünürlük uyuşmazlığı üretebilir. #433, #437, #452; güncel köprü `server.py:1381-1387`. |
| **P2** | Kilitli v2 writer yanında eski CLI kopyası varsa aynı `YUVA_DIR`’ye kilitsiz görev yazımı yapabilir. | Atomik/serileştirilmiş geçiş güvencesi eski writer ile ortaklaşmıyor; #535 denetimi ve #437 rollout uyarısı. |

## Öncelikli düzeltme ve kabul sırası

1. **Tek görev yazma sınırı ve principal kaynağı:** Görev yazımları tek güncel CLI/broker yoluna kapatılmalı. Panelde admin HMAC kapısı işletim kararıyla açılmadıkça API aktör iddiaları yetkili sayılmamalı; doğrudan CLI erişiminin aynı UID altında güvenilir olduğunu varsaymamalı. Gerçek aynı-UID ayrımı gerekiyorsa ayrı OS kimliği + UID doğrulayan IPC/broker tasarlanmalı (#60 ve #451).
2. **İşlem bazlı authorization matrix:** `ekle/ata/iptal`, `al/teslim`, `ilk-kontrol`, `denetle` için aktör, görev sahipliği, role ve hedef durumu açıkça tanımlanmalı. Aynı policy, hem server handler’da (principal üstünden) hem core CLI mutasyonunda uygulanmalı; CLI doğrudan çalıştırıldığında auth bypass oluşmamalı. Admin override ayrı ve audit edilebilir olmalı.
3. **Principal ile claim’i ayır:** API JSON `kimden` alanı aktör olmamalı; HMAC principal ayrı taşınmalı. Doğrudan CLI için de `--from` bir iddia olarak sınıflandırılmalı veya sadece broker tarafından çağrılan trusted operation context ile değiştirilmelidir. Audit olayına auth yöntemi, verified principal, scope/key kimliği ve request/operation referansı eklenmeli; geçmiş kayıtlarında kanıt olmayan actor `unknown/unverified` sayılmalı.
4. **Güvenli retry sözleşmesi:** #437/#452’deki operation makbuzu + outbox + sabit event ID ve `rejected/committed/commit_unknown/delivery_unknown` sonuçları actor authorization’dan bağımsız uygulanmalı. HTTP sonucu non-zero/timeout’u kesin ret gibi yorumlamamalı.
5. **Eski writer kapısı:** Kilitsiz `~/yuva/bin/yuva` görev mutasyonları ortak veri kökünde çalışmamalı; CLI kopyalarının hash/kullanım yolu envanteri tutulmalı. Karışık sürüm rollout’u ya reddedilmeli ya eski yazarın yeni kurallarla uyumlu olduğu kaynak/ kabul kanıtıyla gösterilmeli (#535, #437).
6. **Statik ve dinamik kabul:** Her işlem için doğru rol/assignee, farklı actor, `--from` taklidi, auth off/on, yanlış HMAC scope, aynı-UID direct CLI ve stale CLI writer senaryoları tanımlanmalı. Yetkisiz istekte görev JSON’u ve geçmişi değişmemeli; worker/reviewer/coordinator’a izin verilen en dar iş akışı çalışmalı; commit sonrası hata aynı operation ID ile uzlaştırılmalı. Bu görev kapsamında bu senaryolar çalıştırılmadı.

## Sonuç

v2 geçiş guard’ları ve `.kilit` görev kaydını tutarlı güncellemeye yardım ediyor; bunlar aktör doğrulaması değil. API feature-off kaldığında JSON `kimden`, doğrudan CLI’de `--from` aktörü seçiyor. Feature-on API, doğrulanmış principal kullanıyor ancak tüm görev uçlarını yalnız admin’e topluyor ve CLI’nin ayrı rol haritasıyla çakışabilir. Güvenli çözüm sırası: tek yetkili yazıcı/principal sınırı, işlem bazlı authorization, provenance’lı audit kaydı, sonra idempotent receipt/outbox ve eski writer kullanım dışı bırakma. Aynı UID’li yerel süreçlere karşı API katmanı tek başına güven sınırı oluşturmaz.
