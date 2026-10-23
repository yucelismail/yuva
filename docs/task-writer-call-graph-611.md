# Yuva #611 — Panel task dispatch ve kanonik writer çağrı grafiği

**Tarih:** 2026-10-23
**Kapsam:** Kaynak çağrı grafiği + mevcut sentetik fixture kanıtlarının statik incelemesi. Bu görevde test çalıştırılmadı; servis ve canlı görev defteri değiştirilmedi.

## Sonuç

Repo içindeki desteklenen `yuva-v2` CLI yolu ve panel `/api/gorev` dispatch'i, aşağıda listelenen sekiz task operation için aynı `bin/yuva` core ve aynı süreçler arası `.kilit` writer yoluna bağlanır. Panelde `gorevler.json` için ayrı bir JSON mutatörü veya subprocess ile eski CLI çağrısı yoktur.

Bu sonuç **desteklenen çağrı yolu** ile sınırlıdır. Bilinen `<YUVA_DATA_ROOT>` eski CLI ve eski panel bypass'larının guard'ları #568 fixture raporunda kanıtlanmıştır. Ancak `yuva-dev` ve `yuva-ui-dev` CLI kopyalarının doğrudan görev yazabildiğini `tests/test_cli_copy_compatibility_fixture.py` içindeki fixture açıkça gösteriyor; restore-check kopyaları da canonical writer olarak kabul edilemez. Dolayısıyla bütün yerel kopyalar veya aynı UID altındaki keyfi Python çağrıları için “legacy bypass kapalı” iddiası **kanıtlanmıyor**. Evrensel writer izolasyonu kabulü bu kanıtla **NO-GO** kalır.

## Desteklenen çağrı grafiği

```text
CLI: bin/yuva gorev <operation>
  └─ argparse task subcommand
      └─ cmd_gorev_<operation>
          ├─ normal mutation: gorev_guncelle(callback)
          │   └─ kilit_tut() → flock(KOK/.kilit)
          │       → gorev_yukle() → callback → kaydet(GOREV, ledger)
          └─ sonraki: aynı kilit içinde gorev_yukle()
              → claim seçimi/atama → kaydet(GOREV, ledger)

Panel: POST /api/gorev
  └─ UCLAR['/api/gorev'] → gorev_calistir(payload, principal, authorization)
      ├─ operation allowlist + policy/actor doğrulaması
      ├─ SourceFileLoader(CLI = CODE_ROOT / 'bin/yuva')
      └─ core.run_task_operation(operation, payload, actor, principal)
          └─ ilgili aynı cmd_gorev_<operation>
              └─ aynı .kilit + gorev_yukle + kaydet(GOREV)
```

Panelin `_TASK_CORE_LOCK` kilidi module yükleme ve stdout/stderr capture'ını sıraya koyar; görev ledger'ının süreçler arası kilidi değildir. Ledger writer kilidi CLI core içindeki `kilit_tut()` tarafından alınır. Böylece bir CLI yazımı ile panelden gelen yazım aynı `YUVA_DIR/.kilit` üzerinde serileşir.

## Operation eşlemesi

| Operation | CLI handler | Defter yazım bölümü |
|---|---|---|
| `ekle` | `cmd_gorev_ekle` | `gorev_guncelle()` |
| `ata` | `cmd_gorev_ata` | `gorev_guncelle()` |
| `al` | `cmd_gorev_al` | `gorev_guncelle()` |
| `sonraki` | `cmd_gorev_sonraki` | Seçim, assignee/status ve `kaydet()` tek `kilit_tut()` içindedir |
| `teslim` | `cmd_gorev_teslim` | `gorev_guncelle()` |
| `ilk-kontrol` | `cmd_gorev_ilk_kontrol` | `gorev_guncelle()` |
| `denetle` | `cmd_gorev_denetle` | `gorev_guncelle()` |
| `iptal` | `cmd_gorev_iptal` | `gorev_guncelle()` |

Panel köprüsü bu sekiz operation dışındakileri `400` ile reddeder. CLI parser da `gorev` alt komutlarını aynı handler'lara bağlar. Normal geçişlerde `gorev_guncelle()` lock → taze ledger oku → callback ile doğrula/değiştir → atomik `kaydet()` sırasını izler. `sonraki` ayrı bir özel akıştır; kilidi aday seçimi başlamadan alıp güncellemeyi kaydedene kadar bırakmaz. `kaydet()` JSON dosyasında schema kontrolü, benzersiz geçici dosya, `fsync` ve `os.replace` uygular; fonksiyon kendi başına lock almadığından güvence çağrı grafiğinin kilitli writer girişlerinden gelmesine bağlıdır.

## Panel doğrudan dispatch ve auth sınırı

`panel/server.py` POST dispatch'i, auth açıkken önce HMAC request doğrulama ve task operation authorization yapar; sonra `/api/gorev` için `gorev_calistir` fonksiyonunu principal/policy ile çağırır. Auth kapalıyken de aynı `gorev_calistir` → CLI core → kilitli writer grafiği kullanılır; o kipte aktör body'deki `kimden` alanıdır ve `local_unverified` kabul edilir. Bu nedenle tek writer kanıtı, auth-off actor iddiasını doğrulanmış kimlik yapmaz.

“Doğrudan dispatch” burada panelin ayrı handler ile `gorevler.json` yazmadığı anlamındadır. `gorev_calistir` çağrısı, kanonik CLI modülünün aynı süreçte yüklenip operation handler'ına doğrudan dispatch edilmesidir; shell subprocess değildir. Yetki denetimi ayrı katmandır, ledger yazımı CLI core'dadır.

## Legacy bypass kanıtı ve açık sınır

| Yol | Eldeki kanıt | Sonuç |
|---|---|---|
| Desteklenen `yuva-v2/bin/yuva` + v2 panel | Kaynak çağrı grafiği; #552 writer haritası | Sekiz desteklenen operation aynı canonical core ve lock'e ulaşır |
| Eski `<YUVA_DATA_ROOT>/bin/yuva` + eski panel | #568 geçici fixture'ında altı eski CLI mutation reddedildi; eski panel POST ve iç bridge `410 legacy_task_writes_disabled` verdi; ledger byte hash'i değişmedi | Bu iki bilinen eski giriş kapatılmış olarak raporlanmıştır; #568 testi bu çalışmada tekrar çalıştırılmadı |
| `yuva-dev/bin/yuva`, `yuva-ui-dev/bin/yuva` | Mevcut fixture testi bu kopyaların `gorev al` ile schema v99 ledger'ını `assigned` yaptığını; canonical CLI'ın aynı ledger'ı reddettiğini gösteriyor | Kopyalar kanonik writer'a zorlanmıyor ve aynı data root'a yöneltilirse bypass olabilir. Bu fixture bu görevin çalışmasında yeniden koşturulmadı |
| `yuva-yedek/restore-check.*` CLI kopyaları | Aynı uyumluluk fixture'ında bozuk JSON için fail-open davranışı kapsanıyor | Kurtarma kopyası/fixture'dan üretim yazımı desteklenmez; dosya veya UID sınırıyla kapandığı kanıtlanmamıştır |
| Keyfi `SourceFileLoader`/Python import veya doğrudan `kaydet(GOREV, ...)` | Repo statik araması ve #568 kapsam sınırı | OS seviyesinde writer sahipliği veya modül içe aktarma engeli yok; “her çağrı tek yazıcıdan geçer” denemez |

Mevcut `tests/test_legacy_task_write_guard.py` fixture'ı yalnız #568'deki eski root CLI/panel'i kapsar. `tests/test_cli_copy_compatibility_fixture.py` ise dev kopyalarını bilinçli olarak uyumsuzluk örneği olarak çalıştırır. Bu iki kanıt birlikte, eski root bypass kapısının dar kapsamda kapandığını ve diğer fiziksel kopyaların aynı garantiye dahil olmadığını gösterir.

## Kabul kararı ve kalan iş

- **Scoped PASS:** Kanonik repo panel/CLI destekli görev işlemleri tek kilitli ledger writer'a çağrı grafiğiyle bağlıdır.
- **Scoped PASS:** #568'de belirtilen eski root CLI ve eski panel API yazım girişleri fixture raporunda reddedilmiştir.
- **NO-GO / açık:** Tüm eski/dev/restore kopyalarına karşı fiziksel writer tekilliği yoktur. Aynı OS UID ve ortak `YUVA_DIR` altında dev kopyaları hâlâ yazabilir; helper fonksiyonun doğrudan çağrısı da OS sınırıyla engellenmiyor.
- Bu açığı kapatmanın sonraki kabulü ayrı olarak tüm çağrılabilir CLI kopyalarını desteklenen writer'a yönlendirme veya data root yazma sahipliğini servis UID/ACL/launcher ile sınırlama ve her eski kopya için sentetik no-write fixture'ı çalıştırmadır. Bu görev kapsamında kopya, izin, servis veya canlı ledger değiştirilmedi.

## Kaynaklar

- `bin/yuva`: `run_task_operation()` (122–179), `kilit_tut()` (204–272), `kaydet()` (297+), `gorev_guncelle()` (2163–2169), `cmd_gorev_sonraki()` (2279+), görev parser'ı.
- `panel/server.py`: `gorev_calistir()` (1439–1530), `UCLAR` (`/api/gorev`), `do_POST()` (auth → dispatch).
- `docs/task-ledger-single-writer-552.md` — daha önceki canonical writer envanteri ve fixture kanıtı.
- `docs/legacy-cli-task-write-guard-568.md`, `tests/test_legacy_task_write_guard.py` — eski root CLI/panel guard kapsamı.
- `tests/test_cli_copy_compatibility_fixture.py` — dev/restore kopyalarının canonical writer ile uyumsuz fixture örnekleri.

Bu belge statik çağrı grafiği ile mevcut fixture kaynaklarının incelemesidir; live service/ledger veya test çalıştırması değildir.
