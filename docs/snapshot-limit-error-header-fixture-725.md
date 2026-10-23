# Yuva #725 — snapshot limit hata yanıtı header fixture'ı

`tests/test_panel_snapshot_budget_integration.py` gerçek panel HTTP handler'ı
üzerinden snapshot hata yollarını doğrular. Aşağıdaki cevaplarda `Cache-Control:
no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
`X-Frame-Options: DENY`, JSON content type ve gövdeyle eşleşen
`Content-Length` denetlenir:

- Snapshot bütçe feature flag'i geçersiz olduğunda dönen 503.
- Kaynak boyut sınırı aşıldığında dönen 503.
- Selector `snapshot_response_unavailable` döndürdüğünde oluşan hata yanıtı.

Çalıştırma:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_snapshot_budget_integration -v
```

Sonuç: 7 test geçti. Sandbox yerel TCP socket açmayı engellediğinden HTTP
fixture aynı komutla sandbox dışında çalıştırıldı. Test, hata yanıtlarında
ortak `H.end_headers()` politikasının korunduğunu gösterir; canlı servis veya
production konfigürasyonu üzerinde değişiklik yapmaz.
