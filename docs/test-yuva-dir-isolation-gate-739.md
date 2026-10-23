# Yuva #739 — test data-root isolation gate

`scripts/run_tests.py` artık suite discovery başlamadan önce geçici bir
`YUVA_TEST_ROOT` oluşturur; `HOME` bu kökün altına, `YUVA_DIR` de
`$HOME/yuva` altına yöneltilir. Dizinler oluşturulurken `0700` modu istenir.
Bu environment test modülleri import edilirken ve suite çalışırken aktiftir;
aynı process'in başlattığı child process'ler de bu environment'ı devralır.
Önceki `HOME`, `YUVA_DIR` ve `YUVA_TEST_ROOT` değerleri runner tamamlandığında
geri yüklenir; temp root cleanup edilir.

`tests/test_test_runner.py` pozitif discovery fixture'ında test kodunun
`YUVA_DIR` kökünü temp `HOME`/`YUVA_TEST_ROOT` altında doğruladığını, alt
process'in aynı `YUVA_DIR` değerini aldığını ve runner'ın çağıranın environment
değerlerini geri yüklediğini sınar. Boş discovery regression'ı da aynı runner
üzerinden çalışır.

Odaklı doğrulama: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
tests.test_test_runner -v` — **2 test geçti**. Testler yalnız yeni geçici
dizinleri kullandı; tam suite bu görevde çalıştırılmadı.

Bu, varsayılan Yuva data-root seçimi ve runner üzerinden başlatılan child
process'ler için bir environment izolasyon kapısıdır. Test kodunda açıkça
hardcode edilmiş bağımsız bir mutlak path'i OS filesystem policy'si gibi
engellemez; test suite'in genel temporary-root denetimi #740'da sürer.
