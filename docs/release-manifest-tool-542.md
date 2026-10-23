# #542 — Offline release manifest aracı

## Kullanım

Payload, seçilmiş commit'ten ayrı bir scratch dizinine çıkarılır. Örnek komutlar yalnız geçici kaynak ve payload dizinleri kullanır:

```sh
mkdir -p "$SCRATCH_PAYLOAD" "$SCRATCH"
git -C "$SOURCE_REPO" archive --format=tar HEAD | tar -xf - -C "$SCRATCH_PAYLOAD"
python3 release_manifest.py create \
  --repo "$SOURCE_REPO" \
  --payload "$SCRATCH_PAYLOAD" \
  --repository-id "org/yuva" \
  --output "$SCRATCH/manifest.json"
python3 release_manifest.py verify \
  --payload "$SCRATCH_PAYLOAD" \
  --manifest "$SCRATCH/manifest.json" \
  --source-repo "$SOURCE_REPO" \
  --trusted-manifest-sha256 "$PINNED_MANIFEST_SHA256"
```

`create` manifest JSON'unu kanonik sıralama ve ayraçlarla yazar, payload dosyalarını byte/type/mode/symlink olarak envanterler ve full Git commit/tree bilgisini kaydeder. Dirty kaynakta inventory manifest üretilebilir fakat `release_eligible` false olur. Kaynak tanımlanamıyorsa commit/tree null ve uygunluk yine false kalır. Payload'ın Git commit tree'sinden birebir gelmesi ayrıca `payload_matches_source` ile belirtilir. Zorunlu Yuva dosyaları eksikse komut hata verir.

Manifestteki `data_contract.schema_compatibility` değeri
`yuva-data-contract/v1` olur. Bu, #549'da tanımlanan durum/görev JSON v1,
mesaj JSONL legacy/v1/v2 ve sürümsüz ekran JSONL sözleşmesidir. Manifest
kimliği release içeriğiyle hashlenir; rollback kabulü için eski ve yeni
manifest aynı bilinen kimliği taşımalıdır. `unspecified` veya bilinmeyen kimlik
yerel acceptance kararında NO-GO'dur.

Payload digest'i #522'deki beş sütunlu formatla hesaplanır: NFC POSIX path, file type, mode, byte size ve SHA-256; sütunlar NUL ile, kayıtlar LF ile ayrılır. Symlink'in literal target bytes'ı hashlenir, absolute/root dışına çıkan ya da eksik hedefli symlink reddedilir. Extra, missing, duplicate, normalization-colliding, special file, untracked veya Git tree ile farklı mode/content release adayı olarak doğrulanmaz. Submodule payload'ı bu sürümde desteklenmediği için uygunluk üretmez.

`verify` offline olarak manifest canonical serialization'ını, payload file set/hash/mode/type'ını ve —`--source-repo` verilmişse— temiz kaynak commit/tree eşleşmesini denetler. Komut, external pin olmadan yalnız içerik eşleşmesi raporlar ve exit status 1 döndürür. `verified_release=true` için manifest baytlarının SHA-256 değeri dışarıdan güvenilen `--trusted-manifest-sha256` ile birebir eşleşmeli ve temiz kaynak doğrulaması geçmelidir. Pin manifestin içinden okunmaz. Bu araç imza üretmez veya güvenilir pin dağıtmaz; digest'i aynı güven sınırı içinde üretip hemen geri vermek bağımsız güven kanıtı değildir.

## Uygulama sınırları

- Herhangi bir install root, `current` symlink'i, systemd unit'i, `YUVA_DIR` veya canlı veri yazımı yoktur. `create` output dosyası yalnız bir kez, `O_EXCL` ile oluşturulur; mevcut dosya üzerine yazılmaz.
- Release ID, tam Git commit (veya source unknown ise `unknown`) ile tam payload SHA-256 değerini bağlar; manifest hash'i ayrıca external pin için hesaplanabilir.
- Tool release dosyası listesi için repo tree'nin tüm tracked blob/symlink girdilerini kullanır. `.git` metadata'sı payload içinde olmamalıdır. Commit source tree'de gitlink/submodule varsa bu sürüm fail-closed kalır.
- `release_eligible` creator tarafından hiçbir zaman true yazılmaz; ancak offline verifier temiz source + exact payload + dışarıdan pinlenmiş manifest için doğrulanmış sonucu üretebilir. Bu sonuç kurulum, çalışan süreç, writer tekilliği, veri uyumluluğu veya backup doğrulaması değildir.

## Fixture kanıtı

`python3 -m unittest tests.test_release_manifest -v` sonucu **9/9 geçti**. `tests/test_release_manifest.py` geçici Git reposu ve payload ile clean/dirty/unknown source, canonical digest, dış trust pin'i, payload drift, extra/missing entry, escaping symlink ve manifest değişikliği durumlarını sınar. Testler canlı repo/payload veya kurulum kökü kullanmaz.
