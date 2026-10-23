# `yuva wait` kalıcı cursor ve gözlem makbuzu fixture prototipi (#587)

**Tarih:** 2026-10-23
**Durum:** İzole store prototipi ve hedefli fixture testleri tamamlandı; denetime teslim ediliyor.
**Sınır:** CLI, panel, gerçek inbox, `YUVA_DIR`, provider ve servis kullanılmadı. Yalnız işaretli geçici dizin ve sentetik mesajlar kullanıldı.

## Prototip sözleşmesi

`prototypes/yuva-wait/receipt_store.py` #554'ün info-mode `UntrustedEnvelope` çıktısını kabul eder ve private, temp-only fixture içindeki `receipts.jsonl` append-only dosyasına gözlem kaydı yazar. Her kayıt sabit `consumer_id`, `message_id`, önceki cursor, `read_observed` türü ve şu güven alanlarını taşır:

- `source_class_claim` yalnız `operator` / `agent` / `unknown` değerlerinden biri olabilir;
- `source_class_trust=unverified`, `source_trust=unverified`, `content_class=data_only` store tarafından sabitlenir;
- mesaj metni ve serbest kaynak alanları saklanmaz.

Her consumer'ın cursor'ı kendi makbuz zincirinden türetilir. İki consumer aynı mesaj ID'sini bağımsız gözleyebilir. Aynı consumer için tekrar eden message ID ikinci kez append edilmez. Her yeni kayıt `expected_cursor` ile compare edilir; caller'ın cursor'ı store'daki son değerle uyuşmazsa `cursor_unavailable` döner ve yazım olmaz. Store, JSONL kuyruğu bozuk/yarım, şeması geçersiz, boyutu sınır üstü veya private dosya koşulları bozuksa `store_corrupt` döndürür; ham dosyayı düzeltmez, truncate etmez veya üzerine yazmaz. Append/fsync belirsizliğinde `commit_unknown` döner; otomatik retry yoktur. Store kapasitesi dolarsa `store_full` ile yazım durur.

Fixture root temp dizinin altında olmalı; private marker, root ve owner-only store gereklidir. Süreçler arası append/read işlemleri fixture lock dosyasıyla sıralanır. Bu çalışma store kaybına karşı harici anti-rollback anchor sağlamaz: daha önceki store ve caller cursor'ı birlikte kaybolursa geçmiş tüketici durumunu yerel dosyadan yeniden kanıtlamak mümkün değildir. Kurumsal kullanım öncesi ayrı store custody/backup/recovery kararı gerekir.

## Receipt'in anlamı

`read_observed`, yalnız bu prototipin belirtilen `data_only` zarfını alıp receipt kaydını kalıcılaştırdığını ifade eder. Agent'ın metni gerçekten gördüğünü, okuduğunu, anladığını, kabul ettiğini veya eyleme geçtiğini kanıtlamaz. Görev, dispatch, approval ya da provider teslim durumu üretmez. Sohbet gövdesi receipt store'a hiçbir zaman yazılmaz.

## Fixture kanıtı

`tests/test_yuva_wait_receipt_store.py` sentetik `wait.py` envelope'larıyla dört senaryoyu sınar:

1. Store nesnesi yeniden kurulduğunda cursor aynı kalır; aynı consumer/message replay'i duplicate olarak tanınır ve ikinci event yazılmaz.
2. Caller cursor'ını kaybedip `None` ile sürdürmeye çalışırsa store farklı cursor gösterir ve fail-closed döner. İki consumer aynı message ID'yi ayrı cursor zincirlerinde kaydedebilir.
3. Kısmi/bozuk JSONL tail hem cursor okumasını hem yeni yazımı durdurur; bozuk baytlar değişmeden kalır.
4. `verified`/`data_only` dışı zarf makbuza dönüşmez. `operator` sınıf iddiası saklansa bile trust alanları doğrulanmamış kalır; receipt'te metin yoktur.

Çalıştırma: `python3 -m unittest tests.test_yuva_wait_receipt_store -v` — **4 test geçti**.

## Sınırlar

Bu append-only fixture store'u #554 `wait_for_message()` fonksiyonuna, inbox'a veya agent runtime'a bağlamaz. Mesajın `wait` cursor'ından sonra geldiğini doğrulama görevi caller/reader sözleşmesinde kalır. Receipt ID'leri sınırlı ASCII biçimle tutulur. Store bozulmasında kurtarma/repair, silme/retention, harici yedek/anchor, işletimsel anahtar/custody ve üretim crash dayanıklılığı bu prototipin kabul ettiği garantiler değildir. `read_observed` bir agent read/acceptance receipt'i olarak sunulmamalıdır.

İlgili temel sözleşme: `docs/yuva-wait-prototype-554.md` ve `prototypes/yuva-wait/README.md`.
