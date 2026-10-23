# Yuva JSONL okuyucu envanteri

## Kapsam ve sonuç

Bu envanter, Yuva'nın kalıcı `mesaj.jsonl` ve `ekran/*.jsonl` dosyalarını okuyan
CLI ve panel yollarını eşler. Projedeki bu okuyucuların hiçbiri bounded-tail
değildir: önce tüm dosya `read_text()` ile belleğe alınır, sonra tüm metin
`splitlines()` ile satırlara bölünür ve ancak bundan sonra satır sayısı dilimle
sınırlandırılır. Dolayısıyla satır sayısı sınırlı görünse de okuma belleği dosya
boyutuyla büyür.

Bu not yalnız mevcut okuma davranışını ve sınırlı-bellekli okuyucu için temas
noktalarını kaydeder. Retention, rotation ve dosya ömrü #440 kapsamındadır; bu
belge disk saklama politikasını seçmez.

## Kalıcı JSONL okuma yolları

| Yol | Kaynak ve çağıran | Satır sınırı nerede? | Bellek ve davranış |
|---|---|---|---|
| CLI sohbet okuyucusu | `bin/yuva:445-498` `mesajlar(n, filtre)`; `yuva oku` bunu `cmd_oku` içinden çağırır (`bin/yuva:1567-1573`). | `read_text().splitlines()` sonrasında fiziksel satırların son `3*n` adedi seçilir; JSON parse ve zarf normalizasyonundan sonra `n` kayıt döndürülür. `yuva oku --n` varsayılanı 20'dir (`bin/yuva:2164`). `bana_gelen` 400 adayı, `gelen` ayrıca 120 adayı okur (`bin/yuva:501-506,1589-1592`). | Streaming yok. Tepe geçici bellek en az tüm dosyanın metni ve tüm satırların bölünmüş string'lerini içerir; dilim yalnız bu tahsisten sonra yapılır. Ardından en çok `3*n` aday JSON nesneye çevrilir. Fiziksel dosya baytı ve tek satır uzunluğu sınırsızdır. Okunamayan dosya hatası burada yakalanmaz; geçersiz JSON ve nesne olmayan satırlar atlanır. |
| CLI ekran okuyucusu | `bin/yuva:1377-1402` `cmd_ekran_oku`; `yuva ekran oku` veya `yuva ekran --from ...` okuma yolu. | Dosya başına `splitlines()` sonrası son `a.n` satır seçilir; varsayılan `--n 30` (`bin/yuva:2124-2131`). | Her dosya tam okunup bölünür. Kimlik filtresi tek dosyaya iner; filtresiz kullanım önce bütün `*.jsonl` yollarını `sorted()` ile listeye alır, sonra dosyaları birer birer işler. Bu nedenle tepe dosya-içeriği belleği en büyük tek ekran dosyasıyla, yol listesi belleği dosya adediyle; seçilen satır/JSON nesneleri `n` ile büyür. JSON hatalı satırlar sessizce atlanır. |
| Panel sohbet okuyucusu | `panel/server.py:522-581` `mesajlar(n=MESAJ_SN)`; `veri()` bu fonksiyonu `/api/veri` snapshot'ına ekler (`panel/server.py:936-969`). | `MESAJ_SN=200` olduğundan önce dosyanın tamamı bölünür, sonra son 600 fiziksel satır seçilir (`panel/server.py:51-53,522-570`). Parse ve provenance normalizasyonu ardından sonuç son 200 kayda kesilir. | Streaming yok; geçici bellek tüm `mesaj.jsonl` boyutuyla büyür. Snapshot adedi 200 olsa da kayıt baytları sınırlandırılmamıştır. Okuma/Unicode hatası boş mesaj listesine döner; JSON hataları atlanır. |
| Panel ekran okuyucusu | `panel/server.py:592-608` `tum_ekranlar()`; `veri()` `/api/veri` yanıtına dönen eşlemeyi ekler (`panel/server.py:936-969`). | Her ekran dosyası için tüm metin bölündükten sonra son 60 fiziksel satır seçilir (`EKRAN_SN=60`, `panel/server.py:53,596-603`). | Dosyalar streaming yerine sıralı glob listesiyle keşfedilir. Her dosyanın tamamı ayrı ayrı belleğe alınır; o anki dosyada tepe geçici bellek en büyük dosyanın boyutuyla büyür. Ayrıca seçilmiş/parse edilmiş en çok 60 kayıt **her dosya için** `out` içinde tutulur; ekran dosyası adedi ve her kaydın boyutu sınırsızdır. Dosya okuma/parse sorunları boş sonuçla veya sessiz atlamayla görünmez kalabilir. |

### Limitlerin anlamı

- `n*3`, `n` ve `EKRAN_SN` satır sayısı limitidir; bayt, karakter veya JSON nesne
  boyutu limiti değildir.
- Satır dilimi tam dosya metni ve tam satır listesi oluşturulduktan sonra
  uygulanır. Bu yüzden dosya büyümesini veya dev bir tek satırı sınırlamaz.
- `3*n` mesaj adayı, hatalı/eski/filtre dışı kayıtları tolere etmek için okunan
  fiziksel satır penceresidir; dosya boyutuna göre bellek üst sınırı sağlamaz.
- Panel ekranlarında 60 satır her dosya/kimlik için tutulur. Kimlik/dosya sayısı
  için limit bulunmadığından toplam snapshot kaydı da sabit bir sayıyla
  sınırlanmaz.
- `errors="replace"` kullanımı geçersiz UTF-8 baytlarını `U+FFFD` ile değiştirir;
  bu, ham kaydın bire bir teşhisi için yeterli değildir. `splitlines()` da
  dosyanın son LF ile bitip bitmediğini kaybettirir. Bu gözlem #441'deki kuyruk
  kurtarma sözleşmesiyle ilgilidir; bu envanterde onarım yapılmaz.

## Okuma dışındaki ilişkili yollar

- Panel `/api/veri` tek snapshot üretir; `mesajlar()` ve `tum_ekranlar()` sonucu
  diğer durum/görev alanlarıyla birleştirir (`panel/server.py:936-969`).
  `H._gonder()` dict/list yanıtını önce tam JSON string'ine, sonra UTF-8 byte
  gövdesine dönüştürür (`panel/server.py:1088-1103`). Bu, JSONL okuyucu
  belleğine ek olarak toplam snapshot boyutuna bağlı kopyalar oluşturabilir.
- `bin/yuva` ve `panel/server.py` içindeki `read_text()` çağrılarının diğer
  örnekleri durum/görev JSON'u, UI HTML'i veya `/proc` metnidir; bunlar kalıcı
  Yuva JSONL okuyucusu değildir (`bin/yuva:102-119,647,783,2043`,
  `panel/server.py:164-175,983-985`). HTTP POST gövdesi JSON'dur, JSONL okuması
  değildir.
- `prototypes/codex-app-server/adapter.py` stdin'den satır-temelli JSON-RPC
  protokolü işler; Yuva'nın sohbet/ekran JSONL arşivini okumaz ve bu envanterin
  dışındadır.

## Güvenli bounded-tail için temas noktaları

1. Ortak bir byte-tail okuyucu belirle: önce dosyayı açıp tek file descriptor
   üzerinden inode ve başlangıç boyutunu sabitle; sondan bloklar okuyarak
   istenen sayıda **tam LF satırını** geriye doğru bul. Eşzamanlı append ve
   rotation/truncate halinde hangi snapshot'ın okunacağı açıkça tanımlansın.
2. Salt satır adedi sert bellek sınırı vermez. Maksimum taranacak bayt ve
   maksimum kayıt baytı da belirlenmeli; limit aşılırsa dev satırı sessizce
   parse etme, `record_too_large`/`scan_limit` gibi görünür bir sonuçla dön.
   Bozuk LF'siz kuyruk davranışını #441 sözleşmesine uydur.
3. CLI sohbet noktası `mesajlar()`; CLI ekran noktası `cmd_ekran_oku()`;
   panel noktaları `mesajlar()` ve `tum_ekranlar()`dır. Bu dört okuyucu aynı
   sınır/bozulma sonucunu kullanmalı. `cmd_oku`, `bana_gelen` ve `gelen` gibi
   tüketicilerin mevcut kayıt sayısı/filtre beklentileri korunmalı.
4. Panel ekran keşfinde `sorted(EKRAN.glob(...))` tüm yol listesini üretir.
   Sert toplam sınır isteniyorsa dosya sayısı da sınırlanmalı veya akış halinde
   dolaşılmalı; `/api/veri` hâlâ tüm ekran kimliklerini ve seçilen satırları
   topluca döndürdüğünden toplam kayıt/byte bütçesi ayrıca uygulanmalı.
5. API snapshot serileştirmesi de sınırlı yanıt bütçesi veya akışlı yazım
   gerektirir; yalnız diskten tail okumak, model başına ekran sayısı ve JSON
   response kopyaları nedeniyle toplam HTTP bellek sınırını tek başına
   kanıtlamaz.

Bounded-tail, eski kayıtları silmez veya arşiv boyutunu küçültmez. Diskteki
   retention/rotation politikası ayrı bir karar ve uygulama konusudur (#440).

## Kaynaklar

- `bin/yuva:445-498,501-506` — sohbet JSONL okuyucusu ve büyük aday penceresi.
- `bin/yuva:1567-1597,2124-2131,2164` — sohbet tüketicileri ve varsayılan
  satır limitleri.
- `bin/yuva:1377-1402` — ekran JSONL dosyası keşfi, tam okuma ve son-n dilimi.
- `panel/server.py:51-53,522-581` — panel satır limitleri ve sohbet okuyucusu.
- `panel/server.py:592-608,936-969` — ekran okuyucusu ve birleşik API snapshot'ı.
- `panel/server.py:1088-1103` — bütün snapshot için JSON string/byte yanıt üretimi.
