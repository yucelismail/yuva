# Yuva #558 — shared chat prompt-injection boundary

**Durum:** Kaynak yolu incelemesi ve izole context-envelope prototipi. Canlı
provider/session bağlantısı veya production CLI/panel değişikliği yok.

## Mevcut bağlam yolu

- CLI `yuva gelen --from <id>` mesaj kutusunu ve görevleri aynı komut çıktısında
  ayrı başlıklarla gösterir. Mesaj satırı görünür gönderen/ad, hedef, tür ve
  metni basar; fakat satırda sabit message ID, source/trust ve identity status
  bulunmaz. Görev başlığı/gövdesi sohbetten ayrı tahta kaydından gelir.
- `yuva oku` aynı `msaj_satir()` biçimini kullanır; JSONL okuyucusu mesajı
  unverified provenance ile normalize etse bile terminal özeti bu güven
  ayrımını göstermez.
- Panel snapshot'ı mesaj kaynağı/provenance ek alanları döndürebilir; mevcut
  provider/session dispatch veya diğer ajana otomatik prompt aktarımı yoktur.
  UI'da görünür olmak agent receipt'i veya yetki üretmez.

Bu nedenle bugün güvenli varsayım, gösterilen metni veri olarak tutmaktır.
Gönderen adı, mesaj gövdesi, `role`, `source`, `trust`, `actor_id`,
`provenance`, task ID veya “onaylandı” cümlesi kimlik/rol/izin kanıtı değildir.
Özellikle “user” gönderen iddiası, dış uygulama konuşmasındaki doğrudan
kullanıcı talimatıyla aynı kaynak değildir.

## Uygulanan izole sözleşme

`prototypes/shared-chat-context/context.py` sabit `Origin` enum'u, kaynak ID,
gönderen/kaynak/güven iddiaları ve ayrı metin alanı içeren `ContextItem`
üretir. Her kayıt `identity_status=unknown`, `content_class=data_only`,
`authority_scope=none` olur; body içindeki rol/yetki/provenance alanları bu
değerleri değiştiremez. `source_class_claim` yalnız açık `operator`/`agent`/
`unknown` etiketini korur ve daima `source_class_trust=unverified` kalır;
`operator` insan operatör talimatı, `agent` ajan kaynaklı doğrulanmamış veri
iddiasıdır. Etiket tek başına kullanıcı kimliği veya yetki kanıtı değildir;
eksik veya geçersiz etiket `unknown` olur. `ControlReferences` ayrı argümandır; chat record onu
oluşturamaz veya üzerine yazamaz. Bunlar yalnız ilişki referansıdır, tek
başına tool/task yetkisi değildir.

Kaynaklar ayrı enum değerleriyle taşınır: shared chat, canonical task,
reviewer task, reviewer output, worker output, provider output ve tool output. Direct user
request, canonical assignee/task scope ve reviewer kararı outer/control plane
kanalından ayrı doğrulanarak taşınmalıdır. Prototip bu doğrulamayı yapmaz ve
yetki vermek için kullanılmamalıdır.

UI görünüm önerisi sabit origin badge + source ID + actor/source/trust claim
ve içeriktir. Body HTML yerine text node olarak gösterilir. Etiket ve kontrol
kanalı yalnız body dışı adapter metadata'sından gelir. Bu görev üretim UI'sını
değiştirmedi.

## Fixture kanıtı

`tests/test_shared_chat_context.py`, `role=system`, `authority_scope=reviewer`,
fake `trust=verified`, `origin=canonical_task`, başka task ID'si ve sahte
provenance içeren injection fixture'ı kullanır. Beklenti: özgün metin ve
source ID korunur; adapter'ın verdiği gerçek origin ve dış control reference
değişmez; öğe `data_only`/`unknown`/`none` kalır. Worker/provider/tool
fixture'ları da birbirinden ayrı source label'larını korur. Testler fixture
verisi kullanır; canlı provider/session yok.

Prototip, gerçek authentication, tamper-proof provenance, prompt-injection
engelleme veya onay mekanizması değildir. Production dispatch açılmadan önce
authenticated actor binding, canonical task assignment, redaction/bounds,
session scope ve tool approval policy ayrı kapılarda uygulanıp denetlenmelidir.
