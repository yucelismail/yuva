# Rollback ledger ve reader karar fixture'ı (#709)

**Durum:** Yalnız sentetik fixture/prototip. Gerçek `YUVA_DIR`, canlı install root, servis, pointer, backup veya release'e dokunulmadı. `release_installer` karar davranışı değiştirilmedi.

## Karar modeli

`prototypes/rollback-data-decision/decision.py`, #645 actual-data sınıflarını ve #646 doctor projeksiyonundaki `candidate` sınırını daha dar bir sentetik karar girdisiyle birleştirir. Bu kod üretim rollback yoluna bağlı değildir.

- Current ve target manifest contract'ı exact bilinen v1 değilse sonuç `HOLD`; eşitseler `NO-GO`.
- Sentetik actual schema sınıfları eksik/bilinmiyorsa veya target reader kaydı bilinmiyorsa `HOLD`.
- Hedef reader gözlenen eski/yeni schema sınıfını desteklemiyorsa `NO-GO`.
- Task ledger içindeki nested extension'ın rollback reader tarafından korunacağı kanıtlanmamışsa `HOLD`; düşürüleceği biliniyorsa `NO-GO`.
- Sürümsüz screen JSONL ve auxiliary state için hedef reader desteği bilinmiyorsa `HOLD`.
- Writer freeze kanıtı olmadan `HOLD`.
- Bütün fixture kapıları olumlu olduğunda sonuç yalnız `candidate` olur; asla `GO` değildir. External pin, backup/restore, runtime, host, owner ve gerçek writer/process kanıtı bu prototipte yoktur.

## Sentetik ledger karşılaştırması

Fixture sentetik ledger kayıtları üretir: `durum` v1, `gorevler` v1 içinde `ledger.writer_epoch` ve bilinmeyen nested `ledger.future.tag`, mixed legacy/v1/v2 mesajlar, sürümsüz ekran JSONL ve ayrı cursor auxiliary state. Bu sınıfları eski reader'ın açık destek kümesiyle karşılaştırır. Yeni task schema v2'yi desteklemeyen eski reader `NO-GO`; nested extension preservation bilinmiyorsa `HOLD`; ekran auxiliary state bilinmiyorsa `HOLD` üretir. Explicit destek ve writer-freeze varsayımıyla çıkan `candidate`, rollback onayı sayılmaz.

| Durum | Karar |
|---|---|
| Exact bilinen contract, explicit reader desteği, nested extra korunuyor, screen auxiliary destekli, writer freeze kanıtlı | `candidate` |
| Nested extension preservation bilinmiyor | `HOLD` |
| Eski reader nested extension'ı düşürüyor | `NO-GO` |
| Sürümsüz screen/auxiliary reader desteği bilinmiyor | `HOLD` |
| Target reader bilinmiyor | `HOLD` |
| Actual task schema v2, eski reader yalnız v1 destekliyor | `NO-GO` |
| Contract bilinmiyor veya writer freeze yok | `HOLD` |

Çalıştırma: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_rollback_data_decision_fixture -v`.

Bu test gerçek ledger veya hedef release reader'ı çalıştırmaz; karar tablosunun sentetik kanıt eksikliğinde fail-closed kaldığını doğrular. #645'nin gerçek data root taraması, #646'nın read-only doctor sonucu ve #632'nin operatör NO-GO/HOLD şartları ayrı kalır.
