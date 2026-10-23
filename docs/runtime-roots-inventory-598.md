# Yuva #598 — Salt-okunur çalışma kökleri envanteri

**Gözlem tarihi:** 2026-10-23 (Europe/Istanbul)
**Kapsam:** User systemd panel unit'i, PATH CLI, panel kaynak yolu, süreç
argv/cwd görünürlüğü, veri kökü ve bilinen eski kod kopyaları.
**Sınır:** Servis, symlink, kod veya veri değiştirilmedi; canlı panel başlatılmadı.

## Sonuç

PATH CLI ile user unit'in panel kaynağı aynı `<REPO_ROOT>`
çalışma ağacına çözülüyor ve unit'in `YUVA_DIR` değeri gerçek
`<YUVA_DATA_ROOT>` veri dizinine çözülüyor. Ancak bu, sabit/kurulu release
değil, kullanıcı tarafından değiştirilebilir geliştirme ağacıdır:
`<HOME>/.local/opt/yuva` ve `current` release pointer'ı yoktur.
Dolayısıyla CLI/panel kaynakları kendi aralarında hizalı olsa da **kurulu
release kabulü NO-GO**; manifest/hash ile doğrulanmış release veya immutable
current hedefi yoktur.

User unit `inactive/dead`, `MainPID=0` durumundadır. Salt-okunur görünür süreç
envanterinde `bin/yuva` veya `panel/server.py` çalıştıran süreç bulunmadı.
Bu nedenle aktif süreç argv/cwd'si doğrulanamadı; unit'teki `ExecStart` ve
`WorkingDirectory` yalnızca tanımlı yapılandırmayı gösterir, çalışan süreci
kanıtlamaz. Gözlem anındaki durum servisi yeniden başlatmaz veya durdurmaz.

## Unit ve kök eşleşmesi

| Alan | Gözlenen değer |
|---|---|
| User unit | `<HOME>/.config/systemd/user/yuva-panel.service` |
| Enablement | `default.target.wants/yuva-panel.service` aynı unit'e symlink |
| Unit SHA-256 | `fe310a325b161c295ab698fc087e807201c2e4069ae617a840628af96600164e` |
| systemd durumu | `LoadState=loaded`, `ActiveState=inactive`, `SubState=dead`, `MainPID=0` |
| `WorkingDirectory` | `%h/yuva-v2` → `<REPO_ROOT>` |
| Panel `ExecStart` script'i | `%h/yuva-v2/panel/server.py` → `<REPO_ROOT>/panel/server.py` |
| Unit `YUVA_DIR` | `%h/yuva` → `<YUVA_DATA_ROOT>` |
| Gerçek veri kökü | `<YUVA_DATA_ROOT>`, owner UID `1000`, mode `0700`, symlink değil |
| Beklenen install root | `<HOME>/.local/opt/yuva` yok; `current` ve manifest yok |

Unit dosyası yalnız `WorkingDirectory`, `ExecStart` içindeki executable/script
yolları ve `YUVA_DIR` değeri bakımından ayrıştırıldı. Diğer environment/argv
değerleri rapora alınmadı.

## CLI, panel ve kopya parmak izleri

| Yol | Çözümlenen yol / SHA-256 | Değerlendirme |
|---|---|---|
| `~/.local/bin/yuva` | `<REPO_ROOT>/bin/yuva`; `9643add83b2326ecb6a4c0b10f5382672dc997ad469a7d158821e82da7291b08` | PATH hedefi çalışma ağacındaki CLI ile aynı |
| `yuva-v2/bin/yuva` | Aynı SHA-256 | Çalışma ağacı kopyası; immutable release değil |
| `yuva-v2/panel/server.py` | `dd22963025b15df170826ef0c2bef5962d11202fbd04a954030348f8c5d9f0ce` | Unit `ExecStart` ile aynı kaynak yolu |
| `yuva/bin/yuva` | `7ecfe14ce88abff09e424572f8e27fa2d7e06a8785419ec5541743ea9ccd82d1` | Ayrı eski CLI kopyası |
| `yuva/panel/server.py` | `f3c10cbad99f0b4318c1990733115a2f71f39cba77172476b1b3301f18ef08b4` | Ayrı eski panel kopyası |
| `yuva-dev/bin/yuva` | `11933ae13e8af951d6ab3aa9f0ccef1f8745df4120060a8ffc00ebb43db8fa5e` | Ayrı geliştirme kopyası |
| `yuva-dev/panel/server.py` | `3d6d9b94332909cd5eff72e94e928be9bc798f244b372585b1529044a3588425` | Ayrı geliştirme paneli |
| `yuva-ui-dev/bin/yuva` | `6de3adda675aed0caf9e9cabde96fcd6c5ef44178dc3241bd203f5e55e00cddf` | Ayrı UI geliştirme CLI kopyası |
| `yuva-ui-dev/panel/server.py` | `115c7051f677e8368590a64f1f860d2998f0d8316fa8ca060ca2ea2eac3016f6` | Ayrı UI geliştirme paneli |

Kod ağacında `bin/yuva`, `panel/server.py`, `panel/ui.html` ve unit template'i
çalışma anında git tarafından değiştirilmiş görünüyordu. Bu nedenle hesaplanan
hash'ler gözlem anındaki dosyalara aittir; commit/release provenance veya
çalışan süreçte yüklenmiş byte'lar olduklarını kanıtlamaz. Eski/dev kopyaların
diskte bulunması etkin writer olduklarını kanıtlamaz; görünen süreç taraması
yalnız anlık ve mevcut process namespace'i içindir.

## Kanıt yöntemi ve sınırlar

- `systemctl --user show yuva-panel.service` yalnız `LoadState`, `ActiveState`,
  `SubState`, `MainPID`, `FragmentPath`, `WorkingDirectory` alanlarıyla salt
  okunur çağrıldı.
- User unit dizini ve `default.target.wants` symlink'i metadata olarak
  incelendi; unit'ten yalnız kod/data path alanları çıkarıldı.
- PATH symlink'i, kaynak yolları, bilinen CLI/panel kopyaları ve veri kökü
  `resolve`/stat/hash ile incelendi. Görev, sohbet veya credential içeriği
  okunmadı.
- `/proc` taraması yalnız argv içinde son bileşeni `bin/yuva` veya
  `panel/server.py` olan süreçleri eşleştirdi; eşleşen süreç görülmedi. Diğer
  süreçlerin argv/environment içeriği raporlanmadı.
- systemd'in `inactive` sonucu ve process görünürlüğü farklı namespace'lerde
  gizlenmiş süreçleri dışlamaz; açık unit tanımı aktif süreç argümanlarını
  kanıtlamaz. Unit değişikliği, service start/stop/restart, test veya canlı
  API çağrısı yapılmadı.

## Kaynaklar

- `docs/yuva-cli-copy-cutover-acceptance-508.md` — PATH, release, panel ve
  veri kökü birlikte kabul edilmeli; pointer tek başına çalışan süreci kanıtlamaz.
- `docs/legacy-cli-decommission-540.md` ve
  `docs/legacy-cli-task-write-guard-568.md` — bilinen eski CLI/panel yolları ve
  bunların süreçte aktif olduklarına dair kanıt gereği.
- `docs/agent-uid-host-operations-523.md` — loopback, UID ve ortak veri
  köklerinin işletim sınırı.
- `bin/yuva`, `panel/server.py` ve
  `~/.config/systemd/user/yuva-panel.service` — gözlem anındaki kod/unit kaynakları.
