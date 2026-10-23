# #648 — Yerel release karar formu doğrulayıcısı

`release_decision_form.py` doldurulmuş #617 Markdown formunu salt okunur
inceler. Örnek kullanım:

```sh
python3 release_decision_form.py path/to/filled-release-form.md
```

Araç JSON raporu verir. Form okunamıyorsa, zorunlu alan/kapı/kanıt/imza
eksikse, bir kapı PASS değilse, risk veya seçim çözümsüzse **NO-GO** döndürür
ve sıfır dışı çıkış kodu verir. `issues` alanı boşsa yalnız formun doldurulma
ve tutarlılık kontrolleri geçmiştir. Formdaki karar da açıkça GO seçilmiş
olmalıdır.

Biçim kontrolleri host/instance etiketinde boşluksuz, en çok 128 karakterlik
bir kimlik; release kimliğinde 40/64 karakterlik hex commit veya
64-hex SHA-256 (isteğe bağlı `sha256:` öneki) ya da
`<commit>-<sha256>` biçimini; değerlendirme tarihinde gerçek `YYYY-MM-DD`
veya ISO tarih-saatini; `INSTALL_ROOT` ve `YUVA_DIR` alanlarında mutlak yol
yazımını bekler. Kanıt paketi `<repo-relative/path>; YYYY-MM-DD` gibi bir
referans ve tarih içerir. Her PASS kapısının kanıt alanı
`<referans>; <sorumlu>; <YYYY-MM-DD>` biçiminde olmalıdır. Kanıt referansı
mutlak/relative yol, URI veya SHA-256 olabilir. Backup digest'i 64 hex
olmalı; backup makbuzları ve karar kaydı referans biçimine uymalıdır.
İmza satırları imzalayan metni ve ISO tarihi ister.

Bunlar yalnızca yazım/şekil kontrolleridir: yollar okunmaz veya çözülmez,
referanslar açılmaz, digest içerikle karşılaştırılmaz, imza sahibi
kimliklendirilmez ve kanıtın doğruluğu değerlendirilmez. Eksik, `UNKNOWN`,
çözümsüz veya biçimi geçersiz her alan NO-GO kalır. Sentetik fixture testi
biçim dallarını sınar; host kabul kanıtı oluşturmaz.

Bu araç metin beyanlarını, dosya yollarını, kanıt paketlerini, host/runtime
durumunu, imza kimliğini veya kanıtın gerçekliğini doğrulamaz. `GO` sonucu
`scope: local-form-completeness-only` ve `host_acceptance: not-verified`
alanlarıyla döner; host release onayı değildir. Formun kendisini değiştirmez.
