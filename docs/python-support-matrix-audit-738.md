# Yuva #738 — Python destek aralığı ve CI matrisi incelemesi

**Tarih:** 2026-10-23
**Kapsam:** README’deki Python 3.8+ iddiası, kaynak/test sözdizimi ve bulunan
standart kütüphane kullanımlarının statik karşılaştırması. Bu görevde test
çalıştırılmadı; Python 3.8 yorumlayıcısı bu ortamda kurulu değil.

## Bulgular

- Depodaki 123 Python dosyası güncel yorumlayıcının AST parser’ı ile
  `feature_version=(3, 8)` kullanılarak tarandı. **Python 3.8 dilbilgisi
  hatası bulunmadı.** Bu sonuç yalnız sözdizimi kontrolüdür; kodun Python 3.8
  üzerinde import veya çalışma kanıtı değildir.
- Bir test, [`tests/test_release_manifest.py:230`](../tests/test_release_manifest.py)
  satırında `digest.removeprefix("sha256:")` çağırıyor. `str.removeprefix`
  Python 3.9’da eklendiğinden bu test Python 3.8’de `AttributeError` verir.
  README’deki 3.8+ iddiası bu nedenle mevcut tam unittest suite’i için henüz
  doğrulanmış değil. ([Python `str.removeprefix` dokümantasyonu](https://docs.python.org/3.15/library/stdtypes.html#str.removeprefix))
- `Path.unlink(missing_ok=True)` testlerde ve uygulama kodunda kullanılıyor;
  bu parametre Python 3.8’de eklendi ve bildirilen minimumla uyumlu.
  ([Python `pathlib` dokümantasyonu](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.unlink))
- `|` union anotasyonları ve `list[str]`/`dict[str, …]` gibi anotasyonlar
  kullanılan modüllerde `from __future__ import annotations` mevcut; taramada
  bu tip ifadeleri gelecekteki anotasyon değerlendirmesi olmadan kullanan
  modül bulunmadı. Bu bulgu tek başına 3.8 çalışma zamanı uyumluluğunu
  kanıtlamaz.
- `os.stat`/`os.chmod` ve `DirEntry.stat` için `follow_symlinks` kullanımları
  envanterlendi; bulunan kullanımlarda 3.8’den yeni bir API eşiği görülmedi.
  Kontrol statik tarama ve kaynak okumasıdır, tüm davranışların sürüm bazında
  çalıştırılarak doğrulanması değildir.

## Sürüm desteği ve öneri

Python Developer’s Guide’a göre Python 3.8, 2024-10-07’de; Python 3.10 ise
2026-10-01’de yaşam sonuna ulaştı. 2026-10-23 itibarıyla upstream tarafından
desteklenen en eski seri 3.11’dir. Python.org, güncel kararlı sürümü
3.15.1 olarak listeliyor ([sürüm destek durumu](https://devguide.python.org/versions/),
[Python 3.15.1](https://www.python.org/downloads/release/python-3151/)).

README iddiası bu incelemede değiştirilmedi. Bakım politikası kararı için iki
açık seçenek var:

1. **3.8+ iddiasını koru:** Önce `removeprefix` kullanımını 3.8 uyumlu hale
   getir; sonra gerçek Python 3.8 ve 3.15.1 üzerinde suite’i çalıştır. CI
   matrisi adayı `[3.8, 3.15]` olur. Python 3.8 upstream güvenlik desteği
   almıyor.
2. **Yalnız upstream destekli sürümleri hedefle:** Minimumu açık bir maintainer
   kararıyla 3.11’e yükselt, README’yi aynı kararla güncelle ve CI’da
   `[3.11, 3.15]` kullan. Bu seçenek mevcut 3.8+ iddiasını sessizce geçersiz
   kılmamalı.

Bu görev karar veya uygulama görevi değildir; `.github/workflows/ci.yml` ve
README sürüm gereksinimi değiştirilmedi. Mevcut workflow tek Python 3.12 job’u
olarak kalır; matrise geçiş, destek politikasının seçilmesi ve sürüm başına
çalıştırma kanıtı gerektirir.
