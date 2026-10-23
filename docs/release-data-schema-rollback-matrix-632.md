# Release rollback için desteklenen veri şemaları matrisi (#632)

**Tarih:** 2026-10-23
**Durum:** Kaynak ve acceptance sözleşmelerine dayalı rollback karar matrisi; gerçek `YUVA_DIR` okunmadı, release pointer/installer/deployment değiştirilmedi, test çalıştırılmadı.
**Karar:** Bilinen, aynı `yuva-data-contract/v1` için bile manifest eşitliği yalnız önkoşuldur; actual data root ve writer/reader zinciri ayrıca doğrulanmalıdır. Bilinmeyen sözleşme veya veri kaydı varsa rollback **NO-GO/HOLD**.

## Şu anki data contract

| Veri | Bugünkü v1 sözleşmesi | Current v2 CLI/panel/backup verifier desteği | Rollback sınırı |
|---|---|---|---|
| `durum.json` kökü | `kullanicilar`/`rev`; `schema_version` eksikse v1 kabul edilir. İlk başarılı yazım `schema_version: 1` ekleyebilir; migration değildir. | CLI, panel ve backup validator eksik/v1 kabul eder; unknown, bool veya başka sürümde fail-closed. Unknown root alanları v1 writer'da korunur. | Yalnız v1 okuyup/yazan hedefler için aday. Schema'sız dosyayı okuyan tarihsel kopyanın yeni v1 alanını koruduğu garanti edilmez. |
| `gorevler.json` kökü | `siradaki`/`gorevler`; sürümsüz eski dosya v1 sayılır. İlk başarılı yazım v1 tag ekleyebilir. | CLI, panel ve backup validator v1; unknown/bool/başka sürüm mutation/verify reddi. Task record semantiği ayrıca release writer contract'ına tabidir. | Yalnız v1 hedef ve onaylı task writer. Dev/UI/restore eski kopyalarının lock/schema guard'ı yetersiz olabilir; manifest uyumu bu kopyaları kanonik yapmaz. |
| `mesaj.jsonl` | Dosya bazlı migration yok. Her satır bağımsız: sürüm alanı yoksa legacy/v1, açık `schema_version` 1 veya 2 kabul edilir. Mixed legacy/v1/v2 geçerlidir. | Canonical CLI/panel bu biçimleri okur; unknown/invalid version satırı normal görünümden çıkarılır. Backup verifier da versioned row için yalnız v1/v2 kabul eder. | Target okuyucusunun bütün row sürümlerini ve provenance alanlarını koruyup okuyabildiği ayrıca kanıtlanır. Daha eski release'in v2 satırını görmezden gelmesi/yeniden yazması ihtimali release contract eşitliğinden çıkmaz. |
| `ekran/<kimlik>.jsonl` | Mevcut kayıt şekli sürümsüzdür; #564 sonrası bilinen bazı credential pattern'leri screen writer'ında redakte edilir. Legacy içerik farklı zamanda üretilmiş olabilir. | JSONL object/tail ve yazıcı-redaction kontrolleri vardır; açık screen schema version/migration contract yoktur. Backup verifier satırları JSON object olarak doğrular, screen schema version tanımlamaz. | Content shape aynı görünse bile yeni redaction/producer semantiğinin eski UI/reader ile rollback uyumu bu manifest ID'sinden kanıtlanmaz. Screen record formatı için ayrı version/fixture kapısı gerekir. |
| Auth store, receipts, yedek metadata | `yuva-data-contract/v1` manifest field'ının dışında ayrı store/operation state olabilir. | Mevcut manifest `YUVA_DIR`'i payload dışı tutar; `release_installer` bu external stores'ların state version/anti-rollback uyumunu okumaz. | Bu matris auth-state rollback'i, receipt/outbox replay veya provider state'ini onaylamaz; her biri kendi generation/backup/custody sözleşmesine bağlıdır. |

Temel kaynak: [#549 JSON/JSONL şema uyumluluğu](data-schema-compatibility-549.md). Release manifest `data_contract.schema_compatibility=yuva-data-contract/v1` değerini verir; bu contract durum/görev v1, mesaj legacy/v1/v2 okuyucu ve sürümsüz ekran biçimini tanımlar. Etkin data root manifest payload'ına dahil değildir.

## Source contract eşitliğine göre rollback matrisi

`release_acceptance.schema_rollback_compatible(current, rollback)` yalnız iki tarafın da tam `yuva-data-contract/v1` olmasını ve eşit olmasını kabul eder. Eşitlik release-level gerekli kapıdır, ancak actual data validation ve çalışan writer doğrulamasının yerine geçmez.

| Current release'in yazdığı sözleşme | Rollback hedefi | Karar | Gerekli kanıt / gerekçe |
|---|---|---|---|
| `yuva-data-contract/v1` | `yuva-data-contract/v1` | **Koşullu GO adayı** | İki exact release manifest'i ve source/pin doğrulanmalı; actual durum/görev root v1 veya legacy, mesajlar yalnız legacy/v1/v2 olmalı; screen formatı ve geçmiş writer'lar ayrıca incelenmeli; target CLI/panel bu data root'u okuyup yazabilmeli. Backup/restore, tek writer ve stopped-writer kapıları da geçmeli. |
| `yuva-data-contract/v1` | Bilinmeyen, boş veya `unspecified` | **NO-GO** | #550 helper exact known ID dışında `False` verir; release manifest verifier'ın biçimi kabul etmesi semantic compatibility kanıtı değildir. |
| Bilinmeyen/different contract | `yuva-data-contract/v1` | **NO-GO** | Current release'in data root'a hangi alan/record semantiğini yazdığı bilinmiyor; target v1 bu veriyi reddedebilir, sessizce atlayabilir veya yeniden yazabilir. |
| `yuva-data-contract/v2` veya başka yeni contract | `yuva-data-contract/v1` | **NO-GO, migration istisnası olmadan** | Root `schema_version=2` current v1 CLI/panel/backup verifier tarafından reddedilir. Yeni mesaj row version'ı eski reader tarafından görünmeyebilir. Önceden tasarlanmış geriye dönüşlü dönüşüm, ayrı verified data copy ve explicit operator acceptance gerekir; otomatik data rollback yok. |
| `yuva-data-contract/v1` | Daha eski, schema gate'i/lock/writer uyumu bilinmeyen release | **NO-GO/HOLD** | Manifest contract eşitliği eski binary'nin desteklediğini kanıtlamaz. Hedef reader/writer source ve izole fixture ile actual data shapes üzerinde kabul edilmelidir. |

## Actual data state'e göre overlay kapısı

Release manifestleri source/payload'u sabitler; `YUVA_DIR`'i okumaz. Aşağıdaki tablo manifest ikilisi v1 olsa bile geçerlidir:

| Gözlenen actual data | Rollback etkisi |
|---|---|
| `durum.json`/`gorevler.json` sürümsüz veya v1, `mesaj.jsonl` satırları legacy/v1/v2; tüm JSON/JSONL yapıları valid | #549 v1 schema candidate'i. Target release exact source ile desteklemiyorsa GO değildir; data root bütünlüğü, screen formatı, backup ve writer kanıtları ayrıca. |
| Kök dosyada `schema_version` bool/string/future v2, veya mesaj satırında unknown version | Canonical v1 reader/backup verifier desteklemiyor. Değişiklik öncesi fail-closed; target'a rollback yok. Raw data rewrite/unknown satır silme yok. |
| Kök JSON bozuk/kısmi, duplicate/invalid task state/ID ya da JSONL bozuk tail | Uyumluluk sonucu unknown/fail. Eski target ile deneyerek “tamir” etme; read-only inventory/backup, operatör kontrollü recovery ve izole restore planı gerekir. |
| Screen JSONL sürümsüz ama producer/redactor dönemi veya tüm row şekli belirsiz | Contract v1 bunu versioned data olarak ispatlamaz. Host/content policy kabul edilmeden rollback kapısı unknown kalır; screen legacy/raw içeriği silme/yeniden yazma yok. |
| Restore'dan gelen root veya eski CLI/dev/UI kopyası yazmış data | Schema alanı tutarlı görünse bile aynı writer/reader contract'ı varsayma. Kaynak/hash, mode, lock ve fixture kanıtı belli değilse `HOLD`. |

`bin/yuva doctor` içindeki read-only `_doctor_schema_writer()` yalnız durum/görev schema sürümünü ve mesaj JSONL version biçimini sınırlı/bounds'lu metadata özetiyle inceler. Ek `rollback_data_schema` satırı current/previous pointer'larının stored manifest `schema_compatibility` metadata'sını karşılaştırır; yalnız iki manifest de bilinen v1 ise ve actual `writer_schema` geçerse `candidate` verir. Bu external manifest pin doğrulaması, target release reader/writer incelemesi, screen JSONL format/version'ı, auxiliary store'lar veya etkin process kanıtı değildir. `candidate` rollback onayı/GO sayılmaz; release ve actual data kabulü ayrıca gerekir. Komut gerçek Yuva dosyalarını okuyabilir; bu matriste canlı `doctor` çalıştırılmadı.

## Installer ve fixture arasındaki fark

- `release_manifest.py` manifest şeklinin `schema_compatibility` değerini non-empty string olarak doğrular. Manifest/payload/source/external pin doğrulaması bu alanın bilinen/yeni data contract ile uyumunu tek başına değerlendirmez.
- Bu matris yazıldığında `release_installer.rollback_release()` hedef release manifest/source/payload/pin'ini doğruluyor, ancak current/target contract eşitliğini veya gerçek `YUVA_DIR` şemasını kontrol etmiyordu. #645 bu boşluk için yalnız geçici root'larda sınanmış dar bir fail-closed prototype gate ekledi; ayrıntı ve kalan sınırlar [#645 actual-data gate raporunda](release-rollback-actual-data-gate-645.md). Bu kod rollback'i data migration/restore yapmaz.
- `release_acceptance.py::schema_rollback_compatible()` yalnız her iki fixture manifestinde exact known `yuva-data-contract/v1` equality ister; gerçek data root validation farklı kapıdır. #550/#609 fixture'ları yalnız sentetik status/task/message kaydıyla çalışır ve host schema kabulü değildir.

Bu nedenle gerçek rollback prosedürü pointer işleminden **önce** manifest contract çiftini, actual data state'i ve target writer/reader desteğini operatör tarafından ayrı karara bağlamalıdır. Bu kontrol yoksa installer rollback komutunu çalıştırmak için veri compatibility onayı yoktur.

## Gelecek contract değişikliği ve rollback penceresi

Yeni root/row/schema semantiği yazacak release öncesi:

1. `yuva-data-contract/v2` için desteklenen durum/görev/message/screen şekilleri, writer ve backup/restore validator'ları tanımlanır; eski okuyucuların unknown data'yı fail-closed mi yoksa read-only mi ele alacağı kararlaştırılır.
2. Her iki manifestteki `schema_compatibility` değeri ve actual data migration yönü fixture ile sınanır. Contract ID'si değişmesi, dönüşümün gerçekten yapıldığını kanıtlamaz.
3. Eski release'e dönüş gerekiyorsa yeni yazımın v1 okuyucuya güvenli geri dönüşü, destructive downgrade yokluğu, backup + izole scratch conversion ve rollback sonrası verinin nasıl sürdürülmeyeceği tasarlanır. Yalnız `schema_version` alanını düşürmek yasaktır.
4. Rollback penceresi kapanmadan v2-only data yazımı açılmaz; eski binary yazıcıları aynı data root'tan engellenir. Pencere kapatma ve owner onayı release makbuzuna bağlanır.

## Release karar checklist'i

- [ ] Current ve target tam release ID, source commit/tree, manifest digest ve independent pin ile doğrulandı.
- [ ] Manifestlerde iki exact known `schema_compatibility` değeri eşit; unknown/missing/different contract yok.
- [ ] Actual `YUVA_DIR` release dışında, owner/mode/path doğrulandı; data içeriği target desteklediği schema'lardan oluşuyor.
- [ ] Durum/görev root schema; tüm mesaj row version'ları ve screen JSONL producer/shape desteği hedef code'da kabul edildi.
- [ ] Target CLI/panel/backup reader ve writer fixture'ları aynı actual data class'larına karşı kanıtlandı; legacy/dev/restore writer aktif değil.
- [ ] Verified backup/restore-check, schema rollback uyumu ve data root değişmezliği için ayrı makbuz var.
- [ ] Unknown, bozuk kuyruk, `CommitUnknown`, aktif writer veya orphan/restore-check `HOLD` kalmadı.
- [ ] Cutover/rollback kararı operatör onaylı; installer'ın pointer switch'i data restore/migration gibi yorumlanmıyor.

Herhangi bir kutu belirsizse rollback **NO-GO**; yazımları dondur, pointer/data'yı değiştirme ve salt-okunur uzlaştırma/owner recovery kararı al.

## Kaynaklar ve kanıt sınırı

- [#549 schema sözleşmesi](data-schema-compatibility-549.md); `bin/yuva` ve `panel/server.py` schema validator'ları.
- `release_manifest.py::DATA_CONTRACT`, `_validate_manifest_shape()`, `verify_manifest()` — contract metadata shape'i; actual data root payload dışında.
- `release_acceptance.py::schema_rollback_compatible()` ve `tests/test_release_acceptance.py` — exact known contract equality fixture gate'i.
- `backup_verify.py::_validate_state`, `_validate_tasks`, `_validate_jsonl`, `_validate_restored_yuva` — backup/scratch content checks; screen schema version ayrı tanımlı değil.
- [#543 installer/rollback](release-installer-543.md), [#576 Go/No-Go matrisi](local-mvp-release-go-no-go-matrix-576.md), [#604 rollback checklist'i](operator-acceptance-rollback-checklist-604.md).
- [#645 rollback actual data contract gate'i](release-rollback-actual-data-gate-645.md) — source ve fixture prototipi; canlı rollback/host GO kanıtı değildir.

## #646 doctor projeksiyonu fixture addendum'u

`yuva doctor` salt-okunur `rollback_data_schema` satırı current/previous
pointer'larını, stored manifest contract'larını ve actual data-root/writer
schema sonucunu ayrı değerlendirir. Bilinen eşit v1 contract ile PASS actual
data root ve writer yalnız `candidate` verir. Missing/malformed metadata veya
actual schema UNKNOWN kalır; mismatch/unsupported contract ya da schema FAIL
verir. Candidate external manifest pin'ini, target reader/writer'ı, screen
satırlarını, auxiliary store'u veya runtime'ı kanıtlamaz ve GO/rollback izni
üretmez.

`tests/test_doctor.py` içindeki bounded fixture geçici dizinde current/previous
release ve manifestleri kurarak eşit-known, mismatch, missing/malformed
metadata, bozuk/eksik/eş pointer, actual data-root PASS/FAIL/UNKNOWN ve
writer-schema PASS/FAIL/UNKNOWN dallarını sınar. Runtime/presence UNKNOWN iken
doctor özeti GO olmaz. Çalıştırma: `python3 -m unittest tests.test_doctor -v`.
Bu fixture gerçek `YUVA_DIR` veya canlı install root'u taramaz/değiştirmez.

Bu çalışma statik bir uyumluluk matrisi hazırlar; data root açmaz, `doctor`/fixture/test çalıştırmaz, manifest üretmez, pointer/servis değiştirmez veya migration/backup/restore yapmaz.

## #645–#647 güncel release kapısı eşlemesi

2026-10-23 görev tahtasında #645, #646 ve #647 `verified` görünür. Bu statü
artifact/fixture kabulidir; canlı release, `INSTALL_ROOT`, gerçek `YUVA_DIR`
veya rollback onayı değildir.

| Görev / kaynak | Kanıtlanan dar davranış | #632 rollback checklist'inde kalan kabul |
|---|---|---|
| [#645 — actual data gate](release-rollback-actual-data-gate-645.md) | Verified geçici install/data-root fixture'ı: current/target exact bilinen v1 contract eşitliği, sınırlı durum/görev/message/screen actual data sınıfları ve fail-closed pointer öncesi kontrol. Hatalı/unknown dalda pointer/data byte'ları değişmez. | Bu prototip çağrılan root'ta dosya bazlı read-only sınıflandırmadır; canlı host, bağımsız target manifest pin custody'si, source tree immutability, tüm eski reader/writer süreçlerinin durdurulması veya scan sırasında bütün data root'un tek transaction snapshot'ı değildir. Eşzamanlı writer belirsizse **HOLD/NO-GO**. |
| [#646 — doctor `rollback_data_schema`](release-data-schema-rollback-matrix-632.md) | Verified bounded fixture eşit-known contract + actual root/writer pass için yalnız `candidate`; mismatch/unsupported/schema fail → `fail`; missing/malformed/actual unknown → `unknown`. Genel doctor summary runtime/presence unknown iken GO üretmez. | Doctor `writer_schema=PASS` sınırlı root schema version/message version sinyalidir; #645 kapsamındaki full actual-data acceptance veya target release reader/writer kabulü yerine geçmez. Stored manifest `schema_compatibility` dış trust pin'i değildir. |
| [#647 — staging inventory](release-staging-readonly-inventory-647.md) | Verified read-only, bounded envanter geçici fixture'da staging/orphan/pointer/receipt sinyallerini içerik sızdırmadan raporlar. Belirsiz sınıflar `HOLD`; cleanup/publish/pointer repair yok. | Inventory `HOLD` veya eksik manifest/pointer durumu release'i hazırlamaz ya da rollback'e izin vermez. Owner/process uzlaştırması, external manifest/payload pin ve operatör kararı ayrı kalır. |

## Güncel NO-GO kuralı

Manifest contract equality, doctor `candidate` veya staging inventory sonucu
birbirinin yerine geçmez. #645 actual-data prototype gate'i, #646 doctor
projection'ı ve #647 staging inventory'si ayrı kanıtlardır. Hiçbiri bu görevde
canlı çalıştırılmadı. Rollback ancak exact current/target release ve bağımsız
pin, gerçek ve release dışında data root, hedef reader/writer uyumu, screen /
auxiliary-store sınırı, backup restore-check, writer durdurma/eşzamanlılık ve
owner onayı ayrı ayrı kabul edildiğinde aday olabilir. Herhangi bir unknown,
`HOLD`, aktif/eski writer veya provenance boşluğu **NO-GO** bırakır.

Bu addendum genel MVP karar matrisindeki kapı 4'ü de değiştirmez: veri
şemasının rollback'e uygunluğu, anonim GET/browser erişim kararını veya
snapshot'ın hangi okuyucuya açılmasını kabul etmez. #576'daki güncel kapılar ve
#638–#657 artifact eşlemesi [MVP Go/No-Go matrisinde](local-mvp-release-go-no-go-matrix-576.md)
yer alır.
