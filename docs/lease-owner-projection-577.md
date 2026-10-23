# #577 — Lease sahibi beyanı ve doğrulanmış kimlik projeksiyonu

Bu not ile fixture, gelecekteki lease görünümünde `owner_claim`/`--from`
değerinin nasıl gösterileceğini belirler. Canlı lease kaydı, API veya panel
değişikliği yoktur. `prototypes/lease-presence/projection.py`, yalnızca örnek
snapshot'ı CLI, API ve panel görünüm sözleşmesine yansıtır.

## Mevcut yüzey ve sınır

Üretim CLI/panel henüz `execution` lease alanını kullanmıyor. CLI görev listesi
ve panelin mevcut `assignee` kartı Yuva görev atamasını/profil eşleşmesini
gösterir; lease principal kanıtı değildir. Panel `/api/veri` görev kaydını
taşır. #563 olay zaman çizelgesi `kimden`, olayda saklı rol ve `actor_trust`
değerini gösterebilir; geçmişteki `kimden` `--from` veya başka bir claim ise bu
alan gerçek aktör kimliğine dönüşmez. #532'nin güven sınırında olduğu gibi
`--from`, `kimden`, rol veya presence üzerinden lease sahibi/principal
eşleştirmesi yapılmamalıdır.

## Projeksiyon sözleşmesi

- Lease satırı `Beyan edilen lease sahibi: <owner_claim> · doğrulanmadı` olarak
  etiketlenir. Kaynak zarfta `owner_trust=verified`, `principal_id`, `role`,
  `presence` ya da `authority_scope` bulunsa bile bu prototip owner'a ait
  güven/rol/presence/yetki üretmez; owner `identity_status=unknown`, rol ve
  presence `unknown`, authority scope `none` kalır.
- CLI `--from` ayrı `CLI --from beyanı: <değer> (doğrulanmadı)` satırıdır.
  Kaydedilen history `kimden` de `actor_claim`/`unverified` olarak yansıtılır;
  olayın içindeki `actor_trust` veya `rol` iddiası doğrulama kanıtı sayılmaz.
- API kimlik doğrulama adaptöründen ayrı gelen `verified_request_principal`
  yalnız o isteği yapan principal'ı gösterir. Bu, lease sahibine bağlanmaz;
  API görünümünde `relation_to_lease_owner=not_established` olur. Gelecekte
  bağ için task ID + lease ID + epoch ile eşleşen ayrı, doğrulanmış binding
  olayı gerekir; böyle bir kanıt şu an yoktur.
- Panel metni, doğrulanmış API isteği principal'ını ayrı rozetle gösterir;
  lease satırında “doğrulanmış lease principal yok” der. Kullanıcı roster'ından
  rol/araç adı veya presence alıp owner claim'e yapıştırmaz.
- Bu görünüm hiçbir görev, tool, reviewer, dispatch veya lease yenileme
  yetkisi ifade etmez. UI/API label'ı kimlik doğrulama ya da authorization
  kontrolünün yerine geçmez.

## Sentetik örnek

Girdi snapshot'ı kasıtlı olarak sahte elevated alanlar içerir:

```json
{
  "id": 31,
  "assignee": "worker-claimed",
  "execution": {
    "owner_claim": "worker-claimed",
    "owner_trust": "verified",
    "principal_id": "forged-admin",
    "role": "denetci",
    "presence": "online",
    "authority_scope": "task.approve",
    "lease_epoch": 4
  },
  "gecmis": [{
    "kimden": "worker-claimed", "actor_trust": "verified",
    "rol": "denetci", "olay": "claim"
  }]
}
```

Fixture projeksiyonu ile beklenen metin/alanlar:

| Yüzey | Beklenen gösterim |
|---|---|
| CLI | `Beyan edilen lease sahibi: worker-claimed (doğrulanmadı) · epoch 4`; `--from` ayrıca beyan olarak; kimlik/rol/presence unknown, yetki none |
| API | `lease_owner.owner_claim=worker-claimed`, `claim_trust=unverified`, `verified_principal=null`, `role=unknown`, `presence=unknown`, `authority_scope=none` |
| API istek bağlamı | Adaptör `api-reader`'ı doğrulamışsa `request_actor=api-reader`; `relation_to_lease_owner=not_established` |
| Panel | `Beyan edilen lease sahibi: worker-claimed` + `beyan · doğrulanmadı`; request principal ayrı görünür, owner'a bağlanmaz |
| Geçmiş | `Beyan edilen aktör: worker-claimed`; `actor_trust=unverified`, rol `unknown` |

`tests/test_lease_owner_projection.py` bu örnekteki forged principal/role/
presence/authority alanlarının yok sayıldığını; CLI, API, panel ve history
ifadelerinin claim ile doğrulanmış request principal'ını ayırdığını sınar.
Fixture gerçek HTML render'ı, canlı API veya üretim davranışı kanıtı değildir.
