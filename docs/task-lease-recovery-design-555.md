# Yuva #555 — Görev lease'i ve çökme sonrası kurtarma tasarımı

**Durum:** Salt kaynak incelemesi ve tasarım önerisi. CLI, panel, görev verisi,
servis veya worker davranışı değiştirilmedi; çökme/hata enjeksiyonu ve runtime
denemesi yapılmadı.

## Karar özeti

`queued/claimed/done/failed` durumlarını bugünkü `durum` alanına doğrudan
eklemeyin. Yuva'daki iş yaşam döngüsü ile yürütme sahipliği farklı şeyleri
anlatır. Mevcut `pending/assigned/pending_revision/pending_*_review/verified/
dropped` görev durumları korunmalı; lease, görevin yanında ayrı ve sürümlü bir
yürütme kaydı olmalıdır.

Önerilen kavramsal eşleme:

| Scheduler terimi | Yuva'daki karşılığı |
|---|---|
| `queued` | `durum=pending`; göreve bağlı bir `pending` iş varsa ayrıca uygunluk kuralları gerekir. |
| `claimed` | Kilit altında claim edilmiş `durum=assigned` + geçerli `lease` sahibi/epoch'u. Bugün `assigned` tek başına lease değildir. |
| `done` | İşçi teslimi sonrası `pending_gorevli_review` veya `pending_verification`; nihai tamamlanma yalnız `verified`. Tek bir `done` bunları doğru temsil etmez. |
| `failed` | Bugünkü görev durumlarında karşılığı yok. Hata gözlemi/lease sonucu ayrı tutulmalı; görev `assigned` kalabilir ve kurtarma kararı bekler. |

İlk uygulanabilir aşama, lease süresi dolunca **otomatik assignee değişikliği
yapmayan** `expired_suspect → reconcile/human decision` akışıdır. Otomatik
yeniden claim ancak eski worker'ın artık commit edemediğini fencing token ile
kanıtlayıp/uygulayıp ve çözümlenmemiş sonuçları uzlaştırdıktan sonra açılmalıdır.
Yalnız heartbeat zaman aşımına dayanarak görevi `pending` yapmak iki ajanın
aynı anda çalışmasına yol açabilir.

## Mevcut akıştan doğrulananlar

- `bin/yuva` geçiş yorumunda `pending|pending_revision → assigned` claim'i;
  `assigned → pending_gorevli_review|pending_verification` teslimi;
  review'dan verification/revision ve review'dan `verified`/revision
  geçişlerini tanımlar. `verified` ve `dropped` terminaldir.
- `gorev_guncelle()` ortak `.kilit` altında görev snapshot'ını yükleyip
  değiştirir. `cmd_gorev_sonraki()` aday seçimi, assignee ataması ve `assigned`
  kaydını aynı kilitli bölümde atomik yapar. Paralel claim'lerden yalnızca biri
  durumu önce değiştirir; diğeri yeni state'i görür.
- `cmd_gorev_al()` yalnız `pending`/`pending_revision` alır; başka assignee
  varsa reddeder. `cmd_gorev_teslim()` mevcut `assigned` durumu ve assignee
  eşleşmesini arar. Mevcut CLI'de claim ve teslim kalıcıdır, heartbeat/TTL
  yenilemesi yoktur.
- `assigned`, hangi assignee'nin işi almış olduğunu söyler; çalışanın canlı
  olduğunu, lease'i yenilediğini veya oturumunun yalnız o işe bağlı olduğunu
  kanıtlamaz. #481 tek aktif yürütme görevini politika olarak önerir, fakat
  bugünkü CLI farklı görevlerde bu sınırı zorlamaz.
- Görev snapshot'ı ile JSONL bildirimi ayrı yazılır. Bildirimin kaybolması,
  görev commit'inin olmadığı anlamına gelmez (#437/#452). Aynı UID içindeki
  doğrudan `--from`/legacy writer kullanımı da kriptografik worker kimliği ya da
  lease fencing sağlamaz (#532/#552).

## Ayrı lease kaydı

Bir görev kaydı için olası additive alan (alan adları öneridir):

```json
{
  "execution": {
    "lease_state": "active",
    "owner_claim": "worker-id-as-claim",
    "lease_epoch": 12,
    "lease_id": "opaque-random-id",
    "claim_operation_id": "stable-operation-id",
    "claimed_at": "UTC timestamp",
    "heartbeat_at": "UTC timestamp",
    "expires_at": "UTC timestamp",
    "worker_generation": "process-or-broker-generation",
    "checkpoint_ref": null
  }
}
```

Bu kayıt Yuva `durum`unun yerine geçmez. `owner_claim` bir `--from`/model
kimliği iddiası olabilir; doğrulanmış principal olduğu varsayılmaz. Lease
yenileme/teslim değişiklikleri `gorevler.json` üzerinde mevcut canonical writer
ve aynı kilit/CAS kurallarıyla commit edilmelidir. Scheduler belleği ya da
heartbeat dosyası tek başına lease otoritesi olamaz.

`lease_epoch` her başarılı yeni claim'de artan fencing generation'dır.
Heartbeat, checkpoint ve teslim isteği `task_id + lease_id + lease_epoch`
taşır; mevcut kayıtla eşleşmiyorsa reddedilir. Lease süresinden sonra gelen eski
epoch'lu teslim yeni assignee'nin durumunu değiştiremez. Bu koruma ancak tüm
task writer'ları token'ı doğrularsa işler; eski/alternatif CLI kopyaları aynı
veriye yazabiliyorsa rollout kapısıdır.

Lease zamanı için öneri: aynı hostta UTC `expires_at` kalıcı gösterimdir, ancak
çalışan süreç kendi monotonic deadline'ını ve process/broker generation'ını
kullanır. Host reboot, saat geriye sıçraması, store restore'u veya generation
doğrulanamaması lease'i canlı kabul ettirmez; `unknown/reconcile_required`
üretir. Ajan heartbeat'i (kendi bildirdiği) OS process liveness veya kimlik
kanıtı yerine geçmez.

## Durum ve yarış tablosu

| Olay / mevcut durum | Atomik koşul ve kayıt | Sonuç | Güvenli takip |
|---|---|---|---|
| İlk claim: `pending` (veya sahibi için `pending_revision`) | Kilit altında kanonik durumu ve assignee uygunluğunu oku; lease yok/claim edilebilir olmalı. `lease_epoch` artır, yeni `lease_id` ve operation receipt yaz, `assigned` ve assignee'yi aynı snapshot'ta commit et. | `assigned + active lease`. | Bildirim commit'ten sonra gönderilir; eksik bildirim claim'i geri almaz. |
| İki worker aynı görevi claim ediyor | Her ikisi de aynı compare-and-set önkoşulunu ister. | İlk atomik commit kazanır. İkinci güncel kaydı okuyup başka owner/active lease görür ve reddedilir; ikinci lease üretilmez. | Sonucu belirsiz CLI/HTTP yanıtında yeni claim denemeden önce task + operation receipt'i oku. |
| Sahibi lease süresi dolmadan heartbeat gönderir | Task `assigned`; lease ID ve epoch eşleşir; lease hâlâ aktif sürede ve writer commit'i başarılıdır. | `heartbeat_at/expires_at` uzar, epoch değişmez. | Heartbeat kayıt başarısı doğrulanamazsa worker eylemi durdurup reconcile eder; süresi geçtiyse eski token ile yenileme yoktur. |
| Süre dolar; process/session hâlâ çalışıyor olabilir | `expires_at` geçmiş ama eski worker durduruldu/fenced edildi kanıtı yok. | Yuva durumu `assigned` kalır; lease `expired_suspect`/occupancy `unknown` olarak görünür. Claim kapalıdır. | Liveness, checkpoint ve pending write/approval receipt'lerini salt okunur uzlaştır; gerekirse insan kararı bekle. |
| Worker heartbeat'i kesilir, ama süre henüz dolmadı | Süre ve doğru epoch kontrolü. | Lease active kalır; başka worker alamaz. | Süre sonu geldiğinde yukarıdaki `expired_suspect` uygulanır. Kısa iletişim aralığı çift çalışmayı önlemek için toleranslanır. |
| Süresi dolmuş lease'i yeni worker almak istiyor | Eski token tüm mutasyon/teslim yollarında reddediliyor; eski process/session sonlandırıldığı veya eylem kabiliyeti geri alındığı doğrulanmış; son task/operation/provider yazımları uzlaştırılmış; checkpoint kararı belli. | Yeni epoch/lease ile atomik reassignment yapılabilir. İş `pending`e düşürülmeden `assigned` kalır ve yeni assignee/lease aynı commit'te yazılır. | Tarihçeye eski ve yeni lease ID/epoch, gerekçe ve karar kaydı ekle. Bu şartların bir kısmı yoksa insan müdahalesi gerekir. |
| Eski worker geç teslim gönderiyor; task hâlâ aynı lease'te | `assigned` ve `lease_id/epoch` güncel. Submit ile lease kontrolü tek kilit/CAS bölümünde. | Lease commit'i/teslim yarışı atomik olarak sıralanır: teslim önce commit olursa review durumuna geçer ve requeue şartı boşa düşer; expire/claim önce commit olursa eski teslim reddedilir. | Sonuç/commit belirsizse mevcut durum ve operation receipt'i oku; kör retry veya ikinci assignee yok. |
| Eski worker geç teslim gönderiyor; yeni lease çoktan claim edilmiş | Teslim token'ı mevcut `lease_epoch` ile uyuşmaz. | Eski teslim `stale_lease` olarak reddedilir; task/new lease değişmez; artifact varsa quarantine/ayrı inceleme. | Yeni assignee ve reviewer'a gecikmiş teslim/artefact bilgisi göster; otomatik üzerine yazma yok. |
| Worker başarısız/çöktü, commit sonucu bilinmiyor | `write_started` veya işlem sonucu/bildirim belirsiz. | `failed` ya da `pending` yazılmaz; `commit_unknown`/`reconcile_required` operasyon gözlemi korunur, son teyitli task durumu kalır. | Aynı operation ID ile kanonik kayıt/reconciliation; uzak yan etki varsa read-only durum sorgusu. Bulunamadı sonucu tek başına yokluk kanıtı değildir. |
| İşçi teslim etti; inceleme bekliyor | Güncel lease'in geçerli epoch'uyla teslim compare-and-set edildi. | `pending_gorevli_review` veya `pending_verification`; execution lease kapanır. `done` değildir. | İlk kontrol/denetim kendi geçişinde; reviewer sonucu işçi lease'iyle değiştirilmez. |
| `pending_revision` | Review açıkça revizyon kaydetmiştir. | Revizyon aynı assignee'de kalır; önce eski execution lease kapatılır. | İşçi yeni claim/lease ile revision'ı sürdürür; önceki epoch teslim edemez. |
| `verified` veya `dropped` | Terminal transition kanonik reviewer/iptal yolu ile commit edilmiştir. | Lease kapalı/revoked; claim ve heartbeat reddedilir. | Terminal state geriye alınmaz; yeni iş gerekiyorsa yeni task. |

## Otomatik requeue için kapılar

Otomatik yeniden claim/reassignment ancak aşağıdakilerin tümü uygulanıyorsa
güvenli adaydır:

1. **Tek canonical writer:** claim, heartbeat, teslim, revoke ve lease expiry
   aynı task kilidi/CAS protokolündedir; tüm desteklenen CLI/panel yolları bu
   writer'ı kullanır.
2. **Fencing:** her yazma ve teslim güncel `lease_epoch` ile doğrulanır. Eski
   process yeni owner'dan sonra task, checkpoint, artefact receipt veya mesaj
   commit edemez. Yalnız timeout veya `owner_claim` kıyaslaması yetersizdir.
3. **Eski yürütme durduruldu:** sağlayıcı/worker session'ı kapatıldığı ya da
   mutation capability'si revoke edildiği pozitif kanıtla doğrulanır. “Heartbeat
   gelmedi”, “process görünmüyor” veya presence `unknown` negatif kanıt değildir.
4. **Sonuçlar uzlaştırıldı:** yazılmış/olası provider istekleri, task mutation
   operation'ları, outbox mesajları, approval ve artefact write'ları
   terminal/çözümlenmiş ya da açıkça operator'a devredilmiştir. Bilinmeyen dış
   etki varken otomatik tekrar yoktur.
5. **Checkpoint ve yan etkiler:** işin kalıcı checkpoint'i vardır ve yeniden
   başlatma idempotenttir ya da iş açıkça yan etkisiz/safe-to-replay olarak
   sınıflandırılmıştır. Dosya değişikliği, publish, dış API, para/izin gibi yan
   etkiler varsa bağımsız dedupe/compensation kararı gerekir.
6. **Kalıcı karar kaydı:** expiry, eski lease revoke, yeni claim/epoch ve
   gerekçe aynı denetlenebilir task geçmişi/operation makbuzuna yazılır. Store
   commit'i belirsizse requeue durur.

Bu kapılardan biri yoksa otomatik `assigned → pending` veya başka assignee'ye
devir yapılmaz. Süre dolumu uyarı/inceleme başlatır; task `assigned` ve lease
`expired_suspect/unknown` olarak kalır. İnsan eski worker'ı durdurur, task ve
çıktıları inceler, çözülemeyen dış etkileri uzlaştırır ve explicit revoke/retry
kararı verir. Bu sırada aynı task için ikinci worker claim edemez.

## Uygulama kabul ölçütleri (öneri)

- İki paralel claim için tek lease ve tek assignee oluşur; kaybeden güncel
  assignee'yi değiştirmez.
- Yalnız doğru lease ID/epoch heartbeat yeniler; eski/yanlış token ve süresi
  geçmiş heartbeat reddedilir. Süre taşması, reboot ve saat gerilemesi `unknown`
  üretir; kendiliğinden canlılık/boşluk varsaymaz.
- Expiry tek başına requeue etmez. Eski worker hâlâ yazabiliyorsa yeni claim
  engellenir; requeue önkoşullarının her birinin başarısız olduğu durumlar
  fail-closed kalır.
- Geç teslim ile expiry/reassignment yarışı tek kilit/CAS altında deterministik
  sıralanır; stale epoch teslimi yeni işin üzerine yazamaz.
- `pending_revision`, review kuyruğu, `verified`/`dropped` terminal durumları ve
  geçmiş görevler lease işiyle yanlışlıkla claim edilemez. `done` review veya
  verified ayrımını gizlemez; `failed` belirsiz commit'i maskelemez.
- Mutation yanıtı/JSONL bildirimi kaybında görev kaydı ve operation receipt'i
  kanonik kaynaktır. Bilinmeyen sonuç aynı operation ile uzlaştırılır; kör
  requeue/retry yoktur.
- Actor `--from`/model etiketi doğrulanmış principal sayılmaz; lease token'ı da
  tek başına insan/worker kimliği veya eylem yetkisi değildir. Yetki ayrı
  principal/policy kapısında değerlendirilir.

Bu ölçütler tasarım için kabul kapılarıdır; bu görev kapsamında kod/test
uygulaması değildir.

## Dayanaklar ve sınırlar

- `bin/yuva`: `gorev_guncelle`, `cmd_gorev_al`, `cmd_gorev_sonraki`,
  `cmd_gorev_teslim` ve görev geçiş yorumları.
- `docs/task-switching-state-contract-481.md`: `assigned` aktif slot yorumu,
  review/revision davranışı, çift claim ve belirsiz sonuç sınırları.
- `docs/task-mutation-idempotency-outbox-design-437.md` ve
  `docs/task-mutation-failure-matrix-452.md`: mutation receipt, commit/delivery
  ayrımı, unknown ve güvenli retry sınırları.
- `docs/task-actor-role-trust-boundary-532.md`: `.kilit`/`--from` dosya
  tutarlılığı ile principal doğrulamasını ayırır.
- `docs/task-ledger-single-writer-552.md`: desteklenen CLI/panel writer yolu ve
  eski kilitsiz writer riskinin kapsamı.
- `prototypes/task-scheduler/README.md`: salt okunur scheduler karar taslağı;
  persistence, task store, lock, claim veya lease uygulaması değildir.

Bu tasarımda lease, mesaj bildirimi, provider receipt'i ve Yuva reviewer kararı
ayrı kayıt/kanıt katmanlarıdır. Lease modeli onları tek bir `done/failed`
sonucuna indirgemez.
