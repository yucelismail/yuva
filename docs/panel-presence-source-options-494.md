# #494 — Yuva model presence kanıt kaynağı seçenekleri

Tarih: 2026-10-21
Kapsam: #482 bulgularını temel alan salt-okunur mimari kararı. Kod, test,
runtime, süreç, socket veya panel çalıştırılmadı.

## Karar özeti

Doğrulanmış “çevrimiçi model oturumu” için ana kanıt kaynağı ayrıcalığı
sınırlandırılmış bir broker olmalıdır. Broker, gerçek adapter bağlantısını
ve provider session kimliğini aynı oturum nesline bağlar; taze bir lease
üretir ve yalnız brokerın doğruladığı presence kaydını Yuva'ya sunar.

Adapter ping tek başına modelin işlediğini veya session'ın doğru session
olduğunu kanıtlamaz. Process/socket gözlemi süreç canlılığını ve yerel IPC
peer kimliğini destekleyebilir; model oturumunu veya provider turn'ünü
kanıtlamaz. Bunlar broker tarafından toplanan ek sinyaller olabilir, tek
başına yeşil presence kaynağı olmamalıdır.

Aşağıdaki tüm başarısız/çelişkili durumlarda sonuç unknown kalır: heartbeat
süresinin dolması, panel veya broker erişiminin kesilmesi, adapter/provider
bağının kopması, oturum kimliğinin doğrulanamaması, süreç kimliğinin
belirsizliği, aynı UID kaynaklı güven sınırı veya lease nesli/sırasının
tutarsızlığı. TTL aşımı tek başına doğrulanmış offline kanıtı değildir.

## #482 ile mevcut sözleşme

#482 çalışma ağacında /api/veri alanları son_gorulme ve son_kalp değerlerini
null, online=false, presence_state=unknown ve presence_verified=false sunuyor.
api_kalp doğrulanmış broker principal olmadığı için 503 döndürüyor. bagli
kullanıcı kaydı heartbeat kanıtı sayılmıyor; ekran JSONL satırı da presence
kanıtı değil. Panel verisi alınamazsa CLI/UI çevrimiçi sonucu üretmemeli.
Bu görev yeni bir heartbeat yolu uygulamaz ve mevcut fail-closed davranışı
açık bırakma önerisi vermez.

## Seçenek karşılaştırması

| Kaynak | Ne kanıtlar | Güçlü yanı | Kritik sınır | Karar |
|---|---|---|---|---|
| Broker lease | Yetkili brokerın belirli adapter/provider session neslini yakın zamanda doğruladığını | Kimlik, oturum bağlama, nonce/sıra, TTL ve açık stop olayını tek otoritede birleştirebilir | Broker kendi kimliğini doğrulayamıyorsa sadece yeni bir sahte heartbeat yazarı olur; tek hata noktasıdır | Ana kaynak |
| Adapter ping | Adapter prosesinin yaşıyor ve broker/provider endpointine erişebildiğini | Session API/status kontrolüyle düzenli, taze sinyal üretir | Ping'in başarılı olması model turn'ünün aktif olduğunu veya doğru session'a bağlı olduğunu kanıtlamaz; adapter aynı UID ile taklit edilebilir | Broker lease'ini yenileyen girdi; tek başına yeterli değil |
| PID/process kanıtı | İzlenen yerel process örneğinin halen yaşadığını veya sonlandığını | Child'ı başlatan supervisor process ömrünü doğrudan izleyebilir; pidfd PID yeniden kullanımını önler | PID tek başına kimlik değildir; PIDFD de yalnız process örneğini gösterir, provider session/model state'ini değil | Tanılama ve ek yerel kanıt |
| Unix socket peer | Bağlanan yerel peer'in kernelce bildirilen PID/UID/GID değerlerini | Aynı makinede broker-client IPC'sinde bağlantı peer'ini doğrulayabilir | SO_PEERCRED bağlantı anındaki credential'ları verir; aynı UID süreçlerini ayırmaz, adapter/session içeriğinin doğruluğunu kanıtlamaz | Broker IPC taşıması için yararlı; tek başına principal değil |
| Dosyaya heartbeat/PID yazımı | Dosyayı yazan bir sürecin beyanını | Kurması ve gözlemesi kolay | Aynı UID yazarı/okuyucusu bunu taklit edebilir; stale dosya, PID reuse ve yarım güncelleme riski | Presence güven sınırı olarak reddet |

Linux pidfd_open bir PID ile işaret edilen task'a file descriptor verir; PIDFD process ömrünü poll ile izlemek için kullanılabilir. Bu bir provider session veya modelin çalıştığı kanıt değildir. Hazırda çalışan yabancı bir PID için yalnız PID'den pidfd açmak, yanlış/stale PID bilgisinin ilk doğrulamasını ortadan kaldırmaz; supervisor'ın child'ı oluştururken aldığı process handle daha güçlü bağlam sağlar. Kernel/man-pages kaynakları aşağıda listelenmiştir.

Linux AF_UNIX SO_PEERCRED bağlı socket peer'inin PID, gerçek UID ve gerçek GID değerlerini bağlantı anında verir. Aynı UID altındaki farklı agent/prosesleri birbirinden ayırmaz. Dolayısıyla socket yolu izinleri ve credential kontrolü, bütün istemciler aynı hesapta çalışıyorsa agent kimliği doğrulaması değildir.

## Önerilen broker kanıt sözleşmesi

Broker, basit heartbeat endpoint'i değil, doğrulanmış kaynak ve provider session
bağını tutan stateful yetkili bileşen olmalıdır.

Her lease en az şu alanlara bağlanmalı:

- Yuva principal/agent kimliği ve kimliği doğrulayan broker principal;
- provider adı ve provider instance namespace'i;
- opak provider session ID; başka session ID'leriyle karıştırılmamalı;
- adapter generation/session generation; her yeniden bağlanmada yeni değer;
- artan sequence veya broker challenge nonce'u;
- brokerın gözlem zamanı, lease expiry ve kanıt kaynağı;
- presence semantiği: adapter_connected, provider_session_observed,
  provider_busy/idle/approval_pending veya unknown.

Broker sadece adapter'ın ping aldığını doğruladıysa state adapter_connected
olarak adlandırılmalı. Model oturumu çevrimiçi etiketi için session ID'nin
provider status/history/event kaynağından bağlanmış olması gerekir. Bu da
“iş üretiyor” demek değildir; busy/idle ayrı provider gözlemidir ve kopuk SSE
idle sayılmaz.

Heartbeat isteği taze challenge/sequence ile replay'e karşı bağlanmalı ve
broker tarafından doğrulanmış identity üzerinden üretilmeli. Kimlik alanlarını
istek gövdesinde beyan etmek authentication değildir. Broker anahtarı genel
worker UID'sinin okuyabildiği dosyada tutulursa MAC de same-UID tehdidini
kapatmaz. Tercih edilen sınır ayrı broker UID/service veya OS'nin
doğrulayabildiği process/socket credential ile kapalı IPC; anahtar gerekiyorsa
broker dışında okunamayacak ve loga/ortama dökülmeyecek biçimde korunmalıdır.

Broker aynı hostta ve aynı UID ile tüm worker'larla çalıştırılırsa güven
sınırı iyileşmez. Unix socket üzerinde SO_PEERCRED yalnız UID ayırıyorsa
broker principal için yeterli değildir. Gerçek izolasyon sağlanana kadar
presence_verified=false kalmalıdır.

## TTL, stale ve açık offline kanıtı

1. Heartbeat yaşı ve lease expiry brokerın tek saat alanıyla hesaplanmalı;
   uygulama içi karşılaştırma monotonic clock kullanmalı. Yeniden başlatma
   veya monotonic clock epoch değişiminde eski lease otomatik taşınmamalı.
2. Lease süresi dolarsa state unknown olur. Bu, adapter/broker ile son
   doğrulanmış iletişim eskidi demektir; provider session'ın kapandığını
   kanıtlamaz.
3. Offline yalnız yetkili brokerdan alınan açık, generation-bound stop/exit
   gözlemiyle gösterilebilir. Provider'dan bağımsız adapter ping'inin susması,
   lease TTL aşımı, panel timeout'u veya PID'nin artık bulunamaması tek başına
   doğrulanmış offline olmamalıdır.
4. Eski generation event/heartbeat yeni generation lease'ini yenileyemez.
   Sequence gerilemesi duplicate/stale olarak yok sayılır ve denetim kaydına
   girebilir; aynı sequence ile çelişkili içerik unknown/conflict üretir.
5. Panel veya Yuva API'si brokerı okuyamıyorsa “son bilinen online” yeşil
   kalmamalı; ekranda unknown/presence doğrulanamıyor gösterilmelidir.
   Panel kesintisi offline sonucu üretmez.
6. Açık doğrulanmış offline kayıtları da sonsuza kadar taze sayılmamalı.
   #482'nin belirttiği gibi zaman, kaynak, generation ve offline freshness
   kuralı response sözleşmesinde olmalıdır.

## Gözlem seçeneklerinin uygulama sınırları

### Broker

Gerçek adapter supervisor/broker tarafından başlatılmalı veya broker,
adapter'ın kimliğini koruyan ayrı bir IPC/auth kanalından doğrulamalı. Broker
session seçimini adapter'dan gelen doğrulanabilir provider cevabına bağlamalı;
UI'daki görünen ad, process command-line metni veya worker mesajı kimlik
kanıtı değildir. Broker erişilemezse yeni heartbeat üretilemez ve durum
unknown olur. Brokerın tek olması, provider'ların çoklu ve restartable olması
durumunda generation kaydını provider instance başına tutmalıdır.

### Adapter ping

Ping, “adapter alive” sinyali olarak faydalıdır. Daha güçlü ama hâlâ sınırlı
bir sinyal, pingle birlikte hedef provider health ve session/status readback
yapmaktır. Health endpoint'i server'ın cevap verdiğini, session status ise
provider'ın o anda sunduğu snapshot'ı doğrular; her ikisi de model turn
completion, Yuva teslimi veya user-facing session owner doğrulaması değildir.
SSE kopması reconnect zorunluluğu doğuruyorsa önce read-only status/history
uzlaştırması yapılmalı; boş event akışı idle sayılmamalıdır.

### Local process/socket

Süreci doğrudan başlatan supervisor child handle/pidfd üzerinden process
exit'ini PID dosyasından daha güvenli izleyebilir. Yalnız kayıtlı PID varsa
PID reuse riskine karşı UID, executable identity, starttime ve mümkünse pidfd
ile aynı process instance doğrulanmalıdır; bu adımlar da provider session
binding yerine geçmez. /proc erişimi permission, PID namespace ve süreç
ayrıntılarının gizlenmesiyle kısıtlanabilir.

AF_UNIX socket, broker ile adapter IPC için TCP loopback'ten daha dar yerel
taşıma sunabilir. Socket directory/file izinleri ve peer credential kontrolü
gerekir. Aynı UID'deki yetkisiz worker'lar socket'e bağlanabiliyorsa veya
broker secret'ını okuyabiliyorsa model kimliği/sahipliği doğrulanmış olmaz.
Socket bağlantısı da adapter process'inin provider session'ını gerçekten
gözlediğini ispatlamaz; protokol seviyesinde challenge-response ve provider
binding ayrıca gerekir.

## Aşamalı karar

1. Şimdilik mevcut davranış korunur: doğrulanmış broker principal yokken
   heartbeat endpoint'i kapalı, presence unknown. Kayıtlı bagli ve ekran
   hareketi kanıt olarak yükseltilmez.
2. Önce threat modelde same-UID saldırganın güven sınırının içinde mi dışında
   mı olduğu karara bağlanır. İçindeyse ayrı UID/service/sandbox gerekir;
   yalnız socket permission veya dosya mode çözüm sayılmaz.
3. Broker/adapter session lease protokolü ve lifecycle (start, reconnect,
   explicit stop, crash, stale, restart, revoke) tasarlanır; generation,
   sequence, evidence timestamp ve unknown/offline ayrımı API şemasına eklenir.
4. Adapter ping ve provider status/history readback brokerın kanıt girdileri
   yapılır. PIDFD/AF_UNIX sinyalleri yardımcı process/IPC gözlemidir.
5. Ancak broker principal doğrulama, same-UID sınırı, replay/stale kontrolü,
   explicit offline tazeliği, panel erişim hatası ve reconnect acceptance
   kapıları tamamlandıktan sonra presence_verified etkinleştirilir.

## Kaynaklar

- İç kaynak: docs/panel-presence-evidence-review-482.md (#482); fail-closed
  CLI, API ve UI sözleşmesi ve mevcut broker eksikliği.
- Linux man-pages, pidfd_open(2):
  https://www.man7.org/linux/man-pages/man2/pidfd_open.2.html
- Linux man-pages, unix(7), SO_PEERCRED/SCM_CREDENTIALS:
  https://www.man7.org/linux/man-pages/man7/unix.7.html
- Linux kernel documentation, /proc process information:
  https://www.kernel.org/doc/html/latest/filesystems/proc.html

Bu not seçenek ve karar tasarımıdır; broker, heartbeat, credential, process
handle veya panel/API davranışı uygulandığı iddiası taşımaz.
