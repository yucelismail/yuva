# JSONL arşivleme ve saklama: operatör karar listesi (#496)

**Durum:** karar özeti; uygulama veya operatör onayı değildir. Aşağıdaki
konularda kaynak belgeler sayı ve süreleri onaylamaz. Bu not yeni eşik,
retention süresi veya yetkili rol belirlemez.

| Karar konusu | Henüz seçilmesi gereken | Seçeneklerin etkisi / kaynak sınırı |
|---|---|---|
| Paylaşılabilir kayıt içeriği | Mesaj ve ekran JSONL için yazma öncesi ortak redaksiyonun zorunlu kılınıp kılınmayacağı; belirsiz sınıflandırmada reddetme davranışı | #465, ortak akışta yazma öncesi redaksiyon ve belirsiz kaydı fail-closed reddetmeyi önerir. Redaksiyon geçmiş kayıtları veya yedekleri geriye dönük temizlemez; tam DLP garantisi değildir. |
| Ham inceleme kanıtı | Ayrı ham artifact deposuna ihtiyaç, okuyucu yetkisi, erişim kaydı, saklama/silme, yedekleme ve anahtar sahipliği | Varsayılan öneri ham değeri ortak JSONL’ye koymamaktır. Ayrı depo yeni hassas veri yüzeyi açar; #465 bunu tek başına yetkilendirmez. Gerekçe ve kontroller karara bağlanmadan açılmamalı. |
| Aktif segment ve kayıt sınırları | Mesaj/ekran segment boyutu, yaşla rotation ve tek satır sınırları | #449/#`jsonl-retention-design.md` içindeki değerler adaydır; ölçüm ve operatör kabulü olmadan etkinleştirilmiş politika sayılmaz. Daha sık rotation arşiv sayısını, daha büyük eşikler disk tepesini etkiler. |
| Arşiv retention ve dolu disk | Yaş/bütçe önceliği, minimum yaş garantisi, bütçe dolduğunda eski arşivi silme veya yeni yazmayı durdurma | Yaş ve toplam bütçe birlikte uygulanırsa kayıt süre dolmadan silinebilir. Minimum yaş isteniyorsa ek disk veya yazmayı reddetme seçilmelidir. Kaynaklar bu ürün tercihini çözmüyor; otomatik silme açılmamalı. |
| Ekran kimliği görünürlüğü | API’de hangi kimliklerin gösterileceği ve “en yeni” seçiminin güvenilir metadata kaynağı | #449’daki son etkin kimlik sınırı öneridir. `last_append_at` manifesti, dayanıklılığı ve yazıcıyla tutarlılığı tanımlanmadan dosya sırasından “en yeni” çıkarılamaz. Sınır uygulanırsa atlanan kimlikler görünür raporlanmalı. |
| Yedek kapsamı ve yaşam döngüsü | Mesaj/ekran logları yedeğe alınacak mı; hedef erişimi, şifreleme, ömür, bütçe, silme ve restore kanıtı | Tam KOK yedeği JSONL’leri de kopyalar; dışlamak kopya riskini azaltır, kurtarılabilir geçmişi azaltır. #449’daki yedek değerleri de onaysız başlangıç önerileridir. Yedekler dahil tüm kopyalar aynı hassasiyet sınıfında ele alınmalı. |
| Dosya/operatör erişimi | Farklı UID, aynı UID süreçleri, tarayıcı/panel ve host/yedek yöneticisi için kabul edilen güven sınırı; arşiv/manifest izinleri | #465’e göre `0700/0600` farklı UID erişimini sınırlar; aynı UID süreçlerini birbirinden ayırmaz. Loopback de kimlik doğrulama değildir. Bu sınır yeterli değilse süreç/UID izolasyonu ve panel erişim politikası ayrıca seçilmeli. |
| Bozuk kuyruk ve kurtarma | Son LF’siz kuyruk veya bozuk satırda yazma/temizlik durdurma, alarmı kimin inceleyeceği ve yeni kopya kurtarma onayı | #450 hedefi ham veriyi korumak, `degraded` uyarısını görünür kılmak ve operatör kararı olmadan append, truncate, birleştirme veya silme yapmamaktır. Mevcut okuyucu/yazıcıların bu hedefi uyguladığı varsayılamaz. |
| Silme denetimi ve sıkıştırma | Silme olayının içeriksiz metadata’sı/hedefi/erişim sınırı; ilk sürümde arşiv sıkıştırmasının kapsamı | İçerik kopyalayan audit hassas veriyi yeniden üretir; tarih, kayıt/byte adedi, politika sürümü ve sonuç gibi metadata seçenekleri değerlendirilmelidir. Kaynak taslak sıkıştırmayı ertelemeyi önerir; seçilirse geçici dosya, checksum, rename/fsync ve hata kurtarma ayrıca kararlaştırılmalı. |
| Okuma ve kesilme bildirimi | CLI/API byte-kayıt bütçeleri, kısmi sonucun etiketi ve hata yanıtı | Taslak limitler onaylanmış değer değildir. Limit aşımı `truncated`/`omitted` benzeri açık metadata ile boş/eksiksiz sonuçtan ayrılmalı; okuma veya bütünlük hatası sessiz boş başarı olmamalı. |

## Karar kaydı ve etkinleştirme kapısı

Her satır için sistem sahibi/operatör seçimi, gerekçe, politika sürümü ve
karar tarihi kaydedilmelidir; mevcut kaynaklar karar merciini isimlendirmiyor.
Kararlar ve gerçek veri hacmi doğrulanmadan retention silmesi etkinleştirilmemeli.
Önce salt-okunur envanter ve dry-run çıktısı incelenmeli; yedek/restore yolu,
izinler, okuyucu-yazıcı uyumluluğu ve bozuk kuyruk durdurma davranışı kabul
edilmelidir. Silme sonucu belirsizse tekrar silme yerine envanter uzlaştırılmalı.

Bu belge otomatik silme kodu, arşivleme uygulaması, ölçüm veya test içermez.
Mevcut JSONL’de redaksiyon/retention garantisi bulunduğu iddiası değildir.

## Kaynaklar

- `docs/jsonl-retention-operator-decisions-449.md` — eşikler, yedek, disk
  dolması, audit, rollout ve rollback için açık operatör kararları.
- `docs/jsonl-tail-recovery-compatibility-450.md` ve
  `docs/jsonl-tail-recovery.md` — mevcut okuyucu/yazıcı farkı ile bozuk kuyrukta
  koruma ve operatör kontrollü kurtarma hedefi.
- `docs/jsonl-redaction-policy-adr-465.md` ve
  `docs/jsonl-redaction-boundary.md` — yazma öncesi redaksiyon önerisi, ham
  kanıt deposunun ayrı kararı, erişim sınırı ve geçmiş kopyaların durumu.
- `docs/jsonl-retention-design.md` — başlangıç tasarımı; ölçüm/karar olmadan
  kabul edilmiş saklama politikası değildir.
