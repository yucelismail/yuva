# Backup verifier için expected SHA-256 CLI sözleşmesi (#616)

**Tarih:** 2026-10-23
**Durum:** CLI ve TemporaryDirectory fixture prototipi tamamlandı.
**Güven sınırı:** Araç digest'in nereden geldiğini doğrulamaz; operatörün bağımsız pin olarak verdiği değerle arşiv byte'larının eşleşmesini sınar.

## Kullanım

`verify` ve `restore-check` komutları isteğe bağlı aynı biçimi kabul eder:

```sh
python3 backup_verify.py verify --archive /backup/yuva.tar \
  --expected-sha256 <independent-64-lowercase-hex-digest>

python3 backup_verify.py restore-check --archive /backup/yuva.tar \
  --scratch-root /private/scratch --destination-name restore-01 \
  --expected-sha256 <independent-64-lowercase-hex-digest>
```

Değer tam 64 küçük harfli hex karakter olmalıdır. Boşluk, newline, uppercase, prefix (`sha256:`) veya kısmi digest reddedilir. Argüman verilmezse mevcut davranış korunur.

## Doğrulama anlamı

- Verifier arşivin gerçek SHA-256 digest'ini hesaplar; optional `expected_sha256.matches_archive` bunu caller input'u ile karşılaştırır.
- Pin uyuşmazlığı `verify` sonucunda `ok: false` üretir ve CLI exit code `1` döner. Adjacent `.sha256` dosyası da arşivle eşleşse bile birlikte değiştirilmiş arşivi/pair'i bu pin yakalar.
- Digest biçimi geçersizse doğrulama girdisi reddedilir ve CLI exit code `2` döner.
- `restore-check` pin uyuşmazlığında scratch hedef dizinini oluşturmadan durur. Restore-check refusal/malformed input exit code `2` olarak kalır.
- Mevcut adjacent `.sha256` sidecar zorunlu kalır ve onun yerel tutarlılık karşılaştırması ayrıca yapılır. Sidecar uyuşmazlığı expected pin'in varlığıyla geçersiz sayılmaz.
- Raporun `authenticity` değeri değişmeden `unverified` kalır. `expected_sha256.provenance` yalnız `caller_supplied_unverified` der; araç pinin başka ortamda, ayrı kanalda veya bağımsız operatörce üretildiğini kanıtlayamaz. Eşleşme kaynak doğruluğu, tar içeriğinin güvenliği veya restore kararının doğruluğu değildir.

Digest sır değildir; CLI argümanı process listelerinde görünebilir. Hassas credential değeri bu seçenekten taşınmamalıdır.

## Fixture kanıtı

`tests/test_backup_verify.py` sentetik temp arşivinde şunları sınar:

1. Doğru pin raporda eşleşir; `authenticity` yine `unverified` kalır.
2. Arşiv ve yanındaki `.sha256` beraber yeniden yazıldığında eski bağımsız expected digest uyuşmaz ve `ok` false olur.
3. Non-canonical digest biçimleri reddedilir.
4. Restore-check yanlış pin ile yeni scratch destination yaratmaz.
5. CLI `verify --expected-sha256` argümanı rapora eşleşme sonucunu taşır.

Çalıştırma: `python3 -m unittest tests.test_backup_verify -v`.

İlgili karar: [#565 bağımsız trust anchor değerlendirmesi](backup-authenticity-trust-anchor-565.md). Bu prototip sadece bağımsız olarak saklanmış digest değerini girdi kabul eder; pin custody, üretim zamanı, aktarım kanalı, rotation ve kayıp kurtarma sürecini sağlamaz.
