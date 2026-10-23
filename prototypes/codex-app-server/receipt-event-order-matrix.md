# Codex receipt olay sırası ve çakışma karar matrisi

Bu #410 görevi için salt okunur karar notudur. Üretim kodu, test veya Yuva
durum yazımı içermez. Matris, JSON-RPC cevabı ve Codex turn notification'ları
farklı sırada, yinelenmiş, çelişkili veya restart sonrasında eksik gözlendiğinde
receipt izdüşümünün nasıl davranacağını tanımlar.

## Receipt alanları

- `state`: `accepted`, `running`, `completed` veya `unknown`.
- `terminal_outcome`: yalnız korele edilmiş `turn/completed` içindeki geçerli
  `completed`, `failed` veya `interrupted` değeri. Receipt `completed`, Codex
  turn'ünün terminal kanıtının bulunduğunu söyler; işin başarılı olduğu anlamına
  yalnız `terminal_outcome=completed` gelir.
- Kimlik bağı: `(Yuva message ID, task_id, run_id, attempt_id)` mantıksal işlemi
  tanımlar; request cevabı ayrıca `(connection_generation, JSON-typed request_id)`
  ile eşleşir. Turn olayı `(thread_id, turn_id)` üzerinden aynı attempt'e
  bağlanmalıdır. JSON sayısı `12` ile metni `"12"` ayrı ID'lerdir.
- Gözlemler append-only tutulur. State, gözlemlerden türetilmiş izdüşümdür;
  son gelen olay önceki kanıtı silmez. Birbirini dışlayan kanıt varsa state
  `unknown` olur ve uyuşmazlık incelemeye çıkar.

## Karar matrisi

| Gözlem veya sıra | Ön koşul / korelasyon | Receipt kararı | Yapılacak işlem |
|---|---|---|---|
| `turn/start` yazımı kaydedildi, henüz yanıt/olay yok | Attempt ve bağlantı nesli biliniyor | `unknown` (son bilinen: `write_started`) | Yanıt gelmedi diye ret veya başarı çıkarma; reconnect sonrası otomatik tekrar yollama. |
| Başarılı `turn/start` response | Response ID aynı bağlantı neslinde tek bir `turn/start` request'ine ait; result geçerli `thread.id` ve `turn.id` içeriyor | `accepted` | Thread/turn ID'lerini kanıtla birlikte bağla. `turn/started` beklenebilir. |
| `turn/start` başarılı görünüyor ama ID eşleşmiyor, response başka nesilden veya aynı ID birden fazla adaya uyuyor | Tekil request bağı kurulamıyor | `unknown` | Response'u eşleşmemiş gözlem olarak sakla; başka işlemin state'ini değiştirme. |
| Başarılı response result'ı eksik/bozuk veya turn ID yok | Request ID eşleşiyor fakat turn kimliği kurulamadı | `unknown` | `accepted` verme; ham response ve doğrulama hatasını sakla. |
| Geçerli JSON-RPC error response | Request ID ve connection generation ile tekil eşleşme; hata nesnesi şemaya uygun | `unknown` | Bu matris yalnız bu dört receipt durumunu kullanır. Hata cevabını `request_rejected` kanıtı olarak sakla; protokolün açık semantiği dışarıda yoksa turn'in hiç başlamadığını varsayma. |
| `turn/started` response'tan önce gelir | Event'te thread/turn kimlikleri var ve `turn_id` tek bir bekleyen attempt'e bağlanabiliyor | `running` | Olay kabul response'undan önce gelse de kanıtı sakla; sonradan gelen aynı turn'e ait başarılı response `running`'i `accepted`'a geri düşürmez. |
| `turn/started` gelir ama turn/thread bilinmiyor veya birden çok attempt'e uyuyor | Tekil attempt korelasyonu yok | `unknown` | Event'i orphan/provisional gözlem olarak sakla; yakın zamandaki tek işlem olduğu için otomatik bağlama yapma. |
| Başarılı response önce `accepted`, sonra aynı turn için `turn/started` | Thread ve turn ID'ler uyumlu | `running` | Kanıt sırası normal; state `accepted → running`. |
| `turn/completed` önce gelir ve geçerli terminal turn/thread ID'si tek bir attempt'e bağlanır | Event, bilinen start cevabı olmadan da tekil attempt ile bağ kurabiliyor | `completed` + event'teki `terminal_outcome` | Terminal event'i sakla. Sonradan gelen uyumlu `turn/started` veya start response terminal state'i geriye döndürmez. |
| `turn/completed` gelir ancak turn/thread attempt'e bağlanamıyor | Kimlik eksik, farklı veya belirsiz | `unknown` | Orphan event olarak sakla; `completed` türetme. Sonradan güvenilir bağ oluşursa tüm kanıtı tekrar değerlendir. |
| Aynı terminal event'in tekrar gözlenmesi | Güçlü event kimliği veya aynı kaynak kaydının tekrar okunmasıyla kesin duplicate | State değişmez | Duplicate gözlemi dedupe kaydıyla ilişkilendir; yeni operation/attempt üretme. Yalnız payload eşitliğini yeterli sayma. |
| Aynı mantıksal event kimliği aynı payload ile tekrar, fakat farklı taşıma/reconnect | Event ID'nin protokol veya güvenilir capture kaynağında kararlı olduğu biliniyor | State değişmez | Birincil event bir kez izdüşürülür; tekrar gözlemi provenance olarak sayılabilir. |
| Aynı event anahtarı farklı payload ile tekrar | Aynı anahtar iki farklı içerik iddia ediyor | `unknown` | İki payload digest'ini de sakla, conflict üret; son yazanın kazanmasına izin verme. |
| Aynı turn için `turn/completed(status=completed)` ile `failed`/`interrupted` çelişkisi | Her ikisi de aynı thread/turn'e güvenle bağlı | `unknown` | Terminal outcome çakışması aç; iki kanıtı koru, otomatik başarı/başarısızlık seçme. |
| `turn/started` sonrasında farklı thread/turn ID'siyle aynı attempt'e ikinci start veya response | Attempt zaten başka turn kimliğine bağlanmış | `unknown` | Kimlik çakışması; iki bağlantıyı da kanıtla koru, otomatik yeni turn açma. |
| Bilinen terminal event'ten sonra aynı turn için geç gelen `turn/started` | Terminal kimlik bağıyla aynı | `completed` korunur | Olayı out-of-order olarak kaydet; terminal durumu geriletme. |
| Bilinen terminal event'ten sonra zıt terminal event | Aynı turn için iki farklı terminal outcome | `unknown` | Conflict incelemesi; event geliş zamanına göre seçim yapma. |
| `item/started` veya `item/completed` var, turn terminal olayı yok | Item, bilinen thread/turn'e bağlanmış olsa bile | Önceki `accepted`/`running` korunur; restart/kopma varsa `unknown` | Item olayı turn'ün tamamlandığını ispatlamaz. Item state ve ID'sini ayrı tut. |
| Bilinen turn için yalnız delta/output/diff olayı var | Event uygun turn'e bağlandı | `running` kanıtı varsa korunur; aksi halde `unknown` | İçerik üretimini terminal başarı sayma. |
| Restart/reconnect sonrası önceki nesildeki işlem `write_started`/`accepted`/`running`, devam kanıtı yok | Eski attempt terminal gözlemle kapanmamış | `unknown` | Eski request ID ile otomatik resend yok. Yeni nesildeki aynı ID eski isteğin cevabı sayılamaz. Uzlaştırma sorgusu/operatör kanıtı gerekir. |
| Reconnect sonrası eski turn için terminal event replay edildi | `thread_id`/`turn_id` ve attempt bağı yeterli; event kimliği veya capture provenance saklı | Duruma göre `completed` veya conflict ise `unknown` | Eski generation kaynaklı olduğunu sakla; replay'in kendisi yeni attempt yaratmaz. |
| Bilinmeyen method, eksik status veya bozuk event | Şema/semantik doğrulanamıyor | `unknown` (önceki state'i terminale yükseltme) | Ham digest ve doğrulama hatası sakla; yeni protokol anlamı varsayma. |
| Yuva mesajı teslim edildi ya da task `pending_verification` oldu | Yuva task receipt'i var; Codex terminal receipt'i tek başına yeterli değil | Codex state'i kendi kanıtına göre kalır | Reviewer'ın Yuva `verified` kararı otomatik yazılmaz veya Codex event'inden çıkarılmaz. |

## İzdüşüm sırası

State güncellemesi arrival-order ile değil, kanıtla desteklenen geçişlerle yapılır:

```text
unknown -- tekil başarılı turn/start response --> accepted
unknown -- tekil turn/started event ----------> running
accepted -- aynı turn için turn/started -------> running
unknown|accepted|running -- tekil terminal ----> completed + terminal_outcome
herhangi -- kimlik/terminal kanıt çelişkisi ---> unknown + conflict kaydı
terminal -- uyumlu geç event ------------------> terminal korunur
terminal -- zıt terminal ----------------------> unknown + conflict kaydı
```

`unknown` iki durumda kullanılır: yeterli kanıt henüz gelmemiştir veya kanıtlar
birbiriyle uyuşmamaktadır. Kaydedilen `unknown_reason` bu ayrımı (ör. `awaiting`,
`unmatched`, `restarted`, `conflicting_identity`, `conflicting_terminal`,
`invalid_event`) belirtmelidir. Geç gelen yeni kanıt yalnız önceki bilinmeyenliği
çözdüğü açıkça korele edilebiliyorsa state'i ilerletir. Daha önce görülen zıt
terminal kanıt silinmez; bu durumda `unknown` kalır.

## Kapsam dışı ve uygulama notu

JSON-RPC ID uzak idempotency sağlamaz; kayıp yanıt sonrası `turn/start` tekrar
gönderimi bu matrisin hiçbir dalında otomatik değildir. Event'lerde kararlı
sequence/event ID bulunmuyorsa yalnız varış sırasından gerçek üretim sırası
çıkarılamaz. Yuva reviewer durumu ayrı otoritedir. Bu matris #408'deki kalıcı
ledger tasarımına karar girdisi sağlar; event dedupe anahtarı ve bounded
retention'in ayrıntılı sözleşmesi sonraki #411 görevidir.
