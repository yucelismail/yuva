# CI artifact ve cache denetimi (#750)

## Kapsam ve yöntem

23 Ekim 2026 tarihinde `.github/workflows/` altındaki workflow dosyaları tarandı. Artifact yükleme/indirme adımları, `actions/cache` kullanımı, `setup-python` cache girdileri ve retention ayarları arandı; bulunan tek workflow olan `ci.yml` ayrıca incelendi.

## Bulgular

- Depoda tek workflow var: `.github/workflows/ci.yml`.
- Workflow’da `upload-artifact`, `download-artifact` veya `actions/cache` adımı yok.
- `actions/setup-python` adımlarında `cache` girdisi tanımlanmamış.
- `retention-days` ya da başka bir artifact saklama süresi ayarı yok; çünkü workflow artifact üretmiyor.
- Sözdizimi denetimi ve unittest komutları sonuçlarını Actions adım çıktısına yazıyor. Bu çıktılar için ayrıca ham log veya dosya artifact’ı yükleyen bir adım bulunmuyor.

## Sonuç

Mevcut workflow gereksiz test logu/artifact’ı veya açıkça yapılandırılmış paket cache’i saklamıyor. Bu nedenle workflow değişikliği ve retention politikası eklenmesi gerekmiyor. İleride bir rapor artifact’ı gerçekten gerekirse, yalnızca temizlenmiş ve sır içermeyen rapor yüklenmeli ve o adıma kısa bir `retention-days` değeri verilmelidir. Ham ekran görüntüsü, sohbet veya veri dosyası yüklenmemelidir.
