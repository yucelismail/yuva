# #563 — Görev kartında olay zaman çizelgesi

Tarih: 2026-10-23
Durum: Dar panel UI değişikliği ve sentetik snapshot fixture'ı tamamlandı;
inceleme için teslim ediliyor.

## Davranış

Tahta görev kartları mevcut `gecmis` listesinden açılır `<details>` zaman
çizelgesi gösterir. Gösterim son beş geçerli olayla sınırlıdır; seçim sondan
geriye en fazla 50 kayıt tarar. Her satırda kaydedilmiş olay, timestamp,
`kimden`, not ve mevcutsa event'te saklı `rol`/`role` ile `actor_trust`
değerleri görünür. Kullanıcı/roster kaydındaki güncel rolden geçmiş olay rolü
türetilmez. Mevcut CLI event writer'ı rol alanı yazmadığından eski ve yeni
olaylarda bu alan yoksa UI `rol kaydedilmemiş` der; actor trust yoksa da güven
değeri varsaymaz.

Kayıt listesi yok, boş veya görüntülenemeyen yapı için ayrı açık metinler var;
olay satırı uydurulmaz. Alanlar HTML escape edilir, not 320 karakterde kesilir.
Native `details/summary`, etiketli `ol/li` ve görünür klavye odağı kullanılır.
Kart yenileme anahtarı geçmişteki son 50 kaydı ve toplam adedi içerir; yeni
olay gelince görünüm yenilenir. Açık zaman çizelgeleri poll yenilemesinde açık
kalır. `tahtaArsivKartlari()` aynı kart renderer'ını kullandığından arşiv
kartlarında da timeline bulunur.

## Veri ve kapsam

Görev geçmişi snapshot içindeki mevcut `gorev.gecmis` alanından okunur. Yazma
API'si, görev şeması, actor/role kararı veya event üretimi değişmedi. Kaynakta
`gorev_olay_ekle()` `ts`, `kimden`, `olay`, `actor_trust`, `not` alanlarını
yazıyor; rolü geçmiş olayına yazmıyor. Canlı servis veya kullanıcı verisi
kullanılmadı.

## Doğrulama

`tests/test_panel_ui_workflow.py` içindeki sentetik snapshot worker claim ve
denetçi teslim olayları için role/trust etiketlerinin aynen korunması,
boş geçmişte kayıt uydurulmaması, görünüm limiti, escape, erişilebilir yapı ve
yeni event'te yenileme sözleşmesini denetler.

Çalıştırma: `python3 -m unittest tests.test_panel_ui_workflow -v` — 5 test
geçti. Bu fixture testi gerçek tarayıcı render'ı veya canlı panel doğrulaması
değildir.
