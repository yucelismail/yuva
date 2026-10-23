# Yuva #672 — Panel auth provisioning uygulama öncesi runbook

**Tarih:** 2026-10-23
**Karar:** **NO-GO — provisioning ve auth aktivasyonu yapılmayacak.**
**Kapsam:** Ön koşul, sahiplik, custody, rollback ve fail-closed kabul sırası. Bu belge canlı ortama işlem talimatı değildir.

## Mevcut kaynak durumuna göre karar

`yuva auth init` (#578) yalnızca önceden oluşturulmuş özel dizinde boş auth-state v2 snapshot'ı ve sabit lock dosyası kurar. Key, enrollment veya operator kimliği oluşturmaz; secret teslim etmez, auth ayarını açmaz ve servis başlatmaz. `auth-state-v2-operations.md` ayrıca onaylı host-side key/enrollment lifecycle, backup/restore ve restore'u koruyacak dış anchor aracı olmadığını belirtir.

Bu nedenle mevcut kaynaklarla canlı store/key provisioning'i veya `YUVA_AUTH_ENABLED=1` geçişini başlatmak için onaylı araç zinciri yoktur. #591 ve #613'teki fixture prototipleri yalnız geçici sentetik state içindir; üretim aracı, custody kanıtı veya canlı kabul yerine geçmez. Bu runbook yalnızca hazırlık ve karar kaydıdır. Eksik kapılardan biri varsa sonuç **NO-GO** olarak kalır; elle JSON/state düzenleme, özel key üretme veya varsayılan auth-off davranışını değiştirme yoktur.

## Sahiplik ve custody kapıları

Uygulama değerlendirilmeden önce aşağıdaki roller isimli, yetkili kişilerle atanmalı ve kayıt altına alınmalıdır. Aynı kişi/UID ayrımı bağımsızlık sağladığı iddia edilerek varsayılamaz.

| Rol | Sorumluluk ve kabul kanıtı |
|---|---|
| Servis/veri sahibi | Audience, instance kapsamı, korunacak veri ve erişim hedefini onaylar; özellikle auth dışı GET snapshot/HTML kararını imzalar. |
| Güvenlik/custody sahibi | Issuer ve client key sahipliğini, üretim/teslim/rotasyon/iptal yöntemini ve OS UID ayrımını onaylar; secret'ın Yuva agent'ı, ortak UID, shell geçmişi, log veya genel backup tarafından okunmadığını kanıtlar. |
| Provisioning operatörü | Yalnız onaylı host-side aracı, değişiklik kaydı ve önceden atanmış audience/scope ile çalıştırır; secret içermeyen receipt ve readback kanıtını saklar. |
| Bağımsız gözden geçiren | Araç sürümünü/özetini, istek kapsamını, sonucu, rollback hazırlığını ve kabul matrisini operatörden bağımsız doğrular. |
| Olay/geri dönüş sahibi | Commit belirsizliği, key compromise, store bozulması veya rollback şüphesinde tüketicileri kapalı tutma ve incident kaydını yönetir. |

Owner-only `0700/0600` izinleri aynı OS UID içindeki süreçleri birbirinden ayırmaz. Yuva agent'ı ve operatör aynı UID'deyse `operator` principal etiketi bağımsız insan kimliği kanıtı değildir; bu durumda operator key enrollment/custody ve auth açılışı NO-GO'dur. Alternatif custody sınırı varsa bağımsız olarak belgelenip doğrulanmalıdır.

## İlerleme için zorunlu kanıtlar

Her satırın kanıtı değişiklik kaydında bulunmalı ve ilgili sahibi tarafından kabul edilmelidir. Kanıt yok, belirsiz veya yalnız fixture/test ise satır **açık** kalır.

| Kapı | Gerekli kanıt | Şu anki kaynak kararı |
|---|---|---|
| Yetki ve kimlik | Instance/audience sahibi, hedef principal allowlist'i, gerekli exact `METHOD /path` scope'ları, expiry ve ayrı onaylar | Operasyon girdileri burada tanımlanmamış; canlı konfigürasyon okunmadı. Açık. |
| Onaylı araç | Sürümü sabitlenmiş host-side provisioning/lifecycle aracı; key/enrollment/revoke, secret custody, atomik commit/receipt/readback ve güvenli hata davranışı dokümante edilmiş olmalı | #578 yalnız boş store init eder. Key/enrollment/backup aracı yok. **NO-GO.** |
| UID ve custody | Agent, servis/verifier ve operator signer için doğrulanmış OS kimlikleri veya eşdeğer harici secret-custody sınırı; korumalı teslim ve erişim kanıtı | Aynı UID sınırı çözülmüş varsayılamaz. **NO-GO** (çözüm belgelenene dek). |
| Rollback/restore | Auth consumer'larından bağımsız güvenilir generation/issuance/revoke anchor'ı; tutarlı snapshot+stable-lock yedeği, erişim/şifreleme/saklama, restore doğrulaması ve eski key/nonce yenileme kanıtı | Snapshot generation kendi içinde rollback'i saptamaz; onaylı backup/restore ve dış anchor aracı yok. **NO-GO.** |
| GET gizliliği | `/api/veri`, `/veri`, `/` ve `/index.html` için erişim hedefi ve gerekirse ayrı auth tasarımının kabulü | GET mevcut auth gate dışında. **NO-GO** açık karar olmadan. |
| İşletim kabulü | Feature-off staging'de pozitif/negatif route testleri, yanlış audience/scope/revoked/expired key reddi, restart ve hata davranışı, rollback provası; canlı rollout için ayrı değişiklik onayı | Bu runbook kapsamında çalıştırılmadı; canlı ortam doğrulanmadı. Açık. |

## Kabul sırası — yalnız tüm kapılar kapandıktan sonra

1. **Değişiklik kaydını açın.** Veri sahibi, güvenlik/custody sahibi, operatör, gözden geçiren ve olay sahibi; instance, audience, hedef principal'lar, exact scope'lar, süre, bakım penceresi ve geri dönüş tetiklerini kayda geçirir. Belirsiz/atanmamış rol ilerlemeyi durdurur.
2. **Araç ve kimlik sınırını doğrulayın.** Onaylı host aracı, dağıtım özeti/sürümü ve çalıştıracağı UID'ler bağımsız incelenir. `yuva auth init` bu zincirde yalnız boş store kurma aracı sayılır; key veya operator provisioning aracı sayılmaz. Aynı UID ya da doğrulanmamış custody varsa durun.
3. **Salt okunur preflight yapın.** Hedefin doğru host, instance ve audience olduğuna dair kimlik doğrulanır; mevcut root/state/lock varlığı ve sahiplik/izin bilgisi secret içeriğini dökmeyen onaylı yöntemle incelenir. Var olan store üzerine init/overwrite yapılmaz. Root, symlink, sahiplik, mode, store şeması/audience veya stable lock konusunda belirsizlik varsa durun.
4. **Backup ve rollback'i önce hazır edin.** Consumer'lar kapalıyken, onaylı yordam aynı sabit lock altında snapshot ile lock'u tutarlı biçimde yedekler. Backup erişimi ve expiry'si sınırlı, secret içeriği şifreli custody'de olmalı; dış anti-rollback anchor ve eski issuance/revocation kanıtı restore öncesi erişilebilir olmalı. Bunlar yoksa store'a yazmayın.
5. **Provisioning'i yalnız onaylı araçla uygulayın.** İşlem onaylı principal/audience/scope/expiry sınırında kalır; key sırrı stdout, argv, environment, terminal kaydı, genel Yuva mesajı, JSONL veya receipt'e çıkmaz. Her mutasyon sabit store/lock ve güvenilir receipt/readback sözleşmesine uymalıdır. Böyle bir araç ve kabul edilmiş sözleşme mevcut değilse bu adım çalıştırılmaz.
6. **Sonucu fail-closed doğrulayın.** Store şeması, audience, generation değişimi, key/enrollment bağı ve receipt yalnız secret içermeyen readback ile doğrulanır; verifier/issuer ve tüketici ayarları feature-off kalır. `CommitUnknown`, fsync hatası, beklenmeyen generation, eksik/mismatch receipt veya okunamayan store'da kör retry, yeni operation ID, rollback/fallback veya auth açma yoktur. State çevrimdışı korunur ve incident sahibi unresolved olarak devralır.
7. **İzole staging kabulü yapın.** Auth kapısı kapalı ve gerçek secret içermeyen fixture/staging ortamında pozitif ve negatif istekler, yanlış route/audience/scope, expired/revoked key, replay, restart ve failure senaryoları gözden geçirilir. GET snapshot/HTML davranışı ayrıca doğrulanır. Fixture sonucu canlı host custody veya backup güvenliğini kanıtlamaz.
8. **Bağımsız rollout onayı alın.** Tüm kapılar ve kanıtlar gözden geçirici tarafından imzalanmadan `YUVA_AUTH_ENABLED=1` ya da canlı consumer başlangıcı için değişiklik uygulanmaz. Etkinleştirme ayrı, açık rollout kararıdır; init veya provisioning başarısından çıkarılamaz.

## Durdurma ve geri dönüş kuralları

- Eksik sahip, onaysız/kimliği belirsiz araç, aynı UID custody, kararsız audience/scope veya eksik GET kararı: **NO-GO**, feature-off kalır; provisioning yapılmaz.
- Hedefte önceden var olan state, yanlış owner/mode/link, bozuk şema/audience ya da lock inode uyuşmazlığı: yazmayı durdurun; dosyaları silmeyin veya düzeltmek için elle editlemeyin. Offline inceleme ve incident kaydı açın.
- `CommitUnknown` veya işlem sonrası belirsiz sonuç: consumer kapalı kalır; aynı mutasyon otomatik tekrar edilmez. Yalnız onaylı readback/receipt ile çözülebiliyorsa çözün; aksi halde unresolved olarak eskale edin.
- Key compromise veya güvenilmeyen/eski backup şüphesi: ilgili credential ve nonce geçmişini güvenli kabul etmeyin. Restore'u doğrudan canlıya almayın; dış issuance/revocation kayıtlarıyla karşılaştırın ve onaylı araçla yeni credential/state planı olmadan tüketiciyi başlatmayın.
- Rollback gerekirse auth gate/consumer kapatılır; eski snapshot'ı olduğu gibi geri yüklemek veya auth-off'a sessiz düşmek güvenli rollback varsayılmaz. Revoke/nonce durumunun geri sarma riski ve dış anchor doğrulanmadan yeniden açılış yapılmaz.

## Bu teslimde yapılanlar

Kaynak belgeler ve kabul kayıtları dokümantasyon amacıyla okundu. Canlı auth ayarı, host store, key, UID/izin, servis veya backup üzerinde işlem yapılmadı; provisioning, test ve runtime doğrulaması çalıştırılmadı. Belge, mevcut kanıta göre NO-GO kararını ve gelecekteki kabul sırasını kaydeder.

## Kaynaklar

- `docs/auth-init-578.md` — boş v2 store init sınırı ve aynı UID custody riski.
- `docs/auth-state-v2-operations.md` — gate, GET sınırı, lifecycle/backup araç boşluğu, commit belirsizliği ve rollback sınırı.
- `docs/auth-state-v2-final-source-audit-468.md` — güncel kaynak davranışına ilişkin son denetim.
- `docs/auth-key-enrollment-lifecycle-fixture-591.md` — fixture lifecycle'ının üretim aracı/custody olmadığı ve üretim öncesi kapılar.
- `docs/auth-key-operation-receipt-fixture-613.md` — fixture receipt prototipi ve `CommitUnknown` sınırları.
- `docs/auth-provision-draft-review-478.md`, `docs/auth-provision-commit-unknown-502.md` — taslak provisioning'in commit belirsizliği değerlendirmeleri.
