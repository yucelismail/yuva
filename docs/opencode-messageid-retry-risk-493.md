# Yuva #493 — OpenCode `messageID` ve tekrar gönderim riski

Kapsam: OpenCode resmi Server API dokümanlarında `messageID` alanının dedupe/idempotency garantisi olup olmadığını değerlendirmek ve timeout/unknown için retry kararı önermek. Salt-okunur rapor; OpenCode veya Yuva runtime'ı, kod ya da test çalıştırılmadı.

## Bulgular

OpenCode'un resmi [Server API referansı](https://docs.opencode.ai/docs/server/) şu alanları belgeliyor:

- `POST /session/:id/message` body'sinde isteğe bağlı `messageID?`; endpoint mesaj gönderip yanıtı bekliyor ve `{ info: Message, parts: Part[] }` döndürüyor.
- `POST /session/:id/prompt_async` aynı body'yi alıyor ve `204 No Content` dönüyor.
- `GET /session/:id/message` oturum mesaj listesini, `GET /session/:id/message/:messageID` belirli mesajı okuyor.
- Server her kurulumda `/doc` üzerinden OpenAPI 3.1 şeması yayımlıyor.

Doküman `messageID`'yi request body alanı olarak tanımlıyor; aynı ID ile tekrar POST edilince önceki isteği döndürme, ikinci mesajı bastırma, tool etkilerini tekilleştirme veya `Idempotency-Key` davranışı vaat etmiyor. `GET` ile mesaj arama desteği bir reconciliation girdisidir; POST idempotency garantisi değildir.

**Sonuç:** İncelenen resmi API belgelerinde `messageID` için idempotency veya duplicate önleme garantisi **belgelenmemiş**. Bu, implementasyonun tüm sürümlerde aynı ID'yi mutlaka iki kere işleyeceğini kanıtlamaz; yalnızca güvenli retry kararı için bu davranışa güvenilemeyeceği anlamına gelir. Canlı sunucu `/doc` şeması sürüme bağlıdır ve API dokümanı kendi başına davranış garantisi vermiyorsa runtime gözlemi de genel sözleşme sayılmaz.

## Timeout/unknown sonrası karar akışı

1. **İstek öncesi kayıt:** Provider'a çağrı yapmadan önce Yuva ingress message ID'si, kalıcı `operation_id`, `attempt_id`, hedef OpenCode instance/session, client `messageID` ve içerik fingerprint'ini durable outbox/receipt'e yaz. Hassas içerik yerine policy uyumlu redacted digest kullan.
2. **Kesin gönderilmedi:** İstek başlamadan hata olduğu veya transport'un kesin sıfır byte yazdığı kanıtlanmışsa aynı operation ve attempt içinde transport retry yapılabilir. Aynı `messageID` kullanımı bu durumda duplicate üretmez diye değil, ilk çağrının provider'a hiç ulaşmadığı kanıtlandığı için güvenlidir.
3. **Gönderim başladı, yanıt kayıp:** Partial write, full write sonrası timeout/reset, response parse hatası, `prompt_async` cevabının kaybı veya process crash `unknown` sayılır. Kör retry yok; aynı `messageID` ile retry'nin duplicate'i önleyeceği belgelenmemiştir. Yeni ID ile retry de ikinci mesaj/eylem yaratabilir.
4. **Salt-okunur uzlaştırma:** Aynı session için `GET /session/:id/message/:messageID` ve gerekiyorsa message listesi ile exact ID'yi kontrol et. Eşleşen kayıt bulunursa provider mesajı kanıtı olarak mevcut attempt'e iliştir ve status/history/event akışını izlemeye devam et; bu tek başına model yanıtı, tool işinin tamamlanması veya Yuva teslim makbuzu değildir.
5. **Kayıt bulunamadı:** “Bulunamadı” gönderilmedi kanıtı değildir. Async istek henüz görünmemiş, history eksik/stale veya request sonucu hâlâ açık olabilir. Backoff ile salt-okunur uzlaştırmaya devam et veya operatöre taşı; otomatik resend yapma.
6. **Operatör kararı:** Uzlaştırma sonucu çözülemiyorsa operatöre şu iki seçenek ve etkisi gösterilir: bekleyip yeniden salt-okunur kontrol etmek veya olası duplicate riskini kabul ederek yeni, ayrı `attempt_id` ve yeni `messageID` ile tekrar denemek. Karar, actor, gerekçe, eski attempt ve risk receipt'e append-only yazılır. Önceki unknown attempt silinmez/başarılı varsayılmaz. Tekrar güvenli görünen durumdaki provider kapasitesi ancak açık sürüm garantisi ve doğrulanmış kanıtla bu kararı değiştirebilir.
7. **Teslim sınırı:** Provider message görünmesi Yuva output'un kaydedildiğini kanıtlamaz. Yanıtın Yuva/artifact store'a kalıcı yazımı ayrı delivery receipt ister; Yuva görev review'ı da kendi task lifecycle geçişidir.

## Karar tablosu

| Gözlenen durum | Retry kararı | Gerekçe |
| --- | --- | --- |
| Çağrı öncesi hata veya kesin 0-byte yazım | Aynı operation/attempt içinde transport retry mümkün | İlk çağrının provider'a ulaşmadığı kanıtlı. |
| Kısmi/tam yazım sonrası timeout ya da response kaybı | `unknown`; otomatik retry yok | Provider işlemi almış olabilir, `messageID` dedupe garantisi yok. |
| Exact `messageID` için GET kaydı bulundu | Eski attempt'i uzlaştır; yeni mesaj gönderme | Provider message kaydı var; terminal yanıt/çıktı teslimi yine ayrıca kanıtlanmalı. |
| GET/list içinde kayıt bulunamadı | `unknown` kal; yeni gönderim operatör kararı ister | Yokluk görünümü, işlemin hiç kabul edilmediğini kanıtlamıyor. |
| Operatör yeni denemeyi açıkça seçti | Yeni `attempt_id` ve yeni `messageID`; olası duplicate'i görünür işaretle | Önceki attempt korunur; at-least-once risk kabul edilir, exactly-once denmez. |

## Uygulama için sınırlar

- `messageID`'yi korelasyon/reconciliation anahtarı olarak kullan; tek başına idempotency token sayma.
- `operation_id` aynı Yuva mesajının tekrar işlenmesinde stabil; yeni bilinçli deneme farklı `attempt_id` ve provider `messageID` alır.
- Aynı `messageID` ile yeniden POST ancak OpenCode sürümüne bağlı açık bir resmi garanti eklendiğinde, o garanti belirli endpoint ve yan etkileri kapsadığında tekrar değerlendirilir. Mevcut belgeler bu kapıyı karşılamıyor.
- `prompt_async` için `204` HTTP cevabı yalnız HTTP endpoint yanıtıdır; Yuva makbuzu veya tamamlanma kanıtı değildir.
- Mesaj ID'si bulunduğunda dahi tool side-effect'lerinin tekrarsız kaldığı varsayılmaz; exact ID lookup yalnız ilgili provider mesajı kaydını ilişkilendirir.

## Kaynaklar

- [OpenCode Server](https://docs.opencode.ai/docs/server/) — endpoint/body/response alanları, session message GET yolları ve `/doc` OpenAPI açıklaması. 2026-10-21'de kontrol edildi.
- `docs/session-response-yuva-receipt-correlation-489.md` — Yuva operation/attempt, provider state, unknown, reconnect ve output receipt ayrımı.
- `docs/task-mutation-failure-matrix-452.md` — belirsiz commit/delivery sonrası kör retry yapılmaması için Yuva failure matrix tasarımı.

Rapor yalnız resmi API belgeleri ve yerel sözleşme notlarının statik karşılaştırmasıdır. Belgedeki garanti yokluğu sonucu “OpenCode içinde dedupe kodu kesinlikle yok” iddiası değildir; hedef version `/doc` ve gerekiyorsa kaynak/izole kabul incelemesi olmadan daha ileri davranış varsayılmaz.
