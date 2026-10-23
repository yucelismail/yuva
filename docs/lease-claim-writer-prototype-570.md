# #570 — İzole lease claim writer prototipi

`prototypes/lease-presence/writer.py`, #555'teki claim sözleşmesinin dar bir
fixture uygulamasıdır. CLI veya panel bu modülü çağırmaz; testler yalnız geçici
`YUVA_DIR` benzeri dizinler kullanır. Writer, özel fixture işaret dosyası
olmadan kilit veya görev defteri oluşturmayı reddeder.

## Claim yazımı

- Görev defteri `.kilit` altında okunur, doğrulanır ve aynı kilit bırakılmadan
  güncellenir. `execution` lease nesnesi ile görevin `assignee` ve `durum`
  alanları tek JSON snapshot'ında atomik replace ile yazılır.
- Lease sahibi `owner_claim` olarak kaydedilir; `owner_trust` daima
  `unverified` olur. Presence, görünen ad, rol veya heartbeat claim girdisi
  değildir ve sahibi doğrulayamaz.
- İlk başarılı claim epoch `1`'den başlar. Önceki kayıt `closed`/`revoked`
  ise sonraki başarılı yeni claim epoch'u bir artırır. Aynı `operation_id`
  tekrarı aynı lease'i döndürür, yeni epoch üretmez.
- `pending_revision` yalnız kayıtlı assignee tarafından claim edilebilir.
  `active`, `expired_suspect`, `unknown` veya bozuk execution kaydı yeni claim'i
  reddeder; lease timeout'u tek başına requeue/reclaim sağlamaz.

## Sınırlar ve kanıt

Bu prototip lease yenileme/expiry, stale teslim fencing'i, reassignment veya
canlı görev writer entegrasyonu değildir. #572'nin geç teslim reddi işini
kapsamaz. Kalıcı epoch token'ını her mutation yolunda doğrulayan tek writer
olmadan production fencing garantisi vermez.

`tests/test_lease_writer.py` geçici fixture'larda claim alanlarının tek
snapshot'ta yazıldığını, epoch/idempotency davranışını, eşzamanlı claim'de tek
kazananı, reconciliation gereken kayıtta reddi ve replace hatasında eski
defterin korunmasını denetler.
