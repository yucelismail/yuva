# Yuva #698 — Browser GET/HTML route gate

**Durum:** Repo içi fail-closed route bağlantısı; browser session issuer/provisioning yok.
**Karar:** Korunan GET yolları session verifier kurulana kadar kapalıdır.

## Kanonik route policy

| Exact request target | Scope | Handler |
|---|---|---|
| `GET /`, `GET /index.html` | `browser.shell` | `sayfa()` |
| `GET /api/veri`, `GET /veri` | `snapshot.read` | `veri()` ve ortak snapshot sender |

`browser_get_route()` request target'ı bir kez sınıflandırır. Query veya trailing-slash eklenmiş korunan alias `400` alır; bilinmeyen/encoded path varyantı `404` alır. Başarılı dispatch ve auth aynı exact route değerini kullanır. `GET /api/veri` ve `GET /veri` tek `snapshot.read` policy'sini paylaşır.

## Session sınırı ve cevaplar

`H.BROWSER_SESSION_GATE` varsayılan `None`'dır. Bu durumda dört korunan yol da `503 browser_session_unavailable` döndürür; HTML/snapshot callback'leri çağrılmaz. Kurulu verifier için dar sözleşme `authorize_get(route, scope, cookie)` metodudur ve yalnız literal `True` kabul edilir. Eksik/ret edilen session `401`; verifier `PermissionError` ile scope reddederse `403`; provider hatası `503` olur. Birden fazla Cookie başlığı reddedilir.

GET gate HMAC `AUTH_GATE`, POST scopes, `X-Forwarded-User` veya diğer identity header'larını kullanmaz. Mevcut repo'da browser session store/issuer adapter'ı olmadığı için bu teslim auth sağlayıcısı, login, TLS/proxy veya provisioning eklemez. Gate kurulmaması anonim fallback anlamına gelmez. Tüm cevaplarda mevcut no-store ve security header policy'si `end_headers()` tarafından uygulanır.

## Doğrulama ve sınırlar

Ephemeral HTTP fixture'ları dört route'ta session yok, doğru scope, eksik scope ve adapter yok durumlarını; handler çağrılarının kapı öncesi sıfır olduğunu doğrular. GET snapshot/error/budget fixture'ları ayrı session adapter'ı enjekte ederek çalışır. Dört ilgili test modülü toplam **19 test** geçti.

Canlı panel/port, auth store, kullanıcı hesabı, browser session veya proxy değişmedi. Production session issuer ve browser access için ayrıca gerçek adapter/provisioning, TLS/backend erişim kapısı ve owner kabulü gerekir.
