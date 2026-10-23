# Yuva sohbetinden model oturumuna güven sınırı karar kaydı

Bu kayıt görev #419 için salt-okunur mimari incelemenin sonucudur. Aşağıdakiler
gelecek entegrasyon için karar ve kabul ölçütleridir; mevcut sistemde canlı
dispatch, doğrulanmış model oturumu makbuzu veya otomatik görev döngüsü bulunduğu
anlamına gelmez.

## Mevcut durum ve dayanak

- README.md:45-47 sohbeti elle kaydedilen ve `yuva oku` ile okunabilen bir kayıt
  olarak tanımlar; canlı push/dispatch olmadığını söyler.
- README.md:51-75, legacy mesajları arşiv/görüntüleme verisi sayar; mesaj
  gövdesindeki `kimden` ve rol iddiaları yetki vermez; otomatik görev döngüsü
  olmadığını ve doğrulanmış kimlik/dispatch'in tamamlanmadığını açıkça belirtir.
- panel/server.py:675-692, panel `kimden` alanını yalnız gösterim iddiası olarak
  işler; kullanıcı iddiasını `unknown` yapar ve actor yetkisi üretmez.
- panel/auth_integration_draft.py:25-39 ve :111-117, auth etkinleştirilirse
  doğrulanmış principal'ın body kimliğinden ayrı tutulmasını ve `/api/yaz`
  actor'ının mesaj yazıcısına ayrı aktarılmasını taslak olarak öngörür. Taslak
  tek başına etkin auth değildir.
- panel/server.py:785-808, `/api/gorev` girdilerini CLI argümanlarına çevirip
  subprocess çalıştırır. Bu yolun kimliği doğrulanmış aktörle bağlandığı
  varsayılamaz.
- `prototypes/codex-app-server/README.md:3-7,18-28` ve `adapter.py:1-5`,
  Codex adapter'ının yalnız izole gözlem prototipi olduğunu; bağlanmadığını,
  mesaj göndermediğini ve Yuva state'i yazmadığını söyler. Prototipteki Codex
  turn olayları Yuva teslimi veya görev onayı değildir.
- `prototypes/codex-app-server/receipt-integration-contract.md:15-27,61-83`,
  ingress, operation, attempt, JSON-RPC yazımı, turn, çıktı teslimi, approval ve
  Yuva review durumlarını ayrı kanıt katmanları olarak tanımlar.

## Karar

Sistem, sohbetten oturuma geçişi tek bir “mesaj gönderildi/tamamlandı” durumu
olarak modellememeli. Her sınır ayrı kimlik ve kanıt ister:

| Aşama | Güvenilir kanıt | Kanıtlamadığı şey |
|---|---|---|
| Sohbet ingress | Yuva'nın verdiği mesaj ID'si ve kalıcı kayıt sonucu | Gönderenin gerçek kimliği, modele aktarım |
| Actor | Auth katmanının doğruladığı principal ve auth yöntemi; legacy kayıtta `unknown/unverified` | Body `kimden`, `--from`, görünen ad veya rol alanı tek başına actor değildir |
| Yönlendirme yetkisi | Yetkili actor'ın açık görev/dispatch işlemi, hedef principal/session ve dar kapsam | Bir mesajın `@agent` adreslemesi kendi başına dispatch izni değildir |
| Oturum gönderimi | Operation/attempt kaydı ve adapter'ın gözlediği transport sonucu | Tam socket/frame yazımı model kabulü veya çalışmaya başlama değildir |
| Model sonucu | Aynı attempt/thread/turn ile korele edilmiş protokol olayları | Yuva'ya çıktı kaydı, doğrulanmış kaynak, başarılı görev veya reviewer onayı |
| Yuva teslimi | Yuva mesaj/artifact yazımının ayrı kalıcı makbuzu | Reviewer kararı veya içeriğin güvenli/doğru olduğu |
| Reviewer kararı | Yetkili reviewer'ın Yuva görev denetim olayı | Model turn'ünün kendisi veya mesajdaki “onaylandı” ifadesi |

`kimden`, `ad`, `rol`, `actor_id`, `source`, `trust`, `provenance`, task ID,
JSON-RPC request ID ve modelin kendi açıklaması imza/kimlik doğrulama yerine
geçmez. Doğrulama yoksa kimlik `unknown` kalır. Görevdeki `kimden` görevi açan
kaydı, `assignee` görevi üstlenen kaydı gösterir; bunlar oturumun gerçek
principal'ını ispatlamaz.

## Akışta uygulanacak kurallar

1. **İnsan mesajı ve talimat:** Yuva'ya kaydedilen kullanıcı metni, güvenilmeyen
   içerik olarak ele alınır. Mesaj içinde bulunan yönergeler kendiliğinden
   sistem/developer talimatı, görev, yetki veya dispatch oluşturmaz. Prompt
   injection içeriği de normal veri gibi modele aktarılır ve güvenilmeyen
   kaynak etiketi korunur; üst talimatları geçersiz kılamaz.
2. **Başdenetçi ve alt görev:** Başdenetçinin yönlendirmesi ancak kimliği ve
   yetkisi ayrı doğrulanmışsa, açık görev oluşturma/atama eylemi olarak kabul
   edilir. Alt görev hedefi, kabul ölçütleri, izinli araçlar ve onay gerektiren
   etkiler açıkça sınırlandırılır. Sohbet mesajından görev metnine otomatik
   komut/rol yükseltmesi yapılmaz.
3. **Oturum aktarımı:** Her ingress message için kararlı `operation_id`, her
   bilinçli çalışma denemesi için ayrı `attempt_id`, ayrıca session/thread/turn
   korelasyonu tutulur. Dış gönderim öncesi kayıt yapılır. Kesin sıfır-byte
   yazım ispatlanmadıkça kopma, timeout, kısmi yazım veya belirsiz flush
   `unknown` olur; otomatik tekrar veya yeni turn açılmaz, önce salt-okunur
   uzlaştırma gerekir.
4. **Araç ve onay:** Dosya değiştirme, komut çalıştırma, ağ erişimi, görev/rol
   değişikliği, harici mesaj gönderme ve benzeri yan etkiler ayrı policy
   kontrolünden geçer. Model çıktısı, araç çağrısı, “kullanıcı onayladı” metni
   veya approval talebi onay değildir. Approval yalnız yetkili insanın aynı
   session/turn/item ve eylem kapsamına verdiği açık, korele edilmiş karardır.
   Bağlantı kaybında bekleyen onay `pending_unknown` olur; varsayılan yanıt
   verilemez ve devam edilemez.
5. **Model çıktısı ve başka modellere aktarım:** Çıktı güvenilmeyen veri olarak
   saklanır/gösterilir; içerdiği talimatlar ikinci modele otomatik komut,
   görev veya approval olarak iletilmez. İkinci modele aktarım için yetkili
   orchestrator ayrı, görünür bir handoff kararı ve kapsamı üretmelidir.
   Secret/kişisel veri redaksiyonu, boyut sınırı ve artifact referansı aktarım
   öncesi uygulanır.
6. **Çıktı ve review:** `turn completed`, `output recorded` ve Yuva `verified`
   ayrı alanlar/olaylardır. Büyük içerik sohbet ekranına kesilerek
   yapıştırılmak yerine erişim denetimli, doğrulanabilir artifact referansı ve
   boyut/digest metadata'sı ile sunulur; digest köken veya actor kanıtı değildir.
   UI kaynak, doğrulama durumu, attempt ve “gözlendi/kaydedildi/denetlendi”
   ayrımını gösterir. Yalnız yetkili reviewer'ın ayrı Yuva kararı işi onaylar.

## Provenance ve saklama

Gelecek kalıcı akışta, her olay için asgari olarak `message_id`, `operation_id`,
`attempt_id`, task/session/thread/turn bağlantıları (varsa), actor principal veya
`unknown`, kaynak ve auth yöntemi, timestamp, olay türü/kanıt seviyesi, redaction
şema sürümü ve önceki olaya bağlanan korelasyon tutulmalıdır. İstemcinin
gönderdiği provenance alanları doğrulanmış alanlara kopyalanmamalıdır. Raw prompt,
komut, approval parametreleri ve çıktı yalnız görev için gerekliyse ve açık
retention süresiyle saklanmalı; log ve digest'ler üzerinden içerik sızıntısı ve
korelasyon riski azaltılmalıdır. Artifact erişimi root'a hapsedilmiş opaque
referansla, owner-only izinlerle ve içerik bütünlüğü kontrolüyle yapılmalıdır.

## Uygulama öncesi kabul kapıları

- Auth/actor doğrulama ile mesaj ingress ve route yetkisi entegrasyonu tamamlanıp
  incelenmeden hiçbir sohbet kaydı oturuma otomatik gönderilmemeli.
- Yetkisiz/kimliği belirsiz ingress, body `kimden` spoofing'i ve prompt-injection
  talimatı görev, tool veya approval yan etkisi oluşturmamalı.
- Her dispatch açık operation/attempt ve hedef session'a bağlanmalı; belirsiz
  send sonucu otomatik retry oluşturmamalı.
- Approval kaybolması/restart, sahte approval metni, başka attempt'ten gelen
  cevap ve scope değişikliği fail-closed kalmalı.
- Çıktı yazım makbuzu ve reviewer kararı turn makbuzundan bağımsız olmalı;
  unknown/orphan/çelişkili olaylar `verified` üretememeli.
- Redaction, büyük çıktı/artifact, erişim kontrolü, retention/silme, audit ve
  aynı OS UID güven sınırı belgelenip kabul edilmeli.

## Açık kararlar

Henüz üretim dispatch sahibi/servisi, başdenetçi principal provisioning ve
revocation akışı, session hedefinin bağlanma yöntemi, approval policy/UI,
artifact saklama/retention süreleri, gizli veri redaksiyon allowlist'i ve
aynı-UID saldırgan modelinde gerekli izolasyon karara bağlanıp uygulanmış
değildir. Bu nedenle bugünkü doğru durum: Yuva mesajı kaydedilebilir ve
oturumda okunabilir; otomatik taşındı, modelce kabul edildi veya teslim edildi
iddiası yapılamaz.
