# #509 — OpenCode HTTP adapter bağımsız güvenlik incelemesi

**Kapsam:** `prototypes/opencode-adapter/adapter.py`, `reconcile.py` ve
`README.md` salt-okunur incelendi. Canlı bağlantı, test, runtime veya dosya
değişikliği yapılmadı. OpenCode şeması hedef kurulumun `/doc` çıktısıyla
doğrulanmış değildir.

## Bulgular

### Yüksek — session kimliği olmayan global status event'i hedef oturumu idle yapabilir

`reconcile.py:113-115,141-169`: `ingest()` yalnız event içinde bir session ID
bulunup bu ID hedefle **farklıysa** event'i atıyor. ID hiç yoksa `session.idle`
event'i yine kabul edilip `activity="idle"` yapılıyor; `session.status` da
payload'daki status'a göre state'i değiştiriyor. Adapter `/event` global stream'ini
okuduğu için eksik/başka kapsamlı event hedef session'a bağlanmış sayılmamalı.
Downstream bu değeri dispatch uygunluğu gibi kullanırsa yanlış oturuma iş
gönderilebilir.

**Öneri:** Session state'ini değiştiren event'lerde açıkça eşleşen session ID'yi
zorunlu tut. Alan eksik, bozuk veya sürüm şemasıyla eşleşmiyorsa event'i
`unmatched/unknown` kaydet; idle/busy kanıtı üretme. Şemaya göre ID'nin
bulunduğu tam payload yollarını `/doc` ve fixture ile sabitle.

### Yüksek — SSE EOF'taki yarım event tamamlanmış event gibi veriliyor

`adapter.py:90-105,107-113`: EOF geldiğinde `finish()` bekleyen alanları event
olarak çıkarıyor ve `read_events()` `reason="eof"` için `complete=True` döndürüyor.
Örneğin `event: session.idle` ve data satırları son boş ayraç gelmeden kesilirse
event yine reducer'a gider; eksik session ID'li böyle bir kayıt da yukarıdaki
bulguyla birleşip hedef oturumu idle gösterebilir.

SSE standardı, stream sonu boş satırdan önce gelirse bekleyen event'in
atılmasını şart koşuyor ([WHATWG HTML Standard, event stream parsing](https://html.spec.whatwg.org/multipage/server-sent-events.html#event-stream-interpretation)).

**Öneri:** Event'i yalnız boş satırla sonlandırınca dispatch et; EOF'taki pending
alanları at ve batch'i incomplete/EOF reason ile döndür. `complete=true` yalnız
akışın provider protokolüne göre tamamlandığı kanıtlanırsa kullanılsın.

### Orta — `localhost` doğrulaması DNS sonucunu loopback'e sabitlemiyor

`adapter.py:57-81,180-194,235-240`: IP literal'larında loopback kontrolü
yapılıyor; hostname için yalnız metinsel `localhost` kabul ediliyor. İstek
sırasında adres çözümü kontrol edilmiyor/pinlenmiyor. Yerel resolver/hosts
yapılandırması `localhost`'u loopback dışı adrese yönlendirirse Basic Auth
başlığı da o hedefe gönderilebilir (HTTP kullanımı da kabul ediliyor). Bu, normal
host varsayımına bağlıdır ve resolver yönetimi/connection yönlendirmesi bu
prototipte kanıtlanmıyor.

**Öneri:** Güvenlik sınırı isteniyorsa yalnız loopback IP literal'ları kabul et
veya hostname çözümlemesinin her sonucunu loopback olarak doğrulayıp gerçek
socket peer adresini de kontrol et. Basic Auth kullanılan non-TLS akışın sadece
loopback peer'e gittiğini doğrula; redirect'i reddetme davranışını koru.

### Orta — gönderim timeout'u yapılandırılmış `unknown` receipt üretmiyor

`adapter.py:187-204,206-213`: `prompt_async` çağrısı zaman aşımında
`AdapterError("...failed or timed out")` fırlatıyor. Bu sonuç bağlantı hatası,
timeout ve request'in karşı tarafa ulaştıktan sonra yanıtın kaybolması arasında
ayrım sunmuyor. POST'un işlenip işlenmediği bilinmez; metin içeren exception
çağıranı aynı prompt'u tekrar göndermeye yöneltebilir. Kod otomatik retry
yapmıyor ve README kalıcı ledger/idempotency olmadığını belirtiyor; ancak
çağıran için güvenli retry sözleşmesi API'de temsil edilmiyor.

**Öneri:** Mutation sonucu belirsiz olabilecek POST'larda exception yerine
structured `unknown` attempt receipt döndür veya tipli hata ile bu durumu açıkça
ayır. Operation/attempt kimliğini dışarıdan taşı, önce status/history ile
reconcile et; idempotency kanıtı yokken otomatik retry verme. Bu prototip canlı
Yuva dispatch'ine bağlanmamalı.

### Orta — response gövdesi debug/repr ile hassas veri sızdırabilir

`adapter.py:35-39,197-204`: `HttpResult` dataclass'ı ham ve ayrıştırılmış response
gövdesini tutuyor; varsayılan `repr()` ikisini de gösterebilir. Session history,
tool sonucu veya provider response'u secret/path/kişisel veri içerebilir.
Transport/HTTP hatalarının metni sanitize edilmiş; buna karşın başarılı
`HttpResult` nesnesini debug log'a yazmak ham içeriği sızdırabilir.

**Öneri:** Ham gövdeyi default result/repr'den çıkar veya `repr=False` yap;
gerekli içerik tüketimi redaction/boyut sınırı arkasında olsun. README'de bu
nesnenin loglanmaması gereken hassas response taşıyabileceği açık yazılsın.

### Orta — genel `version` alanı stream sequence gibi sıralanıyor

`reconcile.py:28-35,132-139`: `_event_sequence()` `sequence`, `seq` ve `version`
alanlarını aynı global monoton sayaç gibi kabul ediyor; session ve event türü
başına kapsam doğrulaması yok. `version` bir mesaj/nesne sürümü ise ya da sayaç
farklı kapsamda resetleniyorsa geçerli status event'i eski sayılıp atılabilir;
farklı event ailesinin yüksek numarası daha sonraki status'u bastırabilir.
#472, OpenCode event sıra/replay sözleşmesinin doğrulanmadığını belirtiyor.

**Öneri:** Yalnız `/doc` ile doğrulanmış, scope'u belli monoton stream cursor'ı
kullan. Böyle alan yoksa event sırasını kanıtlı sayma; çelişkili/unsequenced
status geçişlerini `unknown` bırakıp snapshot ile uzlaştır.

### Düşük/Orta — reducer history ve conflict listeleri sınırsız büyüyebilir

`reconcile.py:83-85,186-195`: `event_fingerprints` 4096 kayıtla sınırlandırılmış,
fakat `observed_message_ids` ve `conflicts` aynı biçimde sınırlanmıyor. Uzun
ömürlü reducer'a benzersiz message ID'leri veya tekrarlı çelişkili event'ler
gönderilirse bellek tüketimi zamanla büyür.

**Öneri:** Bu koleksiyonlar için açık adet/bayt bütçesi ve eviction davranışı
belirle; eviction sonrası duplicate/reconcile garantisinin zayıfladığını
`unknown` olarak görünür tut. Kullanıcı event metnini conflict listesine ekleme.

## Mevcut korumalar ve entegrasyon kapıları

- Redirect handler yönlendirmeleri reddediyor; URL userinfo/query/fragment
  reddediliyor; HTTP response ve SSE line/batch boyutları sınırlı.
- HTTP hata metni header, URL, response body veya Basic Auth değerini taşımıyor.
- Adapter permission-response, shell ve TUI kontrol metodu sunmuyor; README
  canlı bağlantı, redaction, durable ledger ve Yuva entegrasyonunun bulunmadığını
  söylüyor.
- Session ID boşluk/kontrol karakteri ve uzunluk bakımından sınırlı, path
  segmentinde URL-encode ediliyor. Buna rağmen event/reconcile sonuçlarının
  hedef session'a bağlandığı ayrıca doğrulanmalı.
- Gerçek server `/doc`, Basic Auth/TLS dağıtım kararı, session ID sözleşmesi,
  response redaction ve operation receipt/reconcile kapıları doğrulanmadan
  gerçek Yuva görevi veya approval akışına bağlanmamalı.

## Kaynaklar

- `prototypes/opencode-adapter/adapter.py:57-81,84-141,153-264`
- `prototypes/opencode-adapter/reconcile.py:19-51,74-197,200-267`
- `prototypes/opencode-adapter/README.md`
- `docs/opencode-session-bridge-options-472.md`
- SSE EOF/event delimiter davranışı: [WHATWG HTML Standard](https://html.spec.whatwg.org/multipage/server-sent-events.html#event-stream-interpretation)

Bu rapor statik incelemedir. Bulgu doğrulamak için test/runtime veya canlı
OpenCode bağlantısı çalıştırılmamıştır.
