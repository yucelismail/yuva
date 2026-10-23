# Tarihsel screen redaction sentetik mirror fixture'ı (#711)

**Durum:** Fixture-only, offline prototip. Yalnız `TemporaryDirectory` içindeki marked sentetik mirror kullanıldı. Gerçek `YUVA_DIR`, screen/chat içeriği, backup, key veya credential okunmadı/değiştirilmedi.

## Güvenli taşıma sözleşmesi

`prototypes/screen-migration/migrate_fixture.py` bir doğrudan `ekran/*.jsonl` dosyasını sabit `.kilit` altında okur, her satırı ortak #564 redactor'ına verir ve yalnız değişiklik varsa aynı dizinde temp dosya + `fsync` + atomik replace + dizin `fsync` akışı uygular. Bozuk/duplicate/unknown şekilli kayıt dosyanın tamamını reddeder. Rename sonrası directory fsync belirsizliği `commit_unknown` üretir; otomatik retry yoktur. İkinci çalıştırma redakte edilmiş kaydı değiştirmeden `unchanged` verir.

Root yalnız sistem temp dizininin altındaki, euid owner/private izinli, exact marker'ı ve doğrudan `ekran/` çocuğu olan fixture olabilir. Backup keşfi, recursive tarama veya YUVA default path'i yoktur.

## Backup, rollback ve credential olay sınırı

- Migrator yedek kopyası üretmez, backup/export/restore dosyalarını açmaz veya temizlemez. Bir synthetic backup sibling fixture'ı taşıma sonrası byte-for-byte aynı kaldı.
- Atomic replacement, otomatik rollback değildir. Replace öncesi hata kaynak byte/inode'u korur; commit sonrası belirsizlikte eski raw dosyayı otomatik geri koymak yasaktır. Restore edilen eski bir kopya redacted satırı geri getirebilir; backup/restore sahibi ayrı envanter ve karar vermelidir.
- Bilinmeyen credential pattern'i redactor değişikliği üretmez ve prototip `unchanged` döndürür. Bu yalnız bilinen pattern eşleşmediği anlamına gelir; geçmişin temiz olduğunu göstermez.
- Gerçek credential maruziyeti operatör/veri sahibi tarafından bildirilirse `--credential-exposure-reported` kaynak fixture dosyasını açmadan `credential_exposure_requires_rotation` ile durur. Argüman secret değeri taşımaz. Önce owner/issuer'ın quarantine + revoke/rotate + consumer readback akışı (#585); migration ve backup kopya işlemleri ancak incident owner'ın ayrı kararıyla devam eder.

## Fixture matrisi

`tests/test_screen_migration.py` geçici mirror üzerinde şunları doğrular: atomik redaction ve metadata korunması; byte/inode/mtime bakımından idempotency; malformed girdide no-write; replace failure'da kaynak korunması/temp temizliği; post-rename fsync hatasında `commit_unknown`/no-retry; lock timeout; temp-root/marker/symlink/traversal kapısı; unknown pattern'de `unchanged` ama temiz iddiası olmaması; backup sibling'in değişmemesi; reported exposure flag'inde kaynağa dokunmadan rotation için durma.

Çalıştırma: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_screen_migration -v`.

Kanıt fixture prototip davranışıyla sınırlıdır. Bilinen-pattern regex'i tam DLP değildir; gerçek legacy veri, backup, export, restore, owner approval veya revoke işlemiyle ilgili kanıt oluşturmaz. 7 gün ekran retention ve segment/rotation limitleri #629/#546'da yalnız operatör onayı bekleyen adaylardır; bu prototip hiçbir TTL, retention cleanup veya backup purge uygulamaz.
