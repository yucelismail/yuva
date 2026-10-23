# Yuva #746 — CI locale ve timezone girdileri

İnceleme yalnız repo içindeki testler, test edilen panel kaynakları ve eski
panel fixture’ı üzerinde yapıldı. Testlerde locale API’si, locale sıralaması
veya tarih biçimine bağlı beklenen metin bulunmadı. Panel timestamp üretimi
`datetime.now().astimezone().isoformat(...)` ile yerel timezone’u kullanıyor;
değerlerin UTC dışındaki makinelerde farklı offset taşıması mümkün.

`.github/workflows/ci.yml` içindeki `unittest` job’una şu sabit girdiler
eklendi:

- `LANG=C.UTF-8` ve `LC_ALL=C.UTF-8`: UTF-8 C locale’i seçer.
- `TZ=UTC`: Python ve alt süreçlerin timezone yorumunu UTC’ye sabitler.

Bu ayarlar job kapsamındadır; discovery script’i, test kapsamı veya sistem saati
değiştirilmedi. Locale/timezone bağımlı assertion bulunmadığından ayrı bir test
eklenmedi; deterministik girdiler workflow konfigürasyonunda açıkça tutuluyor.
Workflow statik olarak incelendi, test çalıştırılmadı.
