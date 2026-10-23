# Release öncesi güvenlik ve veri kapsamı — operatör karar formu (#617)

**Kural:** Bu form her release/host için ayrı doldurulur. Başlangıç ve eksik
kanıt durumu **NO-GO**'dur. Her zorunlu kapının kanıt referansı ve sahibi
yazılmadan, herhangi bir kapı `UNKNOWN` iken veya risk kabulü imzalanmamışken
GO verilemez. Bu form kaynak/fixture bulgularını host kanıtı yerine koymaz.

## Release ve karar sahipleri

| Alan | Doldurulacak değer |
|---|---|
| Host/instance etiketi | ______________________________________________ |
| Release ID / commit / payload SHA-256 | ______________________________________________ |
| INSTALL_ROOT / `current` target | ______________________________________________ |
| `YUVA_DIR` (mutlak, gerçek yol) | ______________________________________________ |
| Operatör / veri sahibi | ______________________________________________ |
| Güvenlik kabul sahibi | ______________________________________________ |
| Kanıt paketi URI/yolu ve tarih | ______________________________________________ |
| Değerlendirme tarihi | ______________________________________________ |

## Bilinen karar girdileri

- **Anonim snapshot:** `GET /`, `/index.html`, `/api/veri` ve `/veri` şu an
  anonimdir. Snapshot roster, görevler ve geçmiş notları, son 200 sohbet kaydı
  ve ekran satırlarını içerebilir. `no-store`, loopback, Host/Origin veya CORS
  bu içeriğe erişen okuyucuyu doğrulamaz. Kaynak değerlendirmesi varsayılan
  tam anonim snapshot'ı **NO-GO** sayar. (#574, #608)
- **Same-UID sınırı:** Aynı OS UID'deki yerel agent/process'ler birbirinden
  HTTP veya dosya izinleriyle ayrılmış sayılmaz. Loopback, aynı namespace'teki
  farklı UID'lere de erişim sınırı oluşturmaz. Auth kapalı POST gövdesindeki
  `kimden`/`kimlik` ve CLI `--from` doğrulanmış actor değildir. (#574, #576)
- **Browser/auth kapsamı:** Kaynakta browser session ve CSRF entegrasyonu
  yoktur. `YUVA_AUTH_ENABLED=1` HMAC POST kapısını açar; anonim GET/HTML'yi
  kapatmaz. #608'in hedef browser kabulü dört GET/HTML yolu ve 11 POST yolunu
  route başına session/scope/CSRF veya kapalı-route davranışıyla sınar; mevcut
  kaynak bu kabulü geçmiyor. HMAC istemcisi browser session değildir. (#583,
  #608)
- **Son kayıtlı host envanteri:** #598'de user unit `inactive/dead`, görünür
  Yuva process'i yok, PATH CLI ve unit kaynakları mutable `yuva-v2`,
  `~/.local/opt/yuva/current` yok, `YUVA_DIR=<YUVA_DATA_ROOT>` idi.
  Bu, 2026-10-23 tarihli gözlemdir; çalışan process/namespace'i kanıtlamaz ve
  sonraki bir release için güncel kabul kanıtı değildir. Release kurulumu
  kararı o bulguda **NO-GO** idi. (#598)
- **Backup authenticity:** Adjacent `.sha256` yalnız arşiv ile sidecar'ın
  yerel tutarlılığını gösterir. #616'daki `--expected-sha256` eşleşmesi
  bağımsız olarak güvenilen bir kaynaktan alınmış digest ile karşılaştırma
  sağlar; araç digest'in kaynağını doğrulamaz. Trust anchor ayrıca
  kanıtlanmadıkça rapor `authenticity: unverified` kalır. Verify ve scratch
  restore-check de authenticity veya etkin veriye restore izni değildir.
  (#565, #616)

## Zorunlu karar kapıları

Her satır için tek bir durum işaretleyin. `PASS` yanında kanıt referansı ve
kanıtı toplayan kişi yazılmalıdır. `FAIL`, boş veya `UNKNOWN` sonuç NO-GO'dur.

| Kapı | PASS | FAIL | UNKNOWN | Kanıt referansı / sahip / tarih |
|---|:---:|:---:|:---:|---|
| **1. Snapshot okuyucuları:** tam roster/task/chat/screen verisini görebilecek tüm HTTP, browser, agent ve yerel process okuyucuları envanterlendi; yetkisiz okuyucu yok veya bu erişim veri sahibi tarafından açıkça kabul edildi. | [ ] | [ ] | [ ] | ______________________________ |
| **2. Same-UID kabulü:** aynı UID içindeki tüm süreçler bu veriyi okuyup mevcut auth-off yüzeyde işlem yapabilecek güven sınırında; veya untrusted process'i engelleyen OS/namespace/broker sınırı negatif testle kanıtlandı. | [ ] | [ ] | [ ] | ______________________________ |
| **3. Ağ ve proxy:** etkin bind, port, network namespace, tunnel/reverse-proxy ve backend bypass yolları doğrulandı; loopback'in authentication olmadığı kabul edildi. | [ ] | [ ] | [ ] | ______________________________ |
| **4. Browser GET/HTML:** `/`, `/index.html`, `/api/veri`, `/veri` için session/scope kapısı uygulanıp kabul edildi; ya da yalnız insan-only istisnasının erişim koşulları ve snapshot riski kanıtlanıp imzalandı. Kaynakta mevcut anonim davranış tek başına PASS değildir. | [ ] | [ ] | [ ] | ______________________________ |
| **5. Browser POST/auth:** 11 POST route için session, route policy, CSRF, auth-off fail-closed ve proxy/backend bypass kontrolleri geçildi; kapalı route'lar kapalı kaldı. Browser dışı HMAC kapsamı ayrı tutuldu. | [ ] | [ ] | [ ] | ______________________________ |
| **6. Release kimliği:** temiz kaynak commit/tree, dış kanaldan pinlenmiş manifest digest'i, payload hash'leri, immutable release ve `current` doğrulandı. | [ ] | [ ] | [ ] | ______________________________ |
| **7. PATH/unit/process eşleşmesi:** PATH CLI, kurulu unit `ExecStart`/`WorkingDirectory`, etkin CLI/panel process executable/cwd ve `current` aynı release'e çözüldü. Unit dosyası tek başına çalışan process kanıtı sayılmadı. | [ ] | [ ] | [ ] | ______________________________ |
| **8. Veri kökü ve writer:** CLI/panel aynı mutlak `YUVA_DIR` kullanıyor; gerçek dizin, owner/mode/link ve release root'tan ayrılık doğrulandı; etkin ve eski/dev writer'ların yokluğu veya yazamaması kanıtlandı. | [ ] | [ ] | [ ] | ______________________________ |
| **9. Veri kapsamı:** roster/rol/organizasyon alanları, görev serbest metni/geçmişi, chat ve screen içerikleri için hedef okuyucu ve kabul edilen hassasiyet kayda alındı. Gereksiz alanlar anonymized response'tan çıkarıldı veya erişim sınırı uygulandı. | [ ] | [ ] | [ ] | ______________________________ |
| **10. Backup integrity/authenticity:** etkin `YUVA_DIR` dışında backup, format/şema verify ve ayrı scratch restore-check kanıtlandı; authenticity gerekiyorsa expected digest'in backup yazma alanından bağımsız kaynağı ve custody'si belgelendi. | [ ] | [ ] | [ ] | ______________________________ |
| **11. Rollback/şema:** hedef release ve manifest pini doğrulandı; veri şeması eski release ile uyumlu; rollback kod/pointer değişimi ile veri restore'unun ayrı işlemler olduğu kabul edildi. | [ ] | [ ] | [ ] | ______________________________ |
| **12. MVP semantiği:** `--from`/`kimden` verified actor sayılmıyor; presence `unknown`; mesaj kaydı agent teslim makbuzu değil; provider dispatch/credential/approval ve otomatik scheduler kapalı. | [ ] | [ ] | [ ] | ______________________________ |

### İnsan-only istisnası (kullanılacaksa ayrıca doldur)

Bu istisna yalnız tek operatörün kullandığı, untrusted agent/browser
extension/diğer kullanıcı process'lerinin panel HTTP yüzeyine erişemediği
host/namespace için düşünülebilir. Aynı UID process'lerine karşı izolasyon
kanıtı yoksa operatör bunların tamamını tam snapshot verisine erişebilen
trusted boundary olarak kabul ettiğini açıkça imzalamalıdır. İstisna,
route/session testlerini geçmiş gibi göstermez.

- [ ] İnsan-only erişim sınırı process/namespace/HTTP negatif testleriyle kanıtlandı.
- [ ] Same-UID süreçleri trusted boundary olarak kabul edildi ve tam snapshot içeriği onaylandı.
- [ ] İstisna kabul edilmiyor veya koşulları bilinmiyor → **NO-GO**.

Kanıt referansı: ______________________________  Sorumlu: __________________

### Backup pin ve authenticity kararı

- Arşiv digest'i: ______________________________
- `--expected-sha256` kullanıldı mı? [ ] Evet  [ ] Hayır
- Digest'in arşiv/sidecar'dan bağımsız kaynak ve custody kanıtı: ______________________________
- Sonuç (yalnız biri): [ ] `unverified` kabul edildi  [ ] bağımsız anchor kanıtlandı
  [ ] gerekli authenticity kanıtlanmadı → **NO-GO**
- Integrity/şema verify makbuzu: ______________________________
- Scratch restore-check makbuzu ve hedef: ______________________________

## Kalan `UNKNOWN` / risk kaydı

Her satıra çözüm sahibi ve kapatma kanıtı yazın. Kayıt yoksa `Yok` yazıp
operatör paraflasın; boş bırakmayın. Her açık veya kabul edilmemiş risk NO-GO'dur.

| Unknown/risk | Etki ve neden açık | Sahip | Kapatma kanıtı / karar |
|---|---|---|---|
| Process/namespace ve same-UID okuyucu görünürlüğü | __________________ | __________ | __________________ |
| Gerçek browser/session/auth modu ve route kapsamı | __________________ | __________ | __________________ |
| Proxy/tunnel/backend bypass | __________________ | __________ | __________________ |
| Güncel release, PATH, unit, çalışan process ve eski writer'lar | __________________ | __________ | __________________ |
| Gerçek `YUVA_DIR`, sahiplik, şema ve rollback uyumu | __________________ | __________ | __________________ |
| Backup digest provenance/custody ve restore kararı | __________________ | __________ | __________________ |
| Diğer | __________________ | __________ | __________________ |

## Operatör kararı ve imzalar

Zorunlu kapıların tümü `PASS`, kanıtlar bu release/host'a bağlı ve açık
unknown/risk yoksa tek operatörlü yerel MVP kapsamında **GO** seçilebilir.
Başka her durumda karar **NO-GO**'dur. GO, çok kullanıcı/uzak erişim,
doğrulanmış actor veya presence, provider dispatch ya da otomatik görev
çalıştırma yetkisi vermez.

- Karar: [ ] **GO**  [ ] **NO-GO** (form eksikse NO-GO varsayılır)
- Kapsam dışı kalan risklerin açık kabulü / gerekçe: ______________________________
- Release sorumlusu imza: ______________________________  Tarih: ______________
- Veri sahibi imza: ____________________________________  Tarih: ______________
- Güvenlik kabul sahibi imza: __________________________  Tarih: ______________
- Karar kaydı / kanıt paketi: ___________________________________________________

## Kaynak kararlar

- [#574 — Anonim panel snapshot veri minimizasyonu](panel-anonymous-snapshot-data-minimization-574.md)
- [#576 — Yerel MVP release Go/No-Go matrisi](local-mvp-release-go-no-go-matrix-576.md)
- [#583 — Browser GET/HTML session kapsamı](browser-session-read-scope-583.md)
- [#598 — Runtime kökleri salt-okunur envanteri](runtime-roots-inventory-598.md)
- [#608 — Browser session/CSRF route kabul matrisi](browser-session-route-acceptance-matrix-608.md)
- [#565 — Backup authenticity trust anchor kararı](backup-authenticity-trust-anchor-565.md)
- [#616 — Backup expected-digest prototipi](backup-expected-digest-cli-616.md)
- [#604 — Operatör kabul ve rollback checklist'i](operator-acceptance-rollback-checklist-604.md)

Bu belge önceki kararları tek forma toplar; host ayarı, service, browser
session, veri veya backup değiştirmez. Fixture GO'su host GO'su değildir.
