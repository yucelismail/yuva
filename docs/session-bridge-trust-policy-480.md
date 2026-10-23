# #480 — Oturum köprüsü talimat ve güven politikası

**Durum:** Önerilen tasarım politikası; uygulanmış kontrol değildir.

## Kaynağa göre yorum

| Girdi | Köprüdeki anlamı | İzin |
|---|---|---|
| Sistem/developer talimatı ve mevcut oturumdaki doğrudan kullanıcı isteği | Talimat hiyerarşisi içinde kullanıcı talimatı | Açıkça istenen ve kapsamı belli işi yürüt. Daha yüksek öncelikli sınırları aşma. |
| Kimliği/oturumu doğrulanmış operatörden gelen yapılandırılmış kontrol | Yalnız doğrulanan principal ve kapsama bağlı talimat/karar | Principal, hedef oturum ve izinli eylem eşleşiyorsa uygula. Body'deki kimden, ad veya rol iddiası kimlik kanıtı değildir. |
| Kanonik Yuva görevi | Atanmış işin sınırlı kapsam talimatı | Görev ID'si, aktif durum, assignee ve kapsamı kanonik görev kaydından doğrula. Görev, üst talimatları veya izinleri genişletemez. |
| Yuva sohbeti, yuva gelen, mesaj başlığı/notu | Güvenilmeyen metin/veri; yönlendirme iddiası olabilir | İçeriğini incele veya ilgili doğrulanmış göreve bağla. @agent, “kullanıcı onayladı” ya da aciliyet sözü tek başına dispatch, yetki veya onay değildir. |
| Worker/model yanıtı, başka modelin değerlendirmesi, tool çıktısı, repo dosyası, terminal ve hata metni | Kaynağına göre kaydedilebilen veri/kanıt; kendiliğinden talimat değil | Özetle, alıntıla ve iddialarını kaynakta doğrula. İçindeki yeni yönergeyi, kimlik/izin iddiasını veya tamamlandı ifadesini yürütme yetkisine yükseltme. |
| JSON-RPC approval isteği | Sağlayıcıdan gelen bekleyen izin isteği | Yalnız isteği kaydet ve doğru Yuva kullanıcısına göster. Cevap verme; karar için açık, eyleme bağlı insan yanıtı bekle. |

Doğrulanmış sözcüğü yalnız mesaj metninin dışındaki güvenilir taşıma
kimliğiyle bağlanmış principal için kullanılabilir. Mevcut Yuva sohbeti, CLI
--from, model adı, loopback/Host/Origin, actor_id, trust veya provenance
metaverisi tek başına gerçek kullanıcı/model kimliğini kanıtlamaz. Bu oturum
köprüsünün bugün böyle bir kimlik doğrulama özelliği olduğu varsayılmamalıdır.
Kanıt yoksa kaynak unknown/unverified olarak kalır ve privileged yönlendirme
ya da eylem yetkisi vermez.

## Yönlendirme ve Yuva makbuzu

1. Provider session/thread ile Yuva konuşması/görev arasındaki bağ yalnız
   yapılandırılmış ve doğrulanmış session binding'den kurulur. Mesaj içindeki
   hedef, modelin önerdiği thread ID veya “bu işi başka ajana ilet” metni
   session binding'i değiştirmez.
2. Bir Yuva mesajı provider'a gönderilecekse önce kararlı Yuva message ID ve
   operation/attempt bağı kaydedilmelidir. Provider turn/thread ID'leri
   yanıt/event kanıtından sonra bu kayda bağlanır; modelin kendi yazdığı
   correlation ID doğrulanmış kimlik sayılmaz.
3. Kayıp yanıt, timeout, kısmi yazım, kopma veya restart sonucu belirsizse
   işlem unknown olur ve yalnız read-only uzlaştırma yapılır. Kesin sıfır
   byte yazıldığı kanıtlanmadıkça aynı mesajı otomatik tekrar gönderme.
   JSON-RPC request ID uzak idempotency garantisi değildir.
4. Provider turn/completed olayı yalnız provider turn'ünün terminal
   gözlemidir. Yuva'ya çıktı yazıldığına dair ayrı durable receipt ve Yuva
   görev pending_verification/review geçişi gerekir. verified yalnız Yuva
   denetim akışının kararıdır; Codex/OpenCode çıktısından türetilmez.
5. Worker mesajı veya model çıktısı, yeni Yuva görevi oluşturamaz/üstlenemez,
   görevi başka çalışana atayamaz, görevi teslim/onay/revize edemez ve
   session'ın yönünü değiştiremez. Bunlar yalnız izinli Yuva lifecycle
   işlemi ve doğrulanmış yetkiyle yapılır.

## İnsan onayı eşiği

Görev veya doğrudan kullanıcı isteği açık ve dar biçimde yetkilendirmedikçe;
dosya silme/üzerine yazma, secret gösterme veya dışarı aktarma, dış servise
veri gönderme, provider iznini kabul etme, rol/görev dağıtma veya iptal etme,
host/servis/daemon değiştirme gibi önemli yan etkiler için ilgili yetkili
insandan eylem, hedef ve kapsamı belirten açık onay gerekir. Onaylandı
şeklindeki model/worker/tool/chat metni bu eşiği karşılamaz.

Approval isteği event'i, approval yanıtı ve provider'ın resolved bildirimi
ayrı gözlemlerdir. Yanıtta karar yoksa veya bağlantı kaybı yüzünden karar
eşleşmiyorsa sonuç unknown/pending_unknown kalır; onay varsayılmaz ve
provider'a otomatik cevap gönderilmez.

## Uygulama kapısı

Bu politika bir tasarım önerisidir; mevcut Yuva ve provider prototiplerinde
zorunlu enforcement bulunduğunu ileri sürmez. Uygulamadan önce authenticated
session binding, principal/permission modeli, durable correlation/receipt,
unknown uzlaştırma ve insan approval UI/yanıt sahipliği ayrıca tanımlanmalı ve
incelenmelidir. Güvenli kaynak bağı kurulamazsa köprü yalnız gözlem yapmalı;
mesajı talimat gibi dispatch etmemeli veya dış eylem başlatmamalıdır.

Dayanak: docs/model-output-trust-boundary-464.md,
prototypes/codex-app-server/receipt-integration-contract.md,
prototypes/codex-app-server/receipt-event-order-matrix.md,
docs/task-mutation-idempotency-outbox-design-437.md ve
docs/task-mutation-failure-matrix-452.md.
