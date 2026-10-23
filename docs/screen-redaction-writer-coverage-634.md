# Ekran kayıtları: writer redaction kapsamı (#634)

## Sonuç

Mevcut kaynak ağacındaki ekran JSONL writer girişleri kayıt diske eklenmeden
önce `yuva_screen_redaction.redact_screen_record()` sınırından geçiyor. CLI
offline fallback'i ve panel writer'ı aynı doğrulama/redaction sözleşmesini
kullanıyor. İncelenen kaynaklarda bu kapıyı atlayan başka bir uygulama writer'ı
bulunmadı. Bu sonuç yalnızca incelenen checkout için geçerlidir; kurulu eski
CLI kopyaları, bağımsız süreçler ve elle dosya değiştirme bu kaynak envanterinin
dışındadır.

## Writer envanteri

| Giriş | Çağrı zinciri | Redaction noktası ve hata davranışı |
|---|---|---|
| Panel `POST /api/ekran` | `api_ekran()` → `ekran_yaz()` → `ekle()` → JSONL append | `ekle()` yalnız desteklenen `ekran/*.jsonl` yolunu kabul eder ve serialize etmeden önce tam kaydı redakte eder. Redactor hatası `api_ekran()` tarafından içeriksiz 400 cevabına çevrilir; raw satır JSONL'e eklenmez. (`panel/server.py:412-430, 952-959, 1381-1409`) |
| CLI `yuva ekran ...`, panel erişilebilir | `cmd_ekran()` → `/api/ekran` | Kalıcı yazımı panel yapar; aynı panel write-boundary'si geçerlidir. CLI yalnız panel başarı cevabında yerel ikinci yazım yapmaz. (`bin/yuva:1698-1716`) |
| CLI `yuva ekran ...`, POST kesin gönderilmemiş | `cmd_ekran()` → `ekle_jsonl()` → JSONL append | Fallback yalnız `POST_NOT_SENT` kanıtında çalışır. `ekle_jsonl()` ekran yolunu redactor'dan geçirir; redaction/şema hatası içeriksiz `VeriHatasi` olur ve kayıt yazılmaz. Belirsiz POST sonucu yerel tekrar yazımı başlatmaz. (`bin/yuva:355-376, 1698-1722`) |
| Tarihsel kayıt migrasyonu prototipi | `prototypes/screen-migration/migrate_fixture.py` | Her satır `redact_screen_record()` ile doğrulanıp redakte edildikten sonra fixture dosyasına atomik olarak yazılır. README bu aracı işaretli geçici fixture köküyle sınırlar; üretim Yuva veri köküne migrasyon aracı değildir. (`migrate_fixture.py:178-201`, `prototypes/screen-migration/README.md`) |

Panel ve CLI ortak writer yardımcıları, `KOK` dışındaki dosyayı ve ekran
dizininin doğrudan çocuğu olmayan JSONL yolunu reddeder. Ekran sözleşmesi tam
`{ts, kimlik, ad, tur, satir}` alan kümesi, timezone taşıyan timestamp,
kısıtlı kimlik/tür, geçerli metin, NUL/kontrol karakteri yokluğu ve 16 KiB
kayıt sınırı ister. `ad` ve `satir` için Bearer/Basic, cookie header'ları,
atanmış token/secret/parola alanları, URL kullanıcı bilgisi ve tanınan token
biçimleri redakte edilir. Beklenmeyen hata dahil redaction başarısızlığı
fail-closed sonuçlanır (`yuva_screen_redaction.py:8-9, 31-94`).

## Kanıt ve sınır

`tests/test_screen_redaction.py` şu kapsama sahip: panel ile CLI fallback
aynı sentetik credential fixture'ını aynı redakte metne çeviriyor; benign metin
korunuyor; redakte edilmemiş fixture secret'ları iki dosyada da yok; panel API
görünen adını redakte edip yanıt/kayıtta sızdırmıyor; bozuk veya aşırı büyük
kayıtlar ve redactor exception'ı iki writer'da da yazımı durduruyor
(`tests/test_screen_redaction.py:48-123`). Bu görevde yalnız kaynak/test
fixture'ları incelendi; canlı Yuva verisi veya servis okunmadı.

Redaction yüksek güvenli biçim eşleşmelerine dayanır; keyfi/şifrelenmiş veya
tanınmayan credential biçimlerinin tümünü bulma garantisi değildir. Eski
JSONL satırları yeni yazım kapısından geçmez. Panel snapshot ve `yuva ekran
oku` geçmiş içeriği okuyabilir; geçmiş dosyaların temizliği ayrı migration,
retention ve backup/restore kararı gerektirir. Harici/eskimiş writer'ların da
aynı modülü kullanması deployment ve writer envanteriyle doğrulanmalıdır.

Önceki `docs/screen-secret-redaction-rotation-559.md` notundaki “ortak
redactor henüz yok” tespiti bu checkout için artık güncel değildir; bu not
mevcut kaynak sınırını ve kalan deployment/historical-data kısıtlarını kayda
geçirir.
