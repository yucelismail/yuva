# Yerel panel önizlemesi

Bu araç, aday `panel/ui.html` dosyasını salt-okunur sunar ve panelin `/api/veri`
isteğine `fixture.json` içindeki sentetik veriyi döndürür. Gerçek Yuva sunucusunu,
servisini veya veri klasörünü kullanmaz.

Proje kökünde çalıştırın:

```bash
python3 preview/server.py
```

Tarayıcıda <http://127.0.0.1:8687/> adresini açın. Port doluysa başka bir yerel
port belirtilebilir:

```bash
python3 preview/server.py --port 8690
```

Sunucuyu durdurmak için çalıştığı terminalde `Ctrl+C` tuşlayın. Sunucu yalnızca
`127.0.0.1` adresine bağlanır; `GET /` panel HTML'ini, `GET /api/veri` statik
fixture JSON'ını sunar. Panelin üstünde `Salt okunur örnek önizleme · veriler
sentetiktir` etiketi görünür; bu etiket sunulan HTML'e eklenir, kaynak dosya
değiştirilmez. Diğer GET yolları reddedilir. POST, PUT, PATCH, DELETE, OPTIONS
ve desteklenmeyen metotlar HTTP 405, `Allow: GET` ve `ok: false` içeren JSON
yanıtı döndürür; önizleme hiçbir değişikliği kaydetmez.
