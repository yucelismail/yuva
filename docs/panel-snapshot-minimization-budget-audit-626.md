# Panel snapshot veri minimizasyonu ile global bütçe etkileşimi denetimi (#626)

**Tarih:** 2026-10-23
**Durum:** Statik kod ve sözleşme incelemesi; üretim davranışı değiştirilmedi, test çalıştırılmadı.
**Kapsam:** #574 veri sınıfları/anonim snapshot kararı, #605 allowlist fixture'ı ve #606 global response bütçesi tasarımı arasındaki etkileşim; ayrıca #619 bütçe uygulamasına yönelik kabul noktaları.

## Karar

Veri minimizasyonu ve byte bütçesi ayrı katmanlardır. Önce okuyucu/amaç için izinli projection uygulanmalı; ardından bu projection üzerindeki tam kayıtlar için bölüm ve global byte bütçesi hesaplanmalıdır. Bütçe, yalnızca yanıt boyutunu ve seçilen tam kayıtların sayısını sınırlar. Bir kaydın hassas olup olmadığını, anonim tüketiciye verilmesinin uygunluğunu veya hassas bir alanın kaldırıldığını kanıtlamaz. Bu nedenle #574'teki anonim tam snapshot **NO-GO** kararı, #605 allowlist'i veya #606 byte bütçesi nedeniyle değişmez.

## Bulgular

### Yüksek — bütçe, hassas alanları azaltmıyor

`panel/server.py::veri()` roster kaydını seçilmiş alanlarla kurar; bu alanlardan `not_`, `katilma` ve kaynakta bulunan ek alanlar çıkmaz. Buna karşılık görev listesi `gorev_oku()` sonucundan doğrudan `gorevler` olarak döner; `mesajlar()` son JSONL kayıtlarının kopyasını normalize ederek döndürür. Ekran map'i de ayrı redaksiyon ve boyut sınırlarıyla döner. #605 testi roster allowlist'ini sınar; görev/message nesnelerinde alan projection'ı veya serbest metin minimizasyonu göstermez.

#606'daki `gorevler`, `mesajlar` ve `ekranlar` bölüm payları ile item tavanları, içeriği yalnızca sınıra sığdığı ölçüde seçer. Özellikle yakın tarihli mesajlar ve açık görevler yüksek önceliklidir; bu seçim verinin hassasiyetine göre değildir. Bir hassas mesaj bütçeye sığıyorsa yine tam metni taşır; bütçe 8 MiB altında olsa bile gizlilik kapısı değildir. #574'teki chat, ekran ve serbest görev notu riskleri için içerik/alan allowlist'i ya da bu grupları tüketici sözleşmesinden çıkaran ayrı projection gerekir.

**Öneri:** Güven/erişim kararı ve tüketici amacı belirlendikten sonra alan/grup projection'ı yapın; bütçe seçiminde yalnız bu projection'ın tam kayıtlarını kullanın. Anonim/summary tüketici ile yetkili tam panelin aynı geniş JSON şemasını paylaşması gerekiyorsa iki ayrı read model/endpoint sözleşmesi ve UI uyumu tasarlayın. #593 summary projection'ı mevcut `/api/veri`'ye bağlı değildir ve anonim GET için tek başına GO sağlamaz.

### Yüksek — policy ile bütçe kaynaklı eksiklik aynı `partial` anlamına gelmemeli

#606 `snapshot_meta.partial` ve `omitted` sayaçlarını bütçe seçiminin dışarıda bıraktığı kayıtlar için tanımlar; #593 ise projection kapsamını `omitted_sections` ve `scope=summary_only` ile belirtir. İki kavram aynı sayaçta/toplam `partial` bitinde birleştirilirse istemci, politika gereği hiç istenmeyen hassas alanları bütçe yüzünden düşmüş içerikle karıştırabilir. UI da gizlilik nedeniyle dışarı verilmeyen bir alanı “response limitine takıldı, yeniden dene” olarak gösterebilir.

**Öneri:** Şemada (a) tüketici/policy kapsamını sabit ve açık bir schema/scope ile, (b) yalnız bütçe nedeniyle seçilemeyen izinli kayıtları `partial`/`omitted` ile ayrı belirtin. `partial_reasons` sabit enum kalmalı; içerik, ID, görev adı, path veya atlanan kayıt listesi taşımamalı. Bütçe uygulanırken tipler sabit ve tam kayıt seçimi korunmalı; metin kesilmemeli. UI policy kapsamı ve bütçe partial'ını ayrı mesajlarla yorumlamalı; kısmi listelerden yokluk, çevrimdışı olma veya tamamlanma çıkarmamalıdır.

### Orta — sayaç ve kısmi nedenler de veri sızıntısı yüzeyi

#606'nin sabit enum ve ID/path/metin içermeyen metadata önerisi iyi bir veri minimizasyonu özelliğidir. Ancak `included`/`omitted` grup sayıları ve screen file sayıları iş yükü, sohbet/görev hacmi veya kullanıcı etkinliği hakkında çıkarım sağlayabilir. Bunlar içerik değil diye otomatik olarak herkese açık kabul edilemez. `omitted_sections` da tüketiciye hangi alan sınıflarının var olduğunu gösterebilir.

**Öneri:** Metadata allowlist'ini de hedef okuyucuya göre seçin. Anonymous/summary mod için kesin adetlerin gerekip gerekmediğini gerekçelendirin; gerekmezse yalnız `partial` ve sınırlı neden enum'ları veya kaba bucket kullanın. Policy nedeniyle bastırılan grubun mevcut olup olmadığını ve exact count'unu anonim response'ta açıklamayın. Yetkili UI exact sayıları kullanıyorsa bunu ayrı yetki ve response scope'u altında tutun.

### Yüksek — screen round-robin cursor'ı final global seçime bağlanmalı

#606 doğru olarak global bütçenin ekran dosyalarını düşürmesi halinde cursor'ın seçilmemiş dosyaları atlayacak şekilde ilerlememesini ister. Fakat mevcut `tum_ekranlar()` kendi screen çıktı bütçesini uyguladıktan sonra `_ekran_secim_ilerlet(cursor_before, last_considered)` çağırır ve cursor'ı `veri()` snapshot'ı dönmeden önce commit eder. Daha sonra response çapında bir global selector screen map'indeki dosya/kayıtları çıkarırsa bu dışlanan içerik `tum_ekranlar()` tarafından zaten tüketilmiş sayılmış olabilir. #619 uygulaması #606'daki gecikmiş commit sözleşmesini karşılamazsa ekranlar round-robin'de atlanabilir.

**Öneri:** Screen reader'ın cursor ilerlemesini final response seçimine kadar erteleyen candidate/commit arayüzü kullanın veya screen seçimi ve global byte seçimini tek bir bütçeli fonksiyonda birleştirin. Cursor yalnız final response'a dahil edilmesi değerlendirilmiş son dosyaya kadar commit edilmeli; bütçe nedeniyle dışlanan dosyalar sonraki çağrıda yeniden aday kalmalıdır. Aynı arayüz #459'un mevcut screen-map limiti, partial metadata ve kendi reader hatalarını korumalıdır.

## Birleşik uygulama sırası

1. Endpoint/consumer için GET erişim ve anonim/yetkili scope kararını uygula; veri minimizasyonu bunun yerine geçmez.
2. İzinli üst seviye grup ve her grup içi alan projection'ını ham içerik seri hale getirilmeden önce uygula. `gorevler` ve `mesajlar` için açık item/field sözleşmesi belirle; `ekranlar` redaksiyonunu ayrı tut.
3. Policy kapsamı metadata'sı ile bütçe kaynaklı `partial`/omitted sayaçlarını birbirinden ayır; metadata için de alan ve boyut allowlist'i uygula.
4. Tam kayıtları UTF-8 wire byte maliyetleriyle deterministik seç; önce bölüm limitlerini sonra tek global gövde limitini uygula. Hassasiyet veya UI görünürlük durumu bütçe önceliği olarak kullanılmasın.
5. Screen cursor commit'ini global seçimle atomikleştir/erteleyerek yalnız son yanıta göre ilerlet. Reader/source hatalarını partial başarı gibi göstermeden fail-closed döndür.
6. Final encode edilmiş gövde uzunluğu, `Content-Length`, section/global sayaçları ve UI partial yorumu aynı sentetik fixture'da doğrulanmalı. Policy ile gizlenmiş grupların byte sayaçlarına dahil edilmediği ve içerik olarak hiç dönmediği de sınanmalı.

## #619 için kabul maddeleri

- [ ] Aynı sentetik kaynak için tam ve minimal projection ayrı kuruluyor; hassas `not_`, görev serbest metni, chat metni ve ekran satırı minimal profile sızmıyor.
- [ ] Her iki projection kendi grup ve global byte tavanı içinde kalıyor; exact limit kabul, limit + 1 UTF-8 byte için tam kayıt omission veya sabit fail-closed davranış var.
- [ ] Policy ile çıkarılan grup/alanlar, bütçe nedeniyle atlanan kayıttan ayrı schema/metadata anlamı taşıyor; anonim response hassas grubun exact varlığını/count'unu açığa çıkarmıyor.
- [ ] `included`/`omitted` sayaçları final response'da gerçekten bulunan tam kayıtlarla eşleşiyor; ID, metin veya path metadata'ya girmiyor.
- [ ] Büyük screen dosyası final global budget'ten çıkarıldığında cursor bu dosyayı atlamıyor; sonraki çağrıda yeniden aday oluyor. Screen-local budget ve round-robin davranışı ayrıca korunuyor.
- [ ] Partial list UI'da eksiksiz liste/total, offline kullanıcı veya tamamlanmış görev sayılmıyor; listeye bağlı mutasyonlar için #606'nin güvenli UI şartı korunuyor.
- [ ] Tüm fixture yalnız geçici/sentetik state kullanıyor; GET erişim yetkisi, anonim kullanım veya canlı rollout kanıtı olarak sunulmuyor.

## Dayanak ve sınırlar

- [#574 anonim snapshot veri minimizasyonu](panel-anonymous-snapshot-data-minimization-574.md): tam anonim snapshot NO-GO; hassas grup sınıfları.
- [#593 summary-only read model](anonymous-summary-read-model-593.md): ayrı scope ve partial UI semantiği; mevcut `/api/veri`'ye bağlı değil.
- [#605 alan allowlist fixture'ı](panel-snapshot-allowlist-fixture-605.md): üst seviye/roster projection ve kaynak/screen yerel limitleri; görev/message field allowlist veya global bütçe kanıtı değil.
- [#606 global byte bütçesi sözleşmesi](panel-global-snapshot-budget-contract-606.md): 8 MiB wire bütçesi ve partial contract; henüz uygulama kanıtı değil.
- `panel/server.py::veri()`, `mesajlar()` ve `tum_ekranlar()`: mevcut projection, message normalization ve screen cursor commit sınırları.
- [#455 GET snapshot erişim kararı](local-api-get-snapshot-decision-455.md): veri azaltımının erişim/yetki sınırının yerine geçmediği.

İnceleme statiktir. Fixture veya canlı endpoint çağrısı yapılmadı; anonim GET/POST politikası, panel UI, veri/servis veya snapshot implementasyonu değiştirilmedi.
