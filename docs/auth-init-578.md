# #578 — Offline auth store başlangıcı ve custody sınırı

`yuva auth init`, önceden oluşturulmuş özel dizinde boş bir auth-state v2
snapshot'ı ile sabit lock dosyası kuran host-side CLI aracıdır. Komut auth
middleware/panel tarafından çağrılmaz ve HTTP route değildir. Komut adı
“provision” olsa da yalnızca boş store kurar; operatör/agent key'i veya
enrollment üretmez, secret yazmaz/çıktılamaz, `YUVA_AUTH_ENABLED` değerini
değiştirmez, servis başlatmaz ve auth'ı etkinleştirmez.

## Kullanım

```bash
yuva auth init \
  --store-root /var/lib/yuva-auth \
  --instance-id yuva-prod-1 \
  --audience yuva-prod-api
```

Üç parametre de zorunludur; store root mutlak yol olmalı ve önceden var
olmalıdır. Root dizini çalışan UID'ye ait ve tam `0700`, dosya sistemi yolunun
güvenli olması gerekir. Parent bileşenler root/euid sahipliğinde olmalı;
yabancı sahipli parent yalnız sticky-bit koruması varsa kabul edilir (`/tmp`
fixture kullanımı). Root veya lock/store symlink'i, yanlış tür/sahip/izin/link,
geçersiz `instance_id`/`audience`, mevcut store veya eşzamanlı init fail-closed
reddedilir. Var olan auth snapshot'ı üzerine yazılmaz. Snapshot ve stable lock
`0600`; lock başlangıçta boş kalır. Dizin `fsync` sonucu belirsizse
`commit_unknown` bildirilir; root çevrimdışı incelenmeden komut kör tekrar
edilmemelidir.

Başarılı sonuç `version=2`, generation 1 ve boş `keys`, `enrollments`,
`nonces`, `rate_limits` ile sınırlıdır. Bu state tek başına auth başlatamaz;
auth bootstrap için credential kaydı ve ayrı işletim kapıları gerekir.

## Aynı UID custody sınırı

Owner-only izinler aynı UID ile çalışan süreçleri birbirinden ayırmaz. Yuva
agent'ı ile operatör aynı OS UID'sinde çalışıyorsa agent auth root'a erişebilir;
dolayısıyla `operator` principal/key etiketinin yalnız protokolde yazması
bağımsız operatör kimliğini kanıtlamaz. Ayrı OS UID/servis hesabı ve kontrollü
credential teslimi (veya eşdeğer harici secret custody sınırı) kurulup
denetlenene kadar:

- `yuva auth init` operatör anahtarı üretmek/enroll etmek veya operatör
  principal'ı seçmek için kullanılmamalıdır;
- operatör ve agent key'leri aynı UID altında ayrı dosya izinleriyle güvenli
  biçimde ayrılmış kabul edilmemelidir;
- `operator` etiketi doğrulanmış kullanıcı kaynağı olarak kullanılamaz ve
  `YUVA_AUTH_ENABLED=1` için kabul kanıtı sayılamaz.

Key enrollment, ilk admin principal allowlist'i, secret teslimi, recovery ve
auth gate açılışı ayrı yetkilendirme/işletim kararlarıdır. Bu komut bu işleri
yapmaz ve onları onaylamaz. Backup restore veya dış anti-rollback anchor da
kapsam dışıdır; store içindeki generation tek başına rollback kanıtı değildir.

## Fixture kanıtı

`tests/test_auth_init_cli.py` geçici store köklerinde CLI üzerinden başarılı
başlangıcı ve v2 şemasını; root/store/lock izinlerini; tekrar init'te state ve
lock inode'unun korunmasını; root, state ve lock symlink reddini; güvensiz root
modu ile geçersiz audience/instance'ın hiçbir dosya oluşturmamasını denetler.
Testler gerçek servisi veya canlı auth store'u kullanmaz ve key/enrollment
oluşturmaz.
