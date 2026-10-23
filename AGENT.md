# Yuva — ajan devir notu

Güncelleme: 2026-10-23 Europe/Istanbul

Bu dosya proje durumunu ve çalışma sınırlarını devralan ajanlara aktarır. Canlı sistemin durumu veya yayın onayı anlamına gelmez.

## Depolar ve çalışma alanları

- Geliştirme deposu: `/home/yucel-pc/yuva-v2`.
- Yuva'nın yerel çalışma/veri alanı: `/home/yucel-pc/yuva`; geliştirme deposuyla karıştırma. Yuva durumu ve görev tahtası `/home/yucel-pc/yuva/gorevler.json` içindedir.
- Bu inceleme dalı `yuva-review-tooling`, başlangıç HEAD'i `64ed896` (`feat: add isolated release and auth helper tooling`) ve `github/yuva-review-tooling` ile eşleşiyordu. Çalışma ağacında birikmiş teslim değişiklikleri vardı; her yeni düzenlemeden önce `git status` ile güncel durumu kontrol et.
- Proje girişi `README.md`, protokol `protokol.md`; panel kaynakları `panel/server.py` ve `panel/ui.html`; izole taslaklar `prototypes/`; teknik karar ve incelemeler `docs/` altındadır.

## Güncel durum

2026-10-21 tarihli Yuva tahtası kontrolünde #483, #487, #488, #491 ve #502 teslimleri statik inceleme sonrası onaylandı. Bu son kontrolün ardından tahtada 494 `verified`, 17 `dropped` ve denetim bekleyen teslim yoktu. Bu sayılar anlık görüntüdür; yeni oturumda tahtayı tekrar oku.

- **#483 — ekran snapshot sayfalama:** Leksikografik round-robin cursor yalnız gerçekten ele alınan son dosyaya ilerler; bütçe nedeniyle işlenmeyen sonraki dosyalar sonraki çağrılarda seçilebilir. Unicode/serialization hataları dosya başına atlanıp partial metadata'ya yansır. Map biçimi ve byte bütçeleri korunur.
- **#487/#488 — OpenCode HTTP/SSE adaptör ve uzlaştırma prototipi:** SSE yarım olayları EOF'ta atılır; yalnız açıkça eşleşen oturum durum olayları occupancy'yi etkiler. Gönderim sonucu belirsizse `unknown` kalır ve otomatik retry yapılmaz. Genel `version`/sequence alanları sıralama kanıtı değildir; dedupe geçmişi sınırlıdır. REST uzlaştırması salt okunur kalır.
- **#491 — köprü kaynak güveni:** Worker, sohbet ve araç çıktısı veri olarak kalır. Kanonik görev talimatı ancak pozitif görev kimliği ve doğrulanmış kayıt/session/workspace/assignee bağını taşıyorsa görev kapsamına alınır. Bu işlev tek başına eylem yetkisi vermez.
- **#502 — auth provisioning commit belirsizliği:** `FileExistsError` dışındaki `os.link` hataları, dosya sistemi türü doğrulanmadığı için `commit_unknown` kabul edilir. Otomatik readback, rollback veya retry yoktur.

Bu teslimler izole taslak/prototip kapsamındadır. Hedef OpenCode `/doc` şeması ve gerçek provider bağlantısı doğrulanmadı; canlı Yuva entegrasyonu, auth gate etkinleştirme, test ve runtime çalıştırma bu denetimlerde yapılmadı. `git diff --check` inceleme anında temizdi; bu, test veya yayın doğrulaması değildir.

## Ürün hedefi ve önceki tasarım çalışmaları

- Kullanıcı Yuva'yı, kullanıcının bir işi başdenetçiye vermesiyle başdenetçinin işi işçilere bölüp dağıttığı, teslimleri izlediği, gerektiğinde revize istediği ve kabul ettiği bir çalışma ortamı olarak tanımladı. Kullanıcı her alt görev için sohbete tekrar yazmak zorunda kalmamalı; sohbet başdenetçiye talimat girişidir, tahta kayıt ve denetim yüzeyidir. Bu otomasyon hedefi mevcut prototiplerin canlıda uygulandığı anlamına gelmez.
- Model mesajı ile gerçek terminal/provider oturumu arasında güvenli köprü ihtiyacı belirlendi. Gönderim belirsizliği yeniden deneme sayılmamalı; model/araç çıktısı kullanıcı talimatı veya yetki olarak yükseltilmemeli; insan onayı gerektiren provider izinleri ayrı kalmalı.
- Önizleme/harita çalışmasında sentetik veriyi canlı sistemden izole tutma; haritayı tam alan kullanabilen, sürüklenerek taşınabilen bir çalışma yüzeyi yapma; kişi hiyerarşisini başdenetçi → görevli/mühendis → işçi biçiminde gösterme; işçi kartından iş/durum ayrıntılarını açma hedefleri konuşuldu. Bağlantı çizgilerinin hangi kimliğe ait olduğu renk/ok ucu ve önde çizimle anlaşılır olmalı. Bunlar ürün/tasarım hedefleridir; uygulanmışlık düzeyi için `preview/` kaynaklarını ve ilgili teslimleri kontrol et.
- Linux yayın adayı ayrı bir çalışma noktasıdır; bu devir güncel canlı servis, deployment, GitHub push veya yayın onayı tespiti yapmıyor.

## Çalışma kuralları ve kullanıcı kararları

- Bu çalışma hattında kullanıcı Yuva başdenetçisinin kendisi olmasını; işleri işçilere dağıtmasını, teslimleri inceleyip revize/onaylamasını istedi. Görevli rolü kullanılmıyor. Ekipte çalışacak modellerin rolleri ve çevrimiçi durumu varsayılmamalı; canlı tahtadan doğrulanmalı.
- 2026-10-23 kullanıcı kararı: ilk yerel MVP'de UID ayırımı yok; tek yerel OS hesabı güvenilir sınır kabul ediliyor. Açık CLI/API task işlemlerinde model kimlikleri yalnız aktör etiketi; `actor_trust=local_unverified` korunmalı ve presence `unknown` kalmalı. Auth sonradan etkinleştirilirse HMAC principal kapısı geçerlidir.
- 2026-10-23 kullanıcı kuralı: Yuva'nın `sıradaki` kuyruğuna yeni görevler toplu eklendikten sonra, eklenen her görevin ne olduğunu ve ne işe yarayacağını açıklayan bir tabloyu kullanıcıya sun; kullanıcı inceleyebilsin. Bu kural sonraki görev ekleme işlemlerinde de geçerlidir.
- Yuva'da teslim onayı verilmeden iş tamamlandı diye raporlanmamalı. Yeni oturumda önce görev tahtasını ve sohbeti oku; çalışma ağacında başkalarının değişiklikleri olabileceği için her düzenlemeden önce `git status` kontrol et.
- İzole prototipleri canlı panele/provider'a bağlama, auth gate'i açma, test/runtime çalıştırma veya commit/push/yayın yapma; bunlar açıkça istenip kendi kapsamları incelenmeden yapılmamalı.
- Bu devirde Codex alt ajanı veya dış model görevlendirilmedi.

## Sonraki adım

Kullanıcı yeni bir iş istediğinde önce bu dosyayı, ilgili `docs/` inceleme/karar notlarını ve Yuva'nın güncel görev/mesaj durumunu oku. Bu incelemede yerel test runner Python 3.14 üzerinde 395 testi geçti; GitHub workflow'u Python 3.8 ve 3.15 runtime koşularını içeriyor. Gerçek Actions sonucu PR açıldıktan sonra kontrol edilmeli; yerel test sonucu GitHub CI başarısının yerine geçmez. Main'e merge veya branch protection değişikliği operatör kararıdır.
