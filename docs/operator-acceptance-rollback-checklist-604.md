# İlk yerel MVP — operatör kabul ve rollback checklist’i (#604)

**Kullanım:** Her release/host geçişinde doldurun; bu belge tek başına GO
veya risk kabulü değildir.

## Şu anki durum

**Şu an NO-GO.** #598 (2026-10-23): panel unit’i `inactive/dead`, PATH CLI ve
unit panel kaynağı mutable `yuva-v2`; `~/.local/opt/yuva/current` yok. Hiçbir
kabul kutusu önceden işaretli değildir.

## Release ve operatör kabulü

Release/instance: __________  Operatör: __________  Tarih/saat: __________
Kanıt paketi / kayıt bağlantısı: ________________________________________

- [ ] **Tehdit modeli:** tek operatör/tek UID, loopback, manuel akış, presence
  `unknown`, dispatch kapalı; `--from`/`kimden` doğrulanmış kimlik değil.
- [ ] **Snapshot erişimi:** anonim GET tüm roster/görev/sohbet/ekran verisini
  açabilir. #574 varsayılan NO-GO: untrusted local agent varsa insan-only
  istisnası kanıtlanmadıkça veya GET+POST erişim sınırı kurulmadıkça dur.
- [ ] **Release:** temiz commit/tree, bağımsız pinli manifest/hash, immutable
  `current`, PATH CLI, unit ve panel aynı release. Her uyumsuzluk **NO-GO**.
- [ ] **Writer/data:** etkin process argv/cwd ve bind doğrulandı; CLI/panel aynı
  release dışı gerçek `YUVA_DIR` kullanıyor; eski/dev writer yok veya yazamaz.
- [ ] **Şema/backup:** mevcut kayıt şemaları destekleniyor; etkin kök dışı backup
  verify ve izole restore-check geçti; rollback uyumu kanıtlı. Unknown/bozuk
  schema, backup veya `restore-check.*` provenance’ı **NO-GO/HOLD**.
- [ ] **Semantik:** HMAC/loopback auth varsayılmıyor; actor beyanı kimlik,
  sohbet mesajı receipt, presence online/offline kanıtı, provider dispatch ve
  approval değildir.
- [ ] **Kanıt:** her gerçek host kapısına makbuz bağlandı. Fixture GO’su host
  kanıtı değildir. Hiçbir `unknown`, eksik kanıt veya açık risk kalmadı.

## Karar

- [ ] **GO:** Bütün kapılar tamam, kanıtlar bağlantılı ve operatör kapsamı
  onayladı. Yalnız bu tek operatörlü, loopback, manuel MVP kapsamı için.
- [ ] **NO-GO:** Herhangi bir kapı başarısız/bilinmiyor; servis/erişim kapalı
  kalır. Erişim, dispatch veya auth’ı sessizce değiştirme.

Karar sahibi/imza: ____________________  Zaman: __________  Kanıt: __________

## Güvenli rollback sırası

Rollback kodu geri alır; ortak `YUVA_DIR` verisini otomatik geri yüklemez.
Commit, proses veya restore sonucu belirsizse **yazımları dondur; kör retry,
pointer değişimi veya backup restore yapma**.

1. [ ] Yazımları dondur; yetkili bakım penceresinde doğrulanmış unit’i durdur.
   PID/port ve eski/yeni writer yokluğunu kanıtla. Symlink değişimi eski
   process’i durdurmaz.
2. [ ] Önceki immutable release/manifest/hash ve CLI-panel eşleşmesini doğrula;
   eski sürüm mevcut schema’yı desteklemiyorsa dur, aynı `YUVA_DIR`’e bağlama.
3. [ ] `YUVA_DIR`’i koru. Kod rollback’i otomatik backup restore değildir;
   restore ayrı onay, verify ve scratch restore-check gerektirir.
4. [ ] Pointer değişimi ve servis start’ı ayrı onaylıysa yalnız uyumlu release’e
   uygula; CLI/panel/data path’lerini tekrar doğrula ve makbuza kaydet.
5. [ ] Herhangi bir sonuç unknown ise servisi/yazımları kapalı tut; kör
   pointer değişimi veya restore yapma.

## Dayanaklar

- `docs/first-local-mvp-scope-go-no-go-536.md`; `docs/local-mvp-release-go-no-go-matrix-576.md`.
- `docs/panel-anonymous-snapshot-data-minimization-574.md`; `docs/runtime-roots-inventory-598.md`.
- `docs/yuva-cli-copy-cutover-acceptance-508.md`; `docs/backup-verify-restore-check-544.md`; `docs/restore-check-retention-policy-530.md`.
