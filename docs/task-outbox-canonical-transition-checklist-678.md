# Yuva #678 — Task outbox canonical writer geçiş checklist'i

**Karar:** Geçiş sırası önce schema/writer uyumluluğu, sonra task receipt
transaction'ı, en son notification worker ve restore/rollout kabulüdür. Herhangi
bir kapı başarısız veya `UNKNOWN` ise outbox worker kapalı, rollout **HOLD / NO-GO**
kalır. Mevcut fixture'lar üretim kabulü değildir.

**Kanıt durumu (2026-10-23):** #644, #657, #661 ve #662 tahtada onaylıdır.
Bu, ilgili tasarım ve disposable fixture görevlerinin kabulidir; canonical
receipt/outbox entegrasyonu veya canlı rollout'un kabul edildiği anlamına
gelmez.

## Mevcut kanıtların kapsamı

| Kaynak | Kanıtladığı | Kanıtlamadığı |
|---|---|---|
| [#644 geçiş sözleşmesi](task-outbox-canonical-writer-transition-644.md) | Aşamalı uygulama sırası; canonical CLI/panel tek writer hedefi; receipt, commit-unknown, event readback, actor policy, retention ve rollback gereksinimleri | Kod entegrasyonu veya runtime davranışı |
| [#657 canonical writer fixture'ı](task-outbox-canonical-writer-compat-657.md) | Geçici `YUVA_DIR`'de mevcut `bin/yuva` v1/schema-less task mutation'ı `operations`, `outbox` ve unknown root alanlarını opak koruyor; future root schema ve replace-öncesi hata no-write | Nested şema doğrulaması, outbox desteği, receipt üretimi, tüm CLI kopyaları, worker veya gerçek fsync/power-loss |
| [#661 nested schema fixture'ı](task-outbox-nested-schema-661.md) | Ayrı prototipte strict receipt/event alanları, ilişki kontrolleri, duplicate/type/byte/count sınırları; nested unknown reject ve root unknown preserve | Canonical reader/writer'ın validator'ı çağırması; fixture'daki 256/4096/128/2048 limitlerinin production için onaylanması; retention/backup uyumu |
| [#662 exact-ID append fixture'ı](task-outbox-exact-id-append-fixture-662.md) | Ayrı prototip JSONL'de exact event/body readback, crash sonrası dedupe, conflict/duplicate/corrupt-tail ve uncertain absence durumunda no-blind-retry | Canonical `ekle_jsonl()` davranışı, production lock integration, durable fsync veya gerçek filesystem arıza garantisi |
| [#611 writer çağrı grafiği](task-writer-call-graph-611.md) | Desteklenen repo panel/CLI task mutation'larının `bin/yuva` core ve ortak `.kilit` yoluna gittiği | Dev/UI/restore/aynı UID keyfi writer'larının aynı sözleşmeye uyduğu; evrensel writer tekilliği |

## A. Tasarım ve schema kapısı — production kodundan önce

- [ ] **Sahip/format kararı:** Receipt/outbox'un kanonik sahibi ve schema yeri
  seçildi (`gorevler.json` v1 additive alanı, ayrı transactional store veya
  başka açıkça sürümlü seçenek). Backup, restore, doctor, rollback ve eski
  reader/writer etkisi kaynak-kabul tablosuna bağlandı.
- [ ] **Alan sözleşmesi:** Required key/type/enum, canonical operation scope,
  task/result shape, `operation_id`, digest, transition event ID, notification
  event ID ve tam sabitlenmiş event body belirlendi. Duplicate JSON object key,
  bool/int coercion, Unicode/alias/default normalizasyonu fail-closed tanımlı.
- [ ] **Boyut ve retention:** Maksimum receipt/outbox adedi, canonical entry
  byte cap, message byte cap, retention/tombstone ömrü ve maksimum client retry
  penceresi operatörce onaylandı. Limit aşımı mutation'dan önce reddediliyor;
  otomatik eviction yok. #661'in fixture limitleri tasarım adayıdır, kabul
  edilmiş production değerleri değildir.
- [ ] **Unknown-field kuralı:** Root additive field preservation ile nested
  schema davranışı ayrıldı. Bilinmeyen future schema veya unsupported nested
  receipt/event'te eski writer byte-for-byte no-write yapıyor ya da açıkça
  read-only/HOLD oluyor.
- [ ] **Digest/actor ayrımı:** `operation_id` idempotency anahtarıdır, yetki
  değildir. Retry'da principal/scope authorization tekrar uygulanır; actor
  policy ve idempotency key namespace'i ayrı tanımlı.

**Kapı A kanıtı:** Schema örnekleri, pozitif/negatif canonical JSON fixtures,
count/byte bound testleri, duplicate-key testleri, eski v1 round-trip ve her
reddedilen şekil için byte-for-byte no-write sonucu. `UNKNOWN` schema/migration
durumunda hiçbir writer upgrade, drop veya rewrite yapmaz.

## B. Canonical compatibility ve tek writer kapısı

- [ ] **Canonical task core:** CLI ve panel bütün task mutation'larını aynı
  locked transaction helper'ına dispatch eder. Task state/history, receipt ve
  outbox tek canonical snapshot mutator'ı dışında değiştirilemez.
- [ ] **Kilit sözleşmesi:** Receipt lookup → transition check → snapshot
  hazırlama → atomic replace/file+directory durability aynı `YUVA_DIR/.kilit`
  kapsamındadır. `sonraki` dahil her task handler aynı path/inode/protokolü
  kullanır. Worker'ın readback+append koordinasyonu için reentrant olmayan
  nested lock deadlock'u yaratılmaz; lock-owned primitive veya aynı kilidi
  koruyan API kullanılır.
- [ ] **Kopya kapsamı:** Desteklenmeyen `yuva-dev`, UI, restore-check ve diğer
  CLI/panel writer'ları ortak data root'a erişemiyor veya exact schema/cap,
  lock, unknown-schema no-write ve rollback sözleşmesini geçen sürümle
  pinlenmiş. Yalnız #657 canonical repo CLI kanıtı bu kutuyu geçirmez.
- [ ] **Hata sınıfları:** Replace öncesi hata, post-replace directory-fsync
  `commit_unknown`, panel timeout ve response loss birbirinden ayrılıyor.
  `commit_unknown` 4xx rejection'a dönüştürülmüyor; worker kesin receipt
  commit'inden önce bildirim göndermiyor.
- [ ] **Bağımsız authorization:** Worker veya receipt rol/assignee denetimini
  atlamıyor. `--from`/`kimden` assertion'ı principal sayılmıyor; her retry
  mevcut policy katmanında yeniden yetkilendiriliyor.

**Kapı B kanıtı:** Her desteklenen writer/copy için exact supported schema
matrix'i; auth-on/off actor ve policy testleri; concurrent same-key testleri;
lock busy/timeout, invalid lock inode ve replace-before/after hata sonuçları.
Untested writer varsa ortak root rollout'u **NO-GO**.

## C. Idempotent task mutation kapısı

- [ ] UI/CLI her mantıksal işlem için bir kez kararlı yüksek-entropi
  `operation_id` üretir; request loss/retry aynı ID ve aynı normalize digest'i
  kullanır.
- [ ] Aynı ID + aynı digest önceki receipt/result'ı döndürür; task state ve
  history ikinci kez değişmez, ikinci event yaratılmaz.
- [ ] Aynı ID + farklı digest `409 idempotency_conflict` verir ve ledger
  bytes/state/history/receipt/outbox byte-for-byte değişmeden kalır.
- [ ] Eşzamanlı duplicate işlemlerde yalnız bir transition, history event,
  receipt ve notification outbox event'i commit edilir.
- [ ] Validation reject, pre-replace hata, post-replace `commit_unknown`,
  timeout ve response-loss durumları aynı ID ile status/readback'e bağlanır.
  Receipt görünmesi durability tamamlandı anlamına gelmiyorsa recovery bunu
  yeniden fsync veya operatör kararıyla netleştirir.
- [ ] Task commit cevabı notification delivery'den ayrıdır: `committed` task
  state'i, `pending/delivered/delivery_unknown` notification sonucu API'de ayrı
  temsil edilir.

**Kapı C kanıtı:** Önce/sonra task, history, receipt, outbox ve JSONL diff'i;
multi-process concurrency; duplicate changed-payload conflict; API response
loss ve receipt lookup. Hiçbir retry yeni operation ID ile kör yürütülmez.

## D. Notification outbox worker kapısı

- [ ] Worker task transition çalıştırmaz; yalnız `committed` outbox event'ini
  teslim/uzlaştırır. Event ID, JSONL `id` ile aynıdır; body/kind/recipient
  transaction anında sabitlenmiştir.
- [ ] Duplicate lookup bounded UI tail değil, tam güvenilir dedupe kaynağı veya
  ayrıca kabul edilmiş bounded index kullanır. Aynı exact ID + exact expected
  body bir kez varsa `delivered_readback`; exact ID farklı body veya birden çok
  satırsa `delivery_unknown`.
- [ ] Append fdatasync/fsync ve, yeni file creation'da, parent directory
  durability davranışı belirlenmiştir. Writer lock readback → append → state
  marker aralığında korunur.
- [ ] Append öncesi crash, append sonrası marker öncesi crash, append/fsync
  belirsizliği, readback error, event bulunamaması, duplicate ID, body conflict
  ve malformed/incomplete tail senaryoları geçer.
- [ ] Daha önceki `delivery_unknown` kaydı için event bulunmaması yeni append
  izni değildir. Belirsiz event no-blind-retry kalır; recovery prosedürü ve
  operatör onayı tanımlıdır.

**Kapı D kanıtı:** #662 fixture dallarının canonical `ekle_jsonl`/lock/receipt
yoluna taşınmış kabul testleri; tekrar başlatma sonrası event sayısı ve exact
body; append/readback belirsizliğinde byte değişmezliği/no-retry. #662'nin
özel append/lock uygulaması canonical writer yerine kullanılamaz.

## E. Backup, restore, rollback ve rollout kapısı

- [ ] Backup/restore task state, history, receipts ve outbox'ı aynı generation
  ve tutarlı snapshot olarak içerir; eski backup restore'u daha önce kullanılmış
  operation/event ID'lerini kaybettirip duplicate üretmez.
- [ ] Restore validator schema, nested shape, count/byte caps ve unknown
  version'ı doğrular veya açık UNKNOWN/HOLD döndürür; bozuk/unknown alanı
  otomatik silmez.
- [ ] Eski writer'a rollback, yeni receipt/outbox alanlarını koruyacağı
  kanıtlanmadıkça yapılmaz. Güvenli rollback veri snapshot'ı ve code release'i
  birlikte ele alır; pointer-only downgrade **NO-GO** olabilir.
- [ ] Staging'de kapalı worker ile schema round-trip, backup→restore, rollback
  rehearsal, operation/event dedupe ve retention-cap testleri geçer.
- [ ] Bütün writer binary/source pin'leri, rollout/rollback owner'ı, backup
  sahibi ve operator GO imzası kayıtlıdır. Worker ancak tüm önceki kapılar ve
  restore rehearsal kabul edildikten sonra enable edilir.

**Kapı E kanıtı:** Disposable release/data roots, içerik/hash önce-sonra
karşılaştırması, exact rollback target, receipt/event replay denemeleri ve
imzalı operator kararı. Live `YUVA_DIR` üzerinde fixture çalıştırılmaz.

## Geçiş kararı

| Durum | Karar |
|---|---|
| Yalnız #657 additive alan pass-through doğrulanmış | **Schema uyum adayı**; nested support değil |
| #661 nested limits ve #662 exact-ID fixture'ları geçiyor ama canonical CLI/panel entegrasyonu yok | **Prototype PASS / production NO-GO** |
| Her canonical writer ve desteklenen copy A–E kapılarını geçti, backup/restore ve operator acceptance var | **GO adayı**; release owner onayı gerekir |
| Writer kopyası, receipt durability, retention, full-readback maliyeti veya restore sonucu UNKNOWN | **HOLD / NO-GO**; worker kapalı, live mutation/outbox enable yok |

Checklist bir uygulama planı veya production guarantee değildir. #644'ün
NO-GO'sunu değiştirmez; yalnız sonraki mühendislik ve release kabul sırasını
operasyonel olarak gözden geçirilebilir hale getirir.

## Kaynaklar

- [#644 canonical geçiş sözleşmesi](task-outbox-canonical-writer-transition-644.md)
- [#657 canonical writer uyumluluk fixture'ı](task-outbox-canonical-writer-compat-657.md)
- [#661 nested schema ve boyut fixture'ı](task-outbox-nested-schema-661.md)
- [#662 exact-ID JSONL uzlaştırma fixture'ı](task-outbox-exact-id-append-fixture-662.md)
- [#612 isolated ledger fixture](task-outbox-ledger-v1-fixture-612.md)
- [#575 task notification idempotency sözleşmesi](task-notification-idempotency-575.md)
- [#611 task writer çağrı grafiği](task-writer-call-graph-611.md)
