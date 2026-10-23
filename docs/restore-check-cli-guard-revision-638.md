# #638 — Restore-check CLI yazma sınırı ve güncel kapsam

**Tarih:** 2026-10-23
**Karar:** Operatör, tarihsel restore-check kopyalarını değiştirmeden koruma yolunu seçti. Bu karar yeni restore-check scratch çıktılarının fail-closed olmasını kabul eder; iki tarihsel CLI kopyasının kendisinin yazamadığını iddia etmez.

## Kabul edilen kapsam

- `backup_verify.restore_check()` yeni bir scratch çıktısı oluşturduğunda içindeki eski `bin/yuva` CLI girişini sabit exit-2 inspection-only stub ile değiştirir.
- `tests/test_restore_check_cli_write_guard.py` sentetik tar, geçici scratch ve sentetik `YUVA_DIR` kullanarak bozuk, v1 ve bilinmeyen schema durumlarını sınar. Canonical CLI writer davranışı ayrı tutulur.
- Arşiv/tar, sidecar, tarihsel restore-check ağaçları ve canlı görev defteri değiştirilmeyecek.
- Tarihsel yolların mevcut kopyaları çalıştırılmamalıdır; bu kopyaların davranışı güvenli kabul edilmez. Ayrı kullanım/containment kararı #659 kapsamında izlenir.

## Tarihsel kopyalar ve düzeltme kaydı

İlk revizyon denemesinde iki tarihsel `bin/yuva` dosyası path-aware guard ile değiştirildi. Bu değişiklik görevdeki “gerçek yedek kopyalarına yazma” sınırını aştığı için teslim reddedildi. Değişiklikler, teslimdeki geri alma kopyalarından atomik olarak geri alındı. Son doğrulamada her iki dosya da özgün SHA-256 `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` ve `0775` modundaydı.

Etkilenen tarihsel yollar:

- `<YUVA_DATA_ROOT>-yedek/restore-check.T4hbP8/yuva/bin/yuva`
- `<YUVA_DATA_ROOT>-yedek/restore-check.XOeUcj/yuva/bin/yuva`

Bu iki dosya şu anda ilk teslimdeki guard'ı **içermez**. Bu nedenle doğrudan bu kopyalarla çağrılan task komutlarının yazamayacağı kanıtlanmış değildir. Arşiv/tar ve sidecar'lara, canlı `YUVA_DIR` görev defterine veya servis ayarlarına dokunulmadı.

## Kanıt ve sınırlar

İlk teslim raporu [restore-check CLI yazma guard'ı](restore-check-cli-task-write-guard-638.md) ve `tests/test_restore_check_cli_write_guard.py` içindedir. Bu kanıt yeni scratch restore-check çıktısını kapsar; tarihsel iki yolun kendisini güvenli hale getirmez. İlk test teslimde raporlanmıştır; bu kapsam kararında test yeniden çalıştırılmadı.

## Sonuç

#638, kapsamı operatör kararıyla scratch çıktılarıyla sınırlı olacak şekilde değerlendirilir. Tarihsel iki kopya ayrı ve açık bir risk olarak kalır; #659 bu kopyaların güvenli kullanım/containment yolunu ele alır. Bu kabul, eski kopyalara `gorev` yazma kapısı eklendiği veya eski kopyaların artık çalıştırılabileceği anlamına gelmez.
