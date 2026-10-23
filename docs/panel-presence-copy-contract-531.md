# Panel presence metinleri için kanıt sözleşmesi (#531)

**Durum:** salt-okunur UI/API kaynak karşılaştırması ve önerilen metin seti.
UI, API, kod, test, runtime veya canlı istek değiştirilmedi/çalıştırılmadı.

## API'nin mevcut kanıtı

`panel/server.py:1476-1500` kullanıcı snapshot'ında `son_gorulme` ve
`son_kalp` alanlarını `null`, `online=false`, `presence_state="unknown"` ve
`presence_verified=false` verir; `online_sn` TTL değerini ayrı sunar. Yorum,
G1/W1b broker kanıtı olmadan persisted presence alanlarının doğrulanmış aktör
kanıtı olmadığını belirtir. Bu nedenle mevcut API sözleşmesi hiçbir kullanıcıyı
doğrulanmış online veya offline yapmaz; kayıtlı `bagli`, ekran/sohbet hareketi
ve `son_okuma` presence veya teslim receipt'i değildir.

`panel/ui.html:515-530` online etiketini yalnız `online=true`,
`presence_verified=true`, `presence_state="online"`, geçerli TTL ve gelecekte
olmayan taze `son_kalp` birlikteyken verir. Panel fetch hatası yeşili kapatır.
Offline etiketi yalnız `presence_verified=true` ve açık `presence_state="offline"`
ile gelir; diğer durumlar unknown'dur. Fakat bu offline dalı kanıt zamanını/
yaşını kontrol etmez. #482'nin belirttiği gibi API'ye offline evidence zamanı,
kaynağı ve freshness kuralı eklenmeden eski doğrulanmış offline kaydı güncelmiş
gibi süresiz gösterilebilir. Mevcut snapshot her kullanıcıyı unknown verdiği
için bu risk şimdiki API cevabında tetiklenmiyor.

## Görünüm karşılaştırması

| Görünüm | Kaynak ve mevcut ifade | Değerlendirme |
|---|---|---|
| Üst ekip özeti (`ui.html:573-586`) | Online sayısını, online yoksa ayrıca verified-offline ve unknown adetlerini sayar. Panel hatasında presence doğrulanamıyor der. | API ile uyumlu; online yok demek offline demek değildir ve sayımlar bunu açıklar. |
| Ekip sekmesi (`ui.html:598-603`) | `Ekip · Yuva presence: N çevrimiçi` yazar; `N=0` olduğunda offline/unknown kırılımı yoktur. | Açıkça “çevrimdışı” iddia etmez, fakat ekip ekranı kapalıyken `0` nedenini ayırt ettirmez. Üst özetteki breakdown ile aynı metin sözlüğünü kullanmıyor. |
| Model kartı (`ui.html:745-771`) | Ortak `onlineEtiketi()` çevrimiçi, çevrimdışı veya durumu doğrulanamıyor der; panel hatasında panel bağlantısı doğrulanamıyor der. | Online ve unknown ayrımı API ile tutarlı. Offline etiketi ileride ancak offline freshness alanı geldikten sonra güncel durum olarak kullanılmalı. `son_gorulme` çevrimiçi kanıtına çevrilmiyor. |
| Ekip boş/katlanır durumları (`ui.html:821-850`) | Kayıt yoksa “Yuva’da kayıtlı model yok”; online yoksa verified offline ve unknown adetleri ayrı belirtilir, kartlar ayrılabilir. | API başarılıysa kayıt yok ifadesi doğru; durum breakdown'ı tutarlı. Unknown/offline kayıtların gizli olması sayaçları etikette tutuyor. |
| Sohbet hedef seçimi ve kayıt şeridi (`ui.html:605-621,2160-2187`) | Normal durumda yalnız doğrulanmış-online bireysel hedefler seçilebilir; panel hatasında eski hedef bilinmiyor etiketiyle kalabilir. Kaydedilen mesajın ardından online hedef sayısı ve agent/session receipt olmadığı belirtilir. | Presence ile Yuva mesaj kaydını ayırır; kayıt şeridi teslim/okunma iddiası değildir. `@hepsi` hedefi mesajın her agente teslim edildiği anlamına gelmez. |
| Sohbet `son_okuma` özeti (`ui.html:662-688,703-725`) | Zaman eşiğinin mesaj zamanını kapsayıp kapsamadığını sayar; kapsam dışı için “okuma durumu bilinmiyor”, ayrıca “agent receipt doğrulanmadı” der. | Yuva read watermark'ını agent receipt olarak sunmaması doğru. Presence sayımı ayrı ek bilgidir. |
| Ekran boş durumu (`ui.html:1888-1894,1920-1928`) | Ekran kaydı yokken “Henüz ekrana çıktı yok; çevrimiçi durumu doğrulanamıyor” der. | **Metin uyumsuzluğu:** panel API presence alanlarını ayrı döndürür. Ekran satırı yokluğu presence'i doğrulanamaz yapmaz; kayıtlı model online olabilir veya presence unknown olabilir. Ekran verisi yokluğu ile presence durumunu birleştiriyor. |
| Ekran hedef seçeneği (`ui.html:1822-1828`) | Her online olmayan model `⚪` alır; offline/unknown ayrımı seçenek metninde bulunmaz. | Kartlar ayrımı gösterse de açılır seçenek tek bakışta iki kanıt durumunu birleştiriyor. Panel hatasında `⚪ ?` kullanımı daha açık. |
| Panel verisi yok (`ui.html:558-568,802-818`) | Ekip, ekran ve harita için panel bağlantı hatasını ve snapshot/veri belirsizliğini yazar; son snapshot gösterilse de online rengi bastırılır. | Fail-closed API/UI sözleşmesi ile tutarlı. “Model yok” yerine “veriye erişilemiyor” denmesi doğru. |

## Önerilen ortak metin sözlüğü

UI metinleri presence için şu dört sonucu ortaklaştırmalı; sayım metni de aynı
sözlüğü kullanmalıdır:

| Kanıt sonucu | Önerilen kısa etiket | Kullanım koşulu |
|---|---|---|
| Doğrulanmış, taze online | `Yuva presence · çevrimiçi` | API'nin online, verified, açık online state ve taze/non-future heartbeat koşullarının tümü geçer. Yeşil yalnız burada. |
| Doğrulanmış offline | `Yuva presence · doğrulanmış çevrimdışı` | Açık verified offline kanıtına ek olarak API'nin tanımlı offline evidence zamanı/kaynağı/freshness sözleşmesi geçer. Bu sözleşme henüz yok; şu an bu etiket güncel durum olarak üretilemez. |
| Diğer/eksik/stale/çelişkili | `Yuva presence · durumu doğrulanamıyor` | `online=false`, missing field, yanlış TTL, eski/gelecek heartbeat, unsupported schema, provider/broker belirsizliği veya çelişki. |
| Panel/API verisi yok | `Panel bağlantısı yok · presence doğrulanamıyor` | Fetch/API hatasında. Eski snapshot gösteriliyorsa ayrıca `son snapshot` denir; snapshot'tan yeşil türetilmez. |

Önerilen kullanıma hazır metinler:

- **Ekip sayacı:** `Ekip · 2 çevrimiçi · 1 doğrulanmış çevrimdışı · 3 durumu doğrulanamıyor`. Her sayı sıfırsa da gerekiyorsa göster; `0 çevrimiçi` tek başına offline anlamına gelmez.
- **Online yok:** `Doğrulanmış çevrimiçi model yok · X doğrulanmış çevrimdışı · Y durumu doğrulanamıyor`. Mevcut API'de X sıfır, Y tüm kayıtlı modellerdir.
- **Model kartı:** ortak etiket fonksiyonunu koru; offline etiketini yalnız offline freshness kararı sonrası etkinleştir.
- **Sohbet kaydı:** `Mesaj Yuva sohbetine kaydedildi; presence hedef sayısı N çevrimiçi. Agent/session teslim veya okuma receipt'i doğrulanmadı.` Bireysel hedefte mesajın kaydı hedefe teslim edildi anlamına gelmez.
- **Ekip listesi boş:** `Yuva’da kayıtlı model yok.` Yalnız geçerli API snapshot'ında `kullanicilar` gerçekten boşsa.
- **Ekran kaydı boş:** `Henüz ekran kaydı yok.` Presence gerekiyorsa ayrıca ortak presence etiketi/count'u göster; ekran yokluğundan presence sonucu çıkarma.
- **Panel hatası:** `Panel verisi alınamıyor; presence doğrulanamıyor.` Kullanıcı/ekip listesi önceki snapshot'tan gösteriliyorsa bunun eski olduğu belirtilir.
- **Ekran hedefi:** `🟢 ad · çevrimiçi`, `⚪ ad · doğrulanmış çevrimdışı`, `⚪ ad · durumu doğrulanamıyor`; panel fetch hatasında `⚪ ad · panel bağlantısı doğrulanamıyor`.

## Kapsam ve dayanak

Bu not UI değişikliği talimatını uygulamaz; yalnızca copy tutarsızlığını ve
önerilen sözlüğü belgeler. #482 mevcut CLI/UI/API fail-closed kurallarını ve
offline freshness boşluğunu; #494 TTL aşımı, broker/provider belirsizliği ve
panel kesintisinin unknown kalması gerektiğini açıklar.

- `panel/server.py:1476-1500` — `/api/veri` snapshot alanları ve sabit unknown.
- `panel/ui.html:515-530,556-603` — online/offline/unknown reducer, özet ve
  ekip sekmesi metni.
- `panel/ui.html:605-621,662-725,2160-2187` — hedef seçimi, `son_okuma`
  kapsamı ve mesaj kaydı sonrası şerit.
- `panel/ui.html:745-850,1822-1828,1888-1928` — model/ekip kartları, ekran
  seçeneği ve boş durumlar.
- `docs/panel-presence-evidence-review-482.md` — API/UI/CLI kanıt eşlemesi ve
  offline evidence freshness boşluğu.
- `docs/panel-presence-source-options-494.md` — TTL/kopma/replay belirsizliği
  unknown olmalı; TTL tek başına verified offline değildir.
