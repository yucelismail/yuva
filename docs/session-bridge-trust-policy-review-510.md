# Yuva #510 — Trust policy prototipi bağımsız davranış incelemesi

## Kapsam ve sonuç

`prototypes/session-bridge/trust_policy.py` statik olarak incelendi ve ilgili `prototypes/session-bridge/README.md` ile #464 güven sınırı notuyla karşılaştırıldı. Kod, test, runtime veya canlı provider/Yuva bağlantısı çalıştırılmadı.

Prototip, açıklanan dar kapsam içinde temel ayrımı doğru yapıyor: sohbet, worker ve tool içeriği daima `data_only`; sınıflandırılmış hiçbir kaynak tek başına dış eyleme izin vermiyor; mesaj gövdesi sınıflandırmaya girdi değil. İnceleme, gelecekteki entegrasyonda yanlış kapsamla talimat yetkisi verilmesine yol açabilecek iki tasarım boşluğu buldu. Bu dosya tek başına canlı sistemde yetkilendirme kanıtı değildir; README de bunu açıkça sınırlıyor.

## Bulgular

### Orta — Talimat sağlayabilen görev sınıfı, görev kapsamını sınıflandırma sonucunda taşımıyor

`CANONICAL_TASK` dalı doğrulanmış bir görev iddiasıyla `may_supply_instruction=True` döndürüyor (`trust_policy.py:106-115`). Ancak `Classification` yalnız kaynak, genel `TASK_SCOPE` seviyesi ve booleans içeriyor; `task_id`, oturum/assignee bağı veya doğrulanmış kapsamı taşımıyor (`:43-49`). Çağıran taraf bu sonucu görev metninden ayırıp başka bir görev/oturum bağlamında kullanırsa, bu fonksiyonun verdiği genel “talimat sağlayabilir” kararı kendi başına kapsamı yeniden doğrulatamaz.

Bu durum prototipin açıkça üretim yetkilendirmesi olmadığını söylemesi nedeniyle mevcut kullanımda doğrudan yetki yükseltme değildir. Entegrasyon kapısı için sonuç, doğrulanmış task/session bağını korumalı veya tüketiciye yalnız orijinal kanonik kayıtla eşleştirilmiş, kapsamı sınırlı bir talimat nesnesi vermelidir. Bağlam kaybolursa görev kaynağı `unknown`/`data_only` kalmalıdır.

### Düşük — Görev kimliği doğrulaması Yuva’nın sayısal ID biçimini kabul etmiyor

`_task_id_valid()` pozitif tamsayıları kabul etmenin yanı sıra boş olmayan, en fazla 256 karakterlik herhangi bir metni geçerli sayıyor (`:52-57`). Yuva görevleri pozitif sayısal ID kullandığından `"not-a-task"` veya çevresinde boşluk olan `" 123 "` gibi değerler, `task_binding_verified=True` ile `TASK_SCOPE` sınıfına ulaşabilir (`:106-115`). Prototipte bu değer sınıflandırma sonucuna aktarılmadığı için mevcut etki sınırlı; yine de kanonik kayıtla eşleme yapan sonraki katmanda biçim uyuşmazlığı ve yanlış kayıt bağlama riski doğurur.

Gerçek Yuva bağlayıcısı için yalnız pozitif tamsayıyı veya boşluksuz kanonik ondalık biçimi kabul edin; metin ID’leri gerekiyorsa ayrı bir sağlayıcı sözleşmesiyle tanımlayın ve kayıt lookup sonucunu doğrulayın.

## Doğrulanan davranışlar

- `USER_INSTRUCTION` yalnız `transport_verified is True` olduğunda talimat sağlayabiliyor; dış eylem yetkisi yine `False`.
- `VERIFIED_OPERATOR` taşıma doğrulamasına ek olarak boş olmayan ve uzunluğu sınırlı principal metni istiyor; bu da dış eylemi yetkilendirmiyor.
- `YUVA_CHAT`, `WORKER_MESSAGE` ve `TOOL_OUTPUT` ek kimlik/verification alanlarına bakılmaksızın `DATA_ONLY` dönüyor.
- Bilinmeyen kaynak veya geçersiz kanıt türü fail-closed `UNKNOWN` sonucuna gidiyor.
- `transport_verified`, `task_binding_verified` ve kimlik alanlarının kriptografik kanıt değil çağıran iddiası olduğu docstring ve README’de belirtilmiş.

## Kaynaklar

- `prototypes/session-bridge/trust_policy.py:32-126`
- `prototypes/session-bridge/README.md`, “`trust_policy.py`” ve “Assumptions and limits”
- `docs/model-output-trust-boundary-464.md`, “Görev kaydı”, “Prompt injection karşısında karar kuralları”
