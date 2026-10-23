# Linux canlı geçiş kontrol listesi

Bu belge mevcut bir Yuva kurulumundan yeni kod ağacına geçiş içindir. Eski ve
yeni CLI/panel yazıcıları aynı veri dosyalarını eşzamanlı kullanmamalıdır.

## Kaynak unit → entrypoint → rol eşlemesi

Bu tablo depo içindeki tanımları gösterir; hostta kurulmuş/çalışan unit'leri
göstermez.

| Unit / başlatma biçimi | Entrypoint | Rol ve mevcut kaynak durumu |
|---|---|---|
| Kalıcı `yuva-panel.service` örneği: `contrib/systemd/yuva-panel.service` | `panel/server.py --host 127.0.0.1 --port 8686` | UI/API sunucusu; yalnız panel unit şablonu depoda bulunur. |
| Tasarlanan transient `yuva-kalp-<hash>.service` | `bin/yuva kalp-dongu --host-supervised ...`; unit adı `bin/yuva:host_birim()` ile hesaplanır. | Ayrı bir `server.py` değildir. Geçerli kaynakta CLI başlatıcısı broker principal olmadığı için erken reddeder, `kalp-dongu` da hata verir; bu kaynak transient unit başlatmaz. Panel `/api/kalp` isteğini `503` ile reddeder. |
| Elle çalıştırılan `preview/server.py` | `python3 preview/server.py` | 8687'de aday `panel/ui.html` ve statik sentetik fixture sunan salt-okunur geliştirici önizlemesi; Yuva servisi veya heartbeat değildir. |

Bu eşleme statik kaynak bilgisidir. Kurulu unit, etkin süreç, host UID veya
servis durumu incelenmiş sayılmaz. README'deki servis diyagramı da aynı ayrımı
gösterir.

## Bilinen sınırlar ve veri geçişi

Eski CLI'nin heartbeat süreçleri yeni sürümün `.kalp-<kimlik>.lock` flock'unu
kullanmaz. Yeni flock bu eski süreçleri tekilleştiremez. Aynı KOK'u kullanan
eski PID-file heartbeat daemon'ları yeni kod başlamadan önce durdurulmalıdır.
PID dosyasını okuyup PID'ye sinyal göndermeyin; eski CLI'nin ayrılma komutunu
veya kurulumu yöneten servis/oturum yöneticisini kullanın, ardından süreçlerin
kapandığını host üzerinde doğrulayın.

Güncel source gate nedeniyle heartbeat transient unit'i başlatılmaz:
`host_kalp_baslat()` systemd çağrısından önce ret döndürür; `cmd_kalp()` ve
`cmd_kalp_dongu()` da broker principal olmadan fail-closed kalır. Panel
`api_kalp()` her isteği `503` ile reddeder. `yuva baglan ... --kalp-yok` yalnız
roster kaydıdır; model presence/heartbeat üretmez. Bu nedenle normal geçişte
heartbeat için D-Bus, network namespace, linger, interval veya lease beklentisi
yoktur.

Eski sürüm daemon'larının durdurulması yine zorunludur; yeni source bu eski
daemon'ları tekilleştirdiğini veya kapattığını kanıtlamaz. W1b/broker kapısı
ileride onayla açılırsa transient unit'in systemd user manager ömrü, KOK
device:inode eşleşmesi ve panel erişimi ayrıca uygulama ve host canary işi
olarak doğrulanmalıdır. O zamana kadar panel `son_kalp` üretmez; eski
heartbeat zamanları online kanıtı değildir.

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

1. Doğrulanmış release'i `<INSTALL_ROOT>/current` işaretçisine alın ve
   `~/.local/bin/yuva` bağlantısını aynı release'in `bin/yuva` dosyasına
   yöneltin. `YUVA_DIR` ayarlanmamışsa yeni CLI varsayılan olarak `~/yuva`
   kullanır.
2. Panel servisinin ve CLI oturumlarının aynı `YUVA_DIR` değerini
   kullandığını doğrulayın. Panel bu değeri başlattığı CLI alt süreçlerine de
   aktarır.
3. Panel servis entrypoint'i aynı release içindeki `panel/server.py` olmalı.
   `--host` loopback adresi olmalı; loopback dışı bind reddedilir.
   Paneli kalıcı user unit ile başlatacaksanız `systemd --user` yöneticisinin
   erişimini hostta doğrulayın. `yuva baglan ... --kalp-yok` roster işlemi için
   bu user manager gerekmez; mevcut heartbeat yolu kapalı olduğu için bu
   sürümde sandbox/host heartbeat network koşulu da uygulanmaz.
   Paneli `systemd --user` ile yönetiyorsanız adaydaki
   `contrib/systemd/yuva-panel.service` örneğini kurun. Unit kalıcı panel UI/API
   sunucusunu başlatır; heartbeat worker unit'i değildir. Kod yolu doğrulanmış
   `<INSTALL_ROOT>/current` release işaretçisine, `YUVA_DIR` ise kurulumdaki
   mevcut veri köküne (`%h/yuva` varsayılanı) gider. README hızlı başlangıcındaki
   `YUVA_INSTALL_ROOT` değerini kullanarak örneği aynı release'ten kurun; kod ve
   veri yollarını birbirine karıştırmayın. Eski panelin durduğunu ve 8686'nın
   boş olduğunu doğruladıktan sonra:

   ```bash
   YUVA_INSTALL_ROOT="$HOME/.local/opt/yuva"  # Kurulumunuzdaki gerçek kökle aynı olmalı
   mkdir -p ~/.config/systemd/user
   install -m 0644 "$YUVA_INSTALL_ROOT/current/contrib/systemd/yuva-panel.service" ~/.config/systemd/user/yuva-panel.service
   systemctl --user daemon-reload
   systemctl --user enable --now yuva-panel.service
   systemctl --user status yuva-panel.service
   journalctl --user -u yuva-panel.service -f
   ```

   Değiştirilmiş bir unit'i kurduktan sonra `systemctl --user daemon-reload` ve
   `systemctl --user restart yuva-panel.service`; durdurmak için
   `systemctl --user stop yuva-panel.service` kullanın. Kaynakta planlanan
   transient heartbeat adı `yuva-kalp-<hash>.service` biçimindedir; bu worker
   `yuva-panel.service`'ten ayrıdır, depoda heartbeat unit şablonu yoktur ve
   mevcut fail-closed gate onu başlatmaz. Panel unit'i `enable` edildiği için user manager başlayınca
   yeniden başlar; logout sonrası çalışması ve reboot'ta manager'ın açılması
   için `loginctl enable-linger "$USER"` gerekir; linger yoksa manager logoutta
   kapanır ve panel durur. Linger etkin değilken panel sonraki kullanıcı oturumu
   açıldığında başlar. Farklı servis
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
5. Tek roster canary'si gerekiyorsa `yuva baglan <kimlik> --arac <arac> --rol
   <rol> --kalp-yok` çalıştırın. Panel/CLI'nin aynı `YUVA_DIR` kullandığını ve
   roster kaydını doğrulayın. Bu kaynakta panel presence'i `unknown` kalmalı;
   başarılı roster kaydını online, gerçek kalp veya tek-worker kanıtı saymayın.
   Kabul koşulu doğrulanmış presence ise geçişi NO-GO bırakın; broker/heartbeat
   özelliği ayrı kabul edilmeden diğer modelleri canlı canary'ye almayın.
6. Yalnız roster, görev ve mesaj akışları bu geçişin hedefiyse canary sonrası
   modelleri küçük gruplarla bağlayın; presence doğrulamasının kapsam dışı ve
   `unknown` olduğunu kayıt altında tutun.

## Rollback

1. Yeni görev atamalarını durdurun ve roster'a eklenmiş modelleri
   `yuva ayril --from <kimlik>` ile ayırın. Eski/başka sürüm transient
   heartbeat unit'leri varsa onları kendi servis yöneticisinden doğrulayın.
   Model ve yönetici oturumlarına yeni
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
