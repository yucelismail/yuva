# Yerel görev yazıcı kopyaları envanteri ve riskleri (#627)

**Tarih:** 2026-10-23
**Durum:** Salt-okunur path/hash/Git/kaynak envanteri; CLI davranış fixture'ı veya canlı süreç denetimi yapılmadı.
**Kök:** `<HOME>`; hash'ler bu inceleme anındaki dosya byte'larına aittir, release pin'i değildir.

## Sonuç

Desteklenen `yuva-v2/bin/yuva` ve aynı ağaçtaki panel görev mutasyonlarını ortak CLI core'una ve süreçler arası `.kilit` writer yoluna gönderir. Bu, **desteklenen yol için** tek yazıcı sözleşmesidir. Yerel makinede eski, geliştirme ve restore-check CLI/panel kaynakları da bulunuyor. `yuva-dev` ile `yuva-ui-dev` kilitli task oku-değiştir-yaz kullanmalarına rağmen ayrı kaynak kopyalarıdır ve shared ledger'a doğrudan yazabilir; schema uyumluluk kapıları yoktur. Restore-check kaynakları fail-open/lock'suz tarihsel kod taşır. Bu nedenle tüm yerel çalıştırılabilirler için evrensel tek writer veya OS izolasyonu kanıtlanmış değildir; aynı kullanıcı/`YUVA_DIR` altında görev mutasyonu için **NO-GO**.

## Kopya envanteri

| Yerel giriş/kaynak | CLI SHA-256 | Panel SHA-256 | Kaynak durumu | Writer değerlendirmesi |
|---|---|---|---|---|
| `~/.local/bin/yuva` → `<REPO_ROOT>/bin/yuva` | `cea24e29c4b3e2f9f91e03153f55a5d728519170fdd9bf90ea25458ddcbbdfa6` | — | Symlink; çözülünce v2 dosyasını çalıştırır. | Beşinci kod kopyası değildir. Symlink doğrudan mutable `yuva-v2` worktree'sine gider; hash immutable release/manifest kimliği oluşturmaz. |
| `<REPO_ROOT>` | `cea24e29c4b3e2f9f91e03153f55a5d728519170fdd9bf90ea25458ddcbbdfa6` | `dcbd7bdd6bc8c8f047400edbc9ac45f006fe9da66868255af4b2b1373a2c3caf` | Git `b0c38d29a2ab6bf256308ead6a712bc4a0ec17c8`; tracked `bin/yuva`, `panel/server.py` ve başka dağıtım dosyaları değiştirilmiş. | `DATA_SCHEMA_VERSION=1`, schema reader/writer gate'i, task mutation'larında `.kilit` ve panelin `SourceFileLoader` ile aynı CLI core'una dispatch'i var. Desteklenen çağrı grafiği içinde kanonik writer; dirty worktree ve release identity doğrulanmamış. |
| `<YUVA_DATA_ROOT>-dev` | `11933ae13e8af951d6ab3aa9f0ccef1f8745df4120060a8ffc00ebb43db8fa5e` | `3d6d9b94332909cd5eff72e94e928be9bc798f244b372585b1529044a3588425` | Git `d072d97c34b1487726cc1addb6cf12e0ef90bc7c`; `protokol.md` tracked değişikliği. | Task RMW `.kilit` flock altında; shared schema `1` doğrulaması ve canonical release pin'i yok. Fixture daha önce schema `99` ledger'ını değiştirebildiğini göstermiştir. Aynı default data root'a yönelirse ikinci writer olabilir. Paneli kendi CLI/task yolu üzerinden mutation yapabilir. |
| `<YUVA_DATA_ROOT>-ui-dev` | `6de3adda675aed0caf9e9cabde96fcd6c5ef44178dc3241bd203f5e55e00cddf` | `115c7051f677e8368590a64f1f860d2998f0d8316fa8ca060ca2ea2eac3016f6` | Git `7fd1437d95f39f5ca78208cc0bb44e579bf14b5e`; tracked değişiklik görünmedi. | Task RMW `.kilit` flock altında; shared schema gate/release pin'i yok. UI ve ilk-kontrol akışları canonical v2 ile uyum kabulü olmadan ayrı writer yolu oluşturabilir. |
| `<YUVA_DATA_ROOT>` | `7ecfe14ce88abff09e424572f8e27fa2d7e06a8785419ec5541743ea9ccd82d1` | `f3c10cbad99f0b4318c1990733115a2f71f39cba77172476b1b3301f18ef08b4` | Git deposu değil. Aynı ağaç hem eski kodu hem varsayılan Yuva data root'unu içeriyor. | CLI parser'ı görev mutation komutlarını çalıştırmadan reddediyor; eski panel `/api/gorev` için `410 legacy_task_writes_disabled` döndürüyor. Bu dar guard'lar doğrudan import/helper veya diğer eski writer yolları için OS engeli değildir. |
| `yuva-yedek/restore-check.T4hbP8/yuva` | `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` | `c6700845c96fc449701b08153f45f2a6b3083da6606556df4b7ae202d560a01b` | Restore-check parent `0700`; içindeki `yuva` ağacı `0775`. Normal Git worktree/runtime olarak sınıflandırılmadı. | Tarihsel task save yolu kilitsiz ve JSON hata/fallback davranışı fail-open; üretim writer'ı olmamalı. Yalnız restore inceleme girdisi. |
| `yuva-yedek/restore-check.XOeUcj/yuva` | `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` | `c6700845c96fc449701b08153f45f2a6b3083da6606556df4b7ae202d560a01b` | Restore-check parent `0700`; içindeki `yuva` ağacı `0775`. T4hbP8 ile CLI/panel hash'leri aynı. | Yukarıdakiyle aynı; restore-check dosyalarının aynı hash'i davranış güvenliği veya production uyumluluğu sağlamaz. |

**Hash notu:** `yuva-dev`, `yuva-ui-dev` ve restore-check hash'leri tarihsel #596 raporuyla eşleşiyor. Eski kök CLI/panel ile v2 CLI/panel hash'leri önceki envanterden farklı; bu tablo yeni ölçümü kaydeder. `yuva-v2` çalışma ağacı dirty olduğundan ölçülen dosya hash'i release artifact hash'i değildir. Hash eşitliği tek başına kaynak, tüm ağaç, çalışma modu veya proses kimliğini kanıtlamaz.

## Giriş ve runtime ayrımı

- `~/.local/bin/yuva` mevcut statik symlink çözümünde v2 workspace dosyasını çalıştırır. Bu bir release altında `current` symlink'i değildir.
- Beklenen release install path'i `<HOME>/.local/opt/yuva` bu incelemede mevcut değildi. Bu durum, çalışan panel/CLI'nin ne olduğunu kanıtlamaz.
- `yuva-yedek/restore-check.*` altındaki kopyalar `rg --files --hidden` taramasında ek `bin/yuva`/`panel/server.py` kaynakları olarak bulundu; bunlar deployment veya desteklenen PATH girdisi olarak görülmedi.
- Çalışan servis, açık process image/cwd, user unit'in kurulu içeriği, shell alias/function, cron/automation ve etkin `YUVA_DIR` bu görevde sorgulanmadı. Etkin runtime **unknown** kalır.

## Tek writer riskleri ve sınırlar

1. **Aynı default data root:** Kopyalar `YUVA_DIR` override almazsa kod ağacından bağımsız şekilde `~/yuva`'ya yazar. Farklı CLI dosyalarının aynı ledger'a çalıştırılması tek süreç kilidiyle değil, bütün yazarların aynı `.kilit` inode/protokolünü kullanmasıyla güvenlidir.
2. **Dev/UI uyumsuzluğu:** İki kopya kilitli RMW yapar, fakat schema `99` gibi desteklenmeyen deftere mutation yapabilir. Paylaşılan flock lost update riskini daraltır; schema compatibility, role/transition equivalence veya release trust sağlamaz.
3. **Legacy/restore:** Eski root CLI/panel dar task guard'larına sahiptir; restore-check kopyalarında bu guard/uyumluluk garantileri yoktur. Bu dosyalar doğrudan path, Python import veya başka caller ile erişilebilir olmaya devam eder. Same-UID file permission tek başına süreçleri ayırmaz.
4. **Panel kopyaları:** Yalnız v2 panelin desteklenen task dispatch'i aynı canonical CLI core'udur. Dev/UI panellerinin ayrı source task bridge'i; eski root panelin ise ayrı legacy guard'ı vardır. Hangi panel process'inin çalıştığı unit dosyasından tek başına çıkarılamaz.
5. **Lock'in kapsamı:** `.kilit` işbirlikçi kilittir; kilidi atlayan writer, farklı lock path/inode kullanan data root veya doğrudan `kaydet()` caller'ı üzerinde OS-level sahiplik kurmaz. Uygulama hatası/kill/atomicity için ilgili task-ledger fixture'ları ayrıca kanıttır; hash envanteri onların yerine geçmez.

## Operasyonel kabul

- Desteklenen yazma girişini onaylı, immutable release içindeki tek CLI/panel çifti ve açıkça belirlenmiş `YUVA_DIR` ile sınırla; bugünkü mutable workspace symlink'i bu kabul değildir.
- `yuva-dev`, `yuva-ui-dev`, eski kök ve restore-check kopyalarını ortak ledger writer'ı olarak kullanma. Tasarım gereği kullanım gerekiyorsa ayrı scratch `YUVA_DIR`, explicit launcher/gate ve kopya başına fail-closed fixture kabulü gerekir.
- Evrensel tek-writer iddiası için tüm elle çağrı/automation/unit girişlerini, bütün kopyaların source/hash/schema/lock davranışını ve çalışan process kimliğini denetle. Mümkün olduğunda ayrı service UID, data-root sahipliği/ACL veya erişimi kısıtlı writer broker ile bypass'ı OS seviyesinde kapat; bu envanter bunları kurmaz.
- Her release/cutover'da canonical manifest pin'i, source/payload hash'i, install root, symlink hedefleri ve data-root ayrımını birlikte doğrula. Sadece `~/.local/bin/yuva` symlink'i veya CLI hash'i yeterli değildir.

## İlgili kanıt

- [#596 CLI schema/writer uyum envanteri](cli-copy-schema-writer-compatibility-596.md) — dev/UI/restore fixture davranışı ve geçmiş kopya hash'leri.
- [#611 task writer çağrı grafiği](task-writer-call-graph-611.md) ve [#552 single-writer haritası](task-ledger-single-writer-552.md) — desteklenen çağrı kapsamı ve bypass sınırı.
- [#598 runtime root envanteri](runtime-roots-inventory-598.md) — önceki statik runtime snapshot'ı; etkin süreç kabulü değildir.
- [#522 release manifest sözleşmesi](cli-copy-release-manifest-contract-522.md) — full source/payload/release kimliği gereksinimi.
- `tests/test_cli_copy_compatibility_fixture.py`, `tests/test_legacy_task_write_guard.py` — geçmişteki geçici-copy fixture kanıtları; bu görevde yeniden koşturulmadı.

Bu görev yalnız statik dosya/pointer/hash/working-tree envanterini yeniler. CLI/panel kopyası, symlink, backup, Yuva data root, service, task ledger veya runtime değiştirilmedi; test/fixture çalıştırılmadı.
