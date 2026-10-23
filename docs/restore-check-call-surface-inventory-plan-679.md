# #679 — Tarihsel restore-check CLI kopyaları için çağrı yüzeyi envanter planı

**Tarih:** 2026-10-23
**Durum:** Salt-okunur envanter planı ve rapor şablonu; sistem çağrı yüzeyi taraması bu görevde yapılmadı.
**Kapsam:** #638/#659 içindeki iki tarihsel restore-check ağacı ve bunlara yönelme ihtimali olan yerel giriş noktaları.

## Amaç

Bu plan, aşağıdaki CLI dosyalarının hangi kullanıcı veya otomasyon girişleriyle çağrılabileceğini sınırlı ve tekrarlanabilir biçimde araştırır:

- `<YUVA_DATA_ROOT>-yedek/restore-check.T4hbP8/yuva/bin/yuva`
- `<YUVA_DATA_ROOT>-yedek/restore-check.XOeUcj/yuva/bin/yuva`

Sonuç, her çağrı yüzeyinin kanıtını ve aramanın sınırını kaydeder. Envanter tek başına containment veya “çalıştırılamaz” garantisi vermez. #638'in scratch çıktısındaki stub'ı tarihsel ağaçları korumaz; #659'daki geçici çalıştırmama kuralı yürürlüktedir.

## Güvenli toplama kuralları

- İki tarihsel CLI'ı veya yanındaki paneli **çalıştırma, import etme, kaynak yükleyiciye verme ya da test subprocess'i olarak başlatma**.
- Dosya, symlink, archive/tar, sidecar, servis, shell ayarı, görev defteri, izin ve sahiplik üzerinde değişiklik yapma.
- İncelemeyi path, symlink hedefi, `lstat`, owner/mode, dosya hash'i, yapılandırma satırı ve statik kaynak referanslarıyla sınırla. Eski hash'i güncel kabul etme; hash'i o inceleme anında yeniden ölç.
- Arama köklerini önceden kaydet. Sonuçları başka kullanıcıların ev dizinlerine veya tüm diske genişletme. Erişilemeyen kökü `unknown` yaz; boş sonuç gibi yorumlama.
- Ortam değişkenlerinin değerlerini, key/token içeriklerini, mesajları ve görev JSON gövdelerini rapora kopyalama. Gerekirse yalnız değişken adını veya redakte edilmiş satırı yaz.
- Gerçek hedefe yönelen pozitif eşleşme bulunursa çağrı yapma. Referansın türünü statik olarak sınıflandır ve operatöre containment kararı için raporla.

## İnceleme sırası

### 1. Kaynak kimliğini sabitle

İki hedef için `lstat` türü, çözülmüş path, SHA-256, owner, mode ve parent dizinlerin mode/owner bilgilerini salt-okunur kaydet. Sonuçları #627/#659'daki eski snapshot'lardan ayır; o snapshot'lar bugünkü dosya durumunu kanıtlamaz. Tar/sidecar kapsamını sadece dosya adı ve metadata düzeyinde tut; içerik taraması yapma.

### 2. PATH, shell ve kısa komut girişleri

İnceleme oturumunun `PATH` değerini gizli/kişisel bileşenleri gerekirse redakte ederek kaydet. `type -a yuva` / `command -v -a yuva` sonuçlarını, alias ve shell function tanımlarını incele. Bilinen shell başlangıç dosyalarında yalnız `yuva`, hedef dizin adı, symlink ve PATH ekleme satırlarını ara. Bulunan symlink zincirini hedefi çalıştırmadan çöz ve her adımı kaydet.

PATH'te tarihsel path bulunmaması yalnız bu PATH snapshot'ında kısa komut eşleşmesi görülmediğini gösterir; absolute path, import veya panel çağrısını dışlamaz.

### 3. Launcher ve servis tanımları

Önceden belirlenen kapsamda desktop `Exec=` alanlarını, user systemd unit/timer `ExecStart=`/`OnCalendar=` alanlarını ve Yuva için bilinen wrapper/launcher dosyalarını statik incele. Unit/environment dökümlerindeki sırları rapora taşıma. Bir launcher'ın çağırdığı her ara script'i zincirin ayrı satırı olarak kaydet; job body'sini çalıştırma.

### 4. Mutlak path ve dinamik kaynak çağrıları

Kayıtlı köklerde aşağıdaki işaretleri salt-okunur metin aramasıyla tara:

- İki tam path ve `restore-check.T4hbP8`, `restore-check.XOeUcj` dizin adları.
- `yuva-yedek`, `bin/yuva` ve shell/Python çağrı kalıpları.
- Python `importlib`, `SourceFileLoader`, `spec_from_file_location`, `runpy.run_path`, `execv`/`subprocess` ile dosya yolu verilen çağrılar.
- Shell script'lerinde `python`, `python3`, `exec`, `source` ve değişken üzerinden kurulan muhtemel path'ler.

Yalnız literal arama değişken birleştirme, symlink veya dışarıdan verilen argümanları bulamayabilir. Herhangi bir Python import/loader mekanizmasını doğrulamak için hedef modülü yükleme; caller kaynak kodunu statik incele.

### 5. Panel kopyası

İki tarihsel ağacın `panel/server.py` dosyalarını yalnız metin olarak incele. CLI core'u hangi sabit path/loader ile çağırıyor, task mutasyon route'ları hangi handler'a gidiyor, panelin başlatılması için hangi unit/launcher var ve `YUVA_DIR` nasıl aktarılıyor sorularını kaydet. Tarihsel paneli import etme veya başlatma. Sadece panel kaynağında bir route bulunması, o panelin kurulu/çalışır olduğunu kanıtlamaz.

### 6. Otomasyon

Önceden belirlenen yerel köklerde cron/crontab, systemd timer/service, desktop launcher, backup/restore script'i ve bilinen Yuva otomasyonlarının statik tanımlarını kontrol et. Zamanlanmış görevin argüman, çalışma dizini ve interpreter/launcher zincirini kaydet; görevi tetikleme. Yetki nedeniyle okunamayan kaynağı `unknown` olarak işaretle.

### 7. Eşleştir ve sınıflandır

Her bulguyu şu durumlardan biriyle işaretle:

- **confirmed-reference:** statik kaynakta hedef path'e doğrudan çözülen çağrı var.
- **candidate-reference:** değişken, alias, symlink veya dinamik import nedeniyle olası çağrı var; hedef çözümlenemedi.
- **no-match-in-scope:** belirtilen kök ve dosya türlerinde arama tamamlandı, eşleşme görülmedi.
- **unknown:** kök okunamadı, dinamik kaynak çözümlenemedi veya kapsama alınmadı.

Bir eşleşmeyi “aktif/çalışan” olarak sınıflandırma; bunun için ayrı, yetkili runtime gözlemi gerekir ve bu plan o gözlemi yapmaz. `no-match-in-scope`, sistem genelinde çağrı yolu olmadığı veya kopyanın güvenli olduğu anlamına gelmez.

## Arama kapsamı kaydı

Her tarama turunda arama öncesinde bu listeyi gerçek kapsamla doldur. Kök atlama nedenini yaz; wildcard'ı `yuva-yedek` içeriğini okumak için genişletme.

| Kök/kaynak | Okunabildi mi? | Aranan uzantı/alan | Arama tarihi ve komutu | Sonuç/sınır |
|---|---|---|---|---|
| İnceleme shell'inin PATH/alias/function görünümü |  |  |  |  |
| Bilinen shell startup dosyaları |  |  |  |  |
| `~/.local/bin` ve bilinen Yuva launcher'ları |  |  |  |  |
| `~/.local/share/applications` |  |  |  |  |
| `~/.config/systemd/user` unit ve timer tanımları |  |  |  |  |
| Yuva repo ve bilinen backup/restore otomasyon kaynakları |  |  |  |  |
| Kullanıcı crontab / okunabilen system cron tanımları |  |  |  |  |
| İki restore-check ağacının statik CLI/panel kaynak dosyaları |  |  |  |  |

Bu kökler örnektir; arama gerçekten yapılmadan “taranmış” olarak işaretlenmemelidir. Yeni kök eklenirse nedeni ve içerdiği dosya sınıfı yazılır.

## Rapor şablonu

### İnceleme bilgisi

- Tarih/saat ve timezone:
- İncelemeyi yapan:
- Salt-okunur yöntem/sürüm:
- Kapsama alınan kökler:
- Atlanan/erişilemeyen kökler ve neden:
- Tarihsel CLI'lar/paneller çalıştırıldı veya import edildi mi: **Hayır**
- Archive, sidecar, canlı `YUVA_DIR`, servis veya izin değişti mi: **Hayır**

### Hedef kimliği

| Hedef | `lstat` türü / resolved path | SHA-256 | owner:mode | Parent mode | Önceki kayıtla fark |
|---|---|---|---|---|---|
| `restore-check.T4hbP8/yuva/bin/yuva` |  |  |  |  |  |
| `restore-check.XOeUcj/yuva/bin/yuva` |  |  |  |  |  |

### Çağrı yüzeyi bulguları

| Surface | Durum | Caller ve kaynak: satır | Hedef çözümü | Tetikleme/argüman | Olası mutasyon | Kapsam/kanıt sınırı |
|---|---|---|---|---|---|---|
| PATH / shell alias/function |  |  |  |  |  |  |
| Symlink / launcher / desktop entry |  |  |  |  |  |  |
| Mutlak path referansı |  |  |  |  |  |  |
| Python import / source loader |  |  |  |  |  |  |
| Panel CLI bridge / panel launcher |  |  |  |  |  |  |
| Cron / systemd / diğer otomasyon |  |  |  |  |  |  |

Her **no-match-in-scope** sonucu arama kökü ve dosya kapsamıyla birlikte verilir. Secret içerebilecek satırlar aynen kopyalanmaz.

### Sonuç ve takip

- Gözlenen doğrudan/candidate çağrı yolları:
- Envanter dışında kalan yollar:
- Mevcut kural: iki tarihsel kopyayı çalıştırma/import etme; yeni scratch restore-check CLI stub'ını normal CLI/release olarak kullanma.
- PATH'ten çıkarma gibi kolaylık önlemlerinin direct-path/import/panel bypass'ını kapatmadığı uyarısı:
- Gerekli operatör/containment kararı ve sahibi:
- Takip görevi / karar kaydı:
- Sonuç etiketi: **inventory complete within listed scope / partial / unknown** (birini seç).

## Kabul kontrolü

- [ ] İki hedefin güncel path/hash/mode/parent metadata'sı read-only kaydedildi.
- [ ] PATH/shell, launcher, absolute path, Python loader, panel ve otomasyon yüzeylerinin her biri `confirmed`, `candidate`, `no-match-in-scope` veya `unknown` olarak raporlandı.
- [ ] Her “no match” için arama kökü, dosya kapsamı, tarih ve araç kaydedildi.
- [ ] Hiçbir tarihsel CLI/panel çalıştırılmadı veya import edilmedi; herhangi bir çağrı tetiklenmedi.
- [ ] Archive/tar/sidecar, canlı `YUVA_DIR`, task ledger, service, mode, owner ve launcher değişmedi.
- [ ] PATH aramasının veya eksik statik aramanın güvenlik sınırı olmadığı açıkça yazıldı.
- [ ] Sonuç containment iddiasına genişletilmedi; runtime için gereken ayrı kanıtlar UNKNOWN bırakıldı.

Bu belge plan/şablondur; gerçek makinede çağrı yüzeyi envanteri veya containment uygulaması yapıldığı anlamına gelmez.
