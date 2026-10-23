# Panel live-board assignment HTTP fixture (#717)

**Tarih:** 2026-10-23
**Durum:** #660 fixture'ının canonical CLI → gerçek Handler → UI data contract zinciriyle genişletilmesi.

`tests/test_task_assignment_ephemeral_http.py` tek bir disposable data root
kullanır. Başlangıçta görev #717 synthetic ledger'da `pending` ve assignee'siz;
`reviewer`/`worker-b` roster kayıtları da aynı temp root içindedir. Gerçek
`bin/yuva gorev al 717 --from worker-b` subprocess'i görevi `assigned` yapar.

Ardından gerçek `panel.server.H` Handler, yalnız `127.0.0.1` üzerindeki
ephemeral porta bağlanır. Fixture browser-session kapısı ile `/api/veri` ve
`/` GET'lerini çağırır. API snapshot aynı `id=717`, `durum=assigned` ve
`assignee=worker-b` değerlerini döndürür; Content-Length gerçek response byte
uzunluğuna eşittir. HTML response'un UI contract'ı `assigned` durumunu aktif
tahta kolonunda filtreler ve kartın aynı görev ID'si ile atanmış kişiyi
göstermesini sağlayan alanları tüketir. GET sonrasında canonical ledger byte'ı
claim sonrası haliyle aynıdır.

Doğrulama:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_task_assignment_ephemeral_http -v
```

Sonuç: **1/1 geçti**. HTTP doğrulaması disposable root ve ephemeral loopback
portuyla yapıldı. Gerçek görev tahtası, canlı panel/port, üretim service,
provider veya kalıcı kullanıcı verisi kullanılmadı; UI JavaScript gerçek
tarayıcıda çalıştırılmadı, fixture served HTML içindeki data contract'ı
doğruluyor.
