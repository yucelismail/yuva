# #564 — Ekran yazıcılarında ortak fail-closed sır redaksiyonu

Tarih: 2026-10-23
Durum: Kaynak ve fixture değişikliği tamamlandı; denetim için teslim ediliyor.

## Uygulama

`yuva_screen_redaction.py` panel ve CLI tarafından yüklenen ortak kural
modülüdür. İki ayrı kalıcı append sınırı aynı `redact_screen_record()`
fonksiyonunu çağırır:

- Panelin `ekle()` fonksiyonu `ekran/*.jsonl` append'inden önce kaydı
  doğrular/redakte eder. `ekran_yaz()` API'ye de aynı temiz kaydı döndürür.
- CLI `ekle_jsonl()` fonksiyonu yalnız ekran JSONL yolunda aynı işlemi
  uygular. `cmd_ekran()` yerel fallback'i sadece POST'un gönderilmediği
  kanıtlandığında bu yazıcıya ulaşır; belirsiz POST sonucunda retry/fallback
  davranışı değiştirilmedi.

Kayıt tam olarak `ts`, `kimlik`, `ad`, `tur`, `satir` alanlarını taşımalı;
timestamp, kimlik ve tür biçimleri doğrulanır. `ad` ile `satir` UTF-8 olarak
incelenir. Bearer/Basic authorization değerleri, credential anahtarı taşıyan
atamalar, credential içeren HTTP(S) URL kullanıcı/parola bölümü ve bilinen
yüksek güvenli API token biçimleri `[REDACTED:credential]` ile maskelenir.
Redakte edildikten sonra da aynı 16 KiB JSONL-record sınırı uygulanır; bu
sınır panel ve CLI ekran okuyucularındaki mevcut kayıt boyutu sınırıyla
eşleşir.

Şema/alan tipi bozuksa, UTF-8 kodlanamıyorsa, kontrol karakteri veya NUL
varsa, kayıt sınırı aşılırsa ya da redactor/serializer beklenmedik hata
verirse yazım içerik taşımayan hata ile reddedilir. Ham satırla fallback
yapılmaz ve hata mesajına kayıt değeri/istisna metni eklenmez. Kural eşleşmesi
olmayan normal metin korunur.

## Fixture kanıtı

`tests/test_screen_redaction.py` geçici `YUVA_DIR` altında sentetik veriyle:

- panel writer'ı ile gerçek CLI `POST_NOT_SENT` fallback'inin aynı redakte
  metni sakladığını; bearer, API key, cookie, credential URL ve token fixture
  değerlerinin JSONL'ye ulaşmadığını;
- panel API yanıtındaki görüntü adının da saklanan redakte değerle
  eşleştiğini;
- benign metnin korunduğunu;
- yanlış tip/alan, timestamp, kimlik, bozuk Unicode ve 16 KiB üstü kaydın
  reddedildiğini;
- enjekte edilen redactor istisnasının panel append'ini ve CLI fallback'ini
  içeriksiz hatayla durdurduğunu ve JSONL dosyası oluşturmadığını

doğrular. Çalıştırma: `python3 -m unittest tests.test_screen_redaction -v`
— 4 test geçti. `py_compile` ve hedefli `git diff --check` de temiz.

## Sınırlar

Bu regex tabanlı yüksek güvenli credential filtresidir; tam DLP, PII/path
anonimleştirme, kodlanmış/parçalı secret tespiti veya tüm sağlayıcı
credential biçimleri garantisi değildir. Credential'a benzeyen key/value
metni yanlış pozitif olarak maskelenebilir. Eski JSONL, backup, export ve
restore kopyaları değiştirilmedi; retention/rotation kararı uygulanmadı.
Canlı veri, servis veya provider kullanılmadı.
