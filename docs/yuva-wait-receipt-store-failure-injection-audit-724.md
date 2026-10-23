# Yuva wait receipt store failure-injection denetimi (#724)

**Tarih:** 2026-10-23
**Önkoşul:** #714 verified.
**Kapsam:** Yalnız #714 fixture store'u, sentetik `TemporaryDirectory`; production bağlantısı yok.

## Sonuç

`tests/test_yuva_wait_receipt_failure_injection_audit.py` dokuz bağımsız hata
enjeksiyonu/yarış senaryosu ekler. Bu modül ve temel store fixture'ı birlikte
**15/15 geçti**; `git diff --check` temiz. Testler arasında gözlenen kusurlar
bilinçli olarak mevcut davranışı kaydeder; bunlar sözleşme kabulü değildir.

## Bulgular

### Yüksek — duplicate kısa yolu cursor/restore çelişkisini gizliyor

`observe()` aynı consumer, epoch ve message ID için `prior_receipt` aramasını
current cursor karşılaştırmasından önce yapıyor (`receipt_store.py:451-461`).
Bu yüzden aynı ID farklı `expected_cursor` ile sunulunca `duplicate_observation`
dönüyor; #688 farklı cursor çelişkisi için `store_conflict` ve no-write bekliyor
(#688:61-62).

Aynı sıra eski, kendi içinde tutarlı store snapshot'ı restore edildiğinde de
önemli: dışarıda kalmış güncel cursor `message-2` iken ledger `message-1`'e
döndürülüp eski `message-1` replay edilirse sonuç `duplicate_observation`,
döndürülen cursor ise gerilemiş `message-1` oluyor. Restore sonrasında yeni ID
`cursor_conflict` alıyor; fakat duplicate shortcut caller'ın daha yeni cursor
kanıtını dikkate almıyor. Tek başına store ve caller state'i birlikte eski
backup'a dönmüşse dış anchor olmadığından rollback'in saptanamayacağı ayrıca
bilinen sınırlamadır (#688:67-70).

Kanıt: `test_same_message_id_with_changed_expected_cursor_is_currently_misclassified`
ve `test_restored_old_store_conflicts_for_new_id_but_duplicate_path_hides_rollback`.
Ledger bytes değişmiyor; sorun hatalı başarı sınıflaması ve cursor'ın geri
dönmüş değerinin duplicate sonucu olarak sunulmasıdır.

### Orta — kilit yeniden doğrulamasında hata flock FD'sini sızdırıyor

`_locked_root()` lock dosyasını açıp flock aldıktan sonra path `stat` ile FD
kimliğini yeniden doğruluyor (`receipt_store.py:259-276`). Bu doğrulama OSError
verince `_reject_fixture()` setup `try` bloğundan çıkıyor; FD cleanup'ını yapan
contextmanager `finally` bloğuna hiç ulaşılmıyor (`:277-283`). Enjekte edilen
hatanın ardından `/proc/self/fd` içinde lock FD kaldı ve ikinci nonblocking flock
`BlockingIOError` ile aynı lock'ın hâlâ tutulduğunu gösterdi. Süreçte sonraki
store çağrıları kilitte takılabilir.

Kanıt: `test_lock_path_revalidation_oserror_leaks_flocked_descriptor`. Test
yalnız kendi sızdırdığı sentetik fixture FD'sini kapatır; host dosyası veya
başka process etkilenmez.

### Düşük — receipt FD close hatası yutulup descriptor açık kalıyor

Append sonrası `os.close(fd)` hatası sessizce yutuluyor ve `recorded` dönülüyor
(`receipt_store.py:371-376`). Enjekte edilen hata öncesinde file `fsync`
başarılıydı; bu nedenle denetim commit'i belirsiz saymıyor, ancak FD'nin aynı
süreçte açık kaldığını doğruluyor. Uzun ömürlü consumer'da tekrarlanan close
hataları descriptor biriktirebilir.

Kanıt: `test_receipt_close_error_is_swallowed_and_leaves_fd_open`.

## Başarılı fail-closed / belirsizlik davranışları

- Yarım JSONL tail ve zincir içinde yinelenen message ID `store_corrupt` olur;
  okuma/ekleme mevcut baytları değiştirmez.
- Payload'ın kısmi `os.write` ardından hata vermesi `commit_unknown` üretir.
  Ardından bozuk tail `store_corrupt` ile durur; otomatik retry veya tail
  onarımı yoktur.
- Tam receipt write'ından sonra file fsync hatası `commit_unknown` üretir.
  Exact replay readback `duplicate_observation` döndürür ve satır sayısını
  artırmaz. İlk bootstrap'ta directory fsync belirsizliği de
  `commit_unknown`; exact bootstrap readback `duplicate_bootstrap` olur.
- İki consumer aynı message ID'yi eşzamanlı gözlediğinde lock altında iki ayrı
  `read_observed` satırı ve bağımsız cursor oluşur.
- Tüm receipt payload'larında `SYNTHETIC_BODY_MUST_NOT_PERSIST` yoktur; normal,
  belirsiz ve kısmi yazım senaryoları message body saklamaz.

Bu denetim `provider`, gerçek inbox, panel, agent runtime, task mutation veya
live `YUVA_DIR` kullanmadı. #714 prototipi üzerinde düzeltme yapmadı; iki
orta/yüksek önem bulgusu için ayrı düzeltme ve tekrar denetim gerekir.
