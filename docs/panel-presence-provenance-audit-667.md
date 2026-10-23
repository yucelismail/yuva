# #667 — Presence projection sentetik girdileri provenance denetimi

**Tarih:** 2026-10-23
**Kapsam:** `prototypes/panel-presence-principal/projection.py`,
`tests/test_panel_presence_broker_principal_fixture.py` ve #650 sözleşmesinin
statik incelemesi. Production adapter, panel/API entegrasyonu veya verified
presence eklenmedi; test ya da canlı broker/socket çalıştırılmadı.

## Karar

Projection feature-off başlıyor ve yalnız nesne alanları tutarlı olduğunda
sentetik girdilerden `online` çıkarıyor. Bu dosya `PeerEvidence` kaynağını
kernel'den almaz, principal map/session store/heartbeat'i okumaz ve
provenance doğrulamaz. Dataclass örneği üretmek kolay olduğundan,
`project_presence()`'e HTTP/body/JSON kaynaklı nesne vermek güvenli kabul
edilemez. #650'nin saf fixture sınırı doğru belgelenmiş; production caller
olarak kullanılmasına izin veren kod yolu yok ve bu denetim yeni bir yol
eklemiyor.

## Kaynak-kontrol matrisi

| Girdi / karar girdisi | Projection'ın yaptığı kontrol | Production adapter'ın güvenilir biçimde sağlaması gereken kaynak | Body/JSON kabul sınırı ve kalan risk |
|---|---|---|---|
| `PeerEvidence` | `source == "kernel_so_peercred"`; PID pozitif exact `int`, UID/GID non-negative exact `int`; UID map'te bulunmalı. | Broker'ın kabul ettiği aynı bağlı AF_UNIX socket üzerinde `getsockopt(SO_PEERCRED)`/incelemeden geçmiş helper sonucu. Peer bilgisi request parse edilmeden ve aynı connection'a bağlı olarak alınmalı. | `source` düz string ve dataclass kurucusu public; HTTP `pid/uid/gid/source` alanları kopyalanarak sahte nesne üretilebilir. Kaynak etiketi kernel provenance'ı kanıtlamaz. Peer UID aynı UID altındaki süreçleri ayırmaz; fixture aynı-UID izolasyonu kanıtlamaz. |
| `PrincipalBinding` ve `bindings` | UID anahtarı exact `int`; `binding.uid` eşit; ID/revision biçimli; principal ID benzersiz; `active is True`; map revision güncel revision ile eşit. | Broker-owned, erişim kontrollü ve revocation/generation semantiği tanımlı principal registry. Güncel snapshot tutarlı biçimde okunmalı; yalnız yetkili yönetim yolu map'i değiştirebilmeli. | `Mapping`, binding alanları ve `current_map_revision` caller parametresidir. Request'teki principal→UID map'i trusted input'a yükseltilemez. Revision'in syntactic ID olması imza/custody/yenilik doğrulaması değildir. |
| `SessionEvidence` | Authenticated/allowed exact `True`; scope exact `presence:read`; principal, peer PID/UID, map revision ve broker epoch eşleşmesi; session ID biçimi ve monotonic expiry kontrolü. | Broker session/auth store ve route authorization kararı. Session, aynı canlı socket peer'i ve map/broker generation'ına bağlanmalı; expiry broker'ın monotonic clock'undan gelmeli. | JSON'dan gelen `authenticated: true`, `allowed: true`, scope, PID/UID veya expiry beyanı kanıt değildir. Projection session authentication, credential, CSRF veya yetki kontrolünü yapmıyor. |
| `HeartbeatEvidence` | Session ID/broker epoch eşleşir; sequence exact pozitif `int`; gözlem saati finite ve `now` ile TTL aralığında; farklı `body_principal_claim` reddedilir. | Yetkili broker/supervisor heartbeat gözlemi; timestamp broker monotonic saatinden, epoch broker lifecycle'ından, session ID doğrulanmış session'dan gelmeli. Replay önleme için session/generation başına sequence high-water/nonce state'i adapter/broker'da tutulmalı. | Heartbeat body'sindeki principal claim yalnız çelişki sinyali; eşleşmesi güven katmaz. Body kaynaklı session/epoch/sequence/timestamp doğrudan evidence'a çevrilemez. Projection yalnız `sequence >= 1` kontrol ediyor; sequence gerilemesi/tekrarını hatırlayan state yok. TTL içinde aynı eski sequence yeniden kullanımı kendi başına engellenmiyor. |
| `now_monotonic`, map revision, broker epoch, TTL ve `feature_enabled` | Monotonic sayı/ID biçimi ve TTL 0–300 sınırı; feature yalnız `is True` ise açık. | Trusted adapter config/clock/generation. Feature toggle kontrollü rollout ve tüm production call path'lerini kapsayan ayrı kabul gerektirir. | Bunlar da caller tarafından verilen parametreler. İstekten gelen saat/revision/epoch, server-side karşılaştırmaya girdi olamaz. `feature_enabled=True` test çağrısı production entegrasyonu değildir. |
| Projection sonucu | Başarısız/eksik/stale/çelişkili kanıt `unknown`, `online=False`, `presence_verified=False`; olumlu durumda `online` üretir. Offline sonucu üretmez. | Panel yalnız accepted broker projection'ını dar yetkili endpoint'te göstermeli; access policy, principal görünürlüğü ve stale/error behavior ayrıca tasarlanmalı. | Projection nesnesi tek başına panel/API response sözleşmesi değildir. `principal_id` hassas iç metadata olabilir; response minimization ve caller authorization ayrıca gerekir. |

## Statik doğrulanan fail-closed sınırları

- `feature_enabled` varsayılanı `False`; değer `True` değilse ilk kontrolde
  `unknown/feature_off` döner.
- Eksik, yanlış türde, stale veya tutarsız peer/map/session/heartbeat
  kanıtları unknown'a iner; fixture doğrulanmış offline üretmez.
- Principal kimliği map binding'den seçilir. Heartbeat body claim eşitse
  yalnız göz ardı edilir; farklıysa unknown olur, claim principal seçmez.
- Projection saf Python fonksiyonudur; socket, auth store, panel, HTTP,
  heartbeat veya clock I/O yapmaz. Testteki başarılı durum tamamen
  sentetik dataclass örneklerine dayanır.
- Test kaynakları feature-off, sentetik pozitif eşleşme, eksik/stale/yanlış
  binding ve session, heartbeat binding/TTL, body spoof ve çakışan principal
  map dallarını içerir. Bu fixture kaynak envanteridir; testler bu görevde
  çalıştırılmadı.

## Production adapter için zorunlu kapılar

1. **Peer provenance:** `PeerEvidence` sadece broker'ın aynı accepted socket
   için kernelden aldığı credential sonucundan üretilsin; body/JSON constructor
   yolu bulunmasın. Source tag değil, broker process/connection sınırı güven
   kökü olsun.
2. **Map/session authority:** Map ve session verisi HTTP request'ten değil,
   broker-owned, access-controlled store ve authorization sonucundan gelsin;
   revision/epoch değişiminde eski evidence invalid olsun.
3. **Heartbeat freshness/replay:** Broker zamanı ve gözlem kaynağı server-side
   belirlensin; session generation başına sequence/nonce monotonluğu ve replay
   state'i kontrol edilsin. TTL tek başına replay/presence proof değildir.
4. **Feature-off ve response:** Default kapalı kalsın; ancak route authorization,
   broker failure→unknown, same-UID boundary, principal minimization ve
   end-to-end negatif/pozitif kabul tamamlanınca ayrı rollout kararıyla açılsın.
5. **Ayrı-UID sınırı:** SO_PEERCRED UID kanıtı aynı UID içindeki iki process'i
   ayırmaz. Kullanıcı/agent izolasyonu iddia edilecekse ayrı UID/service veya
   daha dar OS sınırı ve bypass testleri gerekir.

## Sonuç

#650 saf projection fixture'ı provenance'ı **üretmez veya doğrulamaz**; yalnız
trusted adapter'dan geldiği varsayılan nesnelerin iç tutarlılığını sınar.
Feature-off varsayılanı ve body principal claim'in kimlik seçmemesi doğru
fail-closed sınırlarıdır. Heartbeat replay/high-water kontrolü projection'da
yoktur ve production adapter'a bırakılmalıdır. Bu rapor herhangi bir
production presence, doğrulanmış principal veya çevrimiçi kullanıcı iddiası
oluşturmaz.

## Kaynaklar

- [#650 saf broker-principal projection](panel-presence-broker-principal-projection-650.md)
- `prototypes/panel-presence-principal/projection.py`
- `tests/test_panel_presence_broker_principal_fixture.py`
- [#494 presence kanıt kaynağı kararı](panel-presence-source-options-494.md)
- [#637 broker ayrı-UID host runbook'u](operator-broker-separate-uid-host-acceptance-637.md)
