# #513 — W1b broker principal granülaritesi için operatör karar notu

**Durum:** Öneri ve kabul soruları; **principal modeli seçilmedi.**
**Kapsam:** Yalnız tasarım/karar notu. Kod, credential, servis/runtime, auth gate veya panel davranışı değiştirilmedi; test çalıştırılmadı.
**Tarih:** 2026-10-23

## 1. Kısa sonuç

W1b’de “kim çevrimiçi?” sorusunun cevabı, principal granülaritesine bağlıdır. Aynı host UID’si altında çalışan birden fazla ajanı **SO_PEERCRED tek başına ayıramaz**. Bu nedenle:

- **Host runtime görünürlüğü** yeterliyse: host UID principal’ı en küçük dürüst seçenektir; model kartları yeşil olmaz.
- **Her ajan/model ayrı çevrimiçi görünmeli** isteniyorsa: ya **ajan başına ayrı OS UID** ya da **güvenilir launcher’ın per-session capability/socketpair** modeli gerekir. İkincisi, aynı UID’deki süreçlerin birbirine karşı tehdit kabul edilip edilmediğine bağlıdır.
- Bugünkü `--from`/`kimlik`, loopback, PID, unit adı veya dosyaya yazılan heartbeat **principal kanıtı değildir**.

**Önerilen varsayılan (karar değil):** Ürün hedefi netleşene kadar **A — host UID principal’ı**nı yalnız host/runtime göstergesi olarak kullanmak; model bazlı presence’ı `unknown` bırakmak. Model bazlı presence zorunluysa güvenli varsayılan **B — ajan başına ayrı OS UID**; **C — güvenilir launcher** ancak same-UID tehdit modeli ve capability gizliliği kanıtlanırsa.

## 2. Mevcut kanıt ve sınır

- `/api/kalp` doğrulanmış broker principal olmadığı için **503** döndürüyor; `/api/veri` tüm kayıtlar için `online=false`, `presence_state=unknown`, `presence_verified=false` üretiyor (`panel/server.py`, `api_kalp()` ve `veri()`).
- `yuva baglan` yalnız **roster** kaydıdır; presence/heartbeat üretmez. `cmd_kalp` ve `cmd_kalp_dongu` principal yokken fail-closed durur (`bin/yuva`).
- Eski `host_kalp_baslat`/systemd unit, `InvocationID`, `MainPID`, sağlık dosyası ve `.dur` izleri **süreç/unit liveness** kanıtıdır; model/principal kimliği değildir (#338).
- Auth store aynı UID süreçlerine karşı dosya izniyle yalıtım sağlamaz; `0700` store bile aynı UID’deki süreçleri birbirinden ayırmaz (`docs/auth-state-v2-operations.md`).
- TTL dolması **unknown**’dır; yalnız yetkili brokerın açık, generation-bound stop/exit gözlemi **offline** kanıtıdır (`docs/panel-presence-source-options-494.md`).
- Auth-state restore’u eski generation/key revoke/nonce durumunu geri alabilir; aynı host’taki bir sidecar veya `generation_floor` tek başına anti-rollback garantisi değildir (`docs/auth-state-external-anchor-decision-458.md`).

## 3. Seçenekler

### A — Aynı host UID + Unix socket + `SO_PEERCRED`

**Ne kanıtlar:** Broker’a bağlanan sürecin kernel tarafından bildirilen gerçek UID’si. Sabit `host-user:<uid>` principal’ı için kullanılabilir.

**Sınır:** Aynı UID altındaki bütün ajanlar, terminaller ve CLI süreçleri aynı principal’a düşer. Başka bir ajan `--from` ile istediği model adını yazabilir; PID, argv, unit adı veya socket’e bağlanan süreç bunu ayırmaz. Broker aynı UID’de çalışıyorsa güven sınırı iyileşmez.

**Uygun olduğu yer:** “Bu host hesabında bir Yuva istemcisi yaşıyor” demek yeterliyse; model kartlarında yeşil üretmeden ayrı host göstergesi.

**Kabul ölçütü:**

- Broker ayrı servis/UID veya en azından ayrı, erişimi kısıtlı Unix socket üzerinde çalışır.
- `SO_PEERCRED` ile UID okunur; principal gövdedeki `kimlik`/`--from`’dan değil, sabit UID→`host-user:<uid>` eşlemesinden türetilir.
- Farklı UID/yanlış peer reddedilir; legacy `kimlik` fallback’i yoktur.
- Lease TTL, broker epoch, replay/sequence ve restart davranışı #337’deki gibidir.
- Panel model kartlarına host lease’i yazılmaz; ayrı “host runtime” alanı kullanılır.

### B — Ajan başına ayrı OS UID

**Ne kanıtlar:** Kernel’in bağlantı anındaki gerçek UID’si; broker UID→principal eşlemesiyle her ajanı ayırabilir. Aynı UID’den başka ajan adına bağlanma reddedilir.

**Sınır:** En güçlü yerel OS sınırıdır, ancak her ajan için servis hesabı, user manager/linger, dosya ve socket izinleri, repo/secret erişimi ve operasyonel provisioning gerekir. Ortak writable repo/state bu sınırı bozabilir. Root/OS yöneticisi yine güven köküdür.

**Uygun olduğu yer:** Aynı host UID’sindeki ajanların birbirine karşı düşmanca kabul edildiği veya model bazlı presence’ın gerçekten istendiği üretim düzeni.

**Kabul ölçütü:**

- Her ajan için ayrı UID ve ayrı systemd user manager/runtime yolu; broker socket’ine yalnız ilgili UID erişir.
- Broker, UID→agent principal eşlemesini kendi konfigürasyonundan tutar; request body’deki ad/rol bu eşlemeyi değiştiremez.
- Ajan hesabı devre dışı bırakıldığında lease/credential anında reddedilir; eski lease yeni epoch ile online olamaz.
- Ortak repo/veri dizinleri için yazma sahipliği ve paylaşım politikası ayrıca tanımlanır; “aynı UID değil” tek başına uygulama güvenliği sayılmaz.

### C — Güvenilir launcher’dan per-session capability/socketpair

**Ne kanıtlar:** Launcher, model/ajan kimliğini oturuma kendisi bağlar; capability yalnız o oturuma FD/socketpair ile aktarılır. Broker capability’yi doğrular ve principal’ı capability’den türetir; model adı heartbeat gövdesinden seçilemez.

**Sınır:** Aynı UID’deki diğer süreçler launcher’a, `/proc/<pid>/fd`’ye, süreç belleğine veya ortak dosyaya erişebiliyorsa capability çalınabilir/taklit edilebilir. `SO_PEERCRED` bunu tek başına çözmez. Launcher’ın kendisi güvenilir değilse yeni bir sahte principal üreticisi olur. Capability’nin argv, environment, log veya ortak okunur dosyaya konması yasaktır.

**Uygun olduğu yer:** Launcher her oturumu güvenilir biçimde başlatıyor, capability’yi yalnız FD ile veriyor ve aynı UID tehdidi açıkça kabul edilmişse. Aksi hâlde B’ye geçilmelidir.

**Kabul ölçütü:**

- Launcher principal→session bağını önceden kurar; capability tek oturumluk, kısa ömürlü ve rastgeledir.
- Aktarım yalnız inherited FD/socketpair; argv/env/log/dosya yok.
- Broker capability generation/epoch/sequence ve TTL doğrular; eski capability yeni lease açamaz.
- Oturum sonu/launcher çıkışı/revoke capability’yi geçersiz kılar; panelde `unknown`’a düşer.
- Same-UID saldırganın FD/memory erişimi threat modelde açıkça yazılır; kabul edilemiyorsa B zorunludur.

### D — Aynı UID + per-agent HMAC anahtarı (karşılaştırma)

Bu, A’nın HMAC’li varyantıdır; tek başına principal granülaritesi sağlamaz. Aynı UID’deki süreçler anahtarı okuyabilir, kopyalayabilir veya başka principal adına imza atabilir. HMAC; B veya C ile birlikte taşıma doğrulaması olarak anlamlıdır. Auth store’daki `0700` izinleri de same-UID yalıtımı değildir.

## 4. Karşılaştırma

| Ölçüt | A — host UID | B — ayrı OS UID | C — trusted launcher | D — same-UID HMAC |
|---|---|---|---|---|
| Kimlik granülaritesi | Host hesabı | Ajan başına | Ajan/oturum başına (launcher doğruysa) | Principal başına iddia; same-UID’de ayrım zayıf |
| Aynı UID’de spoofing | Açık | Yok (UID ayrı) | Launcher/FD gizliliğine bağlı | Anahtar okunursa açık |
| Kurulum | En küçük | Yüksek: hesap, servis, izin, repo | Orta-yüksek: launcher, FD protokolü, adapter | Orta: secret dağıtımı |
| Secret taşıma | Gerekmez (SO_PEERCRED) | UID/socket erişimi; secret opsiyonel | FD; dosya/env yok | Dosya/secret; same-UID riski |
| İptal/revoke | UID eşlemesi/socket erişimi | Hesap/UID eşlemesi + lease | Capability generation/session sonu | Key revoke; same-UID kopya riski |
| Restart | Yeni broker epoch; eski lease geçersiz | Aynı + hesap servisi | Launcher/broker epoch; eski capability geçersiz | Store/key restore riski |
| Rollback | Auth store rollback ayrı risk | Aynı; eski UID/key geri gelebilir | Eski capability/session geri gelebilir | Eski key/nonce geri gelebilir |
| Model bazlı yeşil | **Hayır** | Evet (doğru provisioning ile) | Evet (launcher kanıtlanırsa) | Tek başına güvenilir değil |
| Operatör yükü | Düşük | Yüksek | Orta-yüksek | Orta |

## 5. Spoofing, rotasyon, revoke ve rollback etkileri

### Spoofing

- `--from`, gövdedeki `kimlik`, görünen ad, rol, PID, unit adı, terminal ve ekran satırı **kimlik kanıtı değildir**.
- A’da aynı UID’deki herhangi bir süreç broker’a bağlanıp başka ajan adına heartbeat verebilir; bu nedenle A yalnız host hesabı seviyesinde dürüsttür.
- B’de kernel UID’si farklı olduğundan başka ajanın UID’sini taklit etmek normal kullanıcı için mümkün değildir; root/compromised hesap yine güven köküdür.
- C’de capability çalınmadıkça taklit zorlaşır; aynı UID’de FD/memory erişimi varsa bu iddia kanıtlanamaz.
- D’de per-agent HMAC anahtarı aynı UID tarafından okunabiliyorsa spoofing açıktır; “her ajana ayrı key” tek başına yeterli değildir.

### Rotasyon

- A: broker principal eşlemesi/UID sabit olduğundan rotasyon daha çok socket/erişim ve broker epoch yönetimidir; eski lease yeni epoch’ta geçersiz olmalıdır.
- B: ajan hesabı/UID eşlemesi ve socket ACL’si yenilenir; eski hesap kapatılır, yeni principal’a geçilir. Repo/secret erişimi de taşınmalıdır.
- C: launcher yeni session capability üretir; eski capability aynı generation’da yeniden kullanılamaz. Launcher restart’ı tüm eski capability’leri geçersiz kılmalıdır.
- D: HMAC key rotation’da yeni key önce doğrulanır, overlap sonrası eski key revoke edilir; `CommitUnknown`’da kör retry yapılmaz (`docs/auth-key-lifecycle-api-design-462.md`).

### Revoke

- Revoke yalnız doğrulanmış principal/admin tarafından yapılmalıdır; bir ajan başka ajanın lease’ini kapatamaz.
- A’da UID→principal eşlemesi veya socket erişimi kaldırılır; B’de hesap/UID devre dışı bırakılır; C’de capability generation iptal edilir.
- Revoke sonrası aynı credential/capability ile yeni heartbeat reddedilir; eski lease TTL sonunda `unknown` olur, açık stop yoksa “offline” denmez.

### Rollback / restore

- Auth store eski snapshot’a dönerse eski key revoke’ları, nonce’lar ve generation geri gelebilir; bu, B/C/D’nin principal doğrulamasını da zayıflatır.
- Aynı host’taki `generation_floor`, sidecar veya dosya yedeği same-UID/root tehdidine karşı bağımsız değildir (`docs/auth-state-external-anchor-decision-458.md`).
- Otomatik rollback algılama gerekiyorsa ayrı trust domain’de CAS anchor veya TPM monotonic counter; yoksa restore yalnız **offline re-provision + tüm eski credential’ları iptal** ile yapılmalıdır.
- Broker restart yeni epoch açmalı; persist edilmiş eski lease/heartbeat `online` yapmamalıdır. Panel/broker erişilemezse `unknown` korunmalıdır.

## 6. Önerilen varsayılan ve sınırı

**Bu not bir seçim yapmaz.** Operatör kararı için önerilen sıra:

1. **Ürün hedefi “host runtime çevrimiçi mi?” ise:** A — host UID principal’ı, ayrı broker UID/socket, `SO_PEERCRED`, sabit UID→`host-user:<uid>` eşlemesi. Model kartları yeşil olmaz; host göstergesi ayrı olur.
2. **Ürün hedefi “her ajan/model ayrı çevrimiçi mi?” ise:** B — ajan başına ayrı OS UID. Same-UID ajanlar birbirine düşmense bile, model bazlı iddia için en dürüst yerel sınır budur.
3. **Güvenilir launcher zaten varsa ve same-UID tehdidi kabul ediliyorsa:** C — per-session capability/socketpair; aksi hâlde B’ye geçilmeden model bazlı yeşil açılmamalıdır.
4. **Hiçbiri yoksa:** Mevcut fail-closed davranış korunur; presence `unknown`, `online=false`, `presence_verified=false`.

## 7. Operatöre kabul soruları

1. “Çevrimiçi” ile **host runtime/Yuva istemcisi** mi, yoksa **belirli model/ajan oturumu** mu kastediliyor?
2. Aynı host UID’si altındaki ajanlar birbirine karşı **düşman** mı, yoksa ortak güven kökü mü? A seçeneğinin dürüstlük sınırı buna bağlı.
3. Her ajan için **ayrı OS UID** operasyonel olarak kabul edilebilir mi? Repo, secret, systemd user manager, dosya izinleri ve backup buna göre ayrılabilir mi?
4. Güvenilir bir **launcher** var mı? Her oturuma capability/FD’yi argv/env/log/dosya olmadan verebilir ve oturum sonunda iptal edebilir mi?
5. Aynı UID’de kalan ajanların `/proc/<pid>/fd`, süreç belleği veya launcher’a erişimi **kabul edilebilir** mi? Edilemiyorsa C tek başına yeterli değildir.
6. Principal’ı kim **issue/revoke** edecek: operatör mü, broker mı, launcher mı? Admin allowlist ve offline provisioning sahibi kim?
7. Auth-state yedeği geri yüklenirse eski key/lease geri gelmesi **kabul edilebilir** mi? Değilse external CAS/TPM anchor mı, yoksa offline re-provision mı seçilecek?
8. TTL/expiry sonrası gösterim **unknown** mı olacak? Açık `offline` yalnız generation-bound stop/exit ile mi üretilecek?
9. Eski `--from` heartbeat, eski transient systemd unit’ler ve `bagli` alanı için **sessiz fallback** yasak mı? (Öneri: evet.)
10. Host UID lease’i model kartlarına yazılmayacak mı? (Öneri: evet; ayrı host göstergesi.)

## 8. Kaynaklar

- Yuva #337 — W1b broker principal kabul matrisi.
- Yuva #338 — W1b uygulama sınırı ve bağımlılık keşfi.
- Yuva #340 — W1b principal granülaritesi karar incelemesi.
- Yuva #343 — Presence semantiği: model online ile host heartbeat ayrımı.
- Yuva #494 — `docs/panel-presence-source-options-494.md`.
- `docs/auth-state-v2-operations.md` — auth store, same-UID sınırı, provisioning/restore.
- `docs/auth-key-lifecycle-api-design-462.md` — key rotation/revoke, `CommitUnknown`.
- `docs/auth-state-external-anchor-decision-458.md` — rollback/high-water anchor.
- `docs/auth-key-rotation-revoke-offline-501.md` — offline rotation/revoke operatör akışı.
- `docs/auth-session-bridge-milestone-map-497.md` — #513/#514 bağımlılığı ve presence kapısı.
- `docs/local-api-access-decision-451.md` — yerel HTTP/UDS/HMAC erişim sınırları.
- Linux man-pages, `unix(7)` — `SO_PEERCRED`, `SCM_CREDENTIALS`: https://man7.org/linux/man-pages/man7/unix.7.html
- Linux man-pages, `pidfd_open(2)`: https://man7.org/linux/man-pages/man2/pidfd_open.2.html

## 9. Sonuç

- Aynı UID + `SO_PEERCRED` yalnız **host-account** principal’ı için dürüsttür; ajan başına presence üretmez.
- Ajan başına presence için **B** en güçlü yerel OS sınırıdır; **C** ancak güvenilir launcher ve same-UID threat modeli kanıtlanırsa kullanılabilir.
- Her seçenekte TTL/expiry `unknown`, broker restart yeni epoch, revoke anında etkili, restore ise kontrollü re-provision olmalıdır.
- **Nihai seçim kullanıcı/operatöre aittir.** Bu not, seçim yapılmadan W1b’nin model bazlı yeşil üretmesini önermez.
