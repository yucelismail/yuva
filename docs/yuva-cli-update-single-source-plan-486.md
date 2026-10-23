# Yuva #486 — CLI güncelleme ve tek kaynak kullanımı için güvenli plan

Kapsam: #485 yerel kopya envanterinden hareketle kod kaynağını, kurulu çalışma kopyasını, atomik güncellemeyi, doğrulamayı ve geri almayı tanımlamak. Bu bir salt okunur plandır. Veri dosyalarına, bağlantılara veya servislere dokunulmadı; canlı geçiş yapılmadı.

## Envanterden çıkan karar

#485'in gözleminde normal `yuva` komutu `~/.local/bin/yuva` üzerinden `yuva-v2/bin/yuva` dosyasına gidiyor. Ayrı `yuva/` ve `yuva-dev/` ağaçları var; README ilk kurulum için eski ağaç yolunu tarif ediyor. Bu nedenle bugünkü tek kaynak sözleşmesi belirsiz: PATH'teki CLI v2'yi seçerken kurulum belgesi başka kopyayı gösteriyor. Ayrıca bu ağaçların aynı veri kökünü kullanması, ayrı kod sürümlerinin aynı JSON verisine yazabileceği anlamına gelir.

Önerilen sahiplik:

| Rol | Sözleşme |
| --- | --- |
| **Kanonik kaynak** | Bakımı yapılan tek Git deposu ve içindeki açıkça seçilmiş commit. Eski ve geliştirme kopyaları kaynak kabul edilmez; güncellemeler yalnız bu depoya girer. Kaynak çalışma ağacı kirli veya commit'i belirsizse release çıkarılmaz. |
| **Kurulu çalışma kopyası** | Seçilmiş commit'ten oluşturulan, sürüm/commit kimliğiyle adlandırılmış ve kurulumdan sonra değiştirilmeyen release dizini. Uygulanan CLI ve panel bu kopyadan çalışır. |
| **Etkin sürüm işaretçisi** | Kurulum kökündeki tek `current` bağlantısı, bir release dizinini gösterir. CLI giriş noktası ve panel unit'i aynı işaretçiden kod yükler. |
| **Veri kökü** | CLI ve panelin ortak `YUVA_DIR` değeri. Kod release dizininin dışında tutulur; release kurulumu veya rollback veri kökünü kopyalamaz, silmez ya da dönüştürmez. |

`<SOURCE_REPO>`, `<INSTALL_ROOT>`, `<USER_BIN>` ve `<DATA_ROOT>` aşağıdaki planda operatörün mevcut yerel kurulumda belirleyeceği genel adlardır; bunlar gerçek yol veya yeni kurulum talimatı değildir. Mevcut kurulumun hangi kökü kullandığı doğrulanmadan bir varsayılan seçilmemelidir.

## Güncelleme akışı

1. **Kaynağı sabitle:** Yalnız `<SOURCE_REPO>` içindeki seçili Git commit'i kaynak olsun. Commit hash'i, branch/tag adı, çalışma ağacının temiz olduğu bilgisi ve release oluşturma zamanı bir release manifestinde tutulur. Başka kopyadan dosya seçerek release birleştirilmez. Şu anki çalışma ağacında yerel değişiklikler bulunduğundan, bu ağaç temiz ve commit ile eşlenmiş bir kaynağa dönüşmeden buradan release alınmamalıdır.
2. **Adayı ayrı yerde hazırla:** Tam commit ağacını `<INSTALL_ROOT>/releases/.staging-<id>` gibi kurulum köküyle aynı dosya sisteminde yeni bir dizine çıkar. Release dosyaları tamamlanıp doğrulandıktan sonra staging dizinini `<INSTALL_ROOT>/releases/<commit>` adına atomik rename ile geçir. Var olan release dizininin üstüne yazma. Gerekli dosya modu ve sembolik bağ hedeflerini kontrol et; release içindeki bağlantılar release dışına çıkmamalıdır.
3. **Veri uyumluluğunu geçiş kapısı yap:** Aday sürümün okuduğu/yazdığı JSON şemaları ve veri dosyası davranışını `<DATA_ROOT>`'un etkin sürümüyle karşılaştır. Yeni şema eski sürümün okuyamayacağı biçimde değişiyorsa, eski release'e dönmek güvenli sayılmaz. Bu durumda uyumlu geçiş/geri dönüş tasarımı ve ayrı yedek planı tamamlanmadan işaretçi değiştirilmez. Kod güncellemesini veri taşıma ile aynı adımda birleştirme.
4. **Tek etkin kod köküne bağla:** `<USER_BIN>/yuva` giriş noktası `<INSTALL_ROOT>/current/bin/yuva` yoluna, panel unit'indeki `ExecStart` ise `<INSTALL_ROOT>/current/panel/server.py` yoluna bağlı olsun. İkisi de aynı `<DATA_ROOT>` için `YUVA_DIR` alsın. README ve örnek unit dosyası bu sözleşmeyi anlatsın; eski `~/yuva` kod+veri birleşik varsayımı düzeltilsin. Geliştirme ağacı kullanıcı tarafından özellikle seçilmedikçe PATH veya servis başlangıç noktası olmasın.
5. **Yazıcı tekilliğini doğrula:** Symlink değişimi yalnız bundan sonra başlayacak süreçlerin kod seçimini atomik kılar; önceden açılmış CLI veya panel süreci eski kodu bellekte tutabilir. Canlı geçişten önce host işletiminden sorumlu operatör, ortak veri köküne eski/yeni sürümün eşzamanlı yazmadığını, devam eden yazma isteği bulunmadığını ve CLI ile panelin aynı kök yapılandırmasını kullanacağını teyit etmelidir. Bu teyit ve planlı bakım penceresi yoksa güncelleme ilerlemez. Bu belge servis durdurma komutları veya canlı sistemde işlem tarifi vermez.
6. **İşaretçiyi atomik değiştir:** Aynı dosya sisteminde geçici bir symlink'i yeni release'e oluşturup doğrula; sonra `<INSTALL_ROOT>/current` üzerine atomik rename ile al. Symlink hedefi ve `current` aynı kurulum kökünde olmalı; eski release korunmalı. CLI ve panelin sabit giriş yolları `current` kullandığında tek işaretçi flip'i sonraki başlangıçları aynı sürüme yönlendirir. Panel servis dosyasının kendisi ayrıca release yoluna pin edilmişse bu düzen atomiklik sağlamaz; unit'in sabit `current` yolu kullanması gerekir.
7. **Sürümü kanıtla:** `bin/yuva` içinde bir `--version` arayüzü envanterde görülmedi; böyle bir komut varmış gibi varsayma. `current` çözümlemesinin beklenen `<commit>` release'ine ulaştığını, manifest commit/tree kimliğini ve `bin/yuva`, `panel/server.py`, `panel/ui.html` SHA-256 değerlerini doğrula. Panel/CLI konfigürasyonunun aynı `<DATA_ROOT>` değerini kullandığını kaydet. Başlangıç logu veya dağıtım raporu bu commit kimliğini göstermeli; yalnız “komut başarıyla çalıştı” sürüm kanıtı değildir.
8. **Kademeli kabul:** Geçiş öncesi belirlenmiş salt-okunur canary kontrolleriyle CLI'nin beklenen release'i seçtiğini, panelin aynı release ve veri kökünden başladığını, eski/yeni yazar çakışması olmadığını ve tahta/mesaj okumalarının beklenen veriyi sunduğunu doğrula. Yazma canary'si gerekiyorsa ayrı, geri alınabilir kabul planı ve yetkili operatör kararı gerekir; bu statik plan canlı yazım yetkisi vermez.

## Geri alma

- Önceki sürümün release dizini ve manifesti yerinde ve doğrulanmış tutulur. Sorun durumunda aynı atomik işaretçi yöntemi `current`'ı önceki release'e döndürür; `<USER_BIN>/yuva` ve panelin sabit yolları değişmez.
- Rollback sırasında da iki sürümün aynı `<DATA_ROOT>`'a eşzamanlı yazmasına izin verilmez. Host operatörü önce yeni sürümden devam eden işlem kalmadığını ve eski sürümün açılabileceğini teyit etmelidir.
- Sırf kod sürümünü geri alırken veri yedeğini otomatik olarak geri yükleme. Sonradan oluşmuş mesaj/görev kayıtlarını yok edebilir. Veri restore'u yalnız kanıtlanmış veri bozulması, yedek tutarlılığı ve yazım sonrası kayıtların etkisi incelendikten sonra ayrı bir veri kurtarma kararıdır.
- Aday sürüm veri biçimini eski sürümle uyumsuz değiştirdiyse, symlink'i geri döndürmek yeterli değildir. Aday yayımlanmadan önce uyumlu geri dönüş, ileri düzeltme veya doğrulanmış yedekten kurtarma yolu tanımlı olmalıdır.
- Başarısız canary, hatalı hash/manifest, farklı veri kökleri, çalışan eski yazar, belirsiz symlink hedefi veya şema uyumsuzluğu güncellemeyi durdurma koşuludur. Durum doğrulanamıyorsa tekrar kurulum/rollback komutu çalıştırmak yerine önce release ve işlem sonucunu oku.

## #485 ile uyum ve açık işler

- #485'in gösterdiği PATH giriş noktası ve etkin v2 CLI kopyası mevcut durumu betimler; bu, otomatik olarak kalıcı kanonik kaynak kararı vermez. Sözleşme, bir Git commit'ini kaynak ve sürümlü release'i kurulu kopya yapar.
- README'deki ilk kurulum tarifi ile PATH'in seçtiği kopya aynı kaynağı göstermeli. Servis unit'i de sabit `current` işaretçisini kullanmalı; `WorkingDirectory`, `ExecStart` ve `YUVA_DIR` değerleri birbirinden bağımsız, açıkça belgelenmeli.
- CLI ve panel veri kökünü kod kökünden ayrı çözüyor; ortak `YUVA_DIR` doğrulaması release kabul ölçütüdür. Kod kopyası sayısı azaltılsa da eski sürümle aynı veriye yazma tehlikesi tek başına ortadan kalkmaz.
- CLI'da gözlenen `--version` komutu yoktur. Manifest ve hash doğrulaması bu planın mevcut araçlarla uygulanabilir sürüm kanıtıdır; makinece okunur `--version` eklemek ayrı uygulama işidir.
- Bu rapor kaynak envanteri ve `docs/linux-gecis.md` içindeki bakım, yedekleme ve rollback uyarılarını tasarım girdisi alır. Burada tarif edilen release dizini ve atomik `current` düzeni henüz uygulanmış değildir.
