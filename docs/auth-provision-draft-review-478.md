# #478 — Offline provisioning taslağı bağımsız kaynak incelemesi

## P2 — hard-link kurulumundaki asenkron hata commit belirsizliğini bildirmeyebilir

`panel/auth_provision_draft.py:204-217` içinde `installed = True`,
`os.link()` başarıyla döndükten sonra atanıyor; çevresindeki hata yönetimi yalnız
`OSError` yakalıyor. `os.link()` syscall'ı kurulumu yapıp Python kontrolü
`installed = True` satırına ulaşmadan bir `BaseException` (ör. `KeyboardInterrupt`)
gelirse bu yol `commit_unknown` üretmeden dışarı çıkar. `finally` geçici hard
link'i silmeyi dener; hedef snapshot kalmış olabilir, fakat dizin fsync henüz
yapılmamıştır. Çağıran, store'un kurulmuş ve dayanıklı olup olmadığına ilişkin
açık bir belirsizlik durumu alamaz.

Bu pencere `panel/auth_store_v2.py:432-462` içindeki `_atomic_replace()`
yaklaşımıyla farklıdır: mevcut store, replace syscall'ından önce fazı işaretler
ve syscall sırasında/sonrasında gelen `BaseException` için `CommitUnknown`
döndürür. Taslakta da hard-link öncesi bir commit fazı işaretlenmeli ve syscall
çevresindeki `BaseException` güvenli `commit_unknown` durumuna çevrilmelidir.
