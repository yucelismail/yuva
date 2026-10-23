# Yuva #556 — lease ve presence hata sözleşmesi

**Durum:** Kaynak incelemesi ve ayrı saf karar prototipi. Canlı görev/presence
verisi, heartbeat, servis veya lease yazımı kullanılmadı.

## Bulgular

Mevcut Yuva heartbeat yolu kapalıdır: CLI `kalp`/`kalp-dongu` doğrulanmış
principal olmadığında ret verir; panel `/api/kalp` doğrulanmış broker kaynağı
olmadığı için reddedilir. Snapshot `son_kalp=null`, `online=false`,
`presence_state=unknown`, `presence_verified=false` döndürür. Bu haliyle Yuva
presence kanıtı görev sahipliğini yenileyemez.

`bagli`, sohbet/ekran etkinliği, `son_okuma`, unit/PID liveness veya istemci
`--from` etiketi online/işlem ilerliyor/lease sahibi kanıtı değildir. #531 ve
#482'deki offline evidence freshness boşluğu nedeniyle heartbeat yokluğu,
eski heartbeat veya TTL aşımı doğrulanmış offline üretmemelidir. Heartbeat
ayrıca işin ilerlediğini göstermez: canlı fakat askıda/kitlenmiş process, yeni
iş yapmadan kalp atabilir.

## Ayrı durumlar

| Sinyal | İfade ettiği şey | İfade etmediği şey |
| --- | --- | --- |
| Fresh authenticated presence heartbeat | Bağlı principal/instance'ın broker tarafından belirli epoch'ta yakın zamanda görüldüğü | Görev ilerlemesi, tool sonucu, mesaj okundu/teslim edildi, lease yenilendi |
| Explicit lease renewal request | Sahip, görev ve mevcut fencing token ile yenileme isteği | Kalıcı commit; CAS/store onayı olmadan lease hâlâ değişmemiştir |
| Lease store commit/CAS receipt | Tek otoritenin aynı lease/fence üzerinde yazımı kabul ettiği | Agent işi tamamladı veya reviewer onayı var |
| Missing/stale/unverified heartbeat | Yeterli güncel kanıt yok | Agent offline, öldü, görev terk edildi veya lease güvenle geri alınabilir |

Presence ve lease ayrı state machine olmalıdır. Heartbeat, yalnız fresh/auth
bağlamı koşullarında presence projeksiyonunu online yapabilir. Lease'i ancak
ayrı, açık ve authenticated renewal işlemi; task ID + lease ID + principal +
process instance/generation + fencing token + monoton sequence'i eşleyip
tek lease writer'ında CAS kazanırsa uzatabilir. Agent duvar saati deadline
belirlemez; broker kendi monotonic clock'unu ve boot/clock epoch'unu kullanır.

Unknown/stale presence ve lease süresi dolmadan önce: lease'i aynı sahibinde
ayrılmış tut, otomatik uzatma veya geri alma yapma. Deadline geçtiğinde:
durumu `reconcile_required`/insan incelemesi olarak tut; sadece süre veya
heartbeat yokluğuyla başka ajana reassign etme. Mevcut task writer fencing
token kontrol etmiyorsa, eski askıdaki process yeniden başlayıp geç mutation
yapabilir; güvenli otomatik reclaim kanıtlanamaz. Yeni owner verilmeden önce
eski generation'ı her mutation girişinde reddeden fence veya doğrulanmış
operatör stop/recovery gerekir. Geç gelen eski token'lı teslim de aynı
fence'de reddedilip audit/reconcile için korunmalıdır.

## Hata senaryoları ve önerilen sonuç

| Senaryo | Presence sonucu | Lease sonucu | Gerekli koruma |
| --- | --- | --- | --- |
| Legacy/unknown veya auth'suz heartbeat | unknown | Yenileme yok; mevcut lease korunur | Legacy satır UI/history için olabilir, lease input'u olamaz. |
| Ağ kesintisi/broker erişilemiyor | unknown | Önce tut; expiry sonrasında reconcile, reassign yok | Ağ yokluğu worker ölümünü kanıtlamaz; otomatik retry/claim yok. |
| Process scheduler tarafından askıya alındı | unknown (kanıt yaşlanınca) | Lease expire olsa bile reconcile | Process eski token ile geri dönebilir; fencing olmadan yeni sahip tehlikeli. |
| Canlı ama kilitli agent düzenli heartbeat atıyor | online (kimlik kanıtı tazeyse) | Heartbeat tek başına yenilemez; progress/safe-point renewal ayrı | Liveness ve ilerleme ölçütünü ayır. |
| Aynı UID'de birden fazla süreç aynı `--from` adını kullanıyor | unknown veya çakışma | Lease conflict → reconcile | UID ve isim aynı-UID process kimliği değildir; principal + instance/generation gerekir. |
| Sequence replay/geriye sarma | unknown | Yenileme reddi/reconcile | Broker son sequence'i saklar; duplicate sequence'i yeni kanıt saymaz. |
| Broker restart/restore | unknown; eski epoch geçersiz | Eski lease/cursor otomatik sürdürülmez | Yeni broker epoch; dış anti-rollback yoksa offline re-provision/reconcile. |
| Deadline geçtikten sonra eski heartbeat/owner teslimi | Process fresh ise presence online olabilir; sahiplik ayrı | Reconcile; eski fence ile commit reddi | Presence online olmasına rağmen lease expired olabilir. |
| Bir task için birden çok active lease | unknown/çelişkili | Reconcile, hiçbir owner'ı seçme | “En yeni heartbeat kazanır” yok; transaction/fencing incelemesi. |
| Authenticated explicit stop | Yalnız o instance generation için sonlandırma gözlemi | Lease release yine ayrı CAS | Stop request bile başka instance/worker'ın yokluğunu kanıtlamaz. |

## İzole prototip ve fixture planı

`prototypes/lease-presence/decision.py`, lease'in sona ermesi veya heartbeat
görülmemesinden otomatik reclaim çıkarmayan saf bir reducer önerir. Sonuç
yalnız `online` veya `unknown` presence'tır; offline kanıt kaynağı yoktur.
`renew_cas_candidate` gerçek yenileme değil, eşleşmiş açık isteğin lease
store'da CAS bekleyen tavsiyesidir. Expired lease, stale heartbeat ve aynı
task'teki birden fazla lease `reconcile_required` üretir.

İlk gerçek uygulamadan önce geçici fixture testleri en az şu varyantları
kapsamalıdır: taze ve stale heartbeat; future timestamp; imzasız/legacy
heartbeat; aynı UID'den iki process/generation; network timeout; askıda
process'in TTL sonrasında devamı; broker restart epoch'u; duplicate/geriye
giden sequence; lease expiry sınırındaki eşzamanlı yenileme ve claim; yeni
fence sonrası eski token'lı teslim; aynı task için iki lease. Her senaryoda
presence, lease, assignee ve task history öncesi/sonrası ayrıştırılmalı; unknown
durumunda task/assignee değişmediği kanıtlanmalıdır. Bu görevde test çalıştırma
veya canlı durum deneyi yapılmadı.

`prototypes/lease-presence/README.md` #555 görev lifecycle tasarımıyla sınırı
açık tutar. Üretim lease'i için tek durable writer, transaction/CAS, restart
reconciliation, fence enforcement ve online/offline evidence freshness kararı
ayrıca tasarlanıp kabul edilmelidir. Heartbeat/presence'ı lease deadline'ına
bağlamak bu kapıları kendiliğinden çözmez.
