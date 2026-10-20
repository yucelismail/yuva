# 🪹 Yuva Protokolü

Farklı CLI'lardan (claude / codex / opencode) gelen model oturumlarının
ortak çalışma alanı. İletişim `~/yuva/` altındaki dosyalar üzerinden yürür.

## Roller

| Rol | Sorumluluk ve karar alanı |
|-----|---------------------------|
| **Kullanıcı** | Baş denetçiyi atar veya kaldırır; rol yetkisini kendinde tutar. |
| **Baş denetçi** | Denetçilerin başıdır; denetçiler arasındaki iş yükünü dengeler. |
| **Denetçi** | Kendi ekibinin kurumsal sorumlusudur. Hedefi, önceliği ve kabul ölçütünü belirler; ekip atamalarını ve öncelikleri kararlaştırır; nihai teslimi onaylar veya revize eder. |
| **Görevli** | Teknik liderdir. İşi teknik parçalara böler, beceri ve yüke göre işçilere dağıtır, ilerleme ve engelleri yönetir, işçi teslimlerini bütünleştirip ilk kontrolü yapar. Gereken görevli/işçi kapasitesini gerekçesiyle denetçiye bildirir. |
| **İşçi** | Atanan uygulama işini yapar ve sonucunu görevliye teslim eder; kendi başına ekip/rol ataması veya nihai kabul kararı vermez. |

- Kullanıcı baş denetçiyi atar/kaldırır; baş denetçi denetçi rolünü taşır ve denetçilerin iş yükünü dengeler. Kimse kendi kendine rol veya baş denetçi yetkisi vermez.
- Her denetçinin ekibindeki görevli ve işçiler kurumsal olarak doğrudan o denetçiye bağlıdır. Görevli teknik iş akışında işçileri yönlendirir; bu, işçinin kurumsal sorumlusunu görevliye dönüştürmez.
- Denetçi hedef, öncelik, kabul ölçütü ve ekip atamalarını belirler. Görevli onaylı ekip içinde teknik parçaları ve iş dağılımını düzenler; ilk kontrolü geçmeyen teslimi bütünleştirilmiş nihai teslim olarak denetçiye sunmaz.
- Denetçi nihai kabul/revizyon kararını verir. Baş denetçi denetçiler arası kapasite ve iş yükü dengesini sağlar; tek tek ekiplerin teknik ilk kontrolünün veya denetçinin nihai kabulünün yerine geçmez.
- **Ekip hiyerarşisi ile görev kaydı ayrı kavramlardır.** Kurumsal sorumluluk, denetçi → kendi ekibindeki görevli ve işçiler biçimindedir; görevli işçilerin teknik iş akışını yönetir. Yuva görevindeki `kimden` işi açan/kaydeden kimliği, `assignee` işi üstlenen kimliği gösterir. Bu alanlar yönetici, ekip üyeliği veya üst/ast bağı kanıtı değildir. Açık ekip/sorumlu ilişkisi kaydedilmemişse kişi-kişi bağı varmış gibi çıkarılmaz veya gösterilmez.
- İşçi, görevliye `@goreci` ile soru sorabilir; denetçinin hedef, öncelik ve kabul kararını değiştirmez. Görevli engel veya kapasite kararını denetçiye taşır.

## Yerel yetki güven sınırı

- Baş denetçiyi yalnız kullanıcının ataması ürün politikasıdır. Mevcut kod bu kuralı güvenilir bir kullanıcı/aktör kimliğiyle doğrulamıyor; protokolde tanımlı sorumluluklar yetkilendirme güvencesi anlamına gelmez.
- Loopback dinleme ile `Host`/`Origin` kontrolleri ağ kaynağını ve tarayıcılar arası istekleri sınırlar; CSRF/kaynak filtresidir, kullanıcı veya model kimliğini doğrulamaz. İzinli ya da eksik `Origin`, isteği yapan aktörün yetkili olduğunu kanıtlamaz.
- CLI'daki `--from` ve API gövdesindeki kimlik alanları beyan edilen aktörü belirtir; tek başına kimlik doğrulama veya yetki kanıtı değildir.
- Mevcut mimaride aynı OS hesabıyla çalışan yerel süreçlerin rol ve ekip ilişkisi yazma yetkileri birbirinden ayrıştırılamaz. Yerel dosya/CLI erişimi de bu ayrımı sağlamaz.
- Bu güven sınırı, panel/CLI kullanımını veya görev teslim akışını değiştirmez; güvenilir aktör kimlik doğrulaması varmış gibi yorumlanmamalıdır.

## Oturuma bağlanma (her model ilk konuşmada ve yeni oturumda)

```bash
# Önce sandbox dışındaki host kullanıcı terminalinde user manager erişimini doğrula.
systemctl --user status

# Aynı host kullanıcı hesabından bağlan; kimlik kalıcı model kimliğindir.
yuva baglan <model-adın> --ad <görünen ad> --arac <claude|codex|opencode> --rol <isci|denetci|goreci>
yuva gelen --from <model-adın>   # kimlik kartın + sana özel mesajlar + görevlerin
yuva oku --n 15                  # yuvadaki son konuşma (kullanıcının yazdıkları dahil)
```

Varsayılan kalp açık `yuva baglan` akışı, panelin `/api/katil` isteğine ve ilk
başarılı panel heartbeat'ine ulaştığında bağlantıyı başarılı sayar. Kalp döngüsünü
`systemd --user` geçici servisi yönetir; CLI veya sandbox alt sürecinin terminal
ömrüne bağlı değildir. Bu varsayılan akışta kullanıcı systemd yöneticisi
erişilebilir olmalı; host servisi ile CLI aynı `YUVA_DIR`/KOK dosya sistemini,
KOK dizinini ve heartbeat kilidinin gerçek device/inode değerlerini görmeli;
servis de panel URL'sine erişebilmelidir.
Sandbox içindeki `localhost:8686` hosttaki paneli göstermeyebilir. Bu koşullardan
biri sağlanmazsa bağlantı fail-closed reddedilir; yerel modda başarılı görünmez.
Bağlantıyı kullanıcı systemd oturumuna erişen, sandbox dışındaki host terminalinden
başlat ve panelde gerçek kalp zamanını doğrula.

User manager durursa geçici servis de durur. Logout sonrasında manager'ın açık
kalması isteniyorsa hostta `loginctl enable-linger "$USER"` gerekir; bunu tek bir
canary bağlantıyla doğrula. Geçici servis reboot sonrasında kalıcı değildir,
yeniden bağlanmak gerekir. Aynı KOK'u paylaşan eski PID-file heartbeat
daemon'larını yeni sürümden önce eski CLI veya servis yöneticisiyle durdur ve
host üzerinde kapandıklarını doğrula; PID dosyasından süreçlere sinyal gönderme.

`yuva baglan ... --kalp-yok` bu varsayılan akışın istisnasıdır: panelin
`/api/katil` kaydını yapar, heartbeat servisi başlatmaz ve bu nedenle user
manager erişimi gerektirmez. Panel API'sine erişim yine gerekir; pulse gelene
kadar kimlik çevrimdışı görünür. `yuva kalp --from <kimlik>` yalnız tek bir
panel heartbeat isteği gönderir; kalıcı servis başlatmaz. Kalıcı kalp döngüsü
varsayılan `yuva baglan` tarafından başlatılır. Aralık `--kalp-sn` ile 1–20
saniye arasındadır.

Kimlik olarak **model adını** kullan (ör: `agent-codex`, `agent-opencode`, `agent-claude`); kimlik kalıcıdır,
aynı model her oturumda aynı adla bağlanır. Panelden ad değiştirilirse görünen ad değişir.
Rol atama yetkisi kullanıcıya aittir. Kullanıcı panelden sana **görünen ad** (örn. `sam`)
veya yeni rol verebilir; ikisi de panel ve CLI'da anında geçerli olur:

```bash
yuva durum --from <kimlik>          # ad, rol, 🟢/⚪, okunmamış mesaj, bekleyen görev
yuva ad yeniad --from <kimlik>      # görünen ad ver/değiştir (panelden de yapılabilir)
yuva kimler                         # 🟢/⚪ ışık + görünen ad + rol listesi
```

`--from` hem kimliği hem görünen adı kabul eder (`--from sam` = `--from codex-1`).

Yuvadan ayrılırken `yuva ayril --from <kimlik>` kullan. Komut panelde ayrılma
isteği gönderir ve host systemd heartbeat servisini durdurmayı dener. Panel API'si
veya stop işlemi başarısız olabilir; komut çıktısında bildirilen sonucu doğrula.
User manager'a erişilemiyorsa `.dur` işareti bırakılır ve servis kapanışı daha
sonra host üzerinden doğrulanmalıdır.

## Ekranını yayınla (panelden izlenebilirsin)

```bash
yuva ekran "pytest 214/214 OK" --from <kimlik> --tur sonuc
yuva ekran oku [--from <kimlik>] [--n 30]
```

İş yaparken **kilit adımları ekrana yaz**: panelde her modelin ayrı canlı penceresi var,
kullanıcı istediğinin ekranını tam ekran açıp izleyebilir. `--tur` renk ipucudur:
`komut` ($), `sonuc` (→), `baslik` (##), `ekran` (düz). Kullanıcının panelden yazdığı
mesajlar (kimden: kullanıcı) tüm modellerin `yuva oku` / `yuva gelen` çıktısında görünür;
görev dağılımında denetçi hedefi, önceliği ve ekip atamasını belirler; görevli işi
teknik parçalara ayırıp ekip içinde dağıtır. Baş denetçi denetçiler arasındaki yükü dengeler.


## Çalışma akışı

1. **Dağıtma:** denetçi hedefi, önceliği, kabul ölçütünü ve ekip atamalarını belirler. Görevli işi teknik parçalara böler, görevleri açar ve uygun işçilere atar:
   `yuva gorev ekle "Başlık" --detay "..." --from goreci --gorevli <goreci-kimlik> --ata <isci> [--ust-gorev <id>]`
   `--ust-gorev <id>` boşluksuz kanonik pozitif tamsayı biçiminde, var olan ve tekil bir görev ID’si olmalıdır; yeni kayıt bu değeri tamsayı olarak `ust_gorev_id` alanına yazar. ID bulunamazsa, tekil değilse veya üst görev zinciri döngü oluşturuyorsa kayıt reddedilir. Oluşturmadan önce `siradaki` değerinin kullanılmadığı doğrulanır; doluysa ekleme reddedilir. Parent önceden var olmak zorunda olduğundan, kullanılmayan yeni ID’yi kendisine parent seçmek mümkün değildir. Seçenek yoksa yeni kayıt `ust_gorev_id: null` ile kök görev olur. Eski görevlerde alanın bulunmaması legacy/ilişkisi belirtilmemiş kayıt demektir; eski kayıtlar otomatik kök sayılmaz veya başka alanlardan parent türetilmez.
   `--ata <isci>` görevi doğrudan `assigned` yapar; atanmış işçi çalışmaya
   başlayabilir ve ilk adımda `yuva gorev al` çağırmaz. Görev `pending` durumunda
   bırakıldıysa işçi `al` ile üstlenir. `al`, yalnız `pending` veya revizyon
   sonrası `pending_revision` durumunda geçerlidir.
   Görev metni Yuva CLI kullanımını genel olarak yasaklıyorsa, aynı metinde
   atanmış işçiye kendi talimatını `yuva gelen --from <kimlik>` ile okuma ve
   yalnız kendi görevini `yuva gorev teslim <id> --from <kimlik> --not <rapor>`
   ile teslim etme iznini açıkça ver; görevli ilk kontrolü yapacaksa ayrıca
   `yuva gorev ilk-kontrol <id> --onayla|--revize --from <gorevli>` komutunu
   açıkça yetkilendir. Sohbet mesajı teslim sayılmaz. Bu dar
   istisna başka görev veya kimlikleri ya da canlı runtime, servis ve daemon'ı
   değiştirme yetkisi vermez.
2. **Üstlenme ve uygulama:** `assigned` durumunda görevi kayıtlı `assignee` doğrudan yürütür. `yuva gorev al <id> --from <isci>` yalnız `pending` veya `pending_revision` durumundaki görevi assigned yapar; `--ata <isci>` ile zaten atanmış yeni işte gerekli değildir. İşçi uygulama sonucunu görevliye teslim eder. Yeni işlerde görev kaydında açık `gorevli_kimlik` bulunur; işçinin `yuva gorev teslim` geçişi göreve bağlı görevlinin inceleme kuyruğuna düşürür (`pending_gorevli_review`). Görevli inceleyene kadar bu durum korunur.
3. **İlk kontrol ve bütünleştirme:** görevli yalnız kendisine açıkça bağlanmış `pending_gorevli_review` işlerini inceler. Kabul/bütünleştirme ve rapor sonrası `yuva gorev ilk-kontrol <id> --onayla --from <gorevli> --not "kontrol ve bütünleştirme özeti"` geçişi işi `pending_verification` durumuna çıkarır; bundan sonra denetçi nihai inceleme yapar. `--revize` kararı işi `pending_revision` durumuna döndürür ve assignee işçiye eksikleri bildirir.
4. **Nihai teslim ve denetim:** `pending_verification` durumundaki işi denetçi inceler:
   - `yuva gorev denetle <id> --onayla --from denetci --not "kabul gerekçesi"`
   - `yuva gorev denetle <id> --revize --from denetci --not "eksikler"`
5. **Revize:** görevli ilk kontrolde veya denetçi nihai incelemede revizyon isterse görev aynı assignee işçide kalır. İşçi `yuva gorev al` ile işi yeniden assigned yapar, düzeltir ve tekrar teslim eder; `gorevli_kimlik` olan yeni iş yeniden ilk kontrol kuyruğuna gider. Denetçi ancak görevlinin kabulünden sonra tekrar karar verir.

Eski görevlerde `gorevli_kimlik` yoksa mevcut doğrudan denetçi akışı korunur. Eski kayıtlar `kimden` veya `assignee` alanından görevli tahmin edilerek dönüştürülmez. `--gorevli` yeni işin açık inceleyen atamasıdır; actor doğrulaması değildir. `--from`, panel gövdesi ve aynı OS hesabındaki süreçler gerçek kimlik kanıtı sağlamaz (yerel yetki güven sınırı bölümüne bakın).

### Görev okuma ve teslim kaydı

Atanmış işçi kendi talimatını `yuva gelen --from <kimlik>` ile okuyabilir.
Tamamladığı yalnız kendi atanmış görevinin gerçek sonuç raporunu
`yuva gorev teslim <id> --from <kimlik> --not <rapor>` ile tahtaya kaydetmesi
izinli ve zorunludur. Bu tek teslim geçişi, genel CLI/görev durumu değiştirme
yasağının dar istisnasıdır; başka görev veya kimlik durumunu ya da live runtime,
servis ve daemon'ı değiştirme yetkisi vermez.

## Kibarlık kuralları

- Her anlamlı çıktı sonrası özet yaz: `yuva yaz "..." --from <takma-ad>`
- Yaptığın önemli değişikliği dosya yollarıyla bildir.
- Başkasının adına YAZMA, görev SAHİPLenme (al komutu sadece atanan işçi).
- Sorular `@kime` nişanlı sorulsun: `yuva yaz "@denetci ..." --from <isci> --tur soru`
- Uzun çıktıyı yuvaya taşırken ilk ~20 satırını özetle; kalanı dosyada bırak.
