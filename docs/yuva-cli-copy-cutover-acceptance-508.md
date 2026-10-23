# Yuva #508 — CLI kopya geçişi için kabul listesi

Kapsam: #485 envanteri ve #486 tek kaynak planına göre geçiş öncesi/sonrası kabul koşulları. Salt okunur kontrol listesidir; sistem symlink'i, servis veya Yuva verisi değiştirilmedi.

## Geçiş öncesi

- [ ] **Kaynak sabit:** Tek kanonik Git deposu, commit kimliği ve temiz çalışma ağacı kayda geçti. Kurulum adımı başka bir eski/geliştirme kopyasından dosya almıyor.
- [ ] **Aday kopya hazır:** Kurulu aday release bu commit'ten üretildi; release dizini değiştirilmiyor. Manifestte commit/tree kimliği ve CLI/panel dosyalarının hash'leri var.
- [ ] **CLI girişi biliniyor:** PATH'teki `yuva` girişinin çözüldüğü gerçek dosya ve hedef release doğrulandı. #485'teki eski kopya ve geliştirme ağacı doğrudan giriş noktası olarak kalmıyor; bir istisna varsa sahibi ve amacı açıkça kaydedildi.
- [ ] **Panel kod kökü biliniyor:** Kullanıcı servis tanımındaki `ExecStart` ve etkin panel sürecinin yüklediği kod ağacı aynı aday release'i gösteriyor. Yalnız unit dosyasına bakmak, zaten çalışan sürecin kodunu kanıtlamaz.
- [ ] **Veri kökü tek:** CLI ve panel `YUVA_DIR` için aynı mutlak, gerçek dizin çözümlemesini kullanıyor; ayar verilmediği durumdaki varsayılan da doğrulandı. Veri kökü release dizininin dışında.
- [ ] **Eski yazar yok:** Eski CLI kopyasını doğrudan çalıştıran oturum/otomasyon ve eski panel sürecinin aynı veri köküne yazmadığı host işletiminden sorumlu kişi tarafından doğrulandı. Eski bir süreç veya belirsiz writer varsa geçiş kabul edilmez.
- [ ] **Şema dönüşü uyumlu:** Adayın okuyup yazacağı veri biçimi mevcut veriye uygun; rollback hedefi adayın ürettiği kayıtları okuyabiliyor. Bu doğrulanamıyorsa geri dönüş yolu ayrıca tasarlanana kadar geçiş başlamaz.
- [ ] **Koruma hazır:** Ortak veri kökü için izinleri ve gerekli metadata'yı koruyan, restore kontrolü yapılmış bir yedek mevcut; yedek etkin veri kökünün dışında.

## İşaretçi geçişi sonrası

- [ ] **Tek CLI hedefi:** Sabit CLI PATH giriş noktası kurulumdaki `current/bin/yuva` hedefini çözüyor; hedef beklenen commit'e ait release.
- [ ] **Tek panel hedefi:** Panel unit'i aynı `current` işaretçisinin `panel/server.py` dosyasını çalıştırıyor; etkin süreç yeni release'ten başlamış ve eski süreç yok.
- [ ] **Sürüm kanıtı:** Release manifest commit/tree kimliği ve dosya hash'leri kurulu hedefle eşleşiyor. CLI'da envanter sırasında gözlenmiş bir `--version` seçeneği yok; doğrulamayı var olmayan sürüm komutuna dayandırma.
- [ ] **Veri kökü kanıtı:** CLI ve panelin etkin yapılandırmalarındaki `YUVA_DIR` aynı veri kökünü gösteriyor; görev/mesaj verisinin beklenen kökten salt okunur geldiği doğrulandı.
- [ ] **Kademeli kabul:** İlk canary'de CLI hedefi, panel hedefi, veri kökü ve tek writer koşulu birlikte doğrulandı. Bunlardan biri belirsizse daha fazla model/istemci bağlanmıyor.

## Rollback kabulü

- [ ] **Önceki release mevcut:** Önceki release dizini ve manifest/hash kanıtı korunuyor; rollback hedefi tam commit ile belirlenmiş.
- [ ] **Writer tekilliği korunuyor:** Yeni koddan devam eden istek/yazıcı kalmadığı ve eski release'in açılabileceği doğrulanmadan eski sürüm ortak veriye bağlanmıyor.
- [ ] **İşaretçi geri döner:** Rollback yalnız `current` hedefini doğrulanmış eski release'e alır; sabit CLI ve panel giriş yolları tutarlı biçimde eski sürümü seçer.
- [ ] **Veri korunur:** Kod rollback'i veri yedeğini otomatik geri yüklemez. Yeni sürüm verisi eski şemayla uyumsuzsa aynı veri köküne dönüş kabul edilmez; ayrı kurtarma kararı gerekir.
- [ ] **Son doğrulama:** CLI ve panelin eski release'ten çalıştığı, ikisinin aynı `YUVA_DIR` kullandığı ve beklenen görev/mesajların okunduğu doğrulanır.

## Geçişi durdurma koşulları

Kanonik commit, etkin CLI/panel hedefi, ortak veri kökü, writer tekilliği veya geriye dönük şema uyumu kanıtlanamıyorsa geçiş/rollback kabul edilmez. Symlink'i çevirmek tek başına önceden açılmış süreci değiştirmez ve ortak veri yazımlarını durdurmaz.

Bu liste #485'in PATH'teki v2 CLI ile README'deki eski kurulum tarifi arasındaki farkını, #486'nın sürümlü release ve ortak `current` işaretçisi önerisini, ayrıca mevcut Linux geçiş rehberindeki eşzamanlı writer ve veri kurtarma uyarılarını temel alır. Geçiş henüz uygulanmış değildir.
