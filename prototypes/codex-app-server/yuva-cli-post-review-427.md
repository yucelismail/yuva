# Yuva #427 — CLI POST sonucu statik güvenlik incelemesi

Kapsam: `bin/yuva` içindeki #423 POST sınıflandırması ve `cmd_yaz` / `cmd_ekran` çağrıları. Yalnız statik diff ve ilgili akışlar incelendi; kod değiştirilmedi, test veya runtime çalıştırılmadı.

## Bulgular

### Orta — POST yanıtındaki truthy, boolean olmayan `ok` başarı sayılıyor

`bin/yuva:1254` ve `bin/yuva:1445` başarıyı `cevap.get("ok")` değerinin truthy olmasına bağlıyor. Örneğin HTTP 200 ile gelen `{"ok":"false"}` veya `{"ok":1}` başarılı POST gibi kabul edilip komut sessizce dönüyor. Bu, bozuk/uyumsuz bir yanıtın başarı olarak raporlanmasına yol açabilir. Başarı alanının tam olarak JSON `true` olması doğrulanmalı.

## Kontrol edilen durumlar

- **Gönderim öncesi, sıfır-byte kanıtı:** İstek/gövde oluşturma hataları taşıma çağrısından önce yakalanıp `not_sent` olur. Taşıma aşamasında yalnız DNS çözümleme (`socket.gaierror`) ve bağlantı reddi (`ConnectionRefusedError`) `not_sent` sayılıyor; bu hatalarda HTTP isteği bir eşe ulaşamaz. Bu sınıflandırma, POST yönlendirmelerinin kapatılmasıyla korunmuş.
- **HTTP 401/403 ve diğer HTTP hata yanıtları:** `HTTPError` kolu `http_status` ve `http_response` döndürüyor. `cmd_yaz` ile `cmd_ekran` HTTP yanıtında hata veriyor; yerel ekleme/fallback çalışmıyor.
- **Gönderim sonrası timeout/reset/okuma veya JSON çözümleme hatası:** Sıfır-byte kanıtı bulunmadığı için `unknown` olarak kalıyor. Her iki çağıran da yerel kayıt yapmadan hata veriyor; otomatik tekrar gönderme görünmüyor.
- **Yerel fallback ve çift ekleme:** `mesaj_ekle` / ekran JSONL eklemesi sadece `not_sent` dalında. `unknown` ve HTTP yanıtı dalları append yapmıyor.

## İncelenen konumlar

- `bin/yuva:421-432` — gönderilmedi kanıtı
- `bin/yuva:435-480` — HTTP POST sınıflandırması ve redirect engeli
- `bin/yuva:1252-1265` — ekran POST ve yerel fallback
- `bin/yuva:1441-1454` — mesaj POST ve yerel fallback
