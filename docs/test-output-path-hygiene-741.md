# Yuva #741 — test çıktılarında makineye özel yol denetimi

**Kapsam:** Yalnızca repo içindeki Python test ve fixture kaynaklarında sabit
kullanıcı home/data-root yolları ile bu yolları test hata çıktısına taşıyan
girdiler arandı. Secret dosyaları ve gerçek loglar okunmadı.

## Bulgular ve düzeltmeler

- `test_cli_copy_compatibility_fixture.py` ve
  `test_restore_check_cli_write_guard.py` tarihsel CLI kopyaları için sabit
  `/home/yucel-pc/...` kaynak yolları kullanıyordu. Gerekli CLI kaynakları
  `tests/fixtures/cli-copies/` altına alındı; testler artık yalnız repo içindeki
  bu sentetik snapshot’ları kullanıyor.
- `test_legacy_task_write_guard.py` eski CLI ve panel için `Path.home()/yuva`
  kullanıyor ve testleri kopyalar mevcut değilse sessizce atlıyordu. Test artık
  repo içindeki fixture kopyalarını doğrudan kullanıyor; panel importu ve CLI
  alt süreci `YUVA_DIR` ile `HOME` değerlerini geçici test köküne yönlendiriyor.
- Restore-check testindeki kaynak hash eşlemesi ve hata bağlamı mutlak `Path`
  yerine repo-köreli fixture adlarını kullanıyor. Copy-fixture testine kaynak
  dosyaların yalnız `tests/fixtures/cli-copies` altında olmasını doğrulayan
  regresyon eklendi.
- Test kaynaklarında `/home/yucel-pc`, `/home/yucel` ve kullanıcı adı taşıyan
  `/Users/...` eşleşmesi kalmadı. `/home/fixture/source` kullanan mevcut test
  değeri sentetik bir fixture etiketidir; kullanıcı veya gerçek data-root yolu
  değildir.

## Kontrol sınırı

Değiştirilen üç test modülü ve fixture panel kaynağı AST ile statik parse
edildi. Testler çalıştırılmadı. Repo köküne dayalı `ROOT` hesaplamaları doğal
olarak checkout konumunu kullanır; hata mesajlarında gösterilen fixture
kimlikleri göreli adlardır. Fixture panelinin `Path.home()` fallback’i yalnız
`YUVA_DIR` verilmediğinde seçilir; bu test panel modülünü yüklemeden önce iki
ortam değişkenini de sentetik köke ayarlar.
