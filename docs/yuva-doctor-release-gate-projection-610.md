# Yuva #610 — Doctor → release Go/No-Go kanıt projeksiyonu

**Tarih:** 2026-10-23
**Kapsam:** Salt okunur doctor çıktısını #576'daki sekiz zorunlu release kapısına eşler. Host, unit, süreç, auth, veri veya backup değiştirilmedi.

## Karar kuralı

`yuva doctor` bir ön kontrol envanteridir; tek başına release GO kararı üretemez. #576'ya göre **herhangi bir zorunlu kanıttaki `UNKNOWN`, eksik kanıt veya kabul edilmemiş risk release kararını NO-GO yapar**.

Projeksiyonda aşağıdaki kurallar uygulanır:

| Doctor durumu | Release kapısına yansıtma |
|---|---|
| `PASS` | Yalnız doctor'ın açıkça ölçtüğü dar olgu için kanıt. Parent release kapısı, tüm diğer gerekli kanıtlar gelmeden `PASS` olamaz. |
| `FAIL` | İlgili kapı başarısız; release **NO-GO**. |
| `OCCUPIED` | Port dinliyor, sahibi doğrulanmamış. İlgili çalışma yolu için **UNKNOWN**, release kararı NO-GO. |
| `UNKNOWN` | Gerekli olgu kanıtlanmadı; release **NO-GO**. |
| `OBSERVED` | Gözlenen kaynak/yol bilgisi; provenance veya release doğrulaması değil. İlgili kapı **UNKNOWN** kalır. |
| `NO_LISTENER_OBSERVED` | Procfs anlık görüntüsünde listener görülmedi. Unit'in pasif, panelin çalışmıyor veya portun başka yoldan erişilemez olduğunu kanıtlamaz; çalışma durumu **UNKNOWN** kalır. |

**Unit dosyasının varlığı/şablonla eşleşmesi, unit'in etkin olduğu anlamına gelmez. Unit'in inactive görünmesi de release operasyonunun doğrulandığı anlamına gelmez.** Süreç gözlenemiyor, PID executable/cwd veya systemd cgroup ile ilişkilendirilemiyorsa operasyon kanıtı `UNKNOWN`'dır. Doctor mevcut haliyle process sahibini doğrulamaz.

## Doctor satırlarının #576 kapılarıyla eşlemesi

| Doctor satırı | #576 kapısı | PASS'in kanıtladığı dar olgu | PASS'in kanıtlamadığı / zorunlu ek kanıt |
|---|---|---|---|
| `cli_source` (`OBSERVED`) | 2, 3 | Bu çalıştırmada görünen CLI kaynak yolu ve code root ilişkisi | İmzalı/temiz release provenance, bağımsız payload pin'i, etkin PATH/unit ile aynı release |
| `supported_cli_entry` | 2, 3 | PATH symlink'inin `current/bin/yuva` hedefine uyması | Hash pin'i, clean tree, gerçek etkin panel process'i veya writer tekilliği |
| `cli_panel_release_alignment` | 2, 3 | CLI, PATH, panel kaynağı ve `current` yollarının aynı release'e çözülmesi | İçerik hash'i, provenance, panel process executable/cwd ve eski writer yokluğu |
| `legacy_writer_inventory` | 3 | Yalnız bilinen eski yolların metadata envanteri; bilinen kopya yoksa bu listede kopya görülmediği | Tam dosya taraması, process/listener sahipliği, kopyaların etkin olmadığının kanıtı |
| `data_root` | 4 | Veri kökünün metadata düzeyinde gerçek yol/dizin, euid sahipliği ve `0700` mode koşulu | Başka UID/namespace/HTTP erişimi, snapshot okuyucu kabulü, etkin unit'in aynı kökü kullanması |
| `writer_schema` | 4 | Okunabilen JSON/JSONL kayıtlarının desteklenen şema kontratıyla uyumu | Gerçek release ile rollback uyumu, writer singleton veya erişim gizliliği |
| `current` | 2, 3 | `current` symlink'i release dizini içinde ve CLI/panel dosyaları mevcut | Payload hash/provenance, PATH ve etkin unit/process uyumu |
| `unit_template` | 3, 6 | Repo içindeki unit şablonunun beklenen current/data-root direktifleri | Kurulu unit'in şablondan türediği, systemd'nin yüklediği tanım veya unit'in çalışması |
| `installed_unit` | 3, 6 | Kurulu unit dosyasından okunabilen WorkingDirectory/ExecStart/YUVA_DIR'in hedef yollarla eşleşmesi | EnvironmentFile/etkin environment, unit ActiveState, MainPID, process executable/cwd, bind ve erişilebilirlik |
| `panel_port_*` (`occupied`) | 3, 6 | Procfs TCP tablosunda port için LISTEN kaydı olduğu | Listener PID/process sahibi, Yuva unit'i olduğu, bind güvenliği veya doğru release kullandığı |
| `panel_port_*` (`NO_LISTENER_OBSERVED`) | 3, 6 | O an okunabilen procfs tablolarında listener bulunmadığı | Unit inactive, servis durumu, alternat bind/tunnel/proxy yokluğu veya port yarışının olmadığı |
| `auth_runtime` | 1, 4, 6, 7 | Doctor auth runtime'ı okumaz; her zaman belirsizliği görünür kılar | Etkin auth flag'i/store, GET/POST erişim politikası, session/browser erişimi veya güvenli kimlik |
| `presence` | 7 | Doctor heartbeat/presence dosyası okumaz; `unknown` iddiasını korur | Online/offline durumu, doğrulanmış actor veya provider davranışı |

Kapı 1'in operatör snapshot/erişim kabulü, kapı 5'in gerçek backup/restore/rollback kanıtı ve kapı 8'in release makbuzu/canary kanıtı doctor tarafından kontrol edilmez. Bu kapılar her zaman ayrı kanıt ister; doctor `PASS` satırlarıyla doldurulamaz.

## Kapı düzeyinde toplama

Bir kapı `PASS` sayılabilmek için #576'daki **tüm** kabul maddeleri için yetkili kanıt bulunmalı ve ilgili doctor alt kontrolleri varsa onlar da `PASS` olmalıdır. Kapıya ait zorunlu bir alt durum `FAIL` ise kapı `FAIL`; hiçbir `FAIL` olmasa da kanıtlardan biri `UNKNOWN`/eksikse kapı `UNKNOWN` olur. Her iki sonuç da release GO üretmez.

| #576 kapısı | Doktordan kullanılabilecek satırlar | Doctor tek başına yeterli mi? | Eksik dış kanıt örnekleri |
|---|---|---|---|
| 1. Ürün ve erişim sınırı | `auth_runtime` yalnız unknown sinyali | Hayır | #574 operatör kararı; erişebilen süreçler/namespace/proxy kabulü; hassas snapshot okuyucu sınırı |
| 2. Kaynak ve release kimliği | `cli_source`, `supported_cli_entry`, `cli_panel_release_alignment`, `current` | Hayır | Clean commit/tree, manifest ve bağımsız payload hash pin'i, immutable release |
| 3. Tek CLI/panel hedefi ve tek writer | `supported_cli_entry`, `cli_panel_release_alignment`, `legacy_writer_inventory`, `unit_template`, `installed_unit`, `panel_port_*` | Hayır | Etkin PID executable/cwd/cgroup, etkin veri kökü, eski writer yokluğu ve tek writer makbuzu |
| 4. Veri kökü, sahiplik ve snapshot | `data_root`, `writer_schema`, `auth_runtime` | Hayır | Etkin unit'in aynı `YUVA_DIR` kullandığı, HTTP/UID okuyucu sınırı, snapshot kabulü ve release uyumu |
| 5. Backup, restore ve rollback | Yok | Hayır | Gerçek yedek/verify, scratch restore-check, rollback şeması ve authenticity kabulü |
| 6. HTTP, browser ve auth | `unit_template`, `installed_unit`, `panel_port_*`, `auth_runtime` | Hayır | Gerçek bind ve proxy/tunnel/LAN durumu, etkin auth/config, browser/snapshot kabulü |
| 7. Görev, actor, presence ve provider | `presence`, kısmen `auth_runtime` | Hayır | Kurulu release davranışı, config/secret kaynağı, actor güven sınırı, provider/dispatch kapalı kanıtı |
| 8. Acceptance/canary kanıtı | `writer_schema` yalnız şema sinyali | Hayır | #550 fixture raporu ve gerçek host/release için bağımsız release makbuzu; fixture tek başına host kanıtı değildir |

## Bu çalıştırmanın salt okunur sonucu

`python3 bin/yuva doctor` bu belge hazırlanırken salt okunur çalıştırıldı. Çıktının karar özeti `NO-GO · düzeltme/operatör incelemesi gerekli` oldu. Hassas mutlak yollar bu raporda tekrarlanmamıştır.

| Kontrol grubu | Gözlenen durum | Projeksiyon |
|---|---|---|
| Kaynak yeri | `cli_source=OBSERVED` | Release provenance bilinmiyor; kapı 2 unknown |
| PATH CLI ve release hizası | `supported_cli_entry=FAIL`, `cli_panel_release_alignment=UNKNOWN`, `current=UNKNOWN` | Kapı 2 fail/NO-GO |
| Eski kopyalar ve kurulu unit | `legacy_writer_inventory=UNKNOWN` (bilinen ayrı kopyalar görülmüş); `installed_unit=FAIL` (yol eşleşmiyor); çalışma PID'si doğrulanmıyor | Kapı 3 fail/NO-GO |
| Veri kökü ve şema | `data_root=PASS`, `writer_schema=PASS` | Yalnız sahiplik/mode ve okunabilen şema dar kontrolleri geçti; kapı 4'ün snapshot/erişim kabulü bilinmiyor, kapı 4 GO değil |
| Unit şablonu | `unit_template=PASS` | Yalnız repo şablonu doğru yolları gösteriyor; kurulu unit/process doğrulanmıyor |
| Panel listener | `panel_port_8686=NO_LISTENER_OBSERVED` | Listener'ın o an procfs'te görünmediği gözlendi; unit inactive veya operasyon doğrulandı denemez |
| Auth ve presence | `auth_runtime=UNKNOWN`, `presence=UNKNOWN` | Kapılar 1/6/7 için gerekli runtime/operatör kanıtı yok |
| Backup ve release acceptance | Doctor kontrolü yok | Kapılar 5/8 unknown; ayrı kanıt gerekli |

Kapı projeksiyonu: **1 UNKNOWN, 2 NO-GO, 3 NO-GO, 4 UNKNOWN, 5 UNKNOWN, 6 UNKNOWN, 7 UNKNOWN, 8 UNKNOWN**. Genel release kararı **NO-GO**. Bazı metadata/şema kontrollerinin PASS olması, eksik zorunlu kanıtları veya doğrulanmayan çalışma durumunu GO'ya yükseltmez.

## Çalıştırma ve rapor kullanımı

- `python3 bin/yuva doctor` salt okunur gözlem üretir; bu komutun `PASS` satırları yalnız yukarıdaki dar kapsamda aktarılır.
- Raporu release makbuzuna eklerken çalıştırma tarihi, CLI/source version veya hash'i, doctor çıktısındaki her satır durumu ve kaynak release pin'i birlikte kaydedilir. Doctor çıktısı provenance pin'i değildir.
- Çıktıda `UNKNOWN`, `OBSERVED`, `OCCUPIED` veya `NO_LISTENER_OBSERVED` varsa ilgili zorunlu kapı açık kalır; genel karar NO-GO'dur. Unit/process gözlemi yoksa çalışıyor ya da doğrulanmış diye yazılmaz.
- Bu projeksiyon servis başlatma/durdurma, auth açma, backup alma/restore etme, görev/mesaj yazma veya host düzeltmesi yapmaz.

## Kaynaklar

- `docs/local-mvp-release-go-no-go-matrix-576.md` — sekiz zorunlu kapı ve mevcut NO-GO gerekçeleri.
- `docs/release-acceptance-harness-550.md`, `release_acceptance.py` — sentetik fixture'ın host kanıtı olmadığını ve UNKNOWN'un NO-GO olduğunu belirler.
- `bin/yuva` — `doctor_raporu()`, `_doctor_panel_port()`, `cmd_doctor()`.

Bu rapor bir canlı rollout onayı değildir; yalnız bu çalıştırmada görülen doctor sonuçlarının release kapılarına sınırlı projeksiyonudur.
