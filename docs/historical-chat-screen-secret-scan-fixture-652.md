# #652 — Tarihsel chat ve ekran kayıtları için sır içermeyen offline tarama

**Durum:** Fixture-only, read-only prototip. Canlı `YUVA_DIR`, chat/screen
JSONL, backup veya export okunmadı; gerçek secret üretilmedi ya da taranmadı.
**Tarih:** 2026-10-23

## Davranış

`prototypes/history-secret-scan/scanner.py` yalnızca sistem geçici dizini
altındaki owner-private fixture kökünü ve tam marker'ını kabul eder. Yalnız
fixture kökündeki `mesaj.jsonl` ile doğrudan `ekran/*.jsonl` dosyalarını okur;
recursive arama, varsayılan data root veya backup bulma yoktur. Dosya başına
4 MiB, satır başına 16 KiB, dosya sayısı ve satır sayısı bounded'dır. Dosya
owner/mode/type/link ve değişmeden okunma kontrollerinden geçer.

Chat için `metin` ve varsa `ad`, ekran için mevcut shared redactor'ın kabul
ettiği kayıttaki `ad` ve `satir` alanları taranır. Duplicate JSON key, bozuk
UTF-8/JSONL, geçersiz ekran şekli, oversize, güvensiz dosya veya okuma yarışı
dosya reddi ve `partial` sonuç üretir.

CLI raporu yalnız sabit policy/state/reason kodları ve aggregate sayaçlar
içerir: taranan/reddedilen dosya ve kayıt sayısı, bilinen pattern eşleşen
content field sayısı. Path, dosya adı, satır, değer, regex parçası, exception
metni veya içerik hash'i rapora/loga çıkmaz. Hiçbir kaynak dosya değiştirilmez.

## Yorumlama sınırı

`known_pattern_found` bir credential'ın türünü ya da geçerliliğini açıklamaz;
`no_known_pattern_detected` da tüm verinin sır içermediği anlamına gelmez.
Scanner yalnız bilinen pattern'leri, sınırlı kullanıcı metni alanlarında arar;
özel token formatı, parçalı/kodlanmış sır, PII veya yeni secret türleri
kaçabilir. Yalnız aggregate bulgu sayısı cleanup, revoke veya kullanıcıya
“temiz” garantisi vermez. Gerçek bir credential şüphesinde canlı içeriği bu
prototype'a vermek yerine #585 owner-controlled incident akışı kullanılmalıdır.

## Çalıştırma ve sınır

```sh
python3 prototypes/history-secret-scan/scanner.py --fixture-root /tmp/<marked-fixture>
```

Bu teslim gerçek kayıtları taramaz, yedek açmaz, credential revocation
yapmaz, geçmişi redakte etmez ve retention/delete kararı uygulamaz. İzole
sentetik fixture oluşturulup taranabilir; bu teslim kapsamında komut canlı
veri üzerinde çalıştırılmamıştır.

## Dayanak

- `yuva_screen_redaction.py` — ekran writer'larında kullanılan known-pattern
  redactor ve strict screen shape doğrulaması.
- `docs/credential-exposure-incident-runbook-585.md` — sır değerini kopyalamama,
  içerik hash'i/prefix'i üretmeme, karantina/hold ve owner-controlled
  revoke/rotation süreci.
- `docs/chat-screen-retention-export-delete-matrix-629.md` — chat/screen ham
  içerik ve geçmiş/backup kopyalarının temizlenmediği sınır.
- `prototypes/screen-migration/README.md` — fixture-only geçici kök ve gerçek
  veriye uygulanmama sözleşmesi.
