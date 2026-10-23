# Yuva #481 — İnceleme beklerken görev değiştirme durum sözleşmesi

Kapsam: İşçinin teslim edilmiş işi inceleme beklerken bağımsız göreve geçmesi, revizyon önceliği, eşzamanlı görev üstlenme, bağlı görev ve kullanıcıya gösterilen durumlar. Bu belge politika önerisidir; CLI davranışını değiştirmez. Kod değiştirilmedi, test veya runtime çalıştırılmadı.

## Önerilen sözleşme

Bir işçinin aynı anda en fazla bir **aktif yürütme görevi** olmalı. Teslim edilmiş ve inceleme sırasındaki işler aktif yürütme sayılmaz; sonuç kararı beklerken işçi bağımsız bir `pending` görevi üstlenebilir. İnceleme kuyruğundaki teslim, tamamlanmış veya onaylanmış sayılmaz.

| Kalıcı görev durumu | İşçinin yapacağı | Kullanıcıya gösterilecek anlam |
| --- | --- | --- |
| `pending` | Üstlenilebilir; üstlenince yürütmeye başlar. | Atama bekliyor. |
| `assigned` | Kayıtlı assignee yürütür. Yeni bağımsız işe geçmeden önce mevcut işi bitirip teslim etmeli veya durumu ve devam planını açıkça kaydetmelidir. | Atanmış/çalışmaya hazır; bu durum tek başına o anda çalışıldığını kanıtlamaz. |
| `pending_gorevli_review` | İlk kontrol beklerken bağımsız işe geçilebilir. | Teslim edildi, görevli ilk kontrolü bekliyor; henüz onay değil. |
| `pending_verification` | Denetim beklerken bağımsız işe geçilebilir. | Teslim edildi, denetim kararı bekliyor; henüz onay değil. |
| `pending_revision` | Aynı assignee düzeltmeyi önceliklendirir ve `yuva gorev al <id>` ile yeniden `assigned` yapar. | Revizyon istendi; sıradaki iş mevcut görevin düzeltmesidir. |
| `verified` / `dropped` | Bu görevde yürütme yoktur. | Onaylandı / iptal edildi; terminal durum. |
| Tanınmayan durum veya sonucu belirsiz işlem | Durumu varsayma, yeni claim/teslim işlemiyle üstüne yazma. Önce kanonik görev kaydını ve varsa işlem sonucunu oku. | Bilinmeyen/sonuç doğrulanıyor; son teyitli durum ayrıca gösterilir. |

### Geçiş kuralları

1. **İnceleme beklerken:** Görev `pending_gorevli_review` veya `pending_verification` durumuna kalıcı biçimde geçtikten sonra assignee bir bağımsız `pending` işi üstlenebilir. İnceleme kararı gelene kadar ilk iş “teslim edildi, inceleme bekliyor” olarak kalır.
2. **Revizyon gelince:** `pending_revision` görevi assignee'nin önceliğidir. İşçi başka bir işi yürütüyorsa güvenli bir durak noktasında onu bırakır; Yuva'da duraklatma durumu olmadığı için mevcut `assigned` işin gerçek ilerleme bilgisini kullanıcıya bildirir ve yeni görev claim etmez. Ardından revizyonu `al` ile yeniden açar. Revizyon aynı assignee'de kalır.
3. **Çift claim:** Aynı görev için yarışan `al` çağrılarından yalnız geçerli ilk geçiş kazanır. Kaybeden, hata aldıysa görevi yeniden okumadan başka kimliğe atama veya tekrar deneme yapmaz. Farklı görevler ayrı ayrı claim edilebilir; mevcut CLI bunu engellemez. Önerilen tek aktif yürütme sınırını worker/panel veya ileride eklenecek koordinasyon kuralı uygulatmalıdır.
4. **Bağımlı işler:** `ust_gorev_id` yalnız üst/alt görev ilişkisini belirtir; tek başına önkoşul veya blokaj değildir. Gerçek bir önkoşul varsa çocuk görev önkoşul kabul edilene kadar çalıştırılmamalıdır. Mevcut CLI'de `blocked` durumu ya da bağımlılık geçiş denetimi yoktur. Bu desteklenene kadar çocuk `pending` bırakılmalı ve engel görev notunda açıkça belirtilmelidir; `al` ile yürütmeye alınmamalıdır.
5. **Belirsiz sonuç ve bildirim:** Görev kaydı durumun kaynağıdır; mesajın görünmemesi geçişin olmadığını kanıtlamaz. CLI önce görev durumunu kaydedip bildirimi ayrı yazabilir. İşlem hata döndürürse tahtayı/kanonik kaydı okuyup sonucu doğrulamadan aynı değişikliği körlemesine tekrarlama.

## Kullanıcıya durum sunumu

Her görünüm en az görev ID'sini, kanonik `durum` değerini, assignee'yi ve son kalıcı güncelleme zamanını göstermeli. İnsan tarafından okunur açıklama bu kayda bağlı olmalı:

- `assigned`: “Atandı” (aktif çalışıyor iddiası değil).
- `pending_gorevli_review` / `pending_verification`: “Teslim edildi, inceleme bekliyor”.
- `pending_revision`: “Revizyon istendi, assignee'nin önceliğinde”.
- Önkoşul tamamlanmamışsa: kanonik durum `pending` olarak kalır; ek açıklama “önkoşul nedeniyle bekliyor” der. Bu ifade mevcut CLI'de ayrı bir durum değildir.
- Okuma/yazma sonucu doğrulanamıyorsa: “Sonuç belirsiz; doğrulama sürüyor” ve son teyitli durum gösterilir. Bunu görev JSON'una yeni bir durum olarak yazmak mevcut sözleşmenin parçası değildir.
- `verified`: yalnız denetçi açıkça onayladığında gösterilir. Teslim veya görevli ilk kontrolü tek başına nihai onay değildir.

## Mevcut CLI ile farklar

- `gorev al`, yalnız `pending` veya `pending_revision` durumlarını `assigned` yapar. Atanmış görevde `al` gerekmez; `assigned` görevi kayıtlı assignee yürütür. `al` geçişi görev kilidi altında yapıldığından aynı görevde yarışan claim'ler seri hâle gelir.
- Kilit görev bazındadır; farklı görevler arasında tek-aktif-görev sınırı yoktur. Aynı worker birden fazla `assigned` görev tutabilir.
- Teslim `assigned` durumundan, görevli varsa `pending_gorevli_review`, yoksa `pending_verification` durumuna geçer. Bunlar inceleme kuyruklarıdır; nihai onay değildir.
- `pending_revision`, aynı assignee'de kalır; yeniden çalıştırmak için `al` ile `assigned` durumuna dönmek gerekir.
- `verified` ve `dropped` terminaldir. Bilinmeyen bir durum için geçerli görev geçişi tanımlı değildir; tahta bunu ham/bilinmeyen durum olarak gösterebilir.
- `ust_gorev_id` doğrulaması parent varlığı/tekilliği ve döngüyü kapsar; bağımlılık hazır olma koşulunu uygulamaz.
- Görev durumu ve mesaj bildirimi ayrı yazılır. Görev kaydı ilerlemişken mesaj eksik kalabilir; bu nedenle mesaj akışı görev tahtasının yerini tutmaz.

Bu farklar nedeniyle önerilen tek aktif yürütme sınırı, açık blokaj ve belirsiz işlem sonucu sunumu bugünkü CLI'nin otomatik garantileri değildir; politika/arayüz katmanında uygulanmalı veya CLI'ye ayrıca eklenmelidir.
