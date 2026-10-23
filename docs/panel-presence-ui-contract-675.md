# #675 — Panel presence UI sözleşmesi: unknown, host-online ve principal-verified

**Tarih:** 2026-10-23
**Durum:** Tasarım/kabul sözleşmesi; broker entegrasyonu, API şeması ve UI değiştirilmedi.
**Kaynaklar:** #650 sentetik projection, #667 provenance incelemesi, `panel/server.py`, `panel/ui.html`.

## Karar

Panel üç ayrı iddiayı birbirine karıştırmamalı:

1. **Unknown:** Kaynak veya tazelik kanıtı yok; panel kimsenin çevrimiçi ya da çevrimdışı olduğunu çıkaramaz.
2. **Host-online:** Bir host/agent çalışma zamanı ya da broker bağlantısı için güncel liveness sinyali var; bu sinyal bir Yuva principal'ının kimliğini doğrulamaz.
3. **Principal-verified online:** Güncel ve yetkili broker kanıtı, belirli principal'ı aynı bağlantı/session'a bağlar ve taze heartbeat ile online olduğunu doğrular.

Host-online bilgisi kişi satırının yeşil/“çevrimiçi” durumu olarak kullanılamaz. Bu üç durum, API ve UI'da ayrı alan/etiketlerle taşınmalıdır. Mevcut production panel yalnız `unknown` sağlar; tasarımdaki diğer durumlar henüz üretim sinyali değildir.

## Bugünkü kaynak davranışı

- `panel/server.py:1678-1705` `/api/veri` roster girdilerine `online=false`, `presence_state="unknown"`, `presence_verified=false` koyar. Kaynak yorumu, G1/W1b yokken kalıcı heartbeat/presence alanlarının doğrulanmış aktör kanıtı sayılamayacağını söyler.
- `panel/ui.html:547-555` yeşil çevrimiçi durumunu yalnız `online===true`, `presence_verified===true`, `presence_state==="online"`, geçerli tamsayı `online_sn` (1–300) ve son heartbeat'in istemci saatine göre gelecekte olmayıp TTL içinde olması halinde gösterir.
- `panel/ui.html:557-562` `presenceOffline()` şu an daima `false` döndürür; dolayısıyla online kapısından geçmeyen tüm kullanıcılar `unknown` olur. Panel bağlantı hatası da kullanıcıyı çevrimdışı saymaz.
- `son_okuma`, roster `bagli` değeri veya heartbeat gövdesindeki principal metni, mevcut response'ta doğrulanmış online iddiası için kullanılmaz. `host_online` diye ayrı bir production field yoktur.

Bu nedenle bugünkü panel davranışı fail-closed olarak belirsiz durum gösterir. İstemci kodunda pozitif online kapısının bulunması, API'den gerçek bir verified presence üretildiğini kanıtlamaz.

## Kavram ve kanıt sözleşmesi

| UI kavramı | Gerekli server-side kanıt | UI gösterimi | Bu gösterimin anlamı olmayanlar |
|---|---|---|---|
| **Unknown** | Kanıt eksik, stale, çelişkili, feature-off, malformed veya kaynağın provenance'ı doğrulanamıyor; API/panel hatası da bu sınıftadır. | Nötr gri “Durum doğrulanamıyor”; hata varsa ayrıca “Panel bağlantısı doğrulanamıyor”. | Offline, host down, son heartbeat kesin bitti veya principal yok demek değildir. |
| **Host-online** | Yalnız açıkça tanımlı host/process/broker liveness kaynağından güncel ve taze gözlem. PID/UID/socket/heartbeat kaynağı ve ölçüm zamanı server-side olmalı. | Nötr mavi/amber “Host etkin · kullanıcı kimliği doğrulanmadı” gibi; principal satırında çevrimiçi rozeti/yeşil kullanılmaz. | Agent/principal kimliği, kullanıcı oturumu veya Yuva yetkisi doğrulandı demek değildir. Persist edilmiş `bagli`, UI `son_okuma` ya da body claim tek başına bu kanıtı sağlamaz. |
| **Principal-verified online** | Bütün #650 bağları geçerli: aynı kabul edilmiş socket'ten kernel `SO_PEERCRED`; güncel/tekil/active UID→principal map; aynı peer PID/UID, map revision ve broker epoch'a bağlı authenticated+allowed session; exact `presence:read` scope ve süresi geçmemiş session; aynı session/epoch'a bağlı taze broker heartbeat. Production adapter ayrıca heartbeat replay/high-water ve trusted clock/generation kurallarını sağlamalıdır (#667). | Yeşil “Çevrimiçi · kimlik doğrulandı” yalnız principal'a ait doğrulanmış response için. İstemci yalnız API'nin typed boolean/state alanlarına bakar; principal kimliğini yalnız UI caller'ı için gerekli ve yetkiliyse gösterir. | Sentetik projection fixture'ının geçtiği, aynı UID'li süreçlerin birbirinden ayrıldığı veya provider/model oturumunun gerçekliği tek başına kanıtlanmış demek değildir. |
| **Principal-offline (ileride)** | Broker'ın güncel epoch'unda session'ın kapandığı/revoke edildiği ve principal için başka aktif session bulunmadığına dair authoritative state. | Ancak ayrı, açık offline state ve tazelik kuralı kabul edilirse çevrimdışı etiketi. | Heartbeat TTL'inin dolması, panel hatası, kayıt bulunmaması veya feature-off tek başına offline kanıtı değildir; bunlar unknown'dır. |

## API/UI alan sınırı

İleride production entegrasyonu tasarlanırsa host liveness ile principal presence ayrı typed alanlarda taşınmalı. Örnek semantik (bu görevde uygulanmamıştır):

```json
{
  "host_presence": {"state": "unknown|online", "observed_at": null},
  "principal_presence": {
    "state": "unknown|online|offline",
    "verified": false,
    "observed_at": null,
    "display_id": null
  }
}
```

`state=offline` yalnız yukarıdaki authoritative offline kanıtıyla kullanılabilir. Host alanı principal state'ini veya legacy `online` alanını yükseltemez. Mevcut response anahtarlarının geriye uyumlu anlamı `online` = principal online iddiası, `presence_verified` = bu principal iddiasının doğrulanması olarak kalmalıdır; host liveness bu anahtarlara yazılmamalıdır. Gerçek bir wire schema, source/freshness ve client migration ayrıca kabul edilmeden eklenmemelidir.

Production endpoint yalnız trusted server/broker projection'ından alan üretmelidir. `peer`, map, `session.authenticated`, scope, heartbeat zamanı/sequence veya principal ID gibi istek body/JSON alanları evidence olarak kabul edilmemelidir. Principal map/session metadata'sı public roster snapshot'ına gereksiz yere eklenmemelidir.

## #650/#667 fixture sınırı

`prototypes/panel-presence-principal/projection.py` feature-off varsayılanıyla saf bir fonksiyondur. Pozitif sentetik durumda tutarlı peer/map/session/heartbeat nesneleriyle `online=true`, `presence_state="online"`, `presence_verified=true` üretebilir; eksik/stale/çelişkili durumlarda `unknown` döner ve offline üretmez. Fixture socket açmaz, kernel `SO_PEERCRED` okumaz, auth store/session veya broker çağırmaz. Python dataclass girdileri kolayca oluşturulabildiğinden gerçek provenance kanıtı değildir.

#667 ayrıca projection'ın sequence için yalnız pozitif tamsayı kontrol ettiğini; replay/high-water state'inin olmadığını belirtiyor. Production adapter aynı session/generation başına monotonic sequence veya nonce/replay kararı vermeden fixture sözleşmesi production verified-presence iddiasına yükseltilmemelidir. `SO_PEERCRED` UID'si aynı UID altındaki süreçleri ayırmaz; böyle bir izolasyon gerekiyorsa ayrı UID veya daha dar OS sınırı ayrıca tasarlanıp doğrulanmalıdır.

## Gelecek kabul matrisi

Bir production consumer/adapter işi açılırsa en az şu dallar fixture ve end-to-end seviyelerinde ayrı doğrulanmalıdır:

| Durum | Beklenen projection | Beklenen UI |
|---|---|---|
| Feature kapalı; API yok/hatalı; eksik veya malformed roster | Principal unknown, verified false | Nötr unknown; çevrimdışı veya yeşil gösterme |
| Taze host liveness var; principal map/session yok | Host online, principal unknown | Host etkin etiketi; kişi çevrimiçi rozeti yok |
| Peer UID map dışı/stale/inactive ya da map principal çakışmalı | Principal unknown | Nötr unknown |
| Session auth/allow false; scope yanlış; peer/PID/UID/revision/epoch farklı; session expired | Principal unknown | Nötr unknown |
| Heartbeat yok, başka session/epoch'a bağlı, TTL dışı veya replay/high-water reddi | Principal unknown | Nötr unknown |
| Tam ve aynı socket/session/map/epoch bağları; taze replay-safe heartbeat | Principal online, verified true | Yeşil verified online |
| Yalnız heartbeat TTL dolmuş, disconnect/offline authority yok | Principal unknown | Nötr unknown; offline değil |
| Güncel broker state aktif session kalmadığını authoritative biçimde doğruluyor | Yalnız kabul edilmiş offline state | Çevrimdışı etiketi; kaynak ve tazelik erişilebilir olmalı |

Bu tablo gelecek kabul şartıdır; bu görevde yeni fixture veya UI testi eklenmedi/çalıştırılmadı.

## Tamamlanma ve sınırlar

Bu doküman mevcut UI/API davranışını #650 sentetik projection ve #667 provenance sınırlarıyla hizalar. Presence API'si, panel, broker/adapter, host socket/UID, auth, roster veya canlı servis değiştirilmedi. Aktif kullanıcı veya host hakkında yeni iddia üretilmedi.

## Kaynaklar

- [#650 broker principal projection fixture'ı](panel-presence-broker-principal-projection-650.md)
- [#667 projection provenance denetimi](panel-presence-provenance-audit-667.md)
- `panel/server.py:1678-1705` — mevcut unknown projection
- `panel/ui.html:547-564,1228-1232,1436-1444` — online gate ve UI tüketimi
- `prototypes/panel-presence-principal/projection.py`
- `tests/test_panel_presence_broker_principal_fixture.py` (bu görevde çalıştırılmadı)
