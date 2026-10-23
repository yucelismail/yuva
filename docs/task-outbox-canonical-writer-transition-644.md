# Task outbox prototipinden canonical writer'a geçiş sözleşmesi (#644)

**Karar:** `prototypes/task-outbox` canonical writer değildir ve canlı
`YUVA_DIR`'e bağlanmaz. Geçiş, prototip kodunu kopyalayarak değil, önce
canonical CLI/panel çağrı grafiğinde additive ledger alanlarının korunmasını,
sonra idempotent task commit'ini ve en son notification delivery worker'ını
ayrı kabul kapılarıyla uygulayarak yapılır. Bu belge tasarım/uyumluluk
sözleşmesidir; entegrasyon, migration veya canlı rollout yapıldığı anlamına
gelmez.

## Bugünkü durum ve uyumluluk kapsamı

| Parça | Bugünkü davranış | Geçişte gereken sınır |
|---|---|---|
| Canonical task ledger | `bin/yuva` `gorev_yukle()` ile root schema v1'i okur; `gorev_guncelle()` ortak `.kilit` altında güncel nesneyi değiştirip `kaydet(GOREV, gb)` ile atomik yazar. Panel `/api/gorev` aynı CLI core'a dispatch eder. | Bu desteklenen yol owner olmaya devam eder. Receipt/outbox işlemleri de aynı schema kontrolü, veri kökü, kilit ve canonical save yolundan geçmelidir. (`docs/task-writer-call-graph-611.md`, `bin/yuva`) |
| Task outbox fixture | İzole temp `YUVA_DIR`; schema-less root'u v1 kabul eder; optional `operations` ve `outbox` alanlarını ekler/korur; unknown v1 root fields'i bırakır. | Yalnız davranış fixture'ı. Constructor, lock, dosya izinleri, append ve test fault injection kodu production modülüne taşınmamalıdır. (`prototypes/task-outbox/README.md`, `task_outbox.py`) |
| Notification write | Canonical CLI task status/history commit'inden sonra `mesaj_ekle()` ile ayrı `mesaj.jsonl` append yapar; tek transaction veya idempotency receipt yoktur. | Outbox worker yalnız canonical task snapshot commit'i kesin olduktan sonra çalışır; task mutation handler'ı ikinci kez çalıştırılmaz. (`docs/task-notification-idempotency-575.md`) |
| Diğer CLI kopyaları | Bazı dev/UI/restore kopyaları canonical schema/lock uyumunu sağlamıyor; #622 guard ve #611/#627 inventory bu riski sınırlı olarak belgeler. | `operations`/`outbox` alanlarını koruduğu test edilmemiş bir writer aynı ledger'a yazamaz. Karışık release için GO verilmez. |

Canonical `kaydet()` yalnız root schema sürümünü doğrulayıp aldığı nesneyi
serialize eder; çağıranın yüklediği root alanlarını callback değiştirmiyorsa
korur. Bu, `operations`/`outbox` davranışının desteklendiği veya daha eski
writer'ların bu alanları koruyacağı anlamına gelmez. Root schema v1'e additive
alan ekleme kararı ancak canonical ve desteklenen read/write yollarında
round-trip testinden sonra geçerlidir. Nested receipt/outbox shape, boyut,
retention veya değer sınırları için sessiz kabul yapılmaz. Schema/version
kararı değişirse bilinmeyen sürüm fail-closed reddedilir; gelecekteki sürüm
üretim defterine yazılmaz.

## Normatif canonical writer sözleşmesi

1. **Tek entrypoint:** CLI ve panel, task operation'ı aynı canonical core'a
   yönlendirir. Yeni operasyonları uygulayan tek bir writer service/core olur;
   prototype, panel handler, dev/restore kopyası veya outbox worker ikinci bir
   `gorevler.json` mutatörü olamaz. Worker task transition çalıştırmaz; yalnız
   commit edilmiş outbox event'ini teslim/uzlaştırır.
2. **Idempotency key ve digest:** Her mantıksal mutation için istemci bir kez
   kararlı, yeterli entropili `operation_id` üretir ve belirsiz transport
   sonucunda aynı ID + aynı normalize payload ile devam eder. Digest; operation
   türü, task ID ve canonical normalize iş etkisini kapsar. Duplicate JSON
   alanı, type coercion, bool/int eşitliği, alias/default/Unicode
   normalization belirsizliği kabul edilmez. `operation_id`, `kimden` veya
   `--from` kimlik/yetki kanıtı değildir.
3. **Tek task snapshot commit'i:** Canonical `.kilit` altında receipt lookup,
   transition doğrulaması, task alanı ve `gecmis[]` güncellemesi, operation
   receipt'i ve varsa notification outbox kaydı bir `gorevler.json` snapshot'ı
   olarak hazırlanır. Hepsi tek atomik replace + file/directory durability
   sonucuna bağlanır. Receipt/outbox commit edilmeden task değişikliği görünür
   başarı olamaz; commit kesinleşmeden message JSONL append başlamaz.
4. **Duplicate ve conflict:** Aynı `operation_id` + aynı digest önceki
   makbuzu ve task sonucunu verir; ikinci geçiş/history/outbox eklemez. Aynı ID
   farklı digest ise conflict/409 ve byte-for-byte ledger değişmezliği gerekir.
   Receipt alanları operation scope, digest, task ID, result/status,
   transition event ID, notification event ID/state ve creation metadata'sını
   kapsar; notification body/recipient/kind commit anında sabitlenir.
5. **Commit belirsizliği:** `os.replace` sonrasında directory fsync hatası,
   panel child timeout veya response kaybı `commit_unknown`'dır; normal 4xx
   rejection'a çevrilmez. Bildirim dispatch edilmez. Aynı ID ile canonical
   makbuz/readback uzlaştırılır; yeni ID veya kör task retry yoktur. `kaydet()`
   şu anda değişiklik sonrası `VeriHatasi` verebilir; adapter bunu özel ve
   yapılandırılmış bir sonuca çevirmeden prototip retry kuralı uygulanamaz.
6. **Event dedupe ve append:** Outbox `event_id` JSONL `id` ile aynı kararlı
   değerdir. Worker tam dosyada exact ID + exact expected record readback'i
   kullanır; yalnız bounded tail/son 20 mesaj duplicate yokluğu kanıtı değildir.
   Readback, append, fsync ve `delivered` işareti arasında canonical
   `.kilit`/writer serialization korunur. Mevcut `ekle_jsonl()` kendi
   `kilit_tut()` çağrısını yapar; onu zaten aynı lock tutulurken tekrar
   çağırmak deadlock yaratabilir. Entegrasyon ya lock-owned primitive ve ortak
   transaction API sağlar ya da arada yarış yaratmayan ayrı atomik idempotency
   indeksi tasarlar; prototype'ın doğrudan append yordamı kullanılmaz.
7. **Delivery belirsizliği:** Exact event mevcut ve tekilse `delivered` olarak
   uzlaştırılır. Exact ID farklı gövdeyle varsa, ID duplicate ise, tail kısmi/
   bozuksa, readback/append/fsync sonucu belirsizse `delivery_unknown` olur ve
   yeni append durur. Sırf exact ID bulunamadı diye önceki belirsiz append'in
   gerçekleşmediği varsayılmaz. Task receipt `committed` kalabilir; bildirim
   state'i ayrı gösterilir.
8. **Alan sınırı:** Receipt ve outbox alanları bounded sayıda/kayit baytında
   tutulur. Retention, tombstone/expiry, full JSONL readback maliyet üst sınırı,
   malformed tail onarımı ve backup/restore uzlaştırma kararı olmadan worker
   etkinleştirilmez. Outbox/receipt backup'ta task snapshot ile tutarlı olmalı;
   eski backup restore'u event ID veya operation ID'yi unutup tekrar mutasyon/
   append üretmemelidir.
9. **Actor policy ayrıdır:** Authorization, role/scope ve source trust
   mevcut auth/policy katmanında doğrulanır. Idempotency receipt, actor
   iddiasını doğrulamaz veya `operator`/`verified` üretmez. Retry'da principal
   authorization tekrar uygulanır; bir makbuz başka principal'a yetki taşımaz.

## Uygulama sırası ve kapılar

| Aşama | Yapılacak iş | Geçiş kapısı |
|---|---|---|
| 0 — prototip | Mevcut `run_fixture.py` yalnız temp kökte çalışır; schema, duplicate, commit uncertainty, crash sonrası append, bozuk tail ve event conflict dallarını örnekler. | Fixture kanıtı live writer veya gerçek fsync/power-loss kanıtı sayılmaz. Prototip data root'u canonical olarak taşınmaz. |
| 1 — canonical compatibility | Canonical ledger reader/writer için optional root alanı, nested validation, boyut/retention limitleri, unknown field preservation ve eski v1 round-trip testleri eklenir. Restore/backup validator bu alanları validate eder veya açıkça ayrı state olarak raporlar. | Her desteklenen writer exact schema + byte no-write negatiflerini geçer. `yuva-dev`, UI ve restore kopyaları aynı sözleşmeye bağlanmadan ortak root'ta writer olamaz. |
| 2 — mutation receipts | Canonical CLI core ve panel API operation ID/digest'i alır; tüm task handlers aynı locked transaction helper'ına geçer. UI/CLI key'i bir mantıksal işlem başına bir kez üretir, aynı key ile receipt/status sorgular. | Eşzamanlı same-key/same-request bir commit; changed request conflict; response kaybı/CommitUnknown receipt readback ile uzlaşır. Panel 409/unknown/committed ayrımını korur. |
| 3 — notification outbox | Worker task handler dışında pending event tarar. Canonical JSONL writer ile event-ID dedupe, exact-body conflict, append/fsync/readback ve delivery state transaction sınırı tasarlanır. | Crash noktaları, append/fsync belirsizliği, duplicate ID, conflicting body ve bozuk tail için no-duplicate/no-blind-retry fixture'ı geçer. Full-file scan veya idempotency index'in bounded maliyeti kanıtlanır. |
| 4 — rollout | Önce desteklenen tek release/staging data root; backup al, migration önizlemesini salt okunur doğrula, kapalı worker ile schema round-trip ve restore rehearsal yap; sonra kontrollü worker rollout'u. | Yalnız tüm canonical writer'lar pinlenip eski kopyalar kapatıldıktan, operation/outbox backup restore testi geçtikten ve operatör GO verdikten sonra enable. Karışık sürümde rollback ya tam eski schema/data snapshot'a olur ya da read-only NO-GO kalır; outbox alanları eski writer'a emanet edilmez. |

## Kabul fixture matrisi

Canonical entegrasyon şu senaryolarda önce/sonra task, history, receipt,
outbox ve message event'lerini karşılaştırmalı:

- Schema-less legacy v1 additive write; schema v1 unknown nested fields round
  trip; future root version, malformed receipt veya outbox için byte-for-byte
  no-write.
- Same ID/same digest concurrency; same ID/different digest; farklı ID,
  different operation scope; principal/policy mismatch.
- Task validation reject; task snapshot pre-replace error; post-replace
  `commit_unknown`; panel timeout/HTTP response loss ve aynı-ID readback.
- Commit sonrası worker öncesi restart; append öncesi crash; append fsync
  belirsizliği; append sonrası delivered marker crash; restart dedupe.
- Exact event, ID/body conflict, duplicate ID, malformed JSONL tail, full
  readback error, message-store unavailable; her belirsizlikte no blind append.
- Backup restore/rollback sonrası eski makbuz/event tekrarının reddi veya
  uzlaştırılması; receipt/outbox cap ve retention sınırı.

Fixture'lar yalnız disposable `YUVA_DIR` kullanmalı. Production data root,
çalışan service, gerçek kullanıcı bildirimi veya auth state test hedefi değildir.

## Mevcut kanıt ve sınır

`docs/task-outbox-ledger-v1-fixture-612.md` ile
`prototypes/task-outbox/run_fixture.py` v1 task root şekli, additive fixture
alanları, duplicate op, `CommitUnknown`, append crash/readback ve bozuk JSONL
senaryolarını belgeliyor. Bu fixture kendi JSON append/lock yolunu uygular;
canonical `bin/yuva` kodunu import etmez. Canonical çağrı grafiği #611'deki
desteklenen panel/current CLI yolu ile sınırlıdır. #627/#622 kapsamı da eski,
dev veya restore kopyalarının bütün koşullarda canonical-writer uyumlu olduğunu
kanıtlamaz.

Bu nedenle bugün **outbox production rollout'u NO-GO**: canonical CLI'da
operation receipt lookup, task/outbox birlikte commit, idempotent message
append ve outbox worker yoktur. Bu sözleşme mevcut görev bildirimi akışını
değiştirmez ve fixture başarıları canlı idempotency garantisi değildir.

## Dayanaklar

- `docs/task-notification-idempotency-575.md` — normatif operation, commit,
  response, retry ve notification idempotency davranışı.
- `docs/task-mutation-idempotency-outbox-design-437.md` — başlangıç veri modeli
  ve fault matrisi.
- `docs/task-outbox-ledger-v1-fixture-612.md` ile
  `prototypes/task-outbox/` — izole fixture kapsamı ve sınırları.
- `docs/task-writer-call-graph-611.md`, `docs/task-ledger-single-writer-552.md`
  — canonical CLI/panel çağrı grafiği ve legacy writer kapsam sınırları.
- `docs/legacy-copy-writer-compatibility-gate-622.md`,
  `docs/task-writer-local-copy-inventory-627.md` — CLI kopyalarının
  canonical writer/schema uyum kapıları.
- `bin/yuva` — `gorev_guncelle()`, `cmd_gorev_*`, `kaydet()`, `kilit_tut()` ve
  `ekle_jsonl()`; `panel/server.py` — task API'nin canonical core dispatch'i.
