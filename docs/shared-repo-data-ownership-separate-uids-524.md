# Yuva #524 — Ayrı UID'lerde repo ve veri sahipliği

**Kapsam:** Ortak Git çalışma ağacı ve `/home/yucel-pc/yuva` verisinin birden çok ajan UID'siyle paylaşım seçeneklerini kaynaklardan değerlendirme. Bu notta dosya izinleri, kullanıcılar, ACL, repo, veri veya servis değiştirilmedi; test/runtime çalıştırılmadı. Canlı izin ve süreç durumu yeniden ölçülmedi.

## Karar özeti

Kullanıcının kaydedilmiş tercihi, ajan başına ayrı OS UID'dir; aynı UID'deki ajanlar birbirine karşı güvenilir sayılmaz ve trusted launcher varsayılmaz (`docs/auth-session-bridge-milestone-map-497.md`, §Presence; `docs/w1b-broker-principal-granularity-513.md`, §3). Bu tercih, ortak yazılabilir repo veya veri köküne izin verildiği anlamına gelmez.

En küçük güvenli başlangıç modeli:

1. Kanonik kaynak ve sürümlü release tek bir bakım sahibinde kalır. Ajan UID'leri release'i salt okunur kullanır; kod değişikliği gereken ajanlar kendi UID'lerine ait ayrı clone/worktree'de çalışır. Sonuçları kanonik kaynağa yetkili entegrasyon sahibi alır.
2. `/home/yucel-pc/yuva` tek sahibi olan, özel veri kökü olarak kalır. Ayrı UID'li ajanlar burayı doğrudan okuyup yazamaz. Paylaşılan görev/mesaj erişimi gerekiyorsa, UID'yi `SO_PEERCRED` ile doğrulayan ve kapsamı daraltılmış yerel servis/protokol gerekir.
3. Yalnızca presence brokerı eklemek görev/mesaj verisine erişim sağlamaz. Mevcut panelin loopback HTTP uçları farklı UID'yi doğrulamaz; panelin ve CLI'ın aynı özel veri kökünü doğrudan kullanması mevcut kodda euid/sahip/mode kontrollerine takılır.

Dolayısıyla bu modelde çalışma ağacı ve Yuva verisi için ortak yazma grubu, geniş ACL veya `umask` gevşetmesi kullanılmamalıdır. Bu ayarlar ayrı UID sınırını kaldırır; mevcut veri yazıcılarının sahiplik ve izin kontrollerini de karşılamaz.

## Kaynakların bugünkü sözleşmesi

| Kaynak davranışı | Kod veya karar dayanağı | Ayrı UID sonucu |
| --- | --- | --- |
| CLI kod kökünü çalıştırılan dosyanın çözülmüş yolundan, veri kökünü `YUVA_DIR` veya o sürecin `$HOME/yuva` yolundan seçer. Panel de aynı varsayılanı kullanır. | `bin/yuva:29-35`; `panel/server.py:43-50`; #486 §Sahiplik | Aynı `YUVA_DIR` değerini vermek tek başına erişim vermez. Farklı UID'nin HOME varsayılanı başka bir `yuva` dizinine gider. |
| KOK ve ekran alt dizini tam `0700`, sahibi etkin euid olmalıdır. Güvenli üst dizin kontrolleri de uygulanır. | `bin/yuva:277-325`; `panel/server.py:277-350`; `docs/local-data-threat-model.md:21-33` | Başka UID'nin doğrudan erişimi reddedilir. ACL ile izin eklemek, mode/owner doğrulamasını geçersiz kılmaz; KOK'u genişletmek kodun beklediği güvenlik koşulunu bozar. |
| JSONL dosyaları `0600` yaratılır; düzenli dosya, euid sahibi, tam mode ve tek hardlink kontrolleri yapılır. | `bin/yuva:243-263, 351-355`; `panel/server.py:353-402, 486-490` | Ortak grup okuma/yazma izni mevcut doğrulamayla uyumsuzdur. Aynı UID altında ise bu kontroller süreçler arası gizlilik sağlamaz. |
| `.kilit` dosyası `0600` oluşturulur, euid sahipliği/mode/nlink doğrulanır ve `flock` alınır. Aynı dosya CLI ve panel JSONL/state işlemlerini koordine etmek için kullanır. | `bin/yuva:81-148`; `panel/server.py:84-90` | Kilit, erişim denetimi veya UID kimliği değildir. Dosya başka UID'ye açılmaz; sahiplik kontrollerini gevşetmek de kilidi tehdit modeline göre yeniden tasarlamadan güvenli ortaklaşa kullanım sağlamaz. |
| CLI ve panel başlangıçta `umask(0077)` ayarlar. JSONL ve auth store özel dosya kipleriyle açılır; auth store kökü de euid'e ait `0700` olmalıdır. | `bin/yuva:2350`; `panel/server.py:1767`; `panel/auth_store_v2.py:265-327, 399-429` | Grup erişimi umask ile varsayılan olarak üretilmez. Auth store'un paylaşımı da ajan başına UID modelinin dışında tutulmalıdır. |
| Panel TCP loopback'te dinler; `/api/veri` kayıtları sunar ve API handler'ları loopback istemcisinin OS UID'sini eşlemez. | `panel/server.py:1676-1684, 1756-1783`; `docs/local-data-threat-model.md:22-27, 33` | Aynı network namespace'teki farklı UID panelden hassas veriyi okuyabilir veya açık POST uçlarını çağırabilir. Dosya izinleri bu HTTP yolunu kapatmaz; loopback kimlik doğrulama değildir. |

Bu kaynak kontrolleri Yuva veri kökünde farklı UID'ler için ortak yazma/okuma sözleşmesi sunmuyor. JSONL kilidi eşzamanlı, işbirlikçi süreçler içindir; kötü niyetli aynı UID süreçlerine veya yetkisiz UID'lere karşı kimlik kanıtı değildir. JSON state dosyalarının atomik `os.replace` ile kaydedilmesi de çoklu UID sahiplik/izin sorununu çözmez (`bin/yuva:171-205, 411-417, 1987-1993`).

## Paylaşım seçeneklerinin karşılaştırması

| Seçenek | Repo çalışma ağacı | Yuva veri kökü | Güvenlik ve işletim sonucu |
| --- | --- | --- | --- |
| Tek bakım UID'si; ajan UID'lerine salt okunur kaynak | Kanonik repo ve `.git` tek sahibinde; kurulu release ajanlara yalnız okuma/çalıştırma verir. | `0700/0600` tek sahibinde kalır. | En küçük model. Ajanlar kaynak okuyup release çalıştırabilir; doğrudan ortak Yuva tahtası kullanamaz. |
| Ortak grup + setgid + varsayılan ACL + gevşek umask | Birden çok UID aynı dosya ve `.git` metaverisini değiştirebilir. | Grup üyeleri ortak mesaj/görev/state dosyalarına erişebilir. | Ajan başına UID ayrımını kaldırır. Kod içindeki euid, `0700/0600`, nlink ve owner kontrolleri bu düzeni reddeder; kontrolleri gevşetmek kapsamlı yeni tasarım ister. |
| Ajan başına Git worktree | Her worktree ayrı çalışma dosyaları sağlar; Git worktree'leri yine ortak ana depo metaverisini ve referansları paylaşır. Ana `.git` yazılabilir ortaksa UID'ler arası sınır zayıftır. | Her UID'nin özel veri kökü kalır. | Çalışma dosyası çakışmalarını azaltır; ortak Git metaverisi için tek yazma sahibi gerekir. Güçlü ayrım için ayrı clone veya salt okunur kaynaktan üretilmiş release daha basittir. |
| Ajan başına ayrı clone | Her ajan kendi repo ve `.git` alanına yazar; kanonik kaynağa değişiklikler kontrollü entegrasyonla alınır. | Ayrı ve erişilemez kalır. | Güçlü kod yazma ayrımı sağlar; disk ve bakım maliyeti artar. Ortak state erişimi sağlamaz. |
| Tek sahipli veri servisi/broker + UID doğrulamalı IPC | Kod düzeni bağımsız kalır. | Yalnız servis hesabı veriye erişir; broker UID→principal eşlemesi ve yetkili sınırlı işlemler sunar. | Ajanlar ortak görev/mesaj işlevi kullanabilir. `SO_PEERCRED` ve her işlem için yetki politikası gerekir. Presence brokerı için tasarlanan socket, veri API'si ayrıca tasarlanıp yetkilendirilmedikçe görev/mesaj brokerı sayılamaz. |

## Sahiplik, kilit, umask ve ACL değerlendirmesi

- **Sahiplik:** Özel KOK ve auth store için mevcut uygulama sahibi `geteuid()` ile eşleştiriyor. Farklı UID'nin dosyayı okuyabilmesi için owner-only modları gevşetmek kod kontrolleriyle çelişir. Dosyanın sahipliğini ortak/başka UID'ye almak mevcut çalışan CLI/panelin euid beklentisini karşılamaz.
- **Kilitler:** `flock` aynı erişilebilir inode üzerinden eşzamanlı işlemleri sıraya koyar; kimin kilidi almaya yetkili olduğunu tanımlamaz. Yuva `.kilit` dosyasının 0600/euid doğrulaması başka UID'lerin ortak lock kullanmasını engeller. Ortak erişim eklemek, lock dosyası yaşam döngüsü ve bütün state writer'ları için ayrıca gözden geçirilmelidir.
- **Umask ve ACL:** `umask(0077)` yeni dosya/dizinlerde grup erişimini kapalı tutar. `umask(0002)` veya ACL ile grup hakkı vermek, güven sınırı yerine geçmez; aynı gruptaki her ajan diğerinin yazdığı kod ve veriye erişebilir. POSIX ACL, uygulamanın açık owner/mode kontrollerini atlatmaz.
- **Git çalışma ağacı:** Paylaşılan writable working tree'de bir ajan kaynak dosyalarını, `.git/index`/config/hooks veya branch/ref durumunu değiştirebilir; eşzamanlı branch/checkout işlemleri görev kapsamlarını karıştırabilir. `.git` içindeki lock dosyaları tek tek yazımları koordine etse de kullanıcı başına güvenli çalışma alanı veya yetki politikası sağlamaz. Shared worktree yerine tek kanonik kaynak + değiştirilmeyen release ve ajan başına ayrı clone/worktree tercih edilmelidir.
- **Dosya kilidi kapsamı:** Uygulama `.kilit` dosyasını JSONL append ve durum/görev oku-değiştir-yaz akışlarında kullanır. Kilit, panel alt süreci görev çalıştırırken açık tutulmaz; bu kilide ortak UID'lerin aynı veri dosyalarını güvenle yazabileceği anlamı yüklenmemelidir (`panel/server.py:1318-1322`).

## En küçük uygulanabilir model ve kabul kapıları

**Şimdi uygulanabilir sınır:** tek bakım sahibi kanonik kaynak/release'i yönetir; ajan başına ayrı UID + ayrı HOME/runtime kullanılır; ajanların kaynak kodu salt okunur release'ten çalışır veya özel clone/worktree'si olur; Yuva veri kökü ve auth store tek sahipte kalır. Ajan UID'leri doğrudan `/home/yucel-pc/yuva` erişimi almaz. Bu, kaydedilmiş tercih ile uyumludur ve mevcut dosya güvenlik kontrollerini korur; ancak ajan başına ayrı Yuva board/chat erişimini henüz sağlamaz.

Ortak Yuva işlevi eklenmeden önce en az şunlar tasarlanıp doğrulanmalıdır:

1. Broker hesabı ve UID→principal envanteri; yalnız ilgili Unix socket'e gereken UID'ler erişir. Principal request body'den alınmaz.
2. Görev, mesaj, ekran ve okuma uçları için ayrı yetki kapsamı; hassas `/api/veri` snapshot'ının farklı UID'lere açılıp açılmayacağı açık karara bağlanır. Bugünkü loopback HTTP bu şartı karşılamaz.
3. Veriye tek yazma sahibi olan servis ve IPC sözleşmesi; CLI/panel/legacy writer'ların ortak dosyalara doğrudan yazmadığı kanıtlanır. Broker'ın kendi state ve lock dosyaları da yalnız servis UID'sine ait kalır.
4. Revocation, UID tekrar ataması, servis restart/linger, backup/restore ve stale lease için lifecycle kanıtı; eski UID/lease yeni ajanın principal'ı olarak kabul edilmez.
5. Gerçek farklı UID'lerle dosya erişimi reddi, broker peer doğrulaması, yetkisiz read/write reddi ve servis kesintisinde `unknown`/fail-closed davranışını ölçen ayrı kabul planı. Bu belge test veya host kurulum yetkisi vermez.

Kaydedilmiş operatör tercihi ajan başına ayrı UID yönündedir; bu tercih kullanıcı/host kurulumu, ortak repo/veri izinleri, servis yaratma veya auth açılışı onayı değildir. Bu not yalnız statik kaynak analizi ve mevcut karar belgelerinin eşlemesidir; canlı izinler, çalışan servisler ve UID kurulum durumu **unknown** bırakılmıştır.

## Kaynaklar

- `docs/w1b-broker-principal-granularity-513.md`, özellikle §§3–5: ajan başına UID, socket kimliği, ortak writable repo/state uyarısı.
- `docs/auth-session-bridge-milestone-map-497.md`, §Presence ve kullanıcı kararı: same-UID threat model ve tercih edilen principal sınırı.
- `docs/local-data-threat-model.md`, §§2–4: KOK owner/mode, panel HTTP ve mevcut tek kullanıcı güven sınırı.
- `docs/yuva-cli-update-single-source-plan-486.md`, “Envanterden çıkan karar”, “Güncelleme akışı” ve “Geri alma”: kanonik kaynak, immutable release, `current` ve ayrı `YUVA_DIR`.
- `docs/yuva-cli-copy-cutover-acceptance-508.md`, geçiş ve rollback kabul koşulları.
- Kaynak: `bin/yuva`, `panel/server.py`, `panel/auth_store_v2.py`, `contrib/systemd/yuva-panel.service` (yukarıda ilgili satırlar verilmiştir).
