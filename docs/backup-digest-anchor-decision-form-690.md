# #690 — Bağımsız backup digest anchor operatör karar formu

**Durum:** Boş form — doldurulmadı, gerçek backup/pin incelenmedi.

Bu form politika ve custody kararı içindir. Digest veya backup authenticity'yi kendisi doğrulamaz. Bir alan bilinmiyorsa `UNKNOWN/HOLD` seçin; tahminle doldurmayın.

## 1. Karar kapsamı

- Karar ID:
- Karar tarihi (UTC):
- Backup/environment kapsamı:
- Backup owner:
- Üretim operatörü rolü:
- Custody owner:
- İkinci gözden geçiren (gerekiyorsa):
- Korunacak tehdit (işaretle):
  - [ ] Arşiv/sidecar kopyalama veya storage corruption
  - [ ] Backup yazma alanına erişebilen aynı-host süreç
  - [ ] Üretim hostu/aynı UID compromise
  - [ ] Birden fazla doğrulayıcı/ayrı site
  - [ ] Diğer:
- Kapsam dışında kalan tehditler:

## 2. Anchor seçimi

Bir seçenek seçin; gerekli bağımsızlık kanıtı yoksa **No anchor / unverified** seçeneğinde kalın.

- [ ] **Anchor yok; mevcut yerel sidecar kontrolü.** Authenticity `unverified` kalacak.
- [ ] **Operatörce pinlenen SHA-256.** Bağımsız custody hedefi ve aktarım/erişim sınırı bu formun sonraki bölümlerinde tanımlandı.
- [ ] **İmzalı manifest (gelecek karar).** Bu form imza anahtarı veya verifier kurmaz; ayrı key lifecycle kararı gerekir.
- [ ] **Dış immutable store (gelecek karar).** Sağlayıcı, admin separation, retention/recovery ve silme kararı ayrıca onaylanır.
- [ ] **UNKNOWN/HOLD.** Bağımsız hedef veya owner belirlenemedi.

Seçilen anchor türünün beklenen assurance'ı:

- [ ] Yalnız arşiv/sidecar birlikte değişikliğini yakalamak
- [ ] Aynı-host/aynı-UID compromise'a karşı bağımsız koruma (kanıt gerekir)
- [ ] Kaynak üretici/provenance (digest tek başına sağlamaz; ayrı mekanizma gerekir)
- [ ] Anti-rollback/snapshot tazeliği (digest tek başına sağlamaz; ayrı mekanizma gerekir)

## 3. Custody hedefi ve sahiplik

- Hedef türü (ayrı medya/cihaz, ayrı admin/account, immutable store, yok):
- Hedef envanter/record reference (secret içermeyen):
- Backup yazma alanından hangi OS/admin/cihaz sınırıyla ayrılıyor:
- Hedefe yazma yetkili rolleri:
- Hedeften okuma yetkili rolleri:
- Aynı host/UID compromise bu hedefi de değiştirebilir mi? Kanıt:
- Custody erişim ve audit izi:
- Retention ve silme owner'ı:
- Hedef bağımsızlığı kanıtlanamadıysa karar: [ ] `UNVERIFIED/HOLD`

## 4. Backup ve pin record bağlantısı

Bu bölümde gerçek digest'i saklamak zorunlu değildir. Hassas custody alanındaki kaydın kimliğini yazın.

- Backup ID:
- Archive logical name:
- Archive üretim UTC zamanı:
- Kaynak/environment etiketi:
- Üretim tool/source revision reference:
- Digest record ID (custody hedefi):
- Algoritma/sürüm:
- Pin final archive byte'larından ne zaman/kim tarafından hesaplanacak:
- Adjacent sidecar ile bağımsızlığın ayrımı:
- Custody aktarım receipt ID:
- Üretici/aktarımı yapan rol ve zaman:
- Custody owner kabulü ve zaman:
- İkinci kontrol gerekiyorsa reviewer ve sonucu:

## 5. Verify/restore kabul kapıları

- [ ] Pin custody hedefinden bağımsız olarak alındı; archive/sidecar'dan türetilmedi.
- [ ] Backup ID ve archive adı birebir eşleşti.
- [ ] `expected_sha256.matches_archive` sonucu ayrı kaydedilecek.
- [ ] Adjacent sidecar match/mismatch sonucu ayrı kaydedilecek.
- [ ] Tar/permission/schema ve scratch restore-check sonuçları authenticity'den ayrı değerlendirilecek.
- [ ] Verifier sonucu `authenticity=unverified` ise bu etiket korunacak.
- [ ] Restore-check hedefi aktif `YUVA_DIR` dışında, private scratch olacak.
- [ ] Live restore/scratch terfi scope'u bu karardan hariç tutuldu veya ayrı onay reference'ı var:
- Verifier version/command record reference:
- Verify makbuz ID:
- Sonuç: [ ] MATCH / [ ] MISMATCH / [ ] INVALID / [ ] UNKNOWN / [ ] NOT RUN
- Sonucu kaydeden ve tarih:
- Restore kararı (ayrı owner/onay reference'ı):

## 6. Failure, loss ve mismatch kararı

- Eksik/bozuk pin davranışı:
  - [ ] Fail-closed; doğrulama/restore yok, `UNVERIFIED/HOLD`.
- Digest mismatch davranışı:
  - [ ] Restore yok; backup ID/custody record mismatch olayı aç.
- Sidecar mismatch, expected pin match davranışı:
- Verifier I/O/parse UNKNOWN davranışı:
- Custody hedefi kayıp/erişilemezse owner ve recovery yolu:
- Sidecar'dan eski pin'i yeniden üretmeye izin:
  - [ ] Hayır; eski archive `unverified` kalır.
- Olay kaydı reference'ı ve bildirim sorumlusu:

## 7. Rotation / transfer / revocation kararı

- Custody hedefi/owner değişimi için gereken ön onay:
- Eski-yeni record bağı ve dual-control şartı:
- Önceki kayıtların retention/revoke zamanı:
- Aynı isimle yenilenen archive için yeni backup ID/pin kuralı:
- Signed-manifest key rotation gerekiyorsa ayrı karara/fixture'a reference:
- Immutable-store admin/retention/recovery kararı gerekiyorsa reference:
- Rotation/transfer makbuz ID ve tarihi:

## 8. Karar ve imzalar

- Nihai karar:
  - [ ] `UNVERIFIED` — bağımsız anchor yok; mevcut yerel checksum dışında güven iddiası yok.
  - [ ] `CONDITIONAL PIN` — yalnız işbu formdaki custody hedefi ve tehdit sınırı için caller-supplied digest kullanılabilir; verifier authenticity'yi verified yapmaz.
  - [ ] `HOLD/NO-GO` — bağımsızlık, sahiplik, aktarım veya failure recovery belirsiz.
- Açık koşullar / takip işi:
- Backup owner adı/rolü, tarih:
- Custody owner adı/rolü, tarih:
- İkinci kontrol eden adı/rolü, tarih (uygulanıyorsa):
- Risk kabul sahibi ve açıkça kabul ettiği residual risk:
- Yeniden gözden geçirme tetikleyicisi/tarihi:

## Makbuz kayıt şablonu

Gerçek digest'i genel log/chat/task notuna kopyalamayın; gerekiyorsa custody store içindeki erişim kontrollü record ID'yi kullanın.

| event_id | UTC time | backup_id | event type | custody record ref/version | actor/approver role | verifier result enum | receipt ref | next state |
|---|---|---|---|---|---|---|---|---|
|  |  |  | `pin_created / custody_accepted / verify / mismatch / unknown / lost / transfer / rotate / revoke` |  |  |  |  |  |

Boş alanlar tamamlanana ve karar sahibi imzalayana kadar default durum `UNVERIFIED/HOLD`'dur.
