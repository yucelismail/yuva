# #650 — Broker principal kanıtı olmadan panel presence doğrulanmaz

**Durum:** Feature-off sentetik projection fixture hazır.
**Tarih:** 2026-10-23
**Kapsam:** Saf model ve sentetik test verisi. Gerçek broker, panel auth, panel
`/api/veri`, heartbeat endpoint'i, canlı roster, OS hesabı veya socket
değiştirilmedi.

## Sözleşme

`prototypes/panel-presence-principal/projection.py` yalnızca şu kanıtlar aynı
anda eşleştiğinde `online=true`, `presence_state=online` ve
`presence_verified=true` üretir:

- `PeerEvidence`, kernel `SO_PEERCRED` kaynağı olarak işaretlenmiş PID/UID/GID
  içerir; UID, güncel ve tekil principal map kaydına eşlenir.
- Principal map kaydı etkin ve beklenen güncel revision'dadır.
- Session kanıtı aynı principal, peer PID/UID, map revision ve broker epoch'a
  bağlıdır; authentication ve izin doğrulanmıştır, scope tam `presence:read`
  ve session henüz sona ermemiştir.
- Heartbeat aynı session ve broker epoch'a bağlıdır ve izinli TTL içinde
  gözlemlenmiştir.

Feature varsayılanı kapalıdır. Eksik, stale, devre dışı, çelişkili veya
güvenilmeyen kanıt her zaman `unknown`, `online=false`,
`presence_verified=false` üretir. Heartbeat gövdesindeki principal adı
kimlik kanıtı sayılmaz; doğrulanmış principal'a aykırıysa sonuç yine unknown
olur. Fixture doğrulanmış `offline` durumu çıkarmaz.

## Fixture sınırı

Fixture socket açmaz ve `SO_PEERCRED` okumaz. `PeerEvidence` ile session
authenticity, gerçek üretim adapter'ından gelmiş kanıt değil, sentetik test
girdisidir. Aynı OS UID altındaki süreçleri ayırdığı veya provider/model
session'ının gerçekliğini kanıtladığı iddiası yoktur. Üretim entegrasyonu
ancak broker kimliği, session store/authorization ve panel veri sözleşmesi
ayrıca kabul edilirse tasarlanmalıdır. Bugünkü panel projection'ı tüm
kullanıcıları unknown tutmaya devam eder.

## Doğrulama

`python3 -m unittest tests.test_panel_presence_broker_principal_fixture -v`

Testler feature-off, geçerli eşleşme, eksik/stale peer-map-session-heartbeat,
yanlış UID/PID/principal/scope/epoch, inactive map, çakışmalı map ve gövdeden
principal spoof denemelerini kapsar.
