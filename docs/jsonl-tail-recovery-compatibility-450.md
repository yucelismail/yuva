# JSONL kuyruk kurtarma uyum matrisi (#450)

Bu not, `docs/jsonl-tail-recovery.md` içindeki hedef sözleşmeyi mevcut `bin/yuva`
ve `panel/server.py` davranışıyla karşılaştırır. Salt-okunur kaynak incelemesidir;
mevcut programların kurtarma sözleşmesini uyguladığı anlamına gelmez.

## Kısa bulgu

CLI ve panel aynı geriye doğru, bütçeli `jsonl_tail_satirlari()` algoritmasını
kullanıyor. Her iki okuyucu da yalnız LF ile sonlandırılmış satırları döndürüyor;
sonunda LF olmayan kuyruğu sessizce atıyor, satırları UTF-8 `errors="replace"`
ile çözüyor ve JSON parse hatalarını üst seviyede atlıyor. Böylece hedef
sözleşmedeki `degraded` uyarısı ve bozuk kayıt konumu bugün sunulmuyor. Okuma
limitleri mesaj ve ekran uçlarında farklı miktar seçse de aynı tipteki dosya
için kuyruk işleme kuralı aynıdır.

Yazıcılar aynı `.kilit` flock'u altında sıralanıyor ve payload'ın tamamını
yazmak için kısa yazmaları döngüyle tamamlamaya çalışıyor. Fakat append öncesi
mevcut dosyanın son LF'sini veya bütünlüğünü taramıyorlar; JSONL append'te
açık `fsync` de yok. Dolayısıyla yeni kayıt, önceki kısmi kuyruğa eklenebilir;
kilit tek başına okuyucu tutarlılığı, kesinti atomikliği veya güç kesintisine
karşı kalıcılık garantisi değildir.

## Senaryo matrisi

| Senaryo | Mevcut CLI (`bin/yuva`) | Mevcut panel (`panel/server.py`) | `docs/jsonl-tail-recovery.md` hedefi / uyum |
|---|---|---|---|
| Tam LF'li, geçerli JSON satırları | Kuyruk okuyucu satırları verir. Mesaj okuyucusu JSON nesnesi olmayanları atlar; geçerli nesneleri görünümde normalize edebilir. Sağlık/integrity bayrağı yok. | Aynı kuyruk kuralı. `/api/veri` mesaj ve ekran kayıtlarını döndürür; sağlık bayrağı yok. | Hedef `healthy` ve bütünlük durumunun açık dönmesidir. CLI ve panel kayıtları göstermeye yakın, fakat `healthy` kanıtı/etiketi vermediğinden hedefle kısmi uyumlu. |
| LF'siz, JSON'u geçerli veya geçersiz son kuyruk | Son LF'den sonraki baytlar `jsonl_tail_satirlari()` içinde kesilerek sonuçtan çıkarılır. Önceki tam satırlar varsa normal görünür; yoksa boş liste/çıktı oluşabilir. Append bu kuyruk denetimini yapmadığından yeni payload eski baytlarla birleşebilir. | Aynı kuyruk sessizce atılır. Mesaj API'si öncekileri normal döndürebilir; ekran görünümünde de uyarı yoktur. Sonraki append öncesi kuyruk onarılmaz. | Hedef kuyruğu tamamlanmış kayıt saymamak, `degraded` ve offset alarmı göstermek, ham veriyi korumak ve aynı dosyaya append'i durdurmaktır. İki okuyucu da uyarı/offset eksik; iki yazıcı da append durdurmadığı için uyumsuz. |
| LF ile biten bozuk orta satır (JSON/UTF-8/şema) | JSON parse edilemeyen satır atlanır. Geçersiz UTF-8 önce replacement karakterlerine çevrilir; sonuç bazen parse edilir, bazen sonra atılır. Mesaj nesnesi/şeması sorunları sessizce eski/unknown zarfa normalize edilebilir. Bütünlük alarmı yok. | Mesaj okuyucusu parse hatasını atlar; legacy/kısmen hatalı provenance'ı görünümde unknown/unverified zarfa alabilir. Ekran JSON parse hatasını atlar. Bütünlük alarmı yok. | Hedef bozuk tam satırın konumuyla `degraded` raporlanması ve otomatik atlanmamasıdır. CLI/panel sessiz atlama veya görünüm normalizasyonu nedeniyle hedefle uyumsuz. Yazıcılar bozuk dosyada da append eder. |
| İzin/okuma hatası | CLI okuma hatası `OSError` olarak ana komutta yakalanıp stderr'e yazılır ve çıkış kodu 2 olur; başarı/boş çıktı gibi sunulmaz. Append tarafı sahiplik/tür/mod/link kontrollerinde veya OS hatasında reddedilir; kilit ve dosya hataları görünür `VeriHatasi`/`OSError` olur. | Mesaj okuyucusu JSONL okuma hatasını yakalayıp `[]` döndürür; ekran okuyucusu dosya hatasını yakalayıp ilgili dosyayı sonuçtan çıkarır. API bu yolda eksik/boş veri yanıtı üretebilir. Append hatası güvenli dosya kontrolleri veya `DurumHatasi` ile reddedilir; POST yanıtı hata statüsüne çevrilir. | Hedef okuyucunun sağlıklı/boş sonucu gibi davranmaması ve hata durumunu açık vermesidir. CLI okuma hatası bu hedefe daha yakın; panelde hata sessizce boş/eksik görünüme dönüşebilir. Yazma tarafındaki güvenli yol/izin reddi fail-closed; bu, JSONL kuyruğunun bozuk olup olmadığını taradığı anlamına gelmez. |
| Eşzamanlı append | JSONL yazıcısı `.kilit` flock'u alır; CLI ve panel aynı kilidi kullanır. İzin verilen süreçlerin append çağrıları birbirine göre sıralanır. Okuyucu aynı kilidi almadığından append sırasında dosyayı okuyabilir. | Aynı flock ile yazma sırası CLI ile ortaktır. Kuyruk okuyucusu kilitsizdir; başlangıç boyutu üzerinden geriye doğru okuyup boyut değişikliği/eksik chunk'ı hata sayabilir. Mesaj/ekran okuyucuları bu hatayı yakalayıp boş/eksik sonuç verebilir. | Hedef bütünlük kontrolü ve append'in aynı kilit içinde olmasını; kilit/okuma sorununun açık raporlanmasını ister. Mevcut yazıcılar kilitli append sağlar ama append öncesi tail taraması yoktur; okuyucular kilitsizdir. Kısmi yazma/kesinti otomatik `commit_unknown` olarak raporlanmıyor. |

## Limitler ve yorumlama

- Mesaj kuyruğu iki tarafta en çok 2 MiB tarar; bir satır için üst sınır 64
  KiB'dir. CLI isteği en çok 400 mesaja kadar alır ve `n*3` satır inceler;
  panel `/api/veri` için varsayılan üst sınır 200 mesajdır ve `n*3` satır
  inceler.
- Ekran kuyruğu iki tarafta 1 MiB tarar ve satır başına 16 KiB sınırı uygular;
  CLI bir çağrıda en çok 60 satır gösterir, panel model başına 60 satıra kadar
  alır.
- Limit dışındaki eski satırlar veya çok uzun satırlar kurtarıldı/bozuk diye
  ayrıştırılmaz; kuyruk görünümünde yer almayabilir. Bu API/CLI çıktısı tam
  arşiv bütünlüğü denetimi değildir.
- Her iki yazıcı UTF-8 JSON artı LF payload üretir ve kısa `write` sonuçlarını
  döngüyle ilerletir. Döngü ortasında kalıcı OS hatası olursa kısmi baytlar
  dosyada kalabilir; yazıcı bunları geri almaz. Sonraki append önceki son LF'yi
  kontrol etmediği için iki kayıt birbirine bitişebilir.
- `flock` katılan yazıcıları sıraya koyar. Harici/uyumsuz yazıcıyı, salt-okunur
  okuyucuyu veya güç kesintisini kapsamaz. JSONL append kodunda açık `fsync`
  olmadığı için normal dönüş kalıcılık kanıtı sayılmamalıdır.

## Hedefe geçişte gerekli uyum noktaları

`docs/jsonl-tail-recovery.md` içindeki hedef, mevcut davranışın tarifi değil
tasarım sözleşmesidir. Uyum için en azından CLI ve panelin aynı sınıflandırma
sonucunu üretmesi gerekir: tam satır bozukluğu, geçerli/geçersiz LF'siz kuyruk,
offset ve dosya; güvenilir prefix'in kısmi görünüm olduğu; yazıcının kuyruk
temizliğini kilit altındaki append öncesi denetlemesi; izin/kilit/okuma hatasının
normal boş başarıya çevrilmemesi. Bu görevde kod/test/runtime çalıştırılmadı.

## Kaynak eşlemesi

- Hedef kurtarma sözleşmesi: `docs/jsonl-tail-recovery.md`.
- Ortak CLI kuyruk okuyucu ve mesaj görünümü: `bin/yuva` içindeki
  `_jsonl_tail_satirlari()` ve `mesajlar()`.
- CLI ekran okuyucu ve append yazıcı: `bin/yuva` içindeki `cmd_ekran_oku()` ve
  `ekle_jsonl()`.
- Panel kuyruk okuyucu ve mesaj/ekran görünümleri: `panel/server.py` içindeki
  `jsonl_tail_satirlari()`, `mesajlar()`, `tum_ekranlar()`.
- Panel append yazıcı ve API hata yolu: `panel/server.py` içindeki `ekle()` ve
  POST handler.
- Paylaşılan kilit: CLI `kilit_tut()`; panel `dosya_kilidi`.
