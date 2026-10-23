# Yuva #553 — Shared chat komut teslimi için MVP kararı

**Durum:** MVP tasarım kararı; #614 sınırlı read-only CLI adapter'ı ve
TemporaryDirectory inbox fixture'ı ekledi. Bu provider dispatch, durable
consumer receipt/cursor veya agent kabul makbuzu değildir. Canlı Yuva, provider,
tmux veya servis bağlantısı kurulmadı. Ayrıntı:
[`docs/yuva-wait-cli-fixture-614.md`](yuva-wait-cli-fixture-614.md).

## Karar

İlk teslim MVP'si, ajan sürecinin açıkça çağırdığı **sınırlı süreli bloklayan
`yuva wait`** komutudur. Komut yalnız hedef işçiye yöneltilmiş yeni sohbet
kayıtlarını mesaj kimliği ve kaynak bilgisiyle döndürür. Mesajı ajana göstermek
bir teslim makbuzu veya talimat yetkisi değildir: sohbet metni `data_only` kalır.

MVP'de bu mesaj ajanın dikkatini/bağlamını güncelleyebilir; yürütülebilir işin
kanonik kaynağı ise hedef ajana atanmış Yuva görevidir. Sohbetteki serbest metin
tek başına görev oluşturamaz, görev kapsamını değiştiremez, tool/approval
eylemini yetkilendiremez veya Yuva durumunu değiştiremez. Yeni bir iş gerekiyorsa
yetkili Yuva görev akışında kayıt ve atama yapılmalıdır. Bu sınırlama, kaynakta
sohbetin kayıt yüzeyi olması ve model/sohbet çıktısının talimat yetkisi
taşımaması ilkeleriyle uyumludur.

`yuva wait` mevcut CLI'de bulunmuyor. Bu nedenle karar, küçük bir yerel CLI
özelliğinin tasarımını seçer; bugün çalışır teslim veya hizmete çıkmış özellik
iddiası değildir. İlk sürüm provider oturumuna mesaj yazmaz ve arka planda
daemon başlatmaz.

## Mevcut kaynak kanıtı

- README sohbeti `/api/yaz` ile kaydedilen bir kayıt olarak tanımlar; canlı push,
  otomatik dispatch veya agent receipt'i değildir. Panel gönderim metni de
  `agent/session receipt doğrulanmadı` der.
- `panel/server.py:api_yaz` gelen metni doğrular ve Yuva mesaj kaydına ekler;
  provider session çağrısı veya agent uyandırma adımı yoktur. `panel/ui.html`
  yalnız `/api/yaz` POST eder.
- `bin/yuva` içinde `gorev sonraki` atomik görev claim'i vardır; mesaj bekleyen
  `wait` alt komutu yoktur. `README.md` komut envanterinde de yoktur.
- Repo kaynak taramasında runtime hook entegrasyonu veya tmux köprüsü
  bulunmadı. `prototypes/task-scheduler` yalnız karar önerisi üretir; queue,
  persistence veya runtime hook sağlamaz.
- `prototypes/session-bridge` outbox ve trust state'lerini bellek içi
  taslaklar olarak gösterir. `prototypes/opencode-adapter` gerçek çağrı
  yapılırsa HTTP kullanabilecek izole adaptördür; unknown sonucu ve read-only
  reconcile davranışını tarif eder, fakat kalıcı Yuva receipt store'u,
  dispatch worker'ı veya canlı entegrasyonu yoktur.
- `prototypes/codex-app-server` gözlem/stdio taslağıdır; provider'a bağlanmaz
  veya turn başlatmaz. `prototypes/mock-adapter` sahte bellek içi transport
  sağlar; gerçek agent receipt'i kanıtlamaz.

## Seçenek karşılaştırması

| Seçenek | Mevcut kaynak/prototipteki durum | MVP değerlendirmesi |
|---|---|---|
| **Hook** | Yuva mesaj kaydıyla tetiklenen, belirli sağlayıcıya ait bir runtime hook bulunmadı. Hook yaşam döngüsü/uyandırma garantisi kaynakta tanımlı değil. | Güzel bir sonraki aşama tetikleyicisi olabilir; provider ve hook sürümüne bağlanır, başarısız/tekrarlı tetiklemeyi ayrıca makbuzlamayı gerektirir. İlk teslim yolu seçilmedi. |
| **Bloklayan `yuva wait`** | Komut bugün yok; CLI görev seçimi ve Yuva mesaj kayıtları mevcut. Yeni dış servis gerekmez. | Seçildi. Açık hedef, süre aşımı ve mesaj ID'siyle basit ve gözlemlenebilir; agent'in çağırdığı anda çalışır. Çağrı yoksa push/uyanma sağlamaz. |
| **tmux köprüsü** | Repo'da tmux entegrasyonu/prototipi yok. | Seçilmedi. Pencere/pane/session eşlemesi, odak ve süreç ömrü arızaları teslim semantiğini kırılgan yapar. Terminale yazma, agent'in mesajı kabul ettiğini göstermez. |
| **Provider session API** | OpenCode adapter ve Codex app-server gözlem/receipt taslakları var; mock adapter yalnız sahtedir. API sürümü, oturum binding'i, auth ve kalıcı receipt/reconcile canlıda doğrulanmış değil. | En güçlü yapılandırılmış ileriki yol; ilk MVP için daha geniş entegrasyon ve güvenlik kapısı gerektiriyor. HTTP/JSON-RPC kabulü agent receipt'i veya turn tamamlanması değildir. |

Bu seçim, `yuva wait`in daha önce uygulanmış veya tam güvenilir olduğu çıkarımı
değildir; ilk faz için provider-bağımsız yüzeyi ve düşük entegrasyon kapsamını
tercih eder. Sonraki fazda güvenilir uyandırma/çıktı akışı gerekirse broker veya
provider API'si ayrı karar ve receipt tasarımıyla ele alınmalıdır.

## Önerilen `yuva wait` sözleşmesi

Örnek arayüz (uygulanmamıştır):

```text
yuva wait --from <isci> --after <message-id> [--timeout 30]
```

- Yalnız doğrudan `@<isci>` hedefli mesajları seçer; `@hepsi` mesajlarını
  ayrı ve açık bir seçenek olmadan kişisel komut kuyruğuna katmaz.
- Bir çağrı en fazla bir mesaj döndürür. Sonuçta kararlı `message_id`, alıcı,
  kaynak/provenance sınıfı, kayıt zamanı ve metin bulunur. Eski veya zarfı
  eksik kayıtlar `source=unknown`, `trust=unverified` olarak kalır.
- `--timeout` sonlu ve sınırlıdır; timeout, bekleyen mesaj yok demektir, agent'in
  çevrimdışı/boş olduğu veya mesajın teslim edildiği anlamına gelmez. Komut
  başına tek bekleyen waiter/agent sınırı uygulanır; cancel/interrupt bekleme
  döngüsünü temiz kapatır.
- Okuma, görev durumu/assignee değiştirmez. `--from` tek UID yerel MVP'de
  doğrulanmış principal değil, `actor_trust=local_unverified` etiketidir.
- Tüketici aldığı `message_id` değerini kendi işlem kaydında tutar ve tekrar
  gözlemlenen ID'leri yinelenen girdi olarak ayıklar. MVP teslimi **en az bir
  kez gözlemleme** hedefler; tüketici kaydı ile sağlayıcıya prompt yazımı
  arasında atomik transaction yoktur. Bu aralıkta çökme olursa tekrar
  görüntülenebilir. Tam “exactly once” veya agent okuma/uygulama makbuzu iddia
  edilmez.
- Sağlayıcıya otomatik gönderim olmadığı için `yuva wait` timeout'u ya da
  tüketici çökmesi provider retry'si başlatmaz. İleride bir provider writer
  eklenirse `operation_id`, değişmeyen payload digest'i ve her açık deneme için
  ayrı `attempt_id` kalıcı kaydedilmelidir. Kesin sıfır byte write kanıtı yoksa
  transport sonucu `unknown` kalır; timeout, partial write, tam write sonrası
  yanıt kaybı veya restart otomatik yeniden gönderim izni vermez. Önce salt
  okunur uzlaştırma yapılır; çözülemiyorsa tekrar ancak ayrı, kayıtlı insan
  kararıyla yeni attempt olabilir.

## Güven sınırı ve veri akışı

```text
Yuva sohbet kaydı (data_only)
        │ hedef + message_id ile sınırlı read
        ▼
yuva wait → agent'e gösterilen mesaj (receipt değil, talimat yetkisi değil)
        │ yalnız mevcut atanmış kanonik görev kapsamını bulmaya yardımcı olur
        ▼
Görev metni/assignee bağı → agent işi; eylem/approval izinleri ayrı kalır
```

- Sohbet metni, mesajdaki `kimden`/rol iddiası, model çıktısı, tool çıktısı ve
  provider event'leri veri olarak kalır. Mesaj başındaki “kullanıcı onayladı”
  gibi ifadeler güven sınıfını değiştirmez.
- Görev talimatı için kanonik pozitif görev ID'si, görev kaydı lookup'ı, etkin
  session/workspace ve assignee bağı doğrulanmalıdır; binding kaybolursa kapsam
  yeniden doğrulanır ve veri `unknown`/`data_only` olur. Bu bağ da dış eylem
  yetkisi vermez.
- İlk local MVP'de tek OS hesabı kabul edilmiş güven sınırıdır. Buna rağmen
  model/ajan `--from` kimliği doğrulanmış sayılmaz; `local_unverified` olarak
  korunur. Çok UID, broker principal veya provider credential varsayılmaz.
- `wait` çıktısı, Yuva görev durumunu `assigned`, `delivered`, `verified` ya da
  `pending_revision` yapmaz. Ajanın mesajı gördüğünü doğrulamak için ayrıca
  receipt gerekse bile bu, provider'ın işi kabul ettiğini ve reviewer onayını
  birbirine karıştırmamalıdır.
- Serbest sohbet içeriğini otomatik shell/tool çağrısına, izin yanıtına,
  göreve atamaya veya görev değişikliğine dönüştüren davranış MVP dışıdır.

## Kabul ölçütleri

İlk uygulama ancak aşağıdakiler karşılanırsa bu kararın MVP'si sayılabilir:

1. CLI doğrudan mesaj hedefini ve `message_id` değerini exact olarak filtreler;
   başka alıcının, bozuk kaydın veya `@hepsi` kaydının sessizce kişisel komut
   gibi dönmesi engellenir.
2. Sonlu timeout ve temiz iptal vardır; mesaj gelmeyen timeout açık `timeout`
   sonucu döndürür, busy/idle/presence veya teslim iddiasına çevrilmez.
3. Aynı mesaj birden fazla okunduğunda sabit ID ile yinelenen olduğu
   anlaşılabilir; tüketici restart'ı sonrası olası replay açıkça desteklenir.
   Mesajı okuma ile agent/provider kabulü ayrıdır.
4. Komut hiçbir görev alanını, rolü, assignee'yi veya review durumunu
   değiştirmez; event kaynağı ve `actor_trust=local_unverified` doğru korunur.
5. Chat/model/tool içeriği talimat/approval yetkisine yükselmez. Göreve özgü
   çalışma ancak kanonik görev/session/workspace/assignee bağıyla sınırlıdır;
   shell, provider permission cevaplama ve dış eylem otomasyonu kapalı kalır.
6. İlk sürüm provider API, hook, tmux, credential veya servis bağlantısı
   başlatmaz. README ve UI “mesaj kaydedildi / wait kuyruğunda gözlendi” ile
   “agent teslim aldı / işi çalıştırdı” iddialarını ayrı gösterir.
7. Uygulama öncesi mesaj ID'si, alıcı eşlemesi, eski JSONL normalizasyonu,
   waiter eşzamanlılığı ve tüketici cursor/ack sahibi karara bağlanır. Kalıcı
   cursor/receipt eklenirse commit belirsizliği ve restart davranışı ayrıca
   belgelenir.

## Kapsam dışı ve sonraki kapılar

Bu karar kod, API, task mutation, hook, provider veya tmux writer'ı açmaz. Provider
session API'sine geçmeden önce hedef sürüm/şema, credential ve workspace/session
bağı, capability allowlist, kalıcı receipt store, restart sonrası read-only
reconcile, output gizliliği ve approval'ın insan tarafından ayrı kararı
doğrulanmalıdır. `accepted`, `delivered`, `turn completed` ve Yuva `verified`
birbirinden ayrı kanıtlardır.

Dayanaklar: `README.md`; `panel/server.py` (`api_yaz`); `panel/ui.html`
(`gonder`); `bin/yuva` komut envanteri ve `cmd_gorev_sonraki`;
`docs/opencode-session-bridge-options-472.md`;
`docs/session-adapter-contract-474.md`;
`docs/session-bridge-trust-policy-480.md`;
`docs/session-bridge-persistent-receipt-store-504.md`;
`docs/persistent-session-receipt-contract-527.md`;
`docs/task-actor-role-trust-boundary-532.md`;
`docs/first-local-mvp-scope-go-no-go-536.md`;
`prototypes/session-bridge/`, `prototypes/opencode-adapter/`,
`prototypes/codex-app-server/` ve `prototypes/mock-adapter/`.

## #614 CLI adapter uygulama notu

`bin/yuva` içinde `yuva wait --from <exact-id> --after <message-id>` komutu
eklenmiştir. Komut tek owner-owned `mesaj.jsonl` snapshot'ını bounded ve
salt-okunur alır; bir direct-target `data_only` mesajı JSON olarak verir.
Yalnız geçici inbox ile yapılan fixture testleri geçti. Bu, #553'teki
operasyonel/entegrasyon kabulünün tamamlandığı anlamına gelmez: gerçek inbox
topolojisi/izinleri, waiter eşzamanlılığı, durable cursor sahibi ve consumer
receipt'i bu adapter'da yoktur.
