# Panel GET snapshot allowlist ve redaction fixture'ı (#656)

`tests/test_panel_get_snapshot_acceptance.py` geçici bir `YUVA_DIR` ve
ephemeral localhost HTTP server ile gerçek `GET /api/veri` ve `GET /veri`
Handler yollarını sınar. Test Handler alt sınıfı `_gonder()` aşamasında
fixture global byte selector'ını çağırır ve sonucu parent Handler'ın wire
serializer'ına yollar. Bu sayede test edilen route response'unun kendisi
4096 byte sınırını, `Content-Length` eşleşmesini ve partial metadata'yı taşır;
selector artık GET cevabından sonra test tarafından ayrı çağrılmaz.

Fixture roster/task/event/message alan allowlist'lerini ve screen kayıt
şekillerini denetler; chat ve historical screen gövdelerinde bilinen Bearer
biçimli sentinelları redaksiyon öncesi/sonrası karşılaştırır. Ekstra
roster/task/message alanları snapshot'a taşınmamalı, secret sentinelları HTTP
body ve handler hata kaydında görünmemelidir. Selector spy'ı, Handler'ın
budget aşamasına verdiği projected snapshot'ta bilinen chat/provenance/screen
sentinellarının zaten redakte edildiğini ve redacted marker bulunduğunu
doğrular. Okuma fixture'ı kaynak JSONL dosyalarını değiştirmediğini de
kontrol eder.

Bilinen secret kalıpları mesaj/screen text'inden, serialization/budget
fixture'ına ulaşmadan önce redakte edilir. Message ve task projection'ları
yalnız panelin tükettiği alanları ve daraltılmış event/provenance alanlarını
döndürür. Redactor eşleşmesi gizlilik garantisi değildir; bilinmeyen sırların
tespiti veya kalıcı geçmişi düzeltme/migration iddiası taşımaz. Kaynak dosyalar
olduğu gibi kalır.

Selector `prototypes/panel_snapshot_budget` içinde fixture prototipidir ve
yalnız test Handler alt sınıfına bağlanmıştır; production `panel.server.H`
değiştirilmemiştir. Bu nedenle test gerçek GET route projeksiyonunu ve test
Handler'ının wire response'unu sınar, ancak canlı production `/api/veri`
yanıtının global olarak sınırlandığını kanıtlamaz; route'ın production byte
limitini etkinleştirme veya production yük kabulü değildir.

Fixture auth kapalı, cookiesiz/Authorization'sız GET'in başarılı olduğunu
ayrıca kaydeder. **Auth/session sonucu: NO-GO/unverified.** Alan allowlist'i ve
bilinen-pattern redaction **kısmi veri azaltımıdır**; görev, sohbet ve ekran
içeriğinin kapsamda kalması nedeniyle anonim GET'i güvenli yapmaz. #574'ün tam
anonim snapshot kararı **NO-GO** olarak kalır.

Çalıştırma: `python3 -m unittest tests.test_panel_get_snapshot_acceptance -v`.
Yalnız fixture TemporaryDirectory'i kullanılır; production service, gerçek
`YUVA_DIR` veya host state kullanılmaz.
