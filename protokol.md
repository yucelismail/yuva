# 🪹 Yuva Protokolü

Farklı CLI'lardan (claude / codex / opencode) gelen model oturumlarının
ortak çalışma alanı. İletişim `~/yuva/` altındaki dosyalar üzerinden yürür.

## Roller

| Rol         | Komut vereni | Görevi |
|-------------|--------------|--------|
| **görevli** | kullanıcı    | İşi böler, görevleri açar ve işçilere atar; soruları yanıtlar |
| **işçi**    | görevli      | Atanan görevi üstlenir, yapar, teslim eder; kendi başına görev atamaz |
| **denetçi** | kullanıcı    | Teslim edilen işi inceler: onaylar veya revize ister |

- Görevli ve denetçi KULLANICI tarafından belirlenir; kendi kendine rol üstlenme.
- Kullanıcı panelden bir denetçiyi **🔍 BAŞ DENETÇİ** yapabilir: iş bölümünü ve görev
  dağıtımını o yürütür.
- İşçi, görevliye `@goreci` ile soru sorabilir; denetçi kararına karışmaz.

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
görevi kimin dağıttığını **kullanıcının atadığı baş denetçi/görevli** belirler.


## Çalışma akışı

1. **Dağıtma:** görevli görev açar:
   `yuva gorev ekle "Başlık" --detay "..." --from goreci --ata <isci>`
   Görev metni Yuva CLI kullanımını genel olarak yasaklıyorsa, aynı metinde
   atanmış işçiye kendi talimatını `yuva gelen --from <kimlik>` ile okuma ve
   yalnız kendi görevini `yuva gorev teslim <id> --from <kimlik> --not <rapor>`
   ile teslim etme iznini açıkça ver. Sohbet mesajı teslim sayılmaz. Bu dar
   istisna başka görev veya kimlikleri ya da canlı runtime, servis ve daemon'ı
   değiştirme yetkisi vermez.
2. **Üstlenme:** işçi `yuva gorev al <id> --from <isci>` der, çalışır.
3. **Teslim:** bitince `yuva gorev teslim <id> --from <isci> --not "özet + dosya yolları"`
4. **Denetim:** denetçi inceler:
   - `yuva gorev denetle <id> --onayla --from denetci --not "kabul gerekçesi"`
   - `yuva gorev denetle <id> --revize --from denetci --not "eksikler"`
5. **Revize:** işçi `yuva gelen` ile eksikleri görür, düzeltir, yeniden teslim eder.

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
