# Ekran redaction yazım yolları bağımsız denetimi (#710)

**Kapsam:** Kaynak bazlı writer envanteri ve sentetik canary regresyonları. Gerçek `YUVA_DIR`, tarihsel chat/screen dosyası, backup veya credential taranmadı; hiçbir gerçek veri değiştirilmedi.

## Yeni yazım girişleri

| Giriş | Çağrı zinciri | Bulgular / sınır |
|---|---|---|
| Panel HTTP `POST /api/ekran` | `api_ekran()` → `ekran_yaz()` → `ekle()` → JSONL append | `ekle()` serialize etmeden önce `redact_screen_record()` çağırır; `ad` ve `satir` redakte edilir. API başarı cevabı yalnız redakte edilmiş `ad` alanını döndürür. Redaction hatası sabit 400 cevabıdır. Beklenmeyen exception HTTP handler'da içeriksiz event ID/type/errno logu ve genel 500 cevabına dönüşür. |
| CLI `yuva ekran ...`, panel POST başarılı | `cmd_ekran()` → `http_iste()` → panel API | CLI ikinci bir yerel append yapmaz; panel write-boundary'si kullanılır. |
| CLI POST kesinlikle gönderilmedi | `cmd_ekran()` → `ekle_jsonl()` → JSONL append | Yalnız `POST_NOT_SENT` transport kanıtında fallback çalışır; CLI ortak redactor çağırır. Redaction exception içeriksiz `VeriHatasi` ile sonlanır, ham fallback yoktur. |
| CLI POST reddedildi veya sonucu belirsiz | `cmd_ekran()` | HTTP rejection yeniden yazılmaz; sonucu belirsiz POST local fallback'e geçmez. HTTP error cevabının CLI hata gösteriminde ham/uygunsuz bir server body taşıyabilmesi farklı bir genel client sınırıdır; mevcut `/api/ekran` redaction hatası sabit, içeriksiz mesaj döndürür. |
| Offline screen migration prototipi | `prototypes/screen-migration/migrate_fixture.py` | Yalnız açıkça işaretli fixture köküne yazar; her satırı ortak redactor'dan geçirir. Canlı veri migration aracı değildir. |
| Tarihsel secret scanner / screen snapshot projection | `prototypes/history-secret-scan/scanner.py`, `prototypes/screen-snapshot-redaction/project_fixture.py` | Yalnız geçici sentetik/marked fixture'ları read-only okur; kalıcı screen writer değildir. `backup_verify.py` de okuma/doğrulama yoludur. |

Kaynak envanterinde üretim ekran JSONL'e doğrudan append yapan iki sınır bulundu: panel `ekle()` ve CLI `ekle_jsonl()`. Başlatmadaki ekran klasörü oluşturma ve ekran snapshot/cursor işlemleri satır yazmaz. Prototip dosya yazımları kendi disposable fixture'larına bağlıdır.

## Yeni fixture kanıtı

`tests/test_screen_redaction.py` API body'sinden gelen sentetik komut ve env canary'lerinin diske, API cevabına veya testin ürettiği JSONL'e taşınmadığını kontrol eder. Mevcut CLI `POST_NOT_SENT` testi bearer/API-key/cookie/credential URL/env canary'lerini iki writer'dan geçirip diskte bulunmadıklarını doğrular. Redactor exception testi her iki writer'da dosya oluşturulmadığını ve exception metninin canary taşımadığını kontrol eder.

`tests/test_panel_error_ephemeral_http.py` gerçek ephemeral HTTP request handler üzerinden `POST /api/ekran` yazım exception'ı enjekte eder. Request body ve exception metninde sentetik command/env değerleri bulunur; 500 cevabı ve stderr event kaydı ham içeriği dışarı vermez. HTTP response header/error contract'ı da sınanır.

Çalıştırmalar:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_screen_redaction -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_error_ephemeral_http -v
```

Sonuç: redaction fixture **6/6**, ephemeral HTTP error fixture **3/3** geçti. HTTP suite ephemeral loopback socket kullandığı için sandbox dışında onayla çalıştırıldı; canlı panel başlatılmadı. `git diff --check` değişiklikli tracked kaynaklarda temiz; yeni test dosyaları unittest ile parse edilip çalıştırıldı.

## Sonuç ve kalan sınırlar

İncelenen source checkout'taki yeni panel/CLI JSONL yazımları ortak fail-closed redactor'dan geçiyor; API/CLI/exception fixture'larında sentetik canary sızıntısı gözlenmedi. Bu, tüm credential türleri için DLP garantisi değildir: regex tabanlı redactor bilinmeyen, parçalı veya kodlanmış değerleri kaçırabilir. Eski writer kopyaları, aynı UID ile doğrudan dosya yazımı, tarihsel JSONL ve backup kapsam dışıdır. #652/#668 tarihsel scanner fixture'ı redacted yeni yazım kontrolünün veya canlı geçmişin temiz olduğunun kanıtı değildir.

Referanslar: `docs/screen-redaction-writer-coverage-634.md`, `docs/screen-secret-redaction-564.md`, `docs/historical-chat-screen-secret-scan-fixture-652.md`, `yuva_screen_redaction.py`, `tests/test_screen_redaction.py`, `tests/test_panel_error_ephemeral_http.py`.
