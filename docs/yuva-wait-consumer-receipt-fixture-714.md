# Yuva wait consumer receipt fixture (#714)

**Tarih:** 2026-10-23
**Durum:** #688 sözleşmesinin disposable fixture prototipi. Production entegrasyon yok.

## Uygulama

`prototypes/yuva-wait/receipt_store.py`, yalnız işaretli ve private bir
`TemporaryDirectory` altında çalışır. Tüm consumer'lar aynı bounded JSONL
dosyasını kullanır; kayıtlar global `sequence` ile sıralanır, her consumer'ın
cursor/epoch zinciri store içinden yeniden kurulur.

Consumer ilk kullanımda `bootstrap_consumer(consumer_id, consumer_epoch,
initial_cursor, approved=True)` çağrısıyla açık başlangıç sınırı verir.
`approved` olmadan ya da `observe(... expected_cursor=None, ...)` ile implicit
bootstrap yapılmaz. Her gözlemde epoch ve cursor CAS edilir. Önceden mevcut
consumer/message receipt'i ancak consumer epoch'u ve receipt'in
`previous_cursor` alanı gelen çağrıyla uyuşuyorsa `duplicate_observation`
döner ve yeniden append yapılmaz. Aynı ID için başka cursor/epoch
`store_conflict`; yeni ID için stale/yanlış cursor `cursor_conflict` olur.

Receipt yalnız `read_observed`, ID'ler, cursor çifti, unverified trust/class
alanları, `data_only`, zaman damgası ve sequence tutar. Serbest envelope ve
message body depolanmaz. Parser duplicate JSON anahtarı, sıra/zincir ihlali,
partial tail, fazla boyut ve dosya mode/owner/link hatalarında store'u
`store_corrupt` olarak kapatır; içeriği onarmaz veya truncate etmez.

Append öncesi hatalar `store_unavailable`/`store_full` döner. Append başladıktan
sonra write/fsync sonucu belirsizse `commit_unknown` döner. Otomatik retry yok;
çağıran process yeniden açıldığında store içindeki tam receipt'i okuyarak
dedupe sınıflaması yapabilir. Fixture, başarılı `fsync`'in makine çökmesi,
disk/FS garantileri veya consumer'ın kullanıcıya gösterme anıyla atomikliği
kanıtladığını iddia etmez.

## Doğrulama

`tests/test_yuva_wait_receipt_store.py` explicit bootstrap, `None` ile
no-write, epoch/CAS conflict, restart replay, iki consumer izolasyonu, corrupt
tail ve sentetik fsync failure sonrası `commit_unknown`/reconciliation
senaryolarını kapsar. CLI ve end-to-end fixture testleri de explicit bootstrap
API'sine geçirilmiştir. Hedefli komut:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_yuva_wait_receipt_store \
  tests.test_yuva_wait_cli_fixture \
  tests.test_yuva_wait_end_to_end_fixture -v
```

Restore/anti-rollback için dış anchor yoktur; store ve consumer state birlikte
eski snapshot'a dönerse bu fixture rollback'i saptayamaz. Yeni epoch/reset
yalnız explicit fixture bootstrap kararıyla açılabilir; otomatik devam, task
mutation, producer ack, provider dispatch, live `YUVA_DIR` veya agent bağlantısı
yoktur. #688'deki tüm restore, OS custody ve production durability garantileri
bu prototipin dışında kalır.
