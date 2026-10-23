# Yuva yerel veri tehdit modeli

## Kapsam ve varlıklar

Bu not mevcut aday CLI/panel davranışını ve varsayılan tek kullanıcı dağıtımını değerlendirir; yeni erişim kontrolü uygulamaz. Veri kökü `YUVA_DIR` ile seçilir, varsayılanı `~/yuva`'dır (`bin/yuva:28-34`, `panel/server.py:43-48`, `README.md:93-97`). CLI ve panelin aynı kullanıcı hesabı ve aynı veri köküyle çalışması beklenir.

Korunacak veriler:

- `durum.json`: kullanıcı/rol ilişkileri, notlar ve yerel durum.
- `gorevler.json`: görev başlıkları, açıklamaları, atama ve inceleme geçmişi.
- `mesaj.jsonl`: sohbet metinleri ve kaynak/kimlik iddiaları.
- `ekran/<kimlik>.jsonl`: terminal/model çıktısı; komutlar, dosya yolları, hata izleri, ortam bilgisi ve kullanıcı yanlışlıkla yazarsa token/credential içerebilir.
- `.kilit`, geçici dosyalar ve KOK dışı yedekler: kalıcılık ve eşzamanlılık için gereken fakat uygun izinlerle ayrıca korunması gereken yardımcı veriler.

Mesaj ve ekran kayıtlarını hassas kabul edin. Kimlik veya provenance alanları aktör doğrulaması değildir; panelin yeni mesaj zarfı açıkça `trust=unverified`, `actor_id=null`, `auth_method=none` üretir (`README.md:62-69`, `panel/server.py:771-801`).

## Kim neyi okuyabilir ve değiştirebilir?

| Aktör | Dosya sisteminden doğrudan erişim | Panel HTTP erişimi | Güven sınırı |
|---|---|---|---|
| Yuva sahibi Unix UID'si altındaki CLI, panel, model oturumu veya başka süreç | KOK içindeki durum, görev, mesaj ve ekran verisini okuyabilir; izin veriliyorsa değiştirebilir. Aynı UID'deki süreçler birbirinden dosya izinleriyle yalıtılmaz. | Panel açıksa API'yi çağırabilir. | Güvenilen tek yerel kullanıcı sınırı budur; aynı UID altında çalışan model/eklenti/komut da bu güveni paylaşır. |
| Farklı, ayrıcalıksız yerel UID; panelle aynı network namespace | KOK `0700`, alt dizinler `0700`, JSONL dosyaları owner-only `0600` olduğunda doğrudan dosya erişimi engellenir. CLI/panel güvenli append'i sahiplik, tür, mode, symlink ve hard-link kontrolleriyle doğrular (`bin/yuva:221-283`, `panel/server.py:277-339`). | Loopback `127.0.0.1:8686` erişilebilirse kimlik doğrulaması olmadan `/api/veri` ile panel görünümünü okuyabilir ve açık POST uçlarını çağırabilir. `/api/yaz` mesaj ekler, `/api/ekran` ekran satırı ekler. Sunucu tarafından üretilen provenance bu isteği doğrulanmış aktör yapmaz (`panel/server.py:936-969`, `771-817`, `1143-1192`). | Dosya izinleri HTTP erişimini kısıtlamaz. Host/Origin ve Content-Type kontrolleri kimlik doğrulama değildir (`README.md:172-182`, `panel/server.py:1050-1086`). |
| Panel ile aynı UID'yi paylaşmayan, ayrı network namespace içindeki yerel süreç | KOK izinleri doğrudan erişimi engeller. | Panel host'un loopback adresini görmüyorsa varsayılan olarak erişemez; namespace/paylaşılan ağ ayarı değişirse bu varsayım yeniden değerlendirilmelidir. | Namespace ayrımı dosya erişimini değil, yalnız ağ yolunu etkiler. |
| Uzak makine / LAN istemcisi | Normal kullanıcı izinleriyle yerel dosya erişimi yoktur. | Varsayılan bind `127.0.0.1`'dir ve loopback dışı bind reddedilir (`panel/server.py:1205-1226`). SSH tüneli, ters vekil veya başka bir port yönlendirmesi yeni erişim yolu oluşturur. | Kimlik doğrulama/erişim kontrolü eklenmeden paneli LAN'a, internete veya uzaktan erişilebilen vekil arkasına açmayın (`README.md:178-182`). |
| Host yöneticisi / root | Yerel dosyalara erişebilir ve izin denetimlerini aşabilir. | Sunucuyu veya ağ yönlendirmesini değiştirebilir. | Bu yazılım host yöneticisine karşı gizlilik ya da bütünlük sağlamaz. |

Panelin `GET /api/veri` cevabı kullanıcı/durum özetini, görevleri, mesajları ve ekranları bir arada verir (`panel/server.py:936-969`). Bu yüzden yalnızca yazma uçlarını korumak yeterli olmaz: farklı UID'nin localhost erişimi hassas içeriğin okunmasını da sağlar. Mevcut endpoint kaynak/biçim kontrolleri uygular, fakat HTTP istemcisinin Unix UID'sini doğrulamaz (`panel/server.py:1050-1086`, `1143-1192`).

## Varsayılan güvenli dağıtım sınırı

1. Yuva'yı tek, güvenilen Unix kullanıcı hesabıyla çalıştırın. O hesap altındaki tüm süreçleri — model oturumları ve eklentiler dahil — KOK verisini okuyup değiştirebilen süreçler olarak değerlendirin. Aynı UID'ye karşı gizlilik veya yetki ayrımı varsaymayın.
2. KOK ve `ekran/` dizinlerini yalnız sahibi erişebilir (`0700`), JSONL dosyalarını yalnız sahibi okuyup yazabilir (`0600`) tutun. Panel başlangıcı ve güvenli JSONL yazıcıları izin/owner/tür kontrollerinde hata verirse otomatik gevşetme yapmadan durur (`panel/server.py:284-339`, `1209-1218`; `bin/yuva:228-283`). `durum.json`, `gorevler.json`, kilitler, geçici dosyalar ve yedekler için de owner-only izinleri koruyun; yedekleri KOK dışında tutun (`docs/linux-gecis.md:56-83`).
3. Paneli loopback'te bırakın. Loopback yalnız ağ erişimini daraltır; aynı network namespace'teki farklı UID süreçlerini engellemez. Bu süreçler güvenilmiyorsa paneli onlara açık ağ namespace'inde çalıştırmayın. Ayrı UID'ler arasında API paylaşımı gerekirse, Unix domain socket + `SO_PEERCRED` gibi gerçek peer kimliği denetimi ve ayrıcalık tabanlı endpoint politikası tasarlanıp uygulanmadan güvenli kabul etmeyin (`panel/server.py:1219-1226`).
4. Uzak erişim gerekiyorsa erişim kontrolünü dış uçta sağlayan, kimliği doğrulanmış bir vekil kullanın; ham panel portunu tünel veya ağ bind'iyle açmak kimlik doğrulama eklemez.
5. Ekran/sohbet kayıtlarına sır, erişim anahtarı veya kişisel veri yazılmasını önleyin; gerekiyorsa yakalandıktan sonra erişim/retention ve silme politikası uygulayın. Yalnızca arayüzde gizlemek veya kimlik alanını `unknown` yapmak ham JSONL içeriğini gizlemez.

## Sınırlar ve açık işler

- Bu tehdit modeli süreç kimliğini panel API'sine bağlamaz; `--from`, görünen ad, rol ve mesaj provenance alanları tek başına kimlik kanıtı değildir (`README.md:62-75`, `panel/server.py:771-801`).
- JSONL yazıcılarının 0700/0600 ve no-follow kontrolleri, KOK altındaki her JSON/backup dosyasına otomatik olarak uygulanmış sayılmaz; yedek ve durum dosyaları ayrı izin denetimi gerektirir.
- Ağ namespace'leri, tüneller, bind mount'lar, yedekleme hedefleri ve yerel servis yapılandırmaları dağıtıma özgüdür. Bunların güvenliği bu kodun loopback kontrolünden çıkarılamaz.
- Bu belge tasarım/dağıtım rehberidir; canlı host yapılandırmasının veya tüm dosyaların izinlerinin denetlendiği anlamına gelmez.
