# Anonim panel snapshot'ı için veri minimizasyonu kararı (#574)

**Tarih:** 2026-10-23
**Durum:** İlk yerel MVP için karar revizyonu; varsayılan tam anonim snapshot **NO-GO**. Anonim GET veya servis ayarı değiştirilmedi.
**Kapsam:** `GET /api/veri` ve alias `/veri` tarafından dönen roster, görev, sohbet ve ekran alanlarının amaç, hassasiyet ve erişim ihtiyacı.

## Karar özeti

İlk MVP'de tam anonim snapshot varsayılan olarak **açık kalmamalıdır**. `/api/veri` yalnız roster metadata'sı değil; tüm görev nesnelerini, son 200 chat kaydını ve ekran çıktısını verir. Chat/agent içeriği güvenilmeyen olabilir. Bu içerikle çalışan agent süreçleri aynı UID/network namespace altında panelin loopback GET'ine erişebiliyorsa, onları güvenilir saymak doğru değildir: aynı kimlik sınırında GET snapshot'ı okuyabilir ve auth kapalı POST yüzeyine kendi gövdeleriyle istek gönderebilirler. Gövde `kimden`/`kimlik` alanları gerçek çağıranı doğrulamaz. Kaynakta HTTP peer UID/broker doğrulaması yoktur.

Loopback bind, Host/Origin denetimi, CORS, `no-store` ve dosya izinleri bu kabulün yerine geçmez. Farklı UID'li bir süreç de aynı network namespace'te localhost'a erişebilir; aynı UID process'lerini ayıran bir kapı hiç yoktur. `YUVA_AUTH_ENABLED=1` mevcut GET yollarını kapatmaz; mevcut HMAC POST gate de browser için session veya same-UID agent izolasyonu değildir.

Bu nedenle **kaynak incelemesi GO vermez**. Kullanıcı mesajlarını işleyen agent'lar aynı yerel erişim alanında çalışmaya devam ederken tam anonim snapshot **NO-GO**'dur; yalnız tek bir insanın kullandığı özel mod ayrı bir deployment kararı olabilir. Bu belge yalnız kararı ve ölçütleri tanımlar; canlı servisi veya erişim ayarını doğrulamaz.

## Snapshot alanlarının sınıflandırılması

| Grup / alanlar | Amaç ve UI ihtiyacı | Hassasiyet | Anonim GET değerlendirmesi |
|---|---|---|---|
| `kullanicilar`: `kimlik`, `ad`, `arac`, `rol`, `bas_denetci`, `sorumlu_kimlik`, `katilma` | Ekip, görev yönlendirme ve hiyerarşiyi çizmek; görev/mesaj hedeflerini göstermek. Mevcut UI `kimlik/ad/arac/rol`, `bas_denetci` ve `sorumlu_kimlik` kullanır; `katilma` şu an kullanılmıyor. | Orta: gerçek kişi olmasa bile çalışma kimlikleri, araç ve iç organizasyon ilişkileri. | Temel alanlar UI için gerekli. `katilma` düşük etkili çıkarılabilir adaydır. Gizli erişim sınırı değildir; kalan alanların herkese açık sayılması gerekir. |
| `kullanicilar.son_okuma`, `bagli` ve presence alanları | Okunma eşiği/rozet ve durum açıklaması. Kaynak `son_gorulme`/`son_kalp` değerlerini `null`, presence'ı `unknown`, doğrulanmış online'ı `false` yapar. | Düşük/orta operasyonel metadata. `son_okuma` davranış zamanı gösterebilir. | `son_okuma` bazı mesaj rozetleri için kullanılır. `bagli` UI'da kullanılmıyor ve presence kanıtı değildir. Unknown/null alanları gerçek zamanlı kimlik veya varlık bilgisi gibi sunulmamalı. |
| `kullanicilar.not_` | Profil notu. İncelenen panel UI bunu okumuyor. | Yüksek/öngörülemez: serbest metin kişisel veya kurumsal bilgi içerebilir. | Anonim snapshot'tan çıkarılması düşük etkili en küçük veri azaltımıdır; görev/chat/screen erişimini güvenli yapmaz. |
| `gorevler` | Tahtada iş akışı, atama ve inceleme; kartlar `baslik`, `detay`, aktör/assignee/reviewer, durum, parent ve `gecmis` olay/notlarını gösterebilir. | Orta-yüksek: çalışma planı ve serbest metin; geçmiş notları ek bilgi/sır içerebilir. | Ürün akışı için gerekli, ancak toplu görev nesnelerinin tümü tek yanıtta anonim okunur. Kartta gizlemek API yetkisini azaltmaz. |
| `mesajlar` | Son en çok 200 JSONL kaydı; UI sohbet ve mesaj/okuma durumunu işler. Alanlar kimlik/hedef, zaman, tür ve serbest metin içerir; okuma görünümü provenance/trust alanlarını da taşır. | Yüksek: konuşma içeriği, kişisel bilgi, kullanıcı tarafından yapıştırılmış sır ve güvenilmeyen talimat metni barındırabilir. | Son 200 ve ham tail/record byte limitleri hacmi sınırlar; kimin okuyabileceğini sınırlamaz. Tam metin anonim snapshot'ta yüksek riskli alandır. |
| `ekranlar` | Kaydedilmiş terminal/ekran satırlarını UI'da gösterme. | Çok yüksek: komut çıktısı, dosya yolu, kişisel bilgi veya gerçek credential içerebilir. Redaksiyon başarı iddiası değildir. | Mevcut satır/dosya/byte limitleri hacmi ve kaynak yükünü sınırlar; erişim kontrolü veya bütün sırların silindiği kanıtı değildir. Anonim tam snapshot'ın en hassas gruplarındandır. |
| `ekranlar_meta` | `partial`, dosya/byte sayaçları, limitler ve kısmi sonuç nedenleri. | Düşük/orta operasyonel metadata. | İçerik taşımasa da sistem boyutu/iş yükü hakkında bilgi verir; public cevapta bunun da görünür olacağı kabul edilmeli. |
| `ok`, `simdi`, `online_sn`, `rev` | API/UI yenileme, görünüm ve sürüm/zaman göstergesi. | Düşük operasyonel metadata. | Kimlik doğrulaması veya yetki kanıtı değildir; gerekiyorsa azaltılabilir fakat ana veri riskini çözmez. |

Sınıflandırma kaynak kodu ve mevcut UI kullanımına dayanır; gerçek içerik dosyaları okunmamış, canlı snapshot çağrılmamıştır.

## Seçenekler

| Seçenek | MVP etkisi | Kabul koşulu / sınır |
|---|---|---|
| **A — Yerel-only tam anonim snapshot (istisna)** | Mevcut tek fetch ve UI akışı korunur; roster, görev, sohbet ve ekran aynı yanıtta kalır. | Yalnız insan kullanımına ayrılmış host/namespace'te ve loopback'e erişebilen hiçbir untrusted agent/browser eklentisi/başka kullanıcı süreci olmadığının operatörce kanıtlandığı özel modda değerlendirilebilir. Agent'ların aynı UID altında bu GET'e erişebildiği biliniyorsa A reddedilir. |
| **B — Anonim özet, hassas içerik ayrı** | Anonim cevapta gerekiyorsa küçük ve düşük hassasiyetli health/roster özeti kalır; chat metni, ekran satırları, görev detayı/serbest metni ve ayrıntılı geçmiş dışarıda tutulur. | Veri ifşasını azaltır ama `POST /api/gorev`, chat/profile/role yazımları auth kapalıysa ayrı risk olarak kalır. Agent kaynaklı mutasyon kabul edilmiyorsa B tek başına GO vermez; yazma rotalarını da kapatmak/korumak gerekir. |
| **C — GET ve POST için doğrulanmış erişim sınırı** | Hassas snapshot ve mutasyonlar yalnız yetkili browser oturumu veya güvenilir broker üzerinden sunulur. | GET alias'ları ve HTML erişimi dahil exact read policy; POST auth/policy; browser session/CSRF/logout; same-UID agent'lar tehdit modelindeyse ayrı UID broker ve process erişimi kapısı gerekir. Broker anahtarı agent'a verilmemeli. Mevcut HMAC POST gate tek başına yeterli değildir; MVP öncesi ayrı tasarım/uygulama ve kabul gerekir. |

## Önerilen en küçük daraltma ve GO/NO-GO

Öneri **A'yı varsayılan yapmamak**. Agent'ların same-UID loopback'e erişebildiği ürün düzeninde uygulanabilir alt sınır C'dir. Tam GET auth/broker henüz yoksa MVP, hassas alanları anonim `/api/veri` yanıtına vermeden ve auth kapalı task/chat/role mutation rotalarını açmadan hizmete çıkmamalıdır. B geçici bir veri-azaltım basamağı olabilir; fakat açık yazma rotaları için ayrıca kapı ister. A yalnız agent çalıştırmayan, açıkça insan-only kabul edilmiş ayrı host/namespace moduna istisna olarak düşünülebilir.

Kod değişikliği gereken ilk daraltmada UI tarafından kullanılmayan roster `not_`, `katilma` ve `bagli` alanlarını; null dönen `son_gorulme` ve `son_kalp` alanlarını snapshot'tan çıkarmak düşük etkili bir ek azaltımdır. Bu yüksek hassasiyetli görev, chat veya ekran içeriğini korumaz ve route erişim kontrolünün yerine geçmez.

**GO** için operatör/release kabulü şu kanıtları birlikte kaydetmelidir:

1. Çalışan CLI/panel release yolu ve hash'leri onaylı tek release ile aynı; etkin `YUVA_DIR` ayrı ve tek sahipli.
2. İnsan-only A istisnası isteniyorsa agent/tool süreçleri panel endpoint'ine erişemiyor olmalı; aynı UID'de yalnız process düzeyinde söz kalmamalı, host namespace/launcher kısıtı test ve işletim sahibi kanıtıyla gösterilmelidir. Kanıt yoksa A reddedilir.
3. C için `/api/veri`, `/veri`, `/`, `/index.html` ve tüm hassas GET alias'ları aynı yetkilendirme modeline bağlanmalı; POST task/chat/profile/role/ekran rotaları da verified principal/policy olmadan mutasyon yapmamalıdır.
4. Browser key'i paylaşılmaz. Doğrulanmış browser session/CSRF/logout veya agent'ı dışarıda bırakan ayrı UID broker tasarımı ve revocation/expiry yaşam döngüsü kabul edilir.
5. Roster/task/chat/screen alanlarının hedef okuyucuları ve `not_`, serbest görev notları, son 200 chat ile ekran satırlarının hassasiyeti veri sahibince kabul edilir; gerekmeyen alanlar anonime açılmaz.
6. Snapshot azaltımı uygulanırsa birlikte dağıtılan UI eksik veriyi tam görev/ekip listesi, offline durumu veya yetki kanıtı gibi yorumlamaz.

**NO-GO**: Agent/tool süreçleri aynı UID veya loopback alanında çalışıyor ve anonymous GET/legacy POST'a ulaşabiliyorsa; hassas chat/ekran/task içeriğinin bu süreçlere açılması kabul edilmiyorsa; doğrulanmış browser/GET auth veya broker yoksa; host erişim kanıtı, release/veri kökü, revoke veya session kapsamı belirsizse tam anonymous snapshot hizmete alınmaz. **Mevcut çok-agent same-UID kullanım varsayımında karar NO-GO'dur.** İnsan-only A istisnası ayrıca deployment kanıtı ve açık operatör kararı ister.

## Dayanak ve sınırlar

- `panel/server.py:862-920` — mesaj tail/record limitleri ve provenance görünümü.
- `panel/server.py:1011-1158` — ekran map'i, redaksiyon sonrası satırlar, kısmi sayaçlar ve dosya/bayt limitleri.
- `panel/server.py:1600-1628` — `veri()` roster projeksiyonu ve birleşik snapshot alanları.
- `panel/server.py:1847-1859, 1949-1966` — anonymous GET yönlendirmesi ve loopback bind sınırı; HTTP peer UID denetimi yok.
- `panel/ui.html` — `kullanicilar`, `gorevler`, `mesajlar` ve `ekranlar` kullanım yüzeyleri; `not_` için tüketim yok.
- `docs/panel-local-security-snapshot-557.md`, `docs/local-api-get-snapshot-decision-455.md`, `docs/panel-api-route-scope-matrix-526.md`, `docs/first-local-mvp-scope-go-no-go-536.md`.

Bu not statik kaynak ve önceki karar belgeleriyle sınırlıdır. Auth/route/UI kodu, servis, canlı snapshot veya host ayarı değiştirilmedi; gerçek erişim topolojisi doğrulanmadı.
