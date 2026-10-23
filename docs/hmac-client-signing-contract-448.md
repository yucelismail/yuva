# Yuva HMAC istemci imzalama sözleşmesi

Bu belge `panel/auth.py` içindeki `canonical_request_bytes()` ve
`HMACAuthenticator.verify_request()` davranışını istemci geliştiricileri için
açıklar. İstemci ile doğrulayıcı aynı alanları aynı baytlarla kodlamalıdır;
JSON'u yeniden serileştirmek, URL'yi normalize etmek veya imza metnini farklı
Base64 biçiminde göndermek doğrulamayı bozar.

## Kapsam ve çalışma durumu

Bu belge, kaynakta tanımlanmış HMAC biçiminden çıkarılan istemci
sözleşmesidir; dağıtılmış/uygulanmış bir istemci kütüphanesi veya her ortamda
etkin bir özellik iddiası değildir. HMAC byte biçimi `panel/auth.py` içinde,
HTTP gate ve route politikası ise `panel/auth_integration_draft.py` ile
`panel/server.py` içinde tanımlıdır. Örnek yalnız yerel imza hesabını gösterir.

Sunucunun auth yolu `YUVA_AUTH_ENABLED=1` ile açıkça etkinleştirilir ve
önceden hazırlanmış auth state gerektirir. Varsayılan/`0` durumda eski davranış
sürer. Bir istemci bu belgeyi okuyarak ortamın auth'u etkinleştirdiği
sonucuna varamaz; dağıtım yapılandırmasını operatör doğrulamalıdır. İstemcinin
imza üretmesi tek başına kimlik bilgisi oluşturmaz veya sunucuda anahtar
kaydı açmaz.

## İmzalanan bayt dizisi

İmzalanan mesaj aşağıdaki sıradadır:

```text
ASCII("YUVA-HMAC-AUTH") || 0x00 || ASCII("v1")
|| frame(audience)
|| frame(principal_id)
|| frame(key_id)
|| frame(method)
|| frame(path)
|| frame(SHA256(raw_body))
|| frame(timestamp)
|| frame(nonce)
```

Her `frame(x)`, `x` uzunluğunun 4 bayt unsigned big-endian gösterimi ve ardından
`x` baytlarıdır: `uint32_be(len(x)) || x`. Uzunluk karakter değil bayt
uzunluğudur. Body'nin kendisi mesaj içine konmaz; body'nin 32 baytlık ham
SHA-256 özeti konur. Özetin hex metni değil, digest baytları kullanılır.

| Alan | Kanonik gösterim ve sınırlar |
|---|---|
| `audience` | ASCII kimlik: ilk karakter `[A-Za-z0-9]`, devamı `[A-Za-z0-9._:@-]`, toplam 1–128 karakter. İstemci bunu sunucu/operatör tarafından verilen değerle aynı kullanır. |
| `principal_id` | Aynı ASCII kimlik biçimi. İstek gövdesindeki `kimlik` bu alanın yerine geçmez. |
| `key_id` | Aynı ASCII kimlik biçimi; provision edilmiş anahtar kaydını seçer. |
| `method` | Büyük ASCII harflerden oluşur, 1–16 karakter (`POST` gibi). Küçük harfi otomatik büyütmeye güvenmeyin; büyük harf gönderip imzalayın. |
| `path` | Tam kanonik ASCII yol: `/` veya slash ile ayrılmış, boş olmayan `[A-Za-z0-9_-]+` parçalar. Query, fragment, yüzde kodlama, yinelenen slash, sondaki slash ve alternatif/alias yol kabul edilmez. |
| `body` | HTTP'ye gönderilecek **tam ham baytlar**. Boş gövde `b""` olarak imzalanır. JSON kullanılıyorsa önce tek kez UTF-8 baytlarına dönüştürün; imzadan sonra bu baytları değiştirmeden gönderin. |
| `timestamp` | Unix saniyesi, ASCII onluk ve başında gereksiz sıfır olmadan: `0` veya `[1-9][0-9]{0,11}`; üst sınır `253402300799`. İzin verilen zaman penceresi varsayılan olarak ±60 saniyedir (sunucu ayarı 1–300 saniye). |
| `nonce` | ASCII `[A-Za-z0-9_-]`, 22–128 karakter. Her imzalı istek için yeni, tahmin edilmesi güç bir değer üretin. Başarılı doğrulama nonce kaydı oluşturur. Tekrar reddi `(principal_id, key_id, audience, "METHOD path", nonce)` kapsamındadır; başka kapsamda aynı nonce ayrı kayıt olabilir. Kod kaydı `timestamp + window_seconds + 1` bitişiyle yazar ve zamanı geçmiş kayıtları temizler; bu nedenle tekrar koruması global veya süresiz değildir. |

Her alanın çerçeve uzunluğu en çok 4096 bayttır. İmzalama anahtarı 32 bayt
olmalıdır. Anahtar state içinde unpadded canonical Base64URL olarak tutulur;
bu belgeye, loglara veya istemci kaynak koduna gerçek anahtar koymayın.

## İmza ve HTTP header'ları

İmza şu şekilde hesaplanır:

```text
digest = HMAC-SHA256(secret_32_bytes, canonical_message)
signature = Base64URL(digest), `=` padding'i kaldırılmış
```

Sonuç 32 bayttır ve canonical, padding'siz Base64URL gösteriminde 43 karakter
olur (`A-Z`, `a-z`, `0-9`, `_`, `-`). Standart Base64 (`+`, `/`) veya sondaki
`=` karakterleri gönderilmez.

Entegrasyon taslağının beklediği başlıklar şunlardır; her biri tam bir kez
gönderilmelidir:

```http
X-Yuva-Key-Id: <key_id>
X-Yuva-Principal: <principal_id>
X-Yuva-Audience: <audience>
X-Yuva-Timestamp: <canonical Unix seconds>
X-Yuva-Nonce: <fresh nonce>
X-Yuva-Signature: <43-character unpadded Base64URL HMAC>
```

HTTP başlık adları büyük/küçük harfe duyarsızdır. Başlık değerleri HMAC mesajına
ayrı bir ham header bloğu olarak eklenmez; taslak bu altı değeri alıp
doğrulayıcıya geçirir. Taslak `headers.get_all()` ile her başlığın tam bir kez
bulunmasını ister, boş/yalnız boşluk değerini reddeder ve değerin başındaki ile
sonundaki whitespace'i `strip()` ile atar. Bu yüzden istemci her başlığı tek
kez ve kanonik değeriyle yollamalı, yinelenen header'a veya taşıma katmanının
header birleştirmesine güvenmemelidir. Ara katmanlar başlık değerlerini
değiştirebildiğinden, gönderilen timestamp/nonce/kimlik değerleri beklenmedik
biçimde normalize edilmemelidir.

## Raw body ve request-target

İmza, JSON nesnesine değil, gövdenin alınan ham baytlarına bağlanır. Örneğin
`{"a":1}` ile `{ "a": 1 }` farklı baytlar ve farklı imzalardır. JSON kütüphanesi
anahtar sırasını, boşlukları veya Unicode kaçışlarını değiştirebileceğinden,
önce gövdeyi üretin, sonra o aynı byte dizisini hem imzalayıp hem HTTP gövdesi
olarak gönderin. Gövdeyi UTF-8 dışında bir kodlamayla göndermek de imza
eşleşmesini bozar.

Doğrulayıcı `path` alanında query kabul etmez. Entegrasyon HTTP
request-target'ı `urlsplit()` ile inceler ve gelen hedefin doğrudan route
string'iyle eşit olmasını şart koşar. Örneğin `/api/yaz` imzalanacak ve
gönderilecek biçimdir; `/api/yaz?x=1`, `/api/yaz/`, mutlak URL veya kodlanmış
alias kabul edilmez. Genel path gramerine uymak tek başına yeterli değildir:
yalnız aşağıdaki route allowlist'inde açıkça kullanılan POST yolları gate'ten
geçebilir. İstemci kütüphanesinin URL'yi yeniden yazmadığını ve gönderilen
hedefin tam olarak imzaladığı path olduğunu doğrulayın. Mevcut sunucu
handler'ı `self.path` değerini entegrasyon katmanına verir; proxy veya HTTP
kütüphanesi request-target'ı dönüştürüyorsa bu sınır ayrıca uçtan uca kontrol
edilmelidir.

## HTTP taşıma koşulları (kaynakta doğrulanan)

İmza formatı ile HTTP framing ayrı katmanlardır. Güncel `panel/server.py`
POST handler'ı ve kaynak denetimi şu koşulları uygular:

- `Content-Type` taban türü `application/json` olmalıdır; `; charset=utf-8`
  gibi parametreler kabul edilir. Bu başlık HMAC canonical alanı değildir.
- `Transfer-Encoding` varsa istek reddedilir; chunked body desteklenmez.
- Gövde varsa tek `Content-Length` başlığı gerekir. Başlık yoksa mevcut
  handler gövdeyi boş (`b""`) kabul eder. Birden çok `Content-Length` body
  okunmadan reddedilir ve framing belirsizliğini kapatmak için bağlantı
  kapatılır. Tek başlıkta ASCII onluk uzunluk aranır; whitespace çevresi
  trim edilir. Uzunluk sıfırsa boş body'dir.
- POST body üst sınırı **1 MiB**'dir. Aşan istek body okunmadan `413` alır;
  bu sınır canonical HMAC alan uzunluğundan ayrı HTTP kuralıdır.
- Non-empty istemci body'si, tam olarak imzalanan byte'larla tek geçerli
  `Content-Length` üzerinden gönderilmelidir. Sunucu JSON'u ancak framing ve
  varsa HMAC doğrulamasından sonra parse eder.

Bunlar güncel kaynak davranışıdır; önerilen istemci biçimi de bu koşulları
izlemelidir. HTTP kütüphanesinin duplicate başlıkları birleştirme veya body'yi
yeniden kodlama davranışı kullandığınız istemcide ayrıca kontrol edilmelidir.

## POST route allowlist'i (kaynakta doğrulanan)

Gate yalnız `POST` isteklerine uygulanır ve scope tam `POST <path>` biçiminde
olur. `panel/auth_integration_draft.py:POST_ROUTE_POLICY` şu path'leri tanımlar:

| Path | Kaynaktaki policy | İstemci notu |
|---|---|---|
| `/api/katil` | `self` | Provision edilmiş principal kapsamı. |
| `/api/kalp` | `self` | Body kimliği yerine doğrulanmış principal kullanılır. |
| `/api/ayril` | `self` | Kendi principal'ı. |
| `/api/ad` | `self_or_admin` | Kendi adı veya operatörce yapılandırılmış admin. |
| `/api/rol` | `admin` | Admin scope/authorization gerekir. |
| `/api/sorumlu` | `admin` | Admin scope/authorization gerekir. |
| `/api/bas-denetci` | `admin` | Admin scope/authorization gerekir. |
| `/api/yaz` | `principal_actor` | Verified principal aktör olarak bağlanır. |
| `/api/ekran` | `self` | Kendi principal'ı. |
| `/api/not` | `closed` | Route key olsa bile kapalıdır; kullanılamaz. |
| `/api/gorev` | `admin` | Workflow işlemleri privileged policy altındadır. |

Bunlar entegrasyon taslağındaki route policy değerleridir; başarı garantisi
değildir. Auth gate kapalıysa legacy davranış geçerlidir; açıkken bilinmeyen,
query eklenmiş veya canonical olmayan path reddedilir. Key provision edilmesi,
scope ve payload policy'sinin de route için uygun olmasını gerektirir.

## Güvenli, yalnızca yerel imzalama örneği

Aşağıdaki örnek biçimi gösterir; rastgele oluşturulan anahtar sunucuda
provision edilmediği için hiçbir gerçek Yuva isteği doğrulayamaz. Gerçek
istemcide `secret` güvenli bir secret store'dan alınmalı ve operatörün aynı
kimlik bilgisi için provision ettiği 32 baytlık sır olmalıdır. Örnek ağa HTTP
isteği göndermez.

```python
import base64
import hashlib
import hmac
import secrets
import struct
import time

def frame(value: bytes) -> bytes:
    if len(value) > 4096:
        raise ValueError("field too large")
    return struct.pack(">I", len(value)) + value

def sign_post(*, secret: bytes, audience: str, principal_id: str,
              key_id: str, path: str, body: bytes):
    if len(secret) != 32:
        raise ValueError("secret must be exactly 32 bytes")
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(32)  # URL-safe; fresh per request
    fields = (
        audience.encode("ascii"), principal_id.encode("ascii"),
        key_id.encode("ascii"), b"POST", path.encode("ascii"),
        hashlib.sha256(body).digest(), timestamp.encode("ascii"),
        nonce.encode("ascii"),
    )
    message = b"YUVA-HMAC-AUTH\x00v1" + b"".join(frame(x) for x in fields)
    digest = hmac.digest(secret, message, "sha256")
    signature = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return timestamp, nonce, signature

# Offline demonstration only: this key is newly random and is not provisioned.
demo_secret = secrets.token_bytes(32)
body = b'{"metin":"Merhaba"}'
timestamp, nonce, signature = sign_post(
    secret=demo_secret, audience="yuva-prod", principal_id="client-17",
    key_id="key-2026-01", path="/api/yaz", body=body,
)
```

Gerçek istemci, dönen değerleri yukarıdaki header'lara yerleştirmeli ve tam
`body` baytlarını göndermelidir. `nonce` üreticisinin çıktısı alfabeye uymalı;
bu örnekte `token_urlsafe(32)` 43 karakter üretir. Anahtarı her istekte
üretmeyin: sunucudaki provision edilmiş anahtar ile eşleşen sırrı kullanın.

## Önerilen istemci hata önleme davranışı

- İmzalama ve gönderme arasında method, path, body, timestamp veya nonce'u
  değiştirmeyin.
- Her istekte yeni nonce kullanın; ağ hatasında aynı isteği tekrar yollamak
  gerekiyorsa yeni nonce ve yeni imza üretin. Uygulama işleminin idempotency
  davranışı nonce replay korumasından ayrıdır.
- Timestamp'i saniye cinsinden üretin; milisaniye göndermeyin. Saat kayması
  varsayılan pencereden büyükse istek reddedilir.
- Gerçek secret'ı loglamayın, kaynak koduna koymayın veya hata mesajına
  eklemeyin. İmza ve auth header'larını da gereksiz yere loglamayın.
- 401/403/503 yanıtlarını anonim istek veya yerel fallback izni olarak
  yorumlamayın. Operatörle provisioning, audience, kapsam, saat ve store
  durumunu kontrol edin.

## Kaynak kod eşlemesi

- Kanonik alan doğrulama ve frame: `panel/auth.py`
  (`_canonical_*`, `_frame`, `canonical_request_bytes`).
- HMAC doğrulaması, scope, zaman penceresi ve tek kullanımlık nonce:
  `panel/auth.py` (`HMACAuthenticator.verify_request`).
- Header adları, duplicate kontrolü ve exact request-target kontrolü:
  `panel/auth_integration_draft.py` (`_AUTH_HEADERS`,
  `AuthGate.authenticate_post`).
- Sunucu etkinleştirme ayarı ve pre-provisioned store yükleme:
  `panel/server.py` (`auth_gate_yukle`, POST handler).

Sunucu entegrasyonunda bugüne kadar yapılan değişiklikler ve deploy ayarları
bu istemci biçiminden ayrı doğrulanmalıdır. Özellikle server'ın feature flag'i,
provision edilmiş store'u ve HTTP önündeki proxy davranışı dağıtım başına
kontrol edilmelidir.
