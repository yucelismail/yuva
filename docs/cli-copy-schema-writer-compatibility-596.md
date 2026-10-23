# PATH dışı CLI kopyaları için schema/writer uyum kapısı (#596)

**Tarih:** 2026-10-23
**Durum:** Salt-okunur envanter, geçici-kopya fixture'ı ve fail-closed referans kapısı tamamlandı; incelemeye teslim ediliyor.
**Sınır:** Gerçek CLI kopyaları, symlink, görev verisi ve servis değiştirilmedi. Davranış fixture'ları kaynakları `TemporaryDirectory` içine kopyalayıp yalnız `YUVA_DIR` olarak aynı geçici dizini kullandı. Restore-check kaynakları çalıştırılmadı; yalnız geçici kopyaları çalıştırıldı.

## Anlık kopya/hash envanteri

| Dosya | SHA-256 | Kaynak / writer gözlemi |
|---|---|---|
| `~/.local/bin/yuva` → `<REPO_ROOT>/bin/yuva` | `9643add83b2326ecb6a4c0b10f5382672dc997ad469a7d158821e82da7291b08` | Shell giriş işaretçisi kanonik v2 ağacına çözülüyor. `DATA_SCHEMA_VERSION=1`; okuma ve yazmada desteklenmeyen schema sürümü değişiklik öncesi reddediliyor. `gorev_guncelle` tüm oku-değiştir-yaz adımını `.kilit` altında yapıyor; `kaydet` desteklenen schema'yı doğrulayıp alanı koruyor/ekliyor (`bin/yuva:47,87-92,297-304,2061-2068,2163-2169`). |
| `<YUVA_DATA_ROOT>/bin/yuva` | `7ecfe14ce88abff09e424572f8e27fa2d7e06a8785419ec5541743ea9ccd82d1` | Eski kopya; ana CLI'da görev mutasyonları #568 ile fail-closed reddediliyor (`yuva/bin/yuva:885-896`). Alttaki tarihsel `gorev_kaydet` hâlâ kilitsiz olduğundan doğrudan import/başka çağırma yolu desteklenmiş sayılmaz. Schema gate yok. |
| `<YUVA_DATA_ROOT>-dev/bin/yuva` | `11933ae13e8af951d6ab3aa9f0ccef1f8745df4120060a8ffc00ebb43db8fa5e` | Task `gorev_guncelle` tüm oku-değiştir-yaz adımını `KOK/.kilit` üzerindeki flock altında yapıyor (`:27-29,68-94,1536-1542`). Schema version alanını doğrulayan sabit/koruma bulunmuyor; JSON nesnesini olduğu gibi tekrar yazdığı için mevcut `schema_version` değerini bırakır ama bilinmeyen sürümde mutasyona devam eder. Schema'sız varsayılan da sürümsüz kalabilir. |
| `<YUVA_DATA_ROOT>-ui-dev/bin/yuva` | `6de3adda675aed0caf9e9cabde96fcd6c5ef44178dc3241bd203f5e55e00cddf` | `yuva-dev` ile aynı `.kilit` flock + kilitli task RMW yaklaşımı (`:28-30,70-96,1746-1752`); `schema_version` kontrolü yok. UI/ilk-kontrol alanları daha yeni olmasına rağmen bir shared v2 schema uyumluluk kapısı sağlamıyor. |
| `yuva-yedek/restore-check.T4hbP8/yuva/bin/yuva` | `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` | Restore-check fixture kopyası; `.kilit` yalnız JSONL eklemede kullanılır. Task mutasyonları `gorev_kaydet → kaydet` yolunda kilitsizdir (`:43-63,640-645`). `yukle()` her parse/IO hatasında default döndürür; schema kontrolü yok. |
| `yuva-yedek/restore-check.XOeUcj/yuva/bin/yuva` | `90c15912b020735d84c5f44f1dab74ec171540255ef161cf30a752e35cfb8d05` | T4hbP8 ile hash'i aynı restore-check kaynak kopyası; kurtarma amacı için tutulmalı, ortak canlı görev defterine yazıcı olarak kullanılmamalı. |

`yuva-dev` ve `yuva-ui-dev` `KILIT = KOK / ".kilit"` üzerinden aynı `flock` protokolünü ve kilitli task RMW'yi kullanıyor; bunları “kilit yok” diye nitelemiyorum. Fark, canonical v2'nin dosya yolu/lock/schema kontrolleri ile açık schema gate'inin ve release kimliğinin bu kopyalarda bulunmamasıdır. Kilit yalnız aynı inode'a, aynı veri köküne ve tüm yazarların aynı protokole uymasına bağlıdır; tek başına version uyumluluğu veya aktör doğrulaması sağlamaz.

Dev/UI ve restore-check kaynaklarında `schema_version`, `DATA_SCHEMA_VERSION` veya `_schema_version_kontrolu` ifadesi yoktur. `json.dump` alanı mevcut dict'te varsa yazabilir; bu, desteklenmeyen bir sürümde güvenli mutation anlamına gelmez. Kırık/missing schema geçişinin güvenliği için yalnız alanın tesadüfen korunması yeterli değildir.

## Fixture bulguları

`tests/test_cli_copy_compatibility_fixture.py` gerçek task/data kökünü değil, kaynak CLI'ların geçici kopyalarını çalıştırdı:

1. `yuva-dev` ve `yuva-ui-dev` kopyaları schema `99` içeren sentetik defterde `gorev al` mutasyonunu başarıyla yaptı; `schema_version: 99` dosyada kaldı. Bu, değeri korumalarının unsupported schema'yı denetledikleri anlamına gelmediğini gösterir.
2. İki restore-check kaynak hash'i aynı olduğu için her ikisinin geçici kopyası bozuk JSON içeren sentetik defter üzerinde sınandı. `gorev ekle`, fallback boş defter yazıp bozuk içeriği değiştirdi. Gerçek kurtarma kopyalarına dokunulmadı.
3. Eski `yuva/bin/yuva` geçici kopyası CLI guard'ında görevi reddetti; fixture defteri değişmedi.
4. Canonical `yuva-v2/bin/yuva`, geçerli fixture worker durumuyla `schema_version: 99` defterinde yazmayı reddetti; ledger baytları değişmedi.

`tests/test_cli_copy_compatibility_gate.py` ayrıca eksik/yanlış hash, canonical olmayan profil, restore-only kaynak, kilit RMW kanıtı eksik, schema doğrulama/koruma kanıtı eksik veya unsupported sürüm durumlarında reddeden referans gate politikasını sınar. `prototypes/cli-copy-compatibility/gate.py` **yalnız taslak karar fonksiyonudur**; CLI kopyaları tarafından çağrılmaz ve tek başına production binary identity kanıtı oluşturmaz.

Çalıştırma: `python3 -m unittest tests.test_cli_copy_compatibility_fixture tests.test_cli_copy_compatibility_gate -v` — **6 test geçti**.

## Fail-closed kullanım önerisi

- Görev mutasyonlarını yalnız seçilmiş canonical release/hash ve açıkça kabul edilmiş writer contract üzerinden çalıştır. `~/.local/bin/yuva`'nın bugünkü çözümlemesi v2'dir; geliştirme ağacının aynı veriye yazması otomatik release kabulü sayılmaz.
- Writer, `gorevler.json`'ı parse etmeden/işlem uygulamadan önce desteklenen `schema_version`'ı doğrulamalı; unknown, bool, hatalı tür veya gelecek sürümde hiçbir ledger mutasyonu yapmamalı. Yazımda kabul edilen schema alanı korunmalı/eklenmeli. Mevcut v2 kaynağında task/state schema v1'dir; kayıtlı sürüm açıkça `1` olmalıdır.
- Aynı `YUVA_DIR/.kilit` inode'u altında tam oku-doğrula-değiştir-yaz yapılması şarttır; lock alınamazsa veya lock kimliği değişmişse yazım yok. Atomic replace başarıp directory fsync belirsiz kaldığında sonuç unknown bildirilir; kör retry yok.
- `yuva-dev`/`yuva-ui-dev` için schema validator ve canonical release pin eklenene kadar shared ledger mutasyonlarını fail-closed kapat; bunları ancak açıkça fixture veya ayrı data root'ta kullan.
- Restore-check kopyaları read-only kurtarma girdisi olarak kalmalı. Mutasyon altkomutlarını kapat veya yalnız açıkça marker'lı scratch restore alanına, tek seferlik kabul fixture'ı içinde sınırla. JSON parse hatasında default boş ledger ile devam etme; veriyi olduğu gibi koruyup operatör incelemesi iste.
- Referans gate profile'ı caller tarafından verilen boole'lara dayanır; üretimde profile self-attestation kabul edilmemeli. Hash pin'i trusted release manifesti/launcher'dan gelmeli; çalışan binary, lock ve data root aynı release kabul zincirinde doğrulanmalı.

Bu görev PATH/symlink değiştirmedi, herhangi bir CLI kopyasını yamamadı ve canlı task dosyasına yazmadı. Hash'ler bu inceleme anındaki statik dosya snapshot'ıdır; çalışan servis sürecinin o kopyalardan hangisini kullandığını kanıtlamaz.
