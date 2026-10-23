# Eski ekran JSONL kayıtları için fixture-only taşıma prototipi (#579)

**Tarih:** 2026-10-23
**Durum:** Fixture prototipi ve hedefli test tamamlandı; incelemeye teslim ediliyor.
**Sınır:** Yalnız `TemporaryDirectory` içindeki sentetik JSONL kullanıldı. Canlı `YUVA_DIR`, ekran kayıtları, backup, servis veya credential okunmadı/değiştirilmedi.

## Prototip

`prototypes/screen-migration/migrate_fixture.py` tek bir doğrudan `ekran/*.jsonl` dosyasını alır ve yalnız aşağıdaki kapılar birlikte geçerse çalışır:

- Canonical root sistem temp dizininin altında olmalı; root symlink'i reddedilir.
- Root içinde private `.yuva-screen-migration-fixture` marker'ı, doğrudan ve private `ekran/` dizini bulunmalı.
- Dosya adı yalnız basename ve `.jsonl` olabilir; dosya normal, euid sahibi, private, tek linkli olmalı. Boyut 64 MiB ile sınırlıdır.
- Root'taki sabit `.kilit` alınmadan kaynak açılmaz. Lock timeout, symlink, izin veya sahiplik hatası fail-closed olur.

Lock altında her dosya tamamen okunur; newline ile bitmeyen, boş, duplicate JSON key içeren, bozuk veya #564 redactor şemasına uymayan bir kayıt varsa **dosyanın hiçbir satırı değiştirilmez**. Her geçerli kayıt ortak `redact_screen_record()` fonksiyonuna verilir. Bulgu sayısı, `ad` veya `satir` alanı değişen kayıt alanlarının sayısıdır; eşleşme sayısı veya içerik raporlanmaz.

Bulgu yoksa `replace` yapılmaz. Değişiklik varsa geçici dosya aynı `ekran/` dizininde oluşturulur; owner/group, mode, atime/mtime ve okunup yazılabilen xattr metadata'sı korunur; geçici dosya `fsync` edilir, atomik `os.replace` yapılır ve dizin `fsync` edilir. Metadata kopyası, temp yazımı veya replace hatası rename öncesi kaynak dosyayı korur. Rename sonrasında dizin `fsync` başarısızsa sonuç `commit_unknown` olur; otomatik retry yoktur. Inode ve ctime içerik değişikliği nedeniyle doğal olarak değişir.

Komut çıktısı yalnız `status`, orijinal `device:inode` dosya kimliği, satır sayısı ve değişen alan adedi taşır. Dosya yolu, JSONL satırı, redacted değer, exception metni veya içerik hash'i yazdırılmaz. Prototype `YUVA_DIR` okumaz, backup keşfetmez ve birden fazla dosyayı recursive taramaz.

## Fixture kanıtı

`tests/test_screen_migration.py` sentetik kayıtlar ve temp root ile sekiz senaryoyu doğrular:

1. Redaction, atomik replacement, satır sayısı ile owner/group/mode/timestamp ve desteklenen xattr korunması; stdout'ta satır değeri veya dosya yolu bulunmaması.
2. İkinci çalıştırmada `unchanged`, aynı byte içeriği/inode/mtime ve sıfır yeni redaction alanı.
3. Bozuk kayıt, lock timeout, path traversal, root symlink'i ve temp dışı root reddi; kaynak içeriği korunur.
4. Replace hatasında kaynak inode/byte'ları korunur ve geçici dosya temizlenir.
5. Rename sonrası dizin-fsync hatası `commit_unknown` üretir; yeni içerik redakte edilmiştir ve retry yapılmaz.
6. Bilinmeyen pattern `unchanged` bırakılır; bu sonuç clean-history garantisine yükseltilmez.
7. Sentetik backup sibling değişmeden kalır; prototip backup/restore kopyası keşfetmez veya geri yüklemez.
8. Gerçek credential exposure bildirimi yalnız metadata flag'iyle simüle edilir; prototip kaynak dosyayı açmadan `credential_exposure_requires_rotation` ile durur.

Çalıştırma: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_screen_migration -v` — **8 test geçti**. Bu, fixture sözleşmesinin kanıtıdır; canlı ekran dosyası/backup için tarama veya migration kanıtı değildir. #711 addendum: [sentetik mirror kararı ve exposure stop kapısı](screen-migration-synthetic-mirror-711.md).

## Credential sınırı

Redaction bilinen credential biçimlerini maskeler; DLP garantisi vermez. Eski kayıtta gerçek credential bulunursa maskelenmiş JSONL satırı credential'ı geçersiz kılmaz. Operatör credential sahibine göre ilgili key/password/token için rotation veya revoke sürecini ayrıca yürütmelidir. Backup, export ve restore kopyaları ayrı hassas kaynaklardır; prototip bunları bulmaz veya temizlemez.

## Kaynaklar

- `yuva_screen_redaction.py`: kayıt şeması, high-confidence maskeler ve fail-closed redactor.
- `docs/screen-secret-redaction-564.md`: ortak writer redaction kabulü ve kapsam sınırları.
- `docs/screen-secret-redaction-rotation-559.md`, `docs/local-data-retention-export-deletion-policy-546.md`: eski kayıt/backup hassasiyeti ve credential rotation ayrımı.
