# Yuva #721 — sentetik Unix socket session fixture

`tests/test_panel_presence_unix_session_fixture.py` geçici dizinde gerçek bir
AF_UNIX stream socket açar ve `SO_PEERCRED` değerlerini sunucunun kabul ettiği
bağlantı FD'sinden okur. Yalnız test sürecinin mevcut UID'si, fixture içindeki
sentetik principal map'ine bağlanır. Hesap/UID, key, servis, broker kurulumu,
panel veya host konfigürasyonu oluşturulmaz/değiştirilmez.

Fixture #676'daki aşağıdaki dar sözleşmeleri sınar:

- İstemci frame'inden bağımsız olarak accepted socket PID/UID'si welcome/session
  kaydına bağlanır; çelişen principal iddiası reddedilir.
- Session; principal, peer, map revision, broker epoch ve expiry ile ilişkilidir.
- Heartbeat yalnız doğru session/epoch/map revision, geçerli session ömrü ve
  artan tam sayı sequence ile kabul edilir. Replay high-water'ı veya gözlem
  zamanını ilerletmez.
- Broker epoch değişikliği, TTL/session expiry ve socket disconnect projection'ı
  `unknown` yapar. Eski epoch heartbeat'i reddedilir.

Çalıştırma:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_panel_presence_unix_session_fixture -v
```

Yerel test ortamında sandbox geçici socket `bind` işlemini engellediğinden,
test aynı komutla sandbox dışında çalıştırıldı. Sonuç: 4 test geçti.

Bu fixture #649'daki iki farklı gerçek UID kabulünü çalıştırmaz ve bu nedenle
UID izolasyonunu kanıtlamaz. Ayrıca production broker/adapter, yetkili session
oluşturma, kalıcı/atomik high-water store, eşzamanlı heartbeat yarışı, map
yayınlama/revoke, service lifecycle veya panel entegrasyonu kanıtı değildir.
Presence production'da `unknown` kalır; bu görev canlı broker, `/api/kalp`, UID,
key, service veya host üzerinde değişiklik yapmamıştır.
