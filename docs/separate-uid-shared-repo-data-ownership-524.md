# Ayrı ajan UID'lerinde ortak repo ve Yuva verisi sahipliği (#524)

## Karar özeti

Operatörün W1b kararı model/ajan başına doğrulanmış presence, ajanlar arasında same-UID güveni olmaması ve ajan başına ayrı OS UID tercihidir. Bu karar UID hesapları kurma, mevcut home/veri izinlerini gevşetme veya auth/deployment açma izni değildir.

**En küçük güvenli ortak çalışma modeli:** Kod release'i tek entegrasyon sahibinin kurduğu, ajan UID'lerinin salt-okunur kullandığı bir konumda tutun. Her ajan için ayrı HOME, credential alanı ve kendisine ait yazılabilir worktree/outbox kullanın. Ortak `durum.json`, `gorevler.json`, mesaj ve ekran verisini tek bir `yuva-state` sahibi UID'nin yönettiği servis arkasında tutun; ajanlar yalnız kimlikleriyle bağlanan Unix socket/API üzerinden yetkili görev kapsamını okusun ve izinli mesaj/teslim işlemlerini göndersin. Panel aynı servis üzerinden salt-okunur ve kapsamı sınırlı görünüm alsın. İşlemleri ve JSON dosyalarını doğrudan agent UID'lerine açmayın.

Mevcut CLI/panel, bu servis modelini uygulamıyor: her süreç `YUVA_DIR` içindeki dosyaları doğrudan açıp yazar. Dolayısıyla bugünkü kod için güvenli, ortak ve aynı anda çok-UID yazılabilir bir KOK önerilemiyor. Ajan başına UID kabulü ile ortak tahtayı kullanılabilir tutmak arasında gereken köprü, ayrı bir uygulama ve operatör kararıdır.

## Güncel kaynak gerçekleri

- `bin/yuva` ve `panel/server.py`, `YUVA_DIR` yoksa sırasıyla kendi kullanıcısının `~/yuva` dizinini seçer (`bin/yuva:30`, `panel/server.py:44`). Birden fazla UID varsayılanı kullanırsa her birinin ayrı tahtası olur; tek ortak tahta oluşmaz.
- `docs/local-data-threat-model.md` KOK ve `ekran/` için sahibiyle sınırlı `0700`, JSONL için owner-only `0600` öngörür; aynı UID süreçlerini birbirinden ayırmadığını, loopback'teki panel API'sinin farklı UID'lere de açık olduğunu belirtir.
- Kaynak mevcutta daha katı koşullar uygular: KOK ve alt dizinler euid sahibinde `0700`; `.kilit` euid sahibinde `0600`; JSONL dosyaları euid sahibinde `0600` ve tek hard link olmalıdır (`bin/yuva:81-99, 285-355`; `panel/server.py:93-172, 400-495`). Başka UID'nin aynı dizini paylaşması bu kontrollerden geçmez.
- CLI ve panel aynı `KOK/.kilit` inode'u üzerinde `flock` kullanır. Kilit yalnız birlikte çalışan yazıcıları sıraya koyar; dosya sistemi erişim kontrolü veya actor doğrulaması değildir. Ortak grup/ACL ile doğrudan yazma izni verilmesi, güvenilmeyen bir ajanı kilit almaya zorlamaz.
- CLI ve panel başında `umask(0o077)` ayarlar (`bin/yuva:2263`, `panel/server.py:1767`). Bu yeni dosyalar için varsayılandır; yetki sınırı değildir. Durum dosyası atomik yazımı var olan dosyanın modunu korur, dosya yoksa `0644` kullanır (`bin/yuva:175-193`, `panel/server.py:311-337`). Bu nedenle yeni bir servis/çok-UID düzeni, yalnız umask'a güvenmeden durum dosyalarının owner ve mode değerlerini ayrıca tanımlamalı ve doğrulamalıdır.
- `docs/linux-gecis.md` ve #449, eski/yeni panel ve CLI yazıcılarını aynı KOK üzerinde birlikte çalıştırmamayı, ortak veri kökü ve ortak kilit inode'unu doğrulamayı ister. Farklı `YUVA_DIR` seçen süreçler hem ayrı durum üretir hem kilitleri ayırır.
- `/home/yucel-pc/yuva-v2` bir paylaşılan Git çalışma ağacıdır; HEAD `7fd1437`, mevcut çalışma ağacı kirli. `docs/yuva-cli-update-single-source-plan-486.md` kanonik temiz commit'ten sürümlü, değişmez release ve ayrı veri kökü önerir. Aynı writable checkout'u birden çok agent UID'sine vermek Git index, çalışma dosyaları ve ortak `.git` metadata'sı üzerinde doğrudan çapraz yazma yetkisi verir.
- `docs/local-data-threat-model.md` mesaj/ekran kayıtlarını görev ve kimlik bilgileri sızdırabilecek hassas içerik sayar. `docs/session-adapter-workdir-process-boundary-498.md` child süreçlerine parent environment kopyalanmamasını, sırların `argv`, environment, log ve ortak dosyaya konmamasını önerir. Per-agent HOME/credential ayrımı bu yüzden veri/repo izinleriyle birlikte tasarlanmalıdır.

2026-10-23 salt-okunur izin görünümünde `/home/yucel-pc` `0750`, `yuva-v2` `0775`, `/home/yucel-pc/yuva` ve `ekran/` `0700` idi; `durum.json` ve `gorevler.json` `0664`, `mesaj.jsonl` ve `.kilit` `0600` idi. KOK'un `0700` olması diğer UID'lerin bu dosyalara yol erişimini kapatıyor; JSON dosyalarındaki `0664` tek başına erişim anlamına gelmiyor. Bunlar anlık metadata'dır, host kurulumu veya izin kabulü değildir.

## Sahiplik seçenekleri

| Seçenek | Erişim ve kilit davranışı | Güven sınırı / sonuç |
|---|---|---|
| **A. Ortak grup veya ACL ile doğrudan writable repo + KOK** | Setgid dizin/default ACL ortak yazmayı kolaylaştırabilir; tüm writer'lar aynı inode üzerinde `flock` kullanırsa işbirlikçi yarışlar sıraya girebilir. Mevcut euid, `0700`/`0600` kontrolleri ve `umask`/atomik replace davranışı bu modelle uyumlu değildir; kod izin gevşetmeden çalışmaz. | **Seçilmemeli.** Grup üyeleri JSON, görev/mesaj geçmişi, `.kilit`, Git index ve çalışma ağacını CLI dışından değiştirebilir, kimlik iddialarını taklit edebilir veya kilidi atlayabilir. ACL dosya erişimini verir, actor doğrulaması sağlamaz. Same-UID ajanların güvenilmediği kararla çelişir.
| **B. Ajan başına ayrı checkout ve ayrı KOK** | Her UID yalnız kendi home/worktree/data kopyasını yazar. Ortak release read-only dağıtılır; değişiklikler ayrı branch/patch/outbox ile entegrasyon sahibine gelir. | **İzolasyon için güvenli; ortak tahta değildir.** Görev ve mesajların kopyalar arasında uzlaştırılması ayrıca güvenilir bir servis gerektirir; senkronize kopyaları aynı dosya gibi göstermeyin.
| **C. Ayrı UID'ler + tek sahibin yönettiği ortak state servisi** | `yuva-state` tek UID olarak KOK ve `.kilit` sahibi olur. CLI/panel dosya açmaz; UDS üzerinden komut/snapshot kullanır. `SO_PEERCRED` numeric UID→principal eşler; broker/service endpoint'te işlem yetkisini, task kapsamını ve boyut sınırını kontrol eder. | **Önerilen ortak model.** Dosya formatı ve lock tek sahibin kontrolünde kalır. Socket'e bağlanabilmek state üzerinde genel okuma/yazma yetkisi anlamına gelmez. Panel read-only, worker işlemleri görev/actor politikasıyla sınırlı olmalıdır.

## En küçük uygulanabilir işletim sınırı

1. Release ağacı tek kaynak commit'ten kurulsun ve agent UID'lerine salt-okunur olsun. Yazılabilir Git worktree'leri UID başına ayrışsın; bir agent'ın `.git` metadata'sına başka agent yazamasın. Patch/branch kabulü ayrı entegrasyon hesabında yapılsın.
2. `yuva-state` home'u, KOK'u, yedekleri ve lock inode'unu sahipliği altında tutan tek writer olsun. Mevcut KOK'u agent grubuna açmayın. Yeniden yerleştirme/izin değişikliği host operatörünün ayrı onayı ve uyumluluk planı gerektirir.
3. Unix socket dizini ve socket owner/mode'u host tarafından kurulsun. İzinli agent UID'leri bağlanabilse de service her istekte kernel peer UID'sini doğrulasın; body `kimlik`, rol, CLI `--from`, dosya adı veya görünür ad principal sayılmasın. Agent'lar birbirlerinin secret'larına ve key store'una erişmesin.
4. Servis API'si ihtiyaca göre en az veriyi sunsun: görevli kendi atanmış görevini ve teslim durumunu okuyup raporlasın; genel mesaj/screen geçmişi, admin görevi, diğer agent state'i ve secret'lar ayrı scope gerektirsin. Panel aynı owner state'e salt-okunur, ayrı yetkiyle bağlansın. Mevcut loopback HTTP `/api/veri` ve açık POST uçları bu ayrımı sağlamaz (`docs/local-data-threat-model.md`, `panel/server.py:936-969, 1050-1086, 1143-1192`).
5. `flock` yalnız state servisinin içindeki eşzamanlı yazıcıları sıraya koysun. Event/operation ID, atomik JSON/JSONL yazımı, hata sonrası belirsiz sonuç ve backup/restore mevcut sözleşmeleriyle korunmalı; her agent'a ortak filesystem write ACL'si verilmesi single-writer değildir.
6. Her agent UID için ayrı HOME, `XDG_RUNTIME_DIR`, systemd user manager/linger kararı, provider secret sahipliği, revoke ve home kapatma sırası tanımlansın. Linger kalıcı süreçleri logout sonrası da açık tutar; ayrıca host onayı ve service lifecycle kabulü gerekir (`docs/linux-gecis.md`).

## Uygulama öncesi kabul kanıtı

- Her agent UID'nin release kodunu okuyabildiği, fakat diğer worktree'leri, KOK'u, backup'ları ve secret store'u doğrudan okuyup/yazamadığı gerçek filesystem permission testiyle doğrulansın.
- `yuva-state` UID'sinin yalnız belirlenen KOK/backup dizinlerine eriştiği; agent process'lerin KOK/.kilit veya JSON dosyalarını doğrudan açmasının reddedildiği doğrulansın.
- En az iki ayrı OS UID ile UDS bağlanıp `SO_PEERCRED` üzerinden doğru principal eşlemesi, harita dışı UID reddi, body spoofing reddi ve agentlar arası task/message erişim reddi test edilsin. Sahte peer-credential unit testi bu OS sınırının kanıtı değildir.
- Aynı anda iki izinli task/message mutasyonu servis üzerinden yürütülüp tek sıra, tutarlı event/audit ve doğru owner/mode korunduğu; başarısız/commit-unknown durumda kör retry olmadığı doğrulansın.
- Panel read-only scope'u; `/api/veri` ve yazma uçlarının agent UID'lerinden kimliksiz erişim davranışı ayrı doğrulansın. Loopback'in farklı UID'leri yalıtmadığı unutulmasın.
- Logout, linger, manager/service restart, revoke, UID yeniden atama, backup/restore ve rollback durumlarında önceki UID'nin yetkisinin geri gelmediği doğrulansın. Shared data izinleri veya service/API değişikliği yapılmadan multi-UID kabulü verilmesin.

## Açık operatör kararları

- Worker'ların ortak board'da hangi görev, mesaj ve ekran kayıtlarını okuyacağı; içerik redaction/retention sınırı.
- `yuva-state` ve panel UID/grup sahipliği, UDS path, agent UID allowlist sahibi ve provisioning/revoke yetkilisi.
- Ortak state API'sinin mevcut JSON formatını koruyup korumayacağı ve hangi mutasyonların merkezi servis üzerinden geçeceği.
- Agent worktree'lerinin nerede tutulacağı, patch/branch entegrasyon sahibinin kim olduğu ve sır içeren dosyaların checkout'tan nasıl dışlanacağı.
- Provider credential'larının agent başına ayrı mı tutulacağı, logout/revoke/backup politikası ve linger gereksinimi.

## Sınırlar

Bu not karar seçeneklerini ve kaynak davranışını eşleştirir; operator ownership modeli seçmez. Hesap, grup, ACL, servis, repo veya veri değişikliği yapılmadı; test/runtime çalıştırılmadı. Kaynaklar: `docs/local-data-threat-model.md`, `docs/jsonl-retention-design.md`, `docs/jsonl-retention-operator-decisions-449.md`, `docs/jsonl-storage-operator-decisions-496.md`, `docs/linux-gecis.md`, `docs/yuva-cli-update-single-source-plan-486.md`, `docs/yuva-cli-copy-cutover-acceptance-508.md`, `docs/session-adapter-workdir-process-boundary-498.md`, `docs/w1b-broker-principal-granularity-513.md`.
