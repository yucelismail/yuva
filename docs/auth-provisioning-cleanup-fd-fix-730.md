# #730 — Auth provision cleanup FD sızıntısı düzeltmesi

`panel/auth_provision_draft.py` içindeki
`provision_empty_store_with_receipt()` cleanup bloğu unlock, lock-fd close ve
root-fd close adımlarını bağımsız dener. `LOCK_UN` `OSError` üretse bile iki FD
kapatılır. Cleanup hatası normal dönüşte yine raporlanır; daha önce oluşmuş
`ProvisionError("commit_unknown")` gibi işlem hatasını gölgelemez.

Yeni disposable negatif fixture’lar:

- Yalnız provision lock `LOCK_UN` çağrısında sentetik `OSError`: `fd_delta=0`,
  receipt `committed` kalır; exact operation retry `replayed` verir ve store ile
  receipt byte’ları değişmez.
- Store directory `fsync` hatası ile eşzamanlı sentetik provision `LOCK_UN`
  hatası: çağrı `commit_unknown` olarak kalır, `fd_delta=0`; sonraki exact retry
  yine `commit_unknown` verir ve store/receipt byte’ları değişmez.

Test komutu:

`PYTHONPATH=panel:. PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_auth_provision_threat_model tests.test_auth_provision_cli -v`

Sonuç: **12 test geçti.** Yalnız `TemporaryDirectory` ve sentetik boş store
kullanıldı; gerçek key, auth store, host veya canlı `YUVA_DIR` kullanılmadı.
