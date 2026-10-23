# Yuva receipt ledger: kalıcılık ve uzlaştırma tasarımı

Bu belge #408 için tasarım notudur. Çalışan ledger, üretim bağlantısı, Yuva
importu veya app-server runtime'ı eklemez. Amaç, Codex app-server'dan gözlenen
kanıt ile Yuva'nın görev yaşam döngüsünü birbirine karıştırmadan saklamak ve
çökme/kopma sonrası belirsizliği güvenli biçimde görünür tutmaktır.

## Güven sınırı ve iddia

Ledger, bir işlemin hangi Yuva mesajından doğduğunu, hangi task/run/attempt'e
bağlandığını ve Codex protokolünde hangi yanıt/olayların gözlendiğini kalıcı
olarak kaydeder. Ledger satırı tek başına işin başarıyla teslim edildiğini,
Yuva tarafından doğrulandığını veya Codex'in işlemi tam bir kez yürüttüğünü
kanıtlamaz. Yuva `verified` kararı yalnızca Yuva denetim akışından gelir.

JSON-RPC `id` yalnızca istek/yanıt eşleştirme kimliğidir; uzak idempotency anahtarı
değildir. Bir yazım başladıktan sonra bağlantı veya süreç kaybolursa işlem
`unknown` olur. Otomatik tekrar gönderim yapılmaz. İnsan/üst seviye orkestratör
uzlaştırmadan sonra devam kararı verebilir; bu karar ve kanıtı da ayrıca
kaydedilmelidir.

## Asgari kalıcı model

Uygulama bir SQLite veritabanında dört tablo kullanabilir. `operations` yerel
mantıksal isteğin tekil kaydıdır; `observations` append-only protokol ve Yuva
makbuz gözlemleridir; `connection_generations` JSON-RPC ID alanını bağlantı
nesline böler; `artifacts` değişmez içerik digest'ini işlemin kanıtına bağlar.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE connection_generations (
    generation_id       TEXT PRIMARY KEY,
    process_instance_id TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    ended_at            TEXT,
    end_reason          TEXT
);

CREATE TABLE operations (
    operation_id       TEXT PRIMARY KEY, -- Yuva message ID'nin kanonik metni
    task_id            TEXT NOT NULL,
    run_id             TEXT NOT NULL,
    attempt_id         TEXT NOT NULL,
    method             TEXT NOT NULL,
    params_sha256      TEXT NOT NULL,
    request_id_json    TEXT,              -- JSON türünü korur: 7 != "7"
    generation_id      TEXT REFERENCES connection_generations(generation_id),
    thread_id          TEXT,
    turn_id            TEXT,
    state              TEXT NOT NULL CHECK (state IN (
                           'prepared', 'write_started', 'unknown', 'accepted',
                           'running', 'completed', 'failed', 'cancelled'
                       )),
    last_known_state   TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (task_id, run_id, attempt_id)
);

CREATE TABLE observations (
    observation_id     TEXT PRIMARY KEY,
    operation_id       TEXT REFERENCES operations(operation_id),
    generation_id      TEXT REFERENCES connection_generations(generation_id),
    source             TEXT NOT NULL CHECK (source IN (
                           'yuva', 'jsonrpc_request', 'jsonrpc_response',
                           'server_event', 'reconciliation', 'operator'
                       )),
    source_key         TEXT,
    observed_at        TEXT NOT NULL,
    method             TEXT,
    request_id_json    TEXT,
    thread_id          TEXT,
    turn_id            TEXT,
    item_id            TEXT,
    payload_sha256     TEXT NOT NULL,
    payload_json       TEXT,
    UNIQUE (source, generation_id, source_key)
);

CREATE TABLE artifacts (
    artifact_id        TEXT PRIMARY KEY,
    operation_id       TEXT NOT NULL REFERENCES operations(operation_id),
    task_id            TEXT NOT NULL,
    run_id             TEXT NOT NULL,
    attempt_id         TEXT NOT NULL,
    item_id            TEXT,
    sha256             TEXT NOT NULL,
    byte_length        INTEGER NOT NULL CHECK (byte_length >= 0),
    media_type         TEXT,
    immutable_ref      TEXT NOT NULL,
    recorded_at        TEXT NOT NULL,
    UNIQUE (operation_id, sha256, immutable_ref)
);
```

`operation_id` Yuva mesajı ID'sinin türünü ve değerini koruyan kanonik JSON
gösteriminden üretilir; aynı Yuva mesajı tekrar işlendiğinde yeni işlem açılmaz. `task_id`,
`run_id` ve `attempt_id` ayrı tutulur: aynı task için yeni run veya aynı run
içinde yeni attempt farklı kimlikler taşır. Uygulama mevcut Yuva kimliklerini
başka anlama gelecek şekilde yeniden üretmemelidir. `params_sha256` kanonik,
gizlilik politikasıyla filtrelenmiş istek parametrelerinin digest'idir; gizli
değerler `payload_json` içine kopyalanmamalıdır.

`request_id_json` JSON kodlu tutulur; böylece sayısal ve metinsel JSON-RPC ID'ler
karışmaz. Tek başına request ID üzerinde global unique constraint yoktur:
ID'ler bağlantı nesli içinde eşleştirilir ve başka nesilde tekrar kullanılabilir.
Aktif/çözülmemiş eski bir istekle aynı ID yeniden görülürse yeni gönderim
hazırlanmaz; işlem `unknown` kalır ve uzlaştırma gerekir.

## Yazım, olay ve replay akışı

1. Gelen Yuva mesajı `observations`'a eklenir ve aynı transaction'da
   `operations` satırı `prepared` durumunda oluşturulur. Bu transaction yalnızca
   Yuva mesaj deposu ile ledger aynı SQLite transaction sınırını paylaşıyorsa
   ikisini birlikte kapsayabilir. Ayrı depolarda dağıtık atomiklik varsayılmaz;
   mesaj en az bir kez ingest edilir ve kararlı Yuva message ID'siyle
   idempotentleştirilir. `(task_id, run_id,
   attempt_id)` veya `operation_id` çakışması varsa mevcut işlem okunur; farklı
   parametre digest'i aynı kimlik altında kabul edilmez.
2. İstek sokete verilmeden hemen önce `write_started` ve bağlantı nesli, request
   ID, thread/turn bağları tek transaction'da kalıcılaştırılır. Ardından yazım
   denenir. Kesin sıfır byte yazıldığı kanıtlanırsa yalnız o attempt'in
   gönderilmediği kaydedilebilir. Kısmi yazım, flush hatası, süreç çökmesi veya
   yanıt kaybı `unknown` üretir; tekrar gönderilmez.
3. Yanıt yalnızca `(generation_id, JSON-typed request_id)` ile eşleştirilir.
   Başarılı `turn/start` yanıtındaki `thread.id` ve `turn.id`, gözlem satırıyla
   aynı transaction'da saklanır. İlgisiz bağlantıdan veya eşleşmeyen ID'den gelen
   yanıt var olan işlemi çözmez.
4. `turn/started`, item güncellemeleri ve terminal turn olayları önce
   `observations`'a eklenir, sonra aynı transaction'da görünür durum izdüşümü
   güncellenir. Tek bir event'in tekrar uygulanması ikinci bir task/run/attempt
   yaratmaz. Ham gözlem ile türetilmiş durum ayrı kavramlardır.
5. Bağlantı kapanışı veya process restart sırasında `write_started`, `accepted`
   ya da `running` olup terminal kanıtı bulunmayan işlem `unknown` yapılır;
   önceki değer `last_known_state` olarak saklanır. `completed` veya `failed`
   ancak korele edilmiş protokol terminal olayıyla gözlenmiş durumdur.

`source_key`, kaynakta gerçekten kararlı ve tekil bir olay kimliği varsa
deduplikasyon için kullanılır. JSON-RPC her notification için kararlı event ID
sağlamıyorsa yeni gözlemin `observation_id` değeri kullanılır; payload hash'i
tek başına global unique yapılmaz. Aynı payload iki meşru olay olabilir, replay
değişmiş alanlarla gelebilir. Güçlü kimlik yoksa iki gözlemi sessizce birleştirmek
yerine ikisini saklamak ve durum izdüşümünü idempotent güncellemek güvenlidir.
Yerel yakalama dosyasının tekrar ingest edilmesi gerekiyorsa ingest kaynağı ve
dosya konumu/hash'i ayrı bir `source_key` üretmek için kullanılabilir; bu
anahtar gerçek uzak olay kimliği sayılmaz.

## Kopma sonrası uzlaştırma

Uzlaştırıcı önce ledger'daki belirsiz işlemleri listeler; yeni `turn/start`
göndermez. Desteklenen protokol sorguları varsa aynı `thread_id`/`turn_id` ile
sunucu durumu sorgulanır veya thread resume edilir ve dönen kanıt yeni
`reconciliation` gözlemleri olarak kaydedilir. Protokol gerekli sorgu/kimliği
sağlamıyorsa otomatik sonuç çıkarılmaz; durum `unknown` kalır ve operatör kararı
bekler.

Bir `turn_id` bulunması kabul/çalışma ilişkisini güçlendirir fakat tek başına
tamamlanmayı kanıtlamaz. Tamamlanma için korele edilmiş terminal olay gerekir.
Olay sırası geriye dönük gelirse gözlem korunur, ama terminal kanıtı olmayan
işlem tamamlandı yapılmaz. Çelişkili iki terminal gözlem varsa ikisi de append-
only kaydedilir, izdüşüm `unknown`/inceleme gerektirir; son gelen kazanır
kuralı uygulanmaz.

Uzlaştırma kararı bir `operator` gözleminde karar sahibi, zaman, gerekçe ve
kullanılan kanıt digest'leriyle tutulur. Karar yeni bir attempt açıyorsa yeni
`attempt_id` kullanılır; eski attempt'in request ID'si veya operation kaydı
yeniden yazılmaz. Böylece tekrar deneme, yeni ve açık bir iş olarak izlenir.

## Artifact digest bağı

İçerik immutable/content-addressed bir konumda saklanır; ledger artifact satırı
`operation_id`, task/run/attempt, ilgili `item_id`, SHA-256 ve byte uzunluğunu
bağlar. Digest, kaydedilecek tam byte dizisi üzerinden hesaplanır ve sonradan
okumada yeniden doğrulanır. Dosya içeriğiyle SQLite transaction atomik olmadığı
için önerilen sıra: geçici dosyaya yaz, flush/fsync et, digest hesapla, immutable
adla atomik rename yap, ardından DB transaction'ında artifact referansını ve
gözlemi kaydet. DB commit başarısız kalırsa sahipsiz içerik silinmeden önce
ledger referansı için taranır; referanssız içerik temizliği ayrı, güvenli bakım
işidir. DB satırı tek başına dosyanın mevcut veya güvenilir olduğunu kanıtlamaz.

## Kalıcılık ve işletim şartları

- Tek yerel SQLite DB, `foreign_keys=ON`, WAL ve `synchronous=FULL` ile açılır;
  transaction sınırları yukarıdaki state + observation çiftlerini birlikte
  yazar. WAL ve DB dosyaları yedeklenirken aynı tutarlı snapshot alınır.
- DB ve artifact kökü yalnız güvenilen kullanıcı tarafından yazılabilir olmalı;
  DB, WAL, SHM, geçici artifact ve nihai artifact dosyaları için izinler
  kısıtlanmalıdır. Path'ler repository veya geçici çalışma dizini altında
  varsayılmamalı; işletim sistemi dizin izinleri ve disk doluluğu hataları
  fail-closed ele alınmalıdır.
- Unique constraint/foreign key hatası, disk doluluğu, bozuk DB, lock timeout,
  fsync/rename hatası veya migration belirsizliği gönderim/teslim başarı sayılmaz.
  Ledger yazılamıyorsa yeni dış yan etki başlatılmaz; sonuç bilinmiyorsa
  `unknown` korunur.
- Schema migration sürümü ayrıca tutulmalı; migration tek transaction'da,
  önceden yedek ve geri dönüş planıyla yürütülmelidir. Bu taslak migration veya
  dosya sistemi kodu sağlamaz.
- Hassas prompt/çıktı varsayılan olarak saklanmaz. Gerekirse erişim, saklama ve
  silme politikası ayrı belirlenir; payload digest'i de hassas içeriğe dair
  eşleştirilebilir bilgi sızdırabileceği için loglara gelişigüzel yazılmaz.

## Kabul sınırı

Bu tasarımın ilerideki uygulaması için temel kabul ölçütleri: aynı Yuva mesajı
ikinci operation yaratmamalı; her request yanıtı tam bağlantı nesline göre
eşleşmeli; belirsiz yazım tekrar gönderime dönüşmemeli; restart belirsiz işleri
`unknown` yapmalı; olay yinelenmesi yeni run/attempt üretmemeli; çelişki
örtülmemeli; artifact digest ve task/run/attempt bağı doğrulanabilmeli; Yuva
reviewer doğrulaması receipt ledger'dan türetilmemelidir. Bu belge bu ölçütleri
uygulayıp test etmez.
