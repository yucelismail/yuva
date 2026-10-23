# CI sonrası PR kabul kontrol listesi (#758)

- [ ] PR’ın son commit SHA’sını kontrol edin. `unittest` check’i **aynı SHA**
  için başarılı olmalı; eski commit’teki yeşil sonuç yeterli değildir.
- [ ] Aynı CI job’ındaki Python syntax kontrolü ve unittest suite adımlarının
  ikisi de tamamlanmış olmalı.
- [ ] Review yorumlarını okuyup yanıtlayın; çözümlenmemiş konuşma bırakmayın.
- [ ] Diff’i bir insan incelemeli ve proje/repo politikasının istediği onayı
  vermeli. CI kod incelemesinin yerini tutmaz.
- [ ] Son değişikliklerden sonra CI’ın yeniden çalıştığını ve son SHA’da hâlâ
  başarılı olduğunu doğrulayın.

Yeşil CI yalnızca o commit için otomatik kontrollerin geçtiğini gösterir; PR’ı
otomatik onaylamaz veya merge etmez. Merge kararı ve gerekli insan onayları
ayrı adımlardır.
