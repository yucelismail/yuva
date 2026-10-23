# #565 — Yedek doğrulaması için bağımsız authenticity trust anchor

Tarih: 2026-10-23
Durum: Statik tehdit modeli ve MVP kararı; backup, key, servis veya aktif veri
açılmadı/değiştirilmedi.

## Mevcut kanıtın anlamı

`backup_verify.py` arşiv ve yanındaki `.sha256` kaydını karşılaştırıyor; arşiv
biçimini, üye yollarını/türlerini ve güvenli mod koşullarını ayrıca denetliyor.
Eşleşen digest, arşivin sidecar ile **yerel tutarlılığını** gösterir. Arşivle
aynı yazma alanında duran sidecar, ikisi beraber değiştirilebildiği için
üreticiyi veya arşivin beklenen sürüm olduğunu kanıtlamaz. Araç bu nedenle
`authenticity: unverified` döndürüyor (`backup_verify.py:202-250`).

`restore-check` doğrulanmış bir digest eşleşmesi ve güvenli tar yapısı sonrası
yeni, etkin `YUVA_DIR` dışındaki scratch hedefe açıp veri şekillerini kontrol
eder (`backup_verify.py:254+`, `369-397`). Bu bir format/geri-açma provasıdır;
authenticity kanıtı ya da scratch içeriğini etkin veriye terfi ettirme izni
değildir. #550 fixture'ındaki pin de gerçek bağımsız anchor değildir ve host
rollout'u NO-GO bırakır (`docs/release-acceptance-harness-550.md:28-33`).

## Tehdit modeli

| Tehdit / varsayım | Yan yana SHA-256 ne sağlar? | Bağımsız anchor gereksinimi |
|---|---|---|
| Arşiv kopyalanırken bozulma veya eksik yazım | Sidecar sağlam kaldıysa bozulmayı bulur. | Gerekmez; checksum'ın yerel tutarlılık rolüdür. |
| Yedek klasörüne yazabilen süreç arşiv ve sidecar'ı birlikte değiştiriyor | Değişikliği saptamaz. | Digest veya manifest, yedek klasöründen ayrı güven alanında olmalı. |
| Aynı OS hesabı/host ele geçirilip arşiv ve yerel pin defteri değiştiriliyor | Saptamaz. | Başka cihaz/medya, ayrı admin hesabı veya bağımsız hizmet gerekir; yalnız `0600` aynı-UID ayrımı yaratmaz. |
| Hatalı/zararlı tar içeriği veya eksik Yuva dosyası | Digest, içeriğin iyi olduğunu kanıtlamaz. | Anchor'a ek olarak mevcut tar/şema/scratch kontrolleri sürmeli. |
| Backup gizliliği, silinme veya eski snapshot rollback'i | Sağlamaz. | Bu görevdeki authenticity kararı encryption, retention, availability veya anti-rollback garantisi değildir. |

Uygun ilk işletim bağlamı yerel, tek operatörlüdür: `linux-gecis.md` arşivi
`YUVA_DIR` dışındaki backup dizinine alır, hemen `.sha256` üretir ve restore
kontrolü yapar (`docs/linux-gecis.md:56-103`). Bağımsız digest teslim yeri,
imza anahtarı, dış immutable store veya ikinci yönetici mevcut kaynaklarda
tanımlı değildir. Tek kullanıcı hesabı altındaki başka dosya/dizin ya da
backup klasöründen farklı bir path tek başına güven ayrımı oluşturmaz.

## Seçenek karşılaştırması

| Seçenek | Güven sınırı / tehditte etkisi | Anahtar kaybı ve rotasyon | Yerel MVP maliyeti / uygunluğu |
|---|---|---|---|
| Operatörün pinlediği SHA-256 | Beklenen digest backup yazma alanından ayrı kaydedilip sonradan verifier'a bağımsız sağlanırsa, arşiv+sidecar beraber değiştirilmesini yakalar. Kimlik/provenance veya doğru veri üretildiğini kanıtlamaz. Pin arşivden sonra aynı klasörde üretilirse anchor değildir. | Kriptografik anahtar yok. Pin/ledger kaybolursa eski arşiv yalnız `unverified` kalır; digest yeniden arşivden türetilip güven iddiası kuramaz. Yeni arşiv yeni pin alır. | En düşük ek karmaşıklık; bir operatör ve seyrek manuel arşiv için uygulanabilir. Fakat ayrı medya/kanal yoksa bugün bağımsız değildir; elle kayıt/karşılaştırma hatası vardır. |
| İmzalı manifest | Arşiv adı, boyutu, SHA-256, oluşturma zamanı ve backup kimliğini canonical biçimde bağlayan manifest, ayrı tutulan/pinlenen public key ile doğrulanır. İmza private key kontrolünü kanıtlar; signing key aynı hostta ele geçirilirse saldırgan yeni sahte arşivi de imzalayabilir. Doğru source snapshot üretildiğini tek başına kanıtlamaz. | Private key kaybı yeni backup imzalamayı durdurur; eski imzalar pinned public key kaldıkça doğrulanabilir. Public key kaybında güvenli kopya yoksa doğrulama kaybolur. Rotation için eski anahtarla imzalı key-transition veya önceden dağıtılmış yeni public key; compromise için iptal zamanı ve yeniden anchor gerekir. | Otomasyon/çoklu doğrulayıcıda iyi ölçeklenir. Key generation, offline custody, public-key dağıtımı, recovery ve rotation prosedürü bugünkü tek-operatör akışında karşılığı olmayan kalıcı yük oluşturur. İlk MVP için seçilmedi. |
| Dış immutable store | Arşiv veya imzalı manifest, ayrı yönetilen ve retention lock altında tutulan sürümlü depoya yazılırsa yerel host/backup klasörü saldırısını ve eski sürümün üstüne yazılmasını daraltır. Store admin'i/hesabı tek güven alanıysa veya kilit sonradan değiştirilebiliyorsa bağımsızlık zayıflar. | Hesap/credential kaybı restore erişimini kesebilir; yedek admin/recovery ve key erişimi gerekir. Retention lock yanlış ayarlanırsa hassas veriyi silmek gecikebilir. | Host kaybı/off-site ihtiyacında değerli; dış sağlayıcı, ağ, credential, maliyet, veri konumu ve ayrı admin politikası seçilmemiş local MVP'ye uygun değil. |

## İlk local MVP kararı

**Varsayılan karar: authenticity `unverified` kalsın.** Mevcut adjacent
sidecar ve fixture pin'i independent trust anchor olarak yükseltilmesin;
`backup_verify.py` raporundaki ifade korunmalı. Kaynaklardaki gerçek işletim
akışı, aynı operatörün aynı hostta backup üretip verify etmesine dayanıyor ve
ayrı anchor kanalı henüz yok. Bu koşullarda “verified/authentic” etiketi
eklemek kanıtsız güven iddiası olur.

İlk ve dar geçiş adımı, yalnız bağımsız kayıt kanalı gerçekten sağlandığında
operatörce pinlenen digest olabilir. Pin, backup alınırken veya güvenilir
üretim adımında hesaplanmalı; arşiv klasöründen ayrı, aynı yazıcı sürecin
değiştiremediği başka bir medya/cihaz veya ayrı yönetim alanında
korunmalıdır. Sonradan aynı arşivden hesaplanan digest kabul edilmez.
Verifier ileride `--expected-sha256` gibi açık bir girdi alırsa adjacent
sidecar'ı pin yerine kullanmamalı; girdi yok/bozuk/eşleşmiyorsa authenticity
`unverified`/başarısız kalmalı. Pin eşleşse bile sonuç “bu digest'e eşleşiyor”
kanıtıdır, kaynak doğruluğu veya tar güvenliği yerine geçmez.

Unverified arşiv, mevcut parser/permission/scratch sınırları içinde yalnız
izole restore-check için kullanılabilir. Etkin `YUVA_DIR` üzerine restore,
scratch'tan canlıya kopyalama veya yedekten güvenilir kaynak olarak yayınlama
bu kararın kapsamı dışındadır ve anchor dahil ayrı operatör kabul kapısı
gerektirir.

## Geçiş kapıları

1. **Operasyon sahibi ve tehdit seçimi:** Tek host arızası mı, aynı-host
   saldırgan mı, birden fazla doğrulayıcı mı korunacak açıkça seçilsin.
2. **Pin seçeneğini açmadan önce:** Backup üretim adımında digest'in ne zaman
   hesaplandığı, kim tarafından ayrı kanala aktarıldığı ve yanlış/eksik pinin
   nasıl fail-closed reddedildiği tanımlansın. Sentetik test, birlikte
   değiştirilmiş arşiv+sidecar'ın ayrı pinle yakalandığını ve pin yokken
   `unverified` kaldığını göstersin. Gerçek digest rapor/chat/log içine
   gereksiz yere kopyalanmasın.
3. **İmzalı manifest'e geçmeden önce:** Algoritma/format sürümü, canonical
   serialization, signer authority, offline private key custody, pinned
   public-key dağıtımı, backup/recovery kopyaları, rotation/cross-sign ve
   compromise sonrası iptal/yeniden anchor prosedürü kararlaştırılıp kayıp ve
   rotasyon fixture'larıyla sınansın. Private signing key yedek arşiv dizinine
   konmasın.
4. **Immutable store'a geçmeden önce:** Sağlayıcı veya yerel WORM hedefi,
   bağımsız admin sınırı, retention lock, erişim/recovery, maliyet/veri
   konumu ve silme yükümlülüğü onaylansın. Immutable object version veya store
   metadata'sının tar içeriğiyle hangi digest üzerinden bağlandığı
   doğrulansın.
5. Her seçenekte integrity/authenticity sonucu, tar parser/şema sonucu ve
   restore kararı ayrı raporlansın. Anchor başarısı güvenli tar parse,
   snapshot tutarlılığı veya doğru restore kararı anlamına gelmez.

## Kaynak ve kapsam sınırı

- `backup_verify.py:163-192, 202-250` — adjacent checksum parsing, arşiv
  digest'i ve açık `unverified` authenticity sonucu.
- `backup_verify.py:254+` ve `369-397` — scratch extraction ve restore şekil
  kontrolleri.
- `docs/backup-verify-restore-check-544.md` — tool contract ve mevcut
  kullanım örneği.
- `docs/linux-gecis.md:56-103` — backup'ın etkin veri kökünden ayrı tutulduğu
  fakat digest sidecar'ının da backup yanında oluşturulduğu yerel akış.
- `docs/release-acceptance-harness-550.md:28-33` — sentetik fixture pin'inin
  bağımsız anchor olmadığı uyarısı.

Bu not gerçek arşiv veya sidecar açmadı, digest hesaplamadı, anahtar üretmedi,
kod/CLI/deployment değiştirmedi ve test/runtime çalıştırmadı. Bu bir tasarım
kararıdır; trust anchor implement edildiği veya backup authenticity'nin
doğrulandığı anlamına gelmez.
