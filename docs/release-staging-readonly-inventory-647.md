# Yuva #647 — Release staging salt-okunur inventory prototipi

**Tarih:** 2026-10-23
**Durum:** CLI ve sentetik fixture hazır; revize sonrası tekrarlı çağrıda scandir fd sızıntısı kapatıldı. Tüm rapor kararları `HOLD`. Temizlik, resume/publish, chmod/chown ve pointer düzeltmesi yok.

## Kullanım

```sh
python3 release_staging_inventory.py --install-root <absolute-INSTALL_ROOT>
python3 release_staging_inventory.py --install-root <absolute-INSTALL_ROOT> --max-entries 128
```

`--install-root` zorunludur; ortam değişkeninden veya varsayılan dizinden kök türetilmez. Kök var olan absolute bir gerçek dizin olmalı; symlink component, `..` veya filesystem root reddedilir. Kök dizin raporda `<explicit-root-redacted>` ile gösterilir. Çıktı yalnız bounded doğrudan-child envanteri, güvenli release/staging identifier'ları ve `lstat` metadata'sı taşır. Canonical olmayan adları ve güvenilmeyen symlink target'larını rapora yazmaz.

Kök dizin component'leri `openat`/`O_NOFOLLOW` ile açılır; `releases` ve `manifests` dizinleri de file descriptor-relative ve no-follow açılır. Pointer metni `readlinkat` davranışıyla yalnız alınır, target canonical değilse içeriği atılır. Bu, inventory sırasında bir symlink'i çözerek root dışını taramayı önler; eşzamanlı installer/process state'ini kanıtlamaz.

## Sınıflandırma

| Gözlem | Rapor sınıfı | Karar |
|---|---|---|
| `.staging-<32 lowercase hex>` real directory | `STAGING_STATE_UNKNOWN` | `HOLD`; transaction aşaması bilinmiyor, içerik doğrulanmıyor |
| `.staging-*` symlink/yanlış tür veya metadata/process belirsizliği | `HOLD_UNKNOWN` | `HOLD`; target okunmaz |
| Tam release ID, manifest receipt yok | `PUBLISHED_RECEIPT_INCOMPLETE` | `HOLD` |
| Receipt metadata uygun, pointer `current`/`previous` ile eşleşiyor | `POINTER_REFERENCED` | `HOLD`; bağlı release korunur |
| Receipt metadata uygun, hiçbir canonical pointer bağlamıyor | `PUBLISHED_INACTIVE` | `HOLD`; inactive olması silme yetkisi değildir |
| Release/receipt owner-mode/tür/link/size tutarsız veya manifest dizini kullanılamıyor | `HOLD_UNKNOWN` | `HOLD` |
| Canonical olmayan releases/temp-pointer adı | Yalnız aggregate count | `HOLD`; ad/path raporlanmaz |

`.installer.lock` yalnız `lstat` edilir ve `present_uninspected` olarak raporlanır; aktif installer durumu daima `unknown` kalır. Lock dosyasının varlığı veya metadata yaşı process sahipliği kanıtı değildir. Bilinmeyen owner/process durumu her durumda `HOLD` bırakır.

Manifest receipt **okunmaz** veya doğrulanmış sayılmaz: rapor yalnız varlık ve metadata'yı `present_unverified` olarak kaydeder. Staging ağacı recursive gezilmez; payload içeriği, manifest metni, release dosya adı/path'i veya dışarı çıkan symlink hedefi raporlanmaz. Pointer symlink'i yalnız `readlink` ile okunur; target tam `releases/<canonical-id>` biçiminde değilse ham target gizlenip `unsafe_target` denir. `releases/` kendisi symlink/yanlış türse pointer hedefine metadata için dahi girilmez.

Her root ve `releases/` doğrudan dizin taraması `--max-entries` ile bounded (varsayılan 256, üst sınır 4096); aşım `truncated: true` olur. Bounded envanter tüm artifact'ların eksiksiz olduğuna dair kanıt değildir.

## Fixture ve değişmezlik kanıtı

`tests/test_release_staging_inventory.py` geçici `INSTALL_ROOT` kurar ve staging, receipt'siz final release, pointer-referenced release, inactive release, lock, yanlış pointer ve dış dizine bakan symlink senaryolarını sınar. Test öncesi/sonrası geçici ağacın dosya byte'ları, symlink target'ları ve mode'ları karşılaştırılır. Ayrıca secret manifest/payload içeriğinin, absolute root'un, canonical olmayan adların ve dış symlink yolunun JSON rapora çıkmadığı doğrulanır. Eksik root hata çıktısı da istenen absolute path'i yansıtmaz.

Çalıştırma: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_staging_inventory -v` — **7 test geçti**. Linux `/proc/self/fd` fixture'ı 40 ardışık inventory çağrısından önce/sonra descriptor sayısının sabit kaldığını doğrular. `py_compile` ve `git diff --check` başarılı.

## Güven sınırı

Bu bir envanter prototipidir; actual installer process/file-descriptor/cwd/mount incelemesi, external manifest/pin doğrulaması veya install invocation owner uzlaştırması yapmaz. Bu yüzden `STAGING_STATE_UNKNOWN`, `PUBLISHED_INACTIVE`, hatta pointer-referenced durumlar otomatik cleanup veya repair için onay değildir. Operasyonel kullanımda exact root ve host process owner kanıtı ayrıca release owner tarafından uzlaştırılmalıdır. #631 karar ağacındaki HOLD varsayılanını korur.
