# Anonim summary projection tüketici sözleşmesi (#635)

**Durum:** Tasarım ve fixture kabul sözleşmesi. Endpoint açılmaz; canlı snapshot, UI, auth ayarı ve release kararı değiştirilmez.

## Karar sınırı ve tüketici

Bu sözleşme, #593'teki `anonymous-summary/v1` allowlist projection'ını ayrı bir summary-only tüketiciye bağlar. Tam snapshot (`/api/veri`, `/veri`) sözleşmesi veya mevcut panel UI'sı değildir. Summary payload'ı tam snapshot yerine kullanılamaz; tam snapshot alanları, endpoint alias'ları veya handler davranışıyla birleştirilemez. Summary route'u, anonim erişim veya cache politikası bu belgeyle etkinleştirilmiş sayılmaz.

#617'nin başlangıç kararı ve eksik host kanıtı **NO-GO**'dur. Roster kimliği, online/unknown health ve görev toplamları da bilgi açığa çıkarabilir. Summary-only veri azaltımı browser session/CSRF, aynı UID izolasyonu, POST yetkisi, reverse-proxy bypass kontrolü veya operatör/veri sahibi onayının yerine geçmez. Bir ürün summary'yi anonim sunmak isterse bu ayrı bir erişim kararı ve release kabulü gerektirir; varsayılan kapalı kalır.

Yetki varsayımı: bu projection mutation yetkisi veya doğrulanmış actor sağlamaz. Summary tüketicisi salt okunurdur ve yalnız bu belgede izin verilen alanları işler. `id` değerinin yayınlanması yine de bir kimlik ifşası kararıdır; veri sahibi bu roster allowlist'ini ayrıca onaylamadan public kabul edilmez.

## Şema ve alan allowlist'i

Kök şema sabittir; tanınmayan sürüm veya bozuk kök “boş ve tam” yerine unavailable olarak ele alınır.

| Alan | İzinli şekil | Anlam |
|---|---|---|
| `schema` | Sabit `anonymous-summary/v1` | Ayrı consumer şeması; tam snapshot şeması değildir. |
| `scope` | Sabit `summary_only` | Yalnız allowlist summary kapsamı. |
| `state` | `disabled`, `unavailable`, `complete_for_allowlist`, `partial` | Projection/kanıt durumu; roster veya görev sayısı değildir. |
| `partial` | Boolean | `true`, summary tamlığı bilinmediğinde veya allowlist girdisi eksik olduğunda kullanılır. |
| `partial_reasons` | Partial projection'da sabit enum dizisi; disabled/unavailable'da bulunmayabilir | `source_completeness_unknown`, `roster_incomplete`, `task_counts_incomplete`; tekrar yok, sabit sırada. Kullanıcı metni, ID veya path içermez. |
| `omitted_sections` | Aşağıdaki sabit enum listesi | Bu payload'da bulunmayan gruplar; verinin başka yerde olmadığı iddiası değildir. |
| `roster.state` | `complete`, `partial`, `unavailable` | Roster allowlist kaynağının geçerliliği. |
| `roster.shown_count` | Non-negative integer veya `null` | Yalnız geçerli şekilde gösterilen roster giriş sayısı; belirsiz/eksik roster'da `null`, asla `0` varsayılmaz. |
| `roster.entries[]` | Yalnız `id`, `health` | İzinli Yuva kimliği ve iki değerli health enum'u. |
| `task_counts.state` | `complete`, `partial`, `unavailable` | Toplamların tam ve yorumlanabilir olup olmadığı. |
| `task_counts.counts` | Her allowlist status'u için non-negative integer map veya `null` | Yalnız eksiksiz kaynakta yayımlanır; bilinmeyen/eksik durum `null`/unavailable olur, sıfır sayılmaz. |

Roster entry alanları:

- `id`: kanonik Yuva kimliği; yalnız `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` biçimi. Ekran adı, e-posta veya başka kimlik türevi eklenmez.
- `health`: yalnız `online` veya `unknown`. `online`, kaynak `online=true`, `presence_verified=true`, `presence_state="online"` koşullarının tümü doğru; timezone içeren heartbeat yaşı `0..online_sn` aralığında; TTL `1..300` saniye aralığında olduğunda verilir. Eksik, eski, gelecekte, geçersiz veya doğrulanmamış her değer `unknown` olur. `offline` enum'u yoktur; tam zaman damgası verilmez.

Görev toplamları yalnız şu yedi status'u içerir; anahtarlar her yanıtta sabit sırada bulunur:

`pending`, `assigned`, `pending_revision`, `pending_gorevli_review`, `pending_verification`, `verified`, `dropped`.

`omitted_sections` sabit liste:

`task_text`, `task_notes`, `task_history`, `chat_content`, `screen_rows`, `profile_notes`, `display_names`, `roles`, `tools`, `relationships`, `heartbeat_timestamps`, `raw_presence_fields`.

Başka kök, roster veya task alanları şemaya eklenemez. Özellikle görev ID/title/detail/assignee/history, chat metni, ekran satırı, profil notu, role/tool, organizasyon ilişkisi, serbest hata metni, zaman damgası, raw presence alanı ve gizli source metadata'sı dışarı çıkmaz. Yeni alan veya enum yeni şema sürümü ve ayrı onay gerektirir.

## Tamlık, eksik kapsam ve sayım semantiği

`complete_for_allowlist` yalnızca kaynak `ok=true`, `snapshot_meta.partial` açıkça boolean `false`, roster nesnesi geçerli, kimlikler geçerli ve tüm görev status'ları allowlist'te ise kullanılabilir. Metadata'nın bulunmaması, yanlış tipte olması veya `partial` değerinin eksik olması **tam** sayılmaz.

- Roster geçerli ama kaynak snapshot `partial=true` veya tamlık kanıtı yoksa `roster.state=partial`; geçerli gösterilen girişler yalnız alt sınırdır. UI “en az N gösterildi; toplam bilinmiyor” der.
- Roster kaynağı yoksa veya kullanılabilir bir map değilse `roster.state=unavailable`, `shown_count=null`, `entries=[]`; UI “Roster unavailable” der. Bundan sıfır roster, herkes offline veya kullanıcı yok sonucu çıkarılmaz.
- Geçersiz/bozuk kimlik ya da member şekli roster'ı eksik yapar. Doğrulanmış girişler gösterilirse yalnız alt sınırdır; kimliği doğrulanamayan giriş atılır. Kısmi kayıtlar tam roster toplamı veya offline kanıtı değildir.
- Task kaynağı yoksa, list değilse veya tek bir status bilinmiyorsa `task_counts.state=unavailable`, `counts=null`. Görevlerin tümü “0” veya tamamlanmış sayılmaz.
- Task listesi parse edilebilir fakat source snapshot partial ise toplamlar yine yayımlanmaz; görünen kayıtların sayısı tam toplam değildir.
- Herhangi bir source/task/roster tamlık sorunu üst seviyeyi `state=partial`, `partial=true` yapar ve ilgili sabit nedeni ekler. Kaynak okunamama/bozuk JSON gibi transport ya da kalıcı hata ise partial başarı uydurulmaz; üst katman hata verir.
- `omitted_sections` yalnız bu projection'ın kapsam dışını bildirir. “Veri hiç yok”, “kaynak okunmadı”, “başka endpoint erişilemez” veya “silindi” anlamı taşımaz.

Eksik summary payload'ı transport hatası, kapalı feature veya tanınmayan schema nedeniyle gelmiyorsa tüketici bunu sıfır sayımlı başarıya çeviremez. `disabled`, `unavailable` ve `partial` birbirinden farklı UI durumlarıdır.

## UI tüketici sözleşmesi

Summary için ayrı view/model kullanılmalıdır. Mevcut tam panel UI'sına summary payload'ı verilmez; tam veri arayan bir eski consumer bu şemayı kabul etmemeli ve bilinmeyen alanları varsayımla tamamlamamalıdır.

| Projection durumu | UI davranışı |
|---|---|
| `disabled` | “Summary mode is disabled”; roster unavailable; task count yok. |
| `unavailable` veya schema/transport hatası | “Summary unavailable”; sıfır veya offline durumu gösterilmez. |
| `complete_for_allowlist` | Her zaman görünür “Summary only” banner'ı; yalnız allowlist roster ve status toplamları. Bu, tam panel/operasyonel sağlık göstergesi değildir. |
| `partial` | Kısmi summary banner'ı; roster varsa alt sınır etiketi; task toplamları gizlenir. Eksik kapsamdan sıfır/online/offline/tamamlandı/atanmadı sonucu çıkarılmaz. |

Health göstergesinde `unknown` ayrı ve nötr kalır; “offline” veya “çevrimdışı” olarak render edilmez. Roster `shown_count=null` ise sayı veya “0 kişi” gösterilmez. Task toplamları `null`/unavailable ise kartta sıfır, tamamlandı ya da toplam görev sayısı gösterilmez. Summary verisiyle görev atama, mesaj gönderme, rol/yöneticilik eylemi veya online kullanıcı hedefleme açılmaz.

## Fixture kabul matrisi

Fixture yalnız sentetik in-memory source kullanır. Hiçbir test mevcut `/api/veri` handler'ını, canlı servisi veya gerçek kullanıcı dosyalarını çağırmaz. Her vakanın beklenen sonucu projection ve ayrı UI consumer çıktısında doğrulanır.

| Vaka | Sentetik girdi | Projection beklentisi | UI beklentisi / negatif kanıt |
|---|---|---|---|
| F1 default-off | Gizli sentinel alanlı source; `enabled` verilmez | `disabled`; source değerleri okunup output'a yansıtılmaz | Disabled banner; roster unavailable, count yok; hiçbir sentinel görünmez. |
| F2 tam allowlist | `ok=true`, `snapshot_meta.partial=false`, geçerli roster ve yalnız bilinen task status'ları | `complete_for_allowlist`; roster entry key set'i tam `{id, health}`; yedi count anahtarı | “Summary only” banner; tam snapshot iddiası yok. |
| F3 eski heartbeat / online false / verify false / malformed presence | Her health koşulu ayrı ayrı bozulur | `health=unknown`; exact heartbeat output'ta yok | Hiçbir koşul “offline” sayılmaz. |
| F4 kaynak partial veya metadata eksik | `partial=true`, metadata yok/yanlış tip | Üst state partial; roster varsa yalnız alt sınır; task `counts=null` | “At least N … total unknown”; task count yok. |
| F5 roster eksik / yanlış tip / geçersiz kimlik | `kullanicilar` yok, map değil veya hatalı identity | Roster unavailable/partial; doğrulanamayan identity çıkarılır; tamlık false | Roster unavailable ya da alt sınır; `0 roster`/offline çıkarımı yok. |
| F6 task source eksik veya unknown status | `gorevler` yok/liste değil veya status allowlist dışı | Task counts unavailable ve `counts=null`; projection partial | Sıfır/toplam/tamamlandı çıkarımı yok; roster kısmi olabilir. |
| F7 omitted scope ve özel alan sentinel'ları | Profile, role, relation, task text/history, chat, screen ve heartbeat içine unique sentinel'lar | Yalnız izinli allowlist alanları; omitted listesi sabit | Projection ve UI JSON'unda hiçbir sentinel veya detail alanı yok. |
| F8 consumer ayrımı | Summary projection tam veri şekliyle birlikte verilmez; yanlış schema/transport unavailable | Tam snapshot fallback'i yok | Eski full-panel consumer summary'yi reddeder; salt-okunur summary dışında aksiyon yok. |
| F9 NO-GO korunumu | #617 host/auth/same-UID kanıtı yok | Fixture sonucu yalnız fixture evidence olarak işaretlenir | Release kararı NO-GO kalır; route, environment veya cache değişikliği yapılmaz. |

`prototypes/anonymous-summary-read-model/fixture.py` bu matristeki yalnız
fixture ortamında çalıştırılan koruma dallarını genişletir: F3 presence/TTL
sınırları, F5
bozuk ve karışık roster, F6 eksik/yanlış task source ile bilinmeyen status,
eksik veya yanlış tip metadata, F8 null/error transport ve yanlış schema.
Consumer view-model çıktısının read-only alan allowlist'i ve bütün branch
çıktılarında private sentinel yokluğu da named checks olarak doğrulanır.
Koşucunun kapsamı sentetik memory-only projection/consumer davranışıdır; F9
host/auth/route NO-GO kabulini uygulamaz veya PASS yapmaz.

## Ürünleştirme önkoşulları ve sınırlar

1. Veri sahibi kimlik + health + aggregate task count allowlist'inin hedef okuyucu için gerekli ve kabul edilebilir olduğunu onaylar.
2. Endpoint, alias, auth/anonim erişim, cache (`no-store`), response budget, rate limit ve error davranışı bu sözleşmeden ayrı olarak tasarlanıp release formunda kabul edilir.
3. Summary endpoint'i tam snapshot handler'ından önce projection uygular; hassas source alanlarını response nesnesine kopyalayıp sonra silmez. Bu belge böyle bir uygulamanın mevcut olduğunu iddia etmez.
4. Summary UI ayrı consumer olarak birlikte dağıtılır; partial/unknown semantiğini uygular ve hassas mutasyonlara bağlanmaz.
5. #617'nin tüm host/release/reader/auth/POST/data-scope kapıları bağımsız kanıtla kapanır. Summary-only fixture bu kapılardan hiçbirini PASS yapmaz ve tam anonim snapshot için NO-GO'yu gevşetmez.

## Kaynaklar

- [#593 anonymous summary read model](anonymous-summary-read-model-593.md) — fixture projection ve mevcut minimal UI consumer.
- [#574 anonim snapshot veri minimizasyonu](panel-anonymous-snapshot-data-minimization-574.md) — tam snapshot NO-GO ve summary seçeneği.
- [#617 operatör karar formu](release-operator-decision-form-617.md) — release başlangıç kararı ve zorunlu host/auth kapıları.
- `prototypes/anonymous-summary-read-model/project_fixture.py`, `ui_consumer.py`, `fixture.py` — mevcut sentetik prototip; bu belge uygulanmış endpoint veya release kabulü değildir.
