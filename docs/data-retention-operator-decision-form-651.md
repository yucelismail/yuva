# #651 — Chat ve ekran verisi için operatör karar formu

**Durum:** Doldurulacak karar formu; hiçbir politika seçilmedi veya etkinleştirilmedi.
**Tarih:** 2026-10-23
**Kapsam:** Yerel Yuva'daki sohbet/mesaj ve ekran/terminal kayıtları, bunların
arşiv, backup, restore-check ve export kopyaları. Bu form veri okumaz, taşımaz
veya silmez; retention/export/delete uygulamaz.

## Karar sahibi ve politika kaydı

| Alan | Operatör kararı |
|---|---|
| Veri sahibi / karar yetkilisi | ______________________________ |
| Karar veren operatör | ______________________________ |
| Kapsanan Yuva kurulumları / data root'lar | ______________________________ |
| Politika sürümü | ______________________________ |
| Onay tarihi ve saat dilimi | ______________________________ |
| Yürürlük tarihi | ______________________________ |
| Sonraki gözden geçirme tarihi | ______________________________ |
| Hukuki/sözleşmesel saklama şartı veya referansı | ______________________________ |

Her bölüm için bir seçenek işaretleyin. Birden fazla kaynak/kopya farklı
politika taşıyorsa her kopya sınıfı için ayrı karar kaydedin. Boş, çelişkili
veya `ertelendi` kararlar otomatik temizlik izni değildir.

## 1. Birincil chat ve ekran verisinin saklama süresi

Süre, kaydın oluşturulma zamanından itibaren takvim günü olarak değerlendirilir;
özel bir başlangıç anı isteniyorsa “değiştir” alanında belirtin.

| Veri sınıfı | Seçim | Sayı / gerekçe |
|---|---|---|
| `mesaj.jsonl` ve kapalı chat segmentleri | [ ] 90 gün adayını kabul et · [ ] değiştir · [ ] ertele | Süre: ____ gün · gerekçe: __________________ |
| `ekran/<kimlik>.jsonl` ve kapalı ekran segmentleri | [ ] 7 gün adayını kabul et · [ ] değiştir · [ ] ertele | Süre: ____ gün · gerekçe: __________________ |
| Süre başlangıcı | [ ] kayıt zamanı · [ ] segment kapanış zamanı · [ ] başka | ______________________________ |
| Süresiz / belirli süre sınırı yok | [ ] Kabul et · [ ] Reddet | Gerekçe ve kontrol: ______________________________ |

Süreyi onaylamak tek başına aktif JSONL temizliğini etkinleştirmez. Aktif
dosyanın segmentlere ayrılması, ortak writer lock, bozuk kuyrukta durma,
readback/manifest ve restore uyumu ayrıca uygulanıp kabul edilmelidir.

## 2. Rotation, arşiv bütçesi ve disk dolması

Başlangıç eşikleri yalnız adaydır: chat segmenti 32 MiB veya 24 saat ve
64 KiB satır; ekran segmenti kimlik başına 8 MiB veya 24 saat ve 16 KiB satır.
Arşiv taslağı chat için 90 gün/512 MiB, ekran için kimlik başına 7 gün/global
256 MiB önerir. Bunlar ölçülmüş veya etkin değer değildir.

| Karar | Chat | Ekran |
|---|---|---|
| Rotation eşiği (byte / süre / kayıt boyu) | __________________ | __________________ |
| Arşiv TTL | __________________ | __________________ |
| Arşiv toplam byte bütçesi | __________________ | __________________ |
| Bütçe dolunca yaş önceliği | [ ] minimum saklama yaşı korunur · [ ] bütçe erken silmeye izin verir · [ ] ertelenir | [ ] minimum yaş · [ ] erken silme · [ ] ertelenir |
| Güvenli kapasite kalmadığında | [ ] yeni yazmayı durdur ve uyar · [ ] ek disk/limit sağla · [ ] başka (açıkla) | [ ] yazmayı durdur · [ ] ek kapasite · [ ] başka (açıkla) |

Karar/gerekçe: ____________________________________________________________

Minimum saklama yaşı ile byte bütçesi çatışırsa sessiz erken silme yapılmaz;
operatör seçimi yukarıda açık olmalıdır. Bozuk JSONL, eksik son LF,
`append_unknown`, `rotation_unknown` veya belirsiz dosya listesinde cleanup
durur ve salt-okunur uzlaştırma ister.

## 3. Backup ve restore-check kopyaları

30 gün/1 GiB backup taslağı ve kabul edilmiş restore-check için 30 günlük
öneri onaysızdır. Backup kopyası user export değildir. `ACTIVE` veya `HOLD`
durumundaki kopya süre doldu diye silinmez.

| Kopya sınıfı | İçeriğe izin | TTL / bütçe | Süre başlangıcı ve istisna |
|---|---|---|---|
| Tam backup içindeki chat ve ekran | [ ] dahil et · [ ] hariç tut · [ ] karar yok | ______ gün / ______ byte | __________________ |
| Backup arşivleri | [ ] 30 gün/1 GiB adayını kabul et · [ ] değiştir · [ ] ertele | ______ gün / ______ byte | __________________ |
| Restore-check ağacı | [ ] kabulden sonra 30 gün adayını kabul et · [ ] değiştir · [ ] ertele | ______ gün | Kabul makbuzu/owner: __________________ |
| `ACTIVE` / `HOLD` / unknown kopyalar | [ ] Hold zorunlu · [ ] başka | Hold'u kaldırabilecek owner: __________________ |

Backup/restore copy silme kapsamı, onaylı süre, sahip ve envanter makbuzu
olmadan otomatikleştirilmez. Restore eski silinmiş içeriği geri getirebilir;
restore öncesi veya sonrası suppression/tombstone kuralı: ____________________

## 4. Kullanıcı export'u

Bugünkü panel `/api/veri` tail'i ve CLI görüntüleme komutları tam/tarih filtreli
kullanıcı export'u değildir. Export kabul edilirse her artifact yeni ve hassas
bir kopyadır.

| Seçim | Karar |
|---|---|
| Export yetkisi | [ ] veri sahibi · [ ] kurulum operatörü · [ ] başka: __________ · [ ] ertele |
| Seçilebilir kapsam | [ ] chat · [ ] ekran/kimlik · [ ] tarih aralığı · [ ] ikisi · [ ] başka: __________ |
| Snapshot tutarlılığı | [ ] ortak lock ile snapshot · [ ] partial olabilir, açıkça işaretlenir · [ ] ertele |
| Gerekli manifest | [ ] aralık, sınıf, schema ve kayıt/byte sayısı · [ ] redaction sürümü · [ ] bütünlük özeti · [ ] başka: __________ |
| Redaction | [ ] güncel redaction sonrası · [ ] legacy raw içerik ayrıca işaretlenir · [ ] içerik export'u kapalı · [ ] karar yok |
| Hedef ve izin | [ ] kullanıcı seçer · varsayılan mode: ______ · [ ] başka: __________ |
| Export TTL / bütçesi | ______ gün / ______ byte · owner: __________________ |
| Partial/read/permission/limit hatasında | [ ] `partial` ve neden sun · [ ] export'u reddet · [ ] ertele |

Export'a karar verilmesi bugünkü tail/CLI çıktısını export olarak sunma izni
vermez; ayrı kabul edilmiş akış gerekir.

## 5. Silme, kopyalar ve talep durumu

Bugünkü ürün yüzeyinde güvenli per-record veya workspace delete aracı yoktur.
JSONL satırları elle düzenlenmez. Bu bölüm politika yönünü seçer; uygulama ve
doğrulama tamamlanmadan kullanıcıya silme garantisi verilmez.

| Karar alanı | Seçim / sahibi |
|---|---|
| Kullanıcı silme isteği alındığında | [ ] yetkili talep olarak kaydet ve beklet · [ ] ürün kapsamı dışında olduğunu açıkça bildir · [ ] başka: __________ |
| Silme kapsamı | [ ] kayıt · [ ] kişi/kimlik · [ ] tarih aralığı · [ ] tüm yerel workspace · [ ] henüz kararlaştırılmadı |
| Birincil aktif/arşiv segment | [ ] kontrollü segment migration + audit tasarla · [ ] ertele |
| Backup / restore-check / export / cache / index kopyaları | [ ] envantere ekle; kopya başına sonuç bildir · [ ] başka: __________ |
| Legal/incident hold | [ ] hold sahibi ve gözden geçirme tarihi gerekir · [ ] başka: __________ |
| Silme kanıtı | [ ] kopya envanteri ve fiziksel sonuç makbuzu · [ ] yalnız mantıksal gizleme (silme diye adlandırılmaz) · [ ] ertele |
| Backup restore sonrası silme | [ ] tombstone/suppression olmadan restore canlıya açılmaz · [ ] başka: __________ |

Talep sahibi için izin verilen ifade (yalnız kanıtlanan kapsamı yazın):
___________________________________________________________________________

Tamamlanmış silme yalnız birincil dosya değil; archive, backup, export,
restore-check, cache/index ve hold kopyalarının her biri için sonuç bilindiğinde
raporlanabilir. `unknown`, erişilemeyen immutable backup veya açık hold,
tamamlandı beyanını engeller.

## 6. Uygulamaya geçiş kapısı ve onay

Retention cleanup / export / delete özelliğini etkinleştirme kararı ayrı
uygulama ve kabul gerektirir. Tüm maddeler tamamlanmadıysa durum **karar
bekliyor; otomatik cleanup kapalı** kalır.

- [ ] Süreler, disk sınırları ve hangi sınırın önce geldiği owner tarafından onaylandı.
- [ ] Salt-okunur hacim envanteri içerik toplamadan ölçüldü; eşikler bu ölçüme göre kabul edildi.
- [ ] Aktif segment, ortak lock, writer/reader uyumu, restart/rollback ve fail-closed hata halleri fixture ile kabul edildi.
- [ ] Dry-run raporu silinecek path, yaş, byte, kayıt sayısı, hold ve erken silme etkisini gösteriyor; veri değiştirmiyor.
- [ ] Backup kapsamı/TTL, restore suppression, export kopya TTL'si ve purge makbuzu kararlaştırıldı.
- [ ] Incident/legal hold owner'ı, kaldırma koşulu ve gözden geçirme tarihi belirlendi.
- [ ] Kullanıcıya verilecek export/delete ifadesi gerçekten kanıtlanabilen sonucu aşmıyor.
- [ ] Ayrı uygulama sahibi, rollout, rollback ve kabul kaydı belirlendi.

**Karar:** [ ] Onayla — belirtilen kapsam/sürümle ayrı uygulamaya geçilebilir
[ ] Koşullu — açık koşullar: ______________________________________________
[ ] Ertele — neden ve yeniden görüşme tarihi: ______________________________

İmza / kayıt ref'i: ______________________________  Tarih: ______________

## Kaynaklar ve bu formun sınırı

- `docs/chat-screen-retention-export-delete-matrix-629.md` — veri sınıfları,
  mevcut export/delete sınırı ve birincil/backup kopya etkileşimi.
- `docs/local-data-retention-export-deletion-policy-546.md` — yerel MVP
  politikası; 90g/7g/30g adayları ve onaysızlık.
- `docs/jsonl-retention-design.md`,
  `docs/jsonl-storage-operator-decisions-496.md` — segment, arşiv bütçesi,
  disk dolması ve transition adayları.
- `docs/restore-check-retention-policy-530.md` — `ACTIVE/HOLD/ACCEPTED/ELIGIBLE/DELETED`
  ve kabulden sonra restore-check ömrü önerisi.
- `docs/credential-exposure-incident-runbook-585.md` — incident hold ve
  kopyalara erişimi kısıtlama.

Form hiçbir TTL'yi onaylamaz, veri içeriğini incelemez, backup açmaz, dosya
silmez/taşımaz, retention mekanizması etkinleştirmez veya mevcut üründe
user-facing export/delete özelliği varmış izlenimi vermez.
