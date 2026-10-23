# #502 — provisioning hard-link commit durumu

`panel/auth_provision_draft.py` hard-link kurulumu çevresinde açık `commit_phase` geçişi kullanıyor. Faz `os.link()` çağrısından hemen önce `link_attempting` olur; çağrı başarıyla döndükten sonraki ilk işlem `installed` geçişidir. Bu iki nokta arasındaki `BaseException`, link kurulmadı varsayımına düşmez ve `commit_unknown` olur. Kurulumdan sonraki geçici ad silme veya dizin `fsync` kesintileri de `commit_unknown` kalır. Cleanup sırasında yeni bir `BaseException` belirsiz commit sonucunu değiştiremez; aynı sonucu bildirir.

`FileExistsError`, no-replace hard-link çağrısının hedefi kurmadığını gösterdiğinden `store_already_exists` olarak kalır. Auth root'un filesystem türü doğrulanmadığı için `FileExistsError` dışındaki her `os.link()` `OSError` sonucu `commit_unknown` olur; uzak filesystem'de hata yanıtı linkin kurulmadığını kanıtlamayabilir. Bu tutucu sınıflandırma bazı kesin başarısızlıkları da belirsiz sayabilir. Kod kurulum var/yok durumunu otomatik okumaz, dosyayı geri almaz ve yeniden deneme yapmaz; `commit_unknown` sonrasında operatör root'u çevrimdışı incelemelidir.

Bu, yalnız prototip düzeltmesi ve statik açıklamadır. Auth gate etkinleştirilmedi; test/runtime çalıştırılmadı.
