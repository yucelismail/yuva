# #459 — `/api/veri` ekran toplam bütçesi

`/api/veri` içindeki mevcut `ekranlar` alanının map şekli korunur; yanına
ekran verisinin kısmi olup olmadığını bildiren `ekranlar_meta` eklenir.

## Bütçeler ve seçim

- Her `/api/veri` çağrısında en fazla **128** ekran dosyası seçilir. Panel
  süreci bir dosya adı cursor'u tutar: sonraki sayfa cursor'dan leksikografik
  olarak sonraki adlarla başlar, 128'den azı kalırsa en küçük adlardan sarar.
  Seçim cursor ve o andaki dizin içeriği için deterministiktir. Cursor yalnız
  istek tarafından gerçekten ele alınan son dosyaya kadar ilerler; ham bayt
  veya parse bütçesi sayfayı erken durdurursa sonraki seçilmemiş dosyalar sonraki
  çağrıda aday kalır. Eşzamanlı çağrı, seçiminden beri cursor değişmişse eski
  cursor'ı ezmez. Cursor süreç belleğindedir ve panel yeniden başladığında ilk
  leksikografik sayfadan başlar.
  Böylece panel çalışırken sabit ilk 128 dosyanın diğerlerini sürekli aç bırakması
  önlenir. Aday belleği bir sayfayla sınırlıdır. Daha fazla dosya varsa yanıt
  yine kısmi sayılır ve `partial_reasons` içinde `file_count_limit` görünür.
  `ekranlar_meta.selection_mode` değeri `round_robin_lexicographic` seçim
  sözleşmesini bildirir.
- Bir dosyadan en fazla **1 MiB**, bütün ekran dosyalarından toplam en fazla
  **8 MiB** JSONL tail okuma bütçesi rezerve edilir. Her dosyanın okuyucusu en
  fazla 60 satır ve 16 KiB/satır alır. Bütçe nedeniyle dosya/tail atlanırsa
  `raw_byte_limit`, `per_file_row_limit` veya `record_size_limit` işaretlenir.
- JSON parser'a verilecek kayıt satırlarının toplamı **2 MiB** ile sınırlıdır.
  `json.loads` öncesi UTF-8 satır baytları sayılır; bütçeyi aşacak sonraki satır
  parse edilmez, `parsed_byte_limit` eklenir ve daha sonraki dosyalara geçilmez.
- `ekranlar` map'inin `json.dumps(..., ensure_ascii=False)` biçimindeki
  serileştirilmiş boyutu **2 MiB** ile sınırlıdır. Bir dosyanın seçilmiş tam
  satır listesi sığmazsa o dosya tümden atlanır (`output_byte_limit`) ve daha
  sonraki dosyalar sayfa sırasıyla değerlendirilir. Bir kayıt veya dosya adı
  UTF-8'e serileştirilemiyorsa dosya tümden atlanır (`serialization_error`);
  bu durum `/api/veri` bağlantısını düşürmez.
- Herhangi bir dosya/tail, satır, kayıt, parse, çıktı veya dizin okuma sınırı
  nedeniyle veri dışarıda kalırsa `ekranlar_meta.partial=true` olur. Nedenler
  sıralı `partial_reasons` listesinde verilir. Hata olsa bile eski `ekranlar`
  alanı map olarak kalır; hiçbir kayıt dönmezse `{}` olur ve metadata nedeni
  açıklar.

Metadata örnek şekli:

```json
{
  "ekranlar": {},
  "ekranlar_meta": {
    "partial": true,
    "files_discovered": 140,
    "files_considered": 128,
    "files_returned": 32,
    "file_limit": 128,
    "selection_mode": "round_robin_lexicographic",
    "raw_bytes_scanned": 8388608,
    "raw_byte_budget_reserved": 8388608,
    "raw_byte_budget": 8388608,
    "parsed_bytes": 2097152,
    "parsed_byte_budget": 2097152,
    "output_bytes": 1900000,
    "output_byte_budget": 2097152,
    "partial_reasons": ["file_count_limit", "parsed_byte_limit"]
  }
}
```

`raw_byte_budget_reserved` okuma için dosya başına ayrılan üst sınırların
toplamıdır; `raw_bytes_scanned` okuyucunun başarıyla rapor ettiği gerçek
okumadır. Dosya okuma hatasında ayrılmış bütçe tüketilmiş sayılır; üst sınır
korunur ve `read_error` kısmi sonucu bildirir. `files_discovered` glob
enumerasyonunda görülen aday sayısıdır; seçilen dosya yolları bellekte en fazla
bir sayfa tutar.

UI ekran başlığında `ekranlar_meta.partial` true ise bütçe kaynaklı kısmi
gösterim uyarısı çıkar. Eski istemciler `ekranlar` map'ini kullanmaya devam
edebilir; metadata alanı geriye uyumlu ek alandır.

## Sınırlar

Bu sınırlar ekran dosyalarının sayısını, tail okumasını, parse input'unu ve
`ekranlar` map'inin JSON boyutunu kapsar. Python nesne overhead'inin kesin heap
boyutu değildir ve `/api/veri` içindeki mesaj/görev/kullanıcı alanlarının
toplam yanıtını sınırlamaz. Her sayfa için dizin adları taranır; aday belleği
bir sayfayla sınırlı olsa da çok büyük bir dizinin enumerasyon CPU süresi ayrıca
sınırsız olabilir. Cursor birden çok panel süreci arasında paylaşılmaz. Bu API
dosya sayısı problemini çözer, genel toplam snapshot/CPU budget'ı değildir.

Bu değişiklik history dosyalarını silmez veya değiştirmez. Tail/response
bütçeleri retention politikası değildir.
