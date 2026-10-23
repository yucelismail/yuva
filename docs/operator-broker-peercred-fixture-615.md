# Operator signer–broker UID eşleşmesi için Linux peer-credential fixture (#615)

**Tarih:** 2026-10-23
**Durum:** Linux UDS `SO_PEERCRED` fixture kabul testi tamamlandı.
**Sınır:** Yalnız geçici dizin içinde geçici Unix domain socket açıldı. UID, kullanıcı hesabı, broker servisi, signer key'i veya auth store oluşturulmadı; canlı socket/host yapılandırması incelenmedi.

## Kabul edilen davranış

`prototypes/operator-broker-uds/peercred.py` gerçek Linux `getsockopt(SOL_SOCKET, SO_PEERCRED)` çağrısını yapar. `authorize_socket_peer()` principal'ı yalnız o connected AF_UNIX stream socket'inden okunan numeric UID'yi doğrulanmış UID→principal allowlist'inde arayarak üretir. Kernel credentials alınamıyorsa, socket tipi yanlışsa veya mapping boş/bozuk/çakışmalıysa ret verir.

Test geçici dizinde filesystem UDS kurar ve gerçek client/accepted socket üzerinden peer credentials alır. Frame'e konan sahte `peer_uid` allowlist değerine eşitse bile actual kernel UID başka olduğunda bağlantı reddedilir. Gerçek UID map'teyse principal kabul edilir. Böylece frame/body değeri veya `--from` iddiası kernel peer UID yerine geçemez.

## Fixture kanıtı

`tests/test_operator_broker_peercred_fixture.py` şu durumları sınar:

1. Gerçek socket peer UID allowlist'ten principal'a eşlenir; PID ve UID kernel sonucuyla mevcut test sürecine karşılaştırılır.
2. İstemci frame'inde sahte `peer_uid` olsa bile map yalnız bu sahte UID'yi içeriyorsa gerçek socket UID eşleşmediğinden ret alınır.
3. Boolean/boş/duplicate-principal UID map'leri reddedilir; Linux `SO_PEERCRED` özelliği yokmuş gibi olduğunda kapı fail-closed kalır.
4. Unix olmayan veya stream olmayan socket reddedilir.

Çalıştırma: `python3 -m unittest tests.test_operator_broker_peercred_fixture -v` — **3 test geçti**.

Test gerçek kernel UDS çağrısı gerektirir; bu sandbox'ta socket açma `EPERM` verdiği için test onaylı sandbox dışı hedefli çalıştırmada geçti.

## Kanıtın sınırı

Fixture aynı mevcut OS UID'sindeki test süreciyle kernel UID eşleşmesini ve farklı beklenen UID'ye karşı ret davranışını gösterir. Ayrı bir gerçek UID'den bağlantı, root-owned üretim map'i, socket parent/socket ACL'leri, broker key custody, HMAC doğrulaması, dispatch, nonce store veya kullanıcı hesabı izolasyonu kanıtlamaz. Production rollout ya da iki UID'li custody kabulü değildir. Ayrı-UID host kabulinin gerekliliği [#594 sözleşmesinde](operator-broker-uds-binding-594.md) ve [#582 custody kararında](operator-hmac-custody-decision-582.md) kalır.
