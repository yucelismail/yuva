# Yuva #737 — unittest boş discovery guard'ı

`python3 scripts/run_tests.py`, `tests/` altında `test_*.py` unittest keşfini
yürütür ve `TestSuite.countTestCases()` ile bulunan gerçek test case sayısını
çalıştırmadan önce kontrol eder. Sıfır testte kısa, mutlak path içermeyen hata
mesajı ve exit code `2` üretir. Discovery/import hatası `2`, başarısız test
sonucu `1`, başarılı ve en az bir test içeren suite `0` döndürür. Test çıktısı
unittest'in standart ayrıntılı runner'ından gelir.

Doğrulama: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
tests.test_test_runner -v` — iki test geçti. Boş ve tek testli suite'ler
geçici dizinlerde kuruldu; test runner tüm repo testlerini bu görevde
çalıştırmadı.

Bu yardımcı henüz workflow'a bağlanmadı; CI/local komut eşlemesi #736'nın
kapsamıdır. Gerçek data root, servis, socket veya dış ağ kullanmaz.
