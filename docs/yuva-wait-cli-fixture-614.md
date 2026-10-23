# `yuva wait` CLI info-mode fixture (#614)

**Tarih:** 2026-10-23
**Durum:** Read-only CLI adapter ve geçici inbox fixture'ı tamamlandı.
**Sınır:** Hedefli testler `YUVA_DIR` değerini geçici dizine yönlendirdi. Canlı inbox, panel, provider, servis, receipt store veya görev yazıcısı kullanılmadı.

## CLI sözleşmesi

```text
yuva wait --from <exact-roster-id> --after <message-id> [--timeout 30] [--poll-interval 0.25]
```

CLI worker kimliğini `durum.json` içindeki tam roster key'i ile eşleştirir; görünen ad veya fuzzy alias kabul etmez. Alıcı eşleşmesi yalnız saklanan `@<kimlik>` ve `@<görünen-ad>` değerleriyle exact yapılır. `@hepsi`, `@all` ve `@*` kişisel kuyruğa dahil edilmez. Snapshot'a göre tek çağrı en fazla bir yeni mesaj döndürür.

Çıktı bir JSON satırıdır. `status=message` olduğunda `message` yalnız wait prototipinin `UntrustedEnvelope` projection'ıdır ve `next_cursor` içerir. Her mesaj `source_trust=unverified`, `source_class_trust=unverified`, `content_class=data_only` kalır; kaynak satırındaki `trust`, `approval` ve actor iddiaları yetki üretmez.

Çıkış kodları:

- `0`: bir doğrudan mesaj gözlendi;
- `1`: sonlu timeout içinde eşleşen mesaj yok;
- `2`: cursor, kaynak, girdi veya wait seçeneği hatası;
- `130`: Ctrl-C ile iptal.

## Reader sınırı

Reader `mesaj.jsonl` dosyasını `O_NOFOLLOW` ile salt okunur açar, owner-owned normal dosya şartı arar ve tek detached snapshot'ta en çok 8 MiB, 10.000 JSONL satırı ve 64 KiB/satır işler. UTF-8, LF sonu, boş satır ve duplicate JSON key kontrolleri yapılır. Bozuk/yarım kuyrukta wait başarı veya timeout uydurmaz; `source_error` döner. Snapshot'ta `--after` yoksa `cursor_unavailable` olur; reader eski mesaj kaybolduğunda başlangıç noktası tahmin etmez.

`--timeout` 0–300 saniye, `--poll-interval` `(0, 2]` saniye aralığındadır. Reader callback'i bloklu filesystem I/O tamamlanana kadar iptal edilemez; dosya boyutu ve satır sayısı tavanları her okuma için üst sınır koyar. Bu prototip tek process için waiter lock, kalıcı cursor/receipt veya at-least-once consumer state eklemez. Tüketici `next_cursor` saklamazsa aynı ID yeniden gözlenebilir.

## Yan etki sınırı

CLI okuma işareti veya receipt yazmaz; inbox içeriğini ve task ledger'ı değiştirmez; panel/provider HTTP isteği, service/daemon veya dispatch başlatmaz. Mesaj gövdesi consumer'a data-only context olarak döner, komut veya approval olarak çalıştırılmaz. `next_cursor` gözlem cursor'ıdır; agent'ın metni okuduğunu/anladığını, provider'a teslim edildiğini veya görevin yapıldığını kanıtlamaz.

## Fixture kanıtı

`tests/test_yuva_wait_cli_fixture.py` gerçek CLI subprocess'ini her testte geçici `YUVA_DIR` ile çağırır. Fixture direct-recipient seçimini (broadcast atlanır), iddiaları untrusted/data-only projection'a indirmeyi, en fazla bir mesaj döndürmeyi, timeout ile kayıp cursor'ı ayırmayı, `--from` için exact roster key şartını ve inbox üst byte limitini sınar. Inbox, durum ve görev sentinel byte'ları çağrı öncesi/sonrası eşit kalır; receipt dosyası oluşmaz.

İlk #614 tesliminde CLI suite'inin **4 testi** geçti. #623 aynı test modülüne
CLI replay + duplicate-suppressed receipt senaryosunu ekledi; güncel suite'te
5 test geçer. Ayrıntı: [#623 fixture notu](yuva-wait-duplicate-observation-receipt-623.md).

Bu fixture gerçek kurulumdaki inbox izinlerini veya performansını doğrulamaz; gerçek data root bu testte açılmaz. Kalıcı cursor, tek bekleyen waiter politikası ve provider entegrasyonu ayrı kararlardır. İlgili temel davranışlar: [#554 wait prototipi](yuva-wait-prototype-554.md), [#587 receipt fixture](yuva-wait-persistent-receipt-587.md), [#603 birleşik fixture](yuva-wait-end-to-end-fixture-603.md), [#553 teslim kararı](chat-command-delivery-mvp-553.md).
