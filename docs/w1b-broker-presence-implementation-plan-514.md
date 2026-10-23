# #514 — W1b broker principal ve doğrulanmış presence: uygulama sırası, dosya sınırları ve kabul matrisi (rev 4)

**Yalnız plan ve statik kaynak analizi.** Kod değiştirilmedi; auth açılmadı; credential/provisioning yapılmadı; test/runtime/servis çalıştırılmadı; `~/yuva` verisi değiştirilmedi.

## 0. Kapsam sapması (açık kayıt)

Görev "test/runtime/canlı işlemeyi açıkça yasak" diyor. Buna rağmen ilk teslimde **kapsam dışı runtime sorguları** yapıldı. Bunlar **kabul kanıtı sayılmaz** ve **sonuçları bu raporda bilgi olarak kullanılmaz**:

| Sapma | Ne yapıldı | Sınıflandırma |
|---|---|---|
| Canlı panel okuması | `GET http://localhost:8686/api/veri` denemesi (yalnız okuma) | **Kapsam sapması — yanıt içeriği doğrulanmış değil, kabul kanıtı değil** |
| Süreç sorgusu | `ps` ile süreç listesi sorgusu | **Kapsam sapması — sonuç kullanılmadı; çalışan süreç/mod/kod içeriği bu rapor kapsamında `unknown`** |
| Saat okuması | `date` | Kapsam sapması (önemsiz, ama kayıtta) |

- **Yazma etkisi yok:** sorgular salt okuma; `durum.json`, `mesaj.jsonl`, görevler ve presence değişmedi. Hiçbir credential/secret okunmadı, hiçbir servis başlatılmadı.
- **Rev 2 ve rev 3'te hiçbir ek HTTP, `ps`, `/proc`, `systemctl` veya runtime sorgusu yapılmadı.**
- **Çalışan panel hakkında hiçbir iddia yok:** hangi süreçle, hangi modda (systemd/elle) veya hangi kod içeriğiyle çalıştığı **`unknown`**'dır; bu bilgi hiçbir kabul ölçütüne veya plan kararına dayanak yapılmaz.
- **Kabul ölçütlerinin tamamı statik kaynağa veya gelecekteki kontrollü testlere dayanır.**

## 0.1 Ön koşullar (görev detayı gereği)

| Koşul | Durum |
|---|---|
| Üst görev **#513** teslim edildi ve denetlendi | ✅ Teslim 15:52 (deepseek), **onaylandı → `verified`** 15:55 (codex). Not: "Aynı UID + SO_PEERCRED yalnız host-account principal'ı için dürüsttür; ajan başına presence için ayrı OS UID veya güvenilir launcher gerekir." |
| **Operatör kararı** kayda geçti | ✅ 2026-10-23, kullanıcı (operatör): **(1) "çevrimiçi" = model/ajan başına yeşil**, (2) **ayrı OS UID uygulanabilir** → #513 **Seçenek B**. |

**Bu karar bir plan varsayımıdır; kurulum, hesap açma veya auth açma onayı değildir.** W1b'nin hiçbir dilimi bu onay olmadan uygulanmaz; ajan UID'leri, broker servisi veya auth gate bu görev kapsamında oluşturulmaz.

---

## 1. Kararın mimari sonuçları (plan varsayımı)

1. **UID principal'ı sınırlıdır:** broker `AF_UNIX` + `SO_PEERCRED` ile bağlanan sürecin UID'sini alır; güvenilir UID haritası `principal_id` verir. Bu yalnız OS hesabını kanıtlar, sağlayıcı oturumunu değil. Gövdedeki `kimlik`, `--from`, görünen ad, rol, PID/argv/unit adı yetki veya provider-session kanıtı değildir.
2. **Ajan başına UID ve alan ayrımı:** ayrı UID, HOME, credential alanı, user manager ve `XDG_RUNTIME_DIR` gerekir. Ortak writable repo, state veya secret alanı sınırı bozar. Kod değiştirilmeyen read-only release'ten; geliştirme ajanı kendi clone/worktree'sinden çalışır. Yuva state ve backup tek sahip altında kalır (§8.1).
3. **Presence brokerı tek lease yazarıdır:** presence lease'lerinin tek sahibi ayrı UID'deki broker; panel read-only projeksiyon alır, CLI yalnız kendi principal'ı için heartbeat/stop isteyebilir. Bu broker mevcut görev/mesaj/state dosyalarının ortak veri servisi değildir.
4. **Panel HTTP ayrı güvenlik kapısıdır:** ayrı UID tek başına loopback HTTP erişimini engellemez. `/api/veri` GET ve POST mutasyonları için ayrı erişim/authorization kararı ve gerçek server dispatch kapısı gerekir; mevcut feature-off davranışı dağıtımda açıkça seçilmelidir.
5. **`/api/kalp` tek kapalı geçiştir:** HTTP loopback peer kimliği vermez → `/api/kalp` **410 Gone**; POST auth taslağındaki `self` kuralı kaldırılır/closed yapılır. Aynı sürümde CLI broker istemcisine geçer; paralel HTTP fallback yoktur.
6. **Panel projeksiyonu ve tazelik:** broker erişilemez, kimlik/evidence belirsiz veya lease TTL aşılmışsa `unknown` (yeşil korunmaz). Broker saatinde duvar saati + `monotonic` kullanılır; TTL tek başına `offline` kanıtı değildir.

---

## 2. Statik kaynak envanteri (kabul kanıtının dayanağı)

### 2.1 Fail-closed kapılar (W1b'de açılacak)
| Yer | Satır | Bugün (kaynak kodu) |
|---|---|---|
| `panel/server.py` `api_kalp` | 1091-1095 | koşulsuz 503; `principal` yok sayılıyor |
| `panel/server.py` `veri()` | 1470-1496 | `son_gorulme`/`son_kalp`=None, `online=False`, `presence_state="unknown"`, `presence_verified=False` sabit |
| `bin/yuva` `host_kalp_baslat` | 1118-1121 | ilk satırda sert dönüş: "doğrulanmış broker principal yok" (altı ölü kod) |
| `bin/yuva` `daemon_baslat` | 1268-1270 | aynı sert dönüş (ölü kod) |
| `bin/yuva` `cmd_kalp` / `cmd_kalp_dongu` | 1468-1470 / 1474-1475 | `VeriHatasi`; heartbeat yolu kapalı |
| `panel/server.py` `ONLINE_SN` / `taze()` | 52 / 499-507 | 30 sn; ISO `son_kalp` yaşı |

### 2.2 Hazır altyapı
| Bileşen | Yer | Not |
|---|---|---|
| HMAC çekirdeği | `panel/auth.py:165-261` | nonce tek kullanım (241-248), `revoked`/`expires_at`/scope (225-235), `VerifiedPrincipal` (62-70) |
| Auth store | `panel/auth_store_v2.py:476-585` | `transact`, generation + `last_wall_time`, `_atomic_replace` + `CommitUnknown` (399-469); şema (134-175) |
| Route policy | `panel/auth_integration_draft.py:22-40` | `/api/kalp: "self"`, `/api/katil: self`, `/api/gorev: admin`, `/api/yaz: principal_actor` |
| Auth gate | `panel/server.py:1406-1463, 1700-1755` | `YUVA_AUTH_ENABLED=1` + store + audience; JSON öncesi authenticate, sonra authorize, `principal` uca geçer |
| GET read-scope taslağı | `panel/auth_integration_draft.py:9-10, 44-48, 134-185`; `panel/server.py:1676-1688` | Exact GET policy taslağı `read_enabled=False`; server `do_GET()` auth gate'e bağlamadan `/api/veri` dispatch ediyor. GET için ayrı route/alias ve default/fail-closed kararı şart. |
| POST route çatışması | `panel/auth_integration_draft.py:30-48` | POST taslağında `/api/kalp: self`; W1b planı 410/closed diyor. Uygulama öncesi tek karar: legacy HTTP heartbeat kapalı, 410 ve route policy `closed`/kaldırılmış. |
| UI sözleşmesi | `panel/ui.html:515-530` | yeşil = `online===true && presence_verified===true && presence_state==="online" && son_kalp` taze (`online_sn` 1..300) — değişiklik gerekmez |
| CLI sözleşmesi | `bin/yuva:1097-1116, 1629-1646, 1673-1699` | `kalp_tarihi_taze`, `panel_online_esigi`, `durum`/`kimler` aynı üçlü + tazelik |

### 2.3 Boşluklar (statik)
1. Presence lease şeması/store'u yok; `son_kalp` tek ISO alanı (generation/sequence/epoch/evidence yok).
2. Broker bileşeni yok; UID→agent eşlemesi ve socket ACL yok.
3. CLI'de broker istemcisi yok.
4. Auth/presence testi yok: `tests/` = `test_heartbeat_flock.py` (27), `test_code_data_roots.py`, `test_panel_atomic_write.py`.
5. **Kopya uyumsuzluğu (statik):** dört CLI kopyası ve en az eski/preview panel ağaçları vardır. #515/#517 raporlarındaki yollar ve hashler envanter girdisidir; etkin süreç/kod bilinmiyor. `yuva-dev/panel/server.py:412-417` eski `/api/kalp` yolunda body kimliğine göre yazıp online üretebiliyor.
6. Ajan UID'leri için ayrı HOME, credential, user manager, linger, `XDG_RUNTIME_DIR`, socket/config sahipliği ve revoke yaşam döngüsü tanımlı değil. “Ayrı UID uygulanabilir” operatör tercihi host hesap/servis kurulum izni değildir.
7. `unshare` ile UID eşlemesi birim/izole test için kullanılabilir; gerçek iki-UID socket ve host systemd/linger kabulünün yerini tutmaz.
8. `panel/auth_integration_draft.py` GET read-scope prototipi `read_enabled=False` ile kapalı ve `server.do_GET()` dispatch'ine bağlı değil. Loopback HTTP aynı ağ namespace'indeki farklı UID'lere `/api/veri` ve açık POST erişimi sağlayabilir.
9. Auth-state snapshot içi generation ve opsiyonel floor eski, kendi içinde geçerli backup'ı saptayamaz; revoke/nonce geri gelebilir (#458). Presence store için de aynı anti-rollback iddiası dış anchor yokken kurulamaz.

### 2.4 Canlı sistem bilgisi — **`unknown` (kabul kanıtı değil)**

İlk teslimde yapılan kapsam sapması nedeniyle canlı sistem hakkında hiçbir sonuç bu raporda kullanılmaz:

- Çalışan panelin **süreci, çalışma modu (systemd/elle), UID'si ve kod içeriği `unknown`**'dır. Bu rapor "panel şu an şu şekilde çalışıyor" iddiası taşımaz.
- Canlı `GET /api/veri` yanıtının içeriği **doğrulanmış kabul edilmez** ve hiçbir K maddesine, plan kararına veya risk sıralamasına dayanak yapılmaz.
- Bağımsız #515 raporu bu oturumda etkin süreci doğrulayamadı; bu nedenle süreç bilgisi **yalnız kapsam sapması kaydı** olarak kalır.
- Bu gözlemler **tekrar edilmedi**; rev 2 ve rev 3'te ek HTTP/`ps`/`/proc`/`systemctl`/runtime sorgusu yapılmadı.

---

## 3. Hedef mimari

```
ajan UID (model)  --(AF_UNIX, SO_PEERCRED)-->  broker UID (yuva-broker)
                                                  |  auth store (opsiyonel HMAC, 0600)
                                                  |  presence store (0600, tek yazıcı)
                                                  |  audit JSONL
panel UID  <---(AF_UNIX, SO_PEERCRED: panel, read-only)---+
   |                                                      |
HTTP client --> HTTP read/write authorization gate --> panel
                 (GET ve POST ayrı; auth'sız loopback yok)
                 GET /api/veri: izin yoksa fail closed
Yuva task/chat/state store: ayrı tek sahipli servis/sözleşme;
                             presence broker bu store'un yerine geçmez
```

- **Ajan izolasyonu:** her ajan için ayrı UID, HOME, credential erişimi ve `XDG_RUNTIME_DIR`; ayrı user manager/linger işletim kararı ve servis yaşam döngüsü tanımlanır. Ajan kodu salt okunur release'ten çalışır; yazma gerekiyorsa kendi clone/worktree'sine yapılır. Ortak writable `<REPO_ROOT>`, `.git`, `<YUVA_DATA_ROOT>`, backup veya secret alanı kullanılamaz.
- **Yuva state erişimi:** KOK, mesajlar, görevler, ekranlar, durum ve backup için erişim matrisi ve veri API'si ayrı tasarlanır. Tek sahipli state servisi allowlist'li okuma/yazma işlemleri sunar; ajanlar JSON/JSONL dosyalarını doğrudan açmaz. Panel snapshot okuması ayrı yetki ister. Presence broker tek başına bu erişimi sağlamaz.
- **Socket:** `/run/yuva/broker.sock` örnek yol; dizin/socket owner, mode, ACL ve yaşam döngüsü host kararıyla belirlenir. Bağlanma izni kimlik/rol yetkisi değildir; her işlem `SO_PEERCRED` UID'si ve server-side policy ile denetlenir.
- **UID→agent eşlemesi:** root-owned broker config: `uid -> agent_kimlik, role/scope, enabled, mapping_generation`. Kendi UID'si haritada yoksa `403`; mapping değişikliği kayıt altına alınır ve lease/cache anında geçersizleşir.
- **Protokol (satır-çerçeveli JSON, `SOCK_STREAM`):** `hello` (peer cred zorunlu) → own-principal `heartbeat` → yetkisi olan `status/read` → own-principal generation-bound `stop`. `presence.read`, `presence.heartbeat` ve `presence.stop` scope'ları ayrıdır; panel yalnız read/status alır. Gövdedeki `kimlik` yalnız iddia/görüntüdür; uyuşmazsa 403 + audit.
- **Lease:** `principal_id, agent_kimlik, uid, provider, provider_instance, session_id, generation, sequence, epoch, issued_at, expires_at, evidence, state`.
- **Evidence:** `adapter_connected` yeşil değildir. `provider_session_observed` ancak onaylı adapter/provider kaynağı, provider instance, opak session ID ve launch/session generation ile doğrulanmış, broker tarafından bağlanmış kanıt ise yeşil adaydır. UID/SO_PEERCRED veya istemcinin JSON claim'i tek başına yeterli değildir. Stale, replay, session reassignment, adapter restart ve kaynağı doğrulanamayan olay yeşil üretmez.
- **Epoch:** broker her restart'ta artırır; eski epoch yeşile dönmez.
- **Revoke:** UID mapping disable/removal, account disable veya broker revoke mevcut session, lease, açık socket oturumu ve cache girişini geçersizleştirir; yeni mapping generation/epoch gerekir. Erişim durdurma üst sınırı B9/K19'da ölçülür.
- **Opsiyonel HMAC:** taşıma bütünlüğü için; ajan UID'si zaten principal olduğundan tek başına yeşil gerekçesi değildir.
- **Provider evidence açık kapısı:** #474 sözleşmesi session ref/provider instance/generation ayırır; gerçek provider API şeması ve hangi adapter sinyalinin bağımsız/doğrulanmış olduğuna dair kanıt bulunmadan `provider_session_observed` kabul edilmeyecek. Bu kapı kapanana kadar presence `unknown` kalır.

---

## 4. Uygulama dilimleri (sıra, dosya sınırları, kapı)

| # | Dilim | İçerik | Dosyalar | Kapı |
|---|---|---|---|---|
| **B0** | Sözleşme + bayraklar | Presence default `unknown`; broker kapalıysa eski fail-closed davranış. Ayrı GET read flag/policy ve POST auth flag matrisi; feature-off GET'in public mi denied mı olduğu açık startup durumu; bilinmeyen değerler startup hatası. `/api/kalp` tek kapalı/410 kuralı. | `panel/server.py` (config/dispatch), `panel/auth_integration_draft.py`, `bin/yuva`, `docs/` | K1, K20 |
| **B1** | UID haritası + host kimlik alanı | Root-owned config, UID→principal/scope/enabled/mapping generation; ayrı HOME/credential/XDG runtime; owner/mode ve reload/revoke lifecycle; sır taşımayan konfigürasyon | `panel/broker_config.py` (yeni), operator docs | K3, K21 |
| **B2** | Broker iskeleti | `AF_UNIX`, gerçek peer credential, socket dir/file owner+mode, framing/boyut/hız sınırı, mapping/auth öncesi body id reddi, restart epoch; ayrı user manager/systemd/linger varsayımları | `bin/yuva-broker` (yeni), `panel/broker_proto.py` (yeni), unit docs | K5, K21 |
| **B3** | Presence store | Broker-owned 0600; tek writer; generation/lease/stop/audit; commit-unknown; dış anchor yokken backup restore otomatik kabul edilmez | `panel/presence_store.py` (yeni), restore/revoke runbook | K13-K14 |
| **B4** | Lease + session evidence | Ayrı read/status, heartbeat, stop yetkileri; sequence/generation/epoch; onaylı adapter kaynaklı provider session ref; stale/replay/reassignment reddi; TTL/freshness | `panel/broker_proto.py`, `bin/yuva-broker`, adapter contract | K6-K12, K22 |
| **B5** | Panel HTTP + broker projeksiyonu | Panel presence'ı broker'dan yalnız read/status alır. GET snapshot ayrı exact auth/read-scope gate'e girer; GET dispatch auth öncesi snapshot üretmez. POST auth route policy korunur; broker yoksa `unknown`. | `panel/server.py`, `panel/broker_client.py` (yeni), `panel/auth_integration_draft.py` | K2, K6, K20 |
| **B6** | CLI istemcisi + daemon | Broker istemcisi; `--from` yetki değil. CLI yalnız kendi principal heartbeat/stop isteği gönderir; Yuva görev/mesaj dosyalarına doğrudan ortak erişim yok. | `bin/yuva`, state API client (ayrı tasarım) | K15, K17, K21 |
| **B7** | `/api/kalp` kapatma | `/api/kalp` 410/closed ve sıfır mutasyon; POST `self` auth kuralı kaldırılır/kapalı hale gelir; legacy HTTP fallback yok. Panel/CLI aynı sürüm geçişinde eski çağrı yolu kapanır. | `panel/server.py`, `panel/auth_integration_draft.py`, `bin/yuva` | K16, K18 |
| **B8** | Eski kopya ve writer envanteri | Dört CLI (`yuva`, `yuva-dev`, `yuva-v2`, `yuva-ui-dev`), her panel kopyası, sample ve kurulu unit tanımı, elle çağrı/otomasyon girişleri statik envanterlenir. Eski HTTP/state writer'lar disable/hizalanmadan geçiş kabul edilmez; etkin süreç modu/kodu ayrıca kanıtlanır. | dört kopya; ilgili `panel/server.py`; `contrib/systemd/yuva-panel.service`; operator unit inventory | K18 |
| **B9** | Rollout/rollback | Tek ajan canary; kill-switch üst sınırı 30 sn, map/socket/broker/panel cache ve lease freshness sürelerinin toplamıyla hesaplanır; restore offline re-provision/credential-lease revoke/new epoch; audit, backup ve writer tekilliği. | `docs/`, runbook, deployment config | K10, K13, K19 |

**Dokunulmayacaklar:** `panel/auth.py` kanonik imza biçimi; `auth_store_v2` şeması; görev/mesaj JSONL biçimi; `ui.html` presence mantığı; `~/yuva` verisi; canlı panel/servis ve çalışma durumu (modu bilinmiyor; B9'a kadar hiçbir varsayım yapılmaz).

---

## 5. Kabul matrisi — her koşulun kanıt yöntemi

| # | Kabul koşulu | Kanıt yöntemi (statik veya kontrollü test) |
|---|---|---|
| **K1** | `YUVA_PRESENCE_SOURCE=unknown` iken `api_kalp` 503, `/api/veri` alanları bugünküyle birebir | Birim testi: bayraksız sunucu nesnesi; alan-alan snapshot diff (statik kod okumasıyla eşleşmeli) |
| **K2** | Broker yok/erişilemez → tüm kayıtlar `unknown`; CLI yeşil göstermez | Broker kapalıyken CLI birim testi (sahte transport) |
| **K3** | Haritada olmayan UID / `enabled=false` → 403, lease yok; disable/revoke mapping değişikliği aktif session/cache'i geçersizleştirir | Birim ve sahte mapping testleri; `unshare` yalnız izole mantık testi, host kabulü değildir |
| **K4** | Gövde `kimlik` UID haritasıyla uyuşmuyor → 403 + audit; başka UID adına principal seçilemez | İzole `/tmp` state ile gerçek iki-UID broker entegrasyonu |
| **K5** | Peer credential okunamıyor/eksik/yanlış UID → ret; client body, env, PID veya user-provided SCM credential'ı peer identity yerine geçmez | Gerçek Unix socket'te iki ayrı UID; injection testi ek negatif testtir, tek başına yeterli değildir |
| **K6** | `provider_session_observed` yalnız doğrulanmış adapter/provider kaynağı, provider instance + opak session ID + launch/session generation ile taze ve aktif eşleşirse yeşil olur. UID tek başına yeşil vermez. | Önceden seçilmiş adapter/provider kaynak sözleşmesiyle uçtan uca izole test; kaynak yok/yanlış session/generation, stale, replay, reassignment ve adapter restart negatifleri. Şema/kanıt kaynağı henüz seçilmediğinden kapı açık kalır. |
| **K7** | Yalnız `adapter_connected` → yeşil değil | Projeksiyon birim testi |
| **K8** | TTL doldu → `unknown` | Sahte clock enjeksiyonu |
| **K9** | Açık, generation-bound stop → `offline`, `presence_verified=true`, yeşil değil | Stop lease testi |
| **K10** | Revoke/mapping disable/UID reassignment → aktif socket, heartbeat, broker lease, broker/panel cache ve eski session generation invalid olur; yeni UID ataması eski lease'i yeşil yapamaz | Eşzamanlı heartbeat + revoke yarış testi; cache/read-path ve UID reassignment testi; tüm görünüm ≤K19 sınırında `unknown` |
| **K11** | Broker restart → yeni epoch; eski lease geçersiz | Restart testi |
| **K12** | sequence/generation/epoch gerilemesi → red + audit | Çakışma enjeksiyonu |
| **K13** | Restore edilen iç generation/high-water tek başına rollback kanıtı değildir. Dış anchor yokken eski snapshot otomatik kabul edilmez; feature-off kalır, offline re-provision, eski credential/lease revoke ve yeni epoch gerekir. Dış anchor eklenirse snapshot generation+digest+instance/transaction tutarlılığı doğrulanır | Eski geçerli snapshot/credential/nonce/revoke/lease/cache geri yükleme senaryosu. Yalnız generation-floor testi kabul kanıtı değildir. Dış anchor henüz yoksa başarılı otomatik recovery beklenmez; fail-closed + operator runbook kanıtlanır. |
| **K14** | `CommitUnknown` → kör retry yok, ikinci lease yok, kısmi yazım yok | fsync/replace hata enjeksiyonu |
| **K15** | Saat sıçraması/geri gitme → `unknown` | clock enjeksiyonu + `last_wall_time` testi |
| **K16** | `/api/kalp` → 410/closed; panel ve CLI aynı dağıtımda eski yola düşmez; request state/presence store, lease, `durum.json`, `gorevler.json`, `mesaj.jsonl`, ekran, audit ve lock içeriğinde mutasyon üretmez (salt-okunur gözlem dahil belirtilir) | İzole fixture öncesi/sonrası tüm ilgili dosya/lock/store snapshot ve hash karşılaştırması; canlı KOK kullanılmaz |
| **K17** | `--from`/gövde kimliği tek başına yeşil üretemez | Negatif testler |
| **K18** | Dört CLI kopyası, her eski/preview panel, eski `yuva-dev` `/api/kalp` writer'ı, repo sample unit'i, kurulu unit tanımı ve elle çağrı/otomasyon girişlerinin tümü taranır; eski writer ile model bazlı yeşil üretilemez. Kurulu unit ve etkin süreç farklı kanıt türüdür. | Dört kopyada statik + davranış matrisi; unit/launcher envanteri. Nihai sample unit `current` release pointer'ını kullanır; tarihsel ve #520 adayı yolları §9.6 bölümünde ayrılır. Kurulu unit config ve etkin süreç ayrıca kanıtlanır; süreç bilinmiyorsa `unknown` kalır. |
| **K19** | Kill-switch/revoke'dan tüm broker/socket/map/panel cache ve lease/UI freshness durumlarının yeşili bırakmasına kadar üst sınır ≤30 sn; aynı UID güvenli kimlik iddiası yok | Yapılandırılmış en kötü durum sürelerinin toplamını hesapla ve gecikmeli cache/aktif socket/heartbeat/restart ile zaman ölç; herhangi bir ayar 30 sn üstü ise startup/config reddi veya yeşil kapalı. Doküman/kod taraması aynı UID iddiasını denetler. |
| **K20** | `/api/veri`, `/veri`, `/`, `/index.html` ve canonical olmayan/yanlış method varyantlarında GET ve POST policy ayrı; seçilen read flag/policy `do_GET()` dispatch'inden önce çalışır; fail-closed modda auth öncesi snapshot/HTML sızmaz. POST mutasyon auth/payload policy'si GET scope'u kullanmaz; `/api/kalp` policy kapalıdır. | Public/read-auth/closed konfigürasyonları için route matrisi; auth öncesi handler/serialize çağrısı olmadığını statik doğrula, sonra izole HTTP testleri. `read_enabled=False` tek başına koruma sayılmaz. |
| **K21** | UID başına HOME, credential, `XDG_RUNTIME_DIR`, manager/linger ve socket/config owner erişimi izole; ortak repo/KOK/backup/secret doğrudan erişimi yok; state/read/backup/screen/message erişimleri explicit allowlist ile sunulur | Hostta gerçek iki-UID socket/filesystem ve systemd yaşam döngüsü kabul testi; `unshare` yalnız ek testtir. State API olmayan sürümde KOK erişimi deny edilmesi beklenir. |
| **K22** | Broker yetkileri ayrıdır: panel yalnız `presence.read/status`; ajan kendi eşlenmiş principal'ı için heartbeat ve generation-bound stop; başkasının heartbeat/stop veya state/admin read/write isteği reddedilir | Scope/UID kombinasyon matrisi, ayrı UID'lerle izole socket testleri ve audit/assertions |

**Kanıt disiplini:** gelecek testler `/tmp` veri kökü + geçici socket kullanır; **canlı 8686 ve `~/yuva` kullanılmaz**. Çok-UID unit/namespace testleri yararlıdır ama gerçek farklı host UID, user manager/linger ve socket permission kabulinin yerine geçmez; ayrı test hesapları ancak ayrı bir yetkili host test planıyla kullanılabilir. Bu görevde host hesabı oluşturulmaz. §2.4'teki ilk teslim runtime sorguları hiçbir K maddesine dayanak değildir.

---

## 6. Riskler

1. **Operasyonel yük:** ajan başına UID, user manager, linger, dosya izinleri, repo/secret erişimi.
2. **Ortak writable alan:** repo, `.git`, Yuva state, backup, ekran/mesaj veya secret paylaşılırsa UID sınırı delinebilir. Salt-okunur release + ayrı çalışma alanı ve tek sahipli state servisi olmadan B0-B9 ilerlemez.
3. **Broker tek hata noktası:** broker ölürse tüm ışıklar `unknown` (kabul).
4. **Panel↔broker gecikmesi:** TTL 30 sn ile yanlış `unknown` → önbellek en fazla TTL kadar.
5. **HTTP route maruziyeti:** farklı UID aynı network namespace'te loopback `/api/veri` ve auth kapalı mutasyon POST'larına ulaşabilir; UID izolasyonu bu erişimi tek başına kesmez.
6. **`/api/kalp` geçişi:** eski CLI/panel kopyaları 410 alır; POST auth taslağındaki `self` policy ile çelişmemesi ve aynı sürüm geçişi şart.
7. **Eski writer'lar:** dört CLI ve panel kopyalarının kaynakta var olması aktif olduğu kanıtı değildir; bütün giriş yolları envanterlenmeden W1b tamamlanmış sayılmaz.
8. **Rollback:** presence store veya auth snapshot eski generation/revoke/lease bilgisine dönebilir; dış anchor yokken eski snapshot reddedilir ve offline re-provision gerekir.
9. **Provisioning hatası:** yanlış UID→agent eşlemesi yanlış kişiyi yeşil yapar → değişiklik audit'i ve UID yeniden atama testi.
10. **Provider kanıtı:** adapter raporu veya UID session kanıtı değildir; doğrulanmış provider kaynağı/session-generation bağı yoksa `unknown`.
11. **Test edilebilirlik:** çok-UID senaryoları ayrıcalık ister; peer-cred enjeksiyonu sadece parser birim kanıtıdır. Gerçek iki UID/socket ve host systemd lifecycle kabulü ayrıca gerekir.

---

## 7. Kalan operatör kararları

1. **TTL / kill-switch budget:** 30 sn toplam üst sınır korunacak mı? Map yenileme, broker/session/cache, panel cache ve UI freshness üst sınırlarının toplamı en fazla 30 sn olmalı; mevcut UI'nın 300 sn'ye kadar ayarı bu sınırı otomatik karşılamaz.
2. **Panel kimliği/read path:** panel UID'si broker'dan yalnız read/status alacak mı; HTTP GET read scope hangi istemcilere verilecek? `/api/veri` içeriği görev/mesaj/ekran verisi içerir.
3. **Socket/config sahipliği:** broker socket directory/socket ve UID map config owner/mode/ACL'si; root/system manager mı yönetecek? Grupta olma sadece bağlantı hakkıdır.
4. **Yuva state servisi:** görev, mesaj, ekran, durum ve backup için ayrı merkezi read/write API scope'ları ve sorumlusu kim olacak? Presence broker kapsamı bu değildir.
5. **Kod alanı:** ajanlar salt-okunur release mi kullanacak; düzenleme için ayrı clone mu yoksa private worktree mi? Ortak writable `.git` ve working tree kabul edilmez.
6. **Host lifecycle:** ayrı HOME/XDG runtime, per-agent systemd user manager/linger, logout/reboot, disable/revoke ve UID tekrar atama sorumlusu/prosedürü.
7. **Harita sahibi ve onay akışı:** broker config değişikliğini kim yetkili olarak yapar ve audit eder?
8. **Provider evidence:** hangi resmi/izinli adapter/provider kaynağı `provider_session_observed` sağlar; source version/capability nasıl pinlenip denetlenir? Bu seçim yapılmadan yeşil kapalıdır.
9. **Restore ve anti-rollback:** dış anchor yokken #458'in önerdiği offline re-provision + eski credential/lease revoke + yeni epoch prosedürü işletim sahibi tarafından kabul edilecek mi? Eski snapshot'ı online kullanma seçeneği yoktur.
10. **Eski kopyalar/kanarya:** tüm legacy writer yolları statik ve kontrollü kabulde nasıl kapatılacak; ilk ajan ve rollback kriteri nedir? Kurulu unit yapılandırması etkin süreç kanıtı sayılmaz.

---

## 8. Kapsam ve değişiklik beyanı

- Bu rapor dışında hiçbir dosya değişmedi; kod, servis, credential, auth gate, test veya canlı veri değişikliği yok.
- Tek istisna, §0'da açıkça kaydedilen **ilk teslimdeki kapsam dışı runtime sorgularıdır** (panel `GET` denemesi + süreç sorgusu). Bunların **sonuçları kullanılmadı**: çalışan sürecin modu/kodu ve canlı yanıt içeriği bu rapor kapsamında **`unknown`**'dır ve hiçbir kabul ölçütüne dayanak değildir.
- Rev 2, rev 3 ve bu revizyonda **ek HTTP, `ps`, `/proc`, `systemctl` veya runtime sorgusu yapılmadı**.
- Rev 4, #518 bulgularını B0–B9 planına ve K1–K22 kabul matrisine işler; hiçbir kabul maddesi ilk teslimdeki canlı GET/ps/date sonucuna dayanmaz.
- Karar çerçevesi (ajan başına doğrulanmış yeşil, same-UID düşman, ayrı OS UID) **plan varsayımı** olarak tutuldu; kurulum/auth açma onayı sayılmadı.

## 9. Rev 4 — #518 bulgularının uygulama kapıları

### 9.1 Veri ve dosya erişim matrisi

Varsayılan politika **deny**'dir. Aşağıdaki izinler ancak ilgili tek-sahipli servis ve işlem-kapsamı doğrulaması uygulanırsa açılabilir; ortak dizin ACL'siyle verilmez.

| Veri/yol | Ajan UID | Panel UID | Broker/state sahibi | Host operatörü |
| --- | --- | --- | --- | --- |
| Kanonik repo ve `.git` | Salt okunur kaynak veya erişim yok; yazma gerekirse özel clone/worktree | Çalıştırma için salt okunur release | Release/dağıtım işi; runtime writer değil | Kanonik kaynak, release ve hash yönetimi |
| Agent HOME, credential, XDG runtime | Yalnız kendi UID'sinin alanı | Erişim yok | Presence broker credential gereksinimi ayrı ve minimum | Provision/revoke; secret kopyalama yok |
| Presence lease/map | Broker protokolünde yalnız kendi kimlik/scope'u | Read/status only | Tek writer; map ve store owner | Yetkili map değişikliği ve audit |
| `durum.json`, `gorevler.json` | Doğrudan okuma/yazma yok | Yalnız yetkilendirilmiş gerekli projection; varsayılan yok | Ayrı Yuva state servisi tek writer | Backup/recovery sorumlusu |
| `mesaj.jsonl`, `ekran/*.jsonl` | Doğrudan erişim yok; gerekli mesaj/ekran scope'u ayrı onaylanır | Yetkili ve en az veri projection'ı | Tek writer; read scope ayrıca policy | Retention/backup yönetimi |
| Backup ve auth/presence secret | Erişim yok | Erişim yok | Store sahibi gerektiği kadar; backup ayrı protected alan | Offline backup, restore/re-provision ve secret rotation |

`YUVA_DIR` değerini aynı yapmak filesystem erişim yetkisi sağlamaz. Ajan UID'sinin kendi HOME varsayılanı ayrı bir veri ağacı yaratır; ortak `<YUVA_DATA_ROOT>` yolunu yazılabilir gruba açmak same-UID hostile kararını bozar. `umask`, setgid veya ACL bu politika yerine geçmez. `bin/yuva` ve panelin euid/owner/mode kontrolleri de başka UID'li doğrudan writer'ı kabul etmez (`docs/local-data-threat-model.md`, `bin/yuva`, `panel/server.py`).

### 9.2 HTTP GET/POST ve broker yetkisi

- Mevcut `panel/server.py:H.do_GET()` `/api/veri` ve `/veri` yolunu `_kaynak_denetimi()` sonrasında doğrudan `veri()` fonksiyonuna dispatch eder. Bu kaynak/Host/Origin kontrolü UID doğrulaması değildir. GET read-scope taslağı exact route/alias politikası tanımlar ama `read_enabled=False` varsayılanındadır ve server GET dispatch'ine bağlı değildir (`panel/auth_integration_draft.py:9-10, 44-48, 134-185`). Bu nedenle yalnız prototipin varlığı GET'i korumaz.
- B0/B5'te açık bir dağıtım matrisi seçilmelidir: public GET sadece worker UID'lerinin panel network namespace'ine erişimi engellenmişse; aksi durumda GET kapalı veya ayrı doğrulanmış read-scope arkasında. `/api/veri` görev, mesaj, ekran ve roster bilgisi döndürdüğünden presence-only yetki tüm snapshot'ı açmamalıdır. `/`, `/index.html`, `/veri`, alias/canonical varyantları ve yanlış HTTP method ayrıca kapsanır.
- GET authorization, `veri()`/HTML snapshot okumadan ve serialize etmeden önce çalışmalıdır. Mutating POST `YUVA_AUTH_ENABLED` feature-off durumunda ayrıca incelenmeli; GET gate'in POST'u koruduğu varsayılmamalıdır. Exact POST route/payload policy ile exact GET read scope birbirine miras bırakılmaz.
- Broker scope'ları ayrıdır: panel `presence.read/status`; ajan kendi UID-mapped principal'ı için `presence.heartbeat` ve generation-bound `presence.stop`. Başka principal için heartbeat/stop, key/map/admin değişikliği ve görev/mesaj read/write broker yetkisi sayılmaz. Yuva state servisinin ayrıca kendi scope matrisi olur.
- `/api/kalp` HTTP handler'ı W1b'de `410 Gone` veya route-level closed sonucu verir; auth entegrasyon taslağındaki `POST_ROUTE_POLICY["/api/kalp"] = "self"` kaldırılır/closed yapılır. POST key'i bulunan bir istemci de bu endpoint'i tekrar açamaz. Legacy CLI fallback ya da body kimliğiyle heartbeat yoktur.

### 9.3 Provider-session evidence

`SO_PEERCRED` UID'yi, UID haritası agent hesabını adlandırır; ikisi de provider'ın oturum açtığını kanıtlamaz. `provider_session_observed` ancak şu sözleşme uygulanıp kanıtlanırsa `online` adayı olabilir:

1. Adapter/provider kaynağı ve sürümü/capability'si onaylı belgelenir; heartbeat JSON'ındaki `evidence_level` istemci iddiası olarak tek başına kabul edilmez.
2. Güvenilir adapter olayı provider adı/instance, opak native session ID, UID principal, broker epoch ve yeni session/launch generation'ını kriptografik veya işletimsel olarak doğrulanmış bağla iliştirir. Provider `thread_id`, `turn_id`, item/request ID gibi farklı kimlik kapsamları karıştırılmaz (#474).
3. Broker event kaynağını doğrular, kabul zamanı ve sequence'ı kendisi üretir; duplicate/replay, eski timestamp/generation, önceki adapter process/session, provider-instance değişimi ve UID reassignment fail closed olur.
4. Yalnız `adapter_connected`, socket connect, UID map eşleşmesi, process/unit liveness veya modelin kendi bildirimi presence yeşili oluşturmaz. Provider kaynağı doğrulanamıyor, API şeması bilinmiyor veya uzlaştırma belirsizse state `unknown` kalır.

Gerçek provider kaynağı/şeması halen açık karardır; #474 ortak tip sözleşmesidir, gerçek adapter/provider entegrasyonu değildir. Bu kapı kapanmadan K6 başarılı kabul edilmez ve feature flag `broker` yeşil üretemez.

### 9.4 UID/HOME/service yaşam döngüsü

Her ajan için ayrı HOME ve credential store; ayrı `XDG_RUNTIME_DIR`; UID'ye özel user manager, socket/config erişimi ve gerekiyorsa linger davranışı tasarlanır. Servis hesabı yaratma, linger etkinleştirme ve systemd unit dağıtımı ayrı operatör uygulamasıdır; kullanıcının ayrı UID'yi uygulanabilir bulması bu işlemlere izin vermez. Unit'in `User`, `ExecStart`, environment (`YUVA_DIR` dahil), `WorkingDirectory`, restart/stop ve logout/reboot davranışı açıkça kaydedilir.

Revoke sırası: UID map'ini disabled yap → broker mevcut bağlantıları/lease'leri ve cache'i invalid et → panel projection cache'ini temizle → eski account/credential/session generation'ını kapat → testte eski UID/lease reddini doğrula. UID yeniden kullanılacaksa eski eşleme/lease/credential temizliği ve yeni map generation/epoch tamamlanmadan yeni ajan yeşil olamaz. Socket directory/socket ve config file sahipliği/modu root veya yetkili service owner tarafından uygulanıp incelenir; `yuva-clients` gibi grup üyeliği sadece connect ACL'dir.

`unshare --map-users` testleri UID map/parser davranışını veya izole IPC'yi kanıtlayabilir. Gerçek iki ayrı host UID'nin Unix socket credentials, filesystem deny, user manager/linger, service lifecycle ve logout/reboot davranışı için ayrı privileged test host kabulü gerekir. Bu görev ve operatörün “uygulanabilir” kararı bu host işlemlerini onaylamaz.

### 9.5 Restore, revoke ve anti-rollback

`docs/auth-state-external-anchor-decision-458.md` ve `docs/auth-state-v2-operations.md` uyarınca snapshot içi generation/`last_wall_time` ve varsayılan/opsiyonel `generation_floor`, eski fakat kendi içinde geçerli backup'ın revoke/key/nonce durumunu geri getirmesini engellemez. Aynı backup içindeki sidecar veya sabit floor dış anchor değildir. Presence store için de benzer generation iddiası tek başına anti-rollback kanıtı sayılmaz.

Dış anchor tasarlanıp devreye alınana kadar auth/presence state restore'u **online otomatik devam** etmez: ilgili feature kapalı/`unknown` tutulur; operatör offline inceleme yapar; eski credential ve lease'leri revoke eder; broker/principal için yeni epoch ve gerekiyorsa yeni credential/key'leri re-provision eder. Eski snapshot otomatik kopyalanmaz, kör retry/readback/rollback yapılmaz. `CommitUnknown` sonrası da aynı mutation yeni operation/key ile tekrarlanmaz. Restore kararı ve yeni kimlikler audit edilir.

K10 gerçek canlı lease ile aynı anda heartbeat, harita disable, in-flight socket, broker/panel cache invalidation ve UID reassignment yarışını kapsar. K13 eski geçerli backup'ta revoke edilen key, tüketilmiş nonce ve lease'i geri getirip reddedilmesini; dış anchor yokken ise offline re-provision kapısını doğrular. Dış anchor sonradan seçilirse K13 generation yanında canonical digest + `instance_id`/epoch + committed transaction bağını ve recovery semantiğini test eder; sadece minimum generation testini kabul etmez.

### 9.6 Legacy writer envanteri ve sıfır-mutasyon kapısı

Statik envanter en az #515'in dört CLI kopyasını kapsar: `~/yuva/bin/yuva`, `~/yuva-dev/bin/yuva`, `~/yuva-v2/bin/yuva`, `~/yuva-ui-dev/bin/yuva`. `~/.local/bin/yuva` bu kayda göre v2'ye symlink'tir, beşinci kopya değildir; bu PATH/config envanteri etkin sürecin kanıtı sayılmaz. Hash/commit ve davranış farkları release manifestine göre doğrulanır.

Panel envanteri `yuva`, `yuva-dev`, `yuva-v2`, `yuva-ui-dev` ağaçlarının `panel/server.py` kaynaklarını ve tüm `/api/kalp`, presence, CLI child-process, state/JSONL writer callsite'larını inceler. Özellikle `yuva-dev/panel/server.py:412-417` eski body-kimliğine göre `son_kalp` yazan yoldur; B7/B8'de kapalı olduğuna dair kabul kanıtı gerekir.

Unit yolları üç ayrı kayıt olarak tutulur:

1. **Tarihsel repo örneği:** #520 değişikliğinden önce `contrib/systemd/yuva-panel.service`, kodu `%h/yuva/panel/server.py` altından başlatıyordu; bu eski `~/yuva` kod+veri varsayımı #486/#508 ile uyumsuzdur.
2. **#520 düzeltilmiş ve onaylı repo adayı:** ilk teslimdeki `%h/yuva-v2/panel/server.py` ve `WorkingDirectory=%h/yuva-v2` sabit geliştirme yolu revizyonda düzeltildi. Güncel, #520'de onaylanan şablon `ExecStart` için `%h/.local/opt/yuva/current/panel/server.py`, `WorkingDirectory` için `%h/.local/opt/yuva/current` kullanır; `YUVA_DIR=%h/yuva` ayrı veri köküdür. Önceki v2 sabit-yol adayının `pending_revision` olması tarihsel durumdur, güncel #520 durumu değildir.
3. **Release kullanımı:** repo unit'i hâlâ örnek şablondur. Varsayılan `INSTALL_ROOT` `%h/.local/opt/yuva` kabul edilir; özel kök seçilirse iki kod yolu aynı kökteki `current` işaretçisine göre birlikte değiştirilir. Kod pointer'ı veri yolunu değiştirmez; `YUVA_DIR=%h/yuva` ayrı kalır.

#515'in statik kurulu user-unit dosya içeriği, o tarihte `%h/yuva-v2` kod yolunu ve `YUVA_DIR=%h/yuva` değerini göstermiştir; bu zaman damgalı kurulum snapshot'ı #520'nin daha sonra `current` işaretçisine düzeltilip onaylanan repo şablonundan ayrıdır. #515/#517 dosya içeriği kaydı etkin panel sürecinin kodu değildir. Kurulu unit tanımı, çalışan process image/cwd ve elle başlatılmış ya da otomasyon girişleri ayrı kanıt satırlarıdır; etkin süreç ve modu bu planda `unknown` kalır. #520 örnek-unit adayı, #515 kurulu-unit snapshot'ı veya `contrib` dosyasından tek başına canlı süreç sonucu çıkarılmaz.

K16'nın izole before/after kontrolü yalnız `durum.json` ve `mesaj.jsonl` ile sınırlı değildir: presence store/lease, broker audit, panel audit, görev, ekran, auth state ve lock inode/content üzerindeki beklenen/olmayan etki kaydedilir. Endpoint kapatma sırasında read/lock side-effect'i bile kabul ölçütünde açıklanır; canlı KOK üzerinde hash alma veya deney yapılmaz.

### 9.7 Kill-switch bütçesi ve release gate

K19'un 30 saniye sınırı duvar saati/lease TTL'sinden ibaret değildir. En kötü durumda toplam süre şu bileşenleri kapsar: map disable'ın broker tarafından görülme gecikmesi + açık socket/RPC'nin sona ermesi + lease/cache invalidation + panel broker cache/projection yenilemesi + UI taze kabul eşiği. Bu sürelerin toplamı **≤30 saniye** olmalıdır; daha uzun değer yapılandırılamaz ya da `online` üretimi kapalı kalır. Heartbeat interval, reconnect, IPC retry ve failed broker davranışı da bu üst sınıra dahil edilir. `unknown` fail-closed'dur; TTL geçmesi tek başına verified offline değildir.

B0–B9 host/release uygulaması; ortak KOK/secret sahipliği, HTTP read/write scope ve gerçek route dispatch, provider-session evidence kaynağı, host iki-UID socket/lifecycle kabulü, restore/revoke yolu, eski writer envanteri ve ölçülebilir kill-switch budget kararları tamamlanana kadar başlamaz. #514 rev4 yalnız bu uygulama planını günceller; feature flag açmaz veya deployment onaylamaz.

### Rev 4 kaynak notları

- #518 bağımsız review, Yuva görev #518 teslim kaydı (2026-10-23): ortak repo/KOK, HTTP GET/POST, provider evidence, gerçek UID lifecycle, rollback/restore ve legacy writer bulguları.
- `docs/local-data-threat-model.md`; `docs/auth-state-v2-operations.md`; `docs/auth-state-external-anchor-decision-458.md`.
- `docs/hmac-get-read-scope-design-471.md`; `docs/local-api-get-snapshot-decision-455.md`; `panel/auth_integration_draft.py`; `panel/server.py`.
- `docs/session-adapter-contract-474.md`; `docs/w1b-broker-principal-granularity-513.md`; `docs/auth-session-bridge-milestone-map-497.md`.
- #515 ve #517 statik kopya/kurulum kayıtları ile #520 unit görevi ve durum geçmişi (`<YUVA_DATA_ROOT>/gorevler.json`); `contrib/systemd/yuva-panel.service` ve README hızlı başlangıçtaki `%h/.local/opt/yuva/current` varsayılanı. İlk `%h/yuva-v2` adayı revizyon bekledi; düzeltilmiş `current` işaretçili #520 teslimi 2026-10-23 16:35:56'da onaylandı. Önceki rev4 kaynak notundaki “hazırlanırken pending_revision” ifadesi bu tarihsel ara durumu anlatır, güncel durumu değil.
