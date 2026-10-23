# #657 — Canonical task writer ve additive outbox v1 alanları

**Durum:** Disposable fixture eklendi; mevcut kanonik CLI davranışına karşı
hedefli testler çalıştırıldı. Receipt/outbox production entegrasyonu yok.
**Tarih:** 2026-10-23

## Fixture kapsamı

`tests/test_task_outbox_canonical_writer_compat_fixture.py` doğrudan mevcut
`bin/yuva` modülünü geçici, private `YUVA_DIR` ile yükler. Gerçek `/home/.../yuva`
ve panel/runtime kullanılmaz. Sentetik root `schema_version` alanı v1 iken veya
legacy biçimde alan yokken `operations`, `outbox` ve başka unknown additive
root alanlarını canonical `gorev_yukle()`/`gorev_guncelle()` turundan geçirir.

Fixture ayrıca şunları sınar:

- Normal task mutation'ı sırasında additive alanlar değer olarak korunur ve
  legacy, schema-less ledger başarılı save'de v1 olarak yazılır.
- Callback ve canonical `kaydet()` çalışırken ikinci file descriptor üzerinden
  `.kilit` alamamak, mutation ve save boyunca ortak lock tutulduğunu gösterir.
- Başarılı save dosya inode'unu değiştirir, tek bütün JSON snapshot'ı okunur ve
  geçici `.tmp` artığı kalmaz.
- Future `schema_version=99` callback'ten önce reddedilir ve ledger bytes
  değişmeden kalır. `os.replace` öncesi enjekte edilen hata da eski bytes'ı ve
  outbox içeriğini korur.

Çalıştırma:

```sh
python3 -m unittest tests.test_task_outbox_canonical_writer_compat_fixture -v
```

## Sonuç ve sınır

Hedefli fixture **4 test geçti**. Bu yalnız mevcut `bin/yuva` canonical writer
ve disposable fixture için gözlenen additive-field pass-through ile
`gorev_guncelle()` içindeki lock/save çağrı sırasını gösterir.

Canonical reader/writer `operations` ve `outbox` nested shape, byte/item cap,
retention veya delivery state anlamını doğrulamaz; alanları mutasyon sırasında
opak olarak koruması onların desteklenmiş outbox API'si olduğunu göstermez.
Fixture task receipt ile outbox event'ini canonical mutation'la atomik
oluşturmaz, gerçek directory-fsync/power-loss garantisi vermez, ayrı process
release kopyalarını sınamaz ve worker/message dispatch'i çalıştırmaz. Bu
nedenle production outbox worker/receipt entegrasyonu, live ledger değişikliği
ve rollout için kabul kanıtı değildir.

## Dayanak

- `docs/task-outbox-canonical-writer-transition-644.md` — additive round-trip,
  tek writer ve üretim entegrasyonu için aşamalı kapılar.
- `docs/task-outbox-ledger-v1-fixture-612.md` — mevcut izole outbox
  prototipinin canonical CLI'dan ayrı olduğu sınır.
- `docs/task-writer-call-graph-611.md` — `gorev_guncelle()` → `.kilit` →
  `gorev_yukle()` → callback → `kaydet()` akışı.
- `tests/test_task_ledger_integrity.py` — canonical save/ledger için var olan
  temp-root fault ve concurrency fixture kalıpları.
