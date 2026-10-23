# `yuva wait` uçtan uca fixture (#603)

**Tarih:** 2026-10-23
**Durum:** İzole fixture ve hedefli testler tamamlandı; denetime teslim edildi.
**Sınır:** Yalnız sentetik JSONL mesajları ve işaretli `TemporaryDirectory` kullanıldı. Gerçek inbox, CLI görev verisi, panel, provider veya servis çağrılmadı.

## Kapsam

`tests/test_yuva_wait_end_to_end_fixture.py`, #554'teki `wait_for_message()` bilgi zarfını #587'deki `FixtureReceiptStore` ile aynı geçici fixture içinde birleştirir. Test okuyucusu tek bir owner-only JSONL dosyasını salt okunur açar; özel marker, dosya sahibi/türü/izinleri, boyut, UTF-8, satır sonu ve yinelenen JSON anahtarlarını doğrular. Fixture gerçek Yuva state yolunu kullanmaz.

Testler şu davranışları sınar:

1. Kaynak satırı `operator`, `verified` ve `approval=true` iddiaları taşısa da çıktı `source_trust=unverified`, `source_class_trust=unverified` ve `content_class=data_only` kalır. `read_observed` receipt gövde metnini içermez; sentetik inbox ve görev sentinel'i değişmeden kalır.
2. Snapshot içindeki yinelenen message ID `source_invalid` / `duplicate_message_id` ile reddedilir. Aynı consumer/message için replay ikinci receipt üretmez.
3. Inbox cursor'ı yoksa okuma `cursor_unavailable` döner. Store'da kayıtlı cursor kaybedilip `None` verildiğinde de receipt eklenmez ve cursor ilerlemez.

Çalıştırma: `python3 -m unittest tests.test_yuva_wait_end_to_end_fixture -v` — **3 test geçti**.

## Anlam ve sınırlar

Bu birleşik fixture, gözlem zarfı ile yerel fixture receipt'inin birbirine veri kaybetmeden bağlandığını sınar. `read_observed`, agent'ın mesajı okuduğunu/anladığını/kabul ettiğini, herhangi bir işi başlattığını veya mesajın teslim edildiğini kanıtlamaz. Görev durumu, dispatch, approval ya da provider sonucu üretmez. Fixture testi üretim entegrasyonu veya gerçek inbox davranışı için kanıt değildir.

İlgili sözleşmeler: [#554 wait prototipi](yuva-wait-prototype-554.md), [#587 receipt store](yuva-wait-persistent-receipt-587.md), [prototip README](../prototypes/yuva-wait/README.md).
