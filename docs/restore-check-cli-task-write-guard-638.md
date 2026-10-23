# Restore-check scratch CLI görev yazımını kapatma (#638)

**Karar:** #638'in kabul edilen kapsamı yeni scratch restore-check çıktısındaki CLI stub'ıdır. Scratch ağacındaki `bin/yuva` hiçbir komutu çalıştırmaz; sabit bir `exit 2` stub'ı ile değiştirilir. Operatör tarihsel iki kopyayı dokunulmaz tutmayı seçti; bunlar güvenli kabul edilmez ve kullanım/containment riski #659'da izlenir.

**Revize kapsamı:** Scratch koruması yeni restore-check çıktısına uygulanır. Path-aware guard'ın iki tarihsel CLI kopyasındaki uygulanabilirliği yalnız TemporaryDirectory mirror fixture'larında gösterilmiştir; bu fixture gerçek kopyaları değiştirmez. Gerçek kopyalar halen görev yazabilir. Uygulama sınırı, geri alınan deneme ve kalan risk [#638 revize notunda](restore-check-cli-guard-revision-638.md) açıklanır.

## Bulgu ve kapsam

#596/#627 envanterindeki iki tarihsel restore-check CLI kopyası aynı fail-open davranışı taşıyor: task ledger okunurken bozuk JSON varsayılan boş ledger'a dönüşebiliyor ve `gorev ekle` bunu yazabiliyor. Bu kopyalar `<YUVA_DATA_ROOT>-yedek/restore-check.T4hbP8/yuva/bin/yuva` ve `restore-check.XOeUcj/yuva/bin/yuva` yollarında arşiv/inceleme girdisidir. Bu görev onları doğrudan çalıştırmaz veya değiştirmez.

`backup_verify.restore_check()` tar arşivini verify edip yalnız kullanıcı tarafından verilen yeni scratch hedefe çıkarır. Şema kontrolünden önce, çıkarılmış scratch ağacında `yuva/bin/yuva` varsa regular-file/no-follow/inode kontrolleriyle sabit bir stub'a dönüştürür. Stub tüm çağrıları sabit tanı ile `2` kodunda reddeder; bu kopya artık deploy edilebilir/çalıştırılabilir restore kabulü değildir. Sonuç nesnesi `restore_cli_policy` alanında `task_mutations_disabled` veya CLI yoksa `not_present` bildirir. Path-aware guard önerisi iki tarihsel CLI kopyasında henüz uygulanmamıştır.

Tarihsel ağaçlar, backup tarı, tar sidecar'ları ve canlı ledger bu revizyon aşamasında değiştirilmedi. İki gerçek CLI dosyası son salt-okunur kontrolde özgün SHA-256 `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` ve `0775` modundaydı. Hazırlık/geri alma manifesti `/tmp/yuva-638-rollback-avyvyljx/manifest.json` konumundadır; daha sonraki açık uygulama kararı için tekrar doğrulanmalıdır.

## Fixture kanıtı

`tests/test_restore_check_cli_write_guard.py` iki tarihsel CLI kaynağını yalnız okur, kaynak byte hash'lerini başta/sonda karşılaştırır ve her birini yeni sentetik tar fixture'ına yazar. Tar, sidecar, `YUVA_DIR` ve scratch çıktısı `TemporaryDirectory` altındadır.

| Restore-check ledger fixture'ı | Restore-check sonucu | Scratch CLI denemesi | Task ledger byte'ı |
|---|---|---|---|
| Bozuk JSON | Şema doğrulaması reddeder; yarım scratch inceleme klasörü kalabilir | Sabit stub `2` döndürür | Değişmez |
| Schema v1, geçerli biçim | Restore-check geçer; `restore_cli_policy=task_mutations_disabled` | `gorev ekle` sabit stub ile reddedilir | Değişmez |
| Bilinmeyen schema 99 | Şema doğrulaması reddeder; scratch klasörü kalabilir | Sabit stub `2` döndürür | Değişmez |

Kanonik `yuva-v2/bin/yuva` ayrı geçici kopya ve ayrı sentetik `YUVA_DIR` altında sınandı: geçerli v1 task yazımı kabul edilip `schema_version: 1` korunur; bozuk JSON ve schema 99 reddedilir, ledger byte'ları değişmez. Bu canonical writer davranışı restore-check stub'ından bağımsızdır.

Çalıştırılan odaklı test: `python3 -m unittest tests.test_restore_check_cli_write_guard -v` — 3 test geçti; bunlar geçici mirror ve canonical writer fixture'larını kapsar. Gerçek iki tarihsel CLI path'ine karşı sonradan yapılan testler önceki teslimdeki geçici değişiklikler altındaydı; baş denetçi bu iki dosyayı özgün hâline geri aldı. Şu anki gerçek path'ler görev yazımını engellediği kanıtlanmış değildir. Gerçek backup/sidecar ve canlı ledger değiştirilmedi.

## Sınırlar

- `backup_verify.py` içindeki fail-closed değişiklik yeni restore-check scratch output'unu güvenli kılar; iki tarihsel kopya halen yazabilir ve #659'da ayrı ele alınır.
- Restore-check hedefi çalışan release değildir. Stub nedeniyle içindeki eski CLI komutları, `--help` dahil, kullanılamaz; ihtiyaç duyulan salt-okunur veri incelemesi restore-check raporu ve dosya içeriği üzerinden yapılır.
- Bu fixture task writer uyumluluğu, release authenticity, canlı servis, runtime seçimi, task ledger restore izni veya backup provenance kanıtı değildir.
- Canonical v2 test sonucu yalnız bu testin kullandığı kaynak kopyasını ve temporary data root'u kapsar; host'taki tüm CLI kopyalarının tek writer olduğu anlamına gelmez.

## Kaynaklar

- [#544 backup verifier ve restore-check](backup-verify-restore-check-544.md)
- [#627 yerel görev yazıcı kopyaları envanteri](task-writer-local-copy-inventory-627.md)
- [#596 CLI schema/writer fixture bulgusu](cli-copy-schema-writer-compatibility-596.md)
- `backup_verify.py`, `tests/test_restore_check_cli_write_guard.py`
