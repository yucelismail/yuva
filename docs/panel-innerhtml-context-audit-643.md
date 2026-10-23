# Yuva #643 — Panel `innerHTML` bağlam denetimi

**Tarih:** 2026-10-23
**Kapsam:** `panel/ui.html` statik kaynak denetimi; #620 CSP envanterindeki HTML sink'leri, veri kökeni ve sink bağlamı eşleştirildi. UI, CSP ve test fixture'ları değiştirilmedi; sentinel değer kullanılmadı.

## Özet

`rg -n 'innerHTML\\s*=' panel/ui.html` taraması **26 atama** buldu. Dinamik mesaj, ekran ve görev metinlerinin çoğu `esc()` ile HTML metni/quoted attribute bağlamında kaçırılıyor; sabit enum'lar, sayılar ve stil renkleri de sınırlı kaynaktan geliyor. Statik literal hata/boş durumları veri interpolasyonu yapmıyor.

İki kaçışsız interpolation sınıfı var:

1. Kullanıcı/agent roster kaydından gelen `v.rol`, `hedefCiz()` option metnine (satır 655) ve `modelKart()` HTML'ine (satır 832) `ROL_AD[v.rol] || v.rol` olarak giriyor. Bilinmeyen rolde fallback doğrudan HTML text context'ine ulaşır. Normal `api_katil`/`api_rol` yazımları rolü enum ile kısıtlar; ancak `durum_oku()` kullanıcı nesnelerindeki alanları derinlemesine doğrulamıyor. Bu yüzden doğrudan desteklenen API üzerinden exploitability doğrulanmış değil; eski/import edilmiş/elle bozulmuş state'in UI'ya taşınması koşullu stored-XSS yoludur.
2. `ciz()` özetini `innerHTML` ile üretirken `veri.rev` değerini iki hata/normal dalında da kaçışsız ekliyor (satır 611). `veri()` bunu `durum.json` içindeki `rev` alanından doğrudan alıyor; `durum_oku()` revision türünü doğrulamıyor. Normal `durum_yaz()` revision'ı sayısal artırır, fakat yanlış türde önceden var olan snapshot read path'inde HTML olarak gösterilebilir. Bu da bozuk/import edilmiş state'e bağlı koşullu stored-XSS'tir.

`esc()` şu karakterleri `& < > " '` için entity'ye çevirir; HTML text ve quoted-attribute bağlamları için uygundur. CSS/JavaScript bağlamında genel sanitizer değildir. İncelenen değişken inline-style değerleri ya sabit renk paletinden/`rolRenk()` allowlist'inden, ya boolean seçimine bağlı iki sabit renkten, ya da statik boyut/layout literal'inden gelir.

## Sink envanteri

| Sink satırları | Üreten fonksiyon / girdi kaynağı | Kaçış ve bağlam sonucu |
|---|---|---|
| 589, 591, 593, 595, 597 | `ciz()` veri henüz yok durumu; statik markup/metin | Güvenli görünen sabit içerik; API verisi birleştirilmez. |
| 611 | `ciz()` snapshot `mesajlar.length`, `rev`, roster sayıları | Sayımlar normal biçimde sayısal; `veri.rev` kaçışsız HTML text context'inde. Koşullu/bilinmeyen persisted input; bulgu R2. |
| 660 | `hedefCiz()` kullanıcı görünen adı/kimliği, rol etiketi | Ad/kimlik `esc()` ile; bilinmeyen rol etiketi fallback'i kaçışsız. Koşullu/bilinmeyen persisted input; bulgu R1. |
| 698 | `sohbetCiz()` kullanıcı/agent mesajı, ad, kimlik, hedef, tür | Mesaj/kimlik/ad/tür `esc()` ile HTML text/attribute bağlamında. Sınıf birleştirmeleri sabit koşullardan. Güvenli görünen dinamik sink. |
| 761, 779 | `bekleyenCiz()` bağlantı-hatası ve boş durum | Sabit metin veya boş string. Güvenli görünen. |
| 790 | `bekleyenCiz()` sayı sayaçları ve hedef adları | Sayaçlar map `length`; hedef adları `esc()` ile text context'inde. Güvenli görünen. |
| 879, 884, 915 | `ekipCiz()` stale/empty/normal görünüm | Boş metin statik. Dinamik kartlar `modelKart()` üzerinden gelir; rol fallback sink'i R1 bu atamaya da taşınır. Diğer görünen ad, kimlik, araç ve attribute değerleri `esc()` kullanır. |
| 1125 | `tahtaArsivIcerikCiz()` | Durum `TAHTA_ARSIV` sabit listesinden; görünen durum etiketi map'ten; görev kartları escape eden yardımcıdan. Güvenli görünen. |
| 1145, 1165 | `tahtaCiz()` | Task başlığı, ID, actor, not/geçmiş ve form kimlikleri `esc()` kullanan task helper'larından; op/status değerleri uygulama sabit listelerinden. Güvenli görünen. |
| 1407 | `haritaDetayAc()` | Grup adları sabit ve `esc()`; görev alanları `haritaDetayGorevHtml()` içinde `esc()`. Sayılar liste uzunlukları. Güvenli görünen. |
| 1640 | `haritaLegacyListeUygula()` | Arama indeksi `esc()` ile attribute'a; task alanları `haritaGorevHtml()` ile escape edilir. Güvenli görünen. |
| 1676 | `haritaCiz()` boş/hata hali | Yalnız sabit markup/metin. Güvenli görünen. |
| 1730 | `haritaCiz()` ana görünüm | HTML, map/task yardımcılarından birleştirilir; alanların çoğu `esc()` ile korunur. `modelKart()` kaynaklı R1 görünümdeki kişi kartları için ayrıca geçerlidir. Güvenli görünen kısımlar tek başına XSS sanitizasyonu değildir. |
| 2078, 2088, 2099, 2138, 2157 | `ekranCiz()` / `modalCiz()` | `satirlarHtml()` ekran satırı, ad ve ID'yi `esc()` eder; kimlik attribute'u escape edilir; sınıf ve renkler sınırlı/sabit; boş/hata metni statiktir. Güvenli görünen. |

## Girdi güven sınırları

| Alan grubu | Kaynak | UI sink davranışı | Sınıf |
|---|---|---|---|
| Mesaj metni, mesaj adı/kimliği/hedefi/türü | Snapshot içindeki JSONL mesajları; kullanıcı ve agent mesajları | `sohbetCiz()` HTML metninde `esc()`; route/type class'ları da `esc()` | Kullanıcı/agent kontrollü, escape uygulanmış |
| Ekran satırı, ekran adı/kimliği/zaman/tür | Snapshot içindeki ekran kayıtları; agent CLI/panel screen writer | `satirlarHtml()`, option ve kart yardımcılarında `esc()`; renk allowlist'i | Agent kontrollü, escape/allowlist uygulanmış |
| Görev başlığı, aktör, atanan, review notu/geçmiş | Görev formu/CLI ve ledger snapshot'ı | Task/map helper'larında metin ve attribute için `esc()` | Kullanıcı/agent kontrollü, escape uygulanmış |
| Roster adı, kimlik, araç | Durum snapshot'ı | Görünen ad/kimlik/araç çoğunlukla `esc()`; role fallback istisna | Kullanıcı/agent kaynaklı olabilir; R1 istisnası |
| Roster `rol` | `durum.json` içindeki kullanıcı nesnesi | İki HTML sink'inde fallback raw HTML'e ekleniyor. Normal API writer enum ile kısıtlıyor; reader nested alanı doğrulamıyor. | Eski/import/bozuk state için kaynağı ve erişilebilirliği bilinmiyor; R1 |
| Snapshot `rev` | `durum.json` kök alanı, `veri()` tarafından doğrudan aktarılır | Summary HTML'ine raw ekleniyor; reader türü doğrulamıyor. Normal writer sayısal revision yazar. | Eski/import/bozuk state için kaynağı ve erişilebilirliği bilinmiyor; R2 |
| `S.hata`, online/presence etiketleri, status/op ve rol görünen adları | UI boolean'ları, sabit enum/map/allowlist | Literal veya allowlist; dinamik markup'da gerekliyse escape | Güvenli görünen sabit/kısıtlı girdiler |

## Öncelikli takip önerileri

1. **Roster role fallback'ini kapat:** UI render öncesi bilinmeyen rolleri sabit “rol belirtilmemiş” metnine indir veya HTML text oluştururken `esc(ROL_AD[v.rol] || v.rol)` kullan. UI regression fixture'ına bozuk/import edilmiş rol alanı için yalnız test sentinel'ı ekle; hedef option ve kişi kartında metin olarak görünmesini, HTML element/event attribute oluşturmamasını doğrula.
2. **Revision'ı doğrula ve text olarak çiz:** `durum_oku()`/snapshot projection içinde `rev` için tam sayı sözleşmesi uygula; özetin dynamic sayısal bölümünü DOM `textContent`/node yapısıyla üret veya en azından HTML text'e escape et. Fixture sentinel'ı ile string/object revision girişinin HTML oluşturmadığını ve bozuk state'in güvenli şekilde reddedildiğini doğrula.

Bu inceleme source-level bir eşlemedir; browser execution, CSP enforcement veya exploit fixture çalıştırılmadı. Normal API writer'ların alan kısıtları, bozuk/legacy/import edilmiş persisted state'in provenance'ını kanıtlamaz. No UI/CSP değişikliği bu görev kapsamında yapıldı.

## #653/#654 follow-up

`rolGorunen()` bilinmeyen string rolleri yalnız escape edilen text fallback'i
olarak tutar; non-string/prototype değerleri sabit metne indirir. Target option,
kişi kartı ve map görünümleri HTML'e raw rol eklemez. `durum_oku()` artık
`rev` alanını bool/float/string/object/negatif değerlerde reddeder; UI özeti de
yalnız güvenli tamsayı revision'ı gösterir, diğerlerini `?` yapıp escape eder.
Kabul fixture'ları `tests/test_panel_role_fallback_xss.py` ve
`tests/test_panel_revision_validation.py` içindedir; gerçek browser/CSP veya
host verisi üzerinde çalıştırılmaz.
