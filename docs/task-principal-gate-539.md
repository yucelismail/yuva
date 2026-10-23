# #539 — Görev mutasyonlarında doğrulanmış aktör kapısı

> **Revizyon:** İlk yerel MVP tek OS hesabını güven sınırı kabul eder. Auth
> kapalıyken CLI `--from` ve API body `kimden` değerleri yazıma izin veren
> yerel aktör etiketleridir; kimlik kanıtı değildir ve görev geçmişi
> `actor_trust=local_unverified` olarak işaretler. `YUVA_AUTH_ENABLED=1` iken
> aynı etikete güvenilmez: API için doğrulanmış HMAC principal ve uygun işlem
> policy'si gerekir; principal olmadan CLI mutasyonları fail-closed reddedilir.

**Tarih:** 2026-10-23
**Kapsam:** `yuva-v2` görev CLI/panel kapısı ve geçici veri kökü kullanan fixture testleri.
**Sınır:** Canlı Yuva verisi, auth anahtarı/provisioning, çalışan servis ve eski CLI kopyaları değiştirilmedi.

## Uygulanan kapı

- Auth kapalı yerel MVP'de `bin/yuva gorev ...` açıkça verilen `--from` etiketini kabul eder. Bu etiket doğrulanmış kimlik değildir; her görev olayı `actor_trust=local_unverified` taşır.
- Auth açıkken (`YUVA_AUTH_ENABLED=1`) doğrudan CLI mutasyonları doğrulanmış principal bağlamı olmadığı için reddedilir. Her görev writer'ı principal'ın yalnız aynı süreçteki task köprüsü tarafından sağlanan bağlamda bulunmasını ve `--from` metninin principal kimliğiyle eşleşmesini ister.
- Panel, görevi subprocess olarak başlatmak yerine aynı v2 CLI modülünü aynı süreçte çağırır. Auth-on modunda HMAC `VerifiedPrincipal` nesnesi payload’dan ayrı taşınır; olay aktörü request içindeki `kimden` iddiasından alınmaz.
- Auth kapalıyken yerel `/api/gorev` body içindeki `kimden` değerini denetim etiketi olarak kullanır ve olayı `local_unverified` işaretler. Bu, kullanıcının tek-UID MVP kararıdır; model kimliği veya rol doğrulaması iddiası değildir.
- Auth açıkken `/api/gorev` principal yoksa 401 döner; `AuthGate` doğrulanmış principal için işlem policy’sini handler dispatch’inden önce belirler:

| İşlem | Auth kapalı yerel MVP | Auth açık HMAC modu |
|---|---|---|
| Aktör kaynağı | CLI `--from` veya API body `kimden`; doğrulanmış kimlik değil | API'den ayrı taşınan `VerifiedPrincipal`; body iddiası kullanılmaz |
| Görev olayı | `actor_trust=local_unverified` | `actor_trust=verified_hmac` |
| Doğrudan CLI mutasyonu | Yerel kullanıcı etiketiyle izinli | Principal köprüsü olmadığı için fail-closed ret |
| API mutasyonu | Tek UID varsayımı altında yerel etiketle izinli | HMAC principal ve aşağıdaki işlem policy'si gerekli |

| İşlem | Auth-on API policy | CLI/domain kontrolü |
|---|---|---|
| `ekle`, `ata`, `iptal` | yapılandırılmış admin principal | geçiş ve ilgili hedef/görevli kontrolleri |
| `al`, `teslim` | doğrulanmış principal, worker policy | kayıtlı `isci` rolü; `al`/`teslim` geçiş ve assignee denetimi |
| `ilk-kontrol`, `denetle` | doğrulanmış principal, reviewer policy | mevcut `goreci`/`denetci`, görevli/reviewer ve durum denetimleri |

Bilinmeyen işlem policy tarafından reddedilir. Handler ayrıca principal scope’u ile kendisine iletilen işlem policy’sini eşleştirir.

## Fixture kanıtı

`python3 -m unittest tests.test_task_principal_gate tests.test_code_data_roots -v` revizyonda çalıştırıldı: **11 test geçti**. Fixture’lar geçici `YUVA_DIR` kullanır. Kapsam; auth-off CLI/API aktör etiketlerinin `local_unverified` kaydı, auth-on principal yokken CLI/API fail-closed davranışı, yanlış scope/policy retleri, payload'daki sahte `kimden` yerine principal'ın kayda geçmesi, worker claim'inin principal'a bağlanması ve AuthGate işlem policy matrisidir.

## Güven sınırı ve kalan işler

- Bu kapı farklı actor iddialarına karşı uygulama sınırıdır; aynı OS UID’de çalışan saldırgan koda karşı bir güven kökü değildir. Aynı UID kodu bu Python sürecini etkileyebilir, veri dosyalarını doğrudan değiştirebilir veya kendi eski kopyasını çalıştırabilir.
- `<YUVA_DATA_ROOT>/bin/yuva` gibi legacy kopyalar güncellenmedi. Eski kopya ortak `YUVA_DIR`’ye yazabiliyorsa bu v2 kontrolünü atlayabilir ve v2 kilit/provenance davranışını paylaşmayabilir. Eski writer’lar ayrıca devre dışı bırakılmalı veya ortak veriye erişimleri işletim sistemi düzeyinde kaldırılmalıdır.
- AuthGate varsayılan kapalı kalır; auth-off local actor etiketi tek-UID yerel MVP varsayımına dayanır ve OS hesabı içindeki zararlı süreçlere karşı koruma sağlamaz. Auth etkinleştirilecekse önceden provision edilmiş HMAC kayıtları ve doğru route scope gerekir. Admin işlemlerinde `YUVA_AUTH_ADMIN_PRINCIPALS` ayrıca doğru yapılandırılmalıdır. Bu görev auth provisioning veya kapı açma yapmadı.
- Görev geçmişi hâlâ aktör metni tutar; key ID, request ID ve kriptografik imzalı audit receipt eklemez. Aynı-UID / eski CLI ve commit sonrası bildirim belirsizliği bu değişikliğin kapsamı dışındadır.
