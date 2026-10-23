# Yuva #593 — Anonim summary-only snapshot read modeli

## Amaç ve karar sınırı

`#574` seçeneği B için ayrı, opt-in bir summary projection fixture'ı hazırlandı. Projection'ın allowlist'i roster için yalnız kanonik Yuva kimliği ve health enum'u (`online`/`unknown`), görevler içinse yalnız allowlist status'larının toplam sayılarıdır. Ekran adı, rol, araç, yönetim ilişkisi, profile note, tam/ham presence alanları, heartbeat timestamp'i, task ID/title/detail/notes/history, chat metni ve ekran satırı çıkış şemasında yoktur.

Payload'ın ayrı consumer, tamlık/omitted semantiği, UI davranışı ve ürünleştirme kapıları için [#635 summary tüketici sözleşmesi](anonymous-summary-consumer-contract-635.md) esas alınır.

Projection **varsayılan kapalıdır** ve mevcut panel GET route'una, `/api/veri` yanıtına veya `panel/ui.html`'e bağlı değildir. Bu prototip mevcut anonim snapshot riskini gidermiş sayılmaz. Kimlikleri, online/unknown health durumunu ve aggregate task sayısını anonim vermek de bilgi ifşasıdır; bu veri azaltımı kimlik doğrulama, yetkilendirme, same-UID izolasyonu veya anonim yayın onayı değildir. `#574`'ün aynı UID agent'ları ve auth-off POST riskine ilişkin NO-GO kararı ayrı kapıdır.

## Projection sözleşmesi

`prototypes/anonymous-summary-read-model/project_fixture.py` yalnız `enabled=True` ile synthetic fixture'ta çalışır. `enabled` verilmezse kaynak nesneye bakmadan sabit `disabled` şekli döner. Etkin model:

- Kök şema: `anonymous-summary/v1`, `scope=summary_only`, `omitted_sections`, `state` ve `partial`.
- Roster entry: yalnız `id` ve `health`; `id` sabit karakter allowlist'ini geçer. Sağlık yalnız `online=true`, `presence_verified=true`, `presence_state=online`, timezone'lı heartbeat ve izinli freshness TTL birlikte sağlanırsa `online` olur. Diğer her değer `unknown` olur; offline sonucu veya exact timestamp dışarı verilmez.
- Görev özeti: yalnız `pending`, `assigned`, `pending_revision`, `pending_gorevli_review`, `pending_verification`, `verified`, `dropped` enum toplamlarıdır. Bilinmeyen/malformed status varsa görev sayıları tümden unavailable olur; hiçbir serbest görev alanı okunup kopyalanmaz.
- `complete_for_allowlist` yalnız kaynak `ok=true`, açık `snapshot_meta.partial=false`, roster şekli geçerli ve bütün task status'ları tanınmışsa verilir. Eksik metadata “tam” sayılmaz. Kısmi kaynakta sayı varsa yalnız görünen alt sınırdır; task counts yayımlanmaz.

Kasıtlı dışlanan gruplar response'ta sabit `omitted_sections` olarak listelenir. Bu liste içeriğin silindiği, başka endpoint'te erişilemez olduğu ya da kaynağın hiç okunmadığı anlamına gelmez; sadece bu projection nesnesinde yer almadığını belirtir.

## UI tüketimi ve eksik veri

`ui_consumer.py` mevcut büyük panel UI'sinden ayrılmış minimal view-model sözleşmesidir. `complete_for_allowlist` durumunda bile banner “Summary only” kapsamını belirtir. `partial` durumda UI roster elemanlarını varsa “en az N gösterildi; toplam bilinmiyor” olarak etiketler, task count'ları gizler ve eksik kayıttan sıfır/online değil/tamamlandı sonucu çıkarmaz. Roster kaynağı yoksa `shown_count=null` ve “Roster unavailable” gösterilir. `disabled`/`unavailable` da boş roster veya sıfır task olarak yorumlanmaz.

Bu view-model tam uygulama UI'sı değildir ve mevcut `panel/ui.html` ile veri şekli uyumlu gösterilmez. Mevcut UI `gorevler`, `mesajlar`, `ekranlar` ve kişi adı/rol ilişkilerini kullanır; yalnız summary payload'ı ile çalıştırılmamalıdır. Ürünleştirme ayrı bir UI/endpoint sözleşmesi ve birlikte dağıtım gerektirir. Eski veya harici consumer'lar bilmedikleri summary schema'sını tam snapshot diye kullanmamalıdır.

## Fixture kapsamı ve gözlem

`prototypes/anonymous-summary-read-model/fixture.py` tamamen bellek içi sentetik kaynak kullanır. Kaynakta özel alanlara yerleştirilen `PRIVATE_FIXTURE_*` işaretçileri summary ve UI view-model çıktılarında aranır. Fixture şu durumları kapsar:

| Durum | Beklenen tüketim |
|---|---|
| Default-off | Kaynak okunmadan `disabled`; roster/task verisi gösterilmez. |
| Tam allowlist kaynağı | Yalnız kimlik+health ve status count; UI summary-only banner gösterir. |
| Kaynak metadata'sı `partial=true` | Partial banner; görünen roster alt sınır olarak etiketlenir; task sayısı yoktur. |
| Roster alanı eksik | “Roster unavailable”; sıfır üye çıkarımı yoktur. |
| Presence prerequisite'ları | `online=false`, doğrulanmamış/non-online state, heartbeat eksik/bozuk/naive/stale/future her biri `unknown`; TTL geçersiz tip/aralıkta unknown, 1 ve 300 sınırları dahil. Hiçbiri offline üretmez. |
| Roster/task bozuklukları | Bozuk/eksik roster, geçersiz ID ve member tipi partial/unavailable; geçerli girişlerle karışık bozuk ID alt sınır etiketi verir. Eksik/non-list task source ve bilinmeyen status task count üretmez. |
| Eksik metadata ve consumer transport | Eksik/yanlış metadata partial; null/error transport ve yanlış schema unavailable; boş/tam veya full snapshot fallback'i yok. |
| UI yetki alanı | View-model yalnız `state`, banner, roster etiketi/verisi ve task counts taşır; mutation/action alanı üretmez. |
| Herhangi bir output | Task/chat/screen/profile free-text sentinel alanları yoktur. |

Fixture komutu:

```sh
python3 prototypes/anonymous-summary-read-model/fixture.py
```

## Güvenlik ve işletim sınırları

- Bu projection henüz server dispatch'inden önce çalışmıyor. Mevcut `veri()` tam birleşik snapshot'ı yüklemeye devam eder; bu nedenle prototip process memory/source read exposure'ını azaltmaz ve canlı `/api/veri` cevabını değiştirmez.
- Gerçek anonime açma kararı öncesi roster ID ve aggregate task count'un amaçlanan okuyucu için gerçekten gerekli olduğu kabul edilmelidir. Anonim cevapla mutasyon yetkisi oluşmaz; `/api/gorev`, mesaj, rol ve diğer write route'ları ayrı erişim kontrolü ister.
- Ürünleştirilirse projection kaynak/serialization sınırında, hassas alanlar cevap nesnesine eklenmeden çalışmalı; exact route/alias politikası, response bütçesi, auth/CSRF ve cache başlıkları ayrıca kabul edilmelidir.
- `snapshot_meta.partial` bilgisi kaynakta eksik veya güvenilmezse UI tamlık iddiası yapamaz. Read-model'in kendi allowlist bütünlüğü, tam source snapshot/transactional consistency ile aynı şey değildir.

## Kaynaklar

- `docs/panel-anonymous-snapshot-data-minimization-574.md` — seçenek B, hassas alan sınıfları ve anonim full snapshot için NO-GO.
- `panel/server.py:veri()` ve `panel/ui.html` — mevcut birleşik snapshot ve full-data consumer; bu görevde değiştirilmedi.
- `prototypes/anonymous-summary-read-model/project_fixture.py`, `ui_consumer.py`, `fixture.py` — default-off projection, UI view model ve sentetik fixture.

Canlı route, gerçek snapshot/veri, servis veya panel UI değiştirilmedi. Fixture yalnız sentetik in-memory nesnelerle çalışır ve üretim anonimliğine karar vermez.
