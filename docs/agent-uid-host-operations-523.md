# Ajan başına UID: host işletim önkoşulları (#523)

## Amaç ve karar sınırı

2026-10-23 tarihli W1b operatör kararı model/ajan başına doğrulanmış yeşil presence hedefler; same-UID ajanları birbirine karşı güvenilir saymaz ve ajan başına ayrı OS UID'yi tercih eder. Güvenilir per-session launcher varsayılmıyor. Bu, ayrı hesapların operasyonel olarak incelenmesine izin verir; kullanıcı/grup, linger, socket, broker, auth, credential veya servis kurma onayı değildir.

Bu not W1b Seçenek B'nin host işletim gereksinimlerini çıkarır. Presence `unknown` kalır; `SO_PEERCRED` UID kanıtıdır, tek başına provider oturumu kanıtı değildir. `provider_session_observed` için adapter/session/generation kanıtı tanımlanmadan UID heartbeat'i yeşil yapılmamalıdır (#514 revizyon talebi).

## Önerilen varlık ve yetki sınırı

| Varlık | Sahiplik / yetki hedefi | İşletim notu |
|---|---|---|
| Agent hesabı | Her agent için tek, sabit numeric UID; ayrı HOME ve `XDG_RUNTIME_DIR` | UID→principal haritası dışında ad/görünen ad/rol değişikliği kimlik eşlemesini değiştirmez. UID yeniden kullanımı eski eşlemeler/lease'ler temizlenmeden yapılmamalıdır; süre ve temizleme onayı operatör kararıdır. |
| Broker | Ayrı, agent olmayan service UID; yalnız principal haritası ve presence state'i yönetir | Agent process broker UID'si olamaz ve broker state dosyalarını doğrudan yazamaz. Broker state owner, backup, restart epoch ve revoke işlemi tek service lifecycle'a bağlanır. |
| UID→principal haritası | `/etc/yuva/broker.conf` gibi root-owned, sır içermeyen host konfigürasyonu; #514 taslağında `0644` | Her numeric UID için principal, enabled/role ve gerekiyorsa map revision; eksik, duplicate veya çelişkili mapping fail-closed olmalı. Dosya yalnız root/host yöneticisi tarafından değiştirilir; değişikliğin broker'a atomik yüklenmesi ve cache invalidation kabul edilmelidir. |
| Broker socket | `/run/yuva/broker.sock`; #514 önerisi parent `root:root 0755`, socket `root:yuva-clients 0660` | Grup üyeliği yalnız bağlantı kurabilme kapısıdır; principal kernel `SO_PEERCRED` UID'sinden türetilir. Bağlantı, tüm işlem/read yetkilerini vermez. Socket başlangıçta broker tarafından güvenli biçimde yeniden yaratılmalı; symlink/yanlış owner/mode halinde servis açılmamalı. |
| Panel | Agent/broker'dan ayrı, yalnız projeksiyon okuyan servis kimliği önerisi | Panel UID'si ve read-only socket scope'u henüz operatör kararıdır. Loopback HTTP, aynı network namespace'deki başka UID'leri yalıtmaz; `/api/veri` ve açık POST erişimi ayrı çözülmelidir (`docs/local-data-threat-model.md`). |
| Yuva ortak task/message state | Agent UID'lerine doğrudan writable verilmez; tek sahip/yazıcı ve yetkili istemci protokolü gerekir | Bu state-service yolu mevcut CLI/panelde uygulanmış değildir. Broker yalnız presence broker'ı olarak kalırsa görev, mesaj ve ekran dosyalarının güvenli ortak yazımı çözülmüş sayılmaz (#524 notu). |

## Hesap ve user manager yaşam döngüsü

1. **Provisioning girdileri:** principal adı, numeric UID, benzersiz hesap adı, ayrı HOME, `XDG_RUNTIME_DIR`, broker map kaydı, izinli socket/read scope, task/data scope, credential sahibi, systemd user unit'leri ve revoke sorumlusu kayda geçmeden hesap açılmaz. Bir UID'yi birden fazla agent principal'ına bağlamak veya CLI `--from` değerinden principal çıkarmak yasaktır.
2. **Ayrı home ve kod erişimi:** home ve credential alanı agent UID'sine ait, diğer agent'lardan kapalı olmalıdır. Kanonik release kodu agent'lara salt-okunur sunulmalı; ortak writable repo, Git index/`.git` metadata'sı veya sır içeren kullanıcı home'u paylaşılmamalıdır. Shared task state doğrudan home/ACL üzerinden açılmamalıdır; #524'teki tek sahipli servis ve istemci protokolü gerekir.
3. **Systemd --user manager:** her UID'nin kendi manager'ı ve runtime directory'si vardır. `yuva/bin/yuva` içindeki mevcut manager/linger kontrolleri `systemctl --user`/`loginctl show-user` işlemlerini yalnız çağıran `os.getuid()` için yapar; bir manager'ı başka agent adına yönettiğini kanıtlamaz (`bin/yuva:1008-1042`). Agent unit'leri doğru UID'nin user manager'ında kurulup aynı UID ile çalışmalıdır.
4. **Linger:** `docs/linux-gecis.md` user manager'ının logouttan sonra yaşaması ve rebootta başlaması için hostta `loginctl enable-linger` gerektiğini açıklar. Her agent için linger ayrı ve kalıcı süreç/secret erişimi kararıdır; root/host işletim yetkisi gerektirir. Linger olmadan kullanıcı logoutunda manager ve user unit'leri kapanabilir; reboot sonrası model heartbeat'i otomatik geri gelmiş sayılmaz. Linger ile süreçler logoutta devam eder, dolayısıyla stop/revoke mekanizması zorunludur.
5. **Sır yönetimi:** provider credential'ı yalnız gereken agent UID'sinin okuyabildiği ayrı home/secret broker'da tutulmalı; ortak repo, environment dump, ekran/mesaj JSONL, argv veya log'a kopyalanmamalıdır. Broker UID map'i sır tutmamalıdır. Backup/restore owner, mode, şifreleme, saklama ve credential rotasyonu kararları #458/#501 runbook'larıyla uyumlu olmalıdır.

## UID→principal envanteri

Host yöneticisinin root-owned envanteri en az şu sır içermeyen alanları kaydetmelidir:

| Alan | Neden gerekir |
|---|---|
| `agent_principal`, login hesabı ve numeric UID | Kernel UID'yi tek bir principal'a sabitlemek ve çift eşlemeyi reddetmek |
| `enabled`, rol/scope ve map revision | Yetkiyi kapatmak, değişiklikleri takip etmek ve eski map/cache'i tespit etmek |
| HOME, runtime directory, user manager/unit adları | Dosya, socket ve lifecycle kapsamını doğrulamak |
| socket grubu üyeliği | Yalnız UDS bağlantı erişimini denetlemek; üyeliği kim yönetecek sorusunu kaydetmek |
| credential owner/rotation referansı (secret değeri değil) | Agent sırlarının tek sahipliğini ve revoke/rotation adımını bağlamak |
| provisioning/revoke zamanı, onaylayan operator ve tombstone durumu | UID/kimlik yeniden kullanımını ve eski lease/key kalmasını önlemek |

Harita değişiklikleri schema-valid, atomik ve denetlenebilir olmalı. Map dosyası eski yedeğe dönerse eski UID yetkisi yeniden açılabilir; restore, sadece dosya içindeki revision'a güvenerek güvenli sayılmamalıdır (`docs/auth-state-external-anchor-decision-458.md`).

## Socket ve heartbeat yetkisi

- Broker Unix socket'inde `SO_PEERCRED` ile gerçek peer UID alınır; principal `uid→agent` allowlist'inden bulunur. Gövde `kimlik`, `--from`, görünen ad, rol, PID, unit adı, socket grup üyeliği ve loopback bağlantısı principal değildir (#513, #514).
- Harita dışı/disabled UID, yanlış rol, body↔UID çelişkisi, eski epoch, stale/duplicate sequence ve broker erişim hatası fail-closed olmalıdır. Map lookup, presence mutation ve panel projection'da aynı mapping revision/lease generation kullanılmalıdır.
- Socket grubu bağlanma iznini sınırlar; broker her komutu ayrıca yetkilendirir. Panel read/status kullanır; agent yalnız kendi principal'ı için izin verilen heartbeat/status/stop işlemlerini yapar. Başka principal adına lease kapatma veya state okuma reddedilir.
- Broker veya map kaynağı yoksa, lease stale ise ya da service restart/recovery sonucu belirsizse kart `unknown` kalır. Açık, yetkili ve generation-bound stop doğrulanmadan `offline` üretilmez (#513 ve #494).
- `POST /api/kalp` loopback'e güvenerek heartbeat kabul etmemeli. #514'ün 410/closed hedefi ile `panel/auth_integration_draft.py` içindeki `/api/kalp: self` taslak politikası birlikte çözümlenmeli; yeni feature-off kabul kapısı olmadan eski CLI/panel fallback'i açık bırakılmamalıdır.

## Revoke, kapatma ve geri alma

Önerilen sıranın, yetkili actor ve atomik map yükleme davranışı operatörce seçilmelidir:

1. Root-owned UID map'te agent'ı `disabled` yapıp broker'a yeni revision'ı yükle; yeni heartbeat/status mutation reddedilsin.
2. Broker'da agent'ın etkin lease/capability'sini generation-bound revoke et; panel projection aynı işlemde `unknown` olsun. Cache varsa geçersizleştir; yalnız `account locked` veya grup üyeliği kaldırma anlık lease revoke sayılmaz.
3. Agent user manager'ındaki kalp/model/adapter unit'lerini durdur; linger'ı iptal et veya açık tutma gerekçesini kaydet. Hesabı login'e kapat/lock et ve socket grup üyeliğini kaldır.
4. Agent provider credential'larını revoke/rotate et; backup ve task/message/screen artifact erişimini politikasına göre koru. Secret içeriğini genel Yuva loguna yazma.
5. UID/principal kaydını silmek yerine tombstone/denetim izi tut; yeni agent'a aynı numeric UID ancak eski map, lease, credential, unit ve restore zincirinin kullanılamadığı doğrulandıktan sonra verilsin.
6. State restore/rollback durumunda external trusted anchor yoksa eski snapshot'ı doğrudan açma: offline inceleme, eski credential/lease iptali, yeni epoch ve tam re-provision gerekir (#458, #501). Restore sonrasında TTL dolması tek başına verified offline değildir; bilinmeyen durum `unknown` kalır.

Bu adımlar host kurma talimatı değildir. Hangi actor'ın mapping, account lock, broker revoke, credential rotation ve UID re-use onayı vereceği açık operatör kararıdır.

## Geçiş ve kabul kanıtı

Bu görevde hesap/servis oluşturulmadı; aşağıdakiler yalnız ilerideki host kabul planıdır:

1. Her principal için iki farklı gerçek test UID'si ile broker UDS bağlantısı kur; doğru UID eşlemesini, harita dışı UID reddini ve spoof edilmiş body kimliğinin reddini kanıtla. Sahte credential injection veya `unshare` tek başına host UID/user-manager kabulü değildir.
2. Agent UID'nin broker map/config, başka HOME/credential, ortak KOK, `.kilit`, durum/görev/mesaj/ekran dosyalarını doğrudan okuyup yazamadığını izin testleriyle kanıtla. Panel HTTP/API erişimini ayrıca ölç; filesystem UID farkı loopback erişimini kapatmaz.
3. User manager'ın beklenen UID, HOME, `XDG_RUNTIME_DIR` ve unit ile çalıştığını; linger açık/kapalı davranışının logout, reboot, stop ve revoke durumlarında kabul edilen şekilde olduğunu host operatörü doğrulasın.
4. Mapping disable sırasında eşzamanlı heartbeat, mevcut lease, broker cache ve panel projeksiyonunu test et; yeni heartbeat reddedilmeli, eski lease yeşil kalmamalı, açık stop yoksa unknown/offline semantiği korunmalı.
5. Backup/restore, broker restart, UID yeniden atama ve map rollback testinde eski principal/key/lease'in geri dönmediğini dış anchor veya offline re-provision prosedürüyle kanıtla.
6. Legacy `~/yuva`, `yuva-dev`, `yuva-ui-dev` panel/CLI kopyaları, kurulu ve `contrib` unit'leri ile doğrudan başlatma yolları envantere alınmalı. K18 kapanmadan eski `/api/kalp` writer'ı ortak state'i veya yeşil sonucu tekrar üretemez denemez (#515/#517/#514).

## Açık operatör girdileri

- UID/account sahibi ve provisioning/revoke onaylayıcısı kim; normal login mi service account mu kullanılacak?
- `yuva-clients` grubunu kim yönetir; socket mode/owner ve broker unit'inin system-level sahibi kimdir?
- Panel UID'si broker'dan ayrı mı; panel yalnız read scope ile hangi task/message alanlarını görebilir?
- Agent başına hangi user unit'leri/linger açılır; logoutta devam etmesi gereken süreç hangisidir ve shutdown/rebootta kim yeniden başlatır?
- UID/principal rotasyonunda eski state/backup ne kadar tutulur; UID tekrar kullanımını kim onaylar; hangi dış anti-rollback anchor veya offline re-provision kabul edilir?
- Credential provider/agent başına nerede tutulur ve hangi actor revoke/rotate eder?
- Broker/map/cache tutarlılığı ve TTL için kill-switch üst sınırı nedir? #514 K19 bunu broker, mapping, cache ve TTL ile ölçülebilir tanımlamalıdır.

## Kaynaklar ve kapsam

- `docs/w1b-broker-principal-granularity-513.md` — ayrı UID kararı seçenekleri, UID→principal, socket, spoofing/revoke/restore sınırları.
- `docs/local-data-threat-model.md` — tek UID varsayımı, owner-only KOK, loopback'in farklı UID'lere açık olması.
- `docs/linux-gecis.md` — user manager, D-Bus, linger, logout/reboot ve mevcut heartbeat sınırları.
- `bin/yuva:1010-1050` — manager/D-Bus/linger kontrollerinin çağıran UID kapsamında olması.
- `docs/auth-state-v2-operations.md`, `docs/auth-state-external-anchor-decision-458.md`, `docs/auth-key-rotation-revoke-offline-501.md` — secret, restore, external anchor ve revoke operasyon sınırları.
- `docs/auth-session-bridge-milestone-map-497.md` ve Yuva #514 revizyon geçmişi — operatör kararı, feature-off planı ve açık kabul kapıları.

Bu not kaynak/plan eşlemesidir; hesap, grup, linger, socket, servis, auth, credential, izin veya veri değiştirilmedi. Test, runtime ve deployment çalıştırılmadı. Canlı host durumunun uygun olduğu iddia edilmez; final UID/linger/socket/data sahipliği kararı operatöre aittir.
