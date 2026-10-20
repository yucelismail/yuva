# Linux canlı geçiş kontrol listesi

Bu belge mevcut bir Yuva kurulumundan yeni kod ağacına geçiş içindir. Eski ve
yeni CLI/panel yazıcıları aynı veri dosyalarını eşzamanlı kullanmamalıdır.

## Bilinen sınırlar ve veri geçişi

Eski CLI'nin heartbeat süreçleri yeni sürümün `.kalp-<kimlik>.lock` flock'unu
kullanmaz. Yeni flock bu eski süreçleri tekilleştiremez. Aynı KOK'u kullanan
eski PID-file heartbeat daemon'ları yeni kod başlamadan önce durdurulmalıdır.
PID dosyasını okuyup PID'ye sinyal göndermeyin; eski CLI'nin ayrılma komutunu
veya kurulumu yöneten servis/oturum yöneticisini kullanın, ardından süreçlerin
kapandığını host üzerinde doğrulayın.

Yeni heartbeat `systemd --user` geçici servisiyle çalışır. Host kullanıcı
systemd yöneticisi ve D-Bus oturumu erişilebilir olmalı; CLI ile servis aynı
KOK dosya sistemi/inode'larını görmeli ve host servisi panel URL'sine
erişebilmelidir. Sandbox içindeki `localhost:8686`, host network namespace'inde
aynı paneli göstermeyebilir. Bu koşullar sağlanmazsa CLI bağlantıyı yeşil
başarı olarak göstermez. Kullanıcı systemd yöneticisi yoksa bağlantıyı
sandbox dışındaki, kullanıcı yöneticisine bağlı host terminalinden başlatın.
CLI ve servis başlangıçta yalnız KOK yolunu değil, KOK dizini ile heartbeat
lock dosyasının `device:inode` kimliklerini de karşılaştırır; eşleşmezse
heartbeat başlamaz.

Transient user unit Codex CLI/sandbox alt süreci kapansa da çalışır; kullanıcı
systemd manager'ı durursa unit de durur. Logout sonrasında manager'ın yaşamaya
devam etmesi için hostta `loginctl enable-linger "$USER"` gerekir. Transient
unit reboot sonrası kalıcı değildir; reboot'tan sonra yeniden bağlanma gerekir.
Kod bu sınırların dışında süreklilik garantisi vermez. Heartbeat aralığı 1–20
saniyeyle sınırlıdır; panel lease'i 30 saniyedir.

Panel `son_gorulme` alanını kullanıcı etkinliği için tutar; çevrimiçi durumunu
yalnızca `son_kalp` alanındaki başarılı `/api/kalp` zamanından hesaplar. Eski
kayıtlarda `son_kalp` bulunmadığı için ilk gerçek pulse gelene kadar kimlik
çevrimdışı görünür. Mesaj, görev ve geçmiş kayıtları değiştirilmez.

Bağlantıları kesmeden geçiş garantisi yoktur. Bu şart zorunluysa önce eski ve
yeni sürümün kullanacağı ortak bir yazma servisi veya geriye uyumlu kilit
protokolü geliştirilip gerçek süreçlerle doğrulanmalıdır.

## Geçiş öncesi

1. Bakım penceresi belirleyin. Yeni görev atamalarını durdurun ve etkin
   görevlerin teslim veya iptal edildiğini doğrulayın.
2. Eski sürümün her model oturumundan `yuva ayril --from <kimlik>` çalıştırın.
   Eski heartbeat daemon'larının kapandığını eski kurulumun servis/oturum
   yöneticisinden doğrulayın. PID-file kayıtlarını süreç kanıtı saymayın.
   Bir daemon çalışmaya devam ediyorsa geçişi durdurun. Aynı KOK'u yeni sürümle
   paylaşmadan önce bu adım zorunludur.
3. Eski paneli kendi servis yöneticisiyle durdurun. Yeni sürümü başlatmadan
   önce 8686 portunun boş ve eski yazıcı süreçlerinin durmuş olduğunu doğrulayın.
   Tüm eski CLI yazma çağrılarının da bitmesini bekleyin; yalnız panelin
   kapanması CLI süreçlerinin durduğunu kanıtlamaz. Yuva yazımlarını bakım
   penceresi boyunca dondurun.
4. Veri kökünün tamamını, gizli heartbeat/kilit dosyaları ve izin bilgileri dahil,
   yedekleyin. Varsayılan kökte `durum.json`, `gorevler.json`, `mesaj.jsonl` ve
   `ekran/` bulunur. Aşağıdaki örnek `YUVA_DIR` ayarlıysa aynı mutlak yolu
   kullanır; ayarlı değilse `~/yuva` varsayımını kullanır. KOK'u gerçek dizine
   çözer ve yedek/denetim konumlarının KOK içinde olmasını reddeder. Arşiv ve
   kontrol kopyası KOK dışında kalır:

   ```bash
   (
     set -euo pipefail
     KOK_GIRIS="${YUVA_DIR:-$HOME/yuva}"
     case "$KOK_GIRIS" in
       /*) ;;
       *) echo "YUVA_DIR mutlak yol olmalı: $KOK_GIRIS" >&2; exit 1 ;;
     esac
     KOK="$(realpath -e -- "$KOK_GIRIS")"
     test -d "$KOK"
     test "$KOK" != /

     YEDEK_GIRIS="${YUVA_BACKUP_DIR:-$(dirname -- "$KOK")/yuva-yedek}"
     YEDEK_DIR="$(realpath -m -- "$YEDEK_GIRIS")"
     case "$YEDEK_DIR/" in
       "$KOK/"*) echo "Yedek dizini KOK içinde olamaz: $YEDEK_DIR" >&2; exit 1 ;;
     esac
     mkdir -p -- "$YEDEK_DIR"
     YEDEK_DIR="$(realpath -e -- "$YEDEK_DIR")"
     case "$YEDEK_DIR/" in
       "$KOK/"*) echo "Yedek dizini KOK içinde olamaz: $YEDEK_DIR" >&2; exit 1 ;;
     esac

     ARSIV="$(mktemp "$YEDEK_DIR/yuva-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
     tar --acls --xattrs --xattrs-include='user.*' -cpf "$ARSIV" \
       -C "$(dirname -- "$KOK")" --add-file="$(basename -- "$KOK")"
     tar -tvf "$ARSIV" > "$ARSIV.list"
     sha256sum "$ARSIV" > "$ARSIV.sha256"
     sha256sum -c "$ARSIV.sha256"

     KONTROL="$(mktemp -d "$YEDEK_DIR/restore-check.XXXXXX")"
     tar --acls --xattrs --xattrs-include='user.*' -xpf "$ARSIV" -C "$KONTROL"
     GER_YUK="$KONTROL/$(basename -- "$KOK")"
     diff -qr -- "$KOK" "$GER_YUK"
     (cd "$KOK" && getfacl -R -p .) > "$KONTROL/kaynak.acl"
     (cd "$GER_YUK" && getfacl -R -p .) > "$KONTROL/geri-yuklenen.acl"
     diff -u "$KONTROL/kaynak.acl" "$KONTROL/geri-yuklenen.acl"
     (cd "$KOK" && getfattr -R -d -m '^user\..*' .) > "$KONTROL/kaynak.xattr"
     (cd "$GER_YUK" && getfattr -R -d -m '^user\..*' .) > "$KONTROL/geri-yuklenen.xattr"
     diff -u "$KONTROL/kaynak.xattr" "$KONTROL/geri-yuklenen.xattr"
   )
   ```

   Bu Linux örneği GNU `tar`, `realpath`, `sha256sum`, `diff`, `getfacl` ve
   `getfattr` araçlarını gerektirir; eksik araç veya başarısız kontrol varsa
   geçişi durdurun. `tar -tvf` izin/owner listesini verir; `-p`, ACL ve
   `user.*` xattr seçenekleri geri açmada mod/ACL/kullanıcı xattr'larını korumayı
   ister. Bu kullanıcı düzeyindeki örnek `security.*`, `trusted.*` ve `system.*`
   gibi diğer xattr ad alanlarını arşivlemez veya geri yüklemez; bu alanlar hedef
   sisteme göre ayrıca ele alınmalıdır. Sahiplik aynı kullanıcı
   ve hosta geri dönüş varsayımına dayanır; başka UID ile restore sahipliği
   ayrıca planlanmalıdır. Arşivi etkin KOK'un üzerine açmayın. Kaynak kodu ile
   veri dosyalarını aynı işlemde taşımayın veya üzerine yazmayın.
5. Yeni kaynak ağacını ayrı bir dizine kurun (ör. `~/yuva-v2`); mevcut KOK'u
   veri kökü olarak koruyun.

## Geçiş

1. `~/.local/bin/yuva` bağlantısını yeni kaynak ağacının `bin/yuva` dosyasına
   yöneltin. `YUVA_DIR` ayarlanmamışsa yeni CLI varsayılan olarak `~/yuva`
   kullanır.
2. Panel servisinin ve CLI oturumlarının aynı `YUVA_DIR` değerini
   kullandığını doğrulayın. Panel bu değeri başlattığı CLI alt süreçlerine de
   aktarır.
3. Panel servis komutunu yeni kaynak ağacındaki `panel/server.py` dosyasına
   yöneltin. `--host` loopback adresi olmalı; loopback dışı bind reddedilir.
   CLI oturumlarının kullandığı hesapta `systemd --user` yöneticisinin ve
   D-Bus bağlantısının erişilebilir olduğunu host terminalinde
   `systemctl --user status` komutuyla doğrulayın. Komut kullanıcı yöneticisine
   bağlanmıyorsa normal host kullanıcı oturumundan çalıştırın; sonra `yuva
   baglan ...` komutunu aynı host terminalinde yeniden deneyin.
   Sandbox/host ayrımında panel URL'si heartbeat servisinin host network
   namespace'inden erişilebilir olmalıdır.
   Paneli `systemd --user` ile yönetiyorsanız adaydaki
   `contrib/systemd/yuva-panel.service` örneğini kurun. Örnek `~/yuva` kod ve
   veri kökünü varsayar; bu geçişte kod `~/yuva-v2`, mevcut veri kökü ise
   `~/yuva` olduğundan unit'te `ExecStart` yolunu `%h/yuva-v2/panel/server.py`
   yapın, `Environment=YUVA_DIR=%h/yuva` değerini koruyun. Başka kökler
   kullanıyorsanız iki değeri de uygun yollarla değiştirin. Eski panelin
   durduğunu ve 8686'nın boş olduğunu doğruladıktan sonra:

   ```bash
   mkdir -p ~/.config/systemd/user
   install -m 0644 ~/yuva-v2/contrib/systemd/yuva-panel.service ~/.config/systemd/user/yuva-panel.service
   # Kurulan unit'te ExecStart ve gerekirse Environment=YUVA_DIR yollarını düzenleyin.
   systemctl --user daemon-reload
   systemctl --user enable --now yuva-panel.service
   systemctl --user status yuva-panel.service
   journalctl --user -u yuva-panel.service -f
   ```

   Unit'i güncelledikten sonra `systemctl --user daemon-reload` ve
   `systemctl --user restart yuva-panel.service`; durdurmak için
   `systemctl --user stop yuva-panel.service` kullanın. Bu panel unit'i
   heartbeat'in geçici systemd unit'inden ayrıdır: panel unit'i `enable` edildiği
   için user manager başlayınca yeniden başlar; logout sonrası çalışması ve
   reboot'ta manager'ın açılması için `loginctl enable-linger "$USER"` gerekir;
   linger yoksa manager logoutta kapanır ve panel durur. Linger etkin değilken
   panel sonraki kullanıcı oturumu açıldığında başlar. Heartbeat
   unit'i reboot'ta kalıcı değildir; modelleri yeniden bağlayın. Farklı servis
   yöneticisi kullanılıyorsa paneli onunla başlatıp durdurun; aynı anda yalnız bir
   panel 8686 portunu kullanmalıdır.
4. Paneli (kurulu user service veya mevcut servis yöneticisiyle) başlatın ya da
   zaten başladıysa durumunu kontrol edin. Ekip, görev tahtası ve mesaj
   geçmişinin beklenen veri kökünden okunduğunu doğrulayın. Henüz tüm modelleri bağlamayın. Tarayıcı
   veya ters vekil kullanılıyorsa Host, Origin ve JSON Content-Type kontrollerini
   canary ile doğrulayın; bunlar kimlik doğrulaması değildir. Panel aynı network
   namespace içinden localhost'a erişebilen yerel süreçlerden, farklı UID'ler
   dahil, HTTP API isteği kabul edebilir. Kimlik doğrulamasız paneli LAN'a,
   internete veya tünele açmayın. Ters vekil paneli uzaktan erişilebilir
   kılıyorsa vekil üzerinde kimlik doğrulaması ve erişim kontrolü zorunludur;
   panelin kendi Host/Origin/Content-Type kontrolleri bu katmanın yerini tutmaz.
   Hata yanıtlarının işletim sistemi veya alt süreç ayrıntıları içerebileceğini
   de göz önünde bulundurun.
5. Kullanıcı systemd oturumu bulunan sandbox dışı host terminalinden tek bir
   modelle `yuva baglan <kimlik> --arac <arac> --rol <rol>` çalıştırın. CLI
   host servisinin aynı KOK'u ve paneli kullandığını doğrulayınca bağlantı
   başarılı olur. Panelde rolü, gerçek kalp zamanını ve tek heartbeat
   sahipliğini doğrulayın. Kullanılan GET/POST yollarının Host, Origin ve JSON
   içerik türü kontrollerini geçtiğini de doğrulayın. Sorun varsa diğer
   modelleri bağlamadan rollback uygulayın.
   Logout sonrası devamlılık isteniyorsa linger durumunu ve reboot sonrası
   yeniden bağlanma davranışını ayrıca canary ile doğrulayın.
6. Canary doğrulandıktan sonra modelleri küçük gruplarla bağlayın. Her gruptan
   sonra ışıkları, görev/mesaj yazımlarını ve yinelenen heartbeat olmadığını
   kontrol edin.

## Rollback

1. Yeni görev atamalarını durdurun ve bağlı modelleri kendi oturumlarından
   `yuva ayril --from <kimlik>` ile ayırın. Kullanıcı systemd heartbeat
   birimlerinin durduğunu doğrulayın. Model ve yönetici oturumlarına yeni
   candidate CLI/API yazımı göndermemelerini bildirin.
2. Yeni paneli ve heartbeat süreçlerini durdurun. Başlamış tüm tek-atımlık
   candidate CLI çağrılarının bitmesini bekleyin; candidate CLI, panel kapansa
   da doğrudan dosya yazabilir. Panel biriminin pasif olduğunu, candidate CLI
   süreçlerinin kalmadığını ve 8686 portunun boş olduğunu hostta doğrulayın.
   Bu kontroller tamamlanana kadar eski CLI'yi veya paneli başlatmayın; hepsi
   tamamlandıktan sonra da eski sürüm açılana kadar yazımları dondurulmuş tutun.
3. CLI symlink'ini ve panel servis komutunu eski kaynak ağacına döndürün.
   Örnek `yuva-panel.service` kullanılıyorsa `ExecStart` değerini eski
   `panel/server.py` yoluna alın. Eski sürümü başlatmadan önce hedef sürümün
   candidate'ın ürettiği JSON şemasını desteklediğini ve aynı `YUVA_DIR` veri
   kökünü okuyup yazabildiğini doğrulayın. Doğrulanamıyorsa aynı veri kökünü
   eski sürüme bağlamayın; uyumlu bir yedek veya açık bir veri geçişi kullanın.
   Uyumluluk doğrulandıysa `Environment=YUVA_DIR=...` değerini koruyun. Sonra
   aşağıdaki komutlarla unit'i yeniden yükleyip başlatın ve çıktıyı doğrulayın:

   ```bash
   systemctl --user daemon-reload
   systemctl --user restart yuva-panel.service
   systemctl --user status yuva-panel.service
   journalctl --user -u yuva-panel.service -n 50
   ```
4. Yedeği yalnızca veri bozulması varsa geri yükleyin. Yedek sonrasında gelen
   mesaj ve görev değişikliklerini incelemeden üzerine yazmayın.
5. Eski panel ve CLI'yi açtıktan sonra önce bir canary modelle doğrulayın;
   ardından kalan modelleri kademeli bağlayın.

Bu liste kaynak incelemesine dayanır. Canlıya almadan önce servis yöneticisi,
port, etkin kimlikler ve yedek/geri yükleme adımlarını host üzerinde doğrulayın.
