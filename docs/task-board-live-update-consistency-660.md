# #660 — Görev panosu canlı güncelleme tutarlılığı fixture'ı

**Durum:** Disposable ledger/handler fixture tamamlandı; hedefli testler geçti.
**Tarih:** 2026-10-23
**Sınır:** Panel servisi başlatılmadı; gerçek `YUVA_DIR` veya görev tahtası
değiştirilmedi. Testler yalnız geçici data root ve sentetik worker/task kayıtları
kullanır.

## Kanıtlanan akış

`tests/test_task_board_live_update_consistency_fixture.py` gerçek panel
`gorev_calistir()` handler'ını, canonical `bin/yuva` task operation'larını ve
`panel.veri()` snapshot projeksiyonunu aynı geçici `YUVA_DIR` altında kullanır.
UI kaynak sözleşmesi için aktif status sütunları ve assignee görünümünün status
filtreleri de fixture tarafından denetlenir.

Fixture şu dalları kapsar:

1. Panel handler üzerinden assignment sonrası snapshot'ta `assigned`/assignee
   çifti, diğer task'ların `pending` ve `pending_revision` sınıflarıyla tutarlı
   görünür.
2. Önceden atanmış işi yeniden `al` denemesi reddedilir; snapshot'taki durum ve
   assignee değişmez.
3. Yetkili assignee'nin teslimi ledger ve snapshot'ta `pending_verification`
   olarak görünür, assignee korunur ve assignment/teslim geçişleri için iki
   history olayı bulunur.
4. Aynı task'a panel ve canonical CLI üzerinden eşzamanlı iki `al` çağrısında
   yalnız biri kazanır; ledger ve panel snapshot aynı tek assignee/history
   sonucunu gösterir.
5. Yanlış assignee'nin claim denemesi reddedilir; ledger bytes ve mesaj dosyası
   değişmez.

Çalıştırma:

```sh
python3 -m unittest tests.test_task_board_live_update_consistency_fixture -v
```

## Sınır

Bu, panel handler ve snapshot fonksiyonlarının same-process fixture kapsamıdır;
canlı HTTP server, browser DOM/JavaScript runtime veya gerçek eşzamanlı
deployment testi değildir. Concurrent panel/CLI claim, temp root'ta iki
çağıranın ortak `.kilit` yolundan geçtiğini sınar. Sonuç genel olarak her
release kopyasının canonical writer olduğu veya canlı UI polling'in uçtan uca
doğrulandığı anlamına gelmez.
