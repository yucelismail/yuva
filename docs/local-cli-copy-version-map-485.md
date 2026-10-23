# Yerel CLI ve kopya sürüm haritası (#485)

İnceleme salt okunur yapıldı. Bu not, yalnızca bu shell'de görülen komut çözümlemesini ve kaynak kodundaki davranışı kaydeder; çalışan panel/servis sürecinin hangi kod ağacını kullandığını kanıtlamaz.

## Komut hangi dosyayı seçiyor?

- `yuva` komutunun shell çözümlemesi `~/.local/bin/yuva` giriş noktasını buluyor. Giriş noktası şu anda `yuva-v2/bin/yuva` dosyasına sembolik bağ; dolayısıyla normal `yuva durum` ve `yuva kimler` çağrıları v2 CLI'ını çalıştırıyor.
- `yuva/bin/yuva`, ayrı ve eski yerel kopyadır. Bu dosyayı doğrudan çağırmak eski davranışı seçer; `~/.local/bin/yuva` üzerinden yapılan olağan çağrı bunu seçmiyor.
- `yuva-dev/bin/yuva`, ayrı bir geliştirme çalışma ağacındaki CLI'dır. Mevcut PATH çözümlemesinde seçilmiyor.
- `yuva-v2/bin/yuva` ve `yuva-dev/bin/yuva`, kendi kod köklerini `CODE_ROOT` ile çalıştırılan dosyanın konumundan bulur. Her iki CLI da veri kökünü ayrıca `YUVA_DIR` veya varsayılan `~/yuva` olarak belirler. Bu incelemede `YUVA_DIR` ayarlı değildi. Böylece kod kopyası ve paylaşılan durum/görev verisi birbirinden ayrıdır.

## Kurulum belgesiyle gözlenen bağlantı arasındaki fark

`README.md:87-97` ilk kurulum komutlarında `~/.local/bin/yuva` bağının `~/yuva/bin/yuva` dosyasını göstermesini tarif ediyor ve veri kökü için de `~/yuva` varsayılanını açıklıyor. Gözlenen bağlantı ise `yuva-v2/bin/yuva` dosyasını gösteriyor. Ayrıca bu makinedeki `yuva/` kopyası bir Git çalışma ağacı değil; `yuva-dev/` ve `yuva-v2/` ayrı Git çalışma ağaçları. Dolayısıyla README'deki kurulum tarifi, gözlenen yerel kurulumun hangi sürümü seçtiğini açıklamıyor.

## Presence / stale davranışı

| CLI kopyası | Panel verisi yoksa | Panel kaydı varsa | Kaynak |
| --- | --- | --- | --- |
| Eski `yuva/bin/yuva` | `durum` yerel `bagli` değerini korur; `kimler` panel kullanıcı listesi yoksa yine yerel `bagli` değerine düşer. Eski bir yerel değer yeşil/bağlı görünebilir. | `durum` panel `online` değerini kullanır; taze kalp ve doğrulanmış presence koşulu aramaz. | `yuva/bin/yuva:478-500, 507-522` |
| `yuva-dev/bin/yuva` | `durum` panel kullanıcı kaydı yokken `bilinmiyor` gösterir; `kimler` panel verisi yokken çevrimiçi göstermez. | İki komut da paneldeki `online` boolean'ını doğrudan kullanır; taze kalp ve doğrulanmış presence kontrolü görünmüyor. Eski panel kaydı yeşil kalabilir. | `yuva-dev/bin/yuva:1326-1356, 1363-1380` |
| PATH'in seçtiği `yuva-v2/bin/yuva` | `durum` bilinmiyor veya doğrulanamıyor gösterir; `kimler` panel verisi yok uyarısı verir ve yeşil durum üretmez. | Yeşil için `online is True`, doğrulanmış `presence_state == online` ve eşik içinde taze `son_kalp` birlikte gerekir. Doğrulanmış offline ayrıca gösterilir. | `yuva-v2/bin/yuva:1629-1646, 1659-1699` |

Bu nedenle #482'de raporlanan yerel `bagli` fallback'i mevcut PATH çağrısının davranışı olarak genellenmemeli. Fallback, eski kopya doğrudan seçildiğinde geçerli; mevcut sıradan `yuva` girişi v2 CLI'ına gidiyor. `yuva-dev` ise panel kaydı mevcutken stale `online` boolean'ını kabul edebildiği için v2 ile aynı güvenceyi sağlamıyor.

## Güvenli düzeltme hedefi

Önce tek bir kanonik dağıtım kaynağı belirlenmeli; kurulum belgesi ile `~/.local/bin/yuva` bağlantısı aynı kaynak ağacını tarif etmeli. Presence düzeltmesi gerekiyorsa fail-closed ve taze kalp doğrulaması `yuva-v2/bin/yuva` içindeki CLI davranışı referans alınmalı; eski doğrudan giriş noktası ve geliştirme kopyası da bu sözleşmeyle uyumlu hale getirilmeli veya kullanım dışı oldukları açıkça belirtilmeli. Bağlantı ya da kod değişikliği, hangi panel sunucusunun çalıştığı doğrulanmadan yapılmamalı. Paylaşılan veri kökü (`~/yuva`) kod sürümü sanılmamalı ve bu rapor kapsamında değiştirilmemeli.

## Değişiklik ve kapsam

Yalnızca bu belge eklendi. CLI, panel, symlink ve veri dosyalarında değişiklik yapılmadı; komutlar çalıştırılarak sisteme kayıt yazılmadı.
