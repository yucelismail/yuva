# Yuva #461 — Auth-state operasyon kılavuzu bağımsız doğrulaması

## Kapsam ve sonuç

`docs/auth-state-v2-operations.md`, `panel/server.py`, `panel/auth_integration_draft.py`, `panel/auth.py` ve `panel/auth_store_v2.py` statik olarak karşılaştırıldı. Kod değiştirilmedi; test veya runtime çalıştırılmadı.

Kılavuzun önemli güvenlik sınırları kaynakla uyumlu: auth varsayılan olarak kapalı; etkinleştirme önceden provision edilmiş store ve eşleşen audience ister; POST kapısı ham target/body doğrulamasından sonra JSON parse ve dispatch öncesinde çalışır; GET snapshot ve HTML auth dışındadır; store kendiliğinden bootstrap/provision/backup/restore yönetimi sunmaz; snapshot içi generation tek başına restore rollback'ini önlemez. Ancak kılavuzun HTTP revizyon durumu güncel değildir ve `server.py` satır referansları eski kalmıştır.

## Bulgular

### Orta — #426 ve yinelenen Content-Length bulgusu hâlâ açık gösteriliyor

Kılavuz §Durum ve kapsam, §Sunucudaki mevcut kapı ve ayarlar, ilk provisioning adımı ve son hazırlıklar bölümlerinde yinelenen `Content-Length` bulgusunun hâlâ #426 revizyonunda olduğunu veya kabul beklediğini yazıyor. Görev panosunda #426 ve #429 `verified` durumunda. Güncel `_govde_oku()` `headers.get_all("Content-Length", [])` kullanıyor; birden fazla başlığı gövdeyi okumadan 400 ile reddediyor (eşit değerler dahil). `do_POST()` bu framing hatasında bağlantıyı kapatıyor; `Transfer-Encoding` varsa da önce reddediyor (`panel/server.py:1518-1532, 1578-1586`).

Bu nedenle kılavuzdaki #426 revizyonu bekleme ifadeleri artık doğru değil. İşletim kararının kendisi — canlı auth'ı yalnız bu tek düzeltme nedeniyle değil, provisioning/restore, GET gizliliği ve işletim kabulü tamamlanmadan açmama — ihtiyatlı ve geçerlidir. Durum metninde düzeltmenin kabul edildiği belirtilmeli; kalan canlı hazırlık kapıları ayrı bırakılmalıdır.

### Düşük — `server.py` satır referansları güncel dosyayla uyuşmuyor

Özellikle kılavuzdaki şu referanslar eski konumu gösteriyor:

- §Durum ve kapsam ve POST akışı: `server.py:1025-1070, 1315-1362`; güncel gate config `auth_gate_yukle()` içindedir (`server.py:1283-1327`), POST auth/dispatch `do_POST()` içindedir (`server.py:1578-1628`), `AuthGate` ise ayrı `auth_integration_draft.py` dosyasındadır.
- GET sınırı: kılavuz `server.py:1319-1331` der; güncel `do_GET()` `server.py:1554-1566` aralığındadır. GET akışında gate çağrısı olmadığı iddiası doğrudur.
- Loopback başlangıç sınırı: kılavuz `server.py:1385-1400` der; güncel `main()` kontrolü `server.py:1655-1666` aralığındadır. Dış bind'in reddedildiği iddiası doğrudur.

`auth_store_v2.py` referanslarının ve `encode_initial_state()`/`generation_floor` açıklamalarının kontrol edilen esas içerikleri kaynakla uyumludur. Satır numaraları dosyada sonraki düzenlemelerde tekrar değişebilir; fonksiyon/sınıf adıyla birlikte konum vermek daha dayanıklı olur.

## İddia doğrulama özeti

| Kılavuz iddiası | Kaynak karşılığı | Sonuç |
|---|---|---|
| `YUVA_AUTH_ENABLED` yok/`0` → kapalı; tam `1` dışında hata | `panel/server.py:1283-1299` | Doğru |
| Store root ve audience zorunlu; store okunup audience eşleşmesi doğrulanır; hata anonim moda düşmez | `server.py:1296-1327`, startup hata yolu `1662-1666` | Doğru |
| Admin principal listesi operator config'inden, sıkı biçim/tekrar kontrolüyle gelir | `server.py:1301-1311` | Doğru |
| Ham `self.path` ve body auth'tan geçer; parse sonrası payload policy; aynı doğrulanmış route dispatch edilir ve principal ayrı aktarılır | `server.py:1588-1623`; `auth_integration_draft.py:74-150` | Doğru |
| GET `/api/veri` ve `/`, gate kullanmadan sunulur | `server.py:1554-1566` | Doğru; anonim erişim açısından açık sınır |
| `encode_initial_state()` yalnız doğrulayıp byte üretir, dosya/root/lock oluşturmaz | `auth_store_v2.py:586-595`; `AuthStateStore` önceden var olan dosyaları ister (`476-481`) | Doğru |
| `generation_floor` dış güvenilir caller floor'u olmadan anti-rollback sağlamaz; varsayılanı `None` | `auth_store_v2.py:476-503, 505-522` | Doğru |
| Eski, tutarlı backup kendi iç generation/nonce/revocation durumunu geriye sarabilir | store içinde dış anchor/restore transcript doğrulaması yok (`auth_store_v2.py:10-14, 483-485`) | Doğru |
| `auth_store_v2.py` modül docstring'inde “auth.py veya server.py tarafından import edilmez” açıklaması eski | `server.py:1313-1320` store'u import eder; `auth.py` de store tipini kullanır | Kılavuzun uyarısı doğru |

## İncelenen kaynaklar

- `docs/auth-state-v2-operations.md`
- `panel/server.py`: `auth_gate_yukle`, `_govde_oku`, `do_GET`, `do_POST`, `main`
- `panel/auth_integration_draft.py`: `AuthGate.authenticate_post`, `authorize_payload`
- `panel/auth.py`: `HMACAuthenticator.verify_request`
- `panel/auth_store_v2.py`: exact schema, root/file/lock açma, snapshot okuma/yazma, `AuthStateStore`, `encode_initial_state`
- `<YUVA_DATA_ROOT>/gorevler.json`: #426, #429 ve #447 durumları
