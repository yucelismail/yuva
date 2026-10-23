# `yuva wait` yinelenmez gözlem makbuzu fixture'ı (#623)

**Tarih:** 2026-10-23
**Durum:** CLI + temp inbox + fixture receipt-store kabul testi tamamlandı.
**Sınır:** İki CLI subprocess'i ve receipt store aynı test `TemporaryDirectory`'si içinde sentetik state ile çalıştı. Canlı inbox, provider, panel veya gerçek task defteri kullanılmadı.

## Senaryo

1. `yuva wait --from worker-1 --after cursor --timeout 0`, geçici `mesaj.jsonl` içinden tek direct-target mesajı projection olarak döndürür.
2. Test bu untrusted/data-only envelope'ı `FixtureReceiptStore.observe()` ile ilk kez kaydeder. Receipt `read_observed` içerir ama gövde metni içermez.
3. CLI çağrısı aynı eski `--after cursor` ile tekrar edilir. Wait komutu consumer cursor'ını kalıcılaştırmadığından aynı message ID yeniden gözlenir; aynı consumer için store bunu `duplicate_observation` olarak sınıflandırır ve receipt dosyasına ikinci satır eklemez.
4. Caller store cursor'ını da kaybetmiş gibi `expected_cursor=None` verirse store `cursor_unavailable` döndürür; receipt ledger ilerlemez.

Fixture receipt store, #587'nin işaretli temp-only şartını kullanır. Bu birleşim CLI'ın store'a kendiliğinden yazdığı anlamına gelmez; test iki parçanın ayrı sözleşmelerini aynı temporary root üzerinde birleştirir. Tüketici CLI `next_cursor` ile receipt commit'ini kendi yaşam döngüsünde yönetmek zorundadır.

## Kanıt ve sınırlar

`tests/test_yuva_wait_cli_fixture.py::test_cli_replay_produces_one_text_free_duplicate_suppressed_receipt` inbox, durum ve görev dosyalarının ilk/tekrar okuma öncesi-sonrası byte'larını karşılaştırır; receipt gövdesinde mesaj metninin bulunmadığını ve dosyada tek event kaldığını sınar. Çıkışta **5 hedefli CLI fixture testi geçti**.

`read_observed` yalnız fixture store'un typed data-only envelope için bir gözlem satırı commit ettiğini anlatır. Agent'ın mesajı gerçekten gördüğünü, okuduğunu, anladığını veya uyguladığını; provider'a teslimi ya da task completion'ı kanıtlamaz. Store kaybı/anti-rollback, CLI tarafından receipt persist etme, atomic wait+receipt transaction'ı ve producer ack bu görevin kapsamı dışındadır.

İlgili sözleşmeler: [#614 CLI wait adapter](yuva-wait-cli-fixture-614.md), [#587 fixture receipt store](yuva-wait-persistent-receipt-587.md), [#603 wait/receipt birleşik fixture'ı](yuva-wait-end-to-end-fixture-603.md).
