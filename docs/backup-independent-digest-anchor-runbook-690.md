# #690 — Bağımsız backup digest anchor custody runbook'u

**Tarih:** 2026-10-23
**Durum:** Prosedür taslağı; bağımsız custody hedefi seçilene ve operatör formu onaylanana kadar akış etkin değildir.
**Bağlı kararlar:** #565 trust-anchor kararı, #616 caller-supplied digest sözleşmesi, #624 custody runbook'u.

## Amaç ve iddia sınırı

Bu prosedür, backup arşivinin son byte'larından hesaplanan SHA-256'yı arşiv ve yanındaki `.sha256` sidecar'dan **bağımsız bir güven alanında** saklayıp daha sonra verifier'a beklenen digest olarak sağlamayı tarif eder. Böyle bir pin, arşivle sidecar beraber değiştirilmişse eski pin ile uyuşmazlığı ortaya çıkarabilir.

Digest eşleşmesi tek başına backup üreticisinin kimliğini, üretim hostunun temizliğini, snapshot tutarlılığını, arşiv içeriğinin güvenli olduğunu veya restore'un doğru olduğunu kanıtlamaz. `backup_verify.py` çıktısındaki `authenticity: unverified` etiketi digest eşleşse de korunur. Ayrı ve doğrulanmış custody hedefi yoksa pin üretmeyin/kopyalamayın; mevcut yerel sidecar kontrolüyle yetinin ve authenticity'yi `unverified` bırakın.

## Roller ve ön koşullar

- **Backup owner:** backup ID/amacı ve izin verilen restore kullanımını belirler.
- **Üretim operatörü:** onaylı akışta arşivi üretir ve final archive byte'ları için digest hesaplar.
- **Custody owner:** bağımsız hedefi, erişim listesini, kabul makbuzunu ve kayıt saklama/rotation'ını yönetir.
- **İkinci kontrol eden:** threat model dual-control gerektiriyorsa iş kimliği ve aktarım eşleşmesini bağımsız karşılaştırır. Aynı üretim hostundaki ikinci oturum bağımsız kontrol sayılmaz.

İş başlamadan önce [karar formu](backup-digest-anchor-decision-form-690.md) doldurulup onaylanır. Bağımsız hedefin farklı bir path olması yeterli değildir: backup yazarı ile pin yazarı aynı host/UID/yönetici alanındaysa trust boundary oluşmuş sayılmaz. Onaylı medya/cihaz, ayrı admin/account veya bağımsız immutable hizmet yoksa adımları durdurun.

## Backup ve pin oluşturma

1. **Kimlik ata:** benzersiz `backup_id`, kaynak/environment etiketi, backup amacı ve UTC üretim zamanı belirle. Aynı archive adının üzerine yazılması yeni backup ID gerektirir.
2. **Final arşivi üret:** yalnız onaylı backup akışını kullan; etkin `YUVA_DIR`'i hedef yapma. Archive byte'ları kapanıp yazım tamamlanmadan digest hesaplama.
3. **Digest'i hesapla:** güvenilen üretim adımında final archive byte'larının SHA-256'sını hesapla. Yanındaki `.sha256` dosyasından değer kopyalama. Bu prosedür gerçek backup/hash'i üretmez; uygulandığında üretim kanıtı ve araç/revision kaydı tutulur.
4. **Bağımsız custody kaydı aç:** `backup_id`, archive adı, SHA-256, algoritma, UTC zamanı, üretim aracı/revision, source label, custody channel/media reference, kaydı oluşturan operatör ve erişim sınıfını custody hedefinde kaydet. Yuva mesajı, görev panosu, genel log veya archive klasörü bağımsız pin deposu değildir.
5. **Aktarımı doğrula:** custody owner backup ID/archive adını pin kaydıyla eşleştirir ve aktarımın tamam olduğunu makbuza bağlar. Dual-control seçildiyse ikinci kişi iki taraftaki değeri bağımsız karşılaştırır. Yanlış veya eksik aktarımda pin'i düzeltip sessizce overwrite etme; mismatch olayı aç.
6. **Sonraki verify:** pin'i custody kaynağından yeniden al; archive adını ve backup ID'yi eşleştir. Verifier'a açık `--expected-sha256` girdisi olarak ver. Digest sır değildir ama CLI argümanı process listelerinde görülebilir; yine de gereksiz log/chat/ekran kaydına koyma.

Örnek kullanım sözleşmesi:

```text
python3 backup_verify.py verify --archive <archive-path> --expected-sha256 <custody-pin>
python3 backup_verify.py restore-check --archive <archive-path> \\
  --scratch-root <private-scratch-root> --destination-name <backup-id> \\
  --expected-sha256 <custody-pin>
```

`verify` sonucunda `expected_sha256.matches_archive=true`, adjacent sidecar karşılaştırması ve tar/izin kontrolleri birbirinden ayrı değerlendirilir. Bu sonuç `authenticity` değerini yükseltmez. `restore-check` yalnız etkin `YUVA_DIR` dışındaki yeni private scratch hedefinde çalışır; scratch verisi canlıya terfi ettirilmez.

## Makbuz ve olay kaydı

Custody kaydı sürümlü ve audit edilebilir olmalı; önceki değer sessizce ezilmemeli. Makbuz, hassas archive içeriğini değil yalnız gerekli kimlik/işlem metadata'sını taşır. Her olay için en az şunlar kaydedilir:

- `event_id`, event type, UTC time, `backup_id`, ilgili custody record version/reference;
- işlemi yapan ve onaylayan rol/kimlik;
- seçili channel/media/account reference ve erişim owner'ı;
- verify olayıysa verifier version ve sonuç enum'u (`match`, `mismatch`, `invalid_input`, `unknown`), sidecar ve archive integrity sonuçlarının ayrı enum'ları;
- rotation/loss olayıysa eski-yeni record reference, transfer/iptal onayı ve kalan kullanım durumu.

Karar formuna gerçek digest'i veya archive içeriğini kopyalamak zorunlu değildir; form custody record ID ve makbuz referansını işaret etsin. Digest'in erişim/retention kuralları seçilen custody hedefinde belirlenir.

## Fail-closed hata davranışı

| Olay | Gerekli işlem | Karar |
|---|---|---|
| Bağımsız hedef/owner/erişim sınırı bilinmiyor veya aynı host/UID alanında | Pin oluşturma/aktarımı durdur; adjacent sidecar'ı anchor sayma | `authenticity=unverified`, HOLD |
| Pin yok, biçimi geçersiz, backup ID/archive adı uyuşmuyor veya aktarım belirsiz | Archive/sidecar'dan pin'i geri üretme; olay kaydı aç ve owner'a bildir | Verify/restore yok; HOLD |
| `expected_sha256.matches_archive=false` | Dosyayı tekrar adlandırıp/eski pin'i değiştirerek geçiş sağlama; custody ve backup kimliğini incele | Mismatch; restore yok, HOLD |
| Sidecar uyuşmaz, fakat bağımsız pin eşleşiyor | İki integrity sonucunu ayrı kaydet; beklenen policy sidecar'ı zorunlu tutuyorsa FAIL | Sidecar hatasını gizleme; authenticity yine `unverified` |
| Verifier I/O/parse sonucu unknown veya scratch sonucu partial | Kör retry veya canlı restore yok; receipt ile sonucun hangi aşamada kaldığını kaydet | UNKNOWN/HOLD |
| Pin kaydı kayıp veya custody store erişilemez | Aynı archive'dan yeniden pin türetme; önceden mevcut başka bağımsız custody kopyası varsa yetkili erişimle uzlaştır | Eski backup `unverified`; gerekirse yeni backup/ID |
| Archive byte'ı değişti, yeniden paketlendi veya aynı adla yenilendi | Eski pin'i yeni byte'lara taşımama; yeni backup ID ve yeni custody süreci | Eski/new record ayrı; HOLD until anchored |

## Custody rotation, loss ve recovery

Digest-pin yönteminde kriptografik anahtar yoktur; “rotation”, medya/hesap/owner/channel değişimini veya yeni archive için yeni pin oluşturmayı ifade eder. Geçiş sırasında:

1. Eski hedef erişilebilirken owner, yeni hedefin bağımsızlık ve erişim sınırını onaylar.
2. Pin kayıtları backup ID ile aktarılır; eski ve yeni record reference bağımsız karşılaştırılır ve custody transfer makbuzu yazılır.
3. Yeni hedef doğrulanana kadar eski custody kopyası silinmez. Eski kopyanın kapatılması/silinmesi retention ve owner onayına bağlıdır.
4. Backup byte'ları değişirse önceki pin tekrar kullanılmaz; yeni backup ID ile final archive digest'i yeniden alınır.
5. Pin kaybolursa archive veya sidecar'dan eski pin yeniden hesaplanmaz. Önceden var olan bağımsız kopya bulunamazsa eski archive authenticity'si geri kazanılamaz ve `unverified` kalır.

İleride signed manifest'e geçilecekse key generation/custody, pinned public-key dağıtımı, recovery, cross-sign/rotation ve compromise revocation için ayrı karar ve kabul fixture'ı gerekir. Immutable store'a geçiş de admin separation, retention lock, recovery ve silme yükümlülüğü kararı ister. Bu iki seçenek mevcut prosedürde etkin değildir.

## Restore kararı

Pin eşleşmesi, tar formatı/üye yolu/izin kontrolleri, schema kabulü, scratch sonucu ve release owner'ın restore kararı ayrı kapılardır. `verify PASS` canlı `YUVA_DIR` üzerine restore izni değildir; `restore-check PASS` de scratch'tan canlıya kopyalama izni değildir. Beklenen digest, veri kökü, release pin veya operator scope belirsizse restore **HOLD** kalır.

## İlgili kararlar

- [#565 bağımsız trust-anchor kararı](backup-authenticity-trust-anchor-565.md)
- [#616 caller-supplied expected-digest sözleşmesi](backup-expected-digest-cli-616.md)
- [#624 digest custody prosedürü](backup-digest-pin-operator-custody-624.md)
- [#544 verify/restore-check sözleşmesi](backup-verify-restore-check-544.md)
- [Boş operatör karar formu](backup-digest-anchor-decision-form-690.md)

Bu prosedür gerçek archive, sidecar, digest/pin, custody hedefi, key, service veya active data root okumaz/üretmez/değiştirmez. Anchor seçilene ve form onaylanana kadar yerel MVP kararı `unverified` kalır.
