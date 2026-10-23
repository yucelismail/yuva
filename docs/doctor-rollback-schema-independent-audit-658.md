# #658 — Doctor rollback schema projeksiyonu bağımsız statik denetimi

**Tarih:** 2026-10-23
**Kapsam:** `bin/yuva` içindeki `_doctor_pointer_release()`,
`_doctor_manifest_contract()`, `_doctor_schema_writer()`,
`_doctor_rollback_data_schema()` ve `cmd_doctor()` akışının #632 matrisi ile
statik karşılaştırması. Canlı `doctor`, host taraması, fixture veya test
çalıştırılmadı; kaynak kod değiştirilmedi.

## Kaynak-kabul ölçütleri

| Ölçüt | Kaynak davranışı | Kabul sonucu / sınır |
|---|---|---|
| Install root ve `releases/` | `_doctor_pointer_release()` her ikisini gerçek dizin, symlink değil, euid sahibi ve mode `0700` olarak ister. | Eksik/okunamayan veya yanlış metadata pointer için `unknown`; dışarı yönelen yol kabul edilmez. Release alt dizini ayrıca dizin ve symlink değil diye kontrol edilir; owner/mode koşulu release dizinine uygulanmıyor. Mevcut rollback fixture'ında parent'ların yanlış owner/mode dalları ayrıca gösterilmiyor. |
| `current` ve `previous` pointer biçimi | Pointer symlink olmalı; link hedefi tam `releases/<commit>-<sha256>` biçiminde olmalı; release dizini bulunmalı. | Eksik/bozuk/uygunsuz pointer `unknown`; iki pointer aynı release ise `fail`. Pointer hedefi yalnız ID/yol yapısı ve dizin varlığını kanıtlar, payload hash doğrulaması değildir. |
| `manifests/` dizini | Gerçek dizin, symlink değil, euid sahibi ve mode `0700`; descriptor ile açılır. | Koşullar bozulursa contract okunamaz ve `unknown` olur. Mevcut rollback fixture'ında yanlış mode/owner branch'i görünür değil. |
| Manifest dosyası | `O_NOFOLLOW`; regular file, euid sahibi, mode `0600`, tek hard link, en çok 4 MiB. JSON UTF-8, duplicate key reddi ve manifest shape doğrulaması uygulanır; manifest `release_id` pointer ID ile eşleşmelidir. | Eksik/malformed metadata `unknown`. Fixture bozuk shape ve missing dosyayı kapsıyor; mode, hard-link ve owner mismatch dalları ayrıca sınanmıyor. Bu stored metadata'nın okunmasıdır; dış güven kökü/pin, manifest imzası veya payload digest kabulü değildir. |
| Contract semantiği | Her iki manifestte aynı, bilinen `yuva-data-contract/v1` aranır. Farklı değerler `fail`; eşit ama bilinmeyen değer de `fail`. | Eşit bilinen contract yalnız gerekli release-level önkoşuldur. Hedef okuyucu/yazıcı uyumu, screen ve auxiliary store desteği çıkarılamaz. |
| Actual data root | `data_root` satırı gerçek dizin, euid sahibi, mode `0700` ve giriş yolunun symlink olmamasını denetler. `fail` rollback projeksiyonunu `fail`, eksik/okunamayan root `unknown` yapar. | Metadata/integrity ön koşulu geçmeden aday oluşmaz. Etkin unit'in bu kökü kullandığı veya erişim sınırları kanıtlanmaz. |
| Actual `writer_schema` | Durum/görev dosyalarının JSON nesne ve desteklenen integer schema sürümü olmasını, mesaj satırlarının JSON nesne ve desteklenen sürüm olmasını sınar. Unsupported sürüm `fail`; eksik/parse edilemeyen dosya `unknown`; gözlenen dar metadata uygunsa `pass`. | `pass`, tam kayıt şeması veya target release'in okuyup yazabildiği anlamına gelmez. Screen JSONL, görev/kullanıcı alanlarının tam semantiği, geçmiş producer'lar ve auxiliary store'lar bu kontrolde yoktur. |
| Projeksiyon birleşimi | Pointer/manifest hataları `unknown`; contract mismatch/unsupported `fail`; actual data root veya writer-schema `fail` ise `fail`, unknown ise `unknown`. Yalnız iki bilinen eşit manifest ve iki actual pass sonucu `candidate` üretir. | `candidate` **GO değildir**; kod metni stored pin, target reader/writer, screen, auxiliary store ve runtime'ın doğrulanmadığını açıkça ekler. |
| Doctor genel özeti | Herhangi bir `fail`/`occupied` → NO-GO; aksi halde `unknown` → UNKNOWN. Bunlar yoksa dahi sonuç “ÖN KONTROL · runtime veya release doğrulaması değildir”; `candidate` için ayrıca rollback onayı olmadığını belirten ek metin yazılır. | Bu projeksiyon tek başına release GO veya rollback izni üretmiyor. Runtime/presence UNKNOWN kalması da özetin UNKNOWN olmasını sağlar. |

## #632 ile uyum ve kabul dalları

#632'nin ana kuralıyla uyumlu: manifest contract eşitliği actual data ve
writer kontrolünün yerine konmuyor; actual PASS sonucu yalnız koşullu aday;
screen semantiği, target'ın reader/writer kabulü, pin/provenance ve çalışan
process ayrıca açık kalıyor. #646 addendum'undaki fixture kapsamı kaynak
dallarını karşılıyor: eşit-known, mismatch, missing/malformed metadata,
eksik/bozuk/eş pointer, data-root PASS/FAIL/UNKNOWN, writer-schema
PASS/FAIL/UNKNOWN ve runtime UNKNOWN iken genel NO-GO. Bu fixture listesinde
pointer/manifests owner-mode ve manifest hard-link kontrolleri için negatif
dallar ayrıca yer almıyor.

| Sentetik durum | `rollback_data_schema` beklenen sonucu | Genel karar yorumu |
|---|---|---|
| İki manifestte eşit, bilinen v1; root ve writer pass | `candidate` | Release/rollback onayı değil; runtime, pin, target reader, screen ve diğer kanıtlar dışarıda. |
| Contract farklı veya aynı ama bilinmeyen | `fail` | NO-GO. |
| Pointer/manifest eksik, bozuk veya metadata koşulu geçersiz | `unknown` | NO-GO/inceleme; candidate'e yükselmez. |
| Actual root ya da writer-schema fail | `fail` | NO-GO. |
| Actual root veya writer-schema unknown | `unknown` | NO-GO/inceleme; manifest eşitliği bilinmeyen actual durumu telafi etmez. |

`tests/test_doctor.py` statik envanterinde missing/malformed pointer ve
manifest, eş pointer, contract mismatch, data-root mode/symlink ve actual
writer-schema dalları görülüyor. Rollback fixture helper'ı doğru owner/mode
ile kurulum hazırlıyor; parent install/release/manifests için hatalı mode,
manifest mode/hard-link veya owner mismatch durumları ayrı test edilmiyor.
Genel data-root izin testleri bu manifest/pointer metadata dallarını
kanıtlamaz. Bu, fixture kaynağının incelenmesidir; testler çalıştırılmadı.

## Statik denetimde görülen sınırlar

1. `writer_schema=PASS` etiketi, gerçek `YUVA_DIR` içeriğinin #632 anlamında
   tam şema uyumu olarak okunmamalı. Kaynak zorunlu root/task alanlarını,
   kayıtların tam semantiğini, screen JSONL'yi veya rollback hedef koduyla
   davranışsal uyumu kapsamıyor. #632 ve #646 açıklamaları bu sınırı
   belirtiyor; operatör raporlarında PASS metnini de aynı dar kapsamla
   sunmak gerekir.
2. `_doctor_schema_writer()` çocuk dosyalarda önce `lstat()` yapıp sonra
   `read_text()`/`open()` çağırıyor. Symlink ilk metadata kontrolünde
   `unknown` olur; fakat eşzamanlı path değiştirilmesine karşı descriptor
   bazlı `O_NOFOLLOW`/inode kontrolü yok. Aynı nedenle önceki `st_size`
   kontrolü tek başına eşzamanlı büyümeye karşı kesin okuma bütçesi değildir.
   Bu statik bulgu; canlı race veya host etkisi sınanmadı.
3. `_doctor_pointer_release()` release dizini için symlink olmadığını ve
   dizin olduğunu denetliyor; owner/mode doğrulaması install root ve
   `releases/` ile sınırlı. Manifest dosyalarının sıkı owner/mode koşulu
   stored metadata okumasını koruyor ancak release tree/payload provenance
   doğrulamasına dönüşmüyor.

Bu sınırlar mevcut koşullu `candidate` kararının GO sayılmamasını daha da
önemli kılar. Bu görev kapsamında kod veya host değişikliği gerekmedi; gerçek
release kararı için #632 checklist'inin kalan bağımsız kanıtları zorunludur.
