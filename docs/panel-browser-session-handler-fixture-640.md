# Yuva #640 — Browser session / CSRF gerçek panel Handler fixture'ı

**Tarih:** 2026-10-23
**Sonuç:** **Üretim kabulü NO-GO.** Gerçek `panel.server.H` route dispatch'i, geçici loopback HTTP server ve sentetik session/CSRF adapter ile sınandı. Üretim auth varsayılanı açılmadı; servis veya canlı ledger kullanılmadı.

## Fixture sınırı

`tests/test_panel_browser_session_handler_fixture.py` gerçek `panel/server.py` modülünü geçici `YUVA_DIR` ile yükleyip `H` handler'ını ephemeral portlu `127.0.0.1` server'da çalıştırır. Test sürecinde `YUVA_AUTH_ENABLED=0` olarak kalır. Sentetik adapter gerçek handler'ın beklediği `authenticate_post()` ve `authorize_payload()` protokolünü uygular; session cookie, exact route scope, same-origin Origin ve CSRF token kararlarını test girdisinden verir.

POST route callback'leri test sırasında sentetik callback'lerle değiştirilmiştir. İzin verilen callback yalnız test dizinindeki `synthetic-ledger.jsonl` dosyasına route satırı ekler; auth/session retlerinin ledger byte hash'ini değiştirmediği ölçülür. Bu yöntem gerçek handler'ın auth sırası ve route dispatch'ini sınar; production API callback'lerinin domain yan etkilerini kanıtlamaz. GET `sayfa()` ve `veri()` fonksiyonları da canlı uygulama verisine girmemek için sentetik cevaplarla değiştirilmiştir.

## Gözlenen sonuçlar

| Kapsam | Gerçek `H` üzerinden gözlem |
|---|---|
| GET `/`, `/index.html`, `/api/veri`, `/veri` — cookie yok | Dört alias da `200` döndürüp shell/snapshot callback'ine ulaştı. Adapter'ın `authenticate_get()` çağrı sayısı sıfır kaldı. |
| Aynı dört GET — cookie var, shell/snapshot scope yok | Dört alias yine `200` döndürdü; adapter çağrılmadı. GET kimlik ve scope kontrolü gerçek handler'a bağlı değil. |
| 11 POST yolu — session yok | Her biri `401 session_required`; sentetik ledger byte'ları değişmedi, route callback çağrılmadı. |
| 11 POST yolu — session var, CSRF yok | Her biri `403 csrf_rejected`; byte'lar değişmedi. |
| 11 POST yolu — session + CSRF var, route scope yok | Her biri `403 scope_denied`; byte'lar değişmedi. |
| Kapalı `/api/not` — session + doğru CSRF + scope | `403 route_closed`; byte'lar değişmedi, callback çağrılmadı. |
| İzinli POST'lar — session + CSRF + scope | `/api/not` dışındaki 10 route handler dispatch'ine ulaştı; yalnız test ledger'ına satır eklendi. |
| `AUTH_GATE=None` — 11 POST yolu | Tüm 11 route callback'i çağrıldı ve test ledger'ına satır ekledi; browser session/CSRF kontrolü olmadan auth-off fallback mevcut. Bu gözlem auth-off fail-closed kabulini geçmez. |
| Bilinmeyen GET/POST | Her ikisi de 404; fallback route çağrısı ve ledger değişimi yok. |

Bu test, sentetik adapter ile gerçek `H.do_POST()` arasındaki POST kapı noktalarının beklenen çağrı protokolünü gösterebilir; bu adapter production browser-session sağlayıcısı değildir. Kaynaktaki varsayılan HMAC gate de cookie session gate değildir. Gerçek handler GET gate'ini çağırmadığı ve gate kapalıyken POST dispatch'i sürdürdüğü için #608 browser kabul matrisi mevcut production kaynakta **geçmiyor**.

## Doğrulama

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_browser_session_handler_fixture -v
```

Sonuç: **4 fixture testi geçti.** Test komutu sandbox içinde socket izni nedeniyle çalışmadı (`EPERM`); aynı test kullanıcı izniyle localhost ephemeral loopback portunda çalıştırıldı ve geçti. Yalnız `127.0.0.1` üzerinde geçici server açıldı, test sonunda kapatıldı. Üretim `YUVA_AUTH_ENABLED` ayarı veya servis ortamı değiştirilmedi.

## Kabul / takip işi

- Mevcut production davranış için kabul kararı **NO-GO**: dört GET alias anonim ve scope kontrolsüz; auth kapalı POST'lar route dispatch'e ulaşıyor.
- Bu görev session entegrasyonu veya auth varsayılanı uygulamaz. Production API callback'lerini açan kapsamlı integration kabulü için gerçek browser session sağlayıcısının route policy ile `H` GET ve POST dispatch'ine fail-closed bağlanması gerekir.
- Bu fixture auth-off `UCLAR` dispatch'ini ve auth gate varken ret önceliğini test eder; gerçek API callback'lerinin tüm domain invariantlarını veya canlı servis erişimini test etmez.
