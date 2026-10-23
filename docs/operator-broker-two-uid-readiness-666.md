# #666 — İki UID SO_PEERCRED koşusu öncesi readiness checklisti

**Amaç:** #649 disposable fixture'ını elle çalıştırmadan önce host/hesap/araç
önkoşullarını salt okunur kontrol etmek. Bu checklist koşucuyu başlatmaz,
UID/hesap/grup/servis/socket ACL/key oluşturmaz ve gerçek broker/host kabulü
üretmez.

## Güvenlik ve test kapsamı

#649 koşucusu root ister; önceden var olan, birbirinden farklı iki non-root UID
bulmalıdır. `setpriv` bu UID'lerle broker ve signer child process'lerini
çalıştırır. Fixture geçici `TemporaryDirectory` içinde AF_UNIX stream socket
açar; test socket'ini `0666` yapar ve root/broker dizinlerini değiştirir.
Koşu bitince geçici ağaç temizlenir. Bu nedenle koşu yalnız disposable,
izole ve operatörün açıkça onayladığı Linux hostta uygundur; paylaşılan,
production veya gerçek Yuva verisi/credential barındıran hostta **NO-GO**.

Fixture broker servisi, signer/auth key, HMAC, gerçek dispatch, production
socket policy, HTTP bypass veya writer kabulü değildir. `PASS` yalnız iki
synthetic peer-UID fixture senaryosuna aittir; `host_acceptance` yine
`not-verified` olur.

## Readiness kontrolleri

Komutlar sadece işletim sistemi, executable yolu, Python sabitleri ve passwd
hesap metadata'sını okur. UID değerlerini operatör önceden seçer; komutlar
hesap veya grup oluşturmaz/değiştirmez. UID'leri ve kullanıcı adlarını kanıt
raporuna eklemeyin; yalnız gerekli sayısal ayrım ve PASS/NO-GO sonucunu
kaydedin.

1. **Disposable host ve yetki (operatör beyanı)**
   - [ ] Host disposable VM/container veya açıkça onaylı izole staging host;
     geri dönüş/reset yöntemi ve bakım sahibi belli.
   - [ ] Gerçek Yuva `YUVA_DIR`, backup/archive/sidecar, production broker,
     canlı servis ve gerçek signer credential/key bu test ortamında yok.
   - [ ] Host üzerinde test socket'ine erişebilecek güvenilmeyen/başka kullanıcı
     iş yükü yok; koşunun kısa süreli world-accessible socket oluşturacağı
     kabul edildi.
   - [ ] Yetkili operatör root çalıştırmaya ve testin geçici dizinde yaptığı
     mode/owner değişikliklerine izin veriyor.
   - Koşul doğrulanamıyorsa: **NOT RUN / NO-GO**.

2. **Linux, root shell ve yardımcılar**

   Salt okunur kontroller:

   ```sh
   uname -s
   id -u
   command -v python3
   command -v setpriv
   ```

   - [ ] `uname -s` sonucu `Linux`.
   - [ ] Koşucuyu daha sonra başlatacak terminalin `id -u` sonucu `0`.
   - [ ] `python3` ve `setpriv` bulunuyor.
   - Başarısız/erişilemeyen kontrol: **NOT RUN / NO-GO**; sudo, paket kurma
     veya root yükseltmesi bu checklist içinde yapılmaz.

3. **Kernel/Python AF_UNIX ve SO_PEERCRED sembolleri**

   ```sh
   python3 -c 'import socket,sys; print({"linux":sys.platform=="linux","af_unix":hasattr(socket,"AF_UNIX"),"stream":hasattr(socket,"SOCK_STREAM"),"so_peercred":hasattr(socket,"SO_PEERCRED")})'
   ```

   - [ ] Dört değer de `true`.
   - Bu, Python ABI sembollerinin varlığını gösterir; gerçek kernel çağrısı,
     farklı UID credential teslimi veya production broker davranışı değildir.
   - Sembol yoksa: **NOT RUN / NO-GO**; alternatif platformla koşucuya devam
     etmeyin.

4. **Önceden var olan iki UID'nin salt okunur doğrulanması**

   Operatör iki sayısal UID seçip aşağıdaki alanları o değerlerle doldurur.
   Bu Python snippet'i yalnız `pwd` NSS/passwd kayıtlarını okur; kullanıcı adı
   yazdırmaz ve hesap/group oluşturmaz:

   ```sh
   BROKER_UID=2101 SIGNER_UID=2102 python3 -c 'import json,os,pwd
ids=[int(os.environ["BROKER_UID"]),int(os.environ["SIGNER_UID"])]
rows=[]
ok=True
for uid in ids:
    try:
        pwd.getpwuid(uid)
        row={"uid":uid,"exists":True,"non_root":uid>0}
    except KeyError:
        row={"uid":uid,"exists":False,"non_root":uid>0}
    rows.append(row)
    ok=ok and row["exists"] and row["non_root"]
ok=ok and ids[0]!=ids[1]
print(json.dumps({"decision":"PASS" if ok else "NO-GO","distinct_uids":ids[0]!=ids[1],"accounts":rows},sort_keys=True))'
   ```

   - [ ] İki kayıt da mevcut (`exists=true`), UID'ler non-root ve sayısal
     olarak farklı.
   - [ ] UID değerleri yanlışlıkla root, aynı değer, geçici/atanmamış hesap
     değil; testten sonra hesap silinmesine ihtiyaç yok.
   - UID eksik veya koşul belirsizse **NOT RUN / NO-GO**; bu işlem sırasında
     yeni UID/hesap/grup oluşturulmaz.

5. **Koşucu ve kaynak kimliği (salt okunur)**
   - [ ] #649 kaynağı beklenen checkout/release içinden incelendi; bu
     checklist hostta `two_uid_acceptance.py` çalıştırmaz.
   - [ ] Koşucuya verilecek UID'ler iki doğrulanmış mevcut UID ile aynı.
   - [ ] Fixture sonucu canlı broker/host GO, auth veya dispatch izni olarak
     yorumlanmayacak.

## Son karar

| Readiness durumu | Karar |
|---|---|
| Tüm host beyanları ve salt okunur kontroller PASS | Operatör ayrı bir adımda #649 koşucusunu **manuel** başlatmayı değerlendirebilir; bu checklist koşuyu başlatmaz. |
| Herhangi bir koşul NO-GO, eksik veya belirsiz | **NOT RUN / NO-GO**. Provisioning yaparak açığı kapatmayın; uygun disposable host ve mevcut UID'ler sağlanana kadar durun. |

Checklist sonucu: `PASS / NOT RUN / NO-GO`
Host/change id:
UID ilişkisi (yalnız numeric): `broker UID != signer UID`
Operatör ve tarih:
Koşucu başlatıldı mı? `Hayır` (readiness checklist sonucu olarak)

Readiness PASS, fixture PASS veya host acceptance değildir. Gerçek broker,
signer key custody, socket owner/mode/ACL, route policy, legacy HTTP bypass,
downstream writer ve service lifecycle için [#637 host kabul runbook'u](operator-broker-separate-uid-host-acceptance-637.md)
ayrı kalır.

## İlgili kaynaklar

- [#649 iki UID koşucusu](operator-broker-two-uid-fixture-649.md)
- [#637 ayrı UID host kabul/geri alma runbook'u](operator-broker-separate-uid-host-acceptance-637.md)
