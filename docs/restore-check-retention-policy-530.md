# #530 — `restore-check.*` doğrulama artığı saklama ve temizlik politikası

Tarih: 2026-10-23
Durum: Operatör politikası önerisi; uygulanmadı. Bu çalışma statik envanterdir.
Dosya/arşiv silme, taşıma veya değiştirme; arşiv açma/restore; test ve runtime
yapılmadı.

## Kapsam ve gözlem

Politika yalnız `<YUVA_DATA_ROOT>-yedek/restore-check.*` kontrol ağaçlarını
kapsar. Eşleşen `yuva-*.tar`, `.tar.list` ve `.tar.sha256` dosyalarının saklama
süresi bu notla değiştirilmez; kontrol ağacını temizlemek yedeği silme izni
değildir.

Statik envanterde iki klasör bulundu:

| Klasör | Gözlenen zaman | Gözlenen içerik ve izin |
|---|---|---|
| `restore-check.T4hbP8` | 2026-10-19 | Açılmış `yuva/` ağacı; `kaynak.acl`, `geri-yuklenen.acl`, xattr raporları. Kök klasör `0700`; ACL rapor dosyaları `0644`. |
| `restore-check.XOeUcj` | 2026-10-20 | Açılmış `yuva/` ağacı; ACL/xattr raporları. Kök klasör `0700`; ACL rapor dosyaları `0644`. |

İki ağaçta da `yuva/bin/yuva` SHA-256 değeri
`90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05`; bu,
#515'teki `<YUVA_DATA_ROOT>/bin/yuva` hash'iyle aynı. Bu, yalnız o CLI
dosyasının bayt eşitliğini gösterir; hangi arşivden açıldığını, bütün ağacın
özdeşliğini veya güncel/kanonik kaynak olduğunu kanıtlamaz. Klasörlerde arşiv
adı/hashini ve doğrulama sonucunu bağlayan manifest/işaret dosyası
gözlenmemiştir. Tarih ve rastgele klasör eki tek başına arşiv kökeni kanıtı
değildir.

Kontrol ağaçları Yuva görev/mesaj/durum ve presence kayıtlarının kopyalarını,
CLI/panel kaynaklarını, heartbeat/lock dosyalarını ve ACL raporlarını içeriyor.
Bu nedenle `restore-check` geçici çalışma alanı olsa da sıradan, hassasiyetsiz
cache sayılmamalıdır. `0700` kök erişimi sınırlar; içte `0644` görülen raporlar
klasör taşınır veya daha geniş izinli bir köke kopyalanırsa aynı korumayı
sağlamaz.

## Saklama kararı

Önerilen varsayılan ömür, **restore karşılaştırması tamamlanıp sonucu operatörce
kabul edilen tarihten itibaren 30 takvim günüdür**. Gün sayımı klasörün mtime'ı
veya oluşturulma zamanı yerine kabul kaydının zamanından başlar. Bu süre, hata
araştırması ve yeniden inceleme için kısa bir geri dönüş penceresi bırakır;
kurumsal/legal saklama zorunlulukları varsa onların yerini almaz.

Şu koşullardan biri varsa klasörün süresi dolmuş sayılmaz ve temizliğe uygun
değildir:

- restore kontrolü başarısız, eksik, kesilmiş veya sonucu bilinmiyor;
- klasörün hangi backup archive ve checksum'a ait olduğu güvenilir biçimde
  bağlanmamış;
- olay/incident incelemesi, tekrar doğrulama veya açık saklama talebi sürüyor;
- klasörün canlı bir kontrol/inceleme sürecince kullanılıp kullanılmadığı
  bilinmiyor;
- kabul zamanı, sahibi veya görev/olay referansı kaydedilmemiş.

30 günlük varsayılan, başarılı ve kaydı tamamlanmış kontrol ağacı için temizlik
uygunluk eşiğidir; otomatik silme talimatı değildir. Operatör, uzatma kararını
gerekçe ve yeni gözden geçirme tarihiyle kaydetmelidir. Geçersiz/başarısız bir
kontrol için sınırsız saklama da hedeflenmez; düzeltme veya açık incident-owner
kararı gerekir.

## Kaynak ve hash bağı

Yeni oluşturulacak her kontrol klasörü için klasörden ayrı, erişimi daraltılmış
bir envanter kaydı önerilir. Kayıt en az şunları birbirine bağlamalıdır:

- kontrol klasörünün tam adı ve canonical backup-root altındaki yolu;
- kaynak veri kökünün canonical yolu ve doğrulama anındaki kaynak kimliği;
- ilgili arşivin tam adı, byte boyutu ve SHA-256 değeri; hash'in hangi
  `.sha256` sidecar'ından geldiği ve arşiv checksum doğrulamasının sonucu;
- arşiv member-list dosyasının adı ve hash'i;
- ilgili CLI/kod kaynağının seçilmiş commit/tree bilgisi varsa bu provenance;
  yoksa `unknown` ve dosya bazlı hash envanteri. CLI hash'i tek başına kaynak
  provenance'ı sayılmaz;
- kontrol script/prosedürü sürümü ya da hash'i;
- karşılaştırma, ACL ve xattr sonuçları (`pass`, `fail`, `not_run`); operatör,
  başlangıç ve kabul zamanları; saklama bitişi ve varsa incident/hold referansı.

Archive digest'i yanında kontrol ağacı içeriğinin kanıtı gerekirse, hassas
verinin kendisini kopyalamadan kanonik relative path/type/mode/size/hash
manifest'i kullanılabilir. İçerik hashleri de veri türevi hassas metadata
olabileceğinden yalnız dar yetkili envanterde tutulmalı; genel loga yazılmamalı.
Eksik manifest, eşleşmeyen archive digest veya sonradan değişmiş dosya
`unknown`/hold durumudur; isim/tarih sezgisiyle bağ kurulmaz.

## Aktif kullanım etiketi

Her klasöre envanterde şu yaşam döngüsü etiketlerinden biri verilsin:

| Etiket | Anlam | Temizlik |
|---|---|---|
| `ACTIVE` | Backup açma, karşılaştırma veya inceleme devam ediyor | Yasak |
| `HOLD` | Hata, eksik provenance, incident veya bilinmeyen kullanım durumu | Yasak |
| `ACCEPTED` | Sonuç kabul edildi; 30 günlük saklama penceresi başladı | Tarih dolmadan yasak |
| `ELIGIBLE` | Saklama süresi doldu, açık hold yok ve aktif kullanım kontrolü geçti | Operatör onayıyla mümkün |
| `DELETED` | Tam yol ve içerik envanteri doğrulanarak temizlik tamamlandı | Makbuz tutulur |

İlk envanterdeki iki klasör için güvenilir kabul kaydı ve archive bağlantısı
gözlenmediğinden, politika uygulanacak olsaydı etiketleri `HOLD/unknown` olurdu.
Mtime'ın eski olması, klasörün artık kullanılmadığını kanıtlamaz. `ACTIVE`
işaretini yalnız operasyonu başlatan iş akışı koyup, karşılaştırma ve kabul
makbuzu tamamlanınca kaldırmalıdır; bu etiketleme bu görevde yapılmadı.

## Güvenli temizleme kapısı

Temizlik öncesinde operatör şu koşulların tümünü doğrulamalıdır:

1. Hedef canonical path, beklenen backup root'un doğrudan altında ve tam olarak
   `restore-check.<suffix>` biçiminde bir dizindir; symlink veya root dışına
   yönlenen hedef kabul edilmez.
2. Envanter kaydı klasörü tek bir arşiv digest'ine ve tamamlanmış, kabul edilmiş
   doğrulama sonucuna bağlıyordur; 30 günlük kabul sonrası süre dolmuştur.
3. Klasör `ACTIVE`/`HOLD` değildir; çalışan kontrol/inceleme sürecinin cwd,
   açık dosya tanıtıcısı veya mount referansı olarak kullanılmadığı operatörce
   doğrulanmıştır. Yalnız yaş/mtime bu kontrolün yerine geçmez.
4. Temizlenecek tam klasör adı, boyutu ve envanter kaydı silme öncesi gözden
   geçirilmiştir. Wildcard ile tüm `restore-check.*` dizinlerini toplu silme
   yapılmaz; her klasör ayrı değerlendirilir.
5. Arşiv ve gerekli `.tar.list`/`.tar.sha256` saklama kararı ayrıdır. Kontrol
   klasörü temizliği bu dosyalara veya kaynak veri köküne dokunmaz.
6. İşlem sonrası envanterde `DELETED`, işlem zamanı, operatör, tam yol, bağlı
   arşiv digest'i ve gerekçe append-only temizlik makbuzu olarak kaydedilir.

İzin metadata'sı hassas olduğundan, gelecekte üretilecek ACL/xattr raporlarının
da özel erişimli kontrol kökü içinde kalması ve rapor dosyalarının koruyucu
modda oluşturulması önerilir. Mevcut ACL raporlarının modunu değiştirmek bu
görevin kapsamında değildir.

## Uygulanabilirlik ve sınırlar

`docs/linux-gecis.md` kontrol akışı `restore-check.XXXXXX` dizini yaratır,
arşivi oraya açar, kaynak/geri yüklenen ağaç, ACL ve user xattr karşılaştırması
yapar. Örnek akışta kontrol klasörünü otomatik temizleyen bir adım görünmüyor;
bu, bilerek saklama kararı alındığını kanıtlamaz. `<YUVA_DATA_ROOT>-yedek`
içindeki `.tar` arşivleri ve sidecar'lar statik envanterde listelendi; arşiv
içerikleri açılmadı veya okunmadı.

Bu politika yeni metadata üretimi, izin değişikliği, hash manifesti oluşturma,
aktif süreç incelemesi veya temizlik yapmaz. Operatör 30 günlük pencereyi,
backup saklama politikasını ve yetkili onay sahibini kabul etmeden mevcut iki
klasörün silinmesi önerilmez.

## Kaynaklar

- `docs/linux-gecis.md` — backup doğrulama ve `restore-check.*` üretim akışı.
- Yuva #515 teslim/revizyon kayıtları, `<YUVA_DATA_ROOT>/gorevler.json` —
  CLI kopyası SHA-256 değerleri ve kaynak/provenance sınırları.
- `docs/cli-copy-release-manifest-contract-522.md` — source commit/tree,
  payload hash ve release provenance ayrımı.
- Statik dosya envanteri: `<YUVA_DATA_ROOT>-yedek/restore-check.T4hbP8/`
  ve `<YUVA_DATA_ROOT>-yedek/restore-check.XOeUcj/`; yalnız path, mode,
  boyut, timestamp ve `yuva/bin/yuva` SHA-256 gözlendi.
