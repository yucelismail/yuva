# İki UID SO_PEERCRED kabul koşucusu ve fixture sözleşmesi (#649)

`prototypes/operator-broker-uds/two_uid_acceptance.py`, #615'teki gerçek Linux
`SO_PEERCRED` helper'ını iki farklı OS UID altında çalıştıran sınırlı bir
fixture koşucusudur. Koşucu bir broker servisi, signer, HMAC, auth store veya
downstream writer kurmaz.

## Önkoşul ve çalıştırma

Yalnız disposable/onaylı Linux kabul hostunda root olarak, önceden oluşturulmuş
iki farklı **non-root** yerel hesap UID'siyle çalıştırın:

```sh
sudo python3 prototypes/operator-broker-uds/two_uid_acceptance.py \
  --broker-uid 2101 --signer-uid 2102
```

Koşucu UID veya hesap oluşturmaz; UID'leri sadece `pwd` üzerinden bulur ve
sayısal/GID ilişkisini raporlar. `setpriv` ile child process'leri bu UID'lere
düşürür. Root yalnız geçici dizini 0711, broker alt dizinini broker UID'sine
ait 0711 yapar. Socket bu geçici dizinde açılır, fixture için 0666 olur ve
çıktıda/raporda kalıcı socket path'i bırakmadan temporary directory ile
birlikte silinir. Gerçek Yuva kurulumuna, kullanıcı hesaplarına, servis
dosyalarına, `/run`, `YUVA_DIR`, key'lere veya auth ayarlarına dokunulmaz.

## Senaryo ve kabul

Broker child'ı broker UID'sinde çalışır; signer child'ı signer UID'sinde
bağlanır. Aynı socket üzerinde iki ayrı allowlist değerlendirmesi yapılır:

| Senaryo | Gerçek kernel peer UID | Fixture map'i | Beklenen sonuç |
|---|---:|---|---|
| İzinli signer | signer UID | signer UID → `fixture-signer` | Kabul, principal map'ten türetilir, fixture dispatch sayısı 1 |
| UID iddiası eşleşse de map dışında | signer UID | broker UID → `fixture-broker` | `peer_uid_not_allowlisted`, fixture dispatch sayısı 0 |

İlk frame kasıtlı olarak broker UID'si ve sahte principal iddiası taşır; buna
rağmen principal `SO_PEERCRED` UID map'inden `fixture-signer` çıkar. İkinci
frame izinli principal iddiası taşır; fakat UID map'te gerçek signer UID'si
bulunmadığı için reddedilir. Frame içeriği rapora yazılmaz. Sonuç JSON'u yalnız
fixture kapsamı, numeric UID, sabit karar kodu ve dispatch sayısını içerir.

`decision: PASS`, yalnız bu iki geçici fixture iddiasının geçtiğini belirtir;
`host_acceptance` daima `not-verified` kalır. Bu sonuç gerçek broker kodunun
`accept()` sonrası check sırasını, signer/key custody'yi, production socket
owner/mode/ACL'ini, nonce/HMAC/route policy'yi, HTTP bypass'ını, service
lifecycle'ını veya gerçek writer dispatch'ini kanıtlamaz. Bu sınırlar ve
rollout/geri alma koşulları [#637 host kabul runbook'unda](operator-broker-separate-uid-host-acceptance-637.md)
kalır.

Koşucu iki UID sağlanmamışsa, root değilse, `setpriv`/kernel özelliği yoksa
veya senaryo kabul ölçütlerinden biri tutmazsa `NO-GO` ve sıfır dışı exit code
verir. Runner yalnız açıkça verilen mevcut hesaplarla disposable hostta
çalıştırılmalıdır; geliştirici checkout'unda veya üretim kurulumunda otomatik
çalıştırılmaz.
