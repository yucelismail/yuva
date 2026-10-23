# Yuva doctor release UNKNOWN kanıt fixture'ı (#705)

**Tarih:** 2026-10-23
**Durum:** #610/#646/#658 karar sınırları için sentetik regresyon fixture'ı. Host veya release kararı değildir.

## Kapsam ve sonuçlar

`tests/test_doctor.py::test_rollback_evidence_chain_metadata_and_conflicts_stay_unknown_or_fail`
mevcut rollback fixture'ındaki açık metadata/zincir dallarını tamamlar:

| Sentetik durum | `rollback_data_schema` | Neden |
|---|---|---|
| Install root, `releases/` veya `manifests/` mode sapması | `unknown` | Pointer/manifest kanıtı güvenli metadata koşullarında okunamıyor. |
| Manifest mode `0644` veya ikinci hard link | `unknown` | Manifest custody metadata'sı sözleşmeye uymuyor. |
| Duplicate JSON key | `unknown` | Manifest canonical/tek anlamlı biçimde parse edilemiyor. |
| Manifest içindeki `release_id`, pointer kimliğiyle çelişiyor | `unknown` | Stored manifest ile pointer kanıt zinciri uyuşmuyor. |
| Geçerli current ve target manifestleri farklı schema contract söylüyor | `fail` | Bilinen uyuşmazlık rollback için NO-GO. |
| Eşit bilinen v1 + data-root ve writer-schema PASS | `candidate` | Yalnız dar bir schema önkoşulu; release/rollback GO değil. |

Var olan `test_rollback_data_schema_contract_pointer_and_metadata_fail_closed`
eksik/malformed manifest, eksik/bozuk/eş pointer ve aynı current/previous
release durumlarını sınar. `test_rollback_data_schema_candidate_is_bounded_and_never_a_go`
eşit-known candidate durumunda presence/runtime gibi ayrı kanıtlar UNKNOWN
iken genel doctor özetinin UNKNOWN kaldığını korur. Yeni testlerle birlikte
`tests.test_doctor` hedefli modülü **14/14 geçti**.

Bu sonuçlar #610'daki UNKNOWN/eksik kanıt → release NO-GO kuralını ve #632/#646
ayrımını korur: manifest metadata eşitliği dış pin veya target reader/writer
uyumu değildir; `writer_schema=PASS` tam actual-data kabulü değildir; candidate
GO/rollback izni vermez. #658'in statik denetiminde işaretlenen directory
mode, manifest mode/hard-link ve duplicate-key dalları artık disposable
fixture ile görünürdür.

## Sınırlar

Test yalnız `TemporaryDirectory` içindeki sentetik install/data root'u
kullanır. Canlı root, servis, process, backup, writer-freeze, target release
veya YUVA_DIR okunmadı. Fixture owner-mismatch'i iki UID altında kanıtlamaz;
bu metadata/provenance veya anti-rollback kabulü değildir. Genel karar için
#682 kanıt indeksindeki kalan release, backup, reader/writer, screen ve
operatör kapıları ayrıca gereklidir.
