# Installer rollback actual data contract kapısı (#645)

**Durum:** Geçici install/data-root fixture'larında sınanmış dar rollback gate prototipi. Canlı rollback, release pointer, servis veya gerçek `YUVA_DIR` değiştirilmedi. Bu gate tek başına host/release GO kararı değildir.

## Gate davranışı

`release_installer.rollback_release()` pointer güncellemesinden önce, install lock altında sırasıyla:

1. Current pointer'ın saklı manifestini canonical JSON ve release ID bağıyla okur; current payload'ın manifestteki dosya kayıtlarıyla eşleştiğini doğrular.
2. Hedef release'in source/payload ve caller-supplied trusted manifest pin doğrulamasını mevcut `_verify()` yoluyla sürdürür.
3. Current ve target manifestlerinin `data_contract.schema_compatibility` değerlerini şekil/ID doğrulamasından geçirir. İkisi de bilinen `yuva-data-contract/v1` olmalı ve birebir eşit kalmalıdır. Eksik, bozuk, bilinmeyen veya farklı contract red edilir.
4. Çağıranın verdiği ayrılmış `data_root` (`YUVA_DIR`) üzerinde read-only, bounded schema kabulü yapar.
5. Yalnız bütün kapılar geçince `previous` ve ardından `current` pointer'larını değiştirir.

Gate'in hata yolları pointer yazımından önce döner; actual data root'a hiçbir yazım yapılmaz. Sonuç makbuzuna kişisel/içerik verisi yerine kabul edilen contract ID'si ve sınıf özeti eklenir.

## Desteklenen actual data sınıfları

Sınıflar [#549 schema sözleşmesi](data-schema-compatibility-549.md) ve [#632 rollback matrisi](release-data-schema-rollback-matrix-632.md) için sınırlı bir installer preflight'idir; migration veya writer compatibility kanıtı değildir.

| Kaynak | Gate'in kabul ettiği biçim | Read limit / fail-closed koşulu |
|---|---|---|
| `durum.json` | Zorunlu JSON object; `schema_version` yoksa `legacy`, exact integer `1` ise `v1`; `kullanicilar` map, map değerleri object, `rev` non-negative integer | 4 MiB; duplicate JSON key, bozuk UTF-8/JSON, symlink/non-regular, unknown/bool schema veya geçersiz kök şekli red |
| `gorevler.json` | Zorunlu JSON object; sürümsüz `legacy` veya exact integer v1; next ID ve task list şekli geçerli; unique positive IDs, tanınan status ve geçerli history/parent türü | 16 MiB; duplicate key, bozuk JSON, unsupported schema/status, eksik task alanı veya bozuk root red |
| `mesaj.jsonl` | İsteğe bağlı; her satır JSON object. Satır version alanı yoksa legacy/v1; explicit exact integer v1 veya v2 kabul | 64 MiB toplam, satır başına 2 MiB; boş satır, malformed object/JSON, bool/unknown version red |
| `ekran/**/*.jsonl` | İsteğe bağlı; satır satır JSON object ve sürümsüz screen şekli | Dosya başına 16 MiB, toplam 64 MiB, kayıt başına 2 MiB; symlink/non-regular, malformed kayıt veya explicit `schema_version` red |

Parser duplicate JSON object key'lerini ve JSON `NaN`/`Infinity` değerlerini reddeder. Dosyalar `O_NOFOLLOW` ile, inode ve okuma sırasında boyut/zaman metadata'sı karşılaştırılarak okunur. Bütün okuma yolları üst limitlidir. Çıktıdaki `data_schema` yalnız `legacy`, `v1`, `legacy/v1/v2`, `unversioned-json-object`, `absent` gibi sınıf enum'ları taşır; kayıt içeriği ve kimlikleri dışarı sızmaz.

Legacy root sözleşmesi desteklenen biçimlerin aynısıdır ancak yalnız `schema_version` alanı eksiktir; alanın var olup bool/0/unknown değer taşıması legacy fallback değildir. Root dosyasının eksik veya zorunlu şeklinin bulunmaması bilinmeyen data kabul edilir ve pointer'ı tutar.

## Fixture matrisi ve sonuç

`tests/test_release_installer.py` install root, release'ler, manifestler, source worktree ve actual data root'unu `TemporaryDirectory` altında üretir. Testler canlı kurulum veya rollback komutu çalıştırmaz.

| Fixture durumu | Beklenen sonuç | Pointer/data kanıtı |
|---|---|---|
| Current/target ikisi de exact v1 contract, actual state/task v1 | Rollback tamamlanır | `current` hedef olur; data root digest'i değişmez |
| Sürümsüz legacy state/task + legacy/v1/v2 mesaj + sürümsüz screen JSONL | Rollback tamamlanır ve sınıflar raporlanır | Data root byte/digest değişmez |
| Current contract unknown veya target contract unknown/farklı | Red | Önceki `current` ve `previous` symlink hedefleri aynı; data digest aynı |
| Bozuk task JSON, unknown root schema, desteklenmeyen legacy task şekli, unknown message schema veya versioned screen row | Red | İki pointer hedefi ve reddedilen dosyalar byte-for-byte aynı |
| Pointer hatası/fault injection | Var olan `CommitUnknown` sözleşmesi | Önceden kabul edilmiş gate sonrası davranış; data root değişmez |

Çalıştırma:

```sh
python3 -m unittest tests.test_release_installer -v
```

Bu fixture setinde **14 test geçti**. Kapsamı yalnız test filesystem'indeki manifest/data sınıfları ve pointer yollarıdır.

## Bilinçli sınırlar

- Bu gate release manifest çifti ve görünür data schema sınıflarını kontrol eder; writer'ların durduğunu, hedef release'in çalışan process olduğunu, ekran semantiğinin tüm tarihsel producer'larla uyumunu, auth/receipt state'ini veya host namespace'ini kanıtlamaz.
- Data root taraması tek transaction snapshot veya ortak `.kilit` kilidi değildir. Her dosyanın kendi okuma sırasında değişmediğini kontrol eder; kaynaklar arasında eşzamanlılık ve rollback penceresindeki writer'lar için #632/#617 operatör kapıları geçerliliğini korur.
- Current manifest stored install metadata'dır; manifest/payload eşleşmesi ve release ID bağı kontrol edilir. Target için ayrıca mevcut dışarıdan verilen manifest pin ve source verification gerekir.
- Fail-closed karar/limitler bir **prototip** kapsamıdır; canlı host üzerinde rollback denemesi veya release GO yetkisi oluşturmaz. Hata, `current` veya `previous` pointer'ını otomatik değiştirmez.

## Kaynaklar

- [#632 release rollback veri şeması matrisi](release-data-schema-rollback-matrix-632.md)
- [#618 installer fault-injection fixture](release-installer-fault-injection-618.md)
- `release_installer.py::_manifest_data_contract`, `_validate_actual_data_root`, `rollback_release`
- `tests/test_release_installer.py`
