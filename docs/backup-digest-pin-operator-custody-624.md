# Yedek digest pin'i için operatör custody prosedürü (#624)

**Tarih:** 2026-10-23
**Durum:** Yerel MVP için koşullu, manuel prosedür taslağı.
**Karar:** Bağımsız pin kanalı kurulup doğrulanana kadar backup authenticity `unverified` kalır. Bu belge bir kanalı/medyayı provision etmez ve canlı backup'ı doğrulamaz.

## Amaç ve güven sınırı

Bu prosedür, backup arşivinin SHA-256 değerini arşivin ve yan yana `.sha256` dosyasının yazıldığı alandan ayrı bir custody alanında tutup sonradan `backup_verify.py`'ye beklenen değer olarak sağlamayı tarif eder. Bağımsız pin, arşiv ile sidecar'ın beraber değiştirilmesini yakalayabilir. Backup'ın doğru kaynaktan üretildiğini, snapshot'ın tutarlı olduğunu, arşiv içeriğinin güvenli olduğunu veya restore'un doğru olduğunu kanıtlamaz.

Bağımsızlık path adından veya `0600` izinlerinden gelmez. Backup yazarı ile pin yazarı aynı ele geçirilmiş hostta/UID'de çalışıyorsa ya da ikisi de aynı değiştirilebilir klasöre ve yöneticiye bağlıysa pin bağımsız değildir. Yerel MVP'de kullanılacak ayrı medya/cihaz veya ayrı yönetim alanı operasyon sahibi tarafından önceden seçilip erişim sınırı doğrulanmalıdır. Böyle bir hedef yoksa pin'i backup klasörüne kopyalamayın; yalnız yerel checksum ve `unverified` sonucuyla kalın.

## Ön koşullar

Operatör aşağıdakileri backup alınmadan önce kayda bağlar:

1. **Yetkili operatör:** İşlemi yapan kişi ve gerektiğinde ikinci gözden geçiren kişi belirlenir. Beklenen digest'i kimlerin okuyup değiştirebildiği custody alanında sınırlıdır.
2. **Ayrı hedef:** Hedef, backup dizininden farklı bir güven alanıdır: örneğin kontrollü çevrimdışı çıkarılabilir medya veya ayrı kimlik/yönetici alanında tutulan kurumsal kayıt. Aynı hostta farklı bir path yeterli değildir. Seçilen hedef yerel risk modeline göre bağımsız değilse bu prosedür uygulanabilir sayılmaz.
3. **İş kimliği:** Her arşive değişmez bir backup ID, arşiv adı, kaynak instance/ortam etiketi ve oluşturma zamanı (UTC) verilir. Dosya adı tek başına kimlik sayılmaz; aynı adla yenileme yeni backup ID gerektirir.
4. **Araç davranışı:** Hedeflenen verifier sürümü ve `--expected-sha256` sözleşmesi bilinir. Beklenen değer tam 64 küçük harfli hex olmalıdır. CLI değeri process listelerinde gösterebilir; digest credential değildir ama gereksiz yere ortak log, ekran kaydı veya sohbete yazılmaz.

## Oluşturma ve custody aktarımı

1. Backup'ı yalnız onaylı akışla, etkin `YUVA_DIR` dışında üretin. Üretim tamamlandıktan sonra arşiv ve sidecar'ın kapanıp yazımının bittiğini doğrulayın; arşiv için backup klasöründeki değeri kopyalamak yerine güvenilen üretim makinesinde gerçek arşiv byte'larından SHA-256 hesaplayın. Hesaplama arşiv son halini aldıktan sonra, fakat arşiv taşınmadan/yeniden adlandırılmadan önce yapılır.
2. Digest'i backup alanından ayrı bir yolla custody hedefindeki kayda aktarın. Aktarımın kaynağı operatörün güvenilen üretim oturumu olmalı; e-posta/chat, Yuva mesajı, aynı klasördeki yeni sidecar veya arşivle birlikte taşınan USB/klasör bağımsız kanal sayılmaz. Hedefe kaydeden yetkili operatör, aktarımı tam yaptığını ve iş kimliğini eşleştirdiğini doğrular. Mümkünse ikinci operatör digest'in iki görünümünü bağımsız okuyup karşılaştırır; bu kontrol tek başına ele geçirilmiş üretim hostunu güvenilir yapmaz.
3. Custody kaydına yalnız gerekli metadata'yı yazın: backup ID, arşiv adı, SHA-256, algoritma (`SHA-256`), UTC üretim zamanı, üretici/verifier araç sürümü veya kaynak revizyonu, operatör, aktarım kanalı/medya envanter kimliği, alan erişim sınıfı ve doğrulayan kişi/zamanı. Arşiv içeriği, kullanıcı/mesaj verisi veya başka sırları kayda eklemeyin. Kayıt güncellenebilir ise eski değeri sessizce ezmeyin; değişikliğin önceki/yeni backup ID'sini ve onayını içeren audit izi bırakın.
4. Arşiv backup alanına taşındıktan veya hedef adla sabitlendiğinde yeniden verify edin. Arşiv yeniden paketlenir, yeniden oluşturulur veya byte düzeyinde değişirse eski pin'i taşımayın: yeni backup ID ile digest'i yeniden üretip ayrı custody akışını baştan tamamlayın.

## Sonraki doğrulama ve restore kararı

1. Operatör verifier girdisi olarak kullanılacak pin'i custody hedefinden getirir ve backup ID/arşiv adını eşleştirir. Aktarım sırasında beklenen digest'in doğruluğu ayrıca teyit edilir; verifier kendi başına pin'in provenance'ını doğrulamaz.
2. Salt-okunur incelemede `python3 backup_verify.py verify --archive <archive> --expected-sha256 <pin>` çalıştırılır. Çıktıda `expected_sha256.matches_archive=true`, adjacent checksum eşleşmesi ve tar/izin kontrollerinin başarılı olduğu ayrı ayrı incelenir. `authenticity` raporu hâlâ `unverified` ise bu mevcut sözleşmedir; operatör bunu “authentic/verified” diye yükseltemez.
3. Digest yoksa, bozuksa, kimliği eşleşmiyorsa, aktarım/custody belirsizse veya eşleşmiyorsa işlemi durdurun; pin'i arşivden veya adjacent sidecar'dan yeniden türetip eski backup'a güven kazandırmayın. Farkı inceleme kaydına, ham arşiv verisini taşımadan, backup ID ve hata türüyle yazın. Yeni pin ancak yeni ve onaylı backup üretim işlemiyle oluşturulur.
4. Restore provası gerekiyorsa yalnız mevcut `restore-check` ile etkin veri kökünün dışında yeni, private scratch hedef kullanın; aynı bağımsız pin'i verin. Başarılı hash eşleşmesi ve scratch restore-check, etkin `YUVA_DIR` üzerine restore veya scratch'tan canlıya terfi izni değildir. Gerçek restore ayrıca onaylı rollback/operatör kabul kapısı gerektirir.

## Kayıp, değişiklik ve rotasyon

- **Pin kayboldu veya custody hedefi erişilemiyor:** Eski backup `unverified` kalır. Sidecar'dan pin'i geri kurmayın. Önceden doğrulanmış başka custody kopyası varsa onun erişim ve geçmiş bütünlüğünü teyit edip kullanımını kayda alın; yoksa eski arşiv için authenticity pin'i geri kazanılamaz. Yeni backup alınması eski snapshot'ı doğrulamış sayılmaz.
- **Pin kaydı yanlış/uyuşmaz:** Değeri sessizce düzeltmeyin. Backup ID, kayıt sürümü, kimlerin eriştiği ve arşiv değişikliği ihtimalini inceleyin; sonuç netleşene kadar verify/restore kararını durdurun. Olay çözülürse yeni backup kimliği ve yetkili onayıyla yeni kayıt oluşturun.
- **Medya/kanal/hesap değişimi:** Eski hedef erişilebilirken eski ve yeni custody sahipleri backup ID + digest kayıtlarını kontrollü biçimde karşılaştırır. Yeni hedefe aktarım doğrulanır, erişim kaydı tutulur, eski kopya retention politikasına göre kapatılır/silinir. Yalnız yeni path'e kopyalamak custody devri kanıtı değildir.
- **Backup yenileme:** Her değişmiş arşiv ayrı backup ID ve yeni pin alır. Önceki kayıtlar denetim/retention kararıyla saklanır; en son dosya adına göre otomatik overwrite yapılmaz.
- **Aynı host/hesap compromise şüphesi:** Yerel pin kaydını güvenilir kabul etmeyin; o hostun ürettiği yeni pin saldırganın değiştirdiği arşivi de onaylayabilir. Bağımsız cihaz/hesap üzerindeki önceden mevcut kayıt kullanılabiliyorsa incident incelemesi ve verifier hostunun güvenilirliği ayrıca değerlendirilir. Bu prosedür incident response veya güvenli yeniden kurulum sağlamaz.

## Kabul kontrolü

Operatör aşağıdakilerin tümüne `evet` diyemiyorsa bağımsız-pin akışını kullanmaz ve sonucu `unverified` bırakır:

- [ ] Pin, arşiv byte'larından güvenilen üretim adımında ve arşiv son halini aldıktan sonra hesaplandı.
- [ ] Pin'in tutulduğu hedef backup yazma alanından ve onun aynı host/UID/yönetici güven alanından bağımsız.
- [ ] Backup ID ile arşiv ve pin kaydı birebir eşleşiyor; eski/yeni kayıtların izi korunuyor.
- [ ] Pin verifier'a backup alanından bağımsız custody kaynağından sağlandı; adjacent sidecar pin yerine geçmedi.
- [ ] Hash, arşiv yapı/izin kontrolleri ve scratch restore-check sonuçları birbirinden ayrı değerlendirildi.
- [ ] Digest'in geldiği kanal/verifier provenance'ı kanıtlamıyorsa rapordaki `unverified` etiketi aynen korundu.

## İlişkili kanıt ve sınırlar

- [#565 bağımsız trust anchor kararı](backup-authenticity-trust-anchor-565.md): ilk MVP'de varsayılan `unverified`, aynı host/path ayrımının yetersizliği ve alternatiflerin maliyeti.
- [#616 expected-digest CLI sözleşmesi](backup-expected-digest-cli-616.md): pin biçimi, mismatch davranışı ve `caller_supplied_unverified` provenance.
- [#544 verify/restore-check sözleşmesi](backup-verify-restore-check-544.md): arşiv güvenlik kontrolleri ve scratch restore sınırı.
- [#617 operatör karar formu](release-operator-decision-form-617.md): release öncesi backup authenticity/custody kanıt alanı.
- `prototypes/backup-digest-pin/README.md`: sentetik fixture; fixture kendi pin'ini kendisi ürettiğinden gerçek custody kanıtı değildir.

Bu taslak gerçek backup, digest, pin kaydı veya custody medyası oluşturmaz; canlı verifier/restore/deployment çalıştırmaz. Yerel MVP'de ayrı, doğrulanmış hedef seçilmeden operasyonel pin tutmak için izin vermez.
