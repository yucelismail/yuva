# JSON/JSONL şema uyumluluğu ve rollback (#549)

## Bugünkü sözleşme

`durum.json` ve `gorevler.json` aynı `YUVA_DIR` içinde CLI ve panel tarafından
okunur. Mevcut kök alanları (`kullanicilar`/`rev` ve `siradaki`/`gorevler`)
önceki dosyalarda sürüm numarası olmadan bulunur. Eksik `schema_version`, bu
değişiklikle **v1** kabul edilir. İlk başarılı durum/görev yazımı köke
`schema_version: 1` ekler; bu yalnızca eklemeli bir etiketlemedir, kayıtları
dönüştürmez veya silmez.

CLI ve panel v1 köklerini okumaya devam eder; v1 yazımlarında bilinmeyen kök
alanları korunur. Açık ve geçersiz/boolean ya da desteklenmeyen sürüm değeri
fail-closed hatası üretir. Okuyucu görevi başlatmaz, varsayılan boş deftere
düşmez ve dosyayı değiştirmez. `backup_verify.py` de aynı kök sürüm kapısını
uygular.

`mesaj.jsonl` tek bir dosya şemasına toplu yükseltilmez. Sürüm alanı olmayan
eski satırlar v1/legacy, mevcut provenance zarflı satırlar v2 kabul edilir.
CLI ve panel v1/v2 satırlarını okur; legacy satırlar yalnız doğrulanmamış
görüntüleme verisi sayılır. Açıkça verilmiş hatalı veya desteklenmeyen sürümlü
satır normal mesaj görünümüne alınmaz; kaynak JSONL satırı olduğu gibi kalır.
Backup doğrulaması `mesaj.jsonl` için bilinmeyen sürümde arşivi reddeder.
v2 sohbet satırlarında `source_class` ve `source_class_trust` isteğe bağlıdır;
eski v2 satırları geçerli kalır. Yeni satırlar `operator`/`agent`/`unknown`
iddiasını ve `unverified` güvenini taşır. Okuyucular sınıfı yetkiye yükseltmez;
eksik veya geçersiz iddia görünümde `unknown` olur.
`ekran/*.jsonl` kayıtları şu an sürümsüzdür ve bu görev onları yeniden
yazmaz.

Release manifestlerindeki `data_contract.schema_compatibility` değeri
`yuva-data-contract/v1` olur. Bu kimlik, yukarıdaki kök v1 ve mesaj v1/v2
okuma sözleşmesini ifade eder; ekran JSONL için yeni bir şema iddiası taşımaz.
Acceptance aracı yalnızca bildiği bu kimliği uyumlu sayar.

| Veri | Okuyucu uyumluluğu | Bilinmeyen sürüm | Yazma davranışı |
| --- | --- | --- | --- |
| Durum/görev JSON kökü | Eksik sürüm ve v1 | Okuma/yazma reddedilir; dosya korunur | Başarılı yazımda v1 damgası; veri göçü yok |
| Mesaj JSONL satırı | Sürüm alanı olmayan legacy, v1 ve v2 | Normal panel/CLI görünümünden atlanır; satır korunur | Satır ekleme, eski satırları yeniden yazmaz |
| Ekran JSONL satırı | Mevcut sürümsüz biçim | Bu sürümleme değişikliğinin kapsamı dışında | Append-only davranış korunur |

## İleri uyum ve yükseltme

Yeni, isteğe bağlı alanlar mevcut okuyucuların bilinmeyen alanları koruyup
güvenle yok saydığı sürece kök v1 veya ilgili JSONL satır sürümünde kalabilir.
Zorunlu alan/semantik değişikliği, okuyucular ve backup doğrulayıcı birlikte
hazır olmadan yeni sürümle yazılamaz. Yeni bir JSONL satır sürümü ayrı satırlara
aittir; bütün dosyayı yeniden yazmak gerekmez.

Desteklenmeyen JSON kök sürümü değişiklik öncesi backup/inceleme gerektirir.
Desteklenmeyen mesaj satırları normal sohbette gizli kalır; arşiv kaynağında
korunur ve restore-check tarafından kabul edilmez. Otomatik/destructive
migration veya eski alanları düşürme yoktur.

## Release rollback sınırı

Yerel release installer `current` işaretçisini atomik değiştirir ve
`YUVA_DIR`'i değiştirmez. Bu nedenle kod rollback'i veri rollback'i değildir.
Bu sürüm v1'i yazdığı için mevcut eski sürümsüz dosyalarla uyumludur. Ancak
daha önceki okuyucular `schema_version` alanını bilmez; gelecekteki bir release
v2 verisi yazdıktan sonra eski koda pointer rollback yapılması eski okuyucunun
v2'yi görmezden gelerek yazmasına engel olmaz. Bu yüzden v2'ye geçiş, eski
release'e rollback penceresi kapanmadan yapılamaz.

Rollback penceresinde v2 biçimi zorunluysa release yöneticisi aynı aktif
`YUVA_DIR` üzerinde otomatik dönüşüm yapmamalıdır. Ayrı ve doğrulanmış veri
kopyası, geri dönüş eşlemesi ve açık operatör onayı olan offline bir geçiş
planı gerekir. Snapshot içindeki sürüm numarası tek başına eski kodun
korumasını sağlayamaz. Auth/presence gibi anti-rollback garantisi de vermez.

## Kanıt

`tests/test_data_schema_compat.py` yalnız geçici dizin kullanır; legacy okuma,
yazım damgası, gelecekteki kök/mesaj sürümünde fail-closed ve backup verifier
reddini doğrular. Testler canlı `YUVA_DIR` veya servis kullanmaz.
