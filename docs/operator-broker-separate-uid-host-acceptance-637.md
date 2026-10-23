# SO_PEERCRED ayrı UID host kabul ve geri alma runbook'u (#637)

**Durum:** Hazırlık runbook'u; host rollout'u yapılmadı. Mevcut prototip için
karar **NO-GO**.
**Amaç:** Gerçek signer UID'si ile broker UID'si arasındaki kernel peer
credential sınırını ve izinsiz UID retlerini canlı bir servise geçmeden önce
kontrollü bir Linux kabul ortamında kanıtlamak.

## Bugünkü kanıtın sınırı

`prototypes/operator-broker-uds/peercred.py` bağlı Linux AF_UNIX stream
socket'inden `SO_PEERCRED` okur ve UID→principal eşlemesini uygular. #615
fixture geçici socket ve gerçek syscall kullanır; fakat test istemcisi ile
broker aynı euid'de çalışır. Sahte frame UID'sinin allowlist'le eşleşmesi,
kernel UID eşleşmediği için reddedilir. Fixture ayrı UID, ayrı signer veya
broker servisi kanıtlamaz (`docs/operator-broker-peercred-fixture-615.md`,
`tests/test_operator_broker_peercred_fixture.py`). #594 ise protokol
sözleşmesidir; çalışan broker, HMAC signer, provision/revoke aracı veya
production HTTP bridge değildir. Bu nedenle mevcut checkout/host için ayrı UID
kabul edilmiş sayılamaz.

Bu runbook kullanıcı/UID oluşturmaz, servis başlatmaz, socket/izin değiştirmez,
key üretmez ve auth açmaz. Bu işlemler ileride yetkili host operatörü tarafından
ayrı rollout onayıyla yapılmalıdır.

## Kabul önkoşulları

Kabul çalışması yalnız disposable veya açıkça onaylanmış staging Linux hostta
başlatılır. Aşağıdaki her madde sağlanmadan socket'e istek gönderilmez ve
`operator` source class açılmaz:

1. Gerçek, incelenmiş broker ve signer release'i vardır; ikisi de test edilen
   source revision/digest ile bağlanmıştır. Broker `accept()` sonrasında bağlı
   socket'ten UID alır; frame parse, HMAC ve dispatch öncesi map kontrolü yapar.
2. Signer UID, broker/verifier UID ve her agent UID sayısal olarak ayrıdır.
   Broker auth store'u yalnız broker UID tarafından, signer key'i yalnız signer
   UID tarafından okunabilir. Agent UID'leri signer/broker UID'sinde çalışmaz.
3. UID→principal map ve broker store'un güven kökü, owner/mode ve yönetim yolu
   belgelenmiştir. Boş, bozuk, duplicate, stale veya devre dışı map varsayılan
   ret üretir. Map değişimi için generation/revision ve geri alma sahibi bellidir.
4. Private UDS dizini/socket owner, group, mode/ACL ve yaşam döngüsü belirlenmiş
   durumdadır. Socket grubuna üyelik yalnız bağlantı iznidir; broker her
   istekte gerçek peer UID ve işlem policy'sini ayrıca doğrular.
5. İstek allowlist'i, tam route/scope, HMAC key/audience, nonce kalıcılığı,
   `CommitUnknown` davranışı, downstream writer ve legacy HTTP bypass kararı
   #582/#594/#586 sözleşmeleriyle uyumludur. Auth-off HTTP'ye otomatik fallback
   bulunmadığı statik ve host kanıtıyla gösterilmiştir.
6. Operatör, gözlemci ve geri alma sorumlusu belirlenmiş; secret içermeyen kanıt
   deposu ile bakım penceresi hazırlanmıştır. Ham key, imza, Authorization
   header, request body veya gerçek credential test raporuna kopyalanmaz.

Bir önkoşul eksikse sonuç **NO-GO** olarak kaydedilir; eksikliği gidermek için
runbook sırasında üretim erişimlerini gevşetmeyin.

## Host kabul adımları

### 1. Başlangıç envanteri ve değişmezler

- Onaylı release, host/OS/kernel, broker ve signer executable kimliği/digest'i,
  service UID'leri, agent UID'leri, service manager unit'leri ve test zamanı
  kaydedilir. Süreç argümanları veya ortam dökümleri rapora alınmaz.
- Sayısal UID'lerin benzersizliği, supplementary group üyelikleri, HOME ve
  runtime dizinlerinin sahipliği, broker store ve signer key dizinlerinin
  erişim modu salt okunur incelenir. İnceleme hiçbir sahiplik/modu değiştirmez.
- Broker çalıştırılabilir dosyasının test edilen release'e ait olduğu ve
  server-side UID map'in beklenen revision'ı yüklendiği doğrulanır. `PID`,
  process adı, unit adı, environment, frame içeriği veya `--from` UID kanıtı
  olarak kabul edilmez.
- Başlangıçtan önce ilgili fixture/sürüm testleri ve release kabul kayıtları
  incelenir. #615 testi yalnız kernel syscall için ön kanıttır; multi-UID
  sonucunun yerine yazılmaz.

### 2. Socket ve policy gözlemi

- Broker kapalıyken yalnız onaylı service manager rollout prosedürü ile
  başlatılır. Runtime socket path'in parent dizini ve socket nesnesi için
  gerçek owner, group, mode/ACL ve beklenen dosya türü doğrulanır; path symlink
  veya beklenmeyen nesne ise durulur.
- Broker log/config readback'inden UID map revision, audience ve enabled
  principal listesi secret içermeyen biçimde eşleştirilir. Raw map içeriği,
  key materyali veya request gövdesi rapora kopyalanmaz.
- Gerçek socket bağlantısında broker'ın `SO_PEERCRED` UID'sini eşlediği ve
  gövdedeki `peer_uid`, `principal_id`, `kimden`, `--from`, PID/argv veya unit
  claim'lerini kimlik kanıtı saymadığı kod/release incelemesiyle bağlanır.

### 3. Gerçek ayrı-UID kabul matrisi

Her senaryo izole, sentetik ve etkisiz bir request ile çalıştırılır. Sonuçta
karar kodu ve dispatch sayısı kaydedilir; request içeriği kaydedilmez.

| İstemci / durum | Beklenen sonuç | Zorunlu kanıt |
|---|---|---|
| İzinli signer UID, doğru peer map + doğru principal/key/audience/scope | Kabul edilebilir; yalnız allowlist route'una tek dispatch | Kernel raporlu peer UID'si signer UID'ye eşit; tek dispatch makbuzu |
| Agent UID, frame'de izinli signer UID/principal iddiası | `rejected`, dispatch yok | Kernel UID agent UID; forged claim sonucu değiştirmiyor |
| Map'te olmayan ayrı test UID | `rejected`, dispatch yok | Gerçek UID map'te yok; sabit ret nedeni |
| Socket path'e OS izinleri gereği bağlanamayan UID | Connect reddi, dispatch yok | İzinli/izinsiz gerçek UID denemeleri ve değişmeyen socket mode |
| Bozuk, boş, duplicate-principal, stale veya yüklenemeyen map | Fail-closed; servis istek kabul etmez | Güvenli hata kodu; hiçbir HTTP/writer dispatch'i yok |
| İzinli UID ancak yanlış principal, key, audience, method/path, scope veya replay nonce | `rejected`/`unknown` sözleşmesine göre; dispatch yok | Her politika sınırı için ayrı sabit sonuç ve sıfır dispatch |
| Peer credential okunamıyor, socket tipi/ailesi yanlış, broker restart veya response kaybı | Reddet/`unknown`; kör retry veya legacy fallback yok | Downstream writer çağrısı yok; belirsiz sonuç uzlaştırma adımı |

Pozitif senaryo sadece tek doğru UID kombinasyonunda başarılı olmalıdır. Negatif
senaryolar ayrı gerçek UID'lerle çalıştırılmalıdır; aynı UID üzerinde map'i
değiştirerek yapılan sentetik kontrol multi-UID kanıtı sayılmaz. Root/admin
testi UID sınırını doğrulamaz ve gerçek operatör imzası kullanmamalıdır.

### 4. Sonuç ve açılış kararı

Kabul sahibi her tablo satırına `PASS`, `FAIL` veya `NOT RUN` yazar; release
digest'i, UID'lerin sayısal ilişki tablosunu (gereksiz kişisel hesap adları
olmadan), socket owner/mode, map revision, test id ve dispatch sayısını ekler.
Secret/key, imzalı frame, raw request, exception metni ve gerçek kullanıcı
credential'ı eklemez. Herhangi bir `FAIL`/`NOT RUN`, açıklanamayan `unknown`,
fazla dispatch, eski binary, aynı UID veya auth-off HTTP bypass varsa karar
**NO-GO**'dur. Kabul raporu kendi başına auth/custody marker'ını etkinleştirmez;
ayrı rollout onayı gerekir.

## Geri alma

Geri alma aşağıdaki sırayla yetkili operatörce yapılır; otomatik olarak eski
auth-off HTTP yoluna dönülmez:

1. Yeni signer isteği kabulünü kapat; signer istemcilerini durdur. Broker'da
   operator principal/custody'yi devre dışı bırak ve aktif bağlantı/iş kuyrukları
   olmadığını makbuzla doğrula.
2. Broker servisini onaylı service manager prosedürüyle durdur. Durduğunu,
   UDS path'inin artık dinleyen socket olmadığını ve bağlantı/dispatch
   oluşmadığını doğrula. Bilinmeyen path veya owner için silme yapma.
3. Uygun key lifecycle aracı mevcut ve kabul edilmişse operator key'ini revoke
   edip bağımsız readback al. Böyle bir araç yoksa manuel store edit ile
   rollback tamamlandı sayma; ilgili key/custody'yi kapalı kabul et ve yeniden
   başlatma.
4. UID map'i önceki onaylı revision'a ancak dış makbuzla doğrulanmışsa geri
   al; aksi halde tüm ilgili entry'leri disabled tut. UID'yi başka hesaba
   yeniden atama, group ACL'ini genişletme veya eski UID'yi tekrar kullanma.
5. Socket/runtime nesnesini yalnız doğrulanmış service owner, beklenen path ve
   inode/type eşleşiyorsa onaylı cleanup prosedürüyle kaldır. Başka nesneye,
   data root'a veya auth store'a dokunma.
6. Auth açılmadan önce broker durmuş, signer durmuş, eski key revoked/disabled,
   map kapalı, socket erişimi kapalı ve writer'da dispatch olmadığı kanıtlanır.
   HTTP auth-off veya doğrudan panel erişimi bir geri dönüş yolu değildir.
7. Kanıtlar belirsizse broker kapalı ve operator etiketi `unknown/unverified`
   kalır. Yeniden açılış, cause düzeltmesi ve tüm pozitif/negatif kabul
   matrisinin baştan geçmesi ile yeni rollout onayı gerektirir.

## Kabul kaydı şablonu

```text
Host / OS / kernel:
Test zamanı ve change ID:
Broker ve signer release digest:
Broker UID / signer UID / test agent UID'leri (numeric, birbirinden farklı):
Socket parent ve socket owner:group:mode:
UID map revision / audience ID (secret değil):
Test satırı → PASS|FAIL|NOT RUN → karar kodu → dispatch sayısı:
Legacy HTTP bypass kapalı kanıt referansı:
Rollback sonucu / key revoke-readback ref:
Kabul sahibi / bağımsız inceleyen:
Karar: GO | NO-GO
```

## Kaynaklar

- `docs/operator-broker-peercred-fixture-615.md` — mevcut aynı-UID kernel UDS
  fixture'ının kanıtı ve sınırları.
- `docs/operator-broker-uds-binding-594.md` — UDS framing, peer UID/principal,
  signer/broker custody, route policy ve rollout kapıları.
- `docs/operator-hmac-custody-decision-582.md` — ayrı signer/broker UID hedefi,
  enrollment/revoke ve same-UID NO-GO.
- `docs/auth-off-task-mutation-boundary-586.md` — broker dışı HTTP bypass ve
  auth-off fallback sınırı.
- `prototypes/operator-broker-uds/README.md` ve
  `tests/test_operator_broker_peercred_fixture.py` — mevcut fixture komutları
  ve test edilen durumlar.

Bu runbook uygulama veya host kabulü raporu değildir. Gerçek broker, signer,
çok UID'li test, key lifecycle ve servis yayını sağlanmadan ayrı UID güvencesi
iddia edilmez.
