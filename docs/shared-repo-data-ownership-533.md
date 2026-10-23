# #533 — Ayrı UID’lerde ortak repo ve Yuva veri sahipliği

**Tarih:** 2026-10-23
**Kapsam:** Birden çok ajan UID’si için Git çalışma ağacı, `<YUVA_DATA_ROOT>` veri kökü, sahiplik, izin, kilit, umask/ACL ve izolasyon seçeneklerinin kaynak bazlı karşılaştırması.
**Sınır:** Bu not statik kaynak ve karar incelemesidir. Dosya izinleri, kullanıcı/ACL, repo/veri veya servis değiştirilmedi; test/runtime/host durumu incelenmedi. Canlı sahiplik ve kurulum durumu unknown’dur.

## Kaynak anlık görüntüsü

| Kaynak | SHA-256 |
|---|---|
| `yuva-v2/bin/yuva` | `824a8d4379e45b9e40e7316d418fa3fad918388b11164dc11aab1c7c07ea0510` |
| `yuva-v2/panel/server.py` | `683f1b94847a999eea149b2d33fb918c2eca8151aef389c6f9e4adc2c5615245` |
| `yuva-v2/panel/auth_store_v2.py` | `ea49b35a6d1a57b2dce957717812d6ecaee561e80c51d7847142dc4f7a24f82f` |

## Karar özeti

- **Mevcut kodda ortak yazılabilir KOK yok.** CLI ve panel KOK’u `YUVA_DIR` veya kendi `$HOME/yuva` değerinden seçiyor; KOK’un etkin euid’e ait `0700` dizin olmasını, `.kilit` ve JSONL dosyalarının euid/mode/link koşullarını doğruluyor (`bin/yuva:30-35, 81-148, 277-355`; `panel/server.py:43-50, 84-175, 412-490`). Farklı UID aynı `<YUVA_DATA_ROOT>` yolunu `YUVA_DIR` ile seçse de bu, sahiplik ve erişim koşullarını karşılamaz.
- **En küçük güvenli başlangıç:** Kod release’inin sahibi tek bakım/integrasyon hesabı olsun; ajanlar doğrulanmış, değiştirilmeyen release’i salt okunur kullansın. Kod yazacak ajanlar ayrı clone/worktree kullansın; ajan başına ayrı clone Git metadata izolasyonu için daha nettir. `yuva` KOK’u tek servis/sahip UID’sinde özel kalsın. Ortak Yuva işlevi şu an gerekiyorsa ajanlara doğrudan dosya erişimi vermek yerine veri sahibi UID’de çalışan yetkili broker eklenmelidir.
- **Bugünkü en dar operasyonel seçenek:** Broker uygulanana dek her ayrı UID kendi KOK’unu kullanır; bu ayrı bir tahta demektir. Ortak görev/mesaj verisini güvenli biçimde paylaşma garantisi sağlamaz. Ortak dosya, ACL veya grup yazma hakkı ile bu sınır geçici olarak “çözülmüş” sayılmamalıdır.
- Önceki karar notlarında ajan başına ayrı UID tercihi kaydedilmiş olsa da bu tercih kullanıcı/host kurulumu, ortak repo/veri izni, servis veya auth açılışı için onay değildir (#497/#513; #523/#524 karar notları).

## Kaynakta görülen sözleşmeler

### Yuva veri kökü ve kilit

1. CLI ve panel `YUVA_DIR` verilmezse çağıran hesabın kendi `$HOME/yuva` yolunu kullanır (`bin/yuva:29-35`; `panel/server.py:43-50`). Ayrı UID’lerin varsayılanları ortak kuyruk olmaz. Aynı mutlak yolu env ile vermek de kernel dosya erişimi sağlamaz.
2. `_guvenli_dizin_fd()` KOK’u açarken üst dizin zincirini denetler; son KOK dizini etkin euid sahibi ve tam `0700` olmalıdır (`bin/yuva:277-325`; panel karşılığı `server.py:412-464`). Dolayısıyla farklı euid’in doğrudan aynı özel KOK’u kullanması kaynak kontrolleriyle uyumlu değildir.
3. `kilit_tut()` `.kilit` dosyasını `0600` oluşturur; regular file, euid sahibi, tam kip ve tek hard link denetiminden sonra aynı inode üzerinde `flock(LOCK_EX)` alır (`bin/yuva:81-148`). Panel de aynı `KOK/.kilit` yolunu ve euid/mode doğrulamasını kullanır (`server.py:84-175`). Kilit yazıcıları sıraya koyar; yetki veya UID kanıtı değildir. Başka UID’nin dosyayı açamadığı yerde lock protokolüne katılım da yoktur.
4. JSONL yazıcıları dosyaları `0600` açıp euid/mode/link doğrular (`bin/yuva:235-267, 351-355`; `server.py:486-490`). JSON durum dosyalarının `kaydet()` yolu mevcut dosyanın modunu korur; dosya yoksa `0644` ile başlatır (`bin/yuva:171-190`). Fakat KOK’un `0700` sahibiyle sınırlı olması dizin üzerinden erişimi kapatır; bu `0644` değeri ortak UID erişim sözleşmesi değildir.
5. CLI ve panel başlangıçta `umask(0077)` ayarlar (`bin/yuva:2349-2351`; `server.py:1761-1767`). Umask yalnız yeni dosya/dizin oluşturma maskesidir; mevcut izinleri düzeltmez ve euid/mode kontrollerini değiştirmez. `umask(0002)` veya ACL ile grup yazımı açmak bu kontrollerle uyumlu bir ortak KOK oluşturmaz.
6. Auth store da `0700` kök, owner-only regular files ve `0600` atomic temp writes bekler (`panel/auth_store_v2.py:265-330, 399-429`). Ajan credential’larını ortak repository/data dizinine taşımak veya store’u ajanlar arasında yazılabilir yapmak doğru paylaşım katmanı değildir.

### Panel yolu

Panel `127.0.0.1` loopback’inde dinlemeyi varsayıyor (`panel/server.py:1756-1783`); `GET /api/veri` snapshot verir (`:1676-1688`). Kaynakta socket peer UID’yi alan bir kontrol yok. Farklı UID, dosya sisteminden KOK’a giremese bile aynı host/network namespace içindeki loopback HTTP’ye ulaşabilir. Bu yüzden panel HTTP’si çok UID’li ajanlar için veri broker’ı veya kimlik doğrulama sınırı olarak kabul edilmemeli. HMAC kapısı ayrı bir taslaktır; mevcut server’da opsiyoneldir ve görev/veri kapsamları ayrıca tasarlanmalıdır (`auth_integration_draft.py:1-10, 28-49`).

## Seçeneklerin karşılaştırması

| Model | Repo kodu | Yuva verisi | Avantaj | Sınır / karar |
|---|---|---|---|---|
| Tek bakım UID’si, salt okunur release | Kanonik checkout ve release tek sahibin; ajanlar çalıştırma/okuma erişimli | Tek sahipli `0700/0600` KOK | En küçük ve mevcut kodla uyumlu; yayın ve rollback tek kaynaktan | Ajanlar doğrudan ortak Git değişikliği veya ortak Yuva kuyruğu yapamaz. Kod değişikliği kontrollü entegrasyonla alınır. |
| Ortak grup, setgid, varsayılan ACL, gevşek umask | Birden çok UID aynı source, `.git` index/config/refs/hooks alanını değiştirebilir | Grup üyeleri görev, mesaj, durum ve ekran verisine erişebilir | Kurulumu kolay gibi görünür | Ayrı UID sınırını kaldırır; KOK/lock/JSONL owner+mode kontrolleriyle uyumsuzdur. Önerilmez. |
| Her ajan için ayrı Git worktree | Çalışma dosyaları ayrı; linked worktree’ler ortak ana Git deposunun metadata/ref/object alanlarını paylaşır | Her ajan KOK’u ayrı | Aynı branch’te dosya çakışması azalır | Ana `.git` erişimi ortak yazma kapısıdır; tek başına güçlü UID izolasyonu sağlamaz. Ortak Git metadata’sı bakım sahibinde kalmalıdır. |
| Her ajan için ayrı clone | Repo ve `.git` metadata’sı UID’ye özel | Her ajan KOK’u ayrı | Kod yazma ve Git metadata izolasyonu net | Disk/bakım maliyeti ve kontrollü merge ihtiyacı vardır; ortak Yuva verisi sağlamaz. |
| Tek veri sahibi servis + Unix domain socket | Kaynak modeli bağımsız; ajanlar client | Servis hesabı tek KOK sahibi; dar API ile ortak işlev | Ortak görev/mesaj işlevi sağlayabilir; UID/principal politikası merkezî | Yeni broker, UID→principal map’i, `SO_PEERCRED`, route/işlem yetkisi, lifecycle/revoke/audit ve fail-closed davranış gerekir. Mevcut CLI/panel bunu sunmuyor. |

### Sahiplik / ACL / lock değerlendirmesi

- **Sahiplik:** Yuva yazıcıları final veri dizinini ve lock/data dosyasını kendi `geteuid()` değeriyle karşılaştırıyor. Aynı KOK’un bir ajan hesabına ait olması diğer UID’lerin uygulama kontrolünü geçirmesini sağlamaz. Ortak grup veya sahipliği `root`/servis hesabına almak, mevcut süreci otomatik olarak o servis hesabı yapmaz.
- **ACL:** ACL bir dosya sistemi erişim kuralıdır; actor→principal veya task-scope politikası değildir. Named user/group erişimi verilmesi, uygulamanın `0700/0600` owner/mode varsayımlarını gevşetmeyi gerektirir veya dosya açılışını reddettirir. ACL’leri genişletip kod kontrollerini etkisizleştirmek yerine yalnız servis UID’si dosyalara erişmelidir.
- **Umask:** `0077` varsayılanı yeni nesneleri private tutar; paylaşım için `0002`ye indirmek mevcut dosyalara etki etmez ve her oluşturma yolundaki açık mode/owner doğrulamasını değiştirmez. Umask tek başına multi-UID paylaşım politikası değildir.
- **`flock`:** Kilit, aynı erişilebilir `.kilit` inode’unda uyumlu writer’ları serileştirir. Kimlerin okuyup yazabileceğini veya `--from` iddiasının doğru olduğunu doğrulamaz. Kilit yolunu başka UID’lere açmak için yalnız `chmod` yeterli değildir; dosya owner, exact mode, no-follow/hardlink ve tüm writer sürümleri birlikte yeniden tasarlanmalıdır.
- **Git:** Ortak writable working tree’de bir ajan kaynak dosyasını ve Git metadata’sını değiştirip diğer ajanın commit/branch/checkout akışını etkileyebilir. Git’in kendi lock dosyaları eşzamanlı Git işlemlerinin bir bölümünü koordine eder; kullanıcılar arası yetki veya repo içeriği güveni sağlamaz. Linked worktree çalışma dosyalarını ayırır, fakat ortak ana repository metadata’sını tümüyle ayırmaz. Güçlü yazma izolasyonu için ajan başına clone; kullanım için salt okunur, manifest/hash’i doğrulanmış release daha kolay denetlenir (#486/#508/#522).

## En küçük uygulanabilir model

1. Bir bakım/integrasyon UID’si kanonik Git kaynağını ve sürümlü release’i sahiplenir. Ajanlar doğrulanmış release’i salt okunur kullanır; kod değiştiren her ajan kendi UID’sine ait clone’da çalışır. Sonuçlar inceleme ve yetkili merge ile kanonik kaynağa alınır.
2. `<YUVA_DATA_ROOT>` mevcut sahibinde özel KOK olarak kalır. Ajan UID’leri doğrudan bu KOK’a, `.kilit` dosyasına, JSON/JSONL dosyalarına veya auth store’a açılmaz. Ayrı `$HOME/yuva` kullanımı izolasyon sağlar ama ortak tahta yerine ayrı state üretir.
3. Ortak görev/mesaj gereksinimi varsa tek sahipli broker ayrı bir çalışma olarak tasarlanır. Broker gerçek peer UID’yi socket’ten alır, operator-managed UID→principal map’i kullanır, `--from`/body alanlarını yetki kaynağı saymaz ve her okuma/yazma işlevine dar policy uygular. Socket grup üyeliği yalnız bağlanma yetkisi verir; görev yetkisi vermez. Panel de aynı broker API’sine sınırlı ve salt okunur scope ile bağlanır.
4. Broker, CLI, panel ve legacy writer’lar ortak dosyaya doğrudan yazmamalı; tek state owner/lock ve tek commit politikası uygulanmalıdır. Presence servisi varsa onun socket’i görev/mesaj veri API’si sayılmaz.

Bu, mevcut kodla hemen açılabilecek ortak KOK değildir. Bugünkü en küçük güvenli durum tek sahipli özel Yuva verisi + read-only release’tir; ortak Yuva board/chat için yeni servis ve operasyon kararı gerekir.

## İlerideki kabul kanıtları

Bu raporda hiçbir kabul denemesi çalıştırılmadı. Uygulama ve host onayı öncesinde en az:

1. Her UID için HOME, credential, repo/clone, data root, runtime ve socket yolunun ayrı sahipliği envanterlensin; exact release commit/tree/hash ve tek writer kaydı tutulsun.
2. Gerçek farklı UID’lerle (a) diğer UID’nin KOK/lock/task/message/secret dosyalarına doğrudan erişiminin reddedildiği, (b) read-only release’i okuyup çalıştırabildiği, (c) kendi clone’unda kod yazabildiği doğrulansın.
3. Broker gerekiyorsa `SO_PEERCRED` UID→principal eşlemesi, unknown UID reddi, sahte `--from`/body kimliğinin etkisizliği, operation-specific scope, task/chat data minimization ve servis yokken fail-closed davranış kanıtlansın.
4. Panel HTTP’nin loopback’e erişebilen UID’lere ne sunduğu ayrıca ölçülsün; file mode testi HTTP erişim sınırını doğrulamaz.
5. Eski ve yeni CLI/panel kopyalarının aynı KOK’a eşzamanlı yazmadığı ve broker devreye alındıysa tüm writer’ların doğrudan dosya erişiminin kapandığı doğrulansın (#508). Restore/revoke ve UID yeniden kullanımı ayrı yaşam döngüsü kabulüne bağlansın (#523).

## Sonuç

Ortak grup/ACL ve gevşek umask, sahiplik izolasyonunu ortadan kaldırıp mevcut euid/mode kontrolleriyle çatışır. Ortak `flock` yalnız senkronizasyon sağlar. Git worktree çalışma dosyalarını ayırır ama ortak repo metadata’sını koruma sınırı yapmaz; ajan başına clone veya salt okunur release daha uygundur. Yuva state’i için en küçük güvenli model tek sahibi korumak, ortak erişimi gerekiyorsa UID doğrulamalı tek yazıcı broker eklemektir. Mevcut HTTP loopback’i veya presence broker’ı tek başına bu veri servisi yerine geçmez.

## Kaynaklar

- `yuva-v2/bin/yuva:29-35, 81-148, 171-205, 277-355, 2349-2351`
- `yuva-v2/panel/server.py:43-50, 84-175, 412-490, 1676-1688, 1756-1783`
- `yuva-v2/panel/auth_store_v2.py:265-330, 399-429`
- `docs/yuva-cli-update-single-source-plan-486.md`; `docs/yuva-cli-copy-cutover-acceptance-508.md`
- `docs/w1b-broker-principal-granularity-513.md`; `docs/agent-uid-host-operations-523.md`; `docs/shared-repo-data-ownership-separate-uids-524.md`
